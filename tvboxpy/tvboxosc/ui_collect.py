"""收藏页 CollectActivity 复刻"""
import tkinter as tk

from . import store, apiconfig
from .theme import BG, FG, FG_DIM, ACCENT, FocusLabel, tv_font, PANEL


def _fmt_time(ts):
    import time as _t
    return _t.strftime("%m-%d %H:%M", _t.localtime(ts)) if ts else ""


class Page(tk.Frame):
    """对应 ui/activity/CollectActivity.java"""

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", pady=(16, 8))
        FocusLabel(top, text="←", font=tv_font(14, True),
                   on_select=lambda: self._back()).pack(side="left", padx=20)
        tk.Label(top, text="我的收藏", bg=BG, fg=FG,
                 font=tv_font(18, True)).pack(side="left")

        self.list_frame = tk.Frame(self, bg=BG)
        self.list_frame.pack(fill="both", expand=True, padx=40, pady=10)
        self._render()

    def _render(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        items = store.all_collects()
        if not items:
            tk.Label(self.list_frame, text="暂无收藏", bg=BG, fg=FG_DIM,
                     font=tv_font(13)).pack(pady=40)
            return
        for r in items:
            row = tk.Frame(self.list_frame, bg=PANEL, padx=12, pady=8)
            row.pack(fill="x", pady=4)
            bean = apiconfig.api_config.get(r["source_key"])
            src = bean.name if bean else r["source_key"]
            FocusLabel(row, text=f"{r['vod_name']}  ·  {src}  ·  {_fmt_time(r['update_time'])}",
                       bg=PANEL, fg=FG, font=tv_font(12),
                       on_select=lambda rr=r: self._open(rr)).pack(side="left")
            FocusLabel(row, text="取消收藏", bg=PANEL, fg=ACCENT, font=tv_font(11),
                       on_select=lambda rr=r: self._remove(rr)).pack(side="right")

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
