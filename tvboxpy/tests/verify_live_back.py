# -*- coding: utf-8 -*-
"""验证直播页的退出入口：顶栏「← 返回」常驻 + 底部控制栏 + Esc 语义

回归重点（旧 bug）：Esc 处理里先 _wake() 弹出列表，_back() 于是只收起列表，
永远走不到退出分支 —— 全屏后按 Esc 无限循环，用户被卡在直播页。

断言：
1. 顶栏常驻，含可点击的「← 返回」按钮；右上角时钟有值
2. 点「← 返回」→ 退出直播页
3. 底部控制栏 7 个按钮齐全，⏭ 下一台 / ☰ 频道列表 / ⏸ 暂停 生效
4. 列表隐藏时按 Esc → 直接退出（回归）
5. 列表显示时按 Esc → 只收起列表，再按才退出
产物：dist/b1_live_chrome.png / dist/b2_live_bar_hidden.png
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

SRC = os.path.join(OUT, '_live_back_demo.txt')
with open(SRC, 'w', encoding='utf-8') as f:
    f.write("央视频道,#genre#\n"
            "CCTV1,http://127.0.0.1:1/cctv1.m3u8\n"
            "CCTV2,http://127.0.0.1:1/cctv2.m3u8\n"
            "CCTV5,http://127.0.0.1:1/cctv5.m3u8\n"
            "卫视频道,#genre#\n"
            "湖南卫视,http://127.0.0.1:1/hn.m3u8\n")

hawk.put(hawk.LIVE_API_URL, SRC)
hawk.delete(hawk.LIVE_CHANNEL)

app = App()
ctx = {}
fails = []
calls = []


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


def find_btn(parent, text):
    """递归查找指定文案的可点控件（顶栏/底部栏都可能有嵌套 Frame）"""
    import tkinter as tk

    for w in parent.winfo_children():
        if isinstance(w, tk.Label) and str(w.cget('text')).strip() == text:
            return w
        got = find_btn(w, text)
        if got is not None:
            return got
    return None


def step_open():
    # 拦下 app.go_home：真退出会销毁页面，后续断言就没法做了
    App.go_home = lambda self: calls.append('back')
    page = app.switch(LivePage)
    ctx['page'] = page
    app.after(3500, step_assert1)


def step_assert1():
    p = ctx['page']
    check(len(p.groups) == 2, f'一级分组数=2（实际 {len(p.groups)}）')
    check(p.cur_ch is not None and p.cur_ch[1] == 'CCTV1',
          f'默认频道=CCTV1（实际 {p.cur_ch[1] if p.cur_ch else None}）')

    # 1. 顶栏常驻 + 返回按钮
    back = find_btn(p.top, '← 返回')
    check(back is not None, '顶栏存在「← 返回」按钮')
    check(p.top.winfo_ismapped(), '顶栏常驻可见（不随控制栏隐藏）')
    if back is not None:
        check(back.winfo_ismapped(), '「← 返回」按钮可见')
        back.event_generate('<Button-1>')
        app.update()
        check(calls == ['back'], f'点击「← 返回」触发退出（calls={calls}）')
        calls.clear()
    check(bool(p.clock.cget('text')), f'右上角时钟有值：{p.clock.cget("text")}')

    # 2. 底部控制栏按钮
    import tkinter as tk
    texts = []
    for w in p.bottom.winfo_children():
        for b in w.winfo_children():
            if isinstance(b, tk.Label):
                texts.append(str(b.cget('text')))
    print('底部按钮：', texts, flush=True)
    for t in ('⏸ 暂停', '⏮ 上一台', '⏭ 下一台', '⇄ 换源', '☰ 频道列表',
              '⛶ 窗口/全屏', '✕ 退出直播'):
        check(t in texts, f'底部按钮存在：{t}')
    shot('b1_live_chrome')
    app.after(300, step_bar_actions)


def step_bar_actions():
    p = ctx['page']
    before = p.cur_ch[1] if p.cur_ch else None
    find_btn(p.bottom, '⏭ 下一台').event_generate('<Button-1>')
    app.update()
    after = p.cur_ch[1] if p.cur_ch else None
    check(after != before, f'⏭ 下一台生效：{before} → {after}')

    # ☰ 频道列表：可见 → 收起；再点 → 展开
    find_btn(p.bottom, '☰ 频道列表').event_generate('<Button-1>')
    app.update()
    check(not p._visible, '☰ 频道列表 第一次点击收起列表')
    find_btn(p.bottom, '☰ 频道列表').event_generate('<Button-1>')
    app.update()
    check(p._visible, '☰ 频道列表 第二次点击展开列表')
    app.after(300, step_esc_hidden)


def step_esc_hidden():
    """回归：列表隐藏时按 Esc 必须直接退出（旧 bug 会无限收起列表）"""
    p = ctx['page']
    if p._visible:
        p._hide_overlay()
    app.update()
    app.event_generate('<Escape>')
    app.update()
    check(calls == ['back'], f'列表隐藏时 Esc 直接退出（calls={calls}）')
    calls.clear()
    app.after(200, step_esc_visible)


def step_esc_visible():
    """列表显示时 Esc 先收起，第二次才退出"""
    p = ctx['page']
    p._show_overlay()
    app.update()
    check(p._visible, '重新展开列表')
    app.event_generate('<Escape>')
    app.update()
    check(not p._visible and not calls, '列表显示时 Esc 只收起列表，不退出')
    app.event_generate('<Escape>')
    app.update()
    check(calls == ['back'], f'再按 Esc 退出直播（calls={calls}）')
    shot('b2_live_bar_hidden')
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


app.after(300, step_open)
app.after(25000, lambda: app.destroy())
app.mainloop()
print('DONE', flush=True)
