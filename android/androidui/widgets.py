"""安卓版通用控件：扁平按钮 / 分类 chip / 海报卡片。

Kivy 默认按钮是灰色贴图背景，跟深蓝主题不搭，这里统一用 canvas 圆角矩形重绘。
"""
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import AsyncImage
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from . import theme
from .theme import ACCENT, FG, FG_DIM, PANEL, PANEL_HI, POSTER_BG, poster_size


class AutoLabel(Label):
    """按宽度自动换行的 Label（Kivy 默认不换行，必须自己绑 text_size）"""

    def __init__(self, **kw):
        kw.setdefault("font_name", theme.FONT)
        kw.setdefault("color", FG)
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        super().__init__(**kw)
        self.bind(size=self._sync, width=self._sync)
        self._sync()

    def _sync(self, *_):
        self.text_size = (self.width, None)


class FlatButton(Button):
    """圆角纯色按钮"""

    def __init__(self, bg=PANEL, radius=dp(8), fg=FG, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_down", "")
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("font_name", theme.FONT)
        kw.setdefault("color", fg)
        super().__init__(**kw)
        with self.canvas.before:
            self._color = Color(*bg)
            self._rect = RoundedRectangle(radius=[radius])
        self.bind(pos=self._sync, size=self._sync)
        self._sync()

    def _sync(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def set_bg(self, rgba):
        self._color.rgba = rgba


class Chip(FlatButton):
    """分类 / 剧集用的胶囊按钮，带选中态"""

    def __init__(self, text="", on_tap=None, **kw):
        kw.setdefault("size_hint", (None, None))
        kw.setdefault("height", dp(34))
        kw.setdefault("font_size", "13sp")
        kw.setdefault("radius", dp(17))
        super().__init__(text=text, **kw)
        self.on_tap = on_tap
        self.active = False
        self.bind(on_release=self._release)
        self._autosize()

    def _autosize(self):
        # 按钮宽度跟着文字走，太长就截断
        self.texture_update()
        self.width = max(dp(56), self.texture_size[0] + dp(28))

    def _release(self, *_):
        if self.on_tap:
            self.on_tap(self)

    def set_active(self, yes):
        self.active = yes
        self.set_bg(ACCENT if yes else PANEL)
        self.color = (1, 1, 1, 1) if yes else FG_DIM


class PosterCard(ButtonBehavior, BoxLayout):
    """海报卡片：图片 + 片名 + 备注（点按进入详情）"""

    def __init__(self, name="", pic="", note="", on_tap=None, **kw):
        kw.setdefault("orientation", "vertical")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("padding", (dp(2), dp(2)))
        kw.setdefault("spacing", dp(2))
        super().__init__(**kw)
        self.on_tap = on_tap
        with self.canvas.before:
            self._bgc = Color(*POSTER_BG)
            self._rect = RoundedRectangle(radius=[dp(8)])
        self.bind(pos=self._sync, size=self._sync)
        self._sync()
        self.img = AsyncImage(
            source=pic or "", allow_stretch=True, keep_ratio=True,
            nocache=False, mipmap=True, size_hint_y=1.0)
        self.add_widget(self.img)
        self.name_label = Label(
            text=(name or "　")[:14], font_name=theme.FONT, color=FG,
            font_size="12sp", size_hint_y=None, height=dp(20),
            shorten=True, shorten_from="right")
        self.add_widget(self.name_label)
        if note:
            self.add_widget(Label(
                text=note[:16], font_name=theme.FONT, color=FG_DIM,
                font_size="10sp", size_hint_y=None, height=dp(16),
                shorten=True, shorten_from="right"))
        else:
            self.add_widget(Label(text="", size_hint_y=None, height=dp(16)))

    def _sync(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def on_release(self):
        if self.on_tap:
            self.on_tap()


class SectionTitle(Label):
    """小节标题（左侧橙色竖条用颜色区分，不做复杂装饰）"""

    def __init__(self, **kw):
        kw.setdefault("font_name", theme.FONT)
        kw.setdefault("color", ACCENT)
        kw.setdefault("font_size", "14sp")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(28))
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        super().__init__(**kw)
        self.bind(size=self._sync, width=self._sync)
        self._sync()

    def _sync(self, *_):
        self.text_size = (self.width, None)


def grid_cols():
    """按屏幕宽度定列数：手机竖屏 3 列，平板/横屏加列"""
    from kivy.core.window import Window
    w = Window.width
    if w >= dp(1000):
        return 6
    if w >= dp(720):
        return 5
    if w >= dp(560):
        return 4
    return 3


class PosterBoard(BoxLayout):
    """滚动海报网格：清空 / 追加影片 / 空态提示，首页与搜索页共用"""

    def __init__(self, on_tap=None, **kw):
        kw.setdefault("orientation", "vertical")
        super().__init__(**kw)
        self.on_tap = on_tap
        self.rows = []
        self.sv = ScrollView(bar_width=dp(2), scroll_type=["bars", "content"])
        self.grid = GridLayout(cols=grid_cols(), spacing=dp(6), padding=dp(6),
                               size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.sv.add_widget(self.grid)
        self.add_widget(self.sv)
        self.bind(size=lambda *_: self.relayout())

    def relayout(self):
        cols = grid_cols()
        if cols != self.grid.cols:
            self.grid.cols = cols
        cw, ch = poster_size(cols)
        for card in self.grid.children:
            card.width = cw
            card.height = ch

    def clear(self):
        self.grid.clear_widgets()
        self.rows = []

    def empty(self, text):
        self.clear()
        self.grid.add_widget(AutoLabel(
            text=text, color=FG_DIM, font_size="13sp", halign="center",
            size_hint_y=None, height=dp(160), padding=(dp(24), dp(24))))

    def append(self, vods):
        """vods: [(vid, name, pic, remark)]；追加到末尾，不重建已有卡片"""
        cw, ch = poster_size(self.grid.cols)
        for vid, name, pic, remark in vods:
            self.rows.append(vid)
            card = PosterCard(
                name=name, pic=pic, note=remark, width=cw, height=ch + dp(52),
                on_tap=lambda v=vid, n=name: self._tap(v, n))
            self.grid.add_widget(card)
        self.relayout()

    def _tap(self, vid, name):
        if self.on_tap:
            self.on_tap(vid, name)

