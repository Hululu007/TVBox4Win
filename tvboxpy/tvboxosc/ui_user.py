"""主页 UserFragment 复刻：功能宫格（点播/直播/搜索/推送/历史/收藏/设置）"""
import datetime
import tkinter as tk
from . import ui_thread

from .theme import BG, FG, FG_DIM, ACCENT, FOCUS_BG, FOCUS_FG, FocusLabel, tv_font, PANEL

MENU = [
    ("历史", "ui_history", "🕘"),
    ("直播", "ui_live", "📺"),
    ("搜索", "ui_search", "🔍"),
    ("推送", "ui_push", "⚡"),
    ("收藏", "ui_collect", "♡"),
    ("设置", "ui_setting", "⚙"),
]

_WEEK = "一二三四五六日"


class UserFragment(tk.Frame):
    """对应 ui/fragment/UserFragment.java：顶栏 + 主页胶囊 + 大号功能按钮排
    （布局对照原版截图：TVBox 标题 / 右侧完整日期时间 / 一排图标+文字大按钮，
    下方大区域为壁纸区——原版点击壁纸进点播，此处同样处理）"""

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.configure(bg=BG)

        # 顶部：TVBox 标题 + 完整日期时间（2026/10/25 周日 18:44）
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=24, pady=(16, 4))
        tk.Label(top, text="TVBox", bg=BG, fg=FG,
                 font=tv_font(22, True)).pack(side="left")
        self.clock = tk.Label(top, text="", bg=BG, fg=FG, font=tv_font(15, True))
        self.clock.pack(side="right")
        self._tick()

        # 「主页」胶囊标签（原版首页左上角 badge）
        pill = tk.Label(self, text=" 主页 ", bg=FOCUS_BG, fg=FOCUS_FG,
                        font=tv_font(15, True), padx=14, pady=4)
        pill.pack(anchor="w", padx=24, pady=(6, 2))
        try:  # 圆角胶囊（Windows 下 tkinter 无原生圆角，用无边框叠画太重，保持方角即可）
            pill.configure(justify="center")
        except Exception:
            pass

        # 功能按钮排：一横排大按钮（图标 + 文字，半透明面板底，留白充足）
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=24, pady=(10, 6))
        btns = []
        for name, target, icon in MENU:
            b = FocusLabel(row, text=f"{icon} {name}", bg=PANEL, fg=FG,
                           font=tv_font(17, True), padx=26, pady=18,
                           on_select=lambda t=target: self._go(t))
            b.pack(side="left", padx=(0, 12))
            btns.append(b)
        for b in btns:  # 横排左右导航
            b.bind("<Right>", lambda e, bs=btns: self._nav(e, bs, 1))
            b.bind("<Left>", lambda e, bs=btns: self._nav(e, bs, -1))
        btns[0].focus_set()

        # 下方大区域 = 壁纸区，点击进点播（对应原版点壁纸进 VOD）
        import os, sys
        wall_path = os.path.join(os.path.dirname(__file__), "assets", "wallpaper.png")
        if not os.path.exists(wall_path) and getattr(sys, "_MEIPASS", None):
            wall_path = os.path.join(sys._MEIPASS, "tvboxosc", "assets", "wallpaper.png")
        try:
            from PIL import Image as _Img
            _img = _Img.open(wall_path)
            self._wall_photo = None
            self.wall = tk.Canvas(self, bg=BG, highlightthickness=0)
            self.wall.pack(expand=True, fill="both")

            def _paint(e):
                w = max(e.width, 1)
                h = max(e.height, 1)
                scaled = _img.resize((w, h))
                from PIL import ImageTk
                self._wall_photo = ImageTk.PhotoImage(scaled)
                self.wall.delete("all")
                self.wall.create_image(0, 0, image=self._wall_photo, anchor="nw")

            self.wall.bind("<Configure>", _paint)
        except Exception:
            self.wall = tk.Label(self, bg=BG)
            self.wall.pack(expand=True, fill="both")
        for seq in ("<Button-1>", "<Return>", "<space>"):
            self.wall.bind(seq, lambda e: self._go("ui_grid"))

    @staticmethod
    def _nav(e, widgets, step):
        try:
            idx = widgets.index(e.widget) + step
        except ValueError:
            return
        if 0 <= idx < len(widgets):
            widgets[idx].focus_set()
            return "break"

    def _tick(self):
        try:
            if not self.winfo_exists():
                return
            now = datetime.datetime.now()
            self.clock.configure(text=now.strftime(
                f"%Y/%m/%d 周{_WEEK[now.weekday()]} %H:%M"))
            self.after(1000, self._tick)
        except tk.TclError:
            pass  # 页面已销毁


class PlaceholderPage(tk.Frame):
    def __init__(self, master, app, title=""):
        super().__init__(master, bg=BG)
        tk.Label(self, text=f"【{title}】页面尚未移植（对应任务待完成）",
                 bg=BG, fg=FG, font=tv_font(16)).pack(expand=True)
        back = FocusLabel(self, text="返回", on_select=app.go_home)
        back.pack(pady=20)
        back.focus_set()
