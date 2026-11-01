# -*- coding: utf-8 -*-
"""验证直播页新结构：全屏播放 + 左侧两层列表（分组 → 频道）+ 进入即自动播放

断言：
1. 进入页面自动播放默认频道（上次 → CCTV1 → 第一个）
2. 一级分组列、二级频道列都已渲染，序号/▶ 标记正确
3. ↓ 换台、←→ 切列、数字键选台生效
产物：dist/l1_live_overlay.png / dist/l2_live_hidden.png
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PIL import ImageGrab

from tvboxosc import hawk
from tvboxosc.app import App
from tvboxosc.ui_live import Page as LivePage

OUT = os.path.join(ROOT, 'dist')
os.makedirs(OUT, exist_ok=True)

SRC = os.path.join(OUT, '_live_demo.txt')
with open(SRC, 'w', encoding='utf-8') as f:
    f.write("央视频道,#genre#\n"
            "CCTV1,http://127.0.0.1:1/cctv1.m3u8\n"
            "CCTV2,http://127.0.0.1:1/cctv2.m3u8$备用\n"
            "CCTV5,http://127.0.0.1:1/cctv5.m3u8\n"
            "卫视频道,#genre#\n"
            "湖南卫视,http://127.0.0.1:1/hn.m3u8\n"
            "浙江卫视,http://127.0.0.1:1/zj.m3u8\n")

hawk.put(hawk.LIVE_API_URL, SRC)
hawk.delete(hawk.LIVE_CHANNEL)      # 清掉上次频道，验证 CCTV1 默认选中

app = App()
ctx = {}
fails = []


def check(cond, msg):
    print(('OK  ' if cond else 'FAIL') + ' ' + msg, flush=True)
    if not cond:
        fails.append(msg)


def shot(name):
    # 置顶再截屏，避免被模拟器/IDE 等前台窗口遮挡
    app.attributes("-topmost", True)
    app.lift()
    app.update()
    ImageGrab.grab().save(os.path.join(OUT, name + '.png'))
    app.attributes("-topmost", False)
    print('shot', name, flush=True)


def step_open():
    page = app.switch(LivePage)
    ctx['page'] = page
    app.after(3500, lambda: step_assert1())


def step_assert1():
    p = ctx['page']
    check(len(p.groups) == 2, f'一级分组数=2（实际 {len(p.groups)}）')
    check(len(p._group_btns) == 2, f'分组按钮=2（实际 {len(p._group_btns)}）')
    chs = [c for c in p.channels if c[0] == p.cur_group]
    check(len(p._ch_btns) == len(chs), f'二级频道按钮={len(chs)}（实际 {len(p._ch_btns)}）')
    check(p.cur_ch is not None, '已自动播放频道')
    if p.cur_ch:
        check(p.cur_ch[1] == 'CCTV1', f'默认频道=CCTV1（实际 {p.cur_ch[1]}）')
    check('CCTV1' in p.status.cget('text'), f'状态栏含频道名：{p.status.cget("text")}')
    check(p._visible, '进入后列表可见（5 秒后自动隐藏）')
    marked = [b for b, c in p._ch_btns if b.cget('text').startswith('▶')]
    check(len(marked) == 1, f'当前频道 ▶ 标记数=1（实际 {len(marked)}）')
    shot('l1_live_overlay')
    app.after(300, step_switch_channel)


def step_switch_channel():
    p = ctx['page']
    # 焦点进入二级频道列，再按 ↓ 换到下一个频道
    p._to_channels()
    ctx['before'] = p.cur_ch[1] if p.cur_ch else None
    app.update()
    app.event_generate('<Down>')
    app.update()
    app.after(600, step_assert2)


def step_assert2():
    p = ctx['page']
    after = p.cur_ch[1] if p.cur_ch else None
    check(after != ctx['before'], f'↓ 换台生效：{ctx["before"]} → {after}')
    # ← 回到一级分组列，再 ↓ 切到第二个分组
    app.event_generate('<Left>')
    app.update()
    area = p._focus_area()
    check(area == 'group', f'← 焦点回到分组列（实际 {area}）')
    app.event_generate('<Down>')
    app.update()
    app.after(800, step_assert3)


def step_assert3():
    p = ctx['page']
    check(p.cur_group == '卫视频道', f'分组↓切到卫视频道（实际 {p.cur_group}）')
    check(p.cur_ch and p.cur_ch[0] == '卫视频道', '该分组第一个频道已自动播放')
    # 数字键选台：2 → 全局第 2 个频道 CCTV2
    app.event_generate('<Key-2>')
    app.update()
    app.after(1800, step_assert4)


def step_assert4():
    p = ctx['page']
    check(p.cur_ch and p.cur_ch[1] == 'CCTV2', f'数字键选台=CCTV2（实际 {p.cur_ch[1] if p.cur_ch else None}）')
    # Esc：先隐藏列表，再 Esc 返回
    app.event_generate('<Escape>')
    app.update()
    check(not p._visible, 'Esc 隐藏列表')
    shot('l2_live_hidden')
    step_cleanup()


def step_cleanup():
    hawk.delete(hawk.LIVE_API_URL)
    hawk.delete(hawk.LIVE_CHANNEL)
    try:
        from tvboxosc.player import MpvPlayer
        MpvPlayer.shutdown()
    except Exception:
        pass
    os.remove(SRC)
    app.destroy()
    print('FAILS:', fails if fails else 'none', flush=True)


app.after(300, step_open)
app.after(20000, lambda: app.destroy())
app.mainloop()
print('DONE', flush=True)
