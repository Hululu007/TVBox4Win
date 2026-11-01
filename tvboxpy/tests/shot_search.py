# -*- coding: utf-8 -*-
"""拍摄搜索结果网格（改版对照用）"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from tkinter import messagebox

messagebox.askyesno = lambda *a, **k: True

from tvboxosc import apiconfig, hawk
from tvboxosc.app import App

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "shot_search.png")
KW = sys.argv[2] if len(sys.argv) > 2 else "斗罗大陆"

if not hawk.get(hawk.HOME_API):
    hawk.put(hawk.HOME_API, "https://cyao2q.github.io/files/m.json")
try:
    if not apiconfig.api_config.source_bean_list:
        cfg = apiconfig.extract_json(
            apiconfig.fetch_text(hawk.get(hawk.HOME_API)))
        apiconfig.api_config._parse(cfg)
except Exception as ex:
    print("config load warn:", ex, flush=True)

app = App()
app.geometry("1280x720+40+40")
app.attributes("-topmost", True)
app.lift()


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        try:
            app.update()
        except Exception:
            return
        time.sleep(0.02)


from tvboxosc.ui_search import Page as SearchPage

page = app.switch(SearchPage)
pump(1.5)
page.kw.delete(0, "end")
page.kw.insert(0, KW)
page.do_search()
pump(22)
print("SEARCH", {"cols": page.COLS, "card": getattr(page, "_card_size", None),
                 "shown": len(page._rendered)}, flush=True)

import pyautogui
x, y = app.winfo_rootx(), app.winfo_rooty()
pyautogui.screenshot(region=(x, y, app.winfo_width(), app.winfo_height())).save(OUT)
print("saved", OUT, flush=True)
app.destroy()
