"""Spider 运行时 Python 侧封装（对应 spider/Spider.java + CatVodSpider）

通过 Node 子进程 bridge.js 跑 drpy JS 爬虫，stdio JSON-RPC 通信。
每个 site 一个 Spider 进程，懒加载、按需启动、退出时统一回收。
"""
import json
import os
import queue
import re
import subprocess
import sys
import threading

from .apiconfig import fetch_text

def _base_dir():
    import sys
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "tvboxosc")
    return os.path.dirname(__file__)

_RUNTIME_DIR = os.path.join(_base_dir(), "spider_runtime")
_BRIDGE = os.path.join(_RUNTIME_DIR, "bridge.js")
_DRPY = os.path.join(_RUNTIME_DIR, "drpy.js")
from .paths import data_path
_CACHE_DIR = data_path(".spider_cache")

_proc_lock = threading.Lock()
_procs = {}  # key -> Spider
_spawn_locks = {}  # key -> Lock：只让同一站点的启动串行


class SpiderError(Exception):
    pass


class Spider:
    """单个 JS 站点爬虫进程封装"""

    def __init__(self, key, api, ext=None):
        self.key = key
        self.api = api          # 站点 js 地址或本地路径
        self.ext = ext          # 配置里的 ext 字段（附加 js / 参数）
        self._proc = None
        self._lock = threading.RLock()  # 可重入：_call → _ensure → _call(init)
        self._next_id = 1
        self._out_q = queue.Queue()

    # ---------- 进程管理 ----------
    def _site_js_path(self):
        """下载站点 js 到缓存目录，返回本地路径"""
        if os.path.isfile(self.api):
            return self.api
        if not re.match(r"^https?://", self.api):
            # jar 类爬虫（csp_XXX，需 Android dex/Java 运行时），Python 版不支持
            raise SpiderError(
                f"jar 类爬虫站点暂不支持（需 Java 运行时）: {self.api}")
        os.makedirs(_CACHE_DIR, exist_ok=True)
        name = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]", "_", self.key) + ".js"
        path = os.path.join(_CACHE_DIR, name)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            text = fetch_text(self.api)
            if not text or "function" not in text:
                raise SpiderError(f"spider js 下载失败: {self.api}")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return path

    def _ext_js_path(self):
        """ext 字段：可能是本地路径/URL/内联 js，统一落到缓存文件"""
        if not self.ext or not isinstance(self.ext, str):
            return ""
        if os.path.isfile(self.ext):
            return self.ext
        if re.match(r"^https?://", self.ext):
            os.makedirs(_CACHE_DIR, exist_ok=True)
            path = os.path.join(_CACHE_DIR, re.sub(r"[^A-Za-z0-9_.\-]", "_", self.key) + "_ext.js")
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                text = fetch_text(self.ext)
                if not text:
                    raise SpiderError(f"ext js 下载失败: {self.ext}")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            return path
        # 内联 js
        os.makedirs(_CACHE_DIR, exist_ok=True)
        path = os.path.join(_CACHE_DIR, re.sub(r"[^A-Za-z0-9_.\-]", "_", self.key) + "_ext_inline.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.ext)
        return path

    def _ensure(self):
        if self._proc and self._proc.poll() is None:
            return
        node = _find_node()
        site = self._site_js_path()
        self._proc = subprocess.Popen(
            # bridge 参数: <drpy.js> <站点js> <runtime_dir>（站点js 即 ext 文件）
            [node, _BRIDGE, _DRPY, site, _RUNTIME_DIR],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", cwd=_RUNTIME_DIR,
        )
        self._out_q = queue.Queue()
        threading.Thread(target=self._reader, args=(self._proc.stdout,), daemon=True).start()
        # bridge 启动成功时无输出；若加载失败会立刻输出 {"id":0,...} 并退出，
        # 该行会在首次 _call 的 _read_msg 里读到并抛错
        self._call("init", [site])

    def _reader(self, stream):
        for line in stream:
            self._out_q.put(line)
        self._out_q.put(None)  # EOF 标记

    def _read_msg(self, timeout=60):
        line = self._out_q.get(timeout=timeout)
        if line is None:
            raise SpiderError("spider 进程退出")
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"ok": False, "error": "bad json: " + line[:200]}

    def _call(self, method, args, timeout=60):
        with self._lock:
            self._ensure()
            rid = self._next_id
            self._next_id += 1
            req = json.dumps({"id": rid, "method": method, "args": args}, ensure_ascii=False)
            try:
                self._proc.stdin.write(req + "\n")
                self._proc.stdin.flush()
            except (OSError, ValueError):
                # 进程死了，重启重试一次
                self._proc = None
                self._ensure()
                self._proc.stdin.write(req + "\n")
                self._proc.stdin.flush()
            resp = self._read_msg(timeout)
            if resp.get("id") == 0:
                raise SpiderError("spider load: " + str(resp.get("error")))
            if resp.get("id") != rid:
                raise SpiderError(f"响应 id 不匹配: {resp}")
            if not resp.get("ok"):
                raise SpiderError(str(resp.get("error")))
            return resp.get("result")

    # ---------- 对外方法（返回值与 CMS JSON 同构的 dict） ----------
    def home_content(self, filtr=True):
        return json.loads(self._call("home", [filtr]))

    def category_content(self, tid, pg, filtr, extend):
        return json.loads(self._call("category", [str(tid), int(pg), bool(filtr), extend or "{}"]))

    def detail_content(self, ids):
        return json.loads(self._call("detail", [str(ids)]))

    def search_content(self, key, quick=False):
        return json.loads(self._call("search", [str(key), bool(quick)]))

    def player_content(self, flag, id, vip_flags=None):
        # 对应 Java playerContent(playFlag, url, vipParseFlags)，第三参传给 drpy play
        args = [flag or "", str(id)]
        if vip_flags:
            args.append(list(vip_flags))
        return json.loads(self._call("play", args))


def _find_node():
    """找 node：GUI 启动的 .app 只有最小 PATH，所以要显式列常见安装位置"""
    import glob
    import shutil
    home = os.path.expanduser("~")
    cands = [shutil.which("node")]
    if sys.platform == "darwin":
        cands += [
            "/opt/homebrew/bin/node",            # Apple Silicon Homebrew
            "/usr/local/bin/node",               # Intel Homebrew
            os.path.join(home, ".local/bin/node"),
            "/Users/Administrator/.workbuddy/binaries/node/versions/22.22.2-6/node.exe",
        ]
        # nvm / volta 这类版本管理器装的 node
        for pat in (os.path.join(home, ".nvm/versions/node/*/bin/node"),
                    os.path.join(home, ".volta/bin/node"),
                    os.path.join(home, ".workbuddy/binaries/node/versions/*/bin/node")):
            cands += sorted(glob.glob(pat), reverse=True)
    else:
        cands += [
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-6\node.exe",
        ]
    for cand in cands:
        if cand and os.path.isfile(cand):
            return cand
    raise SpiderError("未找到 node 运行时")


def _spawn_lock(key):
    with _proc_lock:
        lk = _spawn_locks.get(key)
        if lk is None:
            lk = _spawn_locks[key] = threading.Lock()
        return lk


def get_spider(bean):
    """按 SourceBean 拿（并缓存）一个 Spider 实例
    api 以 .py 结尾 → py 类爬虫（tvboxosc-python pyramid 运行时同款）
    api 以 csp_ 开头 → jar 类爬虫（JVM 桥，见 jar_spider.py）"""
    if str(bean.api or "").split("?")[0].endswith(".py"):
        from .py_spider import get_py_spider
        return get_py_spider(bean.key, bean.api, bean.ext)
    if str(bean.api or "").startswith("csp_"):
        from .jar_spider import get_jar_spider
        return get_jar_spider(bean)
    with _proc_lock:
        sp = _procs.get(bean.key)
    if sp is not None:
        return sp
    # 构造 Spider 会下载站点 js、拉起 node 子进程并 init（可能耗时数秒乃至超时）。
    # 这段绝不能放在全局锁里：否则切到一个慢站点，会把其它站点的请求全部堵死。
    with _spawn_lock(bean.key):
        with _proc_lock:
            sp = _procs.get(bean.key)
            if sp is not None:
                return sp
        sp = Spider(bean.key, bean.api, bean.ext)
        with _proc_lock:
            _procs[bean.key] = sp
        return sp


def shutdown():
    try:
        from .py_spider import shutdown as _py_shutdown
        _py_shutdown()
    except Exception:
        pass
    try:
        from .jar_spider import shutdown as _jar_shutdown
        _jar_shutdown()
    except Exception:
        pass
    with _proc_lock:
        for sp in _procs.values():
            try:
                if sp._proc and sp._proc.poll() is None:
                    sp._proc.kill()
            except OSError:
                pass
        _procs.clear()
