# -*- coding: utf-8 -*-
"""复现「点播放没反应」：主页站点推荐第一张海报 → 详情 → ▶播放(ACCENT定位) → 连续截图"""
import subprocess, time, os
import win32gui, win32con, win32process, win32api
import pyautogui
from PIL import ImageGrab

pyautogui.FAILSAFE = False
D = r'D:\code\tvbox2exe\tvboxpy\dist'
ACCENT = (0xFF, 0x7A, 0x59)


def find_win():
    res = []
    def cb(hh, _):
        if win32gui.IsWindowVisible(hh) and (win32gui.GetWindowText(hh) or '').startswith('TVBox'):
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
    print('shot', name, flush=True)


def click(h, x, y, wait=0):
    pyautogui.click(x, y)
    print('click(%d,%d)' % (x, y), flush=True)
    if wait:
        time.sleep(wait)


def find_accent_btn(h, min_px=50):
    """窗口里找 ACCENT 色块聚类的中心（▶ 播放按钮）"""
    r = win32gui.GetWindowRect(h)
    img = ImageGrab.grab().convert('RGB')
    px = img.load()
    pts = []
    for y in range(r[1], r[3], 3):
        for x in range(r[0], r[2], 3):
            p = px[x, y]
            if abs(p[0]-ACCENT[0]) < 20 and abs(p[1]-ACCENT[1]) < 20 and abs(p[2]-ACCENT[2]) < 20:
                pts.append((x, y))
    print('accent pts:', len(pts), flush=True)
    if len(pts) < min_px // 3:
        return None
    xs = sum(p[0] for p in pts) // len(pts)
    ys = sum(p[1] for p in pts) // len(pts)
    return xs, ys


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
time.sleep(16)
r = win32gui.GetWindowRect(h)
print('rect', r, flush=True)
shot('p_home')

# 站点推荐第一张海报（左上第一格）
click(h, r[0] + int(1300*0.074), r[1] + int(760*0.466), wait=8)
shot('p_detail')

btn = find_accent_btn(h)
print('accent btn:', btn, flush=True)
if btn:
    click(h, *btn, wait=3)
    shot('p_play0')
    for i in range(6):
        time.sleep(5)
        shot('p_play%d' % (i+1))
else:
    print('未找到播放按钮', flush=True)
    shot('p_nobtn')

err = os.path.join(D, 'error.log')
if os.path.exists(err):
    print('---- error.log tail ----', flush=True)
    with open(err, encoding='utf-8', errors='replace') as f:
        print('\n'.join(f.read().splitlines()[-40:]), flush=True)
subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
print('done', flush=True)
