# -*- coding: utf-8 -*-
"""EXE 冒烟：启动 dist/TVBox4Win.exe，核对窗口标题里的版本号，截一张首页图

用法：python tests/smoke_exe.py [期望版本，如 0.9.5] [截图名]
"""
import os
import subprocess
import sys
import time

import win32con
import win32gui

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "dist")
EXE = os.path.join(D, "TVBox4Win.exe")
WANT = sys.argv[1] if len(sys.argv) > 1 else None
SHOT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(D, "smoke.png")


def find_win():
    res = []

    def cb(hh, _):
        if not win32gui.IsWindowVisible(hh):
            return
        t = win32gui.GetWindowText(hh) or ""
        if t.startswith("TVBox4Win v"):     # 只认主窗口标题，别把浏览器标签页算进来
            res.append((hh, t))
    win32gui.EnumWindows(cb, None)
    return res[0] if res else None


subprocess.run(["taskkill", "/F", "/IM", "TVBox4Win.exe"], capture_output=True)
time.sleep(2)
# 沙箱内 Popen 的窗口不显示，改用 PowerShell Start-Process 拉起真实进程
subprocess.run(["powershell", "-NoProfile", "-Command",
                f'Start-Process -FilePath "{EXE}" -WorkingDirectory "{D}"'],
               capture_output=True)

found = None
for i in range(50):
    time.sleep(1)
    found = find_win()
    if found:
        break

if not found:
    print("FAIL: 45s 内没有出现窗口（可能启动崩溃，查 error.log）")
    sys.exit(1)

h, title = found
print("WINDOW", repr(title), flush=True)
if WANT and WANT not in title:
    print(f"FAIL: 标题里没有期望版本 {WANT}")
    sys.exit(1)
print("OK: 版本号匹配", WANT, flush=True)

# 摆到前台，等首屏加载完再截图
win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 40, 40, 1280, 760, 0)
time.sleep(14)
import pyautogui
x1, y1, x2, y2 = win32gui.GetWindowRect(h)
pyautogui.screenshot(region=(x1, y1, x2 - x1, y2 - y1)).save(SHOT)
print("saved", SHOT, flush=True)
