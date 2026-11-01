# -*- coding: utf-8 -*-
"""P1 功能回归：弹幕/二维码/EPG 回看/直播 m3u 扩展/历史合并/搜索范围/缩放/推送接口

纯逻辑测试，不启动 tkinter 主窗口、不联网（推送接口只测纯函数与注册表）。
用法：python tests/test_p1.py
"""
import inspect
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from tvboxosc import (danmaku, data_api, epg, hawk, qr, store, ui_collect,
                      ui_grid, ui_history, ui_live, ui_push, ui_search,
                      ui_setting)
from tvboxosc.player import MpvPlayer

_fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name +
          (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def eq(name, got, want):
    check(name, got == want, f"got={got!r} want={want!r}")


# ---------------------------------------------------------------- 弹幕 ----
xml = ('<?xml version="1.0"?><i><d p="1.5,1,25,16777215">你好</d>'
       '<d p="2,5,25,16711680">顶部 {弹幕}</d></i>')
items = danmaku.parse(xml)
eq("danmaku: XML 条数", len(items), 2)
eq("danmaku: XML 文本", items[0]["text"], "你好")
eq("danmaku: XML 时间", items[0]["time"], 1.5)
eq("danmaku: 模式保留", items[1]["mode"], 5)
check("danmaku: 花括号替换", "{" not in items[1]["text"], items[1]["text"])

js = json.dumps({"elems": [{"progress": 2500, "text": "json 弹幕",
                            "mode": 1, "color": 255}]})
jitems = danmaku.parse(js)
eq("danmaku: JSON 条数", len(jitems), 1)
eq("danmaku: progress 毫秒转秒", jitems[0]["time"], 2.5)

titems = danmaku.parse_text("01:23 第一分钟\n90 一秒半\n# 注释\n")
eq("danmaku: 文本条数", len(titems), 2)
eq("danmaku: mm:ss", titems[0]["time"], 83.0)
eq("danmaku: 秒数", titems[1]["time"], 90.0)

ass = danmaku.build_ass(items + jitems, width=1280, height=720)
check("danmaku: ASS 头部", ass.startswith("[Script Info]"), ass[:20])
check("danmaku: ASS 事件", ass.count("Dialogue:") == 3, ass[-120:])
check("danmaku: ASS 颜色", "&H000000FF&" in ass or "\\c&H" in ass)

# ---------------------------------------------------------------- 二维码 ----
matrix, version, mask = qr.encode("http://192.168.1.10:9978/")
size = len(matrix)
check("qr: 版本/边长一致", size == 17 + 4 * version, f"size={size} v={version}")
check("qr: 定位图案", matrix[0][0] and matrix[0][6] and not matrix[1][1])
check("qr: 掩码范围", 0 <= mask <= 7)
matrix2, _v, _m = qr.encode("http://192.168.1.10:9978/?t=中文")
check("qr: 中文内容可编码", len(matrix2) >= size)
check("qr: size_for", qr.size_for("http://a/") == 17 + 4 * 1)

# ---------------------------------------------------------------- EPG ----
multi = json.dumps([
    {"channel_name": "CCTV1", "epg_data": [
        {"title": "新闻联播", "start": "19:00", "stop": "19:30"}]},
    {"channel_name": "CCTV2", "epg_data": [
        {"title": "其它", "start": "19:00", "stop": "20:00"}]},
])
progs = epg.parse_json(multi, ["CCTV1"])
eq("epg: 多频道命中", len(progs), 1)
eq("epg: 标题", progs[0]["title"], "新闻联播")

roll = epg.parse_json(json.dumps([
    {"title": "晚高峰", "start": "23:00", "stop": "23:59"},
    {"title": "午夜场", "start": "00:30", "stop": "01:00"},
]), ["X"])
eq("epg: 跨零点排序", [p["title"] for p in roll], ["晚高峰", "午夜场"])
check("epg: 跨零点顺延一天",
      roll[1]["start"].date() > roll[0]["start"].date())

hh = epg._parse_hhmm("12:34:56")
eq("epg: HH:MM:SS", (hh.hour, hh.minute, hh.second), (12, 34, 56))

# 回看模板（_catchup_url 只用 self.cur_ch + CHANNEL_META）
ui_live.CHANNEL_META[("央视", "CCTV1")] = {
    "catchup": "http://h/catchup?ch={channel}&t={start}",
    "tvg_id": "cctv1"}
stub = type("Stub", (), {"cur_ch": ("央视", "CCTV1", [])})()
prog = {"title": "x", "start": roll[0]["start"], "stop": roll[0]["stop"]}
caurl = ui_live.Page._catchup_url(stub, prog)
check("catchup: 模板替换", "ch=CCTV1" in caurl and "{" not in caurl, caurl)
eq("catchup: 节目自带 url 优先",
   ui_live.Page._catchup_url(stub, {"url": "http://p/1"}), "http://p/1")

# ------------------------------------------------------------ 直播 m3u ----
ui_live.GROUP_PASSWORD.clear()
ui_live.CHANNEL_META.clear()
m3u = "\n".join([
    "#EXTM3U",
    '#EXTINF:-1 tvg-id="cctv1" group-title="央视" '
    'catchup="append" catchup-source="http://h/c?t={utcstart}",CCTV1',
    "#EXTVLCOPT:http-user-agent=UA/1.0",
    "http://a/1.m3u8|Referer=http://a/",
    "#EXTINF:-1 group-title=\"加密\" group-password=\"8888\",加密台",
    "http://a/2.m3u8",
])
chs = ui_live._parse_live_text(m3u)
eq("live: m3u 频道数", len(chs), 2)
eq("live: 分组", chs[0][0], "央视")
eq("live: 频道名", chs[0][1], "CCTV1")
src0 = chs[0][2][0]
eq("live: 地址", src0[0], "http://a/1.m3u8")
eq("live: EXTVLCOPT+管道头", (src0[2].get("User-Agent"),
                              src0[2].get("Referer")),
   ("UA/1.0", "http://a/"))
eq("live: 加密分组密码", ui_live.GROUP_PASSWORD.get("加密"), "8888")
check("live: 回看元数据", ui_live.CHANNEL_META.get(
    ("央视", "CCTV1"), {}).get("catchup_source", "").startswith("http://h/c"))

txt = "央视,#genre#\nCCTV1,http://t/1.m3u8|User-Agent=UA2\n"
tchs = ui_live._parse_live_text(txt)
eq("live: txt 分支", (tchs[0][0], tchs[0][1]), ("央视", "CCTV1"))
eq("live: txt 管道头", tchs[0][2][0][2].get("User-Agent"), "UA2")

# ------------------------------------------------------------ 历史合并 ----
_orig_db, _orig_path = store._db, store.data_path


def _restore_store():
    global _orig_db, _orig_path
    try:
        if store._db is not None:
            store._db.close()
    except Exception:
        pass
    store._db = _orig_db
    store.data_path = _orig_path


try:
    store._db = None
    store.data_path = lambda *names: ":memory:"
    store._conn()   # 建表
    store.save_record("s1", "v1", "同名片", "", "", "第1集", 0, 0)
    store.save_record("s2", "v2", "同名片", "", "", "第2集", 0, 0)
    hawk._load()
    _old_merge = hawk._data.get(hawk.HISTORY_MERGE, None)
    hawk._data[hawk.HISTORY_MERGE] = 1
    eq("store: 历史合并", len(store.all_records()), 1)
    hawk._data[hawk.HISTORY_MERGE] = 0
    eq("store: 未合并且保留两条", len(store.all_records()), 2)
    if _old_merge is None:
        hawk._data.pop(hawk.HISTORY_MERGE, None)
    else:
        hawk._data[hawk.HISTORY_MERGE] = _old_merge
    store.delete_record("v1", "s1")
    eq("store: 按 (id,源) 删除", len(store.all_records()), 1)
finally:
    _restore_store()

# ------------------------------------------------------------ 标签/动作 ----
class _Bean:
    key = "test"


data_api._vod_tags.clear()
data_api._capture_tags(_Bean, [
    {"vod_id": "f1", "vod_tag": "folder"},
    {"vod_id": "a1", "vod_tag": "action"},
    {"vod_id": "n1"},
    "not-a-dict",
])
eq("tag: folder", data_api.get_vod_tag(_Bean, "f1"), "folder")
eq("tag: action", data_api.get_vod_tag(_Bean, "a1"), "action")
eq("tag: 无标记", data_api.get_vod_tag(_Bean, "n1"), "")


class _CmsBean(_Bean):
    type = 0
    api = "http://x/api.php"


ok, msg = data_api.do_action(_CmsBean, "x")
check("action: 非爬虫源降级", (ok is False) and msg, (ok, msg))

# ------------------------------------------------------------ 搜索范围 ----
_src_search = inspect.getsource(ui_search.Page._search_run)
check("search: searchable 1/2", "searchable in (1, 2)" in _src_search)
hawk._load()
_old_fast = hawk._data.get(hawk.FAST_SEARCH, None)
hawk._data[hawk.FAST_SEARCH] = 0
check("search: 快速搜索关", ui_search.Page._fast_search() is False)
hawk._data[hawk.FAST_SEARCH] = 1
check("search: 快速搜索开", ui_search.Page._fast_search() is True)
if _old_fast is None:
    hawk._data.pop(hawk.FAST_SEARCH, None)
else:
    hawk._data[hawk.FAST_SEARCH] = _old_fast

# ------------------------------------------------------------ 画面缩放 ----
core = {}
MpvPlayer.apply_scale(core, scale=1)
eq("scale: 16:9", core.get("video-aspect-override"), "16:9")
core = {}
MpvPlayer.apply_scale(core, scale=2)
eq("scale: 4:3", core.get("video-aspect-override"), "4:3")
core = {"osd-width": 1920, "osd-height": 1080}
MpvPlayer.apply_scale(core, scale=3)
eq("scale: 填充", core.get("video-aspect-override"), "1920:1080")
core = {}
MpvPlayer.apply_scale(core, scale=4)
eq("scale: 裁剪", core.get("panscan"), 1.0)
core = {}
MpvPlayer.apply_scale(core, scale=5)
eq("scale: 原始", core.get("video-unscaled"), "yes")
eq("scale: 名称", MpvPlayer.scale_name(5), "原始")

# ------------------------------------------------------------ 推送接口 ----
eq("push: 文件名消毒", ui_push._safe_filename("../../etc/passwd"), "passwd")
eq("push: 反斜杠路径", ui_push._safe_filename("..\\..\\a.txt"), "a.txt")
eq("push: 非法字符", ui_push._safe_filename('a<b>c?.mp4'), "a_b_c_.mp4")
check("push: 越界路径拒绝", ui_push._local_file("../outside") is None)
check("push: 应用目录内文件",
      ui_push._local_file("tvboxosc/__init__.py") is not None)
raw = (b'--X\r\nContent-Disposition: form-data; name="file"; '
       b'filename="a.txt"\r\nContent-Type: text/plain\r\n\r\nhello\r\n--X--\r\n')
eq("push: multipart 解析", ui_push._parse_multipart(raw, b"X"),
   [("a.txt", b"hello")])

_called = []
ui_push.register_action("p1test", lambda: _called.append(1))
check("push: 动作注册", ui_push.ACTIONS.get("p1test") is not None)
ui_push.unregister_action("p1test")
check("push: 动作注销", "p1test" not in ui_push.ACTIONS)

_push_src = inspect.getsource(ui_push)
for needle in ("/proxyM3u8", "/dns-query", "_handle_upload", "_serve_file",
               "_handle_action", "_handle_cache", "_make_qr"):
    check("push: 路由 " + needle, needle in _push_src)

# ------------------------------------------------------------ 页面集成 ----
_grid_src = inspect.getsource(ui_grid.Page)
check("grid: 追加分页", "def _load_more" in _grid_src
      and "append=True" in _grid_src)
check("grid: 文件夹下钻", "def _open_folder" in _grid_src)
check("grid: 动作条目", "def _run_action" in _grid_src)
check("grid: 豆瓣新接口", "j/new_search_subjects" in _grid_src)
check("grid: 壁纸横幅", "def _wallpaper_photo" in _grid_src)

_hist_src = inspect.getsource(ui_history.Page)
check("history: 海报网格", "poster_grid.cell" in _hist_src)
check("history: 多选按 (id,源)",
      '(r["vod_id"], r["source_key"])' in _hist_src)
check("history: 清空确认", "def _confirm" in _hist_src)
check("history: 失效源回落搜索", "self._search_name" in _hist_src)

_set_src = inspect.getsource(ui_setting.Page)
for name in ("数据备份", "数据恢复", "快速搜索", "自动换线", "自动播放",
             "弹幕", "弹幕源", "字幕字号", "默认倍速", "记住倍速",
             "防休眠", "播放缓存", "历史合并", "开发者模式", "查看日志",
             "打开数据目录", "直播倒序", "直播加密分组", "首页壁纸",
             "壁纸图片"):
    check("setting: 卡片 " + name, name in _set_src)

check("collect: 海报网格", "poster_grid.cell" in inspect.getsource(
    ui_collect.Page))

print()
if _fails:
    print("FAILED:", len(_fails), _fails)
    sys.exit(1)
print("ALL PASS")
