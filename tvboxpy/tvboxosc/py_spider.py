"""py 类爬虫站点支持（学习 tvboxosc-python pyramid/src/python）

原版 TVBox OSC 的 python64 版内嵌 Python 运行时，site api 以 .py 结尾时
下载 py 模块并加载其中的 Spider 类。本文件复刻该 API 全集：

- Spider 基类：homeContent/homeVideoContent/categoryContent/detailContent/
  searchContent/playerContent/liveContent/localProxy/isVideoFormat/
  manualVideoCheck/action + fetch/post/postJson/html/xpText/regStr/
  removeHtmlTags/cleanText/getProxyUrl/getCache/setCache/delCache/loadSpider
- jsoup：海阔规则解析器 pdfa/pdfh/pd/pjfh/pj（body&&.class&&a&&href、
  :eq(n)、--排除、Text/Html/属性选项、自动 urljoin）
- PySpider：对外包装，暴露与 spider.py（drpy JS）同构的 snake_case 方法，
  使 data_api.get_play_url / get_vods 等无需改动即可路由。

站点 py 文件下载到 .spider_cache 后用 SourceFileLoader 加载（与原版
app.py downloadPlugin/loadFromDisk 语义一致）。
"""
import json
import os
import re
import threading
import time
from html.parser import HTMLParser
from importlib.machinery import SourceFileLoader
from urllib.parse import urljoin, parse_qs, urlparse

from .apiconfig import fetch_text
from .paths import data_path

_CACHE_DIR = data_path(".spider_cache")
_lock = threading.Lock()
_loaded = {}  # key -> Spider 实例

_FALLBACK_STATUS = (403, 429, 495, 496, 497, 525, 526, 527)


# ---------------------------------------------------------------- DOM ----
class _Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text_parts")

    def __init__(self, tag, attrs, parent=None):
        self.tag = tag.lower()
        self.attrs = dict(attrs)
        self.children = []
        self.parent = parent
        self.text_parts = []

    @property
    def text(self):
        parts = list(self.text_parts)
        for ch in self.children:
            parts.append(ch.text)
        return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()

    @property
    def html(self):
        attrs = "".join(
            f' {k}="{v}"' for k, v in self.attrs.items())
        inner = "".join(c.html for c in self.children) + self.raw_text()
        return f"<{self.tag}{attrs}>{inner}</{self.tag}>"

    def raw_text(self):
        return "".join(self.text_parts)

    def outer_html(self):
        return self.html

    def iter(self):
        yield self
        for ch in self.children:
            yield from ch.iter()


class _TreeBuilder(HTMLParser):
    VOID = {"br", "img", "input", "meta", "link", "hr", "source", "area",
            "base", "col", "embed", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {})
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag.lower() not in self.VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(_Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        node, cur = self.cur, self.cur
        while cur is not None and cur.tag != tag.lower():
            cur = cur.parent
        if cur is not None:
            self.cur = cur.parent
        else:  # 未匹配的结束标签，忽略
            self.cur = node

    def handle_data(self, data):
        if data.strip():
            self.cur.text_parts.append(data.strip())


def _parse_html(content):
    tb = _TreeBuilder()
    try:
        tb.feed(content if isinstance(content, str) else content.decode("utf-8", "ignore"))
    except Exception:
        pass
    return tb.root


# ------------------------------------------------------------ 选择器 ----
_NOADD_INDEX = re.compile(r":eq|:lt|:gt|:first|:last|^body$|^#")
_URLJOIN_ATTR = re.compile(r"(url|src|href|-original|-src|-play|-url)$", re.I)


def _hiker_to_jq(parse, first=False):
    """海阔 && 链转空格链，自动补 :eq(0)（复刻 htmlParser.parseHikerToJq）"""
    if "&&" in parse:
        parts = parse.split("&&")
        out = []
        for i, p in enumerate(parts):
            last = p.split(" ")[-1]
            if not _NOADD_INDEX.search(last):
                if not first and i >= len(parts) - 1:
                    out.append(p)
                else:
                    out.append(p + ":eq(0)")
            else:
                out.append(p)
        parse = " ".join(out)
    else:
        last = parse.split(" ")[-1]
        if not _NOADD_INDEX.search(last) and first:
            parse = parse + ":eq(0)"
    return parse


def _match_simple(node, tok):
    tok = tok.strip()
    if not tok or tok == "body":
        return node.tag != "#root" or True
    if tok.startswith("#"):
        return node.attrs.get("id") == tok[1:]
    if tok.startswith("."):
        cls = node.attrs.get("class", "")
        return tok[1:] in cls.split()
    m = re.match(r"^([a-zA-Z][\w-]*)(\[[^]]+\])?$", tok)
    if m:
        if node.tag != m.group(1).lower():
            return False
        attr = m.group(2)
        if attr:
            inner = attr[1:-1]
            if "=" in inner:
                k, v = inner.split("=", 1)
                return node.attrs.get(k) == v.strip("\"'")
            return k in node.attrs
        return True
    return False


def _select(doc, selector):
    """空格分隔的后代选择器；返回匹配的 _Node 列表"""
    toks = selector.split()
    results = [n for n in doc.iter() if n.tag != "#root"]
    for i, tok in enumerate(toks):
        eq = None
        if ":eq(" in tok:
            tok, eq = tok.split(":eq(")
            eq = int(eq.rstrip(")"))
        elif ":first" in tok:
            tok, eq = tok.replace(":first", ""), 0
        elif ":gt(" in tok:
            tok, gt = tok.split(":gt(")
            gt = int(gt.rstrip(")"))
            eq = ("gt", gt)
        elif ":lt(" in tok:
            tok, lt = tok.split(":lt(")
            lt = int(lt.rstrip(")"))
            eq = ("lt", lt)
        nxt = []
        for n in results:
            # tok 匹配 n 的某个后代链：在 n 的子树中找匹配 tok 的所有节点
            for d in n.iter():
                if d is n:
                    continue
                if _match_simple(d, tok):
                    nxt.append(d)
        # 去重保序
        seen, uniq = set(), []
        for n in nxt:
            if id(n) not in seen:
                seen.add(id(n))
                uniq.append(n)
        results = uniq
        if eq is not None:
            if isinstance(eq, tuple):
                kind, n = eq
                results = results[n + 1:] if kind == "gt" else results[:n]
            else:
                results = results[eq:eq + 1]
        if not results:
            return []
    return results


class _Sel:
    """对节点列表再施加一级选择（模拟 pyquery 链式调用）"""

    def __init__(self, nodes):
        self.nodes = nodes


# ------------------------------------------------------------- jsoup ----
class jsoup:
    """海阔解析规则子集：pdfa / pdfh / pd / pjfh / pj（依赖 pyquery/jsonpath
    的原版此处用标准库自实现，覆盖常见规则写法）"""

    def __init__(self, my_url=""):
        self.MY_URL = my_url
        self._doc_html = ""
        self._doc = None

    # ---- 文档 ----
    def _document(self, html):
        if self._doc is None or self._doc_html != html:
            self._doc_html = html
            self._doc = _parse_html(html)
        return self._doc

    def pq(self, html):
        return _parse_html(html)

    # ---- HTML 规则 ----
    def pdfa(self, html, parse):
        if not html or not parse:
            return []
        doc = self._document(html)
        nodes = _select(doc, _hiker_to_jq(parse))
        return [n.outer_html() for n in nodes]

    def pdfh(self, html, parse, base_url=""):
        if not html or not parse:
            return ""
        if parse in ("body&&Text", "Text"):
            return self._document(html).text
        if parse in ("body&&Html", "Html"):
            return self._document(html).html
        option = None
        if "&&" in parse:
            parse, option = parse.rsplit("&&", 1)
        doc = self._document(html)
        nodes = _select(doc, _hiker_to_jq(parse, True))
        if not nodes:
            return ""
        node = nodes[0]
        if option is None:
            return node.outer_html()
        if option == "Text":
            return node.text
        if option == "Html":
            return node.html
        ret = node.attrs.get(option, "")
        if "style" in option.lower() and "url(" in ret:
            m = re.search(r"url\((.*?)\)", ret)
            ret = m.group(1) if m else ret
        if ret and base_url and _URLJOIN_ATTR.search(option):
            if "http" in ret:
                ret = ret[ret.find("http"):]
            else:
                ret = urljoin(base_url, ret)
        return ret

    def pd(self, html, parse, base_url=""):
        return self.pdfh(html, parse, base_url or self.MY_URL)

    # ---- JSON 规则（jsonpath 子集：$.a.b[0].c） ----
    def pjfh(self, html, parse, add_url=False):
        if not html or not parse:
            return ""
        if isinstance(html, str):
            try:
                html = json.loads(html)
            except Exception:
                return ""
        ret = ""
        for ps in parse.split("||"):
            ps = ps if ps.startswith("$.") else "$." + ps
            val = self._jsonpath(html, ps)
            ret = str(val) if val not in (None, "", [], {}) else ""
            if ret and add_url and self.MY_URL and not ret.startswith("http"):
                ret = urljoin(self.MY_URL, ret)
            if ret:
                break
        return ret

    def pjfa(self, html, parse):
        if not html or not parse:
            return []
        if isinstance(html, str):
            try:
                html = json.loads(html)
            except Exception:
                return []
        ps = parse if parse.startswith("$.") else "$." + parse
        val = self._jsonpath(html, ps)
        if isinstance(val, list) and len(val) == 1 and isinstance(val[0], list):
            val = val[0]
        return val or []

    def pj(self, html, parse):
        return self.pjfh(html, parse, True)

    @staticmethod
    def _jsonpath(obj, path):
        cur = [obj]
        for tok in re.split(r"\.(?![^\[]*\])", path.lstrip("$.")):
            if not tok:
                continue
            nxt = []
            for o in cur:
                m = re.match(r"^([\w\-]+)?(\[[^\]]+\])?$", tok)
                if not m:
                    continue
                key, idx = m.group(1), m.group(2)
                try:
                    if key:
                        if isinstance(o, list):
                            o = [x.get(key) for x in o if isinstance(x, dict)]
                        else:
                            o = o.get(key) if isinstance(o, dict) else None
                    if idx:
                        for ix in re.findall(r"\[([^\]]+)\]", idx):
                            if ix in ("*",):
                                if isinstance(o, list):
                                    nxt.extend(o)
                                o = None
                                continue
                            o = o[int(ix)] if isinstance(o, (list, str)) and int(ix) < len(o) else None
                    if isinstance(o, list) and idx and "*" not in idx:
                        nxt.extend(o)
                    elif o is not None:
                        nxt.append(o)
                except Exception:
                    pass
            cur = nxt
        if len(cur) == 1:
            return cur[0]
        return cur if cur else None


# ------------------------------------------------------------ Spider ----
class Spider:
    """py 爬虫基类（API 与 tvboxosc-python base/spider.py 一致）"""

    def __init__(self):
        self.extend = ""

    # 生命周期
    def init(self, extend=""):
        pass

    def homeContent(self, filter):
        pass

    def homeVideoContent(self):
        pass

    def categoryContent(self, tid, pg, filter, extend):
        pass

    def detailContent(self, ids):
        pass

    def searchContent(self, key, quick, pg="1"):
        pass

    def playerContent(self, flag, id, vipFlags=""):
        pass

    def liveContent(self, url):
        pass

    def localProxy(self, param):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def action(self, action):
        pass

    def destroy(self):
        pass

    def getName(self):
        return ""

    def getDependence(self):
        return []

    def setExtendInfo(self, extend):
        self.extend = extend

    # 工具
    def loadSpider(self, name):
        return self.loadModule(name).Spider()

    def loadModule(self, name, fileName=None):
        path = fileName if fileName else os.path.join("../plugin", f"{name}.py")
        return SourceFileLoader(name, path).load_module()

    @staticmethod
    def regStr(src, reg=None, group=1):
        if reg is None:
            return ""
        match = None
        try:
            match = re.search(reg, src)
        except Exception:
            pass
        if not match:
            try:
                match = re.search(src, reg)
            except Exception:
                pass
        return match.group(group) if match else ""

    @staticmethod
    def removeHtmlTags(src):
        return re.sub(r"<.*?>", "", src)

    @staticmethod
    def cleanText(src):
        return re.sub(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]", "", src)

    def fetch(self, url, headers=None, cookies=None, params=None,
              timeout=15, verify=False, stream=False, allow_redirects=True):
        import requests
        rsp = requests.get(url, params=params, cookies=cookies,
                           headers=headers, timeout=timeout, verify=verify,
                           stream=stream, allow_redirects=allow_redirects)
        rsp.encoding = "utf-8"
        return rsp

    def post(self, url, data=None, headers=None, cookies=None, params=None,
             json=None, timeout=15, verify=False, stream=False,
             allow_redirects=True):
        import requests
        rsp = requests.post(url, params=params, data=data, json=json,
                            cookies=cookies, headers=headers, timeout=timeout,
                            verify=verify, stream=stream,
                            allow_redirects=allow_redirects)
        rsp.encoding = "utf-8"
        return rsp

    def postJson(self, url, json, headers=None, cookies=None):
        import requests
        rsp = requests.post(url, json=json, headers=headers, cookies=cookies,
                            verify=False)
        rsp.encoding = "utf-8"
        return rsp

    def html(self, content):
        return _parse_html(content)

    @staticmethod
    def xpText(root, expr):
        # xpath 子集：//tag、//tag[n]、//tag/@attr、//tag/text()
        try:
            m = re.match(
                r"^(?://|/)(?P<tag>[\w*]+)(?:\[(?P<idx>\d+)\])?"
                r"(?:/@(?P<attr>[\w-]+)|/text\(\))?$", expr or "")
            if not m:
                return ""
            tag, idx, attr = m.group("tag"), m.group("idx"), m.group("attr")
            nodes = [n for n in root.iter() if tag in ("*", n.tag)]
            if idx:
                nodes = nodes[int(idx) - 1:int(idx)]
            if not nodes:
                return ""
            n = nodes[0]
            if attr:
                return n.attrs.get(attr, "")
            return n.text
        except Exception:
            return ""

    @staticmethod
    def str2json(content):
        return json.loads(content)

    @staticmethod
    def json2str(content):
        return json.dumps(content, ensure_ascii=False)

    def getProxyUrl(self, local=True):
        # 本地 9978 推送服务同时充当 localProxy（/proxy?do=py&...）
        return f"http://127.0.0.1:9978/proxy?do=py"

    def log(self, msg):
        if isinstance(msg, (dict, list)):
            print(json.dumps(msg, ensure_ascii=False))
        else:
            print(msg)

    # 缓存：原版走 localProxy HTTP；此处简化为内存缓存
    _cache_store = {}

    def getCache(self, key):
        item = Spider._cache_store.get(key)
        if not item:
            return None
        value, expires = item
        if expires and expires < int(time.time()):
            Spider._cache_store.pop(key, None)
            return None
        return value

    def setCache(self, key, value):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, (int, float)):
            value = str(value)
        Spider._cache_store[key] = (value, 0)
        return "succeed"

    def delCache(self, key):
        Spider._cache_store.pop(key, None)
        return "succeed"


# ---------------------------------------------------------- 包装器 ----
class PySpider:
    """与 spider.Spider（drpy JS）同构的对外包装，供 data_api 无感路由"""

    def __init__(self, key, api, ext=None):
        self.key = key
        self.api = api
        self.ext = ext
        self.jsoup = jsoup()
        self._impl = None
        self._lock = threading.RLock()

    # ---- 加载 ----
    def _site_py_path(self):
        if os.path.isfile(self.api):
            return self.api
        if not re.match(r"^https?://", self.api):
            raise RuntimeError(f"py 爬虫地址无效: {self.api}")
        os.makedirs(_CACHE_DIR, exist_ok=True)
        name = re.sub(r"[^A-Za-z0-9_.\-]", "_", self.key) + ".py"
        path = os.path.join(_CACHE_DIR, name)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            text = fetch_text(self.api)
            if not text or "Spider" not in text:
                raise RuntimeError(f"py 爬虫下载失败: {self.api}")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return path

    def _ensure(self):
        if self._impl is not None:
            return
        with self._lock:
            if self._impl is not None:
                return
            path = self._site_py_path()
            mod_name = "py_sp_" + re.sub(r"\W", "_", self.key)
            mod = SourceFileLoader(mod_name, path).load_module()
            impl = mod.Spider()
            # ext 传参：URL query 里的 extend 或 ext 字段本身
            extend = self.ext or ""
            if isinstance(extend, str) and extend.startswith("http"):
                qs = parse_qs(urlparse(extend).query).get("extend")
                if qs:
                    extend = qs[0]
            # 原版 app.py 同款容错：py 站点类可继承基类，也可独立实现
            setter = getattr(impl, "setExtendInfo", None)
            if callable(setter):
                setter(extend)
            else:
                impl.extend = extend
            getattr(impl, "init", lambda *a: None)(extend)
            self._impl = impl

    # ---- 与 drpy Spider 同构的方法 ----
    def home_content(self, filtr=True):
        self._ensure()
        return self._json(self._impl.homeContent(filtr)) or {"class": []}

    def home_video_content(self):
        self._ensure()
        return self._json(self._impl.homeVideoContent()) or {}

    def category_content(self, tid, pg, filtr, extend):
        self._ensure()
        ext = extend
        if isinstance(ext, str) and ext:
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}
        return self._json(self._impl.categoryContent(tid, pg, filtr, ext)) \
            or {"list": [], "pagecount": 1}

    def detail_content(self, ids):
        self._ensure()
        if isinstance(ids, str) and ids.startswith("["):
            try:
                ids = json.loads(ids)
            except Exception:
                ids = [ids]
        return self._json(self._impl.detailContent(ids)) or {}

    def search_content(self, key, quick=False, pg="1"):
        self._ensure()
        return self._json(self._impl.searchContent(key, quick, pg)) \
            or {"list": []}

    def player_content(self, flag, ep_id, vip_flags=None):
        self._ensure()
        return self._json(
            self._impl.playerContent(flag or "", str(ep_id),
                                     json.dumps(vip_flags or [], ensure_ascii=False))) \
            or {"parse": 1, "url": str(ep_id)}

    @staticmethod
    def _json(result):
        if isinstance(result, str):
            try:
                return json.loads(result)
            except Exception:
                return None
        return result


def get_py_spider(key, api, ext=None):
    with _lock:
        k = f"py::{key}"
        sp = _loaded.get(k)
        if sp is None:
            sp = PySpider(key, api, ext)
            _loaded[k] = sp
        return sp


def shutdown():
    with _lock:
        for sp in _loaded.values():
            try:
                if sp._impl is not None:
                    sp._impl.destroy()
            except Exception:
                pass
        _loaded.clear()
