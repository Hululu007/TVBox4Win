# -*- coding: utf-8 -*-
"""验证播放页「← 返回」：主页 → 历史 → 详情 → 播放 → 点返回 → 应回到详情页
用像素扫描定位按钮（橙色 ACCENT 播放按钮 / 播放页左上白色返回按钮）"""
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


def click_frac(h, fx, fy, wait=0):
    r = win32gui.GetWindowRect(h)
    pyautogui.click(r[0] + int((r[2] - r[0]) * fx),
                    r[1] + int((r[3] - r[1]) * fy))
    if wait:
        time.sleep(wait)


def grab_region(h):
    r = win32gui.GetWindowRect(h)
    img = ImageGrab.grab()
    W, H = img.size
    box = (max(r[0], 0), max(r[1], 0), min(r[2], W), min(r[3], H))
    return img.crop(box), box


def find_accent(h):
    """找详情页橙色「▶ 播放」按钮：取最下方的密集橙色横条带
    （海报红色照片会被上面的带占据，按钮横条在最下）"""
    img, box = grab_region(h)
    w, hh = img.size
    px = img.load()
    rows = []
    for y in range(0, hh, 2):
        xs = [x for x in range(0, w, 2)
              if (lambda p: p[0] > 200 and 60 < p[1] < 170 and p[2] < 130)(px[x, y][:3])]
        rows.append((y, xs))
    # 找连续的密集带（每行 >= 30 个橙色像素，即约 60px 宽的横条）
    bands = []
    cur = []
    for y, xs in rows:
        if len(xs) >= 15:
            cur.append((y, xs))
        else:
            if len(cur) >= 5:
                bands.append(cur)
            cur = []
    if len(cur) >= 5:
        bands.append(cur)
    if not bands:
        return None
    band = bands[-1]  # 最下方带 = 播放按钮
    ys = [y for y, _ in band]
    xs = [x for _, row in band for x in row]
    return box[0] + sum(xs) // len(xs), box[1] + sum(ys) // len(ys)


def find_back_btn(h):
    """播放页左上角白色「← 返回」文字簇中心（黑底上找白色）。
    窗口 rect 含系统标题栏 ~30px，从 y=38 起扫描避开"""
    img, box = grab_region(h)
    w, hh = img.size
    px = img.load()
    xs = ys = n = 0
    for y in range(38, min(hh, 72)):
        for x in range(0, min(w, 140)):
            r, g, b = px[x, y][:3]
            if r > 190 and g > 190 and b > 190:
                xs += x
                ys += y
                n += 1
    if n < 20:
        return None
    return box[0] + xs // n, box[1] + ys // n


def top_strip_is_black(h):
    """播放页顶栏全行纯黑；其它页顶栏是深蓝 BG(18,23,43)。
    按比例采样（窗口 rect 含系统标题栏 ~30px，取 y 5.8% 附近避开）"""
    img, box = grab_region(h)
    px = img.load()
    w, hh = img.size
    pts = [(0.75, 0.058), (0.5, 0.05), (0.1, 0.058), (0.35, 0.065), (0.6, 0.07)]
    black = sum(1 for fx, fy in pts
                if sum(px[int(w * fx), int(hh * fy)][:3]) < 45)
    return black >= 3


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
time.sleep(12)

pyautogui.click(151, 219); time.sleep(4)          # 主页 → 历史
shot('b_hist')
click_frac(h, 0.2, 0.16, wait=15)                 # 历史第一条 → 详情
shot('b_detail')

# 像素定位橙色「▶ 续播/播放」按钮并点击
btn = find_accent(h)
print('accent btn at', btn, flush=True)
if not btn:
    subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
    sys.exit('no play button found')
pyautogui.click(*btn)
for _ in range(10):
    time.sleep(3)
    if top_strip_is_black(h):
        break
print('in player:', top_strip_is_black(h), flush=True)
time.sleep(8)
shot('b_play')
if not top_strip_is_black(h):
    print('FAILED to enter player', flush=True)
    subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
    sys.exit(1)

# 像素定位左上「← 返回」并点击
back = find_back_btn(h)
print('back btn at', back, flush=True)
if not back:
    subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
    sys.exit('no back button found')
pyautogui.click(*back)
time.sleep(3)
left = not top_strip_is_black(h)
print('left player:', left, flush=True)
time.sleep(8)
shot('b_back')
print('final page is detail-like:', left, flush=True)
subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
