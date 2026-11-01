"""搜索页：只搜当前站点源（对应桌面版 FastSearch 的单源分支）。

多源并发搜索在安卓首版先不做——手机上一次并发十几个源容易被打限流，
而且首版目标是先验证「能搜到、能播」这条链路。
"""
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput

from tvboxosc import data_api

from . import theme
from .app import BaseScreen, state, toast
from .net import run
from .widgets import AutoLabel, FlatButton, PosterBoard


class SearchScreen(BaseScreen):

    def __init__(self, **kw):
        super().__init__(**kw)
        self._build()

    def _build(self):
        self.add_top_button("←", lambda: setattr(self.manager, "current", "home"),
                            dp(40))
        self.ti = TextInput(
            hint_text="搜索影片名", multiline=False, font_name=theme.FONT,
            background_color=theme.PANEL, foreground_color=theme.FG,
            hint_text_color=theme.FG_DIM, cursor_color=theme.ACCENT,
            padding=(dp(10), dp(10)), size_hint=(1, 1))
        self.ti.bind(on_text_validate=lambda *_: self._do_search())
        self.topbar.add_widget(self.ti)
        self.add_top_button("搜", self._do_search, dp(44))

        self.hint = AutoLabel(text="", color=theme.FG_DIM, font_size="12sp",
                              size_hint_y=None, height=dp(22),
                              padding=(dp(12), 0))
        self.root_box.add_widget(self.hint)
        self.board = PosterBoard(on_tap=self._open_detail)
        self.root_box.add_widget(self.board)

    def on_pre_enter(self):
        Clock.schedule_once(lambda _dt: setattr(self.ti, "focus", True), 0.25)

    def _do_search(self):
        wd = (self.ti.text or "").strip()
        if not wd:
            toast("请先输入片名")
            return
        bean = state.bean
        if bean is None:
            toast("还没有加载到站点源")
            return
        if not bean.searchable:
            toast("当前源不支持搜索，可换个源再试")
            return
        self.hint.text = "正在搜索「%s」…" % wd
        self.board.clear()
        run(lambda: data_api.search_vods(bean, wd), self._on_results,
            lambda e: setattr(self.hint, "text", "搜索失败：" + e))

    def _on_results(self, vods):
        self.hint.text = "" if vods else "没搜到结果，换个关键词试试"
        self.board.append(vods)

    def _open_detail(self, vid, name):
        self.manager.detail.open(state.bean, vid, name)
        self.manager.current = "detail"
