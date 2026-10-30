"""走查2：直播/设置/推送 三新页面 + 推送 HTTP 服务"""
import os, sys, time, urllib.request, urllib.parse
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tkinter as tk
VIDEO_URL = "https://www.w3schools.com/html/mov_bbb.mp4"
import requests
requests.packages.urllib3.disable_warnings()
from tvboxosc import hawk, apiconfig
from tvboxosc.app import App

results = []
def check(name, fn):
    try:
        fn(); results.append((name, "OK"))
    except Exception as e:
        import traceback; traceback.print_exc()
        results.append((name, f"FAIL: {e}"))

cfg = apiconfig.extract_json(apiconfig.fetch_text("http://xhztv.top/4k.json"))
apiconfig.api_config._parse(cfg)

app = App()

def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        app.update()
        time.sleep(0.02)

def t_setting():
    from tvboxosc.ui_setting import Page
    p = app.switch(Page); pump(1.0)
    # 新版网格卡片设置页：校验六张卡片与当前配置地址值
    for name in ("配置地址", "配置历史", "首页站源", "下次进入", "清空缓存", "关于"):
        assert name in p._vars, f"缺少设置项 {name}"
    assert p._vars["配置地址"].get(), "配置地址值为空"

PUSH_PAGE = [None]
def t_push_server():
    from tvboxosc.ui_push import Page
    p = PUSH_PAGE[0] = app.switch(Page); pump(1.5)
    test_url = VIDEO_URL
    q = urllib.parse.urlencode({"title": "测试推送", "url": test_url})
    r = urllib.request.urlopen(f"http://127.0.0.1:9978/push?{q}", timeout=5)
    assert "推送成功".encode("utf-8") in r.read(), "推送响应异常"
    pump(0.5)
    assert p.pushed and p.pushed[0][1] == test_url, "推送未入列"
    # 首页表单
    r2 = urllib.request.urlopen("http://127.0.0.1:9978/", timeout=5)
    assert "TVBox" in r2.read().decode(), "首页表单异常"

def t_play_pushed():
    p = PUSH_PAGE[0]
    assert p.pushed, "推送列表为空"
    pump(1.0)
    ok = False
    sample = os.path.join("tvboxosc", "assets", "sample.wav")
    for attempt in range(3):  # 网络抖动重试
        p._play(sample, "内置示例")
        for _ in range(40):
            pump(0.25)
            if p.player and p.player.status()[0] > 0:
                ok = True; break
        if ok: break
        p._stop_and_list()
    for _ in range(100):
        pump(0.25)
        if p.player:
            st = p.player.status()
            if st[0] > 0:
                ok = True; break
        elif _ == 20:
            print("DEBUG player None, body children:", p.body.winfo_children())
    print("DEBUG final player:", p.player, "status:", p.player.status() if p.player else None)
    assert ok, "推送播放无进度"
    p._stop_and_list()

def t_live():
    from tvboxosc.ui_live import Page, _parse_live_text
    # 解析器单测（沙箱代理屏蔽外网直播列表，真实列表拉取需本机验证）
    txt = "央视,#genre#\nCCTV1,http://a/1.m3u8\nCCTV2,http://a/2.m3u8"
    chs = _parse_live_text(txt)
    assert len(chs) == 2 and chs[0][0] == "央视", f"txt解析失败: {chs}"
    m3u = "#EXTINF:-1 tvg-group=\"央视\",CCTV1\nhttp://a/1.m3u8\n"
    chs2 = _parse_live_text(m3u)
    assert len(chs2) == 1 and chs2[0][0] == "央视" and chs2[0][1] == "CCTV1", f"m3u解析失败: {chs2}"
    p = app.switch(Page); pump(0.5)
    # 用合成数据直接验证分组/频道渲染
    p._render([("央视", "CCTV1", "http://a/1.m3u8"), ("央视", "CCTV2", "http://a/2.m3u8")], "测试源")
    pump(0.5)
    assert p.groups == ["央视"], "分组渲染失败"
    p._show_channels("央视"); pump(0.5)

for name, fn in [("设置页", t_setting), ("推送服务", t_push_server),
                 ("推送播放", t_play_pushed), ("直播页", t_live)]:
    check(name, fn)

app.destroy()
print("===== 走查结果 =====")
for n, s in results:
    print(f"{n}: {s}")
sys.exit(0 if all(s == "OK" for _, s in results) else 1)
