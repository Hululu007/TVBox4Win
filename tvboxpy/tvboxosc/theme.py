"""TVBox 主题常量 + 公共控件（深蓝夜色主题：海军蓝底 + 卡片面板 + 蓝色焦点）"""
import tkinter as tk
from tkinter import font as tkfont

# ---- 调色板：夜空蓝 ----
BG = "#12172B"          # 页面底色（深海军蓝）
PANEL = "#1C2440"       # 卡片/按钮面板
PANEL_HI = "#26325C"    # 悬浮/次级面板
FG = "#EAF0FF"          # 主文字（柔白）
FG_DIM = "#8C97B8"      # 次级文字（雾蓝）
FOCUS_BG = "#3D7BFF"    # 焦点高亮（品牌蓝）
FOCUS_FG = "#FFFFFF"
ACCENT = "#FF7A59"      # 强调色（珊瑚橙）
POSTER_BG = "#1C2440"   # 海报占位底
DANGER_BG = "#4A2030"   # 错误/警示底


def focus_style(widget, focused):
    if focused:
        widget.configure(bg=FOCUS_BG, fg=FOCUS_FG)
    else:
        widget.configure(bg=widget._bg0, fg=widget._fg0)


class FocusLabel(tk.Label):
    """带焦点样式的 Label（复刻 Android TV focus 效果）"""
    def __init__(self, master, text="", on_select=None, bg=BG, fg=FG,
                 font=None, padx=14, pady=6, **kw):
        self._bg0, self._fg0 = bg, fg
        self.on_select = on_select
        super().__init__(master, text=text, bg=bg, fg=fg, font=font,
                         padx=padx, pady=pady, **kw)
        self.bind("<FocusIn>", lambda e: focus_style(self, True))
        self.bind("<FocusOut>", lambda e: focus_style(self, False))
        self.bind("<Return>", self._activate)
        self.bind("<space>", self._activate)
        self.bind("<Double-Button-1>", self._activate)
        self.bind("<Button-1>", self._activate)

    def _activate(self, _e=None):
        if self.on_select:
            self.on_select()


def tv_font(size=13, bold=False):
    fam = "Microsoft YaHei UI"
    return (fam, size, "bold" if bold else "normal")


def grid_key_nav(widgets, cols, up_down_rows=1):
    """为 widget 网格绑定方向键导航（模拟 TV 遥控焦点移动）"""
    def key(e):
        try:
            idx = widgets.index(e.widget)
        except ValueError:
            return
        r, c = divmod(idx, cols)
        if e.keysym == "Right" and c < cols - 1:
            widgets[idx + 1].focus_set()
        elif e.keysym == "Left" and c > 0:
            widgets[idx - 1].focus_set()
        elif e.keysym == "Down" and r + up_down_rows <= (len(widgets) - 1) // cols:
            widgets[min(idx + cols, len(widgets) - 1)].focus_set()
        elif e.keysym == "Up" and r > 0:
            widgets[max(idx - cols, 0)].focus_set()
        else:
            return
        e.widget.tk.call("event", "generate", e.widget, "<FocusOut>")
        return "break"
    for w in widgets:
        w.bind("<Right>", key)
        w.bind("<Left>", key)
        w.bind("<Down>", key)
        w.bind("<Up>", key)
