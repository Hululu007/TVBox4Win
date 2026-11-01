"""本地播放代理（对应原版 util/Proxy.java）

只服务本机播放器，挂在推送服务的 9978 端口上：
- /proxy?go=live&type=m3u8  → 拉取 m3u8，把分片/密钥/子播放列表改写成代理地址
- /proxy?go=live&type=ts|media|key → 带 UA/Referer 等请求头转发
- /proxy?go=bom → 去掉 UTF-8 BOM 后返回 m3u8
- /proxy?do=py → 交给 py 爬虫的 localProxy

mpv 不经过 Python 的 requests，防盗链直播/相对分片靠这里补齐。
"""
import base64
import json
import re
import urllib.parse

import requests

# 与原版 Proxy.buildRequest / headerQuery 保持一致的参数名
_HEADER_PARAMS = (
    ("ua", "User-Agent"), ("user-agent", "User-Agent"),
    ("User-Agent", "User-Agent"),
    ("referer", "Referer"), ("Referer", "Referer"),
    ("origin", "Origin"), ("Origin", "Origin"),
    ("cookie", "Cookie"), ("Cookie", "Cookie"),
    ("range", "Range"), ("Range", "Range"),
    ("accept", "Accept"), ("Accept", "Accept"),
    ("accept-language", "Accept-Language"),
    ("Accept-Language", "Accept-Language"),
)
_URI_ATTR = re.compile(r'URI="([^"]+)"')
_M3U8_CT = "application/vnd.apple.mpegurl"

_MIME = {
    "ts": "video/mp2t",
    "media": "application/octet-stream",
    "key": "application/octet-stream",
    "m3u8": _M3U8_CT,
}


def _first(params, key):
    val = params.get(key)
    if isinstance(val, (list, tuple)):
        return val[0] if val else None
    return val


def header_params(params):
    """从查询参数还原请求头（对应 Proxy.buildRequest）"""
    out = {}
    for key, header in _HEADER_PARAMS:
        val = _first(params, key)
        if val:
            out[header] = str(val)
    raw = _first(params, "headers") or _first(params, "h")
    if raw:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            data = None
        if isinstance(data, dict):
            for k, v in data.items():
                out.setdefault(str(k), str(v))
    return out


def _header_query(headers):
    """把请求头编码回查询参数（对应 Proxy.headerQuery）"""
    mapping = (("User-Agent", "ua"), ("Referer", "referer"),
               ("Origin", "origin"), ("Cookie", "cookie"))
    out = []
    seen = set()
    for header, key in mapping:
        if header in headers and key not in seen:
            seen.add(key)
            out.append("%s=%s" % (key, urllib.parse.quote(str(headers[header]), safe="")))
    return "".join("&" + item for item in out)


def proxy_link(proxy_base, kind, url, headers=None):
    return ("%sproxy?go=live&type=%s%s&url=%s" % (
        proxy_base, kind, _header_query(headers or {}),
        urllib.parse.quote(url, safe="")))


def _is_m3u8(url):
    path = url.split("?", 1)[0].lower()
    return path.endswith((".m3u8", ".m3u"))


def _absolute(base, ref):
    if ref.startswith(("http://", "https://")):
        return ref
    if ref.startswith("://"):
        return urllib.parse.urlsplit(base).scheme + ref
    if ref.startswith("//"):
        return urllib.parse.urlsplit(base).scheme + ":" + ref
    return urllib.parse.urljoin(base, ref)


def _join(base, ref, kind, proxy_base, headers):
    ref = ref.strip()
    if ref.startswith(("data:", "blob:")):
        return ref
    return proxy_link(proxy_base, kind, _absolute(base, ref), headers)


def _rewrite_uri_attrs(line, base, proxy_base, headers):
    def replace(match):
        uri = match.group(1)
        upper = line.upper()
        if upper.startswith(("#EXT-X-KEY", "#EXT-X-SESSION-KEY")):
            kind = "key"
        elif _is_m3u8(uri) or upper.startswith("#EXT-X-I-FRAME-STREAM-INF"):
            kind = "m3u8"
        else:
            kind = "media"
        return 'URI="%s"' % _join(base, uri, kind, proxy_base, headers)
    return _URI_ATTR.sub(replace, line)


def rewrite_m3u8(content, base_url, proxy_base, headers=None):
    """把所有分片/密钥/子列表改写成代理地址（对应 Proxy.processM3u8Content）"""
    if not content:
        return ""
    if content and ord(content[0]) == 0xFEFF:
        content = content[1:]
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    next_is_variant = False
    for line in lines:
        item = line.strip()
        if not item:
            out.append(line)
        elif item.startswith("#"):
            out.append(_rewrite_uri_attrs(line, base_url, proxy_base, headers or {}))
            next_is_variant = item.upper().startswith("#EXT-X-STREAM-INF")
        else:
            kind = "m3u8" if next_is_variant or _is_m3u8(item) else "media"
            out.append(_join(base_url, item, kind, proxy_base, headers or {}))
            next_is_variant = False
    return "\n".join(out)


def _fetch(url, headers, stream=False, timeout=20):
    return requests.get(url, headers=headers or None, timeout=timeout,
                        verify=False, stream=stream, allow_redirects=True)


def _error(text, code=400):
    return code, "text/plain; charset=utf-8", text.encode("utf-8"), {}


def handle_live(params, proxy_base):
    url = urllib.parse.unquote(_first(params, "url") or "")
    if not url.startswith(("http://", "https://")):
        return _error("invalid url")
    kind = (_first(params, "type") or "media").lower()
    headers = header_params(params)
    try:
        resp = _fetch(url, headers, stream=(kind != "m3u8"))
    except requests.RequestException as exc:
        return _error("upstream error: %s" % exc, 502)
    if resp.status_code >= 400:
        code = resp.status_code
        resp.close()
        return _error("upstream status %s" % code, 502)
    if kind == "m3u8":
        try:
            body = rewrite_m3u8(resp.text, resp.url or url, proxy_base,
                                headers).encode("utf-8")
        finally:
            resp.close()
        return 200, _M3U8_CT, body, {}
    ctype = resp.headers.get("Content-Type") or _MIME.get(kind)
    extra = {}
    for header in ("Content-Range", "Accept-Ranges", "Content-Length"):
        if header in resp.headers:
            extra[header] = resp.headers[header]
    body = resp.content
    resp.close()
    return resp.status_code, ctype, body, extra


def handle_bom(params, proxy_base):
    url = urllib.parse.unquote(_first(params, "url") or "")
    if not url.startswith(("http://", "https://")):
        return _error("invalid url")
    try:
        resp = _fetch(url, header_params(params))
    except requests.RequestException as exc:
        return _error("upstream error: %s" % exc, 502)
    content = resp.text or ""
    resp.close()
    if content and ord(content[0]) == 0xFEFF:
        content = content[1:]
    return 200, _M3U8_CT, content.encode("utf-8"), {}


def _normalize_local_proxy(res):
    """把 py 爬虫 localProxy 的返回值统一成 (code, ctype, body, headers)"""
    if res is None:
        return None
    if isinstance(res, dict):
        code = int(res.get("code", 200) or 200)
        ctype = (res.get("contentType") or res.get("content_type")
                 or "application/octet-stream")
        content = res.get("content")
        headers = res.get("header") or res.get("headers") or {}
        is_base64 = bool(res.get("base64"))
    elif isinstance(res, (list, tuple)) and len(res) >= 3:
        try:
            code = int(res[0])
        except (TypeError, ValueError):
            code = 200
        ctype = str(res[1] or "application/octet-stream")
        content = res[2]
        headers = res[3] if len(res) > 3 and isinstance(res[3], dict) else {}
        is_base64 = len(res) > 4 and str(res[4]) == "1"
    else:
        return None
    if isinstance(headers, str):
        try:
            headers = json.loads(headers)
        except json.JSONDecodeError:
            headers = {}
    if isinstance(content, bytes):
        body = content
    elif is_base64 and isinstance(content, str) and "base64," in content:
        try:
            body = base64.b64decode(content.split("base64,", 1)[1])
        except (ValueError, TypeError):
            body = content.encode("utf-8", "replace")
    else:
        body = str(content or "").encode("utf-8")
    return code, ctype, body, dict(headers or {})


def handle_py(params):
    from .py_spider import proxy_spider
    # parse_qs 的值是列表，爬虫 localProxy 需要普通字符串
    params = {k: (v[0] if isinstance(v, (list, tuple)) and v else v)
              for k, v in params.items()}
    spider = proxy_spider(params)
    if spider is None:
        return _error("no py spider", 404)
    try:
        res = spider.local_proxy(params)
    except Exception as exc:
        return _error("localProxy error: %s" % exc, 500)
    norm = _normalize_local_proxy(res)
    if norm is None:
        return _error("localProxy returned nothing", 404)
    return norm


def handle(params, proxy_base):
    """处理 /proxy 请求，返回 (code, content_type, body_bytes, headers)"""
    do = (_first(params, "do") or "").lower()
    if do == "py":
        return handle_py(params)
    go = (_first(params, "go") or "").lower()
    if go == "live":
        return handle_live(params, proxy_base)
    if go == "bom":
        return handle_bom(params, proxy_base)
    return _error("unsupported proxy request", 404)
