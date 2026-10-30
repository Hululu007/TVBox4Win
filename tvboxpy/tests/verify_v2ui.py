# -*- coding: utf-8 -*-
"""EXE 验证：主页点「杯雪」海报 → 详情页(chips/播放地址/按钮) → 点快速搜索 → 新搜索页"""
import subprocess, time
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


def click_frac(h, fx, fy, wait=0):
    r = win32gui.GetWindowRect(h)
    x = r[0] + int((r[2] - r[0]) * fx)
    y = r[1] + int((r[3] - r[1]) * fy)
    pyautogui.click(x, y)
    print('click(%d,%d) frac=%.2f,%.2f' % (x, y, fx, fy), flush=True)
    if wait:
        time.sleep(wait)


def find_blue_btn(h):
    """详情页按钮行里找蓝色「快速搜索」(#4A90E2) 中心"""
    r = win32gui.GetWindowRect(h)
    img = ImageGrab.grab()
    px = img.load()
    xs = ys = n = 0
    lo_y = r[1] + int((r[3] - r[1]) * 0.3)   # 按钮行在页面上部 30%-55%
    hi_y = r[1] + int((r[3] - r[1]) * 0.55)
    for y in range(lo_y, hi_y, 3):
        for x in range(r[0] + 40, r[0] + (r[2] - r[0]) - 20, 3):
            pr, pg, pb = px[x, y][:3]
            if abs(pr - 74) < 35 and abs(pg - 144) < 35 and abs(pb - 226) < 35:
                xs += x
                ys += y
                n += 1
    if n < 8:
        return None
    return xs // n, ys // n


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
print('rect', win32gui.GetWindowRect(h), flush=True)
shot('d_home')                     # 主页（量子资源分类网格）

# 主页第二张海报「杯雪·一战成名」（第一行中部）
click_frac(h, 0.488, 0.46, wait=8)
shot('d_detail')                   # 详情页：chips/导演主演/播放地址/彩色按钮
print('detail shot', flush=True)

btn = find_blue_btn(h)
if btn:
    print('快速搜索按钮', btn, flush=True)
    pyautogui.click(*btn)
    time.sleep(22)                 # 18 个源并发搜
    shot('d_search')                # 新搜索页：状态/分词/源筛选/卡片
    print('search shot', flush=True)
else:
    print('未找到蓝色快速搜索按钮', flush=True)
    shot('d_noblue')
subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
print('done', flush=True)
