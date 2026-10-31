# -*- coding: utf-8 -*-
"""dev 验证播放控制交互：暂停/继续、进度条跳转、上一集/下一集"""
import subprocess, time, os
import win32gui, win32con
import pyautogui
from PIL import ImageGrab

pyautogui.FAILSAFE = False
ROOT = r'D:\code\tvbox2exe\tvboxpy'
PY = r'C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe'
ACCENT = (0xFF, 0x7A, 0x59)
OUT = os.path.join(ROOT, 'dist')

proc = subprocess.Popen([PY, 'main.py'], cwd=ROOT,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
h = None
for _ in range(40):
    time.sleep(1)
    h = win32gui.FindWindow(None, 'TVBox')
    if h:
        break
assert h, 'no window'
win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 60, 60, 1300, 760, 0)
time.sleep(16)

r = win32gui.GetWindowRect(h)


def click(fx, fy, wait=0):
    pyautogui.click(r[0] + int(1300 * fx), r[1] + int(760 * fy))
    if wait:
        time.sleep(wait)


def click_abs(x, y, wait=0.6):
    pyautogui.click(x, y)
    time.sleep(wait)


def shot(name):
    ImageGrab.grab().save(os.path.join(OUT, name + '.png'))
    print('shot', name, flush=True)


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


click(0.074, 0.466, 9)
if not find_accent(40):
    click(0.225, 0.30, 9)
btn = find_accent(40)
if btn:
    pyautogui.click(*btn)
    time.sleep(15)          # 等起播

# 控制栏坐标（全屏 1920x1080）：底部按钮行 y=1010
BTN_Y = 1010
pause_x, prev_x, next_x, replay_x = 53, 176, 288, 384
SEEK_Y = 1049
SEEK_X0, SEEK_X1 = 90, 1790

pyautogui.moveTo(960, 540)
pyautogui.moveRel(40, 0)
time.sleep(0.8)

click_abs(pause_x, BTN_Y)       # 暂停
shot('ct_paused')
click_abs(pause_x, BTN_Y)       # 继续
click_abs(int(SEEK_X0 + (SEEK_X1 - SEEK_X0) * 0.6), SEEK_Y, wait=2)  # 跳 60%
shot('ct_seek')
click_abs(next_x, BTN_Y, wait=10)   # 下一集
pyautogui.moveTo(960, 540)
pyautogui.moveRel(40, 0)
time.sleep(0.8)
shot('ct_next')

proc.terminate()
print('done', flush=True)
