# -*- coding: utf-8 -*-
"""EXE 验证：设置 → 首页推荐弹窗 → 依次切换 豆瓣热播/观看历史 → 返回主页网格切换
按钮位置运行时按 PANEL 色块聚类定位，不依赖硬编码坐标。
"""
import json
import subprocess
import time

import win32gui, win32con, win32process, win32api
import pyautogui
from PIL import ImageGrab

pyautogui.FAILSAFE = False
D = r'D:\code\tvbox2exe\tvboxpy\dist'
PANEL = (0x1C, 0x24, 0x40)


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
    print('shot', name, flush=True)


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


def find_toolbar_settings(h):
    """主页工具栏最后一颗按钮即「设置」：扫 PANEL 色带聚类"""
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
    assert rows, 'toolbar not found'
    ymid = rows[len(rows) // 2]
    runs = panel_runs(px, ymid, r[0], r[0] + 1300)
    print('toolbar y=%d runs=%s' % (ymid, runs), flush=True)
    assert len(runs) == 6, 'expect 6 toolbar buttons'
    s, e = runs[-1]          # 设置
    return (s + e) // 2, ymid


def find_home_rec_card(h):
    """设置页：PANEL 宽条带 = 卡片行；第一条恰好 2 张卡的行即「首页站源|首页推荐」
    （首卡「配置地址」持有焦点呈 ACCENT 色不会被计入，行带整体上移，不能按下标取）"""
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
    print('card bands:', bands, flush=True)
    for y0, y1 in bands:
        runs = panel_runs(px, y0 + 8, r[0], r[2])
        if len(runs) == 2:
            print('row runs:', runs, flush=True)
            s, e = runs[1]       # 右卡「首页推荐」
            return (s + e) // 2, (y0 + y1) // 2
    raise AssertionError('two-card row (首页站源|首页推荐) not found')


def click(h, x, y, wait=0):
    pyautogui.click(x, y)
    print('click(%d,%d)' % (x, y), flush=True)
    if wait:
        time.sleep(wait)


def open_settings(h):
    x, y = find_toolbar_settings(h)
    click(h, x, y, wait=2)


def home_rec():
    try:
        with open(D + r'\hawk.json', encoding='utf-8') as f:
            return json.load(f).get('home_rec')
    except Exception as e:
        return 'ERR:' + str(e)


def pick_mode(h, key, n, label):
    """打开首页推荐弹窗并用方向键移动 n 次后回车"""
    x, y = find_home_rec_card(h)
    click(h, x, y, wait=1.5)
    shot('hr_dlg_' + label)
    for _ in range(n):
        pyautogui.press(key)
        time.sleep(0.4)
    pyautogui.press('enter')
    time.sleep(1.2)
    shot('hr_picked_' + label)
    print('hawk home_rec =', home_rec(), flush=True)
    # 返回主页
    r = win32gui.GetWindowRect(h)
    click(h, r[0] + 42, r[1] + 26, wait=10)
    shot('hr_home_' + label)


# ------------------------------------------------ main ----
subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
time.sleep(2)
print('hawk before:', home_rec(), flush=True)
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
shot('hr_home0')

# 模式一：豆瓣热播（当前=站点推荐 → up 一次）
open_settings(h)
shot('hr_setting')
pick_mode(h, 'up', 1, 'douban')

# 模式二：观看历史（当前=豆瓣热播 → down 两次）
open_settings(h)
pick_mode(h, 'down', 2, 'hist')

print('hawk final:', home_rec(), flush=True)
print('done', flush=True)
subprocess.run(['taskkill', '/F', '/IM', 'tvboxpy.exe'], capture_output=True)
