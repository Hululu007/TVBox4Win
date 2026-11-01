"""收藏页 CollectActivity 复刻：海报网格（点击进详情，右键取消收藏）"""
import tkinter as tk

from . import apiconfig, imgcache, poster_grid, store
from .theme import BG, FG, FG_DIM, ACCENT, FocusLabel, tv_font


class Page(tk.Frame):
    """对应 ui/activity/CollectActivity.java"""

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", pady=(16, 8))
        FocusLabel(top, text="←", font=tv_font(14, True),
                   on_select=self._back).pack(side="left", padx=20)
        tk.Label(top, text="我的收藏", bg=BG, fg=FG,
                 font=tv_font(18, True)).pack(side="left")
        self.count_lbl = tk.Label(top, text="", bg=BG, fg=FG_DIM,
                                  font=tv_font(11))
        self.count_lbl.pack(side="right", padx=20)

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

    def _render(self):
        for w in self.inner.winfo_children():
            w.destroy()
        items = store.all_collects()
        self.count_lbl.configure(text=f"{len(items)} 部" if items else "")
        if not items:
            tk.Label(self.inner,
                     text="暂无收藏\n在影片详情页点「☆ 收藏」即可加入",
                     bg=BG, fg=FG_DIM, font=tv_font(13), justify="center"
                     ).grid(row=0, column=0, padx=20, pady=50)
            return
        cols, _cw, pw, ph = self._layout()
        poster_grid.fill_columns(self.inner, cols)
        self._layout_used = (cols, pw)
        btns = []
        for i, r in enumerate(items):
            bean = apiconfig.api_config.get(r["source_key"])
            src = bean.name if bean else "源已失效"
            _cell, b, poster = poster_grid.cell(
                self.inner, i // cols, i % cols, pw, ph, r["vod_name"], src,
                on_open=lambda rr=r: self._open(rr),
                on_right_click=lambda e, rr=r: self._remove(rr))
            btns.append(b)
            pic = r.get("vod_pic") or ""
            if pic:
                self._load_poster(f"c{r['source_key']}|{r['vod_id']}", poster,
                                  pic, (pw, ph))
        from .theme import grid_key_nav
        grid_key_nav(btns, cols)

    def _load_poster(self, key, poster, pic, size):
        url, headers = imgcache.parse_pic(pic)
        if not url.startswith("http"):
            return
        max_w, max_h = size

        def on_ready(k, path):
            try:
                if not self.winfo_exists() or not poster.winfo_exists():
                    imgcache.drop(k)
                    return
                photo = imgcache.fit_photo(tk.PhotoImage(file=path),
                                           max_w, max_h)
            except tk.TclError:
                return
            imgcache.keep(k, photo)
            poster.configure(image=photo, text="", width=photo.width(),
                             height=photo.height())
        imgcache.load(key, url, on_ready, headers, priority=0, size=size)

    def _open(self, r):
        from .ui_detail import Page as DetailPage
        self.app.switch(DetailPage, source_key=r["source_key"],
                        vod_id=r["vod_id"], vod_name=r["vod_name"])

    def _back(self):
        from .ui_grid import Page as GridPage
        self.app.go_back(GridPage)

    def _remove(self, r):
        store.remove_collect(r["source_key"], r["vod_id"])
        self._render()
