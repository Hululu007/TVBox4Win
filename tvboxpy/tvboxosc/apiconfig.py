"""ApiConfig 复刻（对应 api/ApiConfig.java + bean/SourceBean.java + bean/ParseBean.java）"""
import json
import os
import threading

import requests

from . import hawk
from .paths import data_path

requests.packages.urllib3.disable_warnings()
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "okhttp/4.9.3"})

STORE_PATH = data_path("tvbox.json")

_AD_HOSTS = set()  # ads 域名拦截（对应 Java AdBlocker）


def clan_to_address(url):
    """clan:// 协议转换（对应 Java clanToAddress）：clan://host/path → http://host/path"""
    if url.startswith("clan://"):
        return "http://" + url[7:]
    return url


def is_ad_host(url):
    for h in _AD_HOSTS:
        if h and h in url:
            return True
    return False


class SourceBean:
    def __init__(self):
        self.key = ""
        self.name = ""
        self.type = 0
        self.api = ""
        self.searchable = 0
        self.quick_search = 0
        self.filterable = 0
        self.player_url = ""
        self.ext = None
        self.jar = None
        self.categories = []

    @classmethod
    def from_json(cls, d):
        b = cls()
        b.key = str(d.get("key", ""))
        b.name = str(d.get("name", ""))
        try:
            b.type = int(d.get("type", 0))
        except (TypeError, ValueError):
            b.type = 0
        b.api = str(d.get("api", ""))
        b.searchable = int(d.get("searchable", 1) or 0)
        b.quick_search = int(d.get("quickSearch", 1) or 0)
        b.filterable = int(d.get("filterable", 1) or 0)
        b.player_url = str(d.get("playUrl", "") or "")
        b.ext = d.get("ext")
        b.jar = d.get("jar")
        b.categories = d.get("categories") or []
        return b

    def is_type012(self):
        return self.type in (0, 1, 2)


class ParseBean:
    def __init__(self, name="", url="", ext=None, flag=0):
        self.name, self.url, self.ext, self.flag = name, url, ext, flag


def fetch_text(url):
    if is_ad_host(url):
        return None
    _FALLBACK_STATUS = (403, 429, 495, 496, 497, 525, 526, 527)  # TLS 指纹被拒等
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=15, verify=False)
            if r.status_code == 200 and r.text:
                r.encoding = "utf-8"
                return r.text
            if r.status_code in _FALLBACK_STATUS:
                # 借鉴 tvboxosc-python app.py：换 UA/客户端特征重试
                try:
                    r2 = requests.get(
                        url, timeout=15, verify=False,
                        headers={"User-Agent": "okhttp/4.12.0"})
                    if r2.status_code == 200 and r2.text:
                        r2.encoding = "utf-8"
                        return r2.text
                except requests.RequestException:
                    pass
        except requests.RequestException:
            pass
    return None


def _strip_comments(text):
    """剥离 JS 风格 // 与 /* */ 注释（TVBox 配置常见），不处理字符串内容"""
    out, i, n = [], 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
        elif c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def extract_json(text):
    """配置文件可能是纯 JSON 或带前后缀文本（对应原版的自动截取）"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        if not text:
            return None
        s, e = text.find("{"), text.rfind("}")
        if 0 <= s < e:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                pass
            try:
                return json.loads(_strip_comments(text[s:e + 1]), strict=False)
            except json.JSONDecodeError:
                return None
    return None


class ApiConfig:
    """对应 ApiConfig 单例：sources / parseBeanList / liveFlag 等"""
    def __init__(self):
        self.source_key_list = []
        self.source_bean_list = []
        self.parse_bean_list = []
        self.spider = None          # spider 地址（jar/js）
        self.wallpaper = None
        self.lives = []             # 直播源配置列表
        self.flags = []
        self.load_lock = threading.Lock()

    def get(self, key) -> SourceBean | None:
        for b in self.source_bean_list:
            if b.key == key:
                return b
        return None

    def load(self, api_url, ok_cb, err_cb=None):
        """对应 ApiConfig.load()：加载并解析配置，回调式（线程内执行）
        网络失败时回退读本地缓存（对应 Java onError 读缓存配置）"""
        def run():
            if not self.load_lock.acquire(blocking=False):
                # 已有加载在跑：静默 return 会让调用方毫无反馈，必须报错
                if err_cb:
                    err_cb("已有配置正在加载，请稍候再试")
                return
            try:
                req_url = clan_to_address(api_url)
                text = fetch_text(req_url)
                from_cache = False
                if text and os.path.basename(req_url) not in ("", "/"):
                    try:
                        with open(STORE_PATH, "w", encoding="utf-8") as f:
                            f.write(text)
                    except OSError:
                        pass
                elif not text:
                    # 回退本地缓存（对应 Java onError → readCache）
                    try:
                        with open(STORE_PATH, encoding="utf-8") as f:
                            text = f.read()
                        from_cache = True
                    except OSError:
                        text = None
                cfg = extract_json(text) if text else None
                if cfg is None:
                    if err_cb:
                        err_cb("配置加载失败" + ("（已无缓存可用）" if from_cache else ""))
                    return
                self._parse(cfg, req_url)
                # 记录历史（对应 ApiHistoryDialogAdapter 数据）
                hist = hawk.get(hawk.API_HISTORY, [])
                if req_url not in hist:
                    hist.insert(0, req_url)
                    hawk.put(hawk.API_HISTORY, hist[:10])
                hawk.put(hawk.HOME_API, req_url)
                self.last_from_cache = from_cache
                if ok_cb:
                    ok_cb()
            except Exception as e:      # 线程里抛异常会静默丢失，转成回调告知界面
                if err_cb:
                    err_cb(f"配置加载异常：{e}")
            finally:
                self.load_lock.release()
        threading.Thread(target=run, daemon=True).start()

    def _parse(self, cfg, base_url=""):
        self.spider = cfg.get("spider")
        if base_url and isinstance(self.spider, str) and self.spider.startswith(("./", "../")):
            from urllib.parse import urljoin
            self.spider = urljoin(base_url, self.spider)
        self.wallpaper = cfg.get("wallpaper")
        self.flags = cfg.get("flags") or []
        self.lives = cfg.get("lives") or []
        # ads 域名拦截（对应 Java parseJson 尾部 AdBlocker.addAdHost）
        _AD_HOSTS.clear()
        for ad in (cfg.get("ads") or []):
            if ad:
                _AD_HOSTS.add(str(ad))
        self.source_bean_list = []
        self.source_key_list = []
        for d in cfg.get("sites", []):
            b = SourceBean.from_json(d)
            if not b.name or not b.api:
                continue
            # 相对路径 js/py 爬虫按配置 base URL 解析（对应 Java URI.resolve）
            if base_url and str(b.api).startswith(("./", "../")):
                from urllib.parse import urljoin
                b.api = urljoin(base_url, b.api)
            if base_url and isinstance(b.ext, str) and b.ext.startswith(("./", "../")):
                from urllib.parse import urljoin
                b.ext = urljoin(base_url, b.ext)
            # jar 字段（站点级 spider jar，csp_ 类源用）
            if base_url and isinstance(b.jar, str) and b.jar.startswith(("./", "../")):
                from urllib.parse import urljoin
                b.jar = urljoin(base_url, b.jar)
            self.source_bean_list.append(b)
            self.source_key_list.append(b.key)
        self.parse_bean_list = []
        for d in cfg.get("parses", []):
            self.parse_bean_list.append(ParseBean(
                str(d.get("name", "")), str(d.get("url", "")),
                d.get("ext"), int(d.get("flag", 0) or 0)))



api_config = ApiConfig()
