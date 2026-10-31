"""快速搜索页 FastSearchActivity 复刻：
两行状态栏 + 关键词分词 chips + 左侧源筛选 + 右侧海报结果卡片，
精确匹配优先，无精确结果时降级显示高匹配（对应原版 exact/highMatch 逻辑）
"""
import re
import threading
import tkinter as tk

from . import apiconfig, data_api, hawk, imgcache, ui_thread
from .theme import BG, FG, FG_DIM, ACCENT, FocusLabel, tv_font, PANEL, PANEL_HI, POSTER_BG

# 副标题分隔符：豆瓣片名常带「-祸进谭-」「：xxx」「·xxx」，整串去搜基本搜不到
_SUB_SEPS = ("：", ":", " -", "—", "·", "（", "(", "【", "[")

# 原版配色：播放橙 / 搜索蓝
BLUE = "#4A90E2"


def clean_keyword(name):
    """取片名主标题：'死神 千年血战篇 -祸进谭-' → '死神 千年血战篇'"""
    k = (name or "").strip()
    for sep in _SUB_SEPS:
        idx = k.find(sep)
        if idx >= 2:
            k = k[:idx].strip()
    return k or (name or "").strip()


def split_words(text):
    """对应 SearchHelper.splitWords：原名 + 非文字分段 + 主标题"""
    out = []
    t = (text or "").strip()
    if not t:
        return out
    out.append(t)
    for p in re.split(r"\W+", t):
        p = p.strip()
        if p and p not in out:
            out.append(p)
    main = clean_keyword(t)
    if main and main not in out:
        out.append(main)
    return out


def match_result(name, kw):
    """对应 Java matchSearchResult：按空白分词 AND 匹配"""
    tokens = [t for t in re.split(r"\s+", kw.strip()) if t]
    if not tokens:
        return False
    return all(t in name for t in tokens)


class Page(tk.Frame):
    """对应 ui/activity/FastSearchActivity.java"""

    COLS = 5
    CARD_W = 128

    def __init__(self, master, app, pre_key=None):
        super().__init__(master, bg=BG)
        self.app = app
        self._searching = False
        self._result_count = 0
        self._token = 0  # 搜索代次：切换关键词后旧结果作废

        back = FocusLabel(self, text="←", font=tv_font(14, True),
                          on_select=app.go_home)
        back.place(x=16, y=10)

        # ── 顶栏：两行状态 + 关键词输入 ──
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=60, pady=(14, 2))
        self.status = tk.Label(top, text="准备搜索\n结果 0", bg=BG, fg=FG_DIM,
                               font=tv_font(11), justify="left", anchor="w")
        self.status.pack(side="left", padx=(40, 16))
        self.kw = tk.Entry(top, font=tv_font(15), bg=PANEL, fg=FG,
                           insertbackground=FG, relief="flat", width=30)
        self.kw.pack(side="left", ipady=5, padx=6)
        self.kw.bind("<Return>", lambda e: self.do_search())
        FocusLabel(top, text="搜索", bg=BLUE, fg="#FFFFFF", font=tv_font(13, True),
                   on_select=self.do_search).pack(side="left", padx=8)

        # 分词 chips（点击换词重搜，对应 mGridViewWordFenci）
        self.chip_bar = tk.Frame(self, bg=BG)
        self.chip_bar.pack(fill="x", padx=60)

        # 搜索历史
        self.hist_bar = tk.Frame(self, bg=BG)
        self.hist_bar.pack(fill="x", padx=60)
        self._render_history()

        # ── 主体：左源筛选 + 右结果网格 ──
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=60, pady=(6, 8))
        self.filter_col = tk.Frame(body, bg=BG, width=150)
        self.filter_col.pack(side="left", fill="y", padx=(0, 10))
        self.filter_col.pack_propagate(False)

        rf = tk.Frame(body, bg=BG)
        rf.pack(side="left", fill="both", expand=True)
        canvas = tk.Canvas(rf, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(rf, orient="vertical", command=canvas.yview)
        self._result_grid = tk.Frame(canvas, bg=BG)
        self._result_grid.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._result_grid, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _wheel(e):
            try:
                canvas.yview_scroll(-e.delta // 120, "units")
            except tk.TclError:
                pass
        canvas.bind_all("<MouseWheel>", _wheel)
        self._canvas = canvas

        # 运行期状态（对应原版字段）
        self._result_vods = {}     # source_key -> [(bean, vid, name, pic, remark)]
        self._sp_names = []        # [(source_key, name)] 按结果到达顺序
        self._matched = []         # AND 匹配的全部结果
        self._exact = []           # 片名完全相等
        self._shown_key = "all"    # 当前筛选
        self._total = 0
        self._done = 0
        self._slow = 0
        self._rendered = set()     # 已渲染的 key|vid

        self.kw.focus_set()

    # ── 兼容旧调用：destroy 时停线程回调 ──
    def destroy(self):
        self._searching = False
        self._token += 1
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        super().destroy()

    def _render_history(self):
        for w in self.hist_bar.winfo_children():
            w.destroy()
        hist = hawk.get(hawk.SEARCH_HISTORY, [])[:8]
        if not hist:
            return
        tk.Label(self.hist_bar, text="历史", bg=BG, fg=FG_DIM,
                 font=tv_font(10)).pack(side="left", padx=(2, 6))
        for word in hist:
            FocusLabel(self.hist_bar, text=word, bg=PANEL, fg=FG_DIM,
                       font=tv_font(10), pady=2,
                       on_select=lambda w0=word: self._search_word(w0)
                       ).pack(side="left", padx=3)

    def _search_word(self, word):
        self.kw.delete(0, "end")
        self.kw.insert(0, word)
        self.do_search()

    # ── 状态栏（对应 updateSearchStatus 两行文案）──
    def _set_status(self, line1, line2):
        try:
            if self.winfo_exists():
                self.status.configure(text=f"{line1}\n{line2}")
        except tk.TclError:
            pass

    def _update_status(self):
        total, done, slow = self._total, self._done, self._slow
        n = self._result_count
        if total <= 0:
            self._set_status("准备搜索", "结果 0")
        elif done >= total:
            l1 = f"搜索完成 {n}"
            l2 = f"源 {total}/{total}"
            if slow:
                l2 += f" · 超时 {slow}"
            self._set_status(l1, l2)
        else:
            self._set_status(f"搜源 {done}/{total}", f"结果 {n} · 待 {total - done}")

    # ── 发起搜索 ──
    def do_search(self):
        kw = self.kw.get().strip()
        if not kw:
            return
        hist = hawk.get(hawk.SEARCH_HISTORY, [])
        if kw not in hist:
            hist.insert(0, kw)
            hawk.put(hawk.SEARCH_HISTORY, hist[:10])
            self._render_history()

        self._token += 1
        token = self._token
        self._searching = True
        self._result_count = 0
        self._result_vods = {}
        self._sp_names = []
        self._matched = []
        self._exact = []
        self._shown_key = "all"
        self._rendered = set()
        self._total = 0
        self._done = 0
        self._slow = 0
        for w in self._result_grid.winfo_children():
            w.destroy()
        self._render_chips(kw)
        self._render_filter()
        self._update_status()
        threading.Thread(target=self._search_run, args=(kw, token), daemon=True).start()

    def _render_chips(self, kw):
        for w in self.chip_bar.winfo_children():
            w.destroy()
        for word in split_words(kw)[:6]:
            FocusLabel(self.chip_bar, text=word, bg=PANEL_HI, fg=FG,
                       font=tv_font(10), pady=2,
                       on_select=lambda w0=word: self._search_word(w0)
                       ).pack(side="left", padx=3, pady=2)

    def _search_run(self, kw, token):
        from concurrent.futures import ThreadPoolExecutor, wait
        beans = [b for b in apiconfig.api_config.source_bean_list if b.searchable == 1]

        def rank(b):
            api = str(b.api or "")
            if "csp_" in api or api.endswith(".js") or api.endswith(".py"):
                return 2  # jar/js 壳源慢（要拉运行时），排后面
            return 0 if b.type in (0, 1, 2) else 1
        beans.sort(key=rank)
        self._total = len(beans)
        ui_thread.run(self._update_status)

        main_kw = clean_keyword(kw)
        kws = [main_kw] if main_kw else [kw]
        if main_kw != kw:
            kws.append(kw)
        lock = threading.Lock()

        def probe(bean):
            if self._token != token:
                return
            vods = []
            for q in kws:  # 主标题优先，没结果再全名
                if self._token != token:
                    return
                try:
                    vods = data_api.search_vods(bean, q)
                except Exception:
                    vods = []
                if vods:
                    break
            with lock:
                self._done += 1
                rows = [(bean, vid, name, pic, remark)
                        for vid, name, pic, remark in vods
                        if match_result(name, kw)]
                if rows:
                    self._result_vods.setdefault(bean.key, []).extend(rows)
                    if all(k != bean.key for k, _ in self._sp_names):
                        self._sp_names.append((bean.key, bean.name))
                    for r in rows:
                        vid, name = r[1], r[2]
                        if name.strip() == kw.strip():
                            self._exact.append(r)
                        self._matched.append(r)
            ui_thread.run(lambda b=bean, r0=rows: self._on_source_done(b, r0, token))

        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(probe, b) for b in beans]
            _, pending = wait(futures, timeout=25)  # jar 慢源超时放弃
            self._slow = len(pending)
        if self._token != token:
            return
        self._searching = False
        self._done = self._total
        ui_thread.run(lambda t=token: self._finish(t))

    # ── 每源完成回调（UI 线程）──
    def _on_source_done(self, bean, rows, token):
        if self._token != token or not self.winfo_exists():
            return
        self._update_status()
        self._render_filter()
        self._refresh_visible(token)

    def _finish(self, token):
        if self._token != token or not self.winfo_exists():
            return
        self._update_status()
        if not self._matched:
            self._set_status(f"搜索完成 0", f"没搜到「{self.kw.get().strip()}」"
                             f"{' · 超时 %d' % self._slow if self._slow else ''}"
                             "，试试分词或更短片名")
            tk.Label(self._result_grid, text="无结果", bg=BG, fg=FG_DIM,
                     font=tv_font(13)).grid(row=0, column=0, padx=20, pady=30)
            return
        self._refresh_visible(token, force=True)

    # ── 显示逻辑：精确匹配优先；无精确且无其它已显示时展示全部匹配 ──
    def _visible_rows(self):
        if self._shown_key != "all":
            return self._result_vods.get(self._shown_key, [])
        if self._exact:
            return self._exact
        return self._matched

    def _refresh_visible(self, token, force=False):
        if self._token != token or not self.winfo_exists():
            return
        rows = self._visible_rows()
        grid = self._result_grid
        idx = len(self._rendered)
        new_rows = [r for r in rows if (r[0].key, r[1]) not in self._rendered]
        if not new_rows:
            return
        for bean, vid, name, pic, remark in new_rows:
            k = (bean.key, vid)
            self._rendered.add(k)
            self._make_card(grid, idx, bean, vid, name, pic, remark)
            idx += 1
        self._result_count = idx
        if self._done < self._total:
            self._update_status()

    # ── 左列源筛选 ──
    def _render_filter(self):
        for w in self.filter_col.winfo_children():
            w.destroy()
        items = [("all", "全部")] + self._sp_names
        for key, name in items:
            sel = (key == self._shown_key)
            FocusLabel(self.filter_col, text=name[:8], bg=PANEL_HI if sel else PANEL,
                       fg=ACCENT if sel else FG, font=tv_font(11, sel),
                       on_select=lambda k0=key: self._select_filter(k0)
                       ).pack(fill="x", pady=2)

    def _select_filter(self, key):
        if key == self._shown_key:
            return
        self._shown_key = key
        for w in self._result_grid.winfo_children():
            w.destroy()
        self._rendered = set()
        self._result_count = 0
        self._render_filter()
        self._refresh_visible(self._token, force=True)

    # ── 结果卡片：海报 + 源名角标 + remark + 标题（对应 item_search）──
    def _make_card(self, grid, idx, bean, vid, name, pic, remark):
        cell = tk.Frame(grid, bg=PANEL, padx=4, pady=4)
        cell.grid(row=idx // self.COLS, column=idx % self.COLS,
                  padx=6, pady=6, sticky="n")
        poster = tk.Label(cell, text=(name[:1] or "🎬"), width=15, height=8,
                          bg=POSTER_BG, fg="#4A5578", font=tv_font(24))
        poster.pack()
        if pic:
            self._load_poster(f"s{bean.key}|{vid}", poster, pic)
        tag = tk.Label(cell, text=f"{bean.name[:8]} {remark[:10]}".strip(),
                       bg=PANEL, fg=FG_DIM, font=tv_font(9))
        tag.pack(fill="x")
        nm = tk.Label(cell, text=name[:16], bg=PANEL, fg=FG, font=tv_font(11))
        nm.pack(fill="x")
        for w in (cell, poster, tag, nm):
            w.bind("<Button-1>", lambda e, b=bean, v=vid, n=name:
                   self._open_detail(b, v, n))
        try:
            cell.bind("<Enter>", lambda e, c=cell: c.configure(bg=PANEL_HI))
            cell.bind("<Leave>", lambda e, c=cell: c.configure(bg=PANEL))
        except Exception:
            pass

    def _load_poster(self, key, poster, pic):
        url, headers = imgcache.parse_pic(pic)
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

        imgcache.load(key, url, on_ready, headers, priority=0)

    def _open_detail(self, bean, vod_id, name):
        from .ui_detail import Page as DetailPage
        self.app.switch(DetailPage, source_key=bean.key, vod_id=vod_id,
                        vod_name=name)
