"""海报图片加载：下载 → 缩放 → PNG 磁盘缓存 → tk.PhotoImage（懒加载线程池）

要点：
- 8 线程 + 线程本地 Session（keep-alive），单图 6s 超时
- 豆瓣多域名镜像兜底：img9 挂了自动换 img1/img2/img3（同路径同一张图）
- 非图片响应（豆瓣防盗链回 HTML）视为失败，继续试镜像
- 失败结果短时黑名单，避免反复重试拖慢队列
"""
import hashlib
import itertools
import os
import queue
import re
import threading
import time
import tkinter as tk

import requests

from . import ui_thread
from .paths import data_path

_CACHE = data_path(".imgcache")
_q = queue.PriorityQueue()  # 小数字先出：当前页面(0) > 其它页面(1) > 预取(2)
_seq = itertools.count()
_started = False
_lock = threading.Lock()
_local = threading.local()

# 失败黑名单：key → 过期时间戳（秒），避免同一坏图反复重试
_FAIL_TTL = 120
_fail_until = {}

# 豆瓣对同 IP 并发很敏感（超了直接回 HTML 软封页），限制并发数
_DOUBAN_SLOTS = threading.Semaphore(4)


class _host_slot:
    """豆瓣域名请求限流（其它站点不受限）"""

    def __init__(self, url):
        self._limit = "doubanio.com" in url

    def __enter__(self):
        if self._limit:
            _DOUBAN_SLOTS.acquire()
        return self

    def __exit__(self, *a):
        if self._limit:
            _DOUBAN_SLOTS.release()
        return False

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")


def _session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": _UA})
        _local.s = s
    return s


def _is_image(data):
    """用魔数判断，比 PIL 解析便宜"""
    if len(data) < 512:
        return False
    head = data[:16]
    return (head[:2] == b"\xff\xd8"                    # JPEG
            or head[:8] == b"\x89PNG\r\n\x1a\n"        # PNG
            or head[:6] in (b"GIF87a", b"GIF89a")      # GIF
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")  # WEBP
            or head[:2] == b"BM")                      # BMP


def fit_photo(photo, max_w=150, max_h=200):
    """海报缩放到格子尺寸（PhotoImage.subsample 整数倍抽样，不引入 PIL 依赖）。

    之前直接用原图尺寸 configure(width=...)，CMS 源原图 247px+，
    六列网格总宽超出视口，最后一列被截掉。
    """
    try:
        w, h = photo.width(), photo.height()
        fx = max(1, -(-w // max_w))
        fy = max(1, -(-h // max_h))
        if fx > 1 or fy > 1:
            photo = photo.subsample(fx, fy)
    except Exception:
        pass
    return photo


def _candidate_urls(url):
    """豆瓣图片多域名镜像：img9 常被软封，优先 img1/2/3（同路径同一张图）"""
    m = re.match(r"(https?)://(img\d+)\.doubanio\.com(/.*)$", url)
    if not m:
        return [url]
    scheme, host, path = m.groups()
    order = [h for h in ("img1", "img2", "img3", "img9") if h != host]
    order.append(host)  # 源给的域名兜底
    return ["%s://%s.doubanio.com%s" % (scheme, h, path) for h in order]


def _worker():
    while True:
        _prio, _seq, (url, headers, size), cb = _q.get()
        try:
            path = _fetch(url, headers, size)
            if path:
                # 注意 c=cb 早绑定：lambda 引用循环变量 cb 会被后续任务覆盖，
                # 导致前面任务的回调全部执行成最后一次的 cb（海报串图/丢失）
                ui_thread.run(lambda p=path, c=cb: c(p))
        except Exception:
            pass


def _fetch(url, headers=None, size=None):
    os.makedirs(_CACHE, exist_ok=True)
    # 缓存键只按 URL：图片内容与请求头无关，UA 变动不该让整库缓存失效
    key = hashlib.md5(url.encode("utf-8")).hexdigest()
    # size=(w,h) 时按目标像素尺寸出图（网格布局需要精确尺寸，缩放交给 PIL）；
    # 不同尺寸各自缓存一份，互不覆盖
    png = os.path.join(_CACHE, "%s_%dx%d.png" % (key, *size)
                       if size else key + ".png")
    if os.path.isfile(png) and os.path.getsize(png) > 0:
        return png
    now = time.time()
    if _fail_until.get(key, 0) > now:
        return None

    raw = os.path.join(_CACHE, key + ".raw")
    if not (os.path.isfile(raw) and os.path.getsize(raw) > 0):
        hdr = dict(headers or {})
        hdr.setdefault("User-Agent", _UA)
        hdr.setdefault("Referer", "/".join(url.split("/")[:3]) + "/")
        data = None
        for cand in _candidate_urls(url):
            try:
                with _host_slot(url):
                    r = _session().get(cand, timeout=(3, 6), verify=False,
                                       stream=True, headers=hdr)
                    if r.status_code != 200:
                        continue
                    body = r.content
                if not _is_image(body):
                    continue  # 豆瓣软封返回 HTML，换镜像再试
                data = body
                break
            except Exception:
                continue
        if data is None:
            _fail_until[key] = now + _FAIL_TTL
            return None
        with open(raw, "wb") as f:
            f.write(data)

    try:
        from PIL import Image, ImageOps
        im = Image.open(raw)
        im = im.convert("RGB")
        if size:
            # 精确适配目标格子：等比缩放 + 居中裁掉多余边（LANCZOS 高质量）
            ImageOps.fit(im, size, Image.LANCZOS).save(png, "PNG")
        else:
            im.thumbnail((260, 350))
            im.save(png, "PNG")
        return png
    except Exception:
        if size:
            # PIL 不可用/坏图：回退到原始整图缓存，由 fit_photo 兜底缩放
            base = os.path.join(_CACHE, key + ".png")
            if os.path.isfile(base) and os.path.getsize(base) > 0:
                return base
        try:
            os.remove(raw)
        except OSError:
            pass
        _fail_until[key] = now + _FAIL_TTL
        return None


def parse_pic(pic):
    """解析 TVBox 海报地址：url@Referer=xxx@User-Agent=yyy → (url, headers)"""
    if not pic:
        return "", {}
    parts = pic.split("@")
    url = parts[0].strip()
    headers = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            k, v = k.strip(), v.strip()
            if k and v:
                headers[k] = v
    if "User-Agent" not in headers:
        headers["User-Agent"] = _UA
    return url, headers


def load(widget_key, url, on_ready, headers=None, priority=1, size=None):
    """异步加载海报；on_ready(path) 会在 UI 线程回调。
    priority：0=当前页面正在显示（最优先），1=普通，2=预取/推荐位
    size=(w,h)：按目标像素尺寸出图（自适应网格用），缺省走 260x350 通用缓存"""
    global _started
    with _lock:
        if not _started:
            for _ in range(10):
                threading.Thread(target=_worker, daemon=True).start()
            _started = True
    _q.put((priority, next(_seq), (url, headers or {}, size),
            lambda p: on_ready(widget_key, p)))


def attach(widget, photo):
    """把 PhotoImage 挂到控件上（替代旧的全局 _keep 字典）。

    tk.Label 只记住 Tk 图像名，不持有 Python 对象；PhotoImage 一旦被 GC，
    Tk 图像随之删除，控件就变成空白。所以引用必须有人持有——挂在控件自己
    身上最合适：控件销毁 → 引用归零 → 图像释放，生命周期天然对齐。

    旧的全局字典按 key 累加，页面 destroy 时无人清理：一张 238x312 海报
    常驻约 307KB，逛几百部片就是上百 MB 不释放。

    只挂引用还不够：imgcache 工作线程可能在回调执行完很久之后才丢掉闭包里
    的最后一个引用，届时 PhotoImage.__del__ 会从工作线程调 Tk 的
    image delete（跨线程，报 "main thread is not in main loop"，且图像对象
    泄漏在 Tk 解释器里）。所以控件销毁时在主线程（<Destroy> 事件）主动删图
    并清空 name，让之后的 __del__ 变成空操作。
    """
    try:
        widget.image = photo
    except (AttributeError, tk.TclError):
        pass

    def _release(_event, photo=photo, widget=widget):
        try:
            widget.image = None
        except Exception:
            pass
        name = getattr(photo, "name", "")
        if name:
            try:
                widget.tk.call("image", "delete", name)
            except tk.TclError:
                pass
            photo.name = ""   # 已删，之后的 __del__ 不再触碰 Tk

    try:
        widget.bind("<Destroy>", _release, add="+")
    except tk.TclError:
        pass
