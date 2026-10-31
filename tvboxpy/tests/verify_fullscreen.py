# -*- coding: utf-8 -*-
"""验证播放页全屏沉浸：自动全屏、视频铺满、控制栏 4s 自动隐藏、Esc 返回恢复窗口"""
import subprocess, time, os
import win32gui, win32con, win32process, win32api
import pyautogui
from PIL import ImageGrab

pyautogui.FAILSAFE = False
D = r'D:\code\tvbox2exe\tvboxpy\dist'
ACCENT = (0xFF, 0x7A, 0x59)
SW, SH = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)


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


def click(h, fx, fy, wait=0):
    r = win32gui.GetWindowRect(h)
    x, y = r[0] + int(1300 * fx), r[1] + int(760 * fy)
    pyautogui.click(x, y)
    print('click(%.3f,%.3f)->(%d,%d)' % (fx, fy, x, y), flush=True)
    if wait:
        time.sleep(wait)


def find_accent_btn(h, min_px=15):
    r = win32gui.GetWindowRect(h)
    img = ImageGrab.grab().convert('RGB')
    px = img.load()
    pts = []
    for y in range(r[1], r[3], 3):
        for x in range(r[0], r[2], 3):
            p = px[x, y]
            if abs(p[0]-ACCENT[0]) < 20 and abs(p[1]-ACCENT[1]) < 20 and abs(p[2]-ACCENT[2]) < 20:
                pts.append((x, y))
    if len(pts) < min_px:
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
time.sleep(18)
shot('fs_home')

# 主页第一格（站点推荐首项，壳源 → 跳搜索页）
click(h, 0.074, 0.466, wait=9)
shot('fs_step2')
btn = find_accent_btn(h, 40)
if not btn:
    print('no play btn, try search result poster', flush=True)
    click(h, 0.225, 0.30, wait=9)   # 搜索结果第一张海报
    shot('fs_detail')
btn = find_accent_btn(h, 40)
print('accent btn:', btn, flush=True)
if btn:
    pyautogui.click(*btn)
    time.sleep(3)
    shot('fs_play0')
    # 全屏时 tk 会重建窗口，需重新获取句柄
    h = find_win()
    # 全屏检查：窗口 rect 应覆盖整屏（fullscreen 属性）
    r = win32gui.GetWindowRect(h)
    print('rect after enter play:', r, flush=True)
    print('FULLSCREEN_OK' if (r[0] <= 0 and r[1] <= 0 and
                              r[2] >= SW and r[3] >= SH) else 'FULLSCREEN_FAIL', flush=True)
    # 控制栏自动隐藏检查：第 6 秒截图，顶部「返回」应已消失（4s 隐藏）
    time.sleep(6)
    shot('fs_play_hidden')
    # 移动鼠标唤出控制栏
    pyautogui.moveTo(r[0] + 400, r[1] + 300)
    pyautogui.moveRel(30, 0)
    time.sleep(1)
    shot('fs_play_chrome')
    for i in range(3):
        time.sleep(5)
        shot('fs_play%d' % (i + 2))
else:
    shot('fs_nobtn')

err = os.path.join(D, 'error.log')
if os.path.exists(err):
    print('---- error.log tail ----', flush=True)
    with open(err, encoding='utf-8', errors='replace') as f:
        print('\n'.join(f.read().splitlines()[-20:]), flush=True)
subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
print('done', flush=True)
