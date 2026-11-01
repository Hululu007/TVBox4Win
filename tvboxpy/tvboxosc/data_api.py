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

# 最近一次播放地址的来源说明（播放页 OSD 显示「解析来自」）
# kind: 直链 / 网页嗅探 / 解析 / 爬虫；name 为解析接口或站点名
LAST_RESOLVE = {"kind": "", "name": ""}


def _mark_resolve(kind, name=""):
    LAST_RESOLVE["kind"] = kind or ""
    LAST_RESOLVE["name"] = name or ""


# (站点 key, vod_id) → vod_tag。爬虫列表项里的 folder/action 标记在转成
# 四元组后会被丢掉，这里单独留存，供网格页判断点击行为。
_vod_tags = {}
_TAG_LIMIT = 5000


def get_vod_tag(bean, vod_id):
    """取列表项的 vod_tag（folder/action）；没有返回空串"""
    return _vod_tags.get((getattr(bean, "key", ""), str(vod_id)), "")


def _capture_tags(bean, items):
    key = getattr(bean, "key", "")
    for v in items or []:
        if not isinstance(v, dict):
            continue
        tag = str(v.get("vod_tag") or "")
        if not tag:
            continue
        if len(_vod_tags) > _TAG_LIMIT:
            _vod_tags.clear()
        _vod_tags[(key, str(v.get("vod_id", "")))] = tag


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
        "content": _clean_html(v.findtext("des") or ""),
        "year": (v.findtext("year") or v.findtext("last") or "").strip(),
        "area": (v.findtext("area") or "").strip(),
        "lang": (v.findtext("lang") or "").strip(),
        "cls": (v.findtext("type") or "").strip(),
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
        _capture_tags(bean, cfg.get("list"))
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
        _capture_tags(bean, cfg.get("list"))
        for v in cfg.get("list", []):
            vods.append((str(v.get("vod_id", "")), str(v.get("vod_name", "")),
                         str(v.get("vod_pic", "")), str(v.get("vod_remarks", ""))))
    return vods, page, pagecount


def search_vods(bean, wd):
    if _is_spider(bean):
        from .spider import get_spider
        cfg = get_spider(bean).search_content(wd)
        _capture_tags(bean, cfg.get("list"))
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
        _capture_tags(bean, cfg.get("list"))
        for v in cfg.get("list", []):
            vods.append((str(v.get("vod_id", "")), str(v.get("vod_name", "")),
                         str(v.get("vod_pic", "")), str(v.get("vod_remarks", ""))))
    return vods


def do_action(bean, action):
    """执行爬虫 action（列表项 vod_tag == "action" 点击时调用）
    返回 (ok, result_or_message)"""
    if not _is_spider(bean):
        return False, "当前源不支持动作"
    try:
        from .spider import get_spider
        sp = get_spider(bean)
        fn = getattr(sp, "action", None)
        if not callable(fn):
            return False, "当前爬虫不支持 action"
        return True, fn(str(action))
    except Exception as e:
        return False, str(e)


def _clean_html(text):
    """简介去 HTML 标签与实体（原版会走 Html.fromHtml，Python 侧直接剥掉）
    部分源在 CDATA 里存双重转义的 &lt;p&gt;，先 unescape 再剥标签"""
    if not text:
        return ""
    import html as _html
    t = _html.unescape(text)
    t = re.sub(r"<(br|/p|/div)[^>]*>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
          .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
          .replace("&#39;", "'"))
    return re.sub(r"\n{3,}", "\n\n", t).strip()


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
            "content": "", "year": "", "area": "", "lang": "", "cls": "",
            "series_flags": [], "series_urls": []}
    if not cfg or not cfg.get("list"):
        return info
    v = cfg["list"][0]
    info.update({
        "name": str(v.get("vod_name", "")),
        "pic": str(v.get("vod_pic", "")),
        "remark": str(v.get("vod_remarks", "")),
        "actors": str(v.get("vod_actor", "")),
        "director": str(v.get("vod_director", "")),
        "content": _clean_html(str(v.get("vod_content", ""))),
        "year": str(v.get("vod_year", "") or v.get("vod_time", "")).strip(),
        "area": str(v.get("vod_area", "")),
        "lang": str(v.get("vod_lang", "")),
        "cls": str(v.get("vod_class", "")),
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


# 原版 DefaultConfig.snifferMatch 的 Python 版（扩展名 + 厂商特殊直链）
_SNIFFER_RE = re.compile(
    r"http((?!http).){12,}?\.(m3u8|mp4|flv|avi|mkv|rm|wmv|mpg|m4a|mp3|aac|mpd)\?.*|"
    r"http((?!http).){12,}\.(m3u8|mp4|flv|avi|mkv|rm|wmv|mpg|m4a|mp3|aac|mpd)|"
    r"http((?!http).)*?video/tos*|"
    r"http((?!http).){20,}?/m3u8\?pt=m3u8.*|"
    r"http((?!http).)*?default\.ixigua\.com/.*|"
    r"http((?!http).)*?dycdn-tos\.pstatp[^?]*|"
    r"http.*?/player/m3u8play\.php\?url=.*|"
    r"http.*?/player/.*?[pP]lay\.php\?url=.*|"
    r"http.*?/playlist/m3u8/\?vid=.*|"
    r"http.*?\.php\?type=m3u8&.*|"
    r"http.*?/download\.aspx\?.*|"
    r"http.*?/api/up_api\.php\?.*|"
    r"https.*?\.66yk\.cn.*|"
    r"http((?!http).)*?netease\.com/file/.*",
    re.I,
)

_MEDIA_RE = re.compile(
    r"\.(m3u8|mp4|flv|mkv|ts|avi|mov|mp3|aac|m4a|mpd)([?#]|$)", re.I)

_QUOTED_MEDIA_RE = re.compile(
    r'''["']([^"'\s<>]*?\.(?:m3u8|mp4|flv|mkv|ts|avi|mov|mpd|mp3|m4a|aac)'''
    r'''(?:\?[^"'\s<>]*)?)["']''', re.I)
_ABS_URL_RE = re.compile(r'''https?://[^\s"'<>\\]+''', re.I)
_QUOTED_ANY_RE = re.compile(r'''["']([^"'\s<>]{3,1000})["']''')


def is_video_format(url):
    """对应原版 DefaultConfig.isVideoFormat：判断链接是否可以直接播放"""
    if not url:
        return False
    if url.startswith(("rtsp://", "rtmp://", "rtp://", "udp://")):
        return True
    # 比原版宽松一点：短路径直链（如 http://a.cn/1.mp4）也认
    return bool(_SNIFFER_RE.search(url)) or bool(_MEDIA_RE.search(url))


_looks_media = is_video_format  # 兼容旧内部调用


def _clean_candidate(url):
    if not url:
        return ""
    return url.strip().strip("\"'").rstrip(",;:)]}").strip()


def _sniff_text(text, base_url):
    """在 HTML/JSON 文本里找可播地址（对应 WebView 嗅探 + VideoParseRuler）"""
    if not text:
        return None
    from .apiconfig import host_filters, host_of, host_rules, filters_match, rules_match
    text = text.replace("\\/", "/").replace("&amp;", "&")
    host = host_of(base_url)
    rules = host_rules(host)
    filters = host_filters(host)
    seen = set()

    def keep(cand):
        if not cand:
            return None
        if cand.startswith(("data:", "blob:", "javascript:", "about:")):
            return None
        url = urllib.parse.urljoin(base_url, cand)
        if not url.startswith(("http://", "https://")):
            return None
        if url in seen:
            return None
        seen.add(url)
        if filters and filters_match(url, filters):
            return None
        if is_video_format(url) or (rules and rules_match(url, rules)):
            return url
        return None

    # 1. 带引号的媒体串（含相对路径）
    for m in _QUOTED_MEDIA_RE.finditer(text):
        url = keep(_clean_candidate(m.group(1)))
        if url:
            return url
    # 2. 绝对地址
    for m in _ABS_URL_RE.finditer(text):
        url = keep(_clean_candidate(m.group(0)))
        if url:
            return url
    # 3. 配置里给该 host 写了自定义规则：再扫一遍引号内容
    if rules:
        for m in _QUOTED_ANY_RE.finditer(text):
            url = keep(_clean_candidate(m.group(1)))
            if url:
                return url
    return None


def _sniff_page(page_url, headers=None):
    """页面嗅探兜底：拉取网页后在文本里找直链"""
    text = fetch_text(page_url, headers=headers, timeout=10, retries=1)
    return _sniff_text(text, page_url) if text else None


def _join_parse_url(api, page_url, encoded=True):
    """解析接口拼接：原版 type1 用 encodeUrl，type0 直接拼页面地址"""
    tail = urllib.parse.quote(page_url, safe="") if encoded else page_url
    if api.endswith(("=", "?", "&")):
        return api + tail
    if "?" not in api:
        return api + "?" + tail
    return api + tail


def _parse_json_api(bean, page_url):
    """JSON 解析接口：api + 网页链接 → {"url","header","parse"}
    兼容纯文本直链返回；解析失败返回 None 交给调用方嗅探。"""
    from .apiconfig import headers_from
    api = getattr(bean, "url", None) or str(bean)
    if not api or not api.startswith(("http://", "https://")):
        return None
    headers = getattr(bean, "headers", None) or None
    text = fetch_text(_join_parse_url(api, page_url),
                      headers=headers, timeout=10, retries=1)
    if not text:
        return None
    cfg = extract_json(text)
    if isinstance(cfg, dict):
        u = cfg.get("url") or cfg.get("playUrl")
        if isinstance(u, str) and u.strip():
            try:
                parse_flag = int(cfg.get("parse", 0) or 0)
            except (TypeError, ValueError):
                parse_flag = 0
            return {"url": u.strip(), "header": headers_from(cfg) or None,
                    "parse": parse_flag}
    plain = text.strip()
    if plain.startswith(("http://", "https://")) and len(plain) < 2048 \
            and "<" not in plain:
        return {"url": plain, "header": None, "parse": 0}
    return None


def _resolve_parsed(result, page_url):
    """解析结果 → 可播地址；parse==1 表示仍是网页，需再嗅探一次"""
    from .apiconfig import check_replace_proxy
    if not result:
        return None
    url = check_replace_proxy(result.get("url") or "")
    if not url:
        return None
    header = result.get("header") or None
    if result.get("parse") == 1 or not is_video_format(url):
        sniffed = _sniff_page(url, header)
        if sniffed:
            return sniffed, header
        return None
    return url, header


def _try_parse_bean(bean, page_url):
    """按原版 parse.type 执行单个解析接口，失败返回 None"""
    from .apiconfig import check_replace_proxy, headers_from
    ptype = int(getattr(bean, "type", 0) or 0)
    api = bean.mix_url() if ptype == 2 else bean.url
    if not api.startswith(("http://", "https://")):
        return None
    # type0 = WebView 直开播放页；type4 = SuperParse（嗅探 + JSON 并发）
    targets = []
    if ptype == 0:
        targets.append(_join_parse_url(api, page_url, encoded=False))
    else:
        targets.append(_join_parse_url(api, page_url))
        if ptype == 4:
            targets.append(_join_parse_url(api, page_url, encoded=False))
    headers = getattr(bean, "headers", None) or None
    for target in targets:
        text = fetch_text(target, headers=headers, timeout=10, retries=1)
        if not text:
            continue
        cfg = extract_json(text)
        if isinstance(cfg, dict):
            u = cfg.get("url") or cfg.get("playUrl")
            if isinstance(u, str) and u.strip():
                try:
                    parse_flag = int(cfg.get("parse", 0) or 0)
                except (TypeError, ValueError):
                    parse_flag = 0
                got = _resolve_parsed({
                    "url": check_replace_proxy(u.strip()),
                    "header": headers_from(cfg) or None,
                    "parse": parse_flag,
                }, page_url)
                if got:
                    return got[0], got[1], _bean_name(bean, api)
        # 解析接口返回的是播放页（或无效果）：静态嗅探代替原版 WebView
        sniffed = _sniff_text(text, target)
        if sniffed:
            return sniffed, headers, _bean_name(bean, api)
    return None


def _bean_name(bean, api=""):
    name = str(getattr(bean, "name", "") or "").strip()
    if name:
        return name
    try:
        from urllib.parse import urlparse
        host = urlparse(str(api or "")).hostname or ""
        return host or "解析接口"
    except Exception:
        return "解析接口"


def _second_parse(bean, page_url, play_url):
    """网页播放地址 → 真实媒体地址（对应原版 parse/嗅探流程）
    返回 (url, header) 或 None"""
    from .apiconfig import ParseBean, api_config
    beans = list(api_config.parse_bean_list)
    # 站点自带 playUrl 也当解析接口（原版是 playUrl + url 直接拼，见 PlayFragment.java:1263）
    if play_url and play_url.startswith(("http://", "https://")) \
            and not is_video_format(play_url):
        beans.insert(0, ParseBean("playUrl", play_url, None, 4))
    if not beans:
        sniffed = _sniff_page(page_url)
        return (sniffed, None, "网页嗅探") if sniffed else None

    # 解析接口并发执行，谁先成功用谁（对应 type3/4 的聚合解析）
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
    pool = ThreadPoolExecutor(max_workers=min(4, len(beans)))
    futures = {pool.submit(_try_parse_bean, p, page_url) for p in beans}
    try:
        for fut in as_completed(futures, timeout=12):
            try:
                got = fut.result()
            except Exception:
                got = None
            if got:
                for f in futures:
                    f.cancel()
                return got
    except TimeoutError:
        pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    # 最后直接嗅探原网页
    sniffed = _sniff_page(page_url)
    if sniffed:
        return sniffed, None, "网页嗅探"
    return None


def _finalize(url, header):
    """播放地址收口：proxy:// 转换 + 配置 hosts 映射"""
    from .apiconfig import apply_host_mapping, check_replace_proxy, proxy_base
    if not isinstance(url, str):
        return url, header
    url = check_replace_proxy(url)
    if "127.0.0.1:UndCover/proxy" in url:
        url = url.replace("http://127.0.0.1:UndCover/proxy",
                          proxy_base() + "proxy")
    return apply_host_mapping(url, header)


def get_play_url(bean, flag, ep_url):
    """播放前把选集地址解析成真实媒体地址（对应 SourceViewModel.getPlay）
    - type3 走 playerContent；parse==1 的页面链接自动走 parses/嗅探二次解析
    - type0/1 对应原版 isVideoFormat 判断：非媒体直链（网页/分享页）同样二次解析
    返回 (url, header)；header 为请求头 dict 或 None"""
    ep_url = str(ep_url or "")
    if not _is_spider(bean):
        # 原版 type0/1：isVideoFormat(requestUrl) ? 直接播 : parse=1 二次解析
        if is_video_format(ep_url) or not ep_url.startswith(("http://", "https://")):
            _mark_resolve("直链")
            return _finalize(ep_url, None)
        # 分享页/网页直链：先嗅探页面直链（快，~1s），失败再试 parses 接口
        try:
            sniffed = _sniff_page(ep_url)
        except Exception:
            sniffed = None
        if sniffed:
            _mark_resolve("网页嗅探")
            return _finalize(sniffed, None)
        try:
            got = _second_parse(bean, ep_url,
                                getattr(bean, "player_url", "") or "")
        except Exception:
            got = None
        if got:
            _mark_resolve("解析", got[2])
            return _finalize(got[0], got[1])
        _mark_resolve("直链")
        return _finalize(ep_url, None)  # 解析失败原样返回，让播放器报错可见
    from .apiconfig import api_config, headers_from
    from .spider import get_spider
    r = get_spider(bean).player_content(flag, ep_url, api_config.flags)
    url = str(r.get("url") or "")
    hdr = r.get("header") if isinstance(r.get("header"), dict) else None
    if hdr is None:
        hdr = headers_from(r) or None
    if not url:
        return url, hdr
    if not r.get("parse") in (1, "1", True):
        _mark_resolve("爬虫", getattr(bean, "name", "") or "")
        return _finalize(url, hdr)
    # parse==1：网页链接，需要二次解析
    if is_video_format(url):
        _mark_resolve("爬虫", getattr(bean, "name", "") or "")
        return _finalize(url, hdr)
    sniffed = _sniff_page(url, hdr)
    if sniffed:
        _mark_resolve("网页嗅探")
        return _finalize(sniffed, hdr)
    try:
        got = _second_parse(bean, url, str(r.get("playUrl") or ""))
    except Exception:
        got = None
    if got:
        _mark_resolve("解析", got[2])
        return _finalize(got[0], got[1])
    return _finalize(url, hdr)  # 解析失败原样返回，让 mpv 报错可见


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
    _vod_tags.clear()
    try:
        from .spider import shutdown
        shutdown()
    except Exception:
        pass
