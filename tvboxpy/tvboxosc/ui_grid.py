"""点播页 GridFragment 复刻（首页+点播合并页）：源名+日期 / 主页tab+分类tab /
功能按钮排 / 内容区（主页 tab=豆瓣热播海报，分类 tab=影片网格）"""
import datetime
import os
import tkinter as tk
from . import ui_thread, imgcache

import requests

from . import apiconfig, hawk, poster_grid
from .theme import BG, FG, FG_DIM, ACCENT, FOCUS_BG, FOCUS_FG, FocusLabel, tv_font, PANEL
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


def _friendly_error(ex):
    """把爬虫异常转成一句话提示（原始异常仍写 error.log）"""
    text = str(ex or "")
    if "ClassNotFoundException" in text:
        return "该源爬虫类缺失（上游配置可能已失效），请换一个源"
    if "NullPointerException" in text and "Spider.init" in text:
        return "该源爬虫初始化失败，请换一个源"
    if "ConnectTimeout" in text or "Max retries" in text or "timed out" in text:
        return "网络连接超时，点击重试"
    if "spider 进程退出" in text or "JVM" in text:
        return "爬虫进程异常，点击重试"
    return text[:60]


class Page(tk.Frame):
    """对应 ui/fragment/GridFragment.java"""

    def __init__(self, master, app, source_key=None, restore_state=None):
        super().__init__(master, bg=BG)
        self.app = app
        self.source_key = source_key or hawk.get(hawk.HOME_SOURCE)
        self._restore_state = dict(restore_state or {})
        self._restore_pending = bool(self._restore_state)
        self._pending_scroll = self._restore_state.get("scroll", 0.0)
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
        FocusLabel(top, text="⟳ 刷新", bg=PANEL, fg=FG, font=tv_font(12),
                   on_select=self._refresh).pack(side="right", padx=(0, 6))
        self._folder_stack = []
        self._folder_title = ""
        # F5 刷新（绑顶层窗口，网格里焦点在按钮上也能收到）
        try:
            fid = self.app.bind("<F5>", lambda e: (self._refresh(), "break")[1],
                                add="+")
            self._app_binds = [("<F5>", fid)]
        except Exception:
            self._app_binds = []
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

        # 功能按钮排（对应原版合并页：历史/直播/搜索/推送/收藏/设置 一横排，
        # 原版是大按钮均分整行宽度）
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=16, pady=(2, 6))
        self._menu_btns = []
        for i, (name, target, icon) in enumerate(MENU):
            row.grid_columnconfigure(i, weight=1, uniform="menu")
            b = FocusLabel(row, text=f"{icon} {name}", bg=PANEL, fg=FG,
                           font=tv_font(15, True), pady=10,
                           on_select=lambda t=target: self._go_menu(t))
            b.grid(row=0, column=i, padx=4, sticky="ew")
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
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        # 内容区宽度跟随画布（否则列宽均分后 inner 仍按内容宽，右侧照样留白）
        self.canvas.bind("<Configure>", self._on_canvas_resize)
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
        self._request_seq = 0
        self._load_classes()
        self._reload_grid()  # 默认「主页」tab：加载豆瓣热播
        self.after(8000, self._slow_hint)   # 爬虫运行时启动慢时给出可见反馈

    def _slow_hint(self):
        """分类迟迟未回来时提示，避免「整页像卡死」"""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if self.classes or getattr(self, "load_err", None):
            return    # 已有结果或已报错，不再反复提示
        self.status_filter.configure(
            text="站点响应较慢，正在等待爬虫运行时…（可点「▾ 切换源」换一个）")
        self.after(8000, self._slow_hint)

    # ---------- 数据 ----------
    def _show_sources(self):
        """弹出源选择面板：列出当前配置里所有可用站点，点选即切换"""
        from .apiconfig import api_config
        # 防重入：面板已开着就把它提到前面，避免叠加多个面板
        old = getattr(self, "_src_panel", None)
        try:
            if old is not None and old.winfo_exists():
                old.lift()
                old.focus_force()
                return
        except tk.TclError:
            pass
        panel = tk.Toplevel(self)
        self._src_panel = panel
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
        # 绑在面板上（子控件事件会冒泡到 toplevel），不要用 bind_all：
        # 否则面板关闭时 unbind_all 会把主页的滚轮一起解绑
        panel.bind("<MouseWheel>", _wheel)

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
        if getattr(self, "_switching", False):   # 防重入：连点不会切两次
            return
        try:
            panel.destroy()
        except tk.TclError:
            pass
        self._src_panel = None
        if bean.key == self.source_key:
            return
        self._switching = True
        hawk.put(hawk.HOME_SOURCE, bean.key)
        try:
            # 切换源替换当前网格，不要把同页的旧源再压入返回栈。
            self.app.switch(Page, source_key=bean.key, push=False)
        finally:
            self._switching = False

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
                self.load_err = _friendly_error(ex)
                from .paths import log_error
                log_error("get_classes 失败 bean=%s api=%s" %
                          (self.bean.name, self.bean.api), ex)
            # 先渲染 tab，别让筛选器预取拖住分类显示
            ui_thread.run(self._render_tabs)
            # 后台预取筛选器（避免 UI 线程网络请求）；取回来后再决定是否显示筛选按钮
            try:
                data_api.get_filters(self.bean)
            except Exception:
                pass
            ui_thread.run(self._refresh_filter_btn)
        import threading
        threading.Thread(target=run, daemon=True).start()

    def _clear_tabs(self):
        """只清 tab 按钮区，保留「⚙ 筛选」按钮与右侧状态标签

        原来这里 `for w in self.tabs_bar.winfo_children(): w.destroy()` 会把
        status_filter / filter_btn 一并销毁 —— 首屏渲染后筛选入口就消失了，
        之后任何 configure 都会抛 TclError: invalid command name。
        """
        holder = getattr(self, "_tabs_holder", None)
        if holder is not None:
            try:
                holder.destroy()
            except tk.TclError:
                pass
        self._tabs_holder = None

    def _render_tabs(self):
        if not self.winfo_exists():
            return
        self._clear_tabs()
        if not self.classes:
            # 分类加载失败：显示重试
            holder = tk.Frame(self.tabs_bar, bg=BG)
            holder.pack(side="left")
            self._tabs_holder = holder
            FocusLabel(holder, text="⚠ 分类加载失败，点击重试" +
                       ("：" + self.load_err[:60] if getattr(self, "load_err", None) else ""),
                       bg="#3a1010", fg=FG, font=tv_font(12),
                       on_select=self._retry).pack(side="left", padx=10, pady=2)
            self._show_grid_error()
            return
        items = [("主页", None)]
        items += [(name, cid) for cid, name in self.classes]
        tab_btns = []
        self._tab_map = []  # [(cid, FocusLabel)]
        holder = tk.Frame(self.tabs_bar, bg=BG)
        holder.pack(side="left")
        self._tabs_holder = holder
        for name, cid in items:
            b = FocusLabel(holder, text=name, bg=PANEL, fg=FG, font=tv_font(12),
                           on_select=lambda c=cid: self.select_class(c))
            b.pack(side="left", padx=4, pady=2)
            tab_btns.append(b)
            self._tab_map.append((cid, b))
        if tab_btns:
            tab_btns[0].focus_set()
        # 默认停在「主页」tab（对应原版合并页：进源即显示豆瓣热播）
        self._apply_restore_state()

    def _apply_restore_state(self):
        if not self._restore_pending:
            return
        self._restore_pending = False
        try:
            class_id = self._restore_state.get("class_id")
            if class_id is not None and class_id in [c[0] for c in self.classes]:
                self.cur_class = class_id
                self.page_index = max(1, int(self._restore_state.get("page", 1)))
                filters = self._restore_state.get("filter_sel")
                self.filter_sel = dict(filters) if isinstance(filters, dict) else {}
                self._render_tabs_hl()
                self._reload_grid()
            else:
                self.cur_class = None
        except (TypeError, ValueError):
            self.cur_class = None
        self._restore_state = {}

    def capture_state(self):
        try:
            scroll = self.canvas.yview()[0]
        except tk.TclError:
            scroll = 0.0
        return (), {
            "source_key": self.source_key,
            "restore_state": {
                "class_id": self.cur_class,
                "page": self.page_index,
                "filter_sel": dict(self.filter_sel),
                "scroll": scroll,
            },
        }

    def select_class(self, class_id, auto=False):
        self._auto = auto
        self.cur_class = class_id
        self.page_index = 1
        self.vods = []
        self.filter_sel = {}   # 筛选条件 {key: value}（切分类重置）
        # 从任一分类 tab 进入都算退出文件夹树
        self._folder_stack = []
        self._folder_title = ""
        try:
            self.status_filter.configure(text="")
        except tk.TclError:
            pass
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
        """筛选面板（对应 GridFragment.showFilter）

        注意：filters 对 spider 站点要跑一次 home_content（网络 + 爬虫运行时），
        绝不能放在 UI 线程里取——切源后点一下就会整窗卡死。改为后台取 + 回调开面板。
        """
        bean, cls = self.bean, self.cur_class
        self.status_filter.configure(text="获取筛选中…")

        def run():
            try:
                data = data_api.get_filters(bean)
            except Exception:
                data = {}
            ui_thread.run(lambda: self._open_filter_panel(data, cls))
        import threading
        threading.Thread(target=run, daemon=True).start()

    def _open_filter_panel(self, all_filters, cls):
        """筛选面板渲染（UI 线程；数据已在后台取好）"""
        try:
            if not self.winfo_exists() or cls != self.cur_class:
                return
        except tk.TclError:
            return
        filters = (all_filters or {}).get(str(cls)) or []
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
                # on_select 是 FocusLabel 的 Python 属性，不能用 configure() 设置
                c.on_select = (lambda c=c, v=v, t=toggle: t(c, v))
            rows[f["key"]] = chips

        def apply():
            self.filter_sel = {k: v for k, v in sel.items() if v}
            panel.destroy()
            self.page_index = 1
            self._reload_grid()

        FocusLabel(panel, text="应用筛选", bg=ACCENT, fg="#FFFFFF",
                   font=tv_font(12, True), on_select=apply).pack(pady=8)

    def _refresh_filter_btn(self):
        """筛选器预取完成后刷新「⚙ 筛选」按钮显隐（只读缓存，不联网）"""
        try:
            if not self.winfo_exists() or self.bean is None:
                return
        except tk.TclError:
            return
        btn = getattr(self, "filter_btn", None)
        if btn is None:
            return
        key = f"{self.bean.key}:{self.bean.api}"
        cached = data_api._filters_cache.get(key, {})
        has = bool(cached.get(str(self.cur_class))) if self.cur_class else False
        try:
            if has and btn.winfo_exists():
                btn.pack(side="right", padx=4)
            elif btn.winfo_exists():
                btn.pack_forget()
        except tk.TclError:
            pass

    def _retry(self):
        self._load_classes()

    def _refresh(self):
        """刷新当前内容（F5 / 顶栏按钮）"""
        self._load_classes()
        if self.cur_class is None:
            self._reload_grid()
        else:
            self.page_index = 1
            self.vods = []
            self._reload_grid()

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
        self._request_seq += 1
        request_seq = self._request_seq
        target_class = self.cur_class
        target_page = self.page_index

        def run():
            try:
                result = data_api.get_vods(self.bean, self.cur_class,
                                           target_page, self.filter_sel or None)
                if not result[0]:  # 偶发网络失败，重试一次
                    result = data_api.get_vods(self.bean, self.cur_class,
                                               target_page, self.filter_sel or None)
            except Exception as ex:
                from .paths import log_error
                log_error("get_vods 失败 bean=%s class=%s" %
                          (self.bean.name, self.cur_class), ex)
                result = ([], target_page, 1)
            ui_thread.run(lambda: self._render_grid_if_current(
                request_seq, target_class, *result))
        import threading
        threading.Thread(target=run, daemon=True).start()

    def _render_grid_if_current(self, request_seq, target_class,
                                vods, page, pagecount):
        if request_seq != self._request_seq or target_class != self.cur_class:
            return
        self._render_grid(vods, page, pagecount)

    def _render_grid(self, vods, page, pagecount, append=False):
        if not self.winfo_exists():
            return
        self._prio = 0
        if not append:
            self.vods = vods
        self.page_index, self.page_count = page, pagecount
        # 首个自动选中的分类若无内容，自动尝试下一个分类（源数据漂移兜底；
        # 首页 tab 无内容时落到第一个真实分类，对应原版进入源即展示内容）
        if not append and not vods and self._auto and self.classes:
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
        if not self.vods:
            tk.Label(self.inner, text="暂无内容", bg=BG, fg=FG_DIM,
                     font=tv_font(13)).grid(row=0, column=0, padx=20, pady=20)
            return
        # 自适应列数：按可用宽度算列，整行均分填满（对应原版 GridLayoutManager）
        cols, _cell_w, pw, ph = self._grid_layout()
        poster_grid.fill_columns(self.inner, cols)
        self._layout_used = (cols, pw)
        btns = []
        for i, (vid, name, pic, remark) in enumerate(self.vods):
            _cell, b, poster = poster_grid.cell(
                self.inner, i // cols, i % cols, pw, ph, name, remark or "",
                on_open=lambda v=vid, n=name: self._open_detail(v, n),
                # 右键单元格 → 按片名跨源搜索（对应原版长按「搜索」）
                on_right_click=lambda e, n=name: self._search_name(n))
            btns.append(b)
            if pic:
                # key 按 vod_id 稳定：追加分页重渲染时复用已下载/已缓存的海报
                self._load_poster(f"g{vid}", poster, pic, size=(pw, ph))
        from .theme import grid_key_nav
        grid_key_nav(btns, cols)
        # 分页：还有下一页时给「加载更多」，追加而不是替换
        pager = tk.Frame(self.inner, bg=BG)
        pager.grid(row=(len(self.vods) + cols - 1) // cols + 1, column=0,
                   columnspan=cols, pady=14)
        if self.page_index < self.page_count:
            FocusLabel(pager, text="加载更多 ▼", bg=PANEL, fg=FG, font=tv_font(12),
                       on_select=self._load_more).pack(side="left", padx=8)
        tk.Label(pager, text=f"{self.page_index}/{self.page_count}",
                 bg=BG, fg=FG_DIM, font=tv_font(11)).pack(side="left", padx=8)
        if btns:
            # 追加分页时焦点落在新加载的第一条，而不是跳回顶部
            focus_idx = getattr(self, "_append_focus", 0)
            self._append_focus = 0
            focus_idx = min(max(focus_idx, 0), len(btns) - 1)
            btns[focus_idx].focus_set()
        self._restore_scroll()

    def _restore_scroll(self):
        if not self._pending_scroll:
            return
        scroll = self._pending_scroll
        self._pending_scroll = 0.0
        self.after(80, lambda: self.canvas.yview_moveto(scroll))

    # ---------- 自适应布局 ----------
    def _grid_layout(self):
        """当前内容区可用宽度 → (cols, cell_w, poster_w, poster_h)"""
        try:
            w = self.canvas.winfo_width()
        except tk.TclError:
            w = 0
        if w < 80:   # 尚未完成首次布局：按窗口宽估算
            try:
                w = max(self.winfo_width() - 80, 640)
            except tk.TclError:
                w = 1180
        return poster_grid.layout(w)

    def _on_canvas_resize(self, e):
        try:
            self.canvas.itemconfigure(self._win, width=e.width)
        except tk.TclError:
            return
        if e.width < 80:
            return
        job = getattr(self, "_rz_job", None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._rz_job = self.after(350, self._relayout)

    def _relayout(self):
        """窗口宽度变化后按新宽度重排网格（列数或格子尺寸变了才重渲染）"""
        self._rz_job = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        cols, _cw, pw, _ph = self._grid_layout()
        if (cols, pw) == getattr(self, "_layout_used", None):
            return
        if self.cur_class is None:
            args = getattr(self, "_rec_args", None)
            if args:
                self._render_home_items(*args)
        elif self.vods:
            self._render_grid(self.vods, self.page_index, self.page_count)

    def _load_poster(self, key, poster, url, size=None):
        url, headers = imgcache.parse_pic(url)
        if not url.startswith("http"):
            return
        max_w, max_h = size or (150, 200)

        def on_ready(k, path):
            if not self.winfo_exists() or not poster.winfo_exists():
                imgcache.drop(k)
                return
            try:
                photo = imgcache.fit_photo(tk.PhotoImage(file=path),
                                           max_w, max_h)
            except tk.TclError:
                return
            imgcache.keep(k, photo)
            poster.configure(image=photo, text="", width=photo.width(),
                             height=photo.height())
        imgcache.load(key, url, on_ready, headers, priority=self._prio,
                      size=size)

    def _load_more(self):
        """追加下一页（对应原版上拉加载更多）"""
        if getattr(self, "_loading_more", False):
            return
        if self.cur_class is None or self.page_index >= self.page_count:
            return
        self._loading_more = True
        self._request_seq += 1
        request_seq = self._request_seq
        target_class = self.cur_class
        target_page = self.page_index + 1
        bean, filters = self.bean, dict(self.filter_sel)

        def run():
            try:
                result = data_api.get_vods(bean, target_class, target_page,
                                           filters or None)
            except Exception as ex:
                from .paths import log_error
                log_error("get_vods(更多) 失败 class=%s" % target_class, ex)
                result = ([], target_page, 1)
            ui_thread.run(lambda: self._finish_more(
                request_seq, target_class, target_page, result))
        import threading
        threading.Thread(target=run, daemon=True).start()

    def _finish_more(self, request_seq, target_class, target_page, result):
        self._loading_more = False
        if request_seq != self._request_seq or target_class != self.cur_class:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        vods, page, pagecount = result
        if not vods:
            # 没拿到新内容：当作已经到底，避免按钮反复空转
            self.page_count = self.page_index
            self._render_grid(self.vods, self.page_index, self.page_count,
                              append=True)
            return
        first_new = len(self.vods)
        self.vods = list(self.vods) + list(vods)
        self._append_focus = first_new
        # 保持视觉位置：滚到新加载内容的起始行附近
        cols = self._grid_layout()[0] or 1
        rows = max(1, (len(self.vods) + cols - 1) // cols + 1)
        self._pending_scroll = min(1.0, (first_new // cols) / rows)
        self._render_grid(self.vods, target_page, pagecount, append=True)

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
        tag = ""
        try:
            tag = data_api.get_vod_tag(self.bean, vod_id) if self.bean else ""
        except Exception:
            tag = ""
        if tag == "folder":
            self._open_folder(vod_id, vod_name)
            return
        if tag == "action":
            self._run_action(vod_id)
            return
        from .ui_detail import Page as DetailPage
        self.app.switch(DetailPage, source_key=self.source_key,
                        vod_id=vod_id, vod_name=vod_name)

    def _open_folder(self, folder_id, folder_name):
        """文件夹条目：以条目 id 作为分类 id 再取一页列表（对应 vod_tag=folder）"""
        self._folder_stack.append({"class_id": self.cur_class,
                                   "title": self._folder_title})
        self._folder_title = folder_name
        self.cur_class = str(folder_id)
        self.page_index = 1
        self.vods = []
        self.filter_sel = {}
        self.status_filter.configure(text=f"📁 {folder_name}")
        self._reload_grid()

    def _run_action(self, action_id):
        """动作条目：调用爬虫 action（vod_tag=action）"""
        self.status_filter.configure(text=f"正在执行：{action_id[:20]}…")

        def run():
            try:
                ok, res = data_api.do_action(self.bean, action_id)
            except Exception as ex:
                ok, res = False, str(ex)
            msg = (f"已执行 {action_id[:20]}" if ok else f"执行失败：{res}")
            if ok and res and isinstance(res, str):
                msg = res[:50]
            ui_thread.run(lambda: self.status_filter.configure(text=msg))
        import threading
        threading.Thread(target=run, daemon=True).start()

    # ---------- 合并主页：日期 / 功能菜单 / 豆瓣热播 ----------
    def _back_home_tab(self):
        """← 返回：文件夹 → 上一级；分类 → 主页 tab"""
        if self._folder_stack:
            st = self._folder_stack.pop()
            self.cur_class = st.get("class_id")
            self._folder_title = st.get("title", "")
            self.page_index = 1
            self.vods = []
            self.filter_sel = {}
            try:
                self.status_filter.configure(
                    text=f"📁 {self._folder_title}" if self._folder_title else "")
            except tk.TclError:
                pass
            self._reload_grid()
            return
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

    _DOUBAN_YEARS = ["全部", "2026", "2025", "2024", "2023", "2022", "2021",
                     "2020", "2019", "2018"]

    def _douban_year(self):
        return str(hawk.get(hawk.DOUBAN_YEAR, "") or "")

    def _cycle_douban_year(self):
        """点击年份按钮循环切换「全部 → 2026 → 2025 …」（对应原版年份筛选）"""
        cur = self._douban_year() or "全部"
        try:
            idx = self._DOUBAN_YEARS.index(cur)
        except ValueError:
            idx = 0
        nxt = self._DOUBAN_YEARS[(idx + 1) % len(self._DOUBAN_YEARS)]
        hawk.put(hawk.DOUBAN_YEAR, "" if nxt == "全部" else nxt)
        self._load_recommend()

    def _douban_subjects(self, year):
        """豆瓣热播：新接口 new_search_subjects（支持年份），失败回落旧接口"""
        ua = {"User-Agent": "Mozilla/5.0"}
        url = "https://movie.douban.com/j/new_search_subjects"
        params = {"sort": "U", "range": "0,10", "genres": "热门"}
        if year:
            params["year"] = year
        try:
            r = requests.get(url, params=params, timeout=8, verify=False,
                             headers=ua)
            data = r.json()
            rows = data.get("data") or []
            items = [(s.get("title", ""), s.get("cover", ""), s.get("rate", ""))
                     for s in rows if s.get("title")][:12]
            if items:
                return items
        except Exception:
            pass
        # 旧接口只支持 tag，无年份筛选
        try:
            r = requests.get("https://movie.douban.com/j/search_subjects",
                             params={"type": "movie", "tag": "热门",
                                     "page_limit": 12, "page": 1},
                             timeout=8, verify=False, headers=ua)
            rows = r.json().get("subjects") or []
            return [(s.get("title", ""), s.get("cover", ""), s.get("rate", ""))
                    for s in rows if s.get("title")][:12]
        except Exception:
            return []

    def _load_recommend(self):
        """豆瓣热播（对应 UserFragment.setDouBanData，按天+年份缓存；失败静默）"""
        year = self._douban_year()

        def run():
            today = datetime.date.today().isoformat()
            cache = hawk.get("douban_rec_day", None)
            items = None
            if (cache and cache.get("day") == today
                    and (cache.get("year") or "") == year):
                items = cache.get("items")
            if not items:
                items = self._douban_subjects(year)
                if items:
                    hawk.put("douban_rec_day",
                             {"day": today, "year": year, "items": items})
            header = "豆瓣热播" + (f" · {year}" if year else "")
            ui_thread.run(lambda: self._render_home_items(
                header,
                [(n, c, (f"评分 {rt}" if rt else ""), None, None)
                 for n, c, rt in (items or [])], "douban"))
        import threading
        threading.Thread(target=run, daemon=True).start()

    def _wallpaper_photo(self):
        """首页壁纸横幅：设置 › 壁纸开启时显示

        优先用户指定图片（PIL 精确裁切，tk.PhotoImage 兜底）；没有素材时
        用主题色竖向渐变占位（不联网、不依赖外部图片）。按宽度缓存复用。
        """
        try:
            if not hawk.get(hawk.WALLPAPER, False):
                return None
        except Exception:
            return None
        try:
            w = self.canvas.winfo_width()
        except tk.TclError:
            w = 0
        w = max(400, min(int(w) if w > 80 else 1200, 1920))
        h = 150
        cache = getattr(self, "_wall_cache", None)
        if cache and cache[0] == w:
            return cache[1]
        photo = None
        path = str(hawk.get(hawk.WALLPAPER_OVERRIDE, "") or "")
        if path and os.path.isfile(path):
            try:
                from PIL import Image, ImageOps, ImageTk
                im = ImageOps.fit(Image.open(path).convert("RGB"), (w, h),
                                  Image.LANCZOS)
                photo = ImageTk.PhotoImage(im)
            except Exception:
                try:
                    photo = tk.PhotoImage(file=path)
                except tk.TclError:
                    photo = None
        if photo is None:
            try:
                from PIL import Image, ImageDraw, ImageTk
                top, bottom = (32, 42, 60), (14, 16, 22)
                im = Image.new("RGB", (w, h))
                d = ImageDraw.Draw(im)
                for y in range(h):
                    t = y / max(1, h - 1)
                    d.line([(0, y), (w, y)], fill=tuple(
                        int(top[i] + (bottom[i] - top[i]) * t)
                        for i in range(3)))
                photo = ImageTk.PhotoImage(im)
            except Exception:
                return None
        self._wall_cache = (w, photo)
        return photo

    def _render_home_items(self, header, items, kind):
        """首页推荐位渲染（kind：douban 豆瓣热播 / site 站点推荐 / history 观看历史）"""
        if not self.winfo_exists():
            return
        if self.cur_class is not None:
            return  # 已切到分类，丢弃迟到的首页推荐结果
        self._prio = 2  # 推荐位让路给网格/详情海报
        self._rec_args = (header, items, kind)  # 窗口变宽后 _relayout 重排用
        for w in self.inner.winfo_children():
            w.destroy()
        cols, _cell_w, pw, ph = self._grid_layout()
        poster_grid.fill_columns(self.inner, cols)
        self._layout_used = (cols, pw)
        row0 = 0
        # 首页壁纸横幅（设置 › 壁纸开启；无自定义图片时用主题色渐变占位）
        wall = self._wallpaper_photo()
        if wall is not None:
            self._wall_photo = wall
            tk.Label(self.inner, image=wall, bd=0, bg=BG).grid(
                row=0, column=0, columnspan=cols, sticky="ew", pady=(0, 8))
            row0 = 1
        head = tk.Frame(self.inner, bg=BG)
        head.grid(row=row0, column=0, columnspan=cols, sticky="ew", pady=(4, 10))
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
        if kind == "douban":
            year = self._douban_year() or "全部"
            FocusLabel(head, text=f"　📅 年份 {year}", bg=PANEL, fg=FG,
                       font=tv_font(10), padx=10, pady=4,
                       on_select=self._cycle_douban_year).pack(side="left",
                                                               padx=(4, 0))
        if not items:
            msg = ("还没有观看记录：点开一部影片开始播放后，就会出现在这里"
                   if kind == "history"
                   else "该源暂无推荐内容，可到「设置 › 首页推荐」切换其它类型")
            box = tk.Frame(self.inner, bg=BG)
            box.grid(row=row0 + 1, column=0, columnspan=cols, pady=40)
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
            dele = None
            if kind == "history":
                dele = (lambda e, n=name, v=vod_id, s=src_key:
                        self._delete_history(n, v, s))
            _cell, b, poster = poster_grid.cell(
                self.inner, row0 + 1 + i // cols, i % cols, pw, ph, name,
                note or "",
                on_open=lambda n=name, v=vod_id, s=src_key:
                self._open_rec_item(kind, n, v, s),
                on_right_click=dele)
            btns.append(b)
            if pic:
                self._seq += 1
                self._load_poster(f"rec{self._seq}", poster, pic, size=(pw, ph))
        if btns:
            btns[0].focus_set()
        from .theme import grid_key_nav
        grid_key_nav(btns, cols)
        self._restore_scroll()

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

    def destroy(self):
        # 页面绑定的顶层快捷键（F5）要解绑，否则每次进出页面都会叠加一份
        for seq, fid in getattr(self, "_app_binds", []):
            try:
                self.app.unbind(seq, fid)
            except Exception:
                pass
        self._app_binds = []
        super().destroy()
