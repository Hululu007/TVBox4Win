"""历史页 HistoryActivity 复刻：海报网格 + 「上次看到」备注 + 多选管理 + 清空确认"""
import tkinter as tk

from . import apiconfig, imgcache, poster_grid, store
from .theme import BG, FG, FG_DIM, ACCENT, FocusLabel, PANEL, tv_font


class Page(tk.Frame):
    """对应 ui/activity/HistoryActivity.java（含批量删除模式 toggleDelMode）"""

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.del_mode = False
        self.marked = set()   # {(vod_id, source_key)}
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", pady=(16, 8))
        FocusLabel(top, text="←", font=tv_font(14, True),
                   on_select=self._back).pack(side="left", padx=20)
        tk.Label(top, text="观看历史", bg=BG, fg=FG,
                 font=tv_font(18, True)).pack(side="left")
        self.clear_btn = FocusLabel(top, text="清空全部", bg=PANEL, fg=ACCENT,
                                    font=tv_font(12), on_select=self._clear_all)
        self.clear_btn.pack(side="right", padx=20)
        self.manage_btn = FocusLabel(top, text="🗑 管理", bg=PANEL, fg=FG,
                                     font=tv_font(12), on_select=self._toggle_del)
        self.manage_btn.pack(side="right", padx=8)
        self.del_btn = FocusLabel(top, text="删除选中", bg=PANEL, fg=ACCENT,
                                  font=tv_font(12), on_select=self._delete_marked)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=40, pady=(0, 10))
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _wheel(e):
            try:
                self.canvas.yview_scroll(-e.delta // 120, "units")
            except tk.TclError:
                pass
        self.canvas.bind_all("<MouseWheel>", _wheel)

        self._layout_used = None
        self._render()

    def destroy(self):
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        super().destroy()

    # ---------- 布局 ----------
    def _layout(self):
        try:
            w = self.canvas.winfo_width()
        except tk.TclError:
            w = 0
        if w < 80:
            try:
                w = max(self.winfo_width() - 100, 640)
            except tk.TclError:
                w = 1180
        return poster_grid.layout(w)

    def _on_resize(self, e):
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
        self._rz_job = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        cols, _cw, pw, _ph = self._layout()
        if (cols, pw) == self._layout_used:
            return
        self._render()

    # ---------- 渲染 ----------
    def _toggle_del(self):
        self.del_mode = not self.del_mode
        self.marked = set()
        self._render()

    def _render(self):
        for w in self.inner.winfo_children():
            w.destroy()
        if self.del_mode:
            self.del_btn.configure(text=f"删除选中（{len(self.marked)}）")
            self.del_btn.pack(side="right", padx=8)
        else:
            self.del_btn.pack_forget()
        self.manage_btn.configure(text="完成" if self.del_mode else "🗑 管理")

        records = store.all_records()   # 已按「历史合并」开关合并同名记录
        if not records:
            tk.Label(self.inner,
                     text="暂无观看记录\n在分类里点开影片开始播放后，这里会记下进度",
                     bg=BG, fg=FG_DIM, font=tv_font(13), justify="center"
                     ).grid(row=0, column=0, padx=20, pady=50)
            return
        cols, _cw, pw, ph = self._layout()
        poster_grid.fill_columns(self.inner, cols)
        self._layout_used = (cols, pw)
        btns = []
        for i, r in enumerate(records):
            key = (r["vod_id"], r["source_key"])
            bean = apiconfig.api_config.get(r["source_key"])
            src = bean.name if bean else "源已失效"
            ep = (r.get("play_ep") or "").strip()
            flag = (r.get("play_flag") or "").strip()
            seen = f"{flag} {ep}".strip() if flag and flag != ep else ep
            note = f"{src} · 上次看到 {seen}" if seen else src
            if self.del_mode and key in self.marked:
                note = "☑ " + note
            _cell, b, poster = poster_grid.cell(
                self.inner, i // cols, i % cols, pw, ph, r["vod_name"], note,
                on_open=(lambda rr=r: self._mark(rr)) if self.del_mode
                        else (lambda rr=r: self._continue(rr)),
                on_right_click=lambda e, rr=r: self._delete(rr))
            btns.append(b)
            pic = r.get("vod_pic") or ""
            if pic:
                self._load_poster(f"h{r['source_key']}|{r['vod_id']}", poster,
                                  pic, (pw, ph))
        from .theme import grid_key_nav
        grid_key_nav(btns, cols)

    def _load_poster(self, key, poster, pic, size):
        url, headers = imgcache.parse_pic(pic)
        if not url.startswith("http"):
            return
        max_w, max_h = size

        def on_ready(_key, path):
            try:
                if not self.winfo_exists() or not poster.winfo_exists():
                    return
                photo = imgcache.fit_photo(tk.PhotoImage(file=path),
                                           max_w, max_h)
            except tk.TclError:
                return
            imgcache.attach(poster, photo)
            poster.configure(image=photo, text="", width=photo.width(),
                             height=photo.height())
        imgcache.load(key, url, on_ready, headers, priority=0, size=size)

    # ---------- 操作 ----------
    def _mark(self, r):
        key = (r["vod_id"], r["source_key"])
        if key in self.marked:
            self.marked.discard(key)
        else:
            self.marked.add(key)
        self._render()

    def _delete_marked(self):
        if not self.marked:
            return
        for vod_id, source_key in list(self.marked):
            store.delete_record(vod_id, source_key)
        self.marked = set()
        self._render()

    def _delete(self, r):
        store.delete_record(r["vod_id"], r["source_key"])
        self.marked.discard((r["vod_id"], r["source_key"]))
        self._render()

    def _clear_all(self):
        if not store.all_records():
            return
        self._confirm("清空观看历史", "确定清空全部观看记录？此操作无法撤销。",
                      self._do_clear_all)

    def _do_clear_all(self):
        store.clear_records()
        self.marked = set()
        self.del_mode = False
        self._render()

    def _confirm(self, title, message, on_yes):
        """轻量确认弹窗（清空等不可撤销操作）"""
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.geometry("520x200")
        win.grab_set()
        tk.Label(win, text=title, bg=BG, fg=FG,
                 font=tv_font(15, True)).pack(pady=(22, 8))
        tk.Label(win, text=message, bg=BG, fg=FG_DIM, font=tv_font(12),
                 wraplength=440, justify="center").pack(pady=(0, 18))

        def yes():
            win.destroy()
            on_yes()
        row = tk.Frame(win, bg=BG)
        row.pack()
        FocusLabel(row, text="取消", bg=PANEL, fg=FG, font=tv_font(12),
                   padx=24, pady=6,
                   on_select=win.destroy).pack(side="left", padx=10)
        FocusLabel(row, text="确定", bg=ACCENT, fg="#FFFFFF",
                   font=tv_font(12, True), padx=24, pady=6,
                   on_select=yes).pack(side="left", padx=10)
        win.bind("<Escape>", lambda e: win.destroy())
        try:
            win.focus_force()
        except tk.TclError:
            pass

    def _continue(self, r):
        bean = apiconfig.api_config.get(r["source_key"])
        if bean is None:
            # 站源已被删除/配置已更换：回落到按片名全源搜索
            self._search_name(r["vod_name"])
            return
        from .ui_detail import Page as DetailPage
        self.app.switch(DetailPage, source_key=r["source_key"],
                        vod_id=r["vod_id"], vod_name=r["vod_name"])

    def _search_name(self, name):
        try:
            from .ui_search import Page as SearchPage
            self.app.switch(SearchPage, pre_key=None)
            page = self.app.current
            page.kw.delete(0, "end")
            page.kw.insert(0, name)
            page.do_search()
        except Exception:
            pass

    def _back(self):
        from .ui_grid import Page as GridPage
        self.app.go_back(GridPage)
