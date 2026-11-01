"""首页：站点源 + 分类 chips + 影片网格 + 分页加载。

对应桌面版 ui_grid.py 的主干（分类浏览），不含首页推荐位：
安卓首版先保证「选源 → 分类 → 列表 → 详情 → 播放」这条主链路跑通。
"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView

from tvboxosc import apiconfig, data_api, hawk

from . import theme
from .app import BaseScreen, choose_source, prompt_config, state, toast
from .net import run
from .widgets import AutoLabel, Chip, FlatButton, PosterBoard


class HomeScreen(BaseScreen):

    def __init__(self, **kw):
        super().__init__(**kw)
        self.vods = []
        self.page = 1
        self.page_count = 1
        self.cur_class = None
        self._chips = []
        self._build()

    # ------------------------------------------------------------ 界面搭建

    def _build(self):
        self.add_top_title("TVBox4Win", "未加载")
        self.add_top_button("源", self._pick_source, dp(40))
        self.add_top_button("搜", self._go_search, dp(40))
        self.add_top_button("设", self._go_setting, dp(40))

        # 分类横条
        self.chip_scroll = ScrollView(size_hint_y=None, height=dp(48),
                                      do_scroll_y=False, bar_width=0)
        self.chip_box = BoxLayout(orientation="horizontal", spacing=dp(6),
                                  padding=(dp(8), dp(6)), size_hint_x=None)
        self.chip_box.bind(minimum_width=self.chip_box.setter("width"))
        self.chip_scroll.add_widget(self.chip_box)
        self.root_box.add_widget(self.chip_scroll)

        # 状态提示
        self.hint = AutoLabel(text="", color=theme.FG_DIM, font_size="12sp",
                              size_hint_y=None, height=dp(22),
                              padding=(dp(12), 0))
        self.root_box.add_widget(self.hint)

        # 海报网格
        self.board = PosterBoard(on_tap=self._open_detail)
        self.root_box.add_widget(self.board)

        # 底部：加载更多
        self.more_box = BoxLayout(size_hint_y=None, height=dp(0), padding=dp(6))
        self.root_box.add_widget(self.more_box)

    # ------------------------------------------------------------ 启动加载

    def bootstrap(self):
        """进入应用：恢复上次配置并加载"""
        url = hawk.get(hawk.HOME_API)
        if not url:
            self.board.empty("还没有配置接口源。\n点右上角「设」填入配置地址。")
            return
        self._load_config(url)

    def _load_config(self, url):
        self.hint.text = "正在加载接口配置…"
        cfg = apiconfig.ApiConfig()

        def ok():
            state.config = cfg
            state.config_url = url
            state.beans = [b for b in cfg.source_bean_list if b.is_type012()]
            if not state.beans:
                self.hint.text = ""
                self.board.empty(
                    "配置里没有可用的 CMS 源。\n"
                    "安卓版暂不支持 jar / js 爬虫源（需要 JVM 或 node 运行时），"
                    "请换一个含 CMS 站点（type 0/1）的配置。")
                return
            state.pick_bean(hawk.get(hawk.HOME_SOURCE))
            if state.bean is None:
                state.bean = state.beans[0]
            hawk.put(hawk.HOME_SOURCE, state.bean.key)
            self.set_sub("%s · %d 个可用源" % (state.bean.name, len(state.beans)))
            self._load_classes()

        def err(msg):
            self.hint.text = ""
            self.board.empty(msg or "配置加载失败")

        cfg.load(url, ok, err)

    def _load_classes(self):
        bean = state.bean
        self.hint.text = "正在读取分类…"
        run(lambda: data_api.get_classes(bean), self._render_chips,
            lambda e: setattr(self.hint, "text", "分类读取失败：" + e))

    def _render_chips(self, classes):
        self.chip_box.clear_widgets()
        self._chips = []
        self.hint.text = ""
        if not classes:
            self.board.empty("该源没有返回分类，可能不是标准 CMS 接口")
            return
        for cid, name in classes:
            c = Chip(text=name)
            c.on_tap = lambda ch, i=cid: self.select_class(i)
            self.chip_box.add_widget(c)
            self._chips.append((cid, c))
        self.select_class(classes[0][0])

    def _sync_chip_state(self):
        for cid, c in self._chips:
            c.set_active(cid == self.cur_class)

    # ------------------------------------------------------------ 列表加载

    def select_class(self, cid):
        if cid == self.cur_class and self.vods:
            return
        self.cur_class = cid
        self._sync_chip_state()
        self.vods = []
        self.page = 1
        self.page_count = 1
        self.board.clear()
        self._load_page(1)

    def _load_page(self, page):
        bean, cid = state.bean, self.cur_class
        if bean is None or cid is None:
            return
        self.hint.text = "加载中…（第 %d 页）" % page
        run(lambda: data_api.get_vods(bean, cid, page),
            lambda res: self._on_vods(res, page), self._on_err)

    def _on_vods(self, res, page):
        vods, cur_page, pagecount = res
        self.page = cur_page
        self.page_count = pagecount
        self.hint.text = "" if vods else "该分类暂无内容"
        for item in vods:
            self.vods.append(item)
        self.board.append(vods)
        self._update_more()

    def _on_err(self, msg):
        self.hint.text = "加载失败：" + msg
        toast("加载失败：" + msg)

    def _update_more(self):
        self.more_box.clear_widgets()
        if self.page >= self.page_count:
            self.more_box.height = dp(0)
            return
        self.more_box.height = dp(52)
        btn = FlatButton(text="加载更多（%d/%d）" % (self.page, self.page_count),
                         bg=theme.PANEL)
        btn.bind(on_release=lambda *_: self._load_page(self.page + 1))
        self.more_box.add_widget(btn)

    # ------------------------------------------------------------ 交互入口

    def _open_detail(self, vid, name):
        self.manager.detail.open(state.bean, vid, name)
        self.manager.current = "detail"

    def _pick_source(self):
        if not state.beans:
            toast("还没有加载到可用的源")
            return
        choose_source(state.beans, state.bean, self._switch_source)

    def _switch_source(self, bean):
        state.bean = bean
        hawk.put(hawk.HOME_SOURCE, bean.key)
        self.set_sub("%s · %d 个可用源" % (bean.name, len(state.beans)))
        self.cur_class = None
        self._chips = []
        self.chip_box.clear_widgets()
        self.board.clear()
        self._load_classes()

    def _go_search(self):
        self.manager.current = "search"

    def _go_setting(self):
        prompt_config(self._load_config,
                      initial=hawk.get(hawk.HOME_API, "") or "")
