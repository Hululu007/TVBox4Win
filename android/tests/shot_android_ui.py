"""本地预览安卓版界面并截图（Kivy 可以直接在桌面上跑，无需设备）。

用法：
    python tests/shot_android_ui.py shot.png [配置URL] [等待秒数]

窗口按手机竖屏尺寸（390x844）建立，截图用 pyautogui 抓窗口区域，
避免 Kivy 自带 screenshot 的文件名序号问题。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "vendor"))

from kivy.config import Config          # noqa: E402  必须在 kivy 其它模块前设置

Config.set("graphics", "width", "390")
Config.set("graphics", "height", "844")
# 新版 Kivy 的 position 只接受 auto/custom，坐标要单独设 left/top
Config.set("graphics", "position", "custom")
Config.set("graphics", "left", "30")
Config.set("graphics", "top", "20")
Config.set("input", "mouse", "mouse,multitouch_on_demand")

from kivy.clock import Clock            # noqa: E402
from kivy.core.window import Window     # noqa: E402

from androidui.app import TVBoxApp      # noqa: E402
from tvboxosc import hawk               # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "shot_android.png"
API = sys.argv[2] if len(sys.argv) > 2 else "https://cyao2q.github.io/files/m.json"
WAIT = float(sys.argv[3]) if len(sys.argv) > 3 else 16.0

if API != "-":
    hawk.put(hawk.HOME_API, API)

app = TVBoxApp()


def take(_dt):
    try:
        import pyautogui
        x, y = Window.left, Window.top
        w, h = Window.width, Window.height
        pyautogui.screenshot(region=(x, y, w, h)).save(OUT)
        print("SHOT", os.path.abspath(OUT), flush=True)
    except Exception as e:
        print("SHOT FAILED", e, flush=True)
    Clock.schedule_once(lambda _dt: app.stop(), 1.2)


Clock.schedule_once(take, WAIT)
app.run()
