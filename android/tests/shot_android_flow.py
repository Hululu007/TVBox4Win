"""跑通「首页 → 详情 → 播放」三页并分别截图（Kivy 桌面预览）。

用法：
    python tests/shot_android_flow.py [配置URL]

注意：桌面版 Kivy 没带 ffpyplayer 时 Video 控件播不了视频，播放页截图
只能验证布局；真实播放行为要在安卓设备/模拟器上验证（走系统 MediaPlayer）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "vendor"))

from kivy.config import Config          # noqa: E402

Config.set("graphics", "width", "390")
Config.set("graphics", "height", "844")
Config.set("graphics", "position", "custom")
Config.set("graphics", "left", "30")
Config.set("graphics", "top", "20")
Config.set("input", "mouse", "mouse")

from kivy.clock import Clock            # noqa: E402
from kivy.core.window import Window     # noqa: E402

from androidui.app import TVBoxApp      # noqa: E402
from tvboxosc import hawk               # noqa: E402

API = sys.argv[1] if len(sys.argv) > 1 else "https://cyao2q.github.io/files/m.json"
hawk.put(hawk.HOME_API, API)


def snap(root, name):
    """把 Kivy 窗口置顶后按真实窗口矩形截图（避免被别的窗口挡住）"""
    try:
        import time
        import win32con
        import win32gui

        hits = []

        def _cb(h, _):
            t = win32gui.GetWindowText(h)
            if t.startswith("TVBox4Win") and win32gui.IsWindowVisible(h):
                hits.append(h)

        win32gui.EnumWindows(_cb, None)
        if hits:
            win32gui.SetWindowPos(hits[0], win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetForegroundWindow(hits[0])
            time.sleep(0.6)
        x1, y1, x2, y2 = win32gui.GetWindowRect(hits[0]) if hits else \
            (Window.left, Window.top,
             Window.left + Window.width, Window.top + Window.height)
        import pyautogui
        pyautogui.screenshot(region=(x1, y1, x2 - x1, y2 - y1)).save(name)
    except Exception:
        import pyautogui
        pyautogui.screenshot(region=(Window.left, Window.top,
                                     Window.width, Window.height)).save(name)
    print("SHOT", os.path.abspath(name), flush=True)


app = TVBoxApp()
root = None


def step1_home(_dt):
    """等首页列表加载完 → 进详情"""
    home = root.home
    if not home.vods:
        print("首页还没有数据，跳过后续", flush=True)
        return app.stop()
    snap(root, "flow_1_home.png")
    vid, name = home.vods[0][0], home.vods[0][1]
    print("打开详情:", name, flush=True)
    home._open_detail(vid, name)
    root.current = "detail"
    Clock.schedule_once(step2_detail, 9)


def step2_detail(_dt):
    detail = root.detail
    snap(root, "flow_2_detail.png")
    if not detail.info or not (detail.info.get("series_flags")):
        print("详情没有线路，跳过播放", flush=True)
        return app.stop()
    # 找一条有剧集的线路
    flags = detail.info["series_flags"]
    urls = detail.info["series_urls"] or []
    for i, (_name, eps) in enumerate(flags):
        if eps:
            detail.select_flag(i)
            links = urls[i] if i < len(urls) else []
            print("播放:", eps[0], flush=True)
            detail._play(eps[0], links[0] if links else "", 0)
            break
    root.current = "play"
    Clock.schedule_once(step3_play, 12)


def step3_play(_dt):
    snap(root, "flow_3_play.png")
    app.stop()


def start(_dt):
    global root
    root = app.root_widget
    root.home.bootstrap()
    Clock.schedule_once(step1_home, 14)


Clock.schedule_once(start, 1.0)
app.run()
