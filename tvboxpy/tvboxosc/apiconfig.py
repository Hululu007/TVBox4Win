"""ApiConfig 复刻（对应 api/ApiConfig.java + bean/SourceBean.java + bean/ParseBean.java）"""
import json
import os
import re
import socket
import threading
from urllib.parse import urlsplit, urlunsplit

import requests

from . import hawk
from .paths import data_path

requests.packages.urllib3.disable_warnings()
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "okhttp/4.9.3"})

STORE_PATH = data_path("tvbox.json")

_AD_HOSTS = set()  # ads 域名拦截（对应 Java AdBlocker）

# 配置 hosts：域名 → IP/域名（对应 ApiConfig.myHosts + OkGoHelper.CustomDns）
_HOSTS = {}
# 配置 rules：按页面 host 的嗅探规则 / 过滤规则（对应 util/VideoParseRuler）
_HOST_RULES = {}
_HOST_FILTERS = {}
_HOST_AD_REGEX = {}
_HOST_SCRIPTS = {}

_ORIG_GETADDRINFO = socket.getaddrinfo


def _install_hosts_patch():
    """把配置 hosts 挂到进程 DNS 解析上：保留原 Host/SNI，只换解析结果。"""
    def _getaddrinfo(host, port, *args, **kwargs):
        name = host.decode("idna", "ignore") if isinstance(host, bytes) else host
        mapped = _HOSTS.get((name or "").lower().rstrip("."))
        if mapped:
            host = mapped
        return _ORIG_GETADDRINFO(host, port, *args, **kwargs)
    socket.getaddrinfo = _getaddrinfo


_install_hosts_patch()


def host_of(url):
    """取 URL 的 host（小写，无端口）"""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def host_rules(host):
    """页面 host 的嗅探规则；无匹配时回落到 "*"（对应 getHostRules）"""
    return _HOST_RULES.get(host) or _HOST_RULES.get("*")


def host_filters(host):
    """页面 host 的嗅探过滤规则（对应 getHostFilters，无 "*" 回落）"""
    return _HOST_FILTERS.get(host)


def rules_match(url, groups):
    """一组规则里任意一条的全部正则都命中即算视频地址（对应 checkVideoForOneHostRules）"""
    if not url or not groups:
        return False
    for group in groups:
        if group and all(re.search(p, url) for p in group):
            return True
    return False


def filters_match(url, groups):
    """过滤规则命中即丢弃（对应 checkIsFilterForOneHostRules）"""
    if not url or not groups:
        return False
    for group in groups:
        if group and any(re.search(p, url) for p in group):
            return True
    return False


def proxy_base():
    """本地代理服务根地址（带结尾 /），对应 ControlManager.getAddress(true)"""
    from .ui_push import proxy_base as _base
    return _base()


def check_replace_proxy(url):
    """proxy:// 协议 → 本地 /proxy（对应 DefaultConfig.checkReplaceProxy）"""
    if isinstance(url, str) and url.startswith("proxy://"):
        return proxy_base() + "proxy?" + url[len("proxy://"):]
    return url


def apply_host_mapping(url, header=None):
    """把配置 hosts 映射落到最终播放地址。

    mpv 不经过 Python 的 DNS，所以播放地址要直接换成 IP，并补上原 Host 头。
    返回 (url, header dict 或 None)。
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return url, header
    try:
        parts = urlsplit(url)
    except ValueError:
        return url, header
    host = (parts.hostname or "").lower()
    mapped = _HOSTS.get(host)
    if not mapped or mapped == host:
        return url, header
    netloc = mapped
    if parts.port:
        netloc = f"{mapped}:{parts.port}"
    new_url = urlunsplit((parts.scheme, netloc, parts.path, parts.query,
                          parts.fragment))
    headers = dict(header or {})
    headers.setdefault("Host", host)
    return new_url, headers



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
        self.changeable = 1
        self.filterable = 0
        self.player_url = ""
        self.ext = None
        self.jar = None
        self.player_type = -1
        self.timeout = 0
        self.click = ""
        self.style = ""
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
        b.changeable = int(d.get("changeable", 1) or 0)
        b.filterable = int(d.get("filterable", 1) or 0)
        b.player_url = str(d.get("playUrl", "") or "")
        b.ext = d.get("ext")
        b.jar = d.get("jar")
        try:
            b.player_type = int(d.get("playerType", -1))
        except (TypeError, ValueError):
            b.player_type = -1
        try:
            b.timeout = int(d.get("timeout", 0) or 0)
        except (TypeError, ValueError):
            b.timeout = 0
        b.click = str(d.get("click", "") or "")
        b.style = str(d.get("style", "") or "")
        b.categories = d.get("categories") or []
        if b.key.startswith("py_"):
            # 原版对 py_ 站点强制开启筛选（ApiConfig.java:766-770）
            b.filterable = 1
        return b

    def is_type012(self):
        return self.type in (0, 1, 2)


def headers_from(obj):
    """从 JSON 对象/字符串里提取 header/headers（对应 PlayFragment.getHeaders）"""
    if isinstance(obj, str):
        text = obj.strip()
        if not text.startswith("{"):
            return {}
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return {}
    if not isinstance(obj, dict):
        return {}
    out = {}
    for key in ("header", "headers"):
        raw = obj.get(key)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if isinstance(raw, dict):
            for k, v in raw.items():
                out[str(k)] = str(v)
    return out


class ParseBean:
    """解析接口（对应 bean/ParseBean.java）

    type 语义与原版一致：0=WebView 嗅探，1=JSON 接口，2=JSON 扩展，
    3=JSON 聚合，4=SuperParse（嗅探+JSON 并发）。
    """
    def __init__(self, name="", url="", ext=None, type=0):
        self.name, self.url, self.ext = name, url, ext
        self.type = type
        self.headers = headers_from(ext)

    @property
    def flag(self):
        """兼容旧代码里的 flag 字段"""
        return self.type

    def mix_url(self):
        """ext 编码进 URL（对应 ParseBean.mixUrl）"""
        if not self.ext or not isinstance(self.ext, str) or "?" not in self.url:
            return self.url
        import base64
        ext = self.ext.encode("utf-8")
        val = base64.urlsafe_b64encode(ext).decode("ascii")
        idx = self.url.index("?")
        return self.url[:idx + 1] + "cat_ext=" + val + "&" + self.url[idx + 1:]


def fetch_text(url, headers=None, timeout=15, retries=3):
    if is_ad_host(url):
        return None
    _FALLBACK_STATUS = (403, 429, 495, 496, 497, 525, 526, 527)  # TLS 指纹被拒等
    for attempt in range(max(1, retries)):
        try:
            r = SESSION.get(url, timeout=timeout, verify=False,
                            headers=headers or None)
            if r.status_code == 200 and r.text:
                r.encoding = "utf-8"
                return r.text
            if r.status_code in _FALLBACK_STATUS:
                # 借鉴 tvboxosc-python app.py：换 UA/客户端特征重试
                try:
                    fallback = dict(headers or {})
                    fallback["User-Agent"] = "okhttp/4.12.0"
                    r2 = requests.get(url, timeout=timeout, verify=False,
                                      headers=fallback)
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
        """对应 ApiConfig.load()：加载并解析配置，回调式（网络在后台线程）

        回调统一经 ui_thread 回主线程执行：Tk 只允许主线程建/改控件，
        macOS（Tk 9）在后台线程建控件会直接 Bus error 崩溃。"""
        def _ui(cb, *args):
            from . import ui_thread
            if cb:
                ui_thread.run(lambda: cb(*args))

        def run():
            if not self.load_lock.acquire(blocking=False):
                # 已有加载在跑：静默 return 会让调用方毫无反馈，必须报错
                _ui(err_cb, "已有配置正在加载，请稍候再试")
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
                    _ui(err_cb, "配置加载失败" + ("（已无缓存可用）" if from_cache else ""))
                    return
                self._parse(cfg, req_url)
                # 记录历史（对应 ApiHistoryDialogAdapter 数据）
                hist = hawk.get(hawk.API_HISTORY, [])
                if req_url not in hist:
                    hist.insert(0, req_url)
                    hawk.put(hawk.API_HISTORY, hist[:10])
                hawk.put(hawk.HOME_API, req_url)
                self.last_from_cache = from_cache
                _ui(ok_cb)
            except Exception as e:      # 线程里抛异常会静默丢失，转成回调告知界面
                _ui(err_cb, f"配置加载异常：{e}")
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
        self._parse_hosts(cfg)
        self._parse_rules(cfg)
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
            if not isinstance(d, dict):
                continue
            try:
                ptype = int(d.get("type", d.get("flag", 0)) or 0)
            except (TypeError, ValueError):
                ptype = 0
            self.parse_bean_list.append(ParseBean(
                str(d.get("name", "")), str(d.get("url", "")),
                d.get("ext"), ptype))

    def _parse_hosts(self, cfg):
        """配置 hosts：域名=IP（对应 ApiConfig.java:856-866）"""
        _HOSTS.clear()
        for entry in (cfg.get("hosts") or []):
            if not isinstance(entry, str):
                continue
            parts = entry.split("=", 1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                _HOSTS[parts[0].strip().lower().rstrip(".")] = parts[1].strip()

    def _parse_rules(self, cfg):
        """嗅探/过滤/广告规则（对应 ApiConfig.java:868-933 + VideoParseRuler）"""
        _HOST_RULES.clear()
        _HOST_FILTERS.clear()
        _HOST_AD_REGEX.clear()
        _HOST_SCRIPTS.clear()

        def _str_list(raw):
            return [str(x) for x in raw] if isinstance(raw, list) else []

        for obj in (cfg.get("rules") or []):
            if not isinstance(obj, dict):
                continue
            host = str(obj.get("host", "") or "")
            if host:
                rules = _str_list(obj.get("rule"))
                if rules:
                    _HOST_RULES.setdefault(host, []).append(rules)
                filters = _str_list(obj.get("filter"))
                if filters:
                    _HOST_FILTERS.setdefault(host, []).append(filters)
            hosts = _str_list(obj.get("hosts"))
            regex = _str_list(obj.get("regex"))
            if hosts and regex:
                normal = [r for r in regex if not _is_ad_regex(r)]
                ads = [r for r in regex if _is_ad_regex(r)]
                for h in hosts:
                    if normal:
                        _HOST_RULES.setdefault(h, []).append(normal)
                    if ads:
                        _HOST_AD_REGEX.setdefault(h, []).extend(ads)
            scripts = _str_list(obj.get("script"))
            if hosts and scripts:
                for h in hosts:
                    _HOST_SCRIPTS.setdefault(h, []).extend(scripts)


def _is_ad_regex(regex):
    """对应 M3u8.isAd：播放列表标签/纯数字正则属于广告过滤规则"""
    return any(tag in regex for tag in (
        "#EXT-X-DISCONTINUITY", "#EXTINF", "#EXT-X-ENDLIST", "#EXT-X-KEY",
        "#EXT-X-CUE-OUT", "#EXT-X-CUE-IN", "#EXT-X-DATERANGE")) or \
        bool(re.fullmatch(r"\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*", regex))



api_config = ApiConfig()
