"""点播页 GridFragment 复刻（首页+点播合并页）：源名+日期 / 主页tab+分类tab /
功能按钮排 / 内容区（主页 tab=豆瓣热播海报，分类 tab=影片网格）"""
import datetime
import tkinter as tk
from . import ui_thread, imgcache

import requests

from . import apiconfig, hawk
from .theme import BG, FG, FG_DIM, ACCENT, FOCUS_BG, FOCUS_FG, FocusLabel, tv_font, PANEL, POSTER_BG
from . import data_api

MENU = [
    ("历史", "ui_history", "🕘"),
    ("直播", "ui_live", "📺"),
    ("搜索", "ui_search", "🔍"),
    ("推送", "ui_push", "⚡"),
    ("收藏", "ui_collect", "♡"),
    ("设置", "ui_setting", "⚙"),
]

_WEEK = "一二三四五六日"


class Page(tk.Frame):
    """对应 ui/fragment/GridFragment.java"""

    def __init__(self, master, app, source_key=None):
        super().__init__(master, bg=BG)
        self.app = app
        self.source_key = source_key or hawk.get(hawk.HOME_SOURCE)
        self.bean = apiconfig.api_config.get(self.source_key) if self.source_key else None
        if self.bean is None and apiconfig.api_config.source_bean_list:
            # 记录里的站源在本次配置中已不存在（配置换了/源被删）→ 回落第一个可用站点，
            # 否则整页空白（对应原版 getHomeSourceBean 空时刷新首页）
            self.bean = apiconfig.api_config.source_bean_list[0]
            self.source_key = self.bean.key
            hawk.put(hawk.HOME_SOURCE, self.source_key)
        self.classes = []      # [(type_id, type_name)]
        self.vods = []         # [(vod_id, vod_name, vod_pic, vod_remarks)]
        self.page_index = 1
        self.page_count = 1
        self.cur_class = None
        self.filter_sel = {}   # 当前筛选条件 {key: value}

        # 顶部：返回 + 源名 + 日期（右侧，对应原版合并页顶栏）
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", pady=(8, 2))
        back = FocusLabel(top, text="←", font=tv_font(14, True),
                          on_select=self._back_home_tab)
        back.pack(side="left", padx=(20, 6))
        tk.Label(top, text=self.bean.name if self.bean else "?",
                 bg=BG, fg=ACCENT, font=tv_font(16, True)).pack(side="left")
        self.clock = tk.Label(top, text="", bg=BG, fg=FG, font=tv_font(14, True))
        self.clock.pack(side="right", padx=20)
        self._tick()
        # 切换已加载源（对应原版首页站点切换）
        FocusLabel(top, text="▾ 切换源", bg=PANEL, fg=FG, font=tv_font(12),
                   on_select=self._show_sources).pack(side="right", padx=16)
        self.tabs_bar = tk.Frame(self, bg=BG)
        self.tabs_bar.pack(fill="x", padx=16, pady=4)
        # 筛选入口（有筛选器的分类才显示，对应 showFilter 按钮）
        self.status_filter = tk.Label(self.tabs_bar, text="", bg=BG, fg=FG_DIM,
                                      font=tv_font(10))
        self.status_filter.pack(side="right", padx=6)
        self.filter_btn = FocusLabel(self.tabs_bar, text="⚙ 筛选", bg=PANEL, fg=FG,
                                     font=tv_font(11),
                                     on_select=self._show_filter)
        self.filter_btn.pack(side="right", padx=4)
        self.filter_btn.pack_forget()  # 默认隐藏，分类加载后按需显示

        # 功能按钮排（对应原版合并页：历史/直播/搜索/推送/收藏/设置 一横排）
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=20, pady=(2, 4))
        self._menu_btns = []
        for name, target, icon in MENU:
            b = FocusLabel(row, text=f"{icon} {name}", bg=PANEL, fg=FG,
                           font=tv_font(14, True), padx=22, pady=10,
                           on_select=lambda t=target: self._go_menu(t))
            b.pack(side="left", padx=(0, 10))
            self._menu_btns.append(b)
        for b in self._menu_btns:  # 横排左右导航
            b.bind("<Right>", lambda e, bs=self._menu_btns: self._nav(e, bs, 1))
            b.bind("<Left>", lambda e, bs=self._menu_btns: self._nav(e, bs, -1))

        # 网格（海报占位 + 名称 + 备注）
        self.grid_frame = tk.Frame(self, bg=BG)
        self.grid_frame.pack(fill="both", expand=True, padx=16)
        self.canvas = tk.Canvas(self.grid_frame, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(self.grid_frame, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        def _wheel(e):
            try:
                self.canvas.yview_scroll(-e.delta // 120, "units")
            except tk.TclError:
                pass
        self.canvas.bind_all("<MouseWheel>", _wheel)

        self._seq = 0
        self._prio = 0  # 海报下载优先级：当前内容区=0，推荐位=2
        self._load_classes()
        self._reload_grid()  # 默认「主页」tab：加载豆瓣热播

    # ---------- 数据 ----------
    def _show_sources(self):
        """弹出源选择面板：列出当前配置里所有可用站点，点选即切换"""
        from .apiconfig import api_config
        panel = tk.Toplevel(self)
        panel.title("切换源")
        panel.configure(bg=BG)
        panel.transient(self.winfo_toplevel())
        panel.geometry("900x520")
        tk.Label(panel, text="选择站点", bg=BG, fg=FG,
                 font=tv_font(15, True)).pack(pady=(12, 6))
        body = tk.Frame(panel, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _wheel(e):
            try:
                canvas.yview_scroll(-e.delta // 120, "units")
            except tk.TclError:
                pass
        canvas.bind_all("<MouseWheel>", _wheel)
        panel.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>")
                   if e.widget is panel else None)

        beans = [b for b in api_config.source_bean_list if b.name and b.api]
        cols = 4
        first = None
        for i, b in enumerate(beans):
            cur = b.key == self.source_key
            btn = FocusLabel(inner,
                             text=("● " if cur else "") + b.name[:16],
                             bg=ACCENT if cur else PANEL,
                             fg="#FFFFFF" if cur else FG,
                             font=tv_font(12, cur),
                             on_select=lambda bb=b, p=panel: self._switch_source(bb, p))
            btn.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="ew")
            if first is None:
                first = btn
        if first:
            first.focus_set()

    def _switch_source(self, bean, panel):
        if bean.key == self.source_key:
            panel.destroy()
            return
        hawk.put(hawk.HOME_SOURCE, bean.key)
        panel.destroy()
        self.app.switch(Page, source_key=bean.key)

    def _load_classes(self):
        def run():
            self.load_err = None
            if self.bean is None:
                self.classes = []
                self.load_err = "未选择首页站源，请在「切换源」里选一个站点"
                ui_thread.run(self._render_tabs)
                return
            try:
                self.classes = data_api.get_classes(self.bean)
            except Exception as ex:
                self.classes = []
                self.load_err = str(ex)
                from .paths import log_error
                log_error("get_classes 失败 bean=%s api=%s" %
                          (self.bean.name, self.bean.api), ex)
            # 后台预取筛选器（避免 UI 线程网络请求）
            try:
                data_api.get_filters(self.bean)
            except Exception:
                pass
            ui_thread.run(self._render_tabs)
        import threading
        threading.Thread(target=run, daemon=True).start()

    def _render_tabs(self):
        if not self.winfo_exists():
            return
        if not self.classes:
            # 分类加载失败：显示重试
            for w in self.tabs_bar.winfo_children():
                w.destroy()
            FocusLabel(self.tabs_bar, text="⚠ 分类加载失败，点击重试" +
                       ("：" + self.load_err[:60] if getattr(self, "load_err", None) else ""),
                       bg="#3a1010", fg=FG, font=tv_font(12),
                       on_select=self._retry).pack(side="left", padx=10, pady=2)
            self._show_grid_error()
            return
        for w in self.tabs_bar.winfo_children():
            w.destroy()
        items = [("主页", None)]
        items += [(name, cid) for cid, name in self.classes]
        tab_btns = []
        self._tab_map = []  # [(cid, FocusLabel)]
        holder = tk.Frame(self.tabs_bar, bg=BG)
        holder.pack(side="left")
        for name, cid in items:
            b = FocusLabel(holder, text=name, bg=PANEL, fg=FG, font=tv_font(12),
                           on_select=lambda c=cid: self.select_class(c))
            b.pack(side="left", padx=4, pady=2)
            tab_btns.append(b)
            self._tab_map.append((cid, b))
        if tab_btns:
            tab_btns[0].focus_set()
        # 默认停在「主页」tab（对应原版合并页：进源即显示豆瓣热播）

    def select_class(self, class_id, auto=False):
        self._auto = auto
        self.cur_class = class_id
        self.page_index = 1
        self.vods = []
        self.filter_sel = {}   # 筛选条件 {key: value}（切分类重置）
        # 有筛选器的分类显示筛选按钮（只读缓存，筛选器已在后台预取）
        key = f"{self.bean.key}:{self.bean.api}"
        cached = data_api._filters_cache.get(key, {})
        has_filter = bool(cached.get(str(class_id))) if class_id else False
        if hasattr(self, "filter_btn"):
            try:
                if has_filter and self.filter_btn.winfo_exists():
                    self.filter_btn.pack(side="right", padx=4)
                elif self.filter_btn.winfo_exists():
                    self.filter_btn.pack_forget()
            except tk.TclError:
                pass  # widget 已随页面销毁
        # 切 tab 后重渲染 tab 高亮（主页/分类胶囊）
        try:
            self._render_tabs_hl()
        except Exception:
            pass
        self._reload_grid()

    def _render_tabs_hl(self):
        """仅刷新 tab 高亮（保留焦点），对应原版当前分类蓝胶囊"""
        if not getattr(self, "winfo_exists", None) or not self.winfo_exists():
            return
        for cid, b in getattr(self, "_tab_map", []):
            if not b.winfo_exists():
                continue
            cur = cid == self.cur_class
            b.configure(bg=FOCUS_BG if cur else PANEL,
                        fg=FOCUS_FG if cur else FG)

    def _show_filter(self):
        """筛选面板（对应 GridFragment.showFilter）"""
        filters = data_api.get_filters(self.bean).get(str(self.cur_class)) or []
        if not filters:
            self.status_filter.configure(text="该分类无筛选")
            return
        self.status_filter.configure(text="")
        panel = tk.Toplevel(self)
        panel.title("筛选")
        panel.configure(bg=BG)
        panel.transient(self.winfo_toplevel())
        panel.geometry("760x480")
        tk.Label(panel, text="筛选", bg=BG, fg=FG,
                 font=tv_font(14, True)).pack(pady=(10, 4))
        body = tk.Frame(panel, bg=BG)
        body.pack(fill="both", expand=True, padx=16)
        # sel: {key: value}（"全部"表示未选）；rows: {key: [chip,...]}
        sel = dict(self.filter_sel)
        rows = {}
        for f in filters:
            rowf = tk.Frame(body, bg=BG)
            rowf.pack(fill="x", pady=3)
            tk.Label(rowf, text=f["name"], bg=BG, fg=FG_DIM,
                     font=tv_font(11), width=6, anchor="w").pack(side="left")
            chips = []
            for v in ["全部"] + f["value"]:
                on = sel.get(f["key"], "") == v
                c = FocusLabel(rowf, text=v[:8], bg=ACCENT if on else PANEL,
                               fg="#FFFFFF" if on else FG, font=tv_font(10),
                               padx=6, pady=2)
                c.pack(side="left", padx=2)
                chips.append((c, v))

            def make_toggle(fkey=f["key"], chips=chips):
                def toggle(clicked, val):
                    sel[fkey] = "" if val == "全部" else val
                    for cc, vv in chips:
                        if cc.winfo_exists():
                            on = sel[fkey] == vv
                            cc.configure(bg=ACCENT if on else PANEL,
                                         fg="#FFFFFF" if on else FG)
                return toggle
            toggle = make_toggle()
            for c, v in chips:
                c.configure(on_select=lambda c=c, v=v, t=toggle: t(c, v))
            rows[f["key"]] = chips

        def apply():
            self.filter_sel = {k: v for k, v in sel.items() if v}
            panel.destroy()
            self.page_index = 1
            self._reload_grid()

        FocusLabel(panel, text="应用筛选", bg=ACCENT, fg="#FFFFFF",
                   font=tv_font(12, True), on_select=apply).pack(pady=8)

    def _retry(self):
        self._load_classes()

    def _show_grid_error(self, msg="内容加载失败，请检查网络后重试"):
        for w in self.inner.winfo_children():
            w.destroy()
        box = tk.Frame(self.inner, bg=BG)
        box.grid(row=0, column=0, padx=40, pady=60)
        tk.Label(box, text=msg, bg=BG, fg=FG_DIM, font=tv_font(13)).pack(pady=(0, 12))
        FocusLabel(box, text="⟳ 重试", bg=PANEL, fg=FG, font=tv_font(12),
                   on_select=lambda: (self._load_classes(),
                                      self.select_class(None) if self.classes else None)
                   ).pack()

    def _reload_grid(self):
        try:
            alive = self.winfo_exists()
        except tk.TclError:
            alive = False
        if not alive:
            return
        if self.cur_class is None:
            # 「主页」tab：按 设置 › 首页推荐 渲染（豆瓣热播/站点推荐/观看历史）
            for w in self.inner.winfo_children():
                w.destroy()
            tk.Label(self.inner, text="加载中...", bg=BG, fg=FG_DIM,
                     font=tv_font(12)).grid(row=0, column=0, padx=10, pady=20)
            self.after(200, self._load_home_tab)
            return
        for w in self.inner.winfo_children():
            w.destroy()
        tk.Label(self.inner, text="加载中...", bg=BG, fg=FG_DIM,
                 font=tv_font(12)).grid(row=0, column=0, padx=10, pady=20)

        def run():
            try:
                result = data_api.get_vods(self.bean, self.cur_class,
                                           self.page_index, self.filter_sel or None)
                if not result[0]:  # 偶发网络失败，重试一次
                    result = data_api.get_vods(self.bean, self.cur_class,
                                               self.page_index, self.filter_sel or None)
            except Exception as ex:
                from .paths import log_error
                log_error("get_vods 失败 bean=%s class=%s" %
                          (self.bean.name, self.cur_class), ex)
                result = ([], self.page_index, 1)
            ui_thread.run(lambda: self._render_grid(*result))
        import threading
        threading.Thread(target=run, daemon=True).start()

    def _render_grid(self, vods, page, pagecount):
        if not self.winfo_exists():
            return
        self._prio = 0
        self.vods = vods
        self.page_index, self.page_count = page, pagecount
        # 首个自动选中的分类若无内容，自动尝试下一个分类（源数据漂移兜底；
        # 首页 tab 无内容时落到第一个真实分类，对应原版进入源即展示内容）
        if not vods and self._auto and self.classes:
            ids = [c[0] for c in self.classes]
            if self.cur_class is None:
                self.select_class(ids[0], auto=True)
                return
            if self.cur_class in ids and ids.index(self.cur_class) < len(ids) - 1:
                self.select_class(ids[ids.index(self.cur_class) + 1], auto=True)
                return
        self._auto = False
        for w in self.inner.winfo_children():
            w.destroy()
        if not vods:
            tk.Label(self.inner, text="暂无内容", bg=BG, fg=FG_DIM,
                     font=tv_font(13)).grid(row=0, column=0, padx=20, pady=20)
            return
        cols = 6
        btns = []
        for i, (vid, name, pic, remark) in enumerate(vods):
            cell = tk.Frame(self.inner, bg=BG, padx=6, pady=6)
            cell.grid(row=i // cols, column=i % cols)
            # 键盘焦点承载层（沉到海报底下，不遮挡图片）
            b = FocusLabel(cell, text="", bg=BG,
                           on_select=lambda v=vid, n=name: self._open_detail(v, n))
            poster = tk.Label(cell, text=(name[:1] or "🎬"), width=13, height=7,
                              bg=POSTER_BG, fg="#4A5578", font=tv_font(26))
            poster.pack()
            tk.Label(cell, text=name[:12], bg=BG, fg=FG,
                     font=tv_font(11)).pack()
            tk.Label(cell, text=remark or "", bg=BG, fg=FG_DIM,
                     font=tv_font(9)).pack()
            b.place(in_=poster, relwidth=1.0, relheight=1.0)
            b.lower()  # 沉底：海报显示在最上层
            poster.bind("<Button-1>", lambda e, v=vid, n=name: self._open_detail(v, n))
            # 焦点时给海报描边（add=True 保留 FocusLabel 自身焦点逻辑）
            b.bind("<FocusIn>", lambda e, p=poster: p.configure(
                highlightthickness=2, highlightbackground=ACCENT), add="+")
            b.bind("<FocusOut>", lambda e, p=poster: p.configure(
                highlightthickness=0), add="+")
            btns.append(b)
            if pic:
                self._seq += 1
                self._load_poster(f"p{self._seq}", poster, pic)
        # 分页
        pager = tk.Frame(self.inner, bg=BG)
        pager.grid(row=(len(vods) + cols - 1) // cols + 1, column=0,
                   columnspan=cols, pady=14)
        if self.page_index < self.page_count:
            FocusLabel(pager, text="下一页 ▶", bg=PANEL, fg=FG, font=tv_font(12),
                       on_select=self._next_page).pack(side="left", padx=8)
        tk.Label(pager, text=f"{self.page_index}/{self.page_count}",
                 bg=BG, fg=FG_DIM, font=tv_font(11)).pack(side="left", padx=8)
        if btns:
            btns[0].focus_set()

    def _load_poster(self, key, poster, url):
        url, headers = imgcache.parse_pic(url)
        if not url.startswith("http"):
            return
        def on_ready(k, path):
            if not self.winfo_exists() or not poster.winfo_exists():
                imgcache.drop(k)
                return
            try:
                photo = imgcache.fit_photo(tk.PhotoImage(file=path))
            except tk.TclError:
                return
            imgcache.keep(k, photo)
            poster.configure(image=photo, text="", width=photo.width(),
                             height=photo.height())
        imgcache.load(key, url, on_ready, headers, priority=self._prio)

    def _next_page(self):
        self.page_index += 1
        self._reload_grid()

    def _open_detail(self, vod_id, vod_name):
        if str(vod_id).startswith("msearch:"):
            # 对应原版 GridFragment：豆瓣类源 msearch 影片 → 跳搜索页搜片名
            # （FastSearchActivity / SearchActivity 语义）
            try:
                from .ui_search import Page as SearchPage
                wd = vod_id.split("###")
                wd = wd[1] if len(wd) > 1 else vod_name
                self.app.switch(SearchPage, pre_key=None)
                page = self.app.current
                page.kw.delete(0, "end")
                page.kw.insert(0, wd)
                page.do_search()
                return
            except Exception:
                pass
        from .ui_detail import Page as DetailPage
        self.app.switch(DetailPage, source_key=self.source_key,
                        vod_id=vod_id, vod_name=vod_name)

    # ---------- 合并主页：日期 / 功能菜单 / 豆瓣热播 ----------
    def _back_home_tab(self):
        """← 返回主页 tab（合并页内回首页内容区）"""
        if self.cur_class is not None:
            self.select_class(None)
        else:
            self._menu_btns[0].focus_set() if self._menu_btns else None

    @staticmethod
    def _nav(e, widgets, step):
        try:
            idx = widgets.index(e.widget) + step
        except ValueError:
            return
        if 0 <= idx < len(widgets):
            widgets[idx].focus_set()
            return "break"

    def _go_menu(self, target):
        try:
            mod = __import__(f"tvboxosc.{target}", fromlist=["*"])
            page = getattr(mod, "Page")
        except (ImportError, AttributeError):
            return
        self.app.switch(page)

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

    # ---------- 首页 tab 内容区：推荐位（对应 UserFragment 首页推荐）----------
    def _home_rec_mode(self):
        """首页推荐类型 0 豆瓣热播 / 1 站点推荐 / 2 观看历史（HawkConfig.HOME_REC）"""
        try:
            return int(hawk.get(hawk.HOME_REC, hawk.DEFAULT_HOME_REC))
        except (TypeError, ValueError):
            return hawk.DEFAULT_HOME_REC

    def _load_home_tab(self):
        try:
            if not self.winfo_exists() or self.cur_class is not None:
                return
        except tk.TclError:
            return
        mode = self._home_rec_mode()
        if mode == 2:
            self._load_home_history()
        elif mode == 1:
            self._load_site_rec()
        else:
            self._load_recommend()

    def _load_site_rec(self):
        """站点推荐：首页站源自带推荐列表

        对应 UserFragment.homeSourceRec ← SourceViewModel.getSort(homeKey) 的
        videoList（spider 走 homeVideoContent，CMS 走首页 ac=videolist 列表）
        """
        def run():
            items = []
            try:
                vods, _, _ = data_api.get_vods(self.bean, None, 1)
                items = [(n, p, r, v, self.source_key)
                         for v, n, p, r in vods if n][:24]
            except Exception as ex:
                from .paths import log_error
                log_error("首页站点推荐失败 bean=%s" %
                          (self.bean.name if self.bean else "?"), ex)
            if items:
                ui_thread.run(lambda: self._render_home_items(
                    "站点推荐", items, "site"))
            else:
                # 该源没有推荐数据 → 回落豆瓣热播（对应原版 homeSourceRec==null）
                self._load_recommend()
        import threading
        threading.Thread(target=run, daemon=True).start()

    def _load_home_history(self):
        """观看历史：本地播放记录前 24 条

        对应 UserFragment HOME_REC==2 → RoomDataManger.getAllVodRecord(20)，
        note 为「上次看到 xx」；长按（此处右键）删除记录。
        """
        from . import store
        try:
            recs = store.all_records(24)
        except Exception as ex:
            from .paths import log_error
            log_error("读取观看历史失败", ex)
            recs = []
        items = []
        for r in recs:
            src = apiconfig.api_config.get(r["source_key"])
            src_name = src.name if src else ""
            ep = r.get("play_ep") or ""
            note = f"上次看到 {ep}" if ep else ""
            if note and src_name:
                note = f"{src_name} · {note}"
            elif not note:
                note = src_name
            items.append((r["vod_name"], r.get("vod_pic") or "", note,
                          r["vod_id"], r["source_key"]))
        self._render_home_items("观看历史", items, "history")

    def _load_recommend(self):
        """豆瓣热播（对应 UserFragment.setDouBanData，按天缓存；失败静默）"""
        def run():
            today = datetime.date.today().isoformat()
            cache = hawk.get("douban_rec_day", None)
            items = None
            if cache and cache.get("day") == today:
                items = cache.get("items")
            if not items:
                try:
                    r = requests.get(
                        "https://movie.douban.com/j/search_subjects",
                        params={"type": "movie", "tag": "热门", "page_limit": 12,
                                "page": 1},
                        timeout=8, verify=False,
                        headers={"User-Agent": "Mozilla/5.0"})
                    data = r.json()
                    items = [(s.get("title", ""), s.get("cover", ""),
                              s.get("rate", ""))
                             for s in data.get("subjects", [])][:12]
                except Exception:
                    items = None
                if items:
                    hawk.put("douban_rec_day", {"day": today, "items": items})
            if items:
                ui_thread.run(lambda: self._render_home_items(
                    "豆瓣热播",
                    [(n, c, (f"评分 {rt}" if rt else ""), None, None)
                     for n, c, rt in items], "douban"))
            else:
                ui_thread.run(lambda: self._render_home_items(
                    "豆瓣热播", [], "douban"))
        import threading
        threading.Thread(target=run, daemon=True).start()

    def _render_home_items(self, header, items, kind):
        """首页推荐位渲染（kind：douban 豆瓣热播 / site 站点推荐 / history 观看历史）"""
        if not self.winfo_exists():
            return
        self._prio = 2  # 推荐位让路给网格/详情海报
        for w in self.inner.winfo_children():
            w.destroy()
        cols = 6
        head = tk.Frame(self.inner, bg=BG)
        head.grid(row=0, column=0, columnspan=cols, sticky="ew", pady=(4, 10))
        tk.Label(head, text=header, bg=BG, fg=ACCENT,
                 font=tv_font(14, True)).pack(side="left", padx=(4, 0))
        hint = {"douban": "点击海报 → 全源搜索播放",
                "site": "点击海报 → 影片详情",
                "history": "点击继续观看 · 右键删除记录"}.get(kind, "")
        if hint:
            tk.Label(head, text="　" + hint, bg=BG, fg=FG_DIM,
                     font=tv_font(10)).pack(side="left")
        # 按钮放左侧：内容区总宽可能超出视口，放右侧会被截掉
        FocusLabel(head, text="　⚙ 更换推荐", bg=PANEL, fg=FG, font=tv_font(10),
                   padx=10, pady=4,
                   on_select=self._open_rec_setting).pack(side="left")
        if not items:
            msg = ("还没有观看记录：点开一部影片开始播放后，就会出现在这里"
                   if kind == "history"
                   else "该源暂无推荐内容，可到「设置 › 首页推荐」切换其它类型")
            box = tk.Frame(self.inner, bg=BG)
            box.grid(row=1, column=0, columnspan=cols, pady=40)
            tk.Label(box, text=msg, bg=BG, fg=FG_DIM,
                     font=tv_font(12)).pack(pady=(0, 10))
            if kind == "history":
                FocusLabel(box, text="去分类里看看", bg=ACCENT, fg="#FFFFFF",
                           font=tv_font(12, True),
                           on_select=self._goto_first_class).pack()
            return
        btns = []
        for i, it in enumerate(items):
            name, pic, note = it[0], it[1], it[2]
            vod_id = it[3] if len(it) > 3 else None
            src_key = it[4] if len(it) > 4 else None
            cell = tk.Frame(self.inner, bg=BG, padx=6, pady=6)
            cell.grid(row=1 + i // cols, column=i % cols)
            b = FocusLabel(cell, text="", bg=BG,
                           on_select=lambda n=name, v=vod_id, s=src_key:
                           self._open_rec_item(kind, n, v, s))
            poster = tk.Label(cell, text=(name[:1] or "🎬"), width=11, height=6,
                              bg=POSTER_BG, fg="#4A5578", font=tv_font(22))
            poster.pack()
            tk.Label(cell, text=name[:12], bg=BG, fg=FG, font=tv_font(11),
                     width=11).pack()
            tk.Label(cell, text=(note or ""), bg=BG, fg=FG_DIM, font=tv_font(9),
                     wraplength=104, justify="center", width=11).pack()
            b.place(in_=poster, relwidth=1.0, relheight=1.0)
            b.lower()
            click = (lambda e, n=name, v=vod_id, s=src_key:
                     self._open_rec_item(kind, n, v, s))
            for w in (poster, cell):
                w.bind("<Button-1>", click)
            if kind == "history":
                dele = (lambda e, n=name, v=vod_id, s=src_key:
                        self._delete_history(n, v, s))
                for w in (poster, cell):
                    w.bind("<Button-3>", dele)
            b.bind("<FocusIn>", lambda e, p=poster: p.configure(
                highlightthickness=2, highlightbackground=ACCENT), add="+")
            b.bind("<FocusOut>", lambda e, p=poster: p.configure(
                highlightthickness=0), add="+")
            btns.append(b)
            if pic:
                self._seq += 1
                self._load_poster(f"rec{self._seq}", poster, pic)
        if btns:
            btns[0].focus_set()
        from .theme import grid_key_nav
        grid_key_nav(btns, cols)

    # ---------- 推荐位交互 ----------
    def _open_rec_item(self, kind, name, vod_id, src_key):
        """点击推荐海报：豆瓣→跨源搜索；站点/历史→详情（msearch 仍走搜索）"""
        if kind == "douban" or not vod_id:
            self._search_name(name)
            return
        if str(vod_id).startswith("msearch:"):
            self._search_name(name)
            return
        from .ui_detail import Page as DetailPage
        self.app.switch(DetailPage, source_key=src_key or self.source_key,
                        vod_id=vod_id, vod_name=name)

    def _delete_history(self, name, vod_id, src_key):
        """删除一条观看记录（对应原版长按删除模式）"""
        from . import store
        try:
            store.delete_record(vod_id, src_key)
        except Exception as ex:
            from .paths import log_error
            log_error("删除观看历史失败", ex)
            return
        self._load_home_history()

    def _goto_first_class(self):
        if self.classes:
            self.select_class(self.classes[0][0])
        else:
            self._load_classes()

    def _open_rec_setting(self):
        from .ui_setting import Page as SettingPage
        self.app.switch(SettingPage)

    def _search_name(self, name):
        """点击豆瓣海报 → 跨源搜索片名（对应原版首页推荐点击）"""
        try:
            from .ui_search import Page as SearchPage
            self.app.switch(SearchPage, pre_key=None)
            page = self.app.current
            page.kw.delete(0, "end")
            page.kw.insert(0, name)
            page.do_search()
        except Exception:
            pass
