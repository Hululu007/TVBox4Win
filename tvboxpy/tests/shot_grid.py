# -*- coding: utf-8 -*-
"""拍摄当前点播页布局（改版前后对照用）

用法：python tests/shot_grid.py [输出png] [分类序号]
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import tkinter as tk

from tvboxosc import apiconfig, hawk
from tvboxosc.app import App

if not hawk.get(hawk.HOME_API):
    hawk.put(hawk.HOME_API, "https://cyao2q.github.io/files/m.json")
try:
    if not apiconfig.api_config.source_bean_list:
        cfg_url = hawk.get(hawk.HOME_API)
        cfg = apiconfig.extract_json(apiconfig.fetch_text(cfg_url))
        apiconfig.api_config._parse(cfg)
except Exception as ex:
    print("config load warn:", ex, flush=True)

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "shot_grid.png")
CLASS_IDX = int(sys.argv[2]) if len(sys.argv) > 2 else 0

from tkinter import messagebox

messagebox.askyesno = lambda *a, **k: True

app = App()
app.geometry("1280x720+40+40")
app.attributes("-topmost", True)
app.lift()
app.focus_force()


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.02)


from tvboxosc.ui_grid import Page as GridPage

page = app.switch(GridPage)
pump(4)
# 若当前首页源是慢爬虫源，换一个快的 CMS 源验证分类网格
if CLASS_IDX >= 0 and apiconfig.api_config.source_bean_list:
    fast = [b for b in apiconfig.api_config.source_bean_list
            if b.type in (0, 1) and "csp_" not in str(b.api)
            and not str(b.api).endswith((".js", ".py")) and b.searchable == 1]
    if fast and page.bean not in fast:
        pick = fast[-1] if len(sys.argv) > 4 else fast[0]
        page = app.switch(GridPage, source_key=pick.key)
        print("switch to fast source:", pick.name, flush=True)
pump(4)
if page.classes:
    page.select_class(page.classes[CLASS_IDX][0])
    pump(10)

info = {
    "win": (app.winfo_width(), app.winfo_height()),
    "canvas": (page.canvas.winfo_width(), page.canvas.winfo_height()),
    "inner": (page.inner.winfo_reqwidth(), page.inner.winfo_reqheight()),
    "children": len(page.inner.winfo_children()),
    "cols": getattr(page, "COLS", None),
    "layout_used": getattr(page, "_layout_used", None),
}
print("LAYOUT", info, flush=True)

import pyautogui
x, y = app.winfo_rootx(), app.winfo_rooty()
w, h = app.winfo_width(), app.winfo_height()
pyautogui.screenshot(region=(x, y, w, h)).save(OUT)
print("saved", OUT, flush=True)

if len(sys.argv) > 3 and sys.argv[3] == "resize":
    app.geometry("1720x960+20+20")
    pump(1.6)
    print("LAYOUT2", {
        "canvas": page.canvas.winfo_width(),
        "layout_used": getattr(page, "_layout_used", None),
    }, flush=True)
    x, y = app.winfo_rootx(), app.winfo_rooty()
    pyautogui.screenshot(region=(x, y, app.winfo_width(), app.winfo_height())
                         ).save(OUT.replace(".png", "_big.png"))
    print("saved big", flush=True)
app.destroy()
