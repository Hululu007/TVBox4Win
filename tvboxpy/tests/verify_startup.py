# -*- coding: utf-8 -*-
"""验证：启动直达点播页（不经过用户主页）+ 直播页标题与点播首页平行"""
import subprocess, time, sys
import win32gui, win32con, win32process, win32api
import pyautogui
from PIL import ImageGrab

pyautogui.FAILSAFE = False
D = r'D:\code\tvbox2exe\tvboxpy\dist'


def find_win():
    res = []
    def cb(hh, _):
        if win32gui.IsWindowVisible(hh) and (win32gui.GetWindowText(hh) or '') == 'TVBox':
            _, wpid = win32process.GetWindowThreadProcessId(hh)
            try:
                ph = win32api.OpenProcess(0x0400 | 0x0010, False, wpid)
                exe = win32process.GetModuleFileNameEx(ph, 0).lower()
            except Exception:
                exe = ''
            if exe.endswith('tvboxpy.exe'):
                res.append(hh)
    win32gui.EnumWindows(cb, None)
    return res[0] if res else None


def shot(name):
    ImageGrab.grab().save(D + '\\' + name + '.png')


def click(x, y, wait=0):
    pyautogui.click(x, y)
    if wait:
        time.sleep(wait)


subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
time.sleep(2)
subprocess.Popen([D + r'\tvboxpy.exe'], cwd=D)
h = None
for i in range(45):
    time.sleep(1)
    h = find_win()
    if h:
        break
assert h, 'no window'
win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 60, 60, 1300, 760, 0)
time.sleep(12)
shot('v_startup')          # 应直接是点播网格页（豆豆推荐 鱼妖源）
click(114, 114, 3)         # 点播页左上 ← → 用户主页（功能入口）
shot('v_home')
click(316, 249, 8)         # 主页按钮排「直播」
shot('v_live')             # 直播页顶栏应与点播首页平行（← + ACCENT 源名）
print('done', flush=True)
