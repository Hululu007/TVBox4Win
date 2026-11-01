# -*- coding: utf-8 -*-
"""验证直播页的频道编号与节目单（EPG）

断言：
1. 二级列表编号是**全局台号**（第二组首台的编号接续第一组），与数字键选台一致
2. 底部节目单条显示 台号 / 台名 / 当前节目+时段 / 下一节目+时段
3. 切台后台号与节目单同步刷新
4. 无节目单时给出可操作提示（不是空白）
产物：dist/e1_live_epg.png
"""
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PIL import ImageGrab

from tvboxosc import hawk
from tvboxosc import ui_live
from tvboxosc.app import App
from tvboxosc.ui_live import Page as LivePage

OUT = os.path.join(ROOT, 'dist')
os.makedirs(OUT, exist_ok=True)

SRC = os.path.join(OUT, '_live_epg_demo.txt')
with open(SRC, 'w', encoding='utf-8') as f:
    f.write("央视频道,#genre#\n"
            "CCTV1,http://127.0.0.1:1/cctv1.m3u8\n"
            "CCTV2,http://127.0.0.1:1/cctv2.m3u8\n"
            "CCTV5,http://127.0.0.1:1/cctv5.m3u8\n"
            "卫视频道,#genre#\n"
            "湖南卫视,http://127.0.0.1:1/hn.m3u8\n"
            "浙江卫视,http://127.0.0.1:1/zj.m3u8\n")

hawk.put(hawk.LIVE_API_URL, SRC)
hawk.delete(hawk.LIVE_CHANNEL)

now = datetime.now()


def fake_progs(title_cur, title_next):
    return [
        {'start': now - timedelta(minutes=30), 'stop': now + timedelta(minutes=30),
         'title': title_cur},
        {'start': now + timedelta(minutes=30), 'stop': now + timedelta(minutes=90),
         'title': title_next},
    ]


FAKE = {
    'CCTV1': fake_progs('新闻直播间', '今日说法'),
    'CCTV2': fake_progs('第一时间', '消费主张'),
    'CCTV5': [],
    '湖南卫视': fake_progs('湖南新闻联播', '快乐大本营'),
    '浙江卫视': fake_progs('浙江新闻', '奔跑吧'),
}
CALLS = []


def fake_load(name, day=None, addr=None, timeout=8):
    CALLS.append(name)
    return FAKE.get(name, [])


ui_live.epg.load = fake_load     # 不真连外网，用固定节目单

app = App()
ctx = {}
fails = []


def check(cond, msg):
    print(('OK  ' if cond else 'FAIL') + ' ' + msg, flush=True)
    if not cond:
        fails.append(msg)


def shot(name):
    app.attributes('-topmost', True)
    app.lift()
    app.update()
    ImageGrab.grab().save(os.path.join(OUT, name + '.png'))
    app.attributes('-topmost', False)
    print('shot', name, flush=True)


def step_open():
    App.go_home = lambda self: ctx.setdefault('home', 0)
    app.switch(LivePage)
    app.after(3000, step_assert1)


def step_assert1():
    p = ctx['page']
    check(len(p.channels) == 5, f'频道总数=5（实际 {len(p.channels)}）')
    # 1. 全局台号
    names = [c[1] for c in p.channels]
    check(names == ['CCTV1', 'CCTV2', 'CCTV5', '湖南卫视', '浙江卫视'], f'频道顺序：{names}')
    check(p.ch_number(p.channels[3]) == 4,
          f'第二组首台全局编号=4（实际 {p.ch_number(p.channels[3])}）')
    texts = [b.cget('text') for b, _ in p._ch_btns]
    print('央视频道列表：', texts, flush=True)
    check(any('1' in t and 'CCTV1' in t for t in texts), '列表显示台号 1 CCTV1')

    # 2. 节目单（并入底部控制栏）
    check(p.bottom.winfo_ismapped(), '控制栏（含节目单行）可见')
    check(p.num_lbl.cget('text') == '01', f'台号显示 01（实际 {p.num_lbl.cget("text")}）')
    check(p.epg_name.cget('text') == 'CCTV1', f'台名：{p.epg_name.cget("text")}')
    check('新闻直播间' in p.epg_cur.cget('text'),
          f'当前节目：{p.epg_cur.cget("text")}')
    check('今日说法' in p.epg_next.cget('text'),
          f'下一节目：{p.epg_next.cget("text")}')
    check(CALLS[:1] == ['CCTV1'], f'按频道名请求 EPG（calls={CALLS[:3]}）')
    shot('e1_live_epg')
    app.after(400, step_switch)


def step_switch():
    p = ctx['page']
    # 切到第二组的第一个频道（全局编号 4）
    p._to_groups()
    app.update()
    p._select_group('卫视频道', play=True)
    app.update()
    app.after(1200, step_assert2)


def step_assert2():
    p = ctx['page']
    check(p.cur_ch and p.cur_ch[1] == '湖南卫视', f'已切到湖南卫视（{p.cur_ch[1] if p.cur_ch else None}）')
    check(p.num_lbl.cget('text') == '04', f'切台后号显示 04（实际 {p.num_lbl.cget("text")}）')
    check('湖南新闻联播' in p.epg_cur.cget('text'),
          f'切台后当前节目：{p.epg_cur.cget("text")}')
    check('快乐大本营' in p.epg_next.cget('text'),
          f'切台后下一节目：{p.epg_next.cget("text")}')
    shot('e2_live_epg_switch')
    # 无节目单的频道
    p._play(p.channels[2])   # CCTV5
    app.update()
    app.after(1200, step_assert3)


def step_assert3():
    p = ctx['page']
    check('暂无节目单' in p.epg_cur.cget('text'),
          f'无节目单提示：{p.epg_cur.cget("text")}')
    check(p.num_lbl.cget('text') == '03', f'台号 03（实际 {p.num_lbl.cget("text")}）')
    step_cleanup()


def step_cleanup():
    hawk.delete(hawk.LIVE_API_URL)
    hawk.delete(hawk.LIVE_CHANNEL)
    try:
        from tvboxosc.player import MpvPlayer
        MpvPlayer.shutdown()
    except Exception:
        pass
    try:
        os.remove(SRC)
    except Exception:
        pass
    app.destroy()
    print('FAILS:', fails if fails else 'none', flush=True)


orig_switch = app.switch


def _switch(cls, *a, **kw):
    page = orig_switch(cls, *a, **kw)
    ctx['page'] = page
    return page


app.switch = _switch
app.after(300, step_open)
app.after(25000, lambda: app.destroy())
app.mainloop()
print('DONE', flush=True)
