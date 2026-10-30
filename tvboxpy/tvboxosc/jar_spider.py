"""jar 类爬虫运行时（csp_ 前缀源，复刻 Win-box 的 JVM 桥方案）

链路：
  1. 下载配置 spider jar（剥 ;md5; 校验段）
  2. 提取 classes.dex → dex2jar 转换（按 md5 缓存），assets/ 合并进转换产物
     （native 桥 SpiderRunner 靠产物 jar 里的 .so 条目发现 ARM 库）
  3. spawn 常驻 JVM：SpiderRunner --serve <转换产物jar>
  4. stdin JSON 行协议调用；stdout 单行信封 {"id","ok","data","pp"}

classpath 铁律：-cp 只放运行时（stubs → libs → unidbg → native-bridge → spiderrunner），
蜘蛛 jar 只走 SpiderRunner 加载器参数（--serve 后面）。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import zipfile

from .apiconfig import SESSION
from .paths import data_path

# ---------------------------------------------------------------------------
# 运行时资产定位
# ---------------------------------------------------------------------------

def _asset_dir():
    """JVM 运行时资产目录（jvmrt：stubs/libs/unidbg/native-bridge/spiderrunner）"""
    from .paths import APP_BASE
    cand = os.path.join(APP_BASE, "jvmrt")
    if os.path.isdir(cand):
        return cand
    # 开发期回退：build 产物目录
    dev = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "build", "jvmrt")
    if os.path.isdir(dev):
        return dev
    raise RuntimeError("未找到 jvmrt 运行时资产目录")

def _d2j_dir():
    from .paths import APP_BASE
    cand = os.path.join(APP_BASE, "dex-tools-v2.4")
    if os.path.isdir(cand):
        return cand
    dev = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "build", "dex-tools-v2.4")
    if os.path.isdir(dev):
        return dev
    return None

_CACHE_DIR = data_path(".jar_cache")
_JARS_DIR = os.path.join(_CACHE_DIR, "jars")
_CONV_DIR = os.path.join(_CACHE_DIR, "converted")
_NATIVE_DIR = os.path.join(_CACHE_DIR, "native")
_WORK_DIR = os.path.join(_CACHE_DIR, "work")

_lock = threading.Lock()
_jvms = {}   # jar md5 -> JarSpider（同一转换产物共用一个常驻 JVM）


def _find_java():
    import shutil
    c = shutil.which("java")
    if c:
        return c
    raise RuntimeError("未找到 java 运行时（jar 类爬虫需要 JDK/JRE 17+）")


def _runtime_cp():
    rt = _asset_dir()
    parts = [os.path.join(rt, "stubs.jar")]
    libs = sorted(
        os.path.join(rt, "libs", f) for f in os.listdir(os.path.join(rt, "libs"))
        if f.endswith(".jar"))
    parts += libs
    for n in ("native-bridge.jar", "spiderrunner.jar"):
        p = os.path.join(rt, n)
        if os.path.isfile(p):
            parts.append(p)
    return ";".join(parts)


def _strip_md5(url):
    """剥掉 tvbox spider 地址的 ;md5;hash 校验段"""
    return re.sub(r";md5;[0-9A-Fa-f]{32}$", "", url or "")


def _download_jar(url):
    """下载（或命中本地缓存）spider jar，返回本地路径"""
    os.makedirs(_JARS_DIR, exist_ok=True)
    name = os.path.basename(url.split("?")[0]) or "spider.jar"
    path = os.path.join(_JARS_DIR, name)
    if os.path.isfile(path) and os.path.getsize(path) > 1024:
        return path
    if not re.match(r"^https?://", url):
        if os.path.isfile(url):
            shutil.copyfile(url, path)
            return path
        raise RuntimeError(f"spider jar 不存在: {url}")
    r = SESSION.get(url, timeout=60, verify=False, stream=True)
    if r.status_code != 200:
        raise RuntimeError(f"spider jar 下载失败 http {r.status_code}: {url}")
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    os.replace(tmp, path)
    return path


def _convert(jar_path):
    """提取 classes.dex → dex2jar 转换；返回转换产物 jar 路径（含缓存）"""
    with open(jar_path, "rb") as f:
        md5 = hashlib.md5(f.read()).hexdigest().upper()
    os.makedirs(_CONV_DIR, exist_ok=True)
    out = os.path.join(_CONV_DIR, md5 + ".jar")
    ok_stamp = out + ".ok"
    if os.path.isfile(out) and os.path.isfile(ok_stamp):
        return out

    # 提取 classes.dex 与 assets/
    dex_tmp = out + ".dex"
    with zipfile.ZipFile(jar_path) as z:
        names = z.namelist()
        if "classes.dex" in names:
            with z.open("classes.dex") as s, open(dex_tmp, "wb") as d:
                shutil.copyfileobj(s, d)
        assets = [(n, z.read(n)) for n in names if n.startswith("assets/")]

    # dex2jar 转换（产物目录已有 Bee 等缓存时跳过）
    lock_for = out + ".lock"
    if os.path.isfile(lock_for):
        for _ in range(240):  # 别的进程在转，最多等 4 分钟
            if os.path.isfile(ok_stamp):
                return out
            import time
            time.sleep(1)
    open(lock_for, "w").close()
    try:
        if os.path.isfile(out):
            os.remove(out)
        if os.path.isfile(ok_stamp):
            os.remove(ok_stamp)
        d2j = _d2j_dir()
        if dex_tmp and os.path.isfile(dex_tmp) and d2j:
            bat = os.path.join(d2j, "d2j-dex2jar.bat")
            subprocess.run(
                [bat, "--force", "-o", out, dex_tmp],
                check=True, capture_output=True, timeout=300,
                env={**os.environ, "JAVA_OPTS": "-Xmx1g"})
        elif dex_tmp and os.path.isfile(dex_tmp):
            raise RuntimeError("dex2jar 工具缺失，无法转换 dex")
        else:
            # 纯 java jar（无 dex）—— 直接用原 jar 当加载产物
            shutil.copyfile(jar_path, out)
        # assets/ 合并进产物（.so 等 native 资源供 SpiderRunner 发现）
        if assets:
            with zipfile.ZipFile(out, "a") as zo:
                existing = set(zo.namelist())
                for n, data in assets:
                    if n not in existing:
                        zo.writestr(n, data)
        open(ok_stamp, "w").write(md5)
        return out
    finally:
        try:
            os.remove(lock_for)
        except OSError:
            pass
        if os.path.isfile(dex_tmp):
            os.remove(dex_tmp)


class JarSpider:
    """一个转换产物 jar 一个常驻 JVM；站点类名/ext 走 JSON 行协议"""

    def __init__(self, conv_jar):
        self.conv_jar = conv_jar
        self._proc = None
        self._lock = threading.RLock()
        self._next_id = 1
        self._log_tail = []

    # ---------- 进程 ----------
    def _ensure(self):
        if self._proc and self._proc.poll() is None:
            return
        java = _find_java()
        # 壳守卫会把解密配置写到「当前盘根:\data\data\com.winbox\...」且置只读；
        # 预建目录 + 每次启动前去只读，否则 FileOutputStream 直接拒绝访问
        try:
            import stat
            root = os.path.abspath(os.sep)
            sharedb = os.path.join(root, "data", "data", "com.winbox",
                                   "cache", "code_cache", "sharedb")
            os.makedirs(sharedb, exist_ok=True)
            db = os.path.join(sharedb, "config.db")
            if os.path.isfile(db):
                os.chmod(db, stat.S_IWRITE)
        except OSError:
            pass
        os.makedirs(_NATIVE_DIR, exist_ok=True)
        os.makedirs(_WORK_DIR, exist_ok=True)
        # 运行时 dex2jar（壳解密出内层 dex 后由 stub DexClassLoader 转换加载）
        d2j_dir = _d2j_dir()
        runtime_dex = os.path.join(_CACHE_DIR, "runtime-dex")
        os.makedirs(runtime_dex, exist_ok=True)
        d2j_props = []
        if d2j_dir:
            d2j_libs = ";".join(sorted(
                os.path.join(d2j_dir, "lib", f)
                for f in os.listdir(os.path.join(d2j_dir, "lib")) if f.endswith(".jar")))
            java_exe = java if os.path.isfile(java) else java + ".exe"
            d2j_props = [
                "-Dtvbox.d2j.java=" + java_exe,
                "-Dtvbox.d2j.cp=" + d2j_libs,
                "-Dtvbox.d2j.cache=" + runtime_dex,
            ]
        self._proc = subprocess.Popen(
            [java, "-Xmx1g",
             # JDK 模块封装放行（Win-box 实测必需：壳混淆 VM 的反射深拷贝、
             # unidbg 反射代理 setAccessible，否则守卫握手带崩）
             "--add-opens=java.base/java.lang=ALL-UNNAMED",
             "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED",
             "--add-opens=java.base/java.lang.invoke=ALL-UNNAMED",
             "--add-opens=java.base/java.util=ALL-UNNAMED",
             "--add-opens=java.base/java.util.concurrent=ALL-UNNAMED",
             "--add-opens=java.base/java.io=ALL-UNNAMED",
             "--add-opens=java.base/java.net=ALL-UNNAMED",
             "--add-opens=java.base/java.nio=ALL-UNNAMED",
             "--add-opens=java.base/java.security=ALL-UNNAMED",
             "--add-opens=java.base/java.text=ALL-UNNAMED",
             "--add-opens=java.base/sun.net.www.protocol.jar=ALL-UNNAMED",
             "-Dfile.encoding=UTF-8",
             "-Dsun.stdout.encoding=UTF-8", "-Dsun.stderr.encoding=UTF-8",
             "-Dtvbox.native.debug=1",
             "-Dtvbox.native.patch=" + _NATIVE_DIR,
             "-Dtvbox.native.work=" + _NATIVE_DIR,
             "-Dtvbox.spiderCacheDir=" + _WORK_DIR,
             ] + d2j_props + [
             "-cp", _runtime_cp(),
             "SpiderRunner", "--serve", self.conv_jar],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace")
        self._log_tail = []
        threading.Thread(target=self._err_reader, args=(self._proc.stderr,),
                         daemon=True).start()
        ping = self._call("__ping__", [], timeout=120)
        if not ping.get("ok"):
            raise RuntimeError("JVM 启动失败: " + str(ping.get("data")))

    def _err_reader(self, stream):
        for line in stream:
            self._log_tail.append(line.rstrip())
            del self._log_tail[:-4000]

    def _call(self, method, args, timeout=120, cls="probe.Probe"):
        with self._lock:
            self._ensure()
            rid = self._next_id
            self._next_id += 1
            req = json.dumps({"id": str(rid), "method": method,
                              "className": cls, "args": args},
                             ensure_ascii=False)
            try:
                self._proc.stdin.write(req + "\n")
                self._proc.stdin.flush()
            except (OSError, ValueError):
                self._proc = None
                self._ensure()
                self._proc.stdin.write(req + "\n")
                self._proc.stdin.flush()
            deadline = timeout
            line = self._proc.stdout.readline()
            while line and not line.strip():
                line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError("JVM 无响应（可能是启动失败）\n" +
                                   "\n".join(self._log_tail[-10:]))
            try:
                env = json.loads(line)
            except json.JSONDecodeError:
                raise RuntimeError("JVM 信封解析失败: " + line[:200])
            if env.get("id") != str(rid):
                raise RuntimeError(f"信封 id 不匹配: {env}")
            return env

    # ---------- 站点调用（对外） ----------
    def _site_call(self, cls, method, ext, rest, timeout=120):
        """SpiderRunner 协议：args[0]=ext（init 消费），后续为真实参数"""
        env = self._call(method, [ext] + list(rest), timeout=timeout, cls=cls)
        if not env.get("ok"):
            raise RuntimeError(f"{cls}.{method}: {env.get('data')}")
        data = env.get("data") or ""
        try:
            return json.loads(data) if data else {}
        except json.JSONDecodeError:
            return data

    def warm(self, cls, ext):
        env = self._call("__warm__", [ext], timeout=600, cls=cls)
        if not env.get("ok"):
            raise RuntimeError(f"预热失败 {cls}: {env.get('data')}")


def _ext_str(ext):
    if ext is None:
        return ""
    if isinstance(ext, dict):
        return json.dumps(ext, ensure_ascii=False)
    return str(ext)


def _class_name(api):
    """csp_DouDouGuard → com.github.catvod.spider.DouDouGuard"""
    short = str(api)[4:] if str(api).startswith("csp_") else str(api)
    return "com.github.catvod.spider." + short


def get_jar_spider(bean):
    """按 SourceBean 取（并缓存）jar 类爬虫站点代理"""
    from .apiconfig import api_config
    jar_url = getattr(bean, "jar", None) or api_config.spider
    if not jar_url:
        raise RuntimeError(f"站点 {bean.key} 未配置 spider jar")
    jar_url = _strip_md5(jar_url)
    with _lock:
        jar_path = _download_jar(jar_url)
        conv = _convert(jar_path)
        js = _jvms.get(conv)
        if js is None:
            js = JarSpider(conv)
            _jvms[conv] = js
        return _SiteProxy(js, _class_name(bean.api), _ext_str(bean.ext))


class _SiteProxy:
    """把 (JVM, 类名, ext) 组合暴露成与 Spider 相同的方法面"""

    def __init__(self, js, cls, ext):
        self.js = js
        self.cls = cls
        self.ext = ext

    def home_content(self, filtr=True):
        return self.js._site_call(self.cls, "homeContent", self.ext, [])

    def home_video_content(self):
        return self.js._site_call(self.cls, "homeVideoContent", self.ext, [])

    def category_content(self, tid, pg, filtr, extend):
        if isinstance(extend, dict):
            extend = "&".join(f"{k}={v}" for k, v in extend.items() if v)
        return self.js._site_call(self.cls, "categoryContent", self.ext,
                                  [str(tid), str(pg), extend or ""])

    def detail_content(self, ids):
        # 原版语义：csp_ 源的 vod_id 可能是 "msearch:###片名###图片@..." —— 转搜索
        ids = [str(i) for i in ids]
        if ids and ids[0].startswith("msearch:"):
            parts = ids[0].split("###")
            wd = parts[1] if len(parts) > 1 else ""
            return self.search_content(wd)
        return self.js._site_call(self.cls, "detailContent", self.ext,
                                  [",".join(ids)])

    def search_content(self, key, quick=False):
        return self.js._site_call(self.cls, "searchContent", self.ext,
                                  [str(key), "1"])

    def player_content(self, flag, id, vip_flags=None):
        vips = ",".join(vip_flags) if vip_flags else ""
        return self.js._site_call(self.cls, "playerContent", self.ext,
                                  [flag or "", str(id), vips])


def shutdown():
    with _lock:
        for js in _jvms.values():
            try:
                if js._proc and js._proc.poll() is None:
                    try:
                        js._proc.stdin.write("quit\n")
                        js._proc.stdin.flush()
                    except (OSError, ValueError):
                        pass
                    try:
                        js._proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        js._proc.kill()
            except OSError:
                pass
        _jvms.clear()
