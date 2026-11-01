"""推送页 PushActivity 复刻：本地 HTTP 服务接收推送 + 播放

对应原版 RemoteServer(9978端口)：手机浏览器访问 http://TV的IP:9978
输入视频链接提交 → 电视端列表出现 → 选中播放
"""
import base64
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import socket
import threading
import tkinter as tk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from . import apiconfig, ui_thread
from .paths import APP_BASE
from .player import MpvPlayer
from .theme import BG, FG, FG_DIM, ACCENT, FocusLabel, tv_font, PANEL, POSTER_BG

PORT = 9978
_UPLOAD_DIR = os.path.join(APP_BASE, "upload")

# 全局常驻推送服务状态（对应 Java ControlManager.startServer 主页即启动）
PUSHED = []            # [(title, url)]
_SERVER = [None]
_PORT = [PORT]         # 实际监听端口（9978 被占用时向后顺延，对应原版 9978-9999）
_UI_CB = [None]        # 推送页注册的刷新回调

# 远程动作注册表（对应原版 /action 指令；只允许页面主动注册的函数）
ACTIONS = {}


def register_action(name, fn):
    ACTIONS[name] = fn


def unregister_action(name, fn=None):
    if fn is None or ACTIONS.get(name) is fn:
        ACTIONS.pop(name, None)


def _safe_filename(name):
    """上传文件名消毒：只取 basename，去掉路径分隔符和控制字符"""
    name = unquote(str(name or ""))
    name = os.path.basename(name.replace("\\", "/")).strip()
    name = re.sub(r'[\x00-\x1f<>:"|?*]', "_", name)
    return name[:120] or "upload.bin"


def _local_file(rel):
    """把 /file/<rel> 解析成 APP_BASE 内的真实文件；越界/不存在返回 None"""
    rel = unquote(str(rel or "")).strip().lstrip("/\\")
    if not rel:
        return None
    root = os.path.realpath(APP_BASE)
    full = os.path.realpath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        return None
    return full if os.path.isfile(full) else None


def _parse_multipart(raw, boundary):
    """解析 multipart/form-data 里的文件字段 → [(filename, bytes)]"""
    if not boundary:
        return []
    out = []
    for part in raw.split(b"--" + boundary):
        if part.startswith(b"--"):
            break
        part = part.lstrip(b"\r\n")
        head, sep, body = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        text = head.decode("utf-8", "replace")
        m = re.search(r'filename="([^"]*)"', text)
        if not m or not m.group(1):
            continue
        if body.endswith(b"\r\n"):
            body = body[:-2]
        out.append((m.group(1), body))
    return out


def server_port():
    """本地服务实际端口；未启动时返回默认端口"""
    return _PORT[0]


def proxy_base():
    """本地代理根地址，带结尾 /（对应 ControlManager.getAddress(true)）"""
    return "http://127.0.0.1:%d/" % server_port()


def _notify_ui(msg):
    if _UI_CB[0]:
        ui_thread.run(lambda: _UI_CB[0](msg))


def start_global_server():
    """启动全局推送服务（只启动一次，页面开关不影响）"""
    if _SERVER[0] is not None:
        return
    import urllib.parse as _up

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, body, code=200):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send(self, code, ctype, body, headers=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            for key, val in (headers or {}).items():
                self.send_header(key, val)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _json(self, data, code=200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(code, "application/json; charset=utf-8", body)

        def _read_body(self, limit=200 * 1024 * 1024):
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
            except ValueError:
                return b""
            if length <= 0 or length > limit:
                return b""
            return self.rfile.read(length)

        def _handle_action(self, params):
            """远程动作（对应原版 ControlManager.onActionReceived）"""
            name = (params.get("do", [""])[0] or "").strip().lower()
            if not name:
                self._json({"ok": False, "error": "missing do"}, 400)
                return
            fn = ACTIONS.get(name)
            if fn is None:
                self._json({"ok": False, "error": "unknown action",
                            "actions": sorted(ACTIONS)}, 404)
                return
            ui_thread.run(fn)
            self._json({"ok": True, "do": name})

        def _handle_upload(self):
            """手机上传文件（multipart 或带 X-Filename 的原始 body）"""
            ctype = self.headers.get("Content-Type", "") or ""
            raw = self._read_body()
            if not raw:
                self._json({"ok": False, "error": "empty body"}, 400)
                return
            m = re.search(r'boundary="?([^";]+)"?', ctype)
            files = _parse_multipart(raw, m.group(1).encode() if m else None)
            if not files:
                name = _safe_filename(self.headers.get("X-Filename")
                                      or "upload.bin")
                files = [(name, raw)]
            try:
                os.makedirs(_UPLOAD_DIR, exist_ok=True)
                saved = []
                for filename, data in files:
                    if not data:
                        continue
                    name = _safe_filename(filename)
                    dest = os.path.join(_UPLOAD_DIR, name)
                    base, ext = os.path.splitext(name)
                    i = 1
                    while os.path.exists(dest):   # 同名不覆盖
                        dest = os.path.join(_UPLOAD_DIR, f"{base}_{i}{ext}")
                        i += 1
                    with open(dest, "wb") as f:
                        f.write(data)
                    saved.append(os.path.basename(dest))
                    PUSHED.insert(0, ("上传：" + os.path.basename(dest), dest))
                    del PUSHED[20:]
            except OSError as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
                return
            _notify_ui("收到文件上传：%s" % "、".join(saved[:3]))
            self._json({"ok": True, "files": saved})

        def _handle_doh(self, parsed, body=None):
            """DoH 转发（播放器不支持 DoH 时用；默认阿里 223.5.5.5）"""
            import requests as _rq
            if body is None:
                qs = parse_qs(parsed.query)
                dns = qs.get("dns", [""])[0]
                if not dns:
                    self._send(400, "text/plain", b"missing dns")
                    return
                try:
                    body = base64.urlsafe_b64decode(dns + "=" * (-len(dns) % 4))
                except (ValueError, TypeError):
                    self._send(400, "text/plain", b"bad dns")
                    return
            try:
                r = _rq.post("https://223.5.5.5/dns-query", data=body,
                             timeout=8, verify=False,
                             headers={"Content-Type": "application/dns-message",
                                      "Accept": "application/dns-message"})
            except _rq.RequestException as exc:
                self._send(502, "text/plain; charset=utf-8",
                           ("doh error: %s" % exc).encode())
                return
            self._send(r.status_code, "application/dns-message", r.content)

        def _handle_proxy_m3u8(self, params):
            """m3u8 代理（对应原版 /proxyM3u8）：重写分片地址走本地代理"""
            import requests as _rq
            from . import local_proxy
            url = unquote(params.get("url", [""])[0])
            if not url.startswith(("http://", "https://")):
                self._send(400, "text/plain", b"invalid url")
                return
            ua = {"User-Agent": "Mozilla/5.0"}
            try:
                r = _rq.get(url, timeout=15, verify=False, headers=ua)
                r.raise_for_status()
                text = local_proxy.rewrite_m3u8(r.text, r.url or url,
                                                proxy_base(), ua)
            except Exception as exc:
                self._send(502, "text/plain; charset=utf-8",
                           ("proxyM3u8 error: %s" % exc).encode())
                return
            self._send(200, "application/vnd.apple.mpegurl",
                       text.encode("utf-8"))

        def _handle_cache(self, params):
            """图片/爬虫缓存状态；?action=clear 清空"""
            from .paths import data_path
            cache_dir = data_path(".imgcache")
            action = (params.get("action", [""])[0] or "").lower()
            cleared = files = size = 0
            try:
                names = os.listdir(cache_dir)
            except OSError:
                names = []
            for name in names:
                p = os.path.join(cache_dir, name)
                try:
                    if os.path.isfile(p):
                        files += 1
                        size += os.path.getsize(p)
                        if action in ("clear", "clean"):
                            os.remove(p)
                            cleared += 1
                    elif os.path.isdir(p) and action in ("clear", "clean"):
                        shutil.rmtree(p, ignore_errors=True)
                        cleared += 1
                except OSError:
                    continue
            self._json({"ok": True, "action": action, "files": files,
                        "size": size, "cleared": cleared})

        def _serve_file(self, rel):
            """在 APP_BASE 内按相对路径提供本地文件（防目录穿越）"""
            full = _local_file(rel)
            if full is None:
                self._send(404, "text/plain; charset=utf-8", b"not found")
                return
            try:
                with open(full, "rb") as f:
                    body = f.read(64 * 1024 * 1024)
            except OSError:
                self._send(500, "text/plain; charset=utf-8", b"read error")
                return
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            self._send(200, ctype, body)

        def _handle_proxy(self, params):
            """播放代理（对应 util/Proxy.java 的 /proxy 路由）"""
            from . import local_proxy
            try:
                code, ctype, body, headers = local_proxy.handle(params, proxy_base())
            except Exception as exc:
                code, ctype, body, headers = 500, "text/plain; charset=utf-8", \
                    ("proxy error: %s" % exc).encode("utf-8"), {}
            self._send(code, ctype, body, headers)

        def _handle_push(self, url, title):
            if not url.startswith(("http", "rtmp", "rtp", "udp")):
                self._reply("<h2>链接无效</h2>".encode(), 400)
                return
            PUSHED.insert(0, (title, url))
            del PUSHED[20:]
            _notify_ui(f"收到推送：{title}")
            self._reply("<html><body style='text-align:center'>"
                        "<h2>推送成功！请在电视上查看</h2></body></html>".encode())

        def _handle_api(self, url):
            """远程换源（对应 Java onApiReceived）"""
            _notify_ui(f"收到远程配置：{url[:40]}")

            def ok():
                def apply():
                    from . import data_api, hawk
                    data_api.clear_caches()
                    first = apiconfig.api_config.source_key_list[0] \
                        if apiconfig.api_config.source_key_list else ""
                    hawk.put(hawk.HOME_SOURCE, first)
                    _notify_ui("远程换源成功")
                ui_thread.run(apply)
            apiconfig.api_config.load(url, ok_cb=ok)
            self._reply("<h2>配置已提交</h2>".encode())

        def _dispatch(self, params):
            url = unquote(params.get("url", [""])[0])
            title = unquote(params.get("title", ["手机推送"])[0])
            if params.get("do", [""])[0] == "api" or \
                    self.path.startswith("/api"):
                self._handle_api(url)
            else:
                self._handle_push(url, title)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            params = parse_qs(parsed.query)
            if path == "/proxy":
                self._handle_proxy(params)
            elif path == "/proxyM3u8":
                self._handle_proxy_m3u8(params)
            elif path == "/dns-query":
                self._handle_doh(parsed)
            elif path == "/cache":
                self._handle_cache(params)
            elif path == "/action":
                self._handle_action(params)
            elif path in ("/file", "/media") or \
                    path.startswith(("/file/", "/media/")):
                rel = path.split("/", 2)[2] if path.count("/") >= 2 else ""
                self._serve_file(rel or params.get("path", [""])[0])
            elif path.startswith(("/push", "/api")):
                self._dispatch(params)
            else:
                self._reply(_FORM)

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/upload":
                self._handle_upload()
                return
            if path == "/dns-query":
                self._handle_doh(parsed, body=self._read_body(65535))
                return
            raw = self._read_body().decode("utf-8", "replace")
            ctype = self.headers.get("Content-Type", "")
            if "json" in ctype:  # 原版 App 的 JSON 协议 {"do":"push","url":..}
                try:
                    data = json.loads(raw)
                    params = {k: [str(v)] for k, v in data.items()}
                except (json.JSONDecodeError, AttributeError):
                    params = {}
            else:
                params = parse_qs(raw)
            if path == "/action":
                self._handle_action(params)
                return
            if params.get("do", [""])[0] == "api" and \
                    not path.startswith("/push"):
                self._handle_api(params.get("url", [""])[0])
            else:
                self._dispatch(params)

        def log_message(self, *a):
            pass

    def run():
        # 端口被占用时向后顺延（对应原版 RemoteServer 9978→9999 的自增重试）
        for port in range(PORT, PORT + 22):
            try:
                server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
            except OSError:
                continue
            _PORT[0] = port
            _SERVER[0] = server
            server.serve_forever()
            return
    threading.Thread(target=run, daemon=True).start()


_FORM = ("<html><head><meta charset='utf-8'><title>TVBox 推送</title></head>"
         "<body style='text-align:center;max-width:480px;margin:40px auto;font-size:18px'>"
         "<h2>TVBox 推送</h2>"
         "<form action='/push' method='get'>"
         "<input name='title' placeholder='标题(可选)' style='width:100%;padding:8px;margin:6px 0'>"
         "<input name='url' placeholder='视频链接' required style='width:100%;padding:8px;margin:6px 0'>"
         "<button style='width:100%;padding:10px'>推送到电视</button>"
         "</form>"
         "<form action='/upload' method='post' enctype='multipart/form-data'"
         " style='margin-top:24px'>"
         "<input type='file' name='file' style='width:100%;padding:8px;margin:6px 0'>"
         "<button style='width:100%;padding:10px'>上传本地视频</button>"
         "</form>"
         "<form action='/api' method='get' style='margin-top:24px'>"
         "<input name='url' placeholder='接口配置地址(远程换源)' required style='width:100%;padding:8px;margin:6px 0'>"
         "<button style='width:100%;padding:10px'>切换电视上的配置</button>"
         "</form>"
         "<p style='margin-top:24px'>遥控："
         "<a href='/action?do=home'>主页</a> · "
         "<a href='/action?do=live'>直播</a> · "
         "<a href='/action?do=vod'>点播</a> · "
         "<a href='/action?do=search'>搜索</a> · "
         "<a href='/action?do=clear'>清空列表</a></p>"
         "</body></html>").encode()


def _local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if "." in ip and not ip.startswith("127."):
                try:
                    ipaddress.IPv4Address(ip)
                    ips.add(ip)
                except ValueError:
                    pass
    except OSError:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("223.5.5.5", 80))
            ips.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    return sorted(ips)


class Page(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.player = None
        start_global_server()  # 服务全局常驻，进页面只是注册刷新回调
        self._register()

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x")
        FocusLabel(bar, text="← 返回", font=tv_font(12, True),
                   on_select=self._back).pack(side="left", padx=12, pady=6)
        tk.Label(bar, text="推送", bg=BG, fg=FG, font=tv_font(16, True)
                 ).pack(side="left", padx=10)

        self._register_actions()

        ips = _local_ips()
        urls = [f"http://{ip}:{server_port()}" for ip in ips]
        self._url = urls[0] if urls else ""
        tip = "\n".join(urls) or "未获取到局域网 IP"
        info = tk.Frame(self, bg=BG)
        info.pack(pady=8)
        qr_cv = self._make_qr(info, self._url) if self._url else None
        if qr_cv is not None:
            qr_cv.pack(side="left", padx=(0, 18))
        tk.Label(info, text=f"手机扫码，或浏览器打开：\n{tip}\n"
                            f"提交视频链接/文件后，在下方列表选中播放",
                 bg=BG, fg=FG_DIM, font=tv_font(12), justify="left").pack(side="left")

        tools = tk.Frame(self, bg=BG)
        tools.pack(pady=(0, 4))
        FocusLabel(tools, text="📋 剪贴板推送", bg=PANEL, fg=FG, font=tv_font(11),
                   padx=14, pady=6, on_select=self._push_clipboard
                   ).pack(side="left", padx=6)
        FocusLabel(tools, text="🔗 复制服务地址", bg=PANEL, fg=FG,
                   font=tv_font(11), padx=14, pady=6,
                   on_select=lambda: self._copy(self._url)
                   ).pack(side="left", padx=6)

        self.status = tk.Label(self, text="等待推送...", bg=BG, fg=ACCENT,
                               font=tv_font(11))
        self.status.pack()

        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True)
        self._show_list()

        sample = os.path.join(os.path.dirname(__file__), "assets", "sample.wav")
        if os.path.isfile(sample):
            FocusLabel(self, text="▶ 播放内置示例（测试播放器/声音）",
                       bg=POSTER_BG, fg=ACCENT, font=tv_font(12),
                       on_select=lambda: self._play(sample, "内置示例")
                       ).pack(pady=6)

    @property
    def pushed(self):
        """兼容：推送列表已提升为模块级 PUSHED（全局常驻服务共用）"""
        return PUSHED

    # ---------- 推送列表 ----------
    def _register(self):
        """注册全局服务回调：推送到达时刷新列表（离开页面自动注销）"""
        def on_msg(msg):
            if self.winfo_exists():
                self.status.configure(text=msg)
                self._show_list()
        self._cb = on_msg
        _UI_CB[0] = on_msg

    # ---------- 二维码 / 剪贴板 ----------
    def _make_qr(self, parent, text, px=4):
        """用纯 Python 二维码生成服务地址，手机扫码直达"""
        try:
            from . import qr
            matrix, _version, _mask = qr.encode(text)
        except Exception:
            return None
        n = len(matrix)
        pad = 8
        cv = tk.Canvas(parent, width=n * px + pad * 2,
                       height=n * px + pad * 2, bg="#FFFFFF",
                       highlightthickness=0)
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    cv.create_rectangle(pad + x * px, pad + y * px,
                                        pad + (x + 1) * px, pad + (y + 1) * px,
                                        fill="#000000", outline="")
        return cv

    @staticmethod
    def _extract_url(text):
        for token in re.split(r"[\s\"'<>]+", text or ""):
            if token.startswith(("http://", "https://", "rtmp://",
                                 "rtp://", "udp://")):
                return token
        return ""

    def _push_clipboard(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            self.status.configure(text="剪贴板为空")
            return
        url = self._extract_url(text)
        if not url:
            self.status.configure(text="剪贴板里没有可播放的链接")
            return
        PUSHED.insert(0, ("剪贴板推送", url))
        del PUSHED[20:]
        self.status.configure(text="已从剪贴板推送")
        self._show_list()

    def _copy(self, text):
        if not text:
            self.status.configure(text="没有可复制的地址")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status.configure(text=f"已复制：{text}")
        except tk.TclError:
            self.status.configure(text="复制失败")

    # ---------- 远程遥控动作 ----------
    def _register_actions(self):
        self._actions = {
            "home": self._act_home,
            "live": self._act_live,
            "vod": self._act_vod,
            "search": self._act_search,
            "clear": self._act_clear,
        }
        for name, fn in self._actions.items():
            register_action(name, fn)

    def _unregister_actions(self):
        for name, fn in getattr(self, "_actions", {}).items():
            unregister_action(name, fn)
        self._actions = {}

    def _act_home(self):
        self.app.go_home()

    def _act_live(self):
        from .ui_live import Page as LivePage
        self.app.switch(LivePage)

    def _act_vod(self):
        from .ui_grid import Page as GridPage
        self.app.switch(GridPage)

    def _act_search(self):
        from .ui_search import Page as SearchPage
        self.app.switch(SearchPage)

    def _act_clear(self):
        PUSHED.clear()
        try:
            if self.winfo_exists():
                self.status.configure(text="推送列表已清空")
                self._show_list()
        except tk.TclError:
            pass

    def _show_list(self):
        for w in self.body.winfo_children():
            w.destroy()
        if not PUSHED:
            tk.Label(self.body, text="暂无推送内容", bg=BG, fg=FG_DIM,
                     font=tv_font(13)).pack(expand=True)
            return
        btns = []
        for i, (title, url) in enumerate(PUSHED):
            b = FocusLabel(self.body, text=f"▶ {title[:40]}", bg=PANEL, fg=FG,
                           font=tv_font(12), padx=16, pady=8,
                           on_select=lambda u=url, t=title: self._play(u, t))
            b.pack(fill="x", padx=40, pady=4)
            btns.append(b)
        if btns:
            btns[0].focus_set()

    # ---------- 播放 ----------
    def _play(self, url, title):
        for w in self.body.winfo_children():
            w.destroy()
        video = tk.Frame(self.body, bg="#000000", highlightthickness=0)
        video.pack(fill="both", expand=True)
        bar = tk.Frame(self.body, bg="#000000")
        bar.pack(fill="x")
        FocusLabel(bar, text="← 返回列表", font=tv_font(12, True),
                   on_select=self._stop_and_list).pack(side="left", padx=12, pady=6)
        tk.Label(bar, text=title[:40], bg="#000000", fg=FG,
                 font=tv_font(13, True)).pack(side="left", padx=10)
        self.status.configure(text=f"正在播放 {title[:30]}")
        # 每次 _play 都新建 video 容器，旧 mpv 的嵌入窗口已随旧容器销毁，
        # 必须重建播放器实例，否则画面黑屏且无进度
        if self.player:
            self.player.terminate()
            self.player = None
        self.update_idletasks()
        self.player = MpvPlayer(video)
        self.player.play(url)

    def _stop_and_list(self):
        if self.player:
            self.player.terminate()
            self.player = None
        self._show_list()

    def _back(self):
        if self.player:
            self.player.terminate()
            self.player = None
        from .ui_grid import Page as GridPage
        self.app.go_back(GridPage)

    def destroy(self):
        if getattr(self, "_cb", None) is not None and _UI_CB[0] is self._cb:
            _UI_CB[0] = None
        self._unregister_actions()
        if self.player:
            self.player.terminate()
            self.player = None
        super().destroy()
