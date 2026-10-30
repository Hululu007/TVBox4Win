# -*- coding: utf-8 -*-
"""全自动验证：启动 EXE → 鱼妖源 → 网格 → 海报(跳搜索) → 结果 → 详情 → 播放"""
import subprocess, sys, time
import win32gui, win32con, win32process, win32api
import pyautogui
from PIL import ImageGrab

pyautogui.FAILSAFE = False
D = r'D:\code\tvbox2exe\tvboxpy\dist'
TAG = sys.argv[1] if len(sys.argv) > 1 else "v"


def find_win(_pid):
    res = []
    def cb(hh, _):
        if win32gui.IsWindowVisible(hh) and (win32gui.GetWindowText(hh) or '') == 'TVBox':
            _, wpid = win32process.GetWindowThreadProcessId(hh)
            try:
                ph = win32api.OpenProcess(0x0400 | 0x0010, False, wpid)  # QUERY|VM_READ
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
    if wait:
        time.sleep(wait)
    return x, y


p = subprocess.Popen([D + r'\tvboxpy.exe'], cwd=D)
# 先清理所有旧实例（onefile 多进程，避免窗口混淆）
subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'],
               capture_output=True)
time.sleep(2)
p = subprocess.Popen([D + r'\tvboxpy.exe'], cwd=D)
h = None
for i in range(45):
    time.sleep(1)
    h = find_win(p.pid)
    if h:
        break
assert h, 'no window'
win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 60, 60, 1300, 760, 0)
time.sleep(6)

click_frac(h, 0.5, 0.62, wait=30)          # 主页 → 点播
click_frac(h, 0.13, 0.32, wait=45)         # 第一张海报 → 跨源搜索
click_frac(h, 0.14, 0.24, wait=20)         # 第一个搜索结果 → 详情
shot(TAG + '_detail')
click_frac(h, 0.115, 0.66)                 # ▶ 播放
print('play clicked, watching...', flush=True)
for i in range(14):
    time.sleep(5)
    shot('%s_play%02d' % (TAG, i))
    print('shot', i, flush=True)
