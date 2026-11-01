# -*- coding: utf-8 -*-
"""验证「配置历史」选择后的加载行为（修复前：先 destroy 再 box.get 抛 TclError，
on_pick 永远不会被调用 → 弹窗关闭但配置不生效）

三条路径分别验证：
1. 鼠标双击列表项
2. 选中后按回车
3. 点「确定」按钮
4. 加载失败要有提示
"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import tkinter as tk

import pyautogui

from tvboxosc import apiconfig, hawk
from tvboxosc.app import App
from tvboxosc.ui_setting import Page as SettingPage

H1 = "http://example.com/api1.json"
H2 = "http://example.com/api2.json"
H3 = "http://example.com/api3.json"

# 备份用户真实历史，测试结束还原
BACKUP = hawk.get(hawk.API_HISTORY, [])
hawk.put(hawk.API_HISTORY, [H1, H2, H3])

calls = []
errors = []


def fake_load(url, ok_cb, err_cb=None):
    calls.append(url)
    print("  >> load:", url, flush=True)
    if ok_cb:
        ok_cb()


apiconfig.api_config.load = fake_load

app = App()
ctx = {}
ok_count = [0]


def check(cond, msg):
    if cond:
        ok_count[0] += 1
        print("OK  ", msg, flush=True)
    else:
        print("FAIL", msg, flush=True)


def open_hist(page):
    page._pick_hist()
    app.update()
    win = [w for w in page.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    box = None

    def walk(w):
        nonlocal box
        for c in w.winfo_children():
            if isinstance(c, tk.Listbox):
                box = c
            walk(c)
    walk(win)
    return win, box


def item_center(box, idx):
    x, y, w, h = box.bbox(idx)
    return box.winfo_rootx() + x + w // 2, box.winfo_rooty() + y + h // 2


def find_btn(parent, text):
    for w in parent.winfo_children():
        if isinstance(w, tk.Label) and str(w.cget('text')).strip() == text:
            return w
        r = find_btn(w, text)
        if r:
            return r
    return None


# ---------------------------------------------------------------- 步骤
def step_setup():
    page = app.switch(SettingPage)
    ctx['page'] = page
    page.app.go_home = lambda: ctx.setdefault('home', 0)   # 拦截回主页
    app.update()
    app.attributes('-topmost', True)
    app.lift()
    app.after(700, lambda: step_a(page))


def step_a(page):
    """A. 双击第 2 项"""
    win, box = open_hist(page)
    ctx['win'] = win
    app.update()
    x, y = item_center(box, 1)
    print("A 双击坐标:", x, y, flush=True)
    pyautogui.doubleClick(x, y, interval=0.06)
    app.after(700, lambda: step_a_check(page))


def step_a_check(page):
    win = ctx['win']
    check(not win.winfo_exists(), "A 双击后弹窗关闭")
    check(calls == [H2], f"A 双击第 2 项触发加载（calls={calls}）")
    app.after(200, lambda: step_b(page))


def step_b(page):
    """B. 单击选中第 3 项 + 回车"""
    calls.clear()
    win, box = open_hist(page)
    ctx['win'] = win
    app.update()
    x, y = item_center(box, 2)
    pyautogui.click(x, y)
    app.update()
    box.event_generate('<Return>')
    app.after(600, lambda: step_b_check(page))


def step_b_check(page):
    win = ctx['win']
    check(not win.winfo_exists(), "B 回车后弹窗关闭")
    check(calls == [H3], f"B 回车确认第 3 项（calls={calls}）")
    app.after(200, lambda: step_c(page))


def step_c(page):
    """C. 点「确定」按钮（默认选中第 1 项）"""
    calls.clear()
    win, box = open_hist(page)
    ctx['win'] = win
    app.update()
    btn = find_btn(win, "确定")
    check(btn is not None, "C 弹窗内含「确定」按钮")
    btn.event_generate('<Button-1>')
    app.after(600, lambda: step_c_check(page))


def step_c_check(page):
    win = ctx['win']
    check(not win.winfo_exists(), "C 点确定后弹窗关闭")
    check(calls == [H1], f"C 点确定使用默认第 1 项（calls={calls}）")
    app.after(150, step_d)


def step_d():
    """D. 加载失败要有提示（err_cb 生效）"""
    page = ctx['page']
    apiconfig.api_config.load = lambda url, ok_cb, err_cb=None: err_cb("模拟失败")
    page._load_api("http://bad.example/x.json")
    app.after(500, step_d_check)


def step_d_check():
    page = ctx['page']
    txt = page.status.cget('text')
    check("配置加载失败" in txt, f"D 失败有明确提示（{txt}）")
    finish()


def finish():
    hawk.put(hawk.API_HISTORY, BACKUP)
    print(f"== 通过 {ok_count[0]} 项 ==", flush=True)
    app.destroy()


def on_err(exc, val, tb):
    errors.append(''.join(traceback.format_exception(exc, val, tb)))
    print("EXC:", errors[-1], flush=True)


app.report_callback_exception = on_err
app.after(400, step_setup)
app.after(25000, lambda: (print("TIMEOUT", flush=True), app.destroy()))
app.mainloop()
print("DONE 异常数:", len(errors), flush=True)
