# -*- coding: utf-8 -*-
"""dev 验证新播放器控制栏：进入播放 → 唤出控制栏截图 → 暂停/进度/下一集"""
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
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
    print('click %.3f,%.3f' % (fx, fy), flush=True)
    if wait:
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


click(0.074, 0.466, 9)          # 主页第一格 → 搜索页
if not find_accent(40):
    click(0.225, 0.30, 9)       # 搜索结果第一张海报 → 详情
btn = find_accent(40)
print('play btn:', btn, flush=True)
t_click = time.time()
if btn:
    pyautogui.click(*btn)

# 起播计时：每 0.3 秒采样，等画面出现（检测底部时间文字区域变化不可靠，
# 改为固定采样截图后人工看，这里只打印放行延时）
time.sleep(8)
pyautogui.moveTo(960, 540)
pyautogui.moveRel(40, 0)        # 唤出控制栏
time.sleep(1)
shot('ui_chrome')
print('elapsed since click: %.1fs' % (time.time() - t_click), flush=True)
time.sleep(5.5)
shot('ui_hidden')

# 暂停/继续
pyautogui.moveRel(-40, 0)
time.sleep(0.6)
shot('ui_chrome2')
proc.terminate()
try:
    out = proc.stdout.read().decode('utf-8', 'replace')
    for line in out.splitlines():
        if 'startup' in line or 'Error' in line:
            print(line, flush=True)
except Exception:
    pass
print('done', flush=True)
