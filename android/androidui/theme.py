"""安卓版配色与字体（沿用桌面版深蓝夜色主题）。

桌面版用的是 Tk 的十六进制色，这里是等价的 RGBA 元组。
中文字体：Kivy 自带的 Roboto 不含汉字，必须显式注册系统 CJK 字体，
安卓通常是 NotoSansCJK，桌面上调试时用微软雅黑 / 苹方。
"""
import os

from kivy.core.text import LabelBase
from kivy.metrics import dp

# ---- 调色板（与 tvboxosc/theme.py 一致）----
BG = (0.071, 0.090, 0.169, 1.0)        # #12172B 页面底色
PANEL = (0.110, 0.141, 0.251, 1.0)     # #1C2440 卡片/按钮
PANEL_HI = (0.149, 0.196, 0.361, 1.0)  # #26325C 次级面板
FG = (0.918, 0.941, 1.0, 1.0)          # #EAF0FF 主文字
FG_DIM = (0.549, 0.592, 0.722, 1.0)    # #8C97B8 次级文字
ACCENT = (1.0, 0.478, 0.349, 1.0)      # #FF7A59 强调（珊瑚橙）
BLUE = (0.239, 0.482, 1.0, 1.0)        # #3D7BFF 品牌蓝
POSTER_BG = (0.110, 0.141, 0.251, 1.0)

FONT = "Roboto"

_CANDIDATES = (
    # 单文件 ttf/otf 优先 —— Kivy 对 .ttc 字体集合"注册成功"却渲染不出汉字
    "/system/fonts/DroidSansFallback.ttf",          # 安卓几乎必带，含 CJK
    "/system/fonts/NotoSansSC-Regular.otf",
    "/system/fonts/NotoSansSC-Regular.ttf",
    "/system/fonts/NotoSansCJKsc-Regular.otf",
    "C:/Windows/Fonts/simhei.ttf",                  # Windows 黑体（单文件）
    "C:/Windows/Fonts/msyhl.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/system/fonts/DroidSansFallbackFull.ttf",
)


def register_font():
    """注册系统中文字体，返回资源名；都不存在时退回 Roboto（可能显示方块）"""
    global FONT
    for path in _CANDIDATES:
        if os.path.isfile(path):
            try:
                LabelBase.register(name="cjk", fn_regular=path)
                FONT = "cjk"
                return path
            except Exception:
                continue
    return None


def poster_size(cols=3):
    """按列数算海报卡片的尺寸（海报比例 244:320，与桌面版一致）"""
    from kivy.core.window import Window
    gap = dp(6)
    cell_w = (Window.width - gap * (cols + 1)) / float(cols)
    return cell_w, cell_w * 320.0 / 244.0 + dp(52)
