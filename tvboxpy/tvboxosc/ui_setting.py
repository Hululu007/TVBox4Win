"""设置页 SettingActivity 复刻（布局对照原版截图：网格卡片，每项
「标签 + 当前值 ›」，2 列排布，方向键移动焦点）

卡片项：配置地址 / 配置历史 / 首页站源 / 首页推荐 / 下次进入 / 清空缓存 / 关于
"""
import os
import shutil
import tkinter as tk

from . import hawk, ui_thread, VERSION
from .apiconfig import api_config
from .theme import (BG, FG, FG_DIM, ACCENT, FOCUS_BG, FOCUS_FG,
                    FocusLabel, tv_font, PANEL)

DEFAULT_API = "https://cyao2q.github.io/files/m.json"

# 首页推荐（对应 HawkConfig.HOME_REC：0 豆瓣热播 / 1 站点推荐 / 2 观看历史）
HOME_REC_NAMES = {0: "豆瓣热播", 1: "站点推荐", 2: "观看历史"}
# 解码方式（对应 IJK_CODEC：硬解码 / 软解码，映射 mpv hwdec auto/no）
CODEC_NAMES = ("硬解码", "软解码")
# 画面缩放（对应 PLAY_SCALE / PlayerHelper.getScaleName）
SCALE_NAMES = {0: "默认", 1: "16:9", 2: "4:3", 3: "填充", 4: "原始"}
# 历史记录上限（对应 HISTORY_NUM / HistoryHelper.hisNumArray）
HIS_NUM_ARRAY = (30, 50, 100)


class Page(tk.Frame):
    """对应 ui/activity/SettingActivity.java"""

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self._vars = {}

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x")
        FocusLabel(bar, text="← 返回", font=tv_font(12, True),
                   on_select=app.go_home).pack(side="left", padx=12, pady=6)
        tk.Label(bar, text="设置", bg=BG, fg=FG, font=tv_font(16, True)
                 ).pack(side="left", padx=10)

        self.status = tk.Label(self, text="", bg=BG, fg=FG_DIM, font=tv_font(11))
        self.status.pack(side="bottom", fill="x", padx=24, pady=4)

        # 网格卡片（截图同款：2 列，方向键导航）
        grid = tk.Frame(self, bg=BG)
        grid.pack(expand=True)
        for c in range(2):
            grid.grid_columnconfigure(c, weight=1)

        self._cards = []
        self._row, self._col = 0, 0
        self._add_card(grid, "配置地址", full=True, cb=self._edit_api)
        self._add_card(grid, "配置历史", full=True, cb=self._pick_hist)
        self._add_card(grid, "首页站源", cb=self._goto_grid)
        self._add_card(grid, "首页推荐", cb=self._pick_home_rec)
        self._add_card(grid, "解码方式", cb=self._pick_codec)
        self._add_card(grid, "画面缩放", cb=self._pick_scale)
        self._add_card(grid, "历史上限", cb=self._pick_his_num)
        self._add_card(grid, "下次进入", cb=self._toggle_home_page)
        self._add_card(grid, "清空缓存", cb=self._clear_cache)
        self._add_card(grid, "关于", cb=self._show_about)
        self._refresh_values()
        if self._cards:
            self._cards[0].focus_set()
        # 方向键导航（2 列）
        from .theme import grid_key_nav
        grid_key_nav(self._cards, 2, up_down_rows=1)

    # ------------------------------------------------ 卡片构建 ----
    def _add_card(self, grid, name, full=False, cb=None):
        var = tk.StringVar(value=name)
        if full:
            if self._col:  # 半宽行未满时先换行，通栏独占一行
                self._row, self._col = self._row + 1, 0
            card = FocusLabel(grid, textvariable=var, bg=PANEL, fg=FG,
                              font=tv_font(13, True), padx=18, pady=14,
                              anchor="w", on_select=cb)
            card.grid(row=self._row, column=0, columnspan=2,
                      sticky="ew", padx=24, pady=5)
            self._row += 1
        else:
            card = FocusLabel(grid, textvariable=var, bg=PANEL, fg=FG,
                              font=tv_font(13, True), padx=18, pady=14,
                              anchor="w", on_select=cb)
            card.grid(row=self._row, column=self._col, sticky="ew",
                      padx=(24, 8) if self._col == 0 else (8, 24), pady=5)
            self._col += 1
            if self._col == 2:
                self._row, self._col = self._row + 1, 0
        card._var, card._name = var, name
        self._cards.append(card)
        self._vars[name] = var
        return card

    def _set_value(self, name, value):
        if name in self._vars:
            self._vars[name].set(f"{name}　　{value}　›" if value else f"{name}　　›")

    def _refresh_values(self):
        api = hawk.get(hawk.HOME_API, DEFAULT_API)
        self._set_value("配置地址", self._short(api))
        hist = hawk.get(hawk.API_HISTORY, []) or []
        self._set_value("配置历史", f"{len(hist)} 条" if hist else "")
        self._set_value("首页站源", self._home_source_name())
        self._set_value("首页推荐", HOME_REC_NAMES.get(self._home_rec(),
                                                       HOME_REC_NAMES[1]))
        try:
            scale = int(hawk.get(hawk.PLAY_SCALE, 0))
        except (TypeError, ValueError):
            scale = 0
        self._set_value("画面缩放", SCALE_NAMES.get(scale, "默认"))
        self._set_value("解码方式",
                        "软解码" if hawk.get(hawk.IJK_CODEC, "硬解码") == "软解码"
                        else "硬解码")
        try:
            hn = int(hawk.get(hawk.HISTORY_NUM, 0))
        except (TypeError, ValueError):
            hn = 0
        self._set_value("历史上限",
                        f"{HIS_NUM_ARRAY[hn]} 条" if 0 <= hn < 3 else "30 条")
        self._set_value("下次进入", "直播" if self._home_page() == "live" else "点播")
        self._set_value("关于", f"v{VERSION}")

    @staticmethod
    def _short(url, n=44):
        return url if len(url) <= n else url[:n] + "…"

    @staticmethod
    def _home_source_name():
        key = hawk.get(hawk.HOME_SOURCE)
        bean = api_config.get(key) if key else None
        return bean.name if bean else ""

    @staticmethod
    def _home_page():
        return hawk.get("home_page", "vod") or "vod"

    @staticmethod
    def _home_rec():
        """首页推荐类型：0 豆瓣热播 / 1 站点推荐 / 2 观看历史"""
        try:
            return int(hawk.get(hawk.HOME_REC, hawk.DEFAULT_HOME_REC))
        except (TypeError, ValueError):
            return hawk.DEFAULT_HOME_REC

    # ------------------------------------------------ 功能动作 ----
    def _edit_api(self):
        self._dialog("配置地址", hawk.get(hawk.HOME_API, DEFAULT_API),
                     self._load_api)

    def _load_api(self, url):
        url = (url or "").strip()
        if not url:
            self.status.configure(text="请输入接口地址")
            return
        self.status.configure(text=f"正在加载 {url} ...")

        def ok():
            def apply():
                from . import data_api
                data_api.clear_caches()
                hawk.delete(hawk.HOME_SOURCE)
                first = api_config.source_key_list[0] if api_config.source_key_list else ""
                hawk.put(hawk.HOME_SOURCE, first)
                self.status.configure(text="配置加载成功，正在返回主页…")
                self._refresh_values()
                self.app.go_home()
            ui_thread.run(apply)
        api_config.load(url, ok_cb=ok)

    def _pick_hist(self):
        urls = hawk.get(hawk.API_HISTORY, []) or []
        if not urls:
            self.status.configure(text="暂无配置历史")
            return
        self._list_dialog("配置历史", urls, self._load_api)

    def _goto_grid(self):
        # 首页站源在主页「切换源」里管理，此处快捷进入点播页
        from .ui_grid import Page as GridPage
        self.app.switch(GridPage)

    def _pick_home_rec(self):
        """首页推荐选择（对应 ModelSettingFragment llHomeRec → SelectDialog）"""
        cur = self._home_rec()
        self._select_dialog("请选择首页列表数据",
                            [(v, HOME_REC_NAMES[v]) for v in (0, 1, 2)],
                            cur, self._apply_home_rec)

    def _apply_home_rec(self, value):
        hawk.put(hawk.HOME_REC, value)
        self._refresh_values()
        self.status.configure(text=f"首页推荐已切换为「{HOME_REC_NAMES[value]}」，"
                                   f"返回主页即可看到效果")
        # 立刻回主页让用户看到效果（对应原版 Hawk 改动后首页重刷）
        self.after(260, self.app.go_home)

    def _pick_codec(self):
        """解码方式（对应 llMediaCodec → IJK_CODEC，映射 mpv hwdec）"""
        cur = 0 if hawk.get(hawk.IJK_CODEC, "硬解码") != "软解码" else 1
        self._select_dialog("请选择解码方式",
                            list(enumerate(CODEC_NAMES)),
                            cur, self._apply_codec)

    def _apply_codec(self, value):
        hawk.put(hawk.IJK_CODEC, CODEC_NAMES[value])
        self._refresh_values()
        self.status.configure(text=f"解码方式已切换为「{CODEC_NAMES[value]}」，"
                                   f"下次播放生效")

    def _pick_scale(self):
        """画面缩放（对应 llScale → PLAY_SCALE）"""
        try:
            cur = int(hawk.get(hawk.PLAY_SCALE, 0))
        except (TypeError, ValueError):
            cur = 0
        if cur not in SCALE_NAMES:
            cur = 0
        self._select_dialog("请选择默认画面缩放",
                            [(v, SCALE_NAMES[v]) for v in sorted(SCALE_NAMES)],
                            cur, self._apply_scale)

    def _apply_scale(self, value):
        hawk.put(hawk.PLAY_SCALE, value)
        self._refresh_values()
        self.status.configure(text=f"画面缩放已切换为「{SCALE_NAMES[value]}」，"
                                   f"下次播放生效")

    def _pick_his_num(self):
        """历史记录上限（对应 llHistoryNum → HISTORY_NUM）"""
        try:
            cur = int(hawk.get(hawk.HISTORY_NUM, 0))
        except (TypeError, ValueError):
            cur = 0
        if cur not in (0, 1, 2):
            cur = 0
        self._select_dialog("保留历史记录数量",
                            [(v, f"{HIS_NUM_ARRAY[v]} 条") for v in (0, 1, 2)],
                            cur, self._apply_his_num)

    def _apply_his_num(self, value):
        hawk.put(hawk.HISTORY_NUM, value)
        self._refresh_values()
        self.status.configure(text=f"历史记录最多保留 {HIS_NUM_ARRAY[value]} 条，"
                                   f"超出部分自动清理")

    def _toggle_home_page(self):
        cur = self._home_page()
        hawk.put("home_page", "vod" if cur == "live" else "live")
        self._refresh_values()
        self.status.configure(text="下次进入将打开 " +
                              ("直播" if cur != "live" else "点播"))

    def _clear_cache(self):
        try:
            from . import data_api
            data_api.clear_caches()
        except Exception:
            pass
        from .paths import data_path
        cache_dir = data_path(".spider_cache")
        try:
            if os.path.isdir(cache_dir):
                shutil.rmtree(cache_dir)
        except Exception:
            pass
        self.status.configure(text="缓存已清空（配置/分类缓存 + 爬虫缓存）")

    def _show_about(self):
        n_sites = len(api_config.source_bean_list)
        n_lives = len(api_config.lives)
        self._info_dialog("关于", (
            f"TVBox4Win v{VERSION}（Python + tkinter + libmpv）\n"
            f"当前配置：{n_sites} 个点播源 · {n_lives} 个直播源\n"
            f"功能：点播(CMS/Spider/py) · 直播 · 搜索 · 历史收藏 · 推送 · 设置"))

    # ------------------------------------------------ 弹窗 ----
    def _dialog(self, title, value, on_ok):
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text=title, bg=BG, fg=FG, font=tv_font(14, True)
                 ).pack(padx=20, pady=(14, 6), anchor="w")
        ent = tk.Entry(win, bg=PANEL, fg=FG, width=64, font=("Consolas", 11),
                       insertbackground=FG, highlightthickness=1,
                       highlightbackground="#333")
        ent.insert(0, value)
        ent.pack(padx=20, pady=4)
        ent.selection_range(0, "end")
        ent.focus_set()

        def confirm(_e=None):
            win.destroy()
            on_ok(ent.get())
        ent.bind("<Return>", confirm)
        FocusLabel(win, text="确定", font=tv_font(12, True), bg=FOCUS_BG,
                   fg=FOCUS_FG, on_select=confirm).pack(pady=(8, 14))
        win.bind("<Escape>", lambda e: win.destroy())

    def _list_dialog(self, title, items, on_pick):
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text=title, bg=BG, fg=FG, font=tv_font(14, True)
                 ).pack(padx=20, pady=(14, 6), anchor="w")
        box = tk.Listbox(win, bg=PANEL, fg=FG, width=70, height=min(8, len(items)),
                         font=("Consolas", 10), highlightthickness=1,
                         highlightbackground="#333", selectbackground=ACCENT)
        for it in items:
            box.insert("end", it)
        box.pack(padx=20, pady=4)
        box.focus_set()

        def pick(_e=None):
            sel = box.curselection()
            if sel:
                win.destroy()
                on_pick(box.get(sel[0]))
        box.bind("<Return>", pick)
        box.bind("<Double-Button-1>", pick)
        win.bind("<Escape>", lambda e: win.destroy())

    def _select_dialog(self, tip, options, current, on_pick):
        """单选弹窗（对应 SelectDialog：竖排选项，当前项高亮，方向键选择）"""
        win = tk.Toplevel(self)
        win.title(tip)
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text=tip, bg=BG, fg=FG, font=tv_font(14, True)
                 ).pack(padx=26, pady=(16, 8), anchor="w")
        box = tk.Frame(win, bg=BG)
        box.pack(fill="both", expand=True, padx=26, pady=(0, 16))
        btns = []
        focus_first = None
        for val, name in options:
            on = val == current
            b = FocusLabel(box, text=("● " if on else "　") + name,
                           bg=ACCENT if on else PANEL,
                           fg="#FFFFFF" if on else FG, font=tv_font(13, on),
                           padx=18, pady=10, anchor="w",
                           on_select=lambda v=val: (win.destroy(), on_pick(v)))
            b.pack(fill="x", pady=4)
            btns.append(b)
            if on and focus_first is None:
                focus_first = b
        if focus_first is not None:  # 焦点停在当前选中项（对应原版 defaultPos）
            focus_first.focus_set()
        elif btns:
            btns[0].focus_set()
        from .theme import grid_key_nav
        grid_key_nav(btns, 1, up_down_rows=1)
        win.bind("<Escape>", lambda e: win.destroy())

    def _info_dialog(self, title, text):
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text=text, bg=BG, fg=FG, font=tv_font(12),
                 justify="left").pack(padx=24, pady=20)
        FocusLabel(win, text="关闭", font=tv_font(12, True),
                   on_select=win.destroy).pack(pady=(0, 14))
