# -*- coding: utf-8 -*-
"""dev 调试：谁在反复唤出 _show_chrome（stdout 打印 show/hide 时间线）"""
import subprocess, sys, time, os
import win32gui, win32con, win32api
import pyautogui
from PIL import ImageGrab

pyautogui.FAILSAFE = False
ROOT = r'D:\code\tvbox2exe\tvboxpy'
PY = r'C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe'
ACCENT = (0xFF, 0x7A, 0x59)
env = dict(os.environ, TVBOXPY_DEBUG='1')
proc = subprocess.Popen([PY, 'main.py'], cwd=ROOT, env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

h = None
for _ in range(40):
    time.sleep(1)
    h = win32gui.FindWindow(None, 'TVBox')
    if h:
        break
assert h, 'no window'
win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 60, 60, 1300, 760, 0)
time.sleep(15)

r = win32gui.GetWindowRect(h)


def fx(fx_, fy_, wait=0):
    pyautogui.click(r[0] + int(1300 * fx_), r[1] + int(760 * fy_))
    if wait:
        time.sleep(wait)


def find_accent(min_px=15):
    rr = win32gui.GetWindowRect(h)
    img = ImageGrab.grab().convert('RGB')
    px = img.load()
    pts = [(x, y) for y in range(rr[1], rr[3], 3) for x in range(rr[0], rr[2], 3)
           if abs(px[x, y][0]-ACCENT[0]) < 20 and abs(px[x, y][1]-ACCENT[1]) < 20
           and abs(px[x, y][2]-ACCENT[2]) < 20]
    if len(pts) < min_px:
        return None
    return (sum(p[0] for p in pts)//len(pts), sum(p[1] for p in pts)//len(pts))


fx(0.074, 0.466, 9)          # 主页第一格 → 搜索页
if not find_accent(40):
    fx(0.225, 0.30, 9)       # 搜索结果第一张海报 → 详情
btn = find_accent(40)
print('accent btn:', btn, flush=True)
if btn:
    pyautogui.click(*btn)
    time.sleep(3)
    # 移动鼠标唤出
    pyautogui.moveTo(r[0]+400, r[1]+300)
    pyautogui.moveRel(30, 0)
    time.sleep(20)           # 观察隐藏时间线

proc.terminate()
out = proc.stdout.read().decode('utf-8', 'replace')
lines = [l for l in out.splitlines() if 'chrome' in l or 'Error' in l or 'File "' in l]
print('\n'.join(lines[-80:]), flush=True)
