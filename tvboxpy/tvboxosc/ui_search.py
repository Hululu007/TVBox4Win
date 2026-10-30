"""搜索页 SearchActivity 复刻：搜索词 + 结果网格 + 搜索历史"""
import tkinter as tk
from . import ui_thread

from . import apiconfig, data_api, hawk, store
from .theme import BG, FG, FG_DIM, ACCENT, FocusLabel, tv_font, PANEL
import urllib.parse
import threading

# 副标题分隔符：豆瓣片名常带「-祸进谭-」「：xxx」「·xxx」，整串去搜基本搜不到，
# 先用主标题搜（对应原版 FastSearchActivity 的片名处理）
_SUB_SEPS = ("：", ":", " -", "—", "·", "（", "(", "【", "[")


def clean_keyword(name):
    """取片名主标题：'死神 千年血战篇 -祸进谭-' → '死神 千年血战篇'"""
    k = (name or "").strip()
    for sep in _SUB_SEPS:
        idx = k.find(sep)
        if idx >= 2:
            k = k[:idx].strip()
    return k or (name or "").strip()


class Page(tk.Frame):
    """对应 ui/activity/SearchActivity.java"""

    def __init__(self, master, app, pre_key=None):
        super().__init__(master, bg=BG)
        self.app = app

        back = FocusLabel(self, text="←", font=tv_font(14, True),
                          on_select=app.go_home)
        back.place(x=16, y=10)

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=60, pady=(16, 6))
        self.kw = tk.Entry(top, font=tv_font(15), bg=PANEL, fg=FG,
                           insertbackground=FG, relief="flat", width=32)
        self.kw.pack(side="left", ipady=6, padx=6)
        self.kw.bind("<Return>", lambda e: self.do_search())
        FocusLabel(top, text="搜索", bg=PANEL, fg=FG, font=tv_font(14, True),
                   on_select=self.do_search).pack(side="left", padx=8)

        # 搜索历史（对应 SearchWordAdapter）
        self.hist_bar = tk.Frame(self, bg=BG)
        self.hist_bar.pack(fill="x", padx=60)
        self._render_history()

        self.result_frame = tk.Frame(self, bg=BG)
        self.result_frame.pack(fill="both", expand=True, padx=60, pady=10)
        self.status = tk.Label(self, text="输入关键词搜索（当前源：全部可搜站点）",
                               bg=BG, fg=FG_DIM, font=tv_font(12))
        self.status.pack(side="bottom", pady=8)
        self.kw.focus_set()
        self._searching = False
        self._result_grid = None

    def destroy(self):
        self._searching = False  # 停止搜索线程回调
        try:
            self.unbind_all("<MouseWheel>")  # 搜索区 bind_all 泄漏防护
        except Exception:
            pass
        super().destroy()

    def _render_history(self):
        for w in self.hist_bar.winfo_children():
            w.destroy()
        for word in hawk.get(hawk.SEARCH_HISTORY, [])[:8]:
            FocusLabel(self.hist_bar, text=word, bg=PANEL, fg=FG_DIM,
                       font=tv_font(11),
                       on_select=lambda w0=word: self._search_word(w0)).pack(side="left", padx=4)

    def _search_word(self, word):
        self.kw.delete(0, "end")
        self.kw.insert(0, word)
        self.do_search()

    def do_search(self):
        kw = self.kw.get().strip()
        if not kw:
            return
        hist = hawk.get(hawk.SEARCH_HISTORY, [])
        if kw not in hist:
            hist.insert(0, kw)
            hawk.put(hawk.SEARCH_HISTORY, hist[:10])
            self._render_history()
        self.status.configure(text=f"正在搜索「{kw}」... 结果会边搜边出现")
        # 预建滚动结果区（边搜边显示：每个源返回立即追加）
        for w in self.result_frame.winfo_children():
            w.destroy()
        inner = tk.Frame(self.result_frame, bg=BG)
        inner.pack(fill="both", expand=True)
        canvas = tk.Canvas(inner, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(inner, orient="vertical", command=canvas.yview)
        grid = tk.Frame(canvas, bg=BG)
        grid.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=grid, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _wheel(e):
            try:
                canvas.yview_scroll(-e.delta // 120, "units")
            except tk.TclError:
                pass
        canvas.bind_all("<MouseWheel>", _wheel)
        self._result_canvas = canvas
        self._result_grid = grid
        self._result_count = 0
        self._searching = True
        threading.Thread(target=self._search_run, args=(kw,), daemon=True).start()

    def _search_run(self, kw):
        # 对应 SearchActivity.searchResult：并发搜全部可搜站点，
        # 结果按关键词过滤（Java L347-350 video.name.contains）；
        # 每个源返回立即追加显示（不等全部搜完）
        from concurrent.futures import ThreadPoolExecutor
        # CMS 源响应快、片名规范，排前面先出结果；jar 壳源慢（要拉 JVM）放后面
        def rank(b):
            api = str(b.api or "")
            if "csp_" in api or api.endswith(".js") or api.endswith(".py"):
                return 2
            return 0 if b.type in (0, 1, 2) else 1
        beans = sorted([b for b in apiconfig.api_config.source_bean_list
                        if b.searchable == 1], key=rank)
        # 主标题（去副标题）优先：豆瓣片名整串在普通源里几乎搜不到
        main_kw = clean_keyword(kw)
        kws = [main_kw] if main_kw else [kw]
        if main_kw and main_kw != kw:
            kws.append(kw)
        lock = threading.Lock()

        def probe(bean):
            if not self._searching:
                return
            vods = []
            for q in kws:  # 先主标题，没结果再用全名
                if not self._searching:
                    return
                try:
                    vods = data_api.search_vods(bean, q)
                except Exception:
                    vods = []
                if vods:
                    break
            found = [(bean, vid, name, remark)
                     for vid, name, pic, remark in vods
                     if any(k in name for k in kws)]
            if not found:
                return
            with lock:
                for item in found:
                    idx = self._result_count
                    self._result_count += 1
                    ui_thread.run(lambda it=item, i=idx:
                                  self._append_result(*it, i))
                n = self._result_count
                done = f"搜索中... 已找到 {n} 条"
                ui_thread.run(lambda t=done: self._set_status_safe(t))
        slow = [0]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(probe, b) for b in beans]
            from concurrent.futures import wait
            done, pending = wait(futures, timeout=25)
            slow[0] = len(pending)  # 个别 jar 壳源要拉 JVM，极慢：超时放弃
        self._searching = False

        def finish():
            n = self._result_count
            extra = f"（{slow[0]} 个慢源超时跳过）" if slow[0] else ""
            if n == 0:
                self._set_status_safe(
                    f"没搜到「{kw}」，试试更短的片名（如去掉副标题）{extra}")
                if self._result_grid is not None:
                    tk.Label(self._result_grid, text="无结果", bg=BG, fg=FG_DIM,
                             font=tv_font(13)).grid(row=0, column=0, padx=20, pady=30)
            else:
                self._set_status_safe(f"共 {n} 条结果（点击卡片即可播放）{extra}")
        ui_thread.run(finish)

    def _set_status_safe(self, text):
        try:
            if self.winfo_exists():
                self.status.configure(text=text)
        except tk.TclError:
            pass  # 页面已切换/销毁

    def _append_result(self, bean, vid, name, remark, idx):
        """每源返回即追加一个结果卡片（保持 winfo_exists 防护）"""
        if not self.winfo_exists():
            return
        grid = self._result_grid
        cols = 5
        cell = FocusLabel(grid, text=f"{name[:14]}\n{bean.name} {remark[:8]}",
                          bg=PANEL, fg=FG, font=tv_font(11), pady=14,
                          on_select=lambda b=bean, v=vid, n=name:
                          self._open_detail(b, v, n))
        cell.grid(row=idx // cols, column=idx % cols, padx=6, pady=6)

    def _open_detail(self, bean, vod_id, name):
        from .ui_detail import Page as DetailPage
        self.app.switch(DetailPage, source_key=bean.key, vod_id=vod_id, vod_name=name)
