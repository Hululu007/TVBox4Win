# -*- coding: utf-8 -*-
"""P0-3 爬虫直播源（lives[] type=3）验证

覆盖：
- type 默认判定（api 含 .py/.js、csp_ jar → 3）
- liveContent 返回值（JSON 数组 / dict / txt）→ 频道列表
- parse_live_source 走爬虫分支（loadProxyLives 语义）
- jar / py 运行时 live_content 方法签名与转发
- 播放时使用每频道 header
"""
import inspect
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from tvboxosc import hawk, jar_spider, py_spider, spider, ui_live
from tvboxosc.player import MpvPlayer

_fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name +
          (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def eq(name, got, want):
    check(name, got == want, f"got={got!r} want={want!r}")


# ---------------------------------------------------------------- type ----
eq("type: api .py", ui_live._live_entry_type(
    {"api": "https://x/live.py"}), "3")
eq("type: api .js", ui_live._live_entry_type(
    {"api": "https://x/live.js?x=1"}), "3")
eq("type: csp_ jar", ui_live._live_entry_type(
    {"api": "csp_Live"}), "3")
eq("type: 普通 txt", ui_live._live_entry_type(
    {"url": "https://x/live.txt"}), "0")
eq("type: 显式 type=0 优先", ui_live._live_entry_type(
    {"api": "https://x/live.py", "type": 0}), "0")
eq("type: 显式 type=1 不兼容", ui_live._live_entry_type(
    {"url": "https://x/live.txt", "type": 1}), "1")

# ------------------------------------------------------------ JSON 解析 ----
arr = [
    {"group": "央视", "channels": [
        {"name": "CCTV1", "urls": ["http://a/1.m3u8", "http://a/2.m3u8"]},
        {"name": "CCTV2", "url": "http://a/3.m3u8",
         "header": {"Referer": "http://a/"}},
        {"name": "坏频道", "urls": ["ftp://bad/x"]},
    ]},
    {"name": "卫视", "channels": [{"name": "湖南卫视", "urls": ["rtmp://h/1"]}]},
]
chs = ui_live._channels_from_json(arr)
eq("json: 频道数", len(chs), 3)
eq("json: 分组", [c[0] for c in chs], ["央视", "央视", "卫视"])
eq("json: 多线路", chs[0][2],
   [("http://a/1.m3u8", "线路1", None), ("http://a/2.m3u8", "线路2", None)])
eq("json: 单 url + header", chs[1][2],
   [("http://a/3.m3u8", "线路1", {"Referer": "http://a/"})])
eq("json: 非 http 协议被过滤（频道剔除）", [c[1] for c in chs],
   ["CCTV1", "CCTV2", "湖南卫视"])

text = json.dumps(arr, ensure_ascii=False)
parsed = ui_live._parse_live_text(text)
eq("json 文本: 频道数", len(parsed), 3)
eq("json 文本: 保留 header", parsed[1][2][0][2], {"Referer": "http://a/"})

eq("liveContent: 直接数组", len(ui_live._channels_from_live_result(arr)), 3)
eq("liveContent: dict.list", len(ui_live._channels_from_live_result(
    {"list": arr})), 3)
eq("liveContent: dict.data", len(ui_live._channels_from_live_result(
    {"data": arr})), 3)
eq("liveContent: dict.channels 单分组",
   len(ui_live._channels_from_live_result(arr[0])), 2)
eq("liveContent: 空", ui_live._channels_from_live_result(None), [])

txt = "央视频道,#genre#\nCCTV1,http://a/1.m3u8$源1\n"
eq("liveContent: txt 兼容", len(ui_live._channels_from_live_result(txt)), 1)

# --------------------------------------------------- parse_live_source ----
class _FakeSpider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def live_content(self, url=""):
        self.calls.append(url)
        return self.result


_orig_get_spider = spider.get_spider
_orig_epg = hawk.get(hawk.EPG_URL, "")
fake = _FakeSpider(json.dumps(arr, ensure_ascii=False))
captured = {}

def _fake_get_spider(bean):
    captured["bean"] = bean
    return fake

spider.get_spider = _fake_get_spider
try:
    cfg = {"lives": [
        {"name": "爬虫直播", "type": 3,
         "api": "https://x/live.py", "url": "https://x/live?type=json",
         "ext": {"a": 1}, "epg": "https://x/epg.xml"},
        {"name": "备用txt", "url": "https://x/live.txt"},
    ]}
    name, chs3 = ui_live.parse_live_source(
        json.dumps(cfg, ensure_ascii=False), "https://x/config.json")
    epg_after = hawk.get(hawk.EPG_URL, "")
finally:
    spider.get_spider = _orig_get_spider
    hawk.put(hawk.EPG_URL, _orig_epg)

eq("parse: 源名", name, "爬虫直播")
eq("parse: 频道数", len(chs3), 3)
eq("parse: liveContent 参数=条目 url", fake.calls, ["https://x/live?type=json"])
eq("parse: bean.api", getattr(captured.get("bean"), "api", None),
   "https://x/live.py")
eq("parse: bean.ext", getattr(captured.get("bean"), "ext", None), {"a": 1})
eq("parse: EPG 写入", epg_after, "https://x/epg.xml")

# ------------------------------------------------------------ 运行时 ----
class _FakeJs:
    def __init__(self):
        self.seen = None

    def _site_call(self, cls, method, ext, rest):
        self.seen = (cls, method, ext, rest)
        return '[{"group":"g","channels":[{"name":"n","urls":["http://h/1"]}]}]'


fjs = _FakeJs()
proxy = jar_spider._SiteProxy(fjs, "com.github.catvod.spider.X", "ext-str")
out = proxy.live_content("http://live/url")
eq("jar: 方法转发", fjs.seen,
   ("com.github.catvod.spider.X", "liveContent", "ext-str",
    ["http://live/url"]))
eq("jar: 返回值原样", out,
   '[{"group":"g","channels":[{"name":"n","urls":["http://h/1"]}]}]')

# py 运行时：有 liveContent / 没有 liveContent
tmp = tempfile.mkdtemp(prefix="tvbox_live_py_")
with open(os.path.join(tmp, "live_ok.py"), "w", encoding="utf-8") as f:
    f.write("class Spider:\n"
            "    def liveContent(self, url):\n"
            "        return '[{\"group\":\"g\",\"channels\":"
            "[{\"name\":\"n\",\"urls\":[\"http://h/1\"]}]}]'\n")
with open(os.path.join(tmp, "live_none.py"), "w", encoding="utf-8") as f:
    f.write("class Spider:\n    pass\n")

sp = py_spider.PySpider("live_ok", os.path.join(tmp, "live_ok.py"))
eq("py: live_content 转发", sp.live_content("u"),
   '[{"group":"g","channels":[{"name":"n","urls":["http://h/1"]}]}]')
sp2 = py_spider.PySpider("live_none", os.path.join(tmp, "live_none.py"))
try:
    sp2.live_content("u")
    check("py: 未实现 liveContent 报错", False)
except RuntimeError as e:
    check("py: 未实现 liveContent 报错", "liveContent" in str(e), str(e))

# 端到端：本地 py 文件作为 type=3 直播源（走 get_spider 真实路由）
sname, chs_e2e = ui_live._load_spider_live(
    {"name": "本地py", "type": 3, "api": os.path.join(tmp, "live_ok.py"),
     "url": "http://arg/url"}, 99)
eq("端到端: 源名", sname, "本地py")
eq("端到端: 频道数", len(chs_e2e), 1)
eq("端到端: 频道名", chs_e2e[0][1], "n")
eq("端到端: 播放地址", chs_e2e[0][2][0][0], "http://h/1")

# JS 运行时：转发 bridge 的 live 方法
src = inspect.getsource(spider.Spider.live_content)
check("js: 调用 bridge live", '_call("live"' in src, src)
check("js: 不再硬编码不支持", "暂不支持直播源" not in src, src)

# ------------------------------------------------------------ 播放 ----
play_src = inspect.getsource(ui_live.Page._play)
check("play: 容忍 3 元组", "item[2] if len(item) > 2" in play_src, play_src)
check("play: 传 header", "self.player.play(u, hdr)" in play_src, play_src)
check("MpvPlayer.play 支持 headers",
      "headers" in inspect.signature(MpvPlayer.play).parameters)

print()
if _fails:
    print("FAILED:", len(_fails), _fails)
    sys.exit(1)
print("ALL PASS")
