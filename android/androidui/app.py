"""安卓版应用骨架：全局状态、页面路由、源切换、配置加载。

业务逻辑全部走 vendor/tvboxosc（与桌面版同一份代码），这里只做界面与调度。
"""
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from tvboxosc import apiconfig, hawk

from . import theme
from .widgets import AutoLabel, FlatButton


class State:
    """全局状态：配置 / 可用站点 / 当前站点（对应桌面版的 GridPage 状态）"""

    def __init__(self):
        self.config = None
        self.beans = []          # 只保留 type 0/1/2（安卓无 node / JVM 运行时）
        self.bean = None
        self.config_url = ""

    def pick_bean(self, key):
        b = self.config.get(key) if self.config else None
        if b is not None and b.is_type012():
            self.bean = b
        return self.bean


state = State()


# ------------------------------------------------------------------ 通用弹窗

def _popup(title, body, height=0.5):
    p = Popup(title=title, content=body, size_hint=(0.92, height),
              title_font=theme.FONT, separator_color=theme.ACCENT)
    return p


def prompt_config(on_done, initial=""):
    """输入接口配置地址（对应桌面版的配置对话框）"""
    box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
    box.add_widget(AutoLabel(
        text="填入 TVBox 接口配置地址（TVBox 配置 JSON 的 URL）",
        color=theme.FG_DIM, font_size="12sp",
        size_hint_y=None, height=dp(40)))
    ti = TextInput(text=initial or hawk.get(hawk.HOME_API, "") or "",
                   multiline=False, font_name=theme.FONT,
                   background_color=theme.PANEL, foreground_color=theme.FG,
                   cursor_color=theme.ACCENT, size_hint_y=None, height=dp(44))
    box.add_widget(ti)
    row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
    p = _popup("配置接口", box, 0.46)

    def do_ok(*_):
        url = (ti.text or "").strip()
        p.dismiss()
        if url:
            on_done(url)

    ok = FlatButton(text="确定", bg=theme.BLUE)
    ok.bind(on_release=do_ok)
    cancel = FlatButton(text="取消")
    cancel.bind(on_release=lambda *_: p.dismiss())
    row.add_widget(cancel)
    row.add_widget(ok)
    box.add_widget(row)
    p.open()


def choose_source(beans, current, on_pick):
    """选择站点源（对应桌面版的源列表）"""
    box = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(8))
    sv = ScrollView()
    grid = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
    grid.bind(minimum_height=grid.setter("height"))
    p = _popup("选择站点源", box, 0.7)

    for b in beans:
        label = b.name or b.key
        if current is not None and b.key == current.key:
            label = "✓ " + label
        btn = FlatButton(text=label, size_hint_y=None, height=dp(46),
                         bg=theme.PANEL_HI if (current and b.key == current.key)
                         else theme.PANEL)
        btn.bind(on_release=lambda _b, bean=b: (p.dismiss(), on_pick(bean)))
        grid.add_widget(btn)
    if not beans:
        grid.add_widget(AutoLabel(text="配置里没有可用的 CMS 源",
                                  color=theme.FG_DIM, size_hint_y=None,
                                  height=dp(40)))
    sv.add_widget(grid)
    box.add_widget(sv)
    close = FlatButton(text="关闭", size_hint_y=None, height=dp(44))
    close.bind(on_release=lambda *_: p.dismiss())
    box.add_widget(close)
    p.open()


def toast(msg):
    """轻提示"""
    box = BoxLayout(padding=dp(10))
    box.add_widget(AutoLabel(text=msg, color=theme.FG, font_size="13sp",
                             halign="center"))
    p = Popup(title="", content=box, size_hint=(0.8, 0.24),
              title_size=0, separator_height=0, background_color=theme.PANEL)
    p.open()
    Clock.schedule_once(lambda _dt: p.dismiss(), 1.8)


# ------------------------------------------------------------------ 页面骨架

class BaseScreen(Screen):
    """带顶栏的页面基类"""

    title_text = ""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.root_box = BoxLayout(orientation="vertical")
        self.add_widget(self.root_box)
        self.topbar = BoxLayout(size_hint_y=None, height=dp(52),
                                padding=(dp(10), dp(6)), spacing=dp(8))
        self._paint_topbar()
        self.root_box.add_widget(self.topbar)

    def _paint_topbar(self):
        from kivy.graphics import Color, Rectangle
        with self.topbar.canvas.before:
            Color(*theme.PANEL)
            self._top_rect = Rectangle(pos=self.topbar.pos, size=self.topbar.size)
        self.topbar.bind(pos=self._sync_top, size=self._sync_top)

    def _sync_top(self, *_):
        self._top_rect.pos = self.topbar.pos
        self._top_rect.size = self.topbar.size

    def add_top_button(self, text, on_release, width=dp(44)):
        b = FlatButton(text=text, size_hint=(None, 1), width=width,
                       font_size="14sp")
        b.bind(on_release=lambda *_: on_release())
        self.topbar.add_widget(b)
        return b

    def add_top_title(self, text, sub=None):
        box = BoxLayout(orientation="vertical", size_hint_x=1)
        lbl = Label(text=text, font_name=theme.FONT, color=theme.FG,
                    font_size="15sp", halign="left", valign="middle",
                    size_hint_y=None, height=dp(24))
        lbl.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, dp(24))))
        box.add_widget(lbl)
        if sub:
            self._sub = Label(text=sub, font_name=theme.FONT,
                              color=theme.FG_DIM, font_size="10sp",
                              halign="left", valign="top", size_hint_y=None,
                              height=dp(16))
            self._sub.bind(size=lambda w, *_: setattr(
                w, "text_size", (w.width, dp(16))))
            box.add_widget(self._sub)
        self.topbar.add_widget(box)
        return box

    def set_sub(self, text):
        if getattr(self, "_sub", None) is not None:
            self._sub.text = text or ""


class Root(ScreenManager):
    def __init__(self, **kw):
        super().__init__(transition=SlideTransition(duration=0.12), **kw)
        from .home import HomeScreen
        from .search import SearchScreen
        from .detail import DetailScreen
        from .play import PlayScreen
        self.home = HomeScreen(name="home")
        self.search = SearchScreen(name="search")
        self.detail = DetailScreen(name="detail")
        self.play = PlayScreen(name="play")
        for s in (self.home, self.search, self.detail, self.play):
            self.add_widget(s)


class TVBoxApp(App):
    title = "TVBox4Win"

    def build(self):
        theme.register_font()
        Window.clearcolor = theme.BG
        Window.softinput_mode = "below_target"
        Window.bind(on_keyboard=self._on_key)
        self.root_widget = Root()
        return self.root_widget

    def on_start(self):
        self.root_widget.home.bootstrap()

    # 安卓返回键（27）/ 桌面 Esc：逐级返回，首页则放行退出
    def _on_key(self, _win, key, *_a):
        if key not in (27, 1001):
            return False
        root = self.root_widget
        cur = root.current
        if cur == "play":
            root.play.stop()
            root.current = "detail"
            return True
        if cur in ("detail", "search"):
            root.current = "home"
            return True
        return False
