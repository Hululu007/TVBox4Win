"""弹幕解析与 ASS 生成

桌面端播放内核（libmpv）没有独立的弹幕层，而 tkinter 也做不到在视频窗口上
透明叠加文字，所以这里把弹幕合成为一条 ASS 字幕轨，交给 mpv 的 sub-add 渲染。
反向复用播放器已有的字幕能力：延迟、字号、显隐都能直接沿用。

支持三种弹幕源：
1. B 站 XML：<d p="时间,模式,字号,颜色,...">文本</d>
2. JSON：B 站 danmaku 接口的 elems 数组、通用 [{time,text,color,mode}] 等
3. 纯文本：每行「秒数 文本」或「mm:ss 文本」

生成规则对照 B 站：模式 1/2/3 滚动、4 底部固定、5 顶部固定；滚动弹幕按
轨道（行）排布，轨道未让出时顺延到下一条，密集时允许重叠（与网页端一致）。
"""
import html
import json
import re

# 默认 1080p 坐标系下的字号；mpv/libass 会按窗口自动缩放
DEFAULT_FONT_SIZE = 42
DEFAULT_DURATION = 8.0       # 滚动弹幕从右到左飞过的时间（秒）
_TOP_RATIO = 0.82            # 顶部 82% 区域用于滚动/顶部弹幕，底部留给固定弹幕

_XML_D_RE = re.compile(r"<d\s+p=\"([^\"]*)\"[^>]*>(.*?)</d>", re.S | re.I)
_TS_RE = re.compile(r"^(?:\[)?(?:(\d{1,2}):)?(\d{1,2}(?:\.\d+)?)(?:\])?\s*[,:，、]?\s*(.+)$")


def _to_int(value, default):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_text(text):
    text = html.unescape(str(text or ""))
    text = text.replace("\r", " ").replace("\n", " ")
    # ASS 用花括号包覆样式指令，正文里的花括号必须换掉，否则会被当成指令
    text = text.replace("{", "｛").replace("}", "｝")
    text = text.replace("\\", "／")
    return re.sub(r"\s+", " ", text).strip()


def _item(time_s, text, mode=1, size=25, color=0xFFFFFF):
    text = _clean_text(text)
    if not text:
        return None
    return {"time": max(0.0, _to_float(time_s)),
            "text": text,
            "mode": _to_int(mode, 1),
            "size": _to_int(size, 25),
            "color": _to_int(color, 0xFFFFFF) & 0xFFFFFF}


def parse_xml(text):
    """B 站 XML 弹幕 → [{time,text,mode,size,color}]"""
    out = []
    for m in _XML_D_RE.finditer(text or ""):
        fields = m.group(1).split(",")
        if len(fields) < 4:
            continue
        item = _item(fields[0], m.group(2), fields[1], fields[2], fields[3])
        if item:
            out.append(item)
    out.sort(key=lambda x: x["time"])
    return out


def _json_time(d):
    for key in ("time", "progress", "start", "st", "t", "offset", "video_time"):
        if key in d:
            val = d.get(key)
            if key == "progress":       # B 站 progress 单位是毫秒
                return _to_float(val) / 1000.0
            return _to_float(val)
    return 0.0


def _json_text(d):
    for key in ("text", "content", "m", "msg", "body", "title"):
        val = d.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def parse_json(text):
    """JSON 弹幕（B 站 danmaku / 通用数组）→ 统一列表"""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    arr = []

    def walk(node, depth=0):
        if depth > 6:
            return
        if isinstance(node, list):
            if node and isinstance(node[0], dict) and _json_text(node[0]):
                arr.extend(node)
            else:
                for child in node:
                    walk(child, depth + 1)
        elif isinstance(node, dict):
            if _json_text(node) and any(
                    k in node for k in ("time", "progress", "start", "st", "t")):
                arr.append(node)
            else:
                for key in ("elems", "comments", "danmaku", "data", "list",
                            "items", "result"):
                    if key in node:
                        walk(node[key], depth + 1)

    walk(data)
    out = []
    for d in arr:
        item = _item(_json_time(d), _json_text(d),
                     d.get("mode", d.get("type", 1)),
                     d.get("size", d.get("fontsize", 25)),
                     d.get("color", d.get("colorDecimal", 0xFFFFFF)))
        if item:
            out.append(item)
    out.sort(key=lambda x: x["time"])
    return out


def parse_text(text):
    """纯文本弹幕：每行「[mm:ss] 文本」/「秒数 文本」/「秒数,文本」"""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _TS_RE.match(line)
        if not m:
            continue
        minutes = _to_float(m.group(1) or 0)
        seconds = _to_float(m.group(2))
        item = _item(minutes * 60 + seconds, m.group(3))
        if item:
            out.append(item)
    out.sort(key=lambda x: x["time"])
    return out


def parse(text):
    """自动识别 XML / JSON / 文本"""
    if not text:
        return []
    head = text.lstrip()[:400]
    if "<d " in head or "<i>" in head or head.lower().startswith("<?xml"):
        items = parse_xml(text)
        if items:
            return items
    if head.startswith(("{", "[")):
        items = parse_json(text)
        if items:
            return items
    return parse_text(text)


def _fmt_time(sec):
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_color(rgb):
    """0xRRGGBB → ASS &H00BBGGRR&"""
    r = (rgb >> 16) & 0xFF
    g = (rgb >> 8) & 0xFF
    b = rgb & 0xFF
    return "&H00%02X%02X%02X&" % (b, g, r)


def _text_width(text, font_size):
    """粗略估算文本像素宽：CJK 按 1 个字号，ASCII 按 0.55 个字号"""
    width = 0.0
    for ch in text:
        width += font_size if ord(ch) > 0x2E80 else font_size * 0.55
    return width


def build_ass(items, width=1920, height=1080, duration=DEFAULT_DURATION,
              font_size=DEFAULT_FONT_SIZE, font_name="Microsoft YaHei UI",
              opacity=0.92):
    """弹幕列表 → ASS 文本（PlayRes 固定 1920x1080，实际窗口由 libass 缩放）"""
    width = max(320, int(width or 1920))
    height = max(240, int(height or 1080))
    font_size = max(12, int(font_size or DEFAULT_FONT_SIZE))
    duration = max(2.0, float(duration or DEFAULT_DURATION))
    alpha = 0xFF - int(max(0.0, min(1.0, float(opacity))) * 0xFF)
    line_h = font_size + 8
    top_rows = max(1, int(height * _TOP_RATIO // line_h))
    bottom_rows = max(1, int(height * (1 - _TOP_RATIO) // line_h))

    # 每条轨道下一次可用时间；顶部固定/底部固定各用一套行号
    scroll_free = [0.0] * top_rows
    top_free = [0.0] * top_rows
    bottom_free = [0.0] * bottom_rows

    def pick(lanes, now):
        """选一条空闲轨道；都忙时选最早空出的（允许密集重叠）"""
        best_i, best_t = -1, None
        for i, free_at in enumerate(lanes):
            if free_at <= now:
                return i
            if best_t is None or free_at < best_t:
                best_i, best_t = i, free_at
        return best_i if best_i >= 0 else 0

    lines = []
    for it in sorted(items, key=lambda x: x["time"]):
        t = max(0.0, float(it.get("time") or 0))
        text = it.get("text") or ""
        if not text:
            continue
        size = max(18, min(72, int(it.get("size") or 25)))
        # B 站字号 25 对应 1080p 下约 42px；按比例换算并受全局字号约束
        size = int(round(size / 25.0 * font_size))
        mode = int(it.get("mode") or 1)
        color = _ass_color(it.get("color") or 0xFFFFFF)
        tw = _text_width(text, size)
        if mode in (4, 5):                      # 底部/顶部固定
            lanes = bottom_free if mode == 4 else top_free
            row = pick(lanes, t)
            end = t + max(4.0, duration * 0.75)
            lanes[row] = end
            y = (height - line_h * (row + 1)) if mode == 4 else line_h * row + 4
            effect = f"{{\\an8\\pos({width // 2},{y})\\c{color}\\fs{size}}}"
            lines.append(f"Dialogue: 0,{_fmt_time(t)},{_fmt_time(end)},"
                         f"Danmaku,,0,0,0,,{effect}{text}")
            continue
        # 滚动弹幕：设定 lane，用 move 从右侧外飞到左侧外
        row = pick(scroll_free, t)
        speed = (width + tw) / duration
        free_at = t + tw / speed if speed else t + duration
        scroll_free[row] = free_at
        y = line_h * row + 4
        effect = (f"{{\\an7\\move({width + int(tw)},{y},{-int(tw)},{y})"
                  f"\\c{color}\\fs{size}}}")
        lines.append(f"Dialogue: 0,{_fmt_time(t)},{_fmt_time(t + duration)},"
                     f"Danmaku,,0,0,0,,{effect}{text}")

    header = f"""[Script Info]
ScriptType: v4.00+
Collisions: Normal
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Danmaku,{font_name},{font_size},&H{alpha:02X}FFFFFF,&H{alpha:02X}FFFFFF,&H{alpha:02X}000000,&H{alpha:02X}000000,0,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + "\n".join(lines) + ("\n" if lines else "")


def build_from_text(text, **kwargs):
    """弹幕原文 → ASS 文本（解析失败返回空串）"""
    items = parse(text)
    return build_ass(items, **kwargs) if items else ""
