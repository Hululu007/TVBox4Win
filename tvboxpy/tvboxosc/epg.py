"""EPG 节目单（对应原版 LivePlayActivity.getEpg + parseXmlEpg + EpgUtil）

数据来源优先级（与原版一致）：
1. 直播源自带的地址：m3u 头部 `#EXTM3U x-tvg-url="..."`、TVBox 配置 `lives[].epg`
2. hawk 里的 `epg_url`（ApiConfig 解析配置时写入）
3. 内置默认接口 `http://epg.51zmt.top:8000/api/diyp/?ch={name}&date={date}`

支持两种响应：XMLTV（<tv><programme start=... stop=...><title>）与 JSON
（{"channel_name":..,"epg":[{"title":..,"start":..,"end":..}]}）。
"""
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

DEFAULT_EPG = "http://epg.51zmt.top:8000/api/diyp/?ch={name}&date={date}"
_CACHE = {}                 # (频道key, 日期) -> (ts, [programme])
_TTL = 30 * 60              # 缓存 30 分钟
_LOCK = threading.Lock()
_UA = {"User-Agent": "okhttp/4.12.0"}

# 频道名后缀（原版 normalizeEpgChannelName 的近似实现）
_SUFFIX = re.compile(
    r"(高清|超清|蓝光|标清|4K|8K|HD|FHD|UHD|SD|H265|HEVC|IPV6|备用|测试)+$", re.I)


def normalize(name):
    """频道名规范化：去空白/后缀，用于与 EPG 的 channel 或 tvg-id 匹配"""
    s = str(name or "").strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("－", "-").replace("—", "-")
    prev = None
    while prev != s:                     # 反复剥离后缀：CCTV1高清HD → CCTV1
        prev = s
        s = _SUFFIX.sub("", s)
    return s


def epg_address():
    """当前使用的 EPG 地址模板（空则用内置默认）"""
    try:
        from . import hawk
        addr = str(hawk.get(hawk.EPG_URL, "") or "").strip()
    except Exception:
        addr = ""
    return addr or DEFAULT_EPG


def build_url(addr, name, day=None):
    """把 {name}/{date} 模板替换成实际值（对应原版 buildEpgUrl）"""
    day = day or datetime.now()
    ds = day.strftime("%Y-%m-%d")
    if "{name}" in addr or "{date}" in addr:
        return (addr.replace("{name}", _quote(name)).replace("{date}", ds))
    if addr.lower().split("?")[0].endswith(".xml"):
        return addr
    sep = "&" if "?" in addr else "?"
    return f"{addr}{sep}ch={_quote(name)}&date={ds}"


def _quote(s):
    from urllib.parse import quote
    return quote(str(s or ""), safe="")


# ---------------------------------------------------------------- 解析 ----
def _parse_time(s):
    """XMLTV 时间：20261101120000 +0800 → 本地时间 datetime"""
    s = str(s or "").strip()
    m = re.match(r"(\d{12,14})", s)
    if not m:
        return None
    raw = m.group(1)
    fmt = "%Y%m%d%H%M%S" if len(raw) == 14 else "%Y%m%d%H%M"
    try:
        dt = datetime.strptime(raw, fmt)
    except ValueError:
        return None
    tz = re.search(r"([+-]\d{4})", s)
    if tz:
        sign = 1 if tz.group(1)[0] == "+" else -1
        hh, mm = int(tz.group(1)[1:3]), int(tz.group(1)[3:5])
        off = timezone(sign * timedelta(hours=hh, minutes=mm))
        dt = dt.replace(tzinfo=off).astimezone().replace(tzinfo=None)
    return dt


def parse_xmltv(text, names):
    """解析 XMLTV → [{start, stop, title}]，只留命中的频道"""
    out = []
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text.encode("utf-8", "ignore"))
    except Exception:
        return _parse_xmltv_regex(text, names)
    want = {normalize(n) for n in names if n}
    for p in root.iter("programme"):
        ch = normalize(p.get("channel", ""))
        if want and ch and ch not in want and not any(
                w in ch or ch in w for w in want):
            continue
        title = ""
        for t in p.iter("title"):
            title = (t.text or "").strip()
            if title:
                break
        start, stop = _parse_time(p.get("start")), _parse_time(p.get("stop"))
        if title and start:
            out.append({"start": start, "stop": stop or start, "title": title})
    out.sort(key=lambda x: x["start"])
    return out


def _parse_xmltv_regex(text, names):
    """XML 不合法时的兜底解析（真实源里常有多余字符）"""
    out = []
    want = {normalize(n) for n in names if n}
    for m in re.finditer(r"<programme\b([^>]*)>(.*?)</programme>", text, re.S | re.I):
        attrs, body = m.group(1), m.group(2)
        ch = re.search(r'channel\s*=\s*"([^"]*)"', attrs)
        ch = normalize(ch.group(1)) if ch else ""
        if want and ch and ch not in want and not any(
                w in ch or ch in w for w in want):
            continue
        t = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        title = re.sub(r"<[^>]+>", "", t.group(1)).strip() if t else ""
        st = re.search(r'start\s*=\s*"([^"]*)"', attrs)
        sp = re.search(r'stop\s*=\s*"([^"]*)"', attrs)
        start = _parse_time(st.group(1)) if st else None
        stop = _parse_time(sp.group(1)) if sp else None
        if title and start:
            out.append({"start": start, "stop": stop or start, "title": title})
    out.sort(key=lambda x: x["start"])
    return out


def parse_json(text, names):
    """解析 JSON 节目单（51zmt 的 json 变体 / 自定义接口）"""
    out = []
    try:
        data = json.loads(text)
    except Exception:
        return out
    arr = None
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        for k in ("epg", "programs", "programmes", "data", "list"):
            if isinstance(data.get(k), list):
                arr = data[k]
                break
    if not arr:
        return out
    for it in arr:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or it.get("name") or "").strip()
        start = (it.get("start") or it.get("start_time") or it.get("st")
                 or it.get("starttime") or "")
        stop = (it.get("end") or it.get("stop") or it.get("end_time")
                or it.get("et") or "")
        s = _parse_time(start) or _parse_hhmm(start)
        e = _parse_time(stop) or _parse_hhmm(stop)
        if title and s:
            out.append({"start": s, "stop": e or s, "title": title})
    out.sort(key=lambda x: x["start"])
    return out


def _parse_hhmm(s):
    """只有 HH:MM 的节目单，按今天补全"""
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(s or "").strip())
    if not m:
        return None
    now = datetime.now()
    return now.replace(hour=int(m.group(1)), minute=int(m.group(2)),
                       second=0, microsecond=0)


def parse(text, names):
    """自动识别 XMLTV / JSON"""
    if not text:
        return []
    head = text.lstrip()[:200].lower()
    if head.startswith("<?xml") or head.startswith("<tv") or "<programme" in head:
        return parse_xmltv(text, names)
    if head.startswith("{") or head.startswith("["):
        return parse_json(text, names)
    # 头部判断不出就两路都试
    return parse_json(text, names) or parse_xmltv(text, names)


# ---------------------------------------------------------------- 加载 ----
def load(channel_name, day=None, addr=None, timeout=8):
    """取某频道当天的节目单 → [{start, stop, title}]；失败返回 []"""
    name = normalize(channel_name)
    if not name:
        return []
    key = (name, (day or datetime.now()).strftime("%Y%m%d"))
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < _TTL:
            return hit[1]
    url = build_url(addr or epg_address(), name, day)
    try:
        r = requests.get(url, timeout=timeout, verify=False, headers=_UA)
        if r.status_code != 200 or not r.text:
            progs = []
        else:
            r.encoding = r.apparent_encoding or "utf-8"
            progs = parse(r.text, [name, channel_name])
    except Exception:
        progs = []
    with _LOCK:
        _CACHE[key] = (time.time(), progs)
    return progs


def current_next(progs, now=None):
    """当前节目 / 下一节目（对应原版 showBottomEpg）"""
    now = now or datetime.now()
    cur = nxt = None
    for i, p in enumerate(progs):
        if p["start"] <= now < p["stop"]:
            cur = p
            nxt = progs[i + 1] if i + 1 < len(progs) else None
            break
        if p["start"] > now:
            nxt = p
            break
    return cur, nxt


def hhmm(dt):
    return dt.strftime("%H:%M") if dt else "--:--"


def clear_cache():
    with _LOCK:
        _CACHE.clear()
