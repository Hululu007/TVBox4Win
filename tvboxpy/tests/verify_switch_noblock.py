# -*- coding: utf-8 -*-
"""验证「切换源 / 筛选」不再卡死 UI，以及慢源不会拖住其它源

覆盖：
1. _show_filter 立即返回（取 filters 在后台），慢网络不再冻结主线程
2. 后台取到 filters 后仍能正常弹出筛选面板
3. spider.get_spider 构造慢站点时不占全局锁：别的站点取实例不受影响
4. jar 准备失败会短时记忆，第二次立刻失败而不是再等一个超时
"""
import os
import sys
import threading
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import tkinter as tk

from tvboxosc import apiconfig, data_api, hawk, spider, ui_thread
from tvboxosc.app import App
from tvboxosc.ui_grid import Page as GridPage

CFG = hawk.get(hawk.HOME_API) or "https://cyao2q.github.io/files/m.json"
okn = [0]


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg, flush=True)
    if cond:
        okn[0] += 1


app = App()
ctx = {'ticks': 0}


def tick():
    ctx['ticks'] += 1
    app.after(100, tick)


def on_ok():
    page = app.switch(GridPage)
    ctx['page'] = page
    app.after(1500, step_filter_slow)


def step_filter_slow():
    """1+2: get_filters 人为延迟 4 秒"""
    page = ctx['page']
    # 首屏渲染后「⚙ 筛选」按钮与状态标签必须还活着（曾被 _render_tabs 一并销毁）
    check(page.filter_btn.winfo_exists(), "首屏渲染后「⚙ 筛选」按钮仍在")
    check(page.status_filter.winfo_exists(), "首屏渲染后状态标签仍在")
    real = data_api.get_filters
    FAKE = {"0": [{"key": "year", "name": "年代", "value": ["2024", "2023"]}]}

    def slow(bean):
        time.sleep(4)
        return FAKE

    data_api.get_filters = slow
    page.cur_class = "0"
    t0 = time.time()
    page._show_filter()
    cost = time.time() - t0
    check(cost < 0.3, f"_show_filter 立即返回（{cost*1000:.0f}ms，原实现会阻塞 4s）")
    t1 = ctx['ticks']
    app.after(1200, lambda: step_mid(t1))


def step_mid(t1):
    page = ctx['page']
    check(ctx['ticks'] - t1 >= 8, f"延迟期间主线程仍在跑（心跳 {ctx['ticks']-t1} 次）")
    panels = [w for w in page.winfo_children() if isinstance(w, tk.Toplevel)]
    check(len(panels) == 0, "延迟期间还没弹面板（说明确实在后台取）")
    app.after(3500, step_panel)


def step_panel():
    page = ctx['page']
    panels = [w for w in page.winfo_children() if isinstance(w, tk.Toplevel)]
    check(len(panels) == 1, f"后台取到数据后弹出筛选面板（{len(panels)} 个）")
    if panels:
        # 点一下筛选条件 chip：重构前这里是 configure(on_select=...) → 直接抛 TclError
        chips = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Label) and getattr(c, 'on_select', None):
                    chips.append(c)
                walk(c)
        walk(panels[0])
        ok_chip = None
        for c in chips:
            if str(c.cget('text')) not in ("应用筛选",):
                ok_chip = c
                break
        check(ok_chip is not None, f"面板内有可点的筛选条件（{len(chips)} 个可点控件）")
        if ok_chip:
            try:
                ok_chip.on_select()
                check(True, f"点击筛选条件「{ok_chip.cget('text')}」无异常")
            except Exception as ex:
                check(False, f"点击筛选条件异常：{ex}")
    for p in panels:
        p.destroy()
    app.after(300, step_lock)


def step_lock():
    """3: 慢站点构造不占全局锁"""
    sleep_s = 5
    orig_init = spider.Spider.__init__

    def slow_init(self, key, api, ext=None):
        if "slowsite" in str(api):
            time.sleep(sleep_s)          # 模拟下载站点 js + 起 node
        orig_init(self, key, api, ext)

    spider.Spider.__init__ = slow_init
    a = types.SimpleNamespace(key="slowA", api="http://x/slowsite.js", ext=None)
    b = types.SimpleNamespace(key="fastB", api="http://x/fast.js", ext=None)

    t_a = []

    def run_a():
        t0 = time.time()
        try:
            spider.get_spider(a)
        except Exception:
            pass
        t_a.append(time.time() - t0)

    th = threading.Thread(target=run_a, daemon=True)
    th.start()
    time.sleep(0.6)              # 确保 A 已经开始慢构造
    t0 = time.time()
    try:
        spider.get_spider(b)
    except Exception:
        pass
    cost_b = time.time() - t0
    check(cost_b < 2.0, f"慢站点 A 构造中，B 取实例仅 {cost_b:.2f}s（未被全局锁拖住）")
    th.join(timeout=sleep_s + 15)
    spider.Spider.__init__ = orig_init
    app.after(300, step_jar_memo)


def step_jar_memo():
    """4: jar 准备失败短时记忆"""
    from tvboxosc import jar_spider
    calls = []

    def boom(url):
        calls.append(time.time())
        time.sleep(0.8)
        raise RuntimeError("模拟网络不可达")

    orig = jar_spider._download_jar
    jar_spider._download_jar = boom
    url = "http://example.invalid/none.jar"
    jar_spider._fail_until.pop(url, None)

    t0 = time.time()
    try:
        jar_spider._prepare(url)
    except Exception:
        pass
    first = time.time() - t0
    t0 = time.time()
    try:
        jar_spider._prepare(url)
    except Exception as e:
        msg2 = str(e)
    second = time.time() - t0
    check(first > 0.5 and second < 0.05,
          f"失败后立即失败：首次 {first:.2f}s → 再次 {second:.3f}s（{msg2[:28]}）")
    jar_spider._download_jar = orig
    jar_spider._fail_until.pop(url, None)
    finish()


def finish():
    print(f"== 通过 {okn[0]}/4 ==", flush=True)
    app.destroy()


app.after(200, tick)
apiconfig.api_config.load(CFG, lambda: ui_thread.run(on_ok), lambda m: print("配置失败", m))
app.after(60000, finish)
app.mainloop()
print("DONE", flush=True)
