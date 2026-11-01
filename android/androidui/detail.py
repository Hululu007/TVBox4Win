"""详情页：海报 + 信息 + 简介 + 线路/剧集选择（对应桌面版 ui_detail.py）。"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import AsyncImage
from kivy.uix.scrollview import ScrollView

from tvboxosc import data_api

from . import theme
from .app import BaseScreen, state, toast
from .net import run
from .widgets import AutoLabel, Chip, FlatButton, SectionTitle

MAX_EPISODES = 300      # 千集长剧一次全渲染会卡，先截断并提示


class DetailScreen(BaseScreen):

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bean = None
        self.vid = None
        self.info = None
        self.flag_index = 0
        self._build()

    def _build(self):
        self.add_top_button("←", lambda: setattr(self.manager, "current", "home"),
                            dp(40))
        self.add_top_title("详情", "")

        self.sv = ScrollView(bar_width=dp(2))
        self.body = BoxLayout(orientation="vertical", padding=dp(12),
                              spacing=dp(10), size_hint_y=None)
        self.body.bind(minimum_height=self.body.setter("height"))
        self.sv.add_widget(self.body)
        self.root_box.add_widget(self.sv)

        # 头部：海报 + 基本信息
        self.head = BoxLayout(size_hint_y=None, height=dp(180), spacing=dp(12))
        self.poster = AsyncImage(allow_stretch=True, keep_ratio=True,
                                 size_hint=(None, 1), width=dp(124))
        self.head.add_widget(self.poster)
        self.meta = BoxLayout(orientation="vertical", spacing=dp(4))
        self.lb_name = AutoLabel(text="", font_size="15sp", color=theme.FG,
                                 bold=True, size_hint_y=None, height=dp(46))
        self.lb_info = AutoLabel(text="", font_size="11sp", color=theme.FG_DIM,
                                 size_hint_y=None, height=dp(28))
        self.lb_cast = AutoLabel(text="", font_size="11sp", color=theme.FG_DIM,
                                 size_hint_y=None, height=dp(40))
        for w in (self.lb_name, self.lb_info, self.lb_cast):
            self.meta.add_widget(w)
        self.head.add_widget(self.meta)
        self.body.add_widget(self.head)

        self.hint = AutoLabel(text="", color=theme.FG_DIM, font_size="12sp",
                              size_hint_y=None, height=dp(24))
        self.body.add_widget(self.hint)

        # 简介
        self.body.add_widget(SectionTitle(text="简介"))
        self.desc = AutoLabel(text="", font_size="12sp", color=theme.FG_DIM,
                              size_hint_y=None)
        self.desc.bind(texture_size=lambda w, s: setattr(w, "height", s[1]))
        self.body.add_widget(self.desc)

        # 线路
        self.body.add_widget(SectionTitle(text="线路"))
        self.flag_box = BoxLayout(size_hint_y=None, height=dp(38),
                                  spacing=dp(6))
        self.body.add_widget(self.flag_box)

        # 剧集
        self.body.add_widget(SectionTitle(text="选集"))
        self.ep_grid = GridLayout(cols=4, spacing=dp(6), size_hint_y=None)
        self.ep_grid.bind(minimum_height=self.ep_grid.setter("height"))
        self.body.add_widget(self.ep_grid)

    # ------------------------------------------------------------ 数据加载

    def open(self, bean, vid, name):
        self.bean, self.vid = bean, vid
        self.info = None
        self.flag_index = 0
        self.set_sub(name or "")
        self.hint.text = "加载详情…"
        self.poster.source = ""
        self.poster.reload()
        self.lb_name.text = name or ""
        self.lb_info.text = ""
        self.lb_cast.text = ""
        self.desc.text = ""
        self.flag_box.clear_widgets()
        self.ep_grid.clear_widgets()
        run(lambda: data_api.get_detail(bean, vid), self._render,
            lambda e: setattr(self.hint, "text", "详情加载失败：" + e))

    def _render(self, info):
        self.info = info
        if not info or not info.get("name"):
            self.hint.text = "详情为空，可能源已失效"
            return
        self.hint.text = ""
        self.poster.source = info.get("pic") or ""
        self.lb_name.text = info.get("name") or ""
        bits = [x for x in (info.get("remark"), info.get("year"),
                            info.get("area")) if x]
        self.lb_info.text = " · ".join(bits)
        cast = []
        if info.get("director"):
            cast.append("导演 " + info["director"])
        if info.get("actors"):
            cast.append("主演 " + info["actors"])
        self.lb_cast.text = "\n".join(cast)
        self.desc.text = (info.get("content") or "暂无简介").strip()
        self._render_flags()

    def _render_flags(self):
        self.flag_box.clear_widgets()
        flags = self.info.get("series_flags") or []
        self._flag_chips = []
        if not flags:
            self.hint.text = "该片没有可播放线路"
            return
        for i, (name, eps) in enumerate(flags):
            c = Chip(text=(name or ("线路%d" % (i + 1)))[:14])
            c.on_tap = lambda ch, idx=i: self.select_flag(idx)
            self.flag_box.add_widget(c)
            self._flag_chips.append(c)
        self.select_flag(0)

    def select_flag(self, idx):
        self.flag_index = idx
        for i, c in enumerate(self._flag_chips):
            c.set_active(i == idx)
        flags = self.info.get("series_flags") or []
        urls = self.info.get("series_urls") or []
        if idx >= len(flags):
            return
        names = flags[idx][1]
        links = urls[idx] if idx < len(urls) else []
        self.ep_grid.clear_widgets()
        if not names:
            self.hint.text = "该线路没有剧集"
            return
        self.hint.text = ""
        for i, ep_name in enumerate(names[:MAX_EPISODES]):
            btn = FlatButton(text=ep_name or ("第%d集" % (i + 1)),
                             font_size="11sp", bg=theme.PANEL)
            btn.bind(on_release=lambda _b, n=ep_name,
                     u=(links[i] if i < len(links) else ""), i=i:
                     self._play(n, u, i))
            self.ep_grid.add_widget(btn)
        if len(names) > MAX_EPISODES:
            self.ep_grid.add_widget(AutoLabel(
                text="仅显示前 %d 集" % MAX_EPISODES, color=theme.FG_DIM,
                font_size="11sp"))

    def _play(self, ep_name, ep_url, index):
        if not ep_url:
            toast("这一集没有播放地址")
            return
        flags = self.info.get("series_flags") or []
        flag = flags[self.flag_index][0] if flags else ""
        self.manager.play.open(self.bean, flag, ep_name, ep_url, self.info,
                               self.flag_index, index)
        self.manager.current = "play"
