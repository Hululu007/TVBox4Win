# -*- coding: utf-8 -*-
"""P0-5 目视验证：坏配置 → 重试 / 更换配置 → 成功进首页（截图留在 tests/）"""
import json
import os
import subprocess
import sys
import tempfile
import time

import pyautogui
import win32api
import win32clipboard
import win32con
import win32gui
import win32process
from PIL import ImageGrab

pyautogui.FAILSAFE = False
ROOT = r"D:\code\tvbox2exe\tvboxpy"
OUT = os.path.join(ROOT, "tests")


def find_win():
    res = []

    def cb(hh, _):
        if not win32gui.IsWindowVisible(hh):
            return
        if "TVBox4Win v" not in (win32gui.GetWindowText(hh) or ""):
            return
        _, wpid = win32process.GetWindowThreadProcessId(hh)
        try:
            ph = win32api.OpenProcess(0x0400 | 0x0010, False, wpid)
            exe = win32process.GetModuleFileNameEx(ph, 0).lower()
        except Exception:
            exe = ""
        if exe.endswith("python.exe") or exe.endswith("tvbox4win.exe"):
            res.append(hh)

    win32gui.EnumWindows(cb, None)
    return res[0] if res else None


def shot(h, name):
    r = win32gui.GetWindowRect(h)
    ImageGrab.grab(bbox=r).save(os.path.join(OUT, name))
    print("shot:", name, r, flush=True)


def paste(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text)
    win32clipboard.CloseClipboard()
    pyautogui.hotkey("ctrl", "a")
    pyautogui.hotkey("ctrl", "v")


# 一份可用的本地配置（含一个 CMS 站点，进首页后不会立刻请求网络）
tmp = tempfile.mkdtemp(prefix="tvbox_p05_")
cfg = os.path.join(tmp, "cfg.json")
with open(cfg, "w", encoding="utf-8") as f:
    json.dump({"sites": [{"key": "demo", "name": "本地测试站",
                          "api": "http://127.0.0.1:9/api.php/provide/vod/"}]}, f)

def _read(p):
    try:
        with open(p, "rb") as f:
            return f.read()
    except OSError:
        return None


# 诊断会写入真实配置目录：结束后原样恢复，避免污染本机设置
_hawk_path = os.path.join(ROOT, "hawk.json")
_store_path = os.path.join(ROOT, "tvbox.json")
_old_hawk, _old_store = _read(_hawk_path), _read(_store_path)

subprocess.run(["taskkill", "/F", "/IM", "TVBox4Win.exe"], capture_output=True)
bad = os.path.join(tmp, "missing.json")
p = subprocess.Popen([sys.executable, os.path.join(ROOT, "main.py"), bad], cwd=ROOT)

h = None
for _ in range(40):
    time.sleep(0.5)
    h = find_win()
    if h:
        break
assert h, "no window"
win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 80, 80, 1280, 760,
                      win32con.SWP_SHOWWINDOW)
time.sleep(3)
shot(h, "p05_error.png")

pyautogui.press("enter")          # 重试（错误时焦点在「重试」上）
time.sleep(2)
shot(h, "p05_retry.png")

pyautogui.press("tab")            # 焦点从「重试」移到「更换配置」
pyautogui.press("enter")
time.sleep(1)
shot(h, "p05_dialog.png")

paste(cfg)
pyautogui.press("enter")          # 确定 → 加载本地配置
time.sleep(3)
shot(h, "p05_loaded.png")

p.terminate()
try:
    p.wait(timeout=5)
except subprocess.TimeoutExpired:
    p.kill()
for path, old in ((_hawk_path, _old_hawk), (_store_path, _old_store)):
    if old is None:
        try:
            os.remove(path)
        except OSError:
            pass
    else:
        with open(path, "wb") as f:
            f.write(old)
print("done", flush=True)
