# -*- coding: utf-8 -*-
"""综合验证：设置页新卡片（解码/缩放/历史上限）→ 画面缩放选 16:9 → 播放生效"""
import json
import subprocess
import time

import win32gui, win32con, win32process, win32api
import pyautogui
from PIL import ImageGrab

pyautogui.FAILSAFE = False
D = r'D:\code\tvbox2exe\tvboxpy\dist'
PANEL = (0x1C, 0x24, 0x40)
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


def hawk_val(key):
    try:
        with open(D + r'\hawk.json', encoding='utf-8') as f:
            return json.load(f).get(key)
    except Exception as e:
        return 'ERR:' + str(e)


def panel_runs(px, y, x0, x1, min_w=40):
    runs, s = [], None
    for x in range(x0, x1):
        m = abs(px[x, y][0] - PANEL[0]) < 8 and \
            abs(px[x, y][1] - PANEL[1]) < 8 and abs(px[x, y][2] - PANEL[2]) < 8
        if m and s is None:
            s = x
        if not m and s is not None:
            if x - s > min_w:
                runs.append((s, x))
            s = None
    if s is not None and x1 - s > min_w:
        runs.append((s, x1))
    return runs


def card_bands(h):
    r = win32gui.GetWindowRect(h)
    img = ImageGrab.grab().convert('RGB')
    px = img.load()
    bands, cur = [], None
    for y in range(r[1] + 60, r[3] - 40):
        n = sum(1 for x in range(r[0], r[2], 2)
                if abs(px[x, y][0] - PANEL[0]) < 8 and
                abs(px[x, y][1] - PANEL[1]) < 8 and abs(px[x, y][2] - PANEL[2]) < 8)
        wide = n > 120
        if wide and cur is None:
            cur = [y, y]
        elif wide:
            cur[1] = y
        elif cur and y - cur[1] > 8:
            if cur[1] - cur[0] > 20:
                bands.append(tuple(cur))
            cur = None
    if cur and cur[1] - cur[0] > 20:
        bands.append(tuple(cur))
    return bands, px, r


def two_card_rows(h):
    """返回 [(中心x, 中心y, 左run, 右run)] 全部两卡行，按行序"""
    bands, px, r = card_bands(h)
    print('bands:', bands, flush=True)
    out = []
    for y0, y1 in bands:
        runs = panel_runs(px, y0 + 8, r[0], r[2])
        if len(runs) == 2:
            out.append(((runs[0][0] + runs[0][1]) // 2, (y0 + y1) // 2,
                        runs[0], runs[1]))
    return out


def open_settings(h):
    r = win32gui.GetWindowRect(h)
    img = ImageGrab.grab().convert('RGB')
    px = img.load()
    rows = []
    for y in range(r[1] + 40, r[1] + 300):
        n = sum(1 for x in range(r[0], r[0] + 1300, 2)
                if abs(px[x, y][0] - PANEL[0]) < 8 and
                abs(px[x, y][1] - PANEL[1]) < 8 and abs(px[x, y][2] - PANEL[2]) < 8)
        if n > 25:
            rows.append(y)
    ymid = rows[len(rows) // 2]
    runs = panel_runs(px, ymid, r[0], r[0] + 1300)
    s, e = runs[-1]
    click(h, (s + e) // 2, ymid, wait=2)


def find_accent_btn(h, min_px=50):
    r = win32gui.GetWindowRect(h)
    img = ImageGrab.grab().convert('RGB')
    px = img.load()
    pts = []
    for y in range(r[1], r[3], 3):
        for x in range(r[0], r[2], 3):
            p = px[x, y]
            if abs(p[0]-ACCENT[0]) < 20 and abs(p[1]-ACCENT[1]) < 20 and abs(p[2]-ACCENT[2]) < 20:
                pts.append((x, y))
    if len(pts) < min_px // 3:
        return None
    return (sum(p[0] for p in pts) // len(pts),
            sum(p[1] for p in pts) // len(pts))


# ------------------------------------------------ main ----
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
r = win32gui.GetWindowRect(h)

# 1) 设置页：新卡片
open_settings(h)
shot('v2_setting')
rows = two_card_rows(h)
print('two-card rows:', len(rows), flush=True)
assert len(rows) >= 3, 'expect >=3 two-card rows'

# 2) 第 2 个两卡行右卡 = 画面缩放 → 选 16:9（down 一次）
_, _, _, right = rows[1]
click(h, (right[0] + right[1]) // 2, rows[1][1], wait=1.5)
shot('v2_scale_dlg')
pyautogui.press('down')
time.sleep(0.4)
pyautogui.press('enter')
time.sleep(1.2)
shot('v2_scale_picked')
print('play_scale =', hawk_val('play_scale'), flush=True)

# 3) 解码方式卡片：第 2 行左卡（只看弹窗，不改）
click(h, rows[1][0], rows[1][1], wait=1.5)
shot('v2_codec_dlg')
pyautogui.press('escape')
time.sleep(0.8)

# 4) 历史上限：第 3 行左卡 → 选 50 条（down 一次）
r3 = rows[2]
click(h, r3[0], r3[1], wait=1.5)
shot('v2_his_dlg')
pyautogui.press('down')
time.sleep(0.4)
pyautogui.press('enter')
time.sleep(1.2)
print('history_num =', hawk_val('history_num'), flush=True)

# 5) 返回主页 → 海报 → 详情 → 播放
click(h, r[0] + 42, r[1] + 26, wait=10)
click(h, r[0] + int(1300*0.074), r[1] + int(760*0.466), wait=8)
shot('v2_detail')
btn = find_accent_btn(h)
print('accent btn:', btn, flush=True)
if btn:
    click(h, *btn, wait=3)
    for i in range(4):
        time.sleep(5)
        shot('v2_play%d' % (i+1))
print('done', flush=True)
subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
