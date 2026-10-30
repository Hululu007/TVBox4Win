# -*- coding: utf-8 -*-
"""EXE 最终验证：豆瓣推荐海报 → 分类网格海报 → 点影片跳搜索出结果"""
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


subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
time.sleep(2)
subprocess.Popen([D + r'\tvboxpy.exe'], cwd=D)
h = None
for _ in range(45):
    time.sleep(1)
    h = find_win()
    if h:
        break
assert h, 'no window'
win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 60, 60, 1300, 760, 0)
time.sleep(15)
shot('f_home')            # 合并主页：豆瓣推荐海报行
print('home shot', flush=True)

# 点「热播电影」分类 tab（tab 行 y≈206；步进找）
r = win32gui.GetWindowRect(h)
clicked = False
for x in (206, 176, 236, 150, 266):
    pyautogui.click(x, 167)
    time.sleep(6)
    img = ImageGrab.grab()
    # 判断是否进入网格：tab 行下方 y~300 出现多个深色海报块（非纯 BG）
    px = img.load()
    n = 0
    for xx in range(r[0] + 60, r[0] + 1200, 60):
        p = px[xx, 380]
        if sum(p[:3]) < 200:   # 海报块（暗色）或占位块
            n += 1
    print('x=%d 暗块=%d' % (x, n), flush=True)
    if n >= 10:
        clicked = True
        break
print('tab clicked:', clicked, flush=True)
time.sleep(10)
shot('f_grid')            # 分类网格海报
print('grid shot', flush=True)

# 点第一张海报（网格第一行中心）
pyautogui.click(176, 380)
time.sleep(6)
shot('f_search1')
time.sleep(10)
shot('f_search2')
print('search shots done', flush=True)
subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
