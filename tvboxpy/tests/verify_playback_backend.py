# -*- coding: utf-8 -*-
"""播放链路验证（不依赖网络）

用 mpv 的 lavfi 本地测试信号当作片源，走完整的 UI 播放页路径：
建窗口 → 进播放页 → 等出画面（position 推进）→ 暂停/seek → 截图。

比 --smoke 更适合离线/受限网络环境验证「重构后播放器还能用」。

用法：python tests/verify_playback_backend.py [截图名]
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk      # noqa: E402

from tvboxosc import hawk, ui_thread          # noqa: E402
from tvboxosc.app import App                  # noqa: E402
from tvboxosc.ui_play import Page as PlayPage  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "play_check.png")

# 本地合成信号：mpv 的 lavfi 输入，无需任何网络
SRC = "av://lavfi:testsrc=size=640x360:rate=15:duration=30"

fails = []


def ok(msg):
    print("OK   " + msg)


def bad(msg):
    print("FAIL " + msg)
    fails.append(msg)


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        app.update()
        time.sleep(0.03)


app = App()
app.geometry("1280x720+40+40")
pump(1.0)

series = (("测试线路", ["测试信号"]), [SRC])
page = app.switch(PlayPage, "smoke", "smoke", "播放链路自检", "测试线路",
                  "测试信号", SRC, series=series, ep_index=0)
pump(1.5)

if not page.player:
    bad("播放页未创建播放器")
else:
    ok("播放器已创建，后端=%s" % page.player.backend_name)

# 等出画面（position 推进即可，无需真有视频窗口）
pos = dur = 0.0
end = time.time() + 20
while time.time() < end:
    app.update()
    time.sleep(0.1)
    if page.player:
        pos, dur, _p = page.player.status()
        if pos > 0.5:
            break
if pos > 0.5:
    ok("出画面：position=%.1fs / duration=%.1fs" % (pos, dur))
else:
    bad("20 秒内未出画面（position=%.1f）" % pos)

# 暂停 → 位置应基本停住
if page.player:
    page.player.set_pause(True)
    pump(0.4)
    p1, _d, paused = page.player.status()
    pump(1.2)
    p2, _d2, _p = page.player.status()
    if paused and abs(p2 - p1) < 0.6:
        ok("暂停生效（%.1fs → %.1fs）" % (p1, p2))
    else:
        bad("暂停异常：paused=%s %.1fs → %.1fs" % (paused, p1, p2))
    page.player.set_pause(False)
    pump(0.3)

    # seek：跳到 10s，位置应跟上
    page.player.seek(10)
    end = time.time() + 10
    got = 0.0
    while time.time() < end:
        app.update()
        time.sleep(0.1)
        got, _d, _p = page.player.status()
        if got > 7.0:
            break
    if got > 7.0:
        ok("seek 生效（跳到 10s 后 position=%.1fs）" % got)
    else:
        bad("seek 无效（position=%.1fs）" % got)

    # 倍速 / 音量接口不抛错即可
    try:
        page.player.set_speed(1.5)
        page.player.set_volume(60)
        vol = page.player.get_volume()
        ok("倍速/音量接口可用（volume=%d）" % vol)
    except Exception as e:
        bad("倍速/音量接口异常：%r" % (e,))

# 切页时播放器必须能安全解绑（旧实现这里会卡 UI 线程）
try:
    app.switch(type(page), "smoke", "smoke", "切页后", "测试线路", "测试信号",
               SRC, series=series, ep_index=0)
    pump(1.0)
    ok("切换播放页不卡死")
except Exception as e:
    bad("切换播放页异常：%r" % (e,))

try:
    import pyautogui
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    pyautogui.screenshot(region=(x, y, w, h)).save(OUT)
    print("saved", OUT)
except Exception as e:
    print("截图失败:", e)

try:
    page.player and page.player.terminate()
except Exception:
    pass
app.destroy()
print("\n== 通过 %d / 失败 %d ==" % (5 - len(fails), len(fails)) if not fails
      else "\n== 失败 %d 项 ==" % len(fails))
print("DONE" if not fails else "FAILED")
sys.exit(1 if fails else 0)
