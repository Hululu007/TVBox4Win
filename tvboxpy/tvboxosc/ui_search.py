"""快速搜索页 FastSearchActivity 复刻：
两行状态栏 + 关键词分词 chips + 左侧源筛选 + 右侧海报结果卡片，
精确匹配优先，无精确结果时降级显示高匹配（对应原版 exact/highMatch 逻辑）
"""
import re
import threading
import tkinter as tk

from . import apiconfig, data_api, hawk, imgcache, poster_grid, ui_thread
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


# 拼音首字母联想（对应 SearchActivity.loadRec 的腾讯 smart_box 接口）
SUGGEST_URL = ("https://tv.aiseet.atianqi.com/i-tvbin/qtv_video/"
               "search/get_search_smart_box")


def parse_suggestions(data):
    """解析联想结果：data.search_data.vecGroupData[].group_data[].keyword_txt"""
    out = []
    try:
        groups = data["data"]["search_data"]["vecGroupData"]
        items = []
        for g in groups:
            items.extend(g.get("group_data") or [])
    except (KeyError, TypeError, AttributeError):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        word = ""
        try:
            word = item["dtReportInfo"]["reportData"]["keyword_txt"]
        except (KeyError, TypeError):
            for key in ("keyword", "word", "title"):
                if isinstance(item.get(key), str):
                    word = item[key]
                    break
        word = str(word or "").strip()
        if word and word not in out:
            out.append(word)
    return out


class Page(tk.Frame):
    """对应 ui/activity/FastSearchActivity.java"""

    COLS = 5  # 默认列数；实际由 _calc_card_layout 按窗口宽度自适应覆盖

    def __init__(self, master, app, pre_key=None, restore_state=None):
        super().__init__(master, bg=BG)
        self.app = app
        self._searching = False
        self._result_count = 0
        self._token = 0  # 搜索代次：切换关键词后旧结果作废
        self._restore_state = dict(restore_state or {})
        self._pending_filter = self._restore_state.get("filter", "all")
        self._sug_job = None     # 输入防抖定时器
        self._sug_token = 0      # 联想请求代次：输入变了旧结果作废

        back = FocusLabel(self, text="←", font=tv_font(14, True),
                          on_select=self._back)
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
        self.kw.bind("<KeyRelease>", self._on_kw_key)
        FocusLabel(top, text="搜索", bg=BLUE, fg="#FFFFFF", font=tv_font(13, True),
                   on_select=self.do_search).pack(side="left", padx=8)

        # 首字母联想（对应原版 loadRec：输入拼音首字母 → 猜你想搜）
        self.sug_bar = tk.Frame(self, bg=BG)
        self.sug_bar.pack(fill="x", padx=60)

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
        self._win_id = canvas.create_window((0, 0), window=self._result_grid,
                                            anchor="nw")
        # 结果区宽度跟随画布 + 列数随窗口宽度自适应（避免右侧留白）
        canvas.bind("<Configure>", self._on_canvas_resize)
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
        keyword = str(self._restore_state.get("keyword", "") or "").strip()
        if keyword:
            self.kw.insert(0, keyword)
            self.after(0, self.do_search)

    def _back(self):
        from .ui_grid import Page as GridPage
        self.app.go_back(GridPage)

    def capture_state(self):
        try:
            scroll = self._canvas.yview()[0]
        except (AttributeError, tk.TclError):
            scroll = 0.0
        return (), {
            "pre_key": None,
            "restore_state": {
                "keyword": self.kw.get().strip(),
                "filter": self._shown_key,
                "scroll": scroll,
            },
        }

    # ── 兼容旧调用：destroy 时停线程回调 ──
    def destroy(self):
        self._searching = False
        self._token += 1
        self._sug_token += 1
        if self._sug_job:
            try:
                self.after_cancel(self._sug_job)
            except Exception:
                pass
            self._sug_job = None
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

    # ── 拼音首字母联想（对应 SearchActivity.loadRec / PinyinAdapter）──
    def _on_kw_key(self, e=None):
        keysym = getattr(e, "keysym", "") if e is not None else ""
        if keysym in ("Return", "KP_Enter", "Escape"):  # 回车直接搜索，不联想
            return
        if self._sug_job:
            try:
                self.after_cancel(self._sug_job)
            except Exception:
                pass
            self._sug_job = None
        text = self.kw.get().strip()
        if not text:
            self._sug_token += 1
            self._render_suggest([])
            return
        self._sug_job = self.after(300, lambda t=text: self._load_suggest(t))

    def _load_suggest(self, text):
        self._sug_job = None
        try:
            if not self.winfo_exists() or self.kw.get().strip() != text:
                return
        except tk.TclError:
            return
        self._sug_token += 1
        token = self._sug_token
        threading.Thread(target=self._suggest_run,
                         args=(text, token), daemon=True).start()

    def _suggest_run(self, text, token):
        words = []
        try:
            r = apiconfig.SESSION.get(
                SUGGEST_URL,
                params={"format": "json", "page_num": 0,
                        "page_size": 20, "key": text},
                timeout=6, verify=False)
            if r.status_code == 200:
                words = parse_suggestions(r.json())
        except Exception:
            words = []
        if self._sug_token != token:
            return
        ui_thread.run(lambda: self._show_suggest(words, text, token))

    def _show_suggest(self, words, text, token):
        try:
            if (self._sug_token != token or not self.winfo_exists()
                    or self.kw.get().strip() != text):
                return
        except tk.TclError:
            return
        self._render_suggest(words)

    def _render_suggest(self, words):
        for w in self.sug_bar.winfo_children():
            w.destroy()
        if not words:
            return
        tk.Label(self.sug_bar, text="猜你想搜", bg=BG, fg=FG_DIM,
                 font=tv_font(10)).pack(side="left", padx=(2, 6))
        for word in words[:12]:
            FocusLabel(self.sug_bar, text=word[:20], bg=PANEL, fg=FG,
                       font=tv_font(10), pady=2,
                       on_select=lambda w0=word: self._search_word(w0)
                       ).pack(side="left", padx=3, pady=2)

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
        # 开始搜索后收起联想，避免旧输入的结果继续弹出
        if self._sug_job:
            try:
                self.after_cancel(self._sug_job)
            except Exception:
                pass
            self._sug_job = None
        self._sug_token += 1
        self._render_suggest([])
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
        self._calc_card_layout()
        self._render_chips(kw)
        self._render_filter()
        self._update_status()
        threading.Thread(target=self._search_run, args=(kw, token), daemon=True).start()

    @staticmethod
    def _fast_search():
        """快速搜索开关（HawkConfig.FAST_SEARCH，默认开）"""
        try:
            return bool(hawk.get(hawk.FAST_SEARCH, True))
        except Exception:
            return True

    def _render_chips(self, kw):
        for w in self.chip_bar.winfo_children():
            w.destroy()
        words = split_words(kw) if self._fast_search() else [kw]
        for word in words[:6]:
            FocusLabel(self.chip_bar, text=word, bg=PANEL_HI, fg=FG,
                       font=tv_font(10), pady=2,
                       on_select=lambda w0=word: self._search_word(w0)
                       ).pack(side="left", padx=3, pady=2)

    def _search_run(self, kw, token):
        from concurrent.futures import ThreadPoolExecutor, wait
        # searchable 1/2 都参与搜索（2 常见于 js 壳源，原版同样会搜）
        beans = [b for b in apiconfig.api_config.source_bean_list
                 if b.searchable in (1, 2)]

        def rank(b):
            api = str(b.api or "")
            if "csp_" in api or api.endswith(".js") or api.endswith(".py"):
                return 2  # jar/js 壳源慢（要拉运行时），排后面
            return 0 if b.type in (0, 1, 2) else 1
        beans.sort(key=rank)
        self._total = len(beans)
        ui_thread.run(self._update_status)

        if self._fast_search():
            # 快速搜索：主标题优先，没结果再搜全名
            main_kw = clean_keyword(kw)
            kws = [main_kw] if main_kw else [kw]
            if main_kw != kw:
                kws.append(kw)
        else:
            kws = [kw]
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
        if self._pending_filter not in ("", "all"):
            self._select_filter(self._pending_filter)
        self._pending_filter = "all"
        scroll = self._restore_state.get("scroll", 0.0)
        self._restore_state = {}
        if scroll:
            self.after(80, lambda: self._canvas.yview_moveto(scroll))

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
        self._calc_card_layout()
        self._rendered = set()
        self._result_count = 0
        self._render_filter()
        self._refresh_visible(self._token, force=True)

    # ── 自适应结果网格：列数/卡片尺寸随结果区宽度计算 ──
    def _calc_card_layout(self):
        try:
            w = self._canvas.winfo_width()
        except tk.TclError:
            w = 0
        if w < 80:   # 尚未完成首次布局：按窗口宽扣掉左侧源筛选列估算
            try:
                w = max(self.winfo_width() - 260, 560)
            except tk.TclError:
                w = 960
        cols, _cw, pw, ph = poster_grid.layout(w)
        self.COLS = cols          # 覆盖类常量：本次搜索/筛选会话内保持不变
        self._card_size = (pw, ph)
        poster_grid.fill_columns(self._result_grid, cols)
        try:
            self._canvas.itemconfigure(self._win_id, width=w)
        except tk.TclError:
            pass

    def _on_canvas_resize(self, e):
        try:
            self._canvas.itemconfigure(self._win_id, width=e.width)
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
        self._rz_job = self.after(400, self._relayout_cards)

    def _relayout_cards(self):
        """窗口变宽/变窄后按新宽度重列卡片（数据都在，重画不重搜）"""
        self._rz_job = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        old = (getattr(self, "COLS", 0), getattr(self, "_card_size", (0, 0)))
        self._calc_card_layout()
        if (self.COLS, self._card_size) == old:
            return
        for w in self._result_grid.winfo_children():
            w.destroy()
        self._rendered = set()
        self._result_count = 0
        self._refresh_visible(self._token, force=True)

    # ── 结果卡片：海报 + 源名角标 + remark + 标题（对应 item_search）──
    def _make_card(self, grid, idx, bean, vid, name, pic, remark):
        pw, ph = getattr(self, "_card_size", (160, 240))
        tag = f"{bean.name[:8]} {remark[:10]}".strip()
        cell, _focus, poster = poster_grid.cell(
            grid, idx // self.COLS, idx % self.COLS, pw, ph, name, tag,
            on_open=lambda b=bean, v=vid, n=name: self._open_detail(b, v, n),
            cell_bg=PANEL, overlay=False)
        if pic:
            self._load_poster(f"s{bean.key}|{vid}", poster, pic,
                              size=(pw, ph))
        try:
            cell.bind("<Enter>", lambda e, c=cell: c.configure(bg=PANEL_HI))
            cell.bind("<Leave>", lambda e, c=cell: c.configure(bg=PANEL))
        except Exception:
            pass

    def _load_poster(self, key, poster, pic, size=None):
        url, headers = imgcache.parse_pic(pic)
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

        imgcache.load(key, url, on_ready, headers, priority=0, size=size)

    def _open_detail(self, bean, vod_id, name):
        from .ui_detail import Page as DetailPage
        self.app.switch(DetailPage, source_key=bean.key, vod_id=vod_id,
                        vod_name=name)
