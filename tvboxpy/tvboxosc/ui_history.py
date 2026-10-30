"""历史页 HistoryActivity 复刻"""
import tkinter as tk

from . import store, apiconfig
from .theme import BG, FG, FG_DIM, ACCENT, FocusLabel, tv_font, PANEL


def _fmt_time(ts):
    import time as _t
    return _t.strftime("%m-%d %H:%M", _t.localtime(ts)) if ts else ""


class Page(tk.Frame):
    """对应 ui/activity/HistoryActivity.java（含批量删除模式 toggleDelMode）"""

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.del_mode = False
        self.marked = set()
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", pady=(16, 8))
        FocusLabel(top, text="←", font=tv_font(14, True),
                   on_select=app.go_home).pack(side="left", padx=20)
        tk.Label(top, text="观看历史", bg=BG, fg=FG,
                 font=tv_font(18, True)).pack(side="left")
        FocusLabel(top, text="🗑 管理", bg=PANEL, fg=FG, font=tv_font(12),
                   on_select=self._toggle_del).pack(side="right", padx=20)
        FocusLabel(top, text="清空全部", bg=PANEL, fg=ACCENT, font=tv_font(12),
                   on_select=self._clear_all).pack(side="right", padx=8)

        self.list_frame = tk.Frame(self, bg=BG)
        self.list_frame.pack(fill="both", expand=True, padx=40, pady=10)
        self._render()

    def _toggle_del(self):
        self.del_mode = not self.del_mode
        self.marked = set()
        self._render()

    def _clear_all(self):
        for r in store.all_records():
            store.delete_record(r["vod_id"], r["source_key"])
        self._render()

    def _render(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        records = store.all_records()
        if self.del_mode:
            bar = tk.Frame(self.list_frame, bg=BG)
            bar.pack(fill="x", pady=(0, 6))
            FocusLabel(bar, text="完成", bg=ACCENT, fg="#FFFFFF",
                       font=tv_font(12, True),
                       on_select=self._toggle_del).pack(side="right")
            FocusLabel(bar, text=f"删除选中（{len(self.marked)}）", bg=PANEL, fg=FG,
                       font=tv_font(12), on_select=self._delete_marked).pack(side="right", padx=10)
        if not records:
            tk.Label(self.list_frame, text="暂无观看记录", bg=BG, fg=FG_DIM,
                     font=tv_font(13)).pack(pady=40)
            return
        for r in records:
            row = tk.Frame(self.list_frame, bg=PANEL, padx=12, pady=8)
            row.pack(fill="x", pady=4)
            bean = apiconfig.api_config.get(r["source_key"])
            src = bean.name if bean else r["source_key"]
            if self.del_mode:
                marked = r["vod_id"] in self.marked
                FocusLabel(row, text=("☑ " if marked else "☐ ") + r["vod_name"],
                           bg=ACCENT if marked else PANEL, fg=FG, font=tv_font(12),
                           on_select=lambda rr=r: self._mark(rr)).pack(side="left")
            else:
                FocusLabel(row,
                           text=f"{r['vod_name']}  ·  {src}  ·  "
                                f"{r['play_flag']}/{r['play_ep']}  ·  {_fmt_time(r['update_time'])}",
                           bg=PANEL, fg=FG, font=tv_font(12),
                           on_select=lambda rr=r: self._continue(rr)).pack(side="left")
            if not self.del_mode:
                FocusLabel(row, text="删除", bg=PANEL, fg=ACCENT, font=tv_font(11),
                           on_select=lambda rr=r: self._delete(rr)).pack(side="right")

    def _mark(self, r):
        key = r["vod_id"]
        if key in self.marked:
            self.marked.discard(key)
        else:
            self.marked.add(key)
        self._render()

    def _delete_marked(self):
        for r in store.all_records():
            if r["vod_id"] in self.marked:
                store.delete_record(r["vod_id"], r["source_key"])
        self.marked = set()
        self._render()

    def _continue(self, r):
        from .ui_detail import Page as DetailPage
        self.app.switch(DetailPage, source_key=r["source_key"],
                        vod_id=r["vod_id"], vod_name=r["vod_name"])

    def _delete(self, r):
        store.delete_record(r["vod_id"], r["source_key"])
        self._render()
