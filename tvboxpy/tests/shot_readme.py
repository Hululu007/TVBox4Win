# -*- coding: utf-8 -*-
"""README 主界面截图：启动 EXE，等 banner 加载完再拍"""
import os
import subprocess
import time

import pyautogui
import win32con
import win32gui

D = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dist"))
EXE = os.path.join(D, "TVBox4Win.exe")
SHOT = os.path.join(D, "readme_home_raw2.png")


def find_win():
    res = []

    def cb(hh, _):
        if not win32gui.IsWindowVisible(hh):
            return
        t = win32gui.GetWindowText(hh) or ""
        if t.startswith("TVBox4Win v"):
            res.append((hh, t))
    win32gui.EnumWindows(cb, None)
    return res[0] if res else None


subprocess.run(["taskkill", "/F", "/IM", "TVBox4Win.exe"], capture_output=True)
time.sleep(2)
os.startfile(EXE)  # 直接拉起，不经 shell 包装
found = None
for _ in range(50):
    time.sleep(1)
    found = find_win()
    if found:
        break
if not found:
    print("FAIL: 没有出现窗口")
    raise SystemExit(1)
h, title = found
print("WINDOW", repr(title))
win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 40, 40, 1280, 800, 0)
print("waiting 45s for banner...")
x1, y1, x2, y2 = win32gui.GetWindowRect(h)
time.sleep(45)
# 若页面有滚动，滚回顶部再拍
cx = (x1 + x2) // 2
cy = (y1 + y2) // 2
pyautogui.moveTo(cx, cy)
for _ in range(15):
    pyautogui.scroll(1200)
    time.sleep(0.15)
pyautogui.keyDown("home") if False else None
time.sleep(2)
x1, y1, x2, y2 = win32gui.GetWindowRect(h)
pyautogui.screenshot(region=(x1, y1, x2 - x1, y2 - y1)).save(SHOT)
print("saved", SHOT)
subprocess.run(["taskkill", "/F", "/IM", "TVBox4Win.exe"], capture_output=True)
