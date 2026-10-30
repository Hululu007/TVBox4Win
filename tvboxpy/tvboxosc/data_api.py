"""CMS 数据接口层（对应 bean/AbsSortJson、SourceViewModel 的数据请求部分）
type 0/1/2 走 CMS HTTP 接口；type 3 走 spider JS 爬虫（Node bridge）"""
import re
import threading
import urllib.parse

from .apiconfig import extract_json, fetch_text


def _cms_url(bean, query):
    """规范 CMS URL：剥掉配置里自带的 ?ac=xxx 后缀，正确拼接 & 或 ?"""
    api = re.sub(r"[?&]ac=[a-z]+$", "", bean.api.rstrip("&?"))
    sep = "&" if "?" in api else "?"
    return f"{api}{sep}{query}"

_classes_cache = {}

_filters_cache = {}


def get_filters(bean):
    """分类筛选器（对应 Java sortJson 的 filters + getSortFilter）
    返回 {class_id: [{key, name, value}]}；无筛选返回 {}"""
    key = f"{bean.key}:{bean.api}"
    if key in _filters_cache:
        return _filters_cache[key]
    out = {}
    try:
        if _is_spider(bean):
            from .spider import get_spider
            cfg = get_spider(bean).home_content(True)
            out = cfg.get("filters") or {}
        else:
            cfg = extract_json(fetch_text(_cms_url(bean, "ac=class")))
            out = (cfg or {}).get("filters") or {}
    except Exception:
        out = {}
    norm = {}
    for cid, items in (out or {}).items():
        arr = []
        for f in (items or []):
            if isinstance(f, dict) and f.get("key") and f.get("name"):
                arr.append({"key": str(f["key"]), "name": str(f["name"]),
                            "value": [str(v) for v in (f.get("value") or [])]})
        if arr:
            norm[str(cid)] = arr
    _filters_cache[key] = norm
    return norm


def _is_spider(bean):
    return getattr(bean, "type", 0) == 3


def _is_xml(bean):
    """type 0 = XML CMS（对应 Java sortXml/getDetail type==0 分支）"""
    return getattr(bean, "type", 0) == 0


def _xml_root(text):
    import xml.etree.ElementTree as ET
    if not text:
        return None
    try:
        return ET.fromstring(text.strip())
    except ET.ParseError:
        return None


def _xml_classes(text):
    """<class><ty id="1">电影</ty></class> → [(id, name)]"""
    root = _xml_root(text)
    out = []
    if root is not None:
        for ty in root.iter("ty"):
            out.append((str(ty.get("id", "")), (ty.text or "").strip()))
    return out


def _xml_vods(text):
    """<list><video><id/><name/><pic/><note/></video></list> → [(id,name,pic,note)]"""
    root = _xml_root(text)
    out = []
    if root is not None:
        for v in root.iter("video"):
            out.append((str((v.findtext("id") or "").strip()),
                        (v.findtext("name") or "").strip(),
                        (v.findtext("pic") or "").strip(),
                        (v.findtext("note") or "").strip()))
    return out


def _xml_pagecount(text):
    root = _xml_root(text)
    node = root if root is not None else None
    if node is None:
        return 1
    list_el = node if node.tag == "list" else node.find(".//list")
    el = list_el if list_el is not None else node
    try:
        return max(1, int(el.get("pagecount", 1) or 1))
    except ValueError:
        return 1


def _xml_detail(text):
    """<video><dl><dd flag="..">名$url#名$url</dd></dl></video> → info dict"""
    root = _xml_root(text)
    info = {"name": "", "pic": "", "remark": "", "actors": "", "director": "",
            "content": "", "series_flags": [], "series_urls": []}
    if root is None:
        return info
    v = next(root.iter("video"), None)
    if v is None:
        return info
    info.update({
        "name": (v.findtext("name") or "").strip(),
        "pic": (v.findtext("pic") or "").strip(),
        "remark": (v.findtext("note") or "").strip(),
        "actors": (v.findtext("actor") or "").strip(),
        "director": (v.findtext("director") or "").strip(),
        "content": (v.findtext("des") or "").strip(),
    })
    for dd in v.iter("dd"):
        flag = dd.get("flag", "")
        eps_names, eps_urls = [], []
        for ep in (dd.text or "").split("#"):
            if "$" in ep:
                n, u = ep.split("$", 1)
                eps_names.append(n.strip())
                eps_urls.append(u.strip())
        if eps_urls:
            info["series_flags"].append((flag, eps_names))
            info["series_urls"].append(eps_urls)
    return info


def get_classes(bean):
    """对应获取分类（ac=class），带缓存（空结果不缓存）"""
    key = f"{bean.key}:{bean.api}"
    if key in _classes_cache:
        return _classes_cache[key]
    out = []
    if _is_spider(bean):
        from .spider import get_spider
        cfg = get_spider(bean).home_content(True)
        for c in cfg.get("class", []):
            cid, name = c.get("type_id"), c.get("type_name")
            if name is not None:
                out.append((str(cid), str(name)))
        if out:
            _classes_cache[key] = out
        return out
    if _is_xml(bean):
        out = _xml_classes(fetch_text(_cms_url(bean, "ac=class")))
        if out:
            _classes_cache[key] = out
        return out
    out = _parse_classes(extract_json(fetch_text(_cms_url(bean, "ac=class"))))
    if out:
        _classes_cache[key] = out
    return out


def _parse_classes(cfg):
    out = []
    if cfg and cfg.get("class"):
        for c in cfg["class"]:
            cid, name = c.get("type_id"), c.get("type_name")
            if name is None:
                continue
            out.append((str(cid), str(name)))
    return out


def get_vods(bean, class_id, page=1, extend=None):
    """对应获取影片列表，返回 (vods, page, pagecount)；extend 为筛选条件 dict"""
    if _is_spider(bean):
        from .spider import get_spider
        sp = get_spider(bean)
        if class_id is None:
            # 对应 Java 首页：homeVideoContent（部分蜘蛛 categoryContent(null) 返回空）
            try:
                cfg = sp.home_video_content() or {}
            except AttributeError:
                cfg = sp.home_content(True) or {}
        else:
            cfg = sp.category_content(
                class_id, page, True, __import__("json").dumps(extend or {}, ensure_ascii=False))
        vods = []
        for v in cfg.get("list", []):
            vods.append((str(v.get("vod_id", "")), str(v.get("vod_name", "")),
                         str(v.get("vod_pic", "")), str(v.get("vod_remarks", ""))))
        return vods, int(cfg.get("page", page)), int(cfg.get("pagecount", 1) or 1)
    if class_id is None:
        url = _cms_url(bean, "ac=videolist")
    else:
        url = _cms_url(bean, f"ac=videolist&t={class_id}&pg={page}")
    if extend:
        # 对应 Java getList 的 sortData.filterSelect（f 参数）
        import json as _json
        url += "&f=" + urllib.parse.quote(_json.dumps(extend, ensure_ascii=False))
    if _is_xml(bean):
        text = fetch_text(url)
        return _xml_vods(text), page, _xml_pagecount(text)
    cfg = extract_json(fetch_text(url))
    vods = []
    pagecount = 1
    if cfg:
        pagecount = int(cfg.get("pagecount", 1) or 1)
        for v in cfg.get("list", []):
            vods.append((str(v.get("vod_id", "")), str(v.get("vod_name", "")),
                         str(v.get("vod_pic", "")), str(v.get("vod_remarks", ""))))
    return vods, page, pagecount


def search_vods(bean, wd):
    if _is_spider(bean):
        from .spider import get_spider
        cfg = get_spider(bean).search_content(wd)
        return [(str(v.get("vod_id", "")), str(v.get("vod_name", "")),
                 str(v.get("vod_pic", "")), str(v.get("vod_remarks", "")))
                for v in cfg.get("list", [])]
    if _is_xml(bean):
        return _xml_vods(fetch_text(
            _cms_url(bean, f"ac=videolist&wd={urllib.parse.quote(wd)}")))
    # 对应 Java type1 搜索用 ac=detail；wd 需 URL 编码（在此处编码，勿在调用方双重编码）
    cfg = extract_json(fetch_text(
        _cms_url(bean, f"ac=detail&wd={urllib.parse.quote(wd)}")))
    vods = []
    if cfg:
        for v in cfg.get("list", []):
            vods.append((str(v.get("vod_id", "")), str(v.get("vod_name", "")),
                         str(v.get("vod_pic", "")), str(v.get("vod_remarks", ""))))
    return vods


def get_detail(bean, vod_id):
    """对应获取详情，返回 dict: name/pic/remark/actors/director/content/
    series_flags=[(flag_name,[ep_name...])], series_urls=[[url...]]"""
    if _is_spider(bean):
        from .spider import get_spider
        cfg = get_spider(bean).detail_content(vod_id)
    elif _is_xml(bean):
        return _xml_detail(fetch_text(_cms_url(bean, f"ac=videolist&ids={vod_id}")))
    else:
        cfg = extract_json(fetch_text(_cms_url(bean, f"ac=videolist&ids={vod_id}")))
    info = {"name": "", "pic": "", "remark": "", "actors": "", "director": "",
            "content": "", "series_flags": [], "series_urls": []}
    if not cfg or not cfg.get("list"):
        return info
    v = cfg["list"][0]
    info.update({
        "name": str(v.get("vod_name", "")),
        "pic": str(v.get("vod_pic", "")),
        "remark": str(v.get("vod_remarks", "")),
        "actors": str(v.get("vod_actor", "")),
        "director": str(v.get("vod_director", "")),
        "content": str(v.get("vod_content", "")).strip(),
    })
    flags = str(v.get("vod_play_from", ""))
    urls = str(v.get("vod_play_url", ""))
    flag_list = flags.split("$$$")
    url_groups = urls.split("$$$")
    for i, flag in enumerate(flag_list):
        eps_names, eps_urls = [], []
        if i < len(url_groups):
            for ep in url_groups[i].split("#"):
                if "$" in ep:
                    n, u = ep.split("$", 1)
                    eps_names.append(n)
                    eps_urls.append(u)
        info["series_flags"].append((flag, eps_names))
        info["series_urls"].append(eps_urls)
    return info


_MEDIA_RE = re.compile(
    r"\.(m3u8|mp4|flv|mkv|ts|avi|mov|mp3|aac|m4a|mpd)([?#]|$)", re.I)


def _looks_media(url):
    if not url:
        return False
    return bool(_MEDIA_RE.search(url)) or url[:7] in ("rtmp://", "rtp://", "udp://") \
        or url[:6] == "rtsp://"


def _parse_json_api(api, page_url):
    """JSON 解析接口：api + urlencode(网页链接) → {"url": 真实地址, "header": ...}"""
    if not api or not api.startswith(("http://", "https://")):
        return None
    sep = "&" if "?" in api else "?"
    text = fetch_text(api + sep + urllib.parse.quote(page_url, safe=""))
    cfg = extract_json(text) if text else None
    if cfg:
        u = cfg.get("url")
        if isinstance(u, str) and u:
            hdr = cfg.get("header")
            return u, hdr if isinstance(hdr, dict) else None
    return None


def _sniff_page(page_url):
    """页面嗅探兜底：在 HTML 里找第一个直链媒体地址"""
    text = fetch_text(page_url)
    if not text:
        return None
    m = re.search(r'https?://[^\s"\'<>\\]+?\.(?:m3u8|mp4|flv|mkv)[^\s"\'<>\\]*',
                  text, re.I)
    return m.group(0) if m else None


def _second_parse(bean, page_url, play_url):
    """parse==1 的网页链接 → 真实视频地址（对应原版 parse/嗅探流程）
    返回 (url, header) 或 None"""
    from .apiconfig import api_config
    candidates = []
    # 1. playerContent 自带的 playUrl、站点的 playerUrl
    for u in (play_url, getattr(bean, "player_url", "")):
        if u:
            candidates.append(u)
    # 2. 配置 parses 里 JSON 解析接口（flag 0=通用, 1=json）
    for p in api_config.parse_bean_list:
        if p.flag in (0, 1) and p.url.startswith(("http://", "https://")):
            candidates.append(p.url)
    tried = set()
    for api in candidates:
        if api in tried:
            continue
        tried.add(api)
        try:
            r = _parse_json_api(api, page_url)
        except Exception:
            r = None
        if r and _looks_media(r[0]):
            return r
    # 3. 页面嗅探
    sniffed = _sniff_page(page_url)
    if sniffed:
        return sniffed, None
    return None


def get_play_url(bean, flag, ep_url):
    """type3 站点播放前把选集 id 解析成真实播放地址（对应 playerContent）
    parse==1 的页面链接自动走 parses/嗅探二次解析。
    返回 (url, header)；header 为请求头 dict 或 None"""
    if not _is_spider(bean):
        return ep_url, None
    from .apiconfig import api_config
    from .spider import get_spider
    r = get_spider(bean).player_content(flag, ep_url, api_config.flags)
    url = str(r.get("url") or "")
    hdr = r.get("header") if isinstance(r.get("header"), dict) else None
    if url and not r.get("parse") in (1, "1", True):
        return url, hdr
    # parse==1：网页链接，需要二次解析
    if _looks_media(url):
        return url, hdr
    try:
        got = _second_parse(bean, url, str(r.get("playUrl") or ""))
    except Exception:
        got = None
    if got:
        return got
    return url, hdr  # 解析失败原样返回，让 mpv 报错可见


def _probe_source(b):
    """快速探测：8 秒短超时只试一次，成功结果直接进分类缓存"""
    key = f"{b.key}:{b.api}"
    if key in _classes_cache:
        return True
    try:
        from .apiconfig import SESSION
        r = SESSION.get(_cms_url(b, "ac=class"), timeout=8, verify=False)
        if r.status_code == 200 and r.text:
            out = _parse_classes(extract_json(r.text))
            if out:
                _classes_cache[key] = out
                return True
    except Exception:
        pass
    return False


def pick_default_source():
    """并发探测所有直连源，返回第一个分类非空的（跳过失效源），供启动/换源后使用"""
    from .apiconfig import api_config
    from concurrent.futures import ThreadPoolExecutor
    beans = [b for b in api_config.source_bean_list if b.type in (0, 1, 2)]
    if not beans:
        return None
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(_probe_source, beans))
    for b, ok in zip(beans, results):
        if ok:
            return b
    return None


def clear_caches():
    """换源后清空分类/筛选缓存与 spider 进程"""
    _classes_cache.clear()
    _filters_cache.clear()
    try:
        from .spider import shutdown
        shutdown()
    except Exception:
        pass
