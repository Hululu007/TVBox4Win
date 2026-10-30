"""详情页 DetailActivity 复刻：海报 + 简介 + 线路/选集 + 收藏/播放 + 快速搜索/倒序"""
import tkinter as tk
from . import ui_thread

from . import apiconfig, store
from . import ui_thread
from .theme import BG, FG, FG_DIM, ACCENT, FocusLabel, tv_font, grid_key_nav, PANEL, POSTER_BG, FOCUS_BG, FOCUS_FG


class Page(tk.Frame):
    """对应 ui/activity/DetailActivity.java"""

    def __init__(self, master, app, source_key, vod_id, vod_name=""):
        super().__init__(master, bg=BG)
        self.app = app
        self.source_key = source_key
        self.vod_id = vod_id
        self.vod_name = vod_name
        self.bean = apiconfig.api_config.get(source_key)
        self.info = None
        self.cur_flag = 0

        back = FocusLabel(self, text="←", font=tv_font(14, True),
                          on_select=self._back)
        back.place(x=16, y=10)

        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True, padx=70, pady=40)
        self._load()

    def _back(self):
        from .ui_grid import Page as GridPage
        self.app.switch(GridPage, source_key=self.source_key)

    def _load(self):
        tk.Label(self.body, text="加载中...", bg=BG, fg=FG_DIM,
                 font=tv_font(13)).pack(pady=30)

        import threading
        def run():
            try:
                info = self.info = __import__(
                    "tvboxosc.data_api", fromlist=["get_detail"]
                ).get_detail(self.bean, self.vod_id) if self.bean else {}
            except Exception as e:
                from .paths import log_error
                log_error("[detail] 加载详情失败 vod_id=%s" % self.vod_id, e)
                self.info = {}
            ui_thread.run(self._render)
        threading.Thread(target=run, daemon=True).start()

    def _render(self):
        try:
            kids = self.body.winfo_children()
        except tk.TclError:
            return  # 页面已切走
        for w in kids:
            w.destroy()
        info = dict(self.info or {})
        # 兜底：源返回空详情（豆瓣壳源/接口失败）时补字段，避免 KeyError 炸渲染
        for k, dv in (("name", self.vod_name or ""), ("pic", ""), ("remark", ""),
                      ("actors", ""), ("director", ""), ("content", ""),
                      ("year", ""), ("area", ""), ("lang", ""), ("cls", ""),
                      ("series_flags", []), ("series_urls", [])):
            info.setdefault(k, dv)
        self.info = info
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x")
        poster = tk.Label(top, text=((info.get("name") or self.vod_name or "🎬")[:1]),
                          width=16, height=10,
                          bg=POSTER_BG, fg="#4A5578", font=tv_font(44))
        poster.pack(side="left", padx=(0, 24))
        if info["pic"]:
            self._load_poster(poster, info["pic"])

        right = tk.Frame(top, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text=info["name"], bg=BG, fg=FG,
                 font=tv_font(20, True), wraplength=700, justify="left").pack(anchor="w")
        # 来源/年份/地区/语言/类型 chips（对应原版 tvSite/tvYear/tvArea/tvLang/tvType）
        chips = []
        if self.bean and self.bean.name:
            chips.append(("源", self.bean.name))
        for label, key in (("年份", "year"), ("地区", "area"),
                           ("语言", "lang"), ("类型", "cls")):
            if info.get(key):
                chips.append((label, str(info[key])[:12]))
        if info["remark"]:
            chips.append(("备注", info["remark"][:14]))
        if chips:
            chipbar = tk.Frame(right, bg=BG)
            chipbar.pack(anchor="w", pady=3)
            for label, val in chips:
                tk.Label(chipbar, text=f" {label} {val} ", bg=PANEL, fg=FG_DIM,
                         font=tv_font(9), padx=6, pady=1).pack(side="left", padx=3)
        for label, val in (("导演", info["director"]), ("主演", info["actors"])):
            if val:
                tk.Label(right, text=f"{label}：{val[:80]}", bg=BG, fg=FG_DIM,
                         font=tv_font(10), wraplength=700,
                         justify="left").pack(anchor="w", pady=1)
        # 播放地址行（对应原版 tvPlayUrl，随选中集更新）
        self.playurl_lbl = tk.Label(right, text="", bg=BG, fg="#5A6B94",
                                    font=tv_font(9), wraplength=700,
                                    justify="left", anchor="w")
        self.playurl_lbl.pack(anchor="w", pady=1)

        btns = tk.Frame(self.body, bg=BG)
        btns.pack(anchor="w", pady=12)
        # 历史恢复（对应 Java onChanged 读 VodInfo 恢复 playFlag/playIndex）
        self._resume = self._resume_from_history()
        if self._resume:
            f_idx, ep_idx = self._resume
            ep_name = self.info["series_flags"][f_idx][1][ep_idx]
            ep_url = self.info["series_urls"][f_idx][ep_idx]
            FocusLabel(btns, text=f"▶ 续播 {ep_name[:10]}", bg=ACCENT, fg="#FFFFFF",
                       font=tv_font(14, True),
                       on_select=lambda: self._play(ep_idx, ep_url)
                       ).pack(side="left", padx=(0, 10))
        else:
            first_ep = ""
            if info["series_urls"] and info["series_urls"][0]:
                first_ep = info["series_urls"][0][0]
            FocusLabel(btns, text="▶ 播放", bg=ACCENT, fg="#FFFFFF",
                       font=tv_font(14, True),
                       on_select=lambda: self._play(0, first_ep)).pack(side="left", padx=(0, 10))
        FocusLabel(btns, text="🔍 快速搜索", bg="#4A90E2", fg="#FFFFFF",
                   font=tv_font(14, True),
                   on_select=self._quick_search).pack(side="left", padx=(0, 10))
        FocusLabel(btns, text="☆ 收藏", bg="#E91E63", fg="#FFFFFF",
                   font=tv_font(14, True),
                   on_select=self._collect).pack(side="left", padx=(0, 10))
        FocusLabel(btns, text="⇅ 倒序", bg=PANEL, fg=FG, font=tv_font(14, True),
                   on_select=self._reverse_eps).pack(side="left")

        if info["content"]:
            tk.Label(self.body, text=info["content"][:300], bg=BG, fg=FG_DIM,
                     font=tv_font(11), wraplength=1000, justify="left",
                     anchor="nw").pack(fill="x", pady=(4, 10))

        # 线路 flags + 选集
        if info["series_flags"]:
            flag_bar = tk.Frame(self.body, bg=BG)
            flag_bar.pack(fill="x", pady=(4, 4))
            self.ep_area = tk.Frame(self.body, bg=BG)
            self.ep_area.pack(fill="both", expand=True)
            for i, (flag, eps) in enumerate(info["series_flags"]):
                FocusLabel(flag_bar, text=flag or f"线路{i+1}", bg=PANEL, fg=FG,
                           font=tv_font(12),
                           on_select=lambda idx=i: self._select_flag(idx)).pack(side="left", padx=4)
            # 选集区定位到上次看的线路，并标记 ▸
            if self._resume:
                self._select_flag(self._resume[0], resume_ep=self._resume[1])
            else:
                self._select_flag(0)
        else:
            # 该源无选集（豆瓣类源 detailContent 为空）：引导到其他源
            tk.Label(self.body, text="⚠ 该源没有可播放的选集（豆瓣类源详情多为空）",
                     bg=BG, fg=ACCENT, font=tv_font(13)).pack(anchor="w", pady=(16, 6))
            FocusLabel(self.body, text="🔍 搜索其他源播放", bg=FOCUS_BG, fg=FOCUS_FG,
                       font=tv_font(14, True),
                       on_select=self._quick_search).pack(anchor="w")

    def _load_poster(self, poster, pic):
        """详情页海报（复用 imgcache，含 @Referer/@User-Agent 解析）"""
        from . import imgcache
        url, headers = imgcache.parse_pic(pic)
        if not url.startswith("http"):
            return
        def on_ready(k, path):
            if not self.winfo_exists() or not poster.winfo_exists():
                imgcache.drop(k)
                return
            try:
                photo = tk.PhotoImage(file=path)
            except tk.TclError:
                return
            imgcache.keep(k, photo)
            poster.configure(image=photo, text="", width=photo.width(),
                             height=photo.height())
        imgcache.load(f"detail{self.vod_id}", url, on_ready, headers, priority=0)

    def _resume_from_history(self):
        """从历史 dataJson 恢复 (flag_idx, ep_idx)，线路/集名不匹配则返回 None"""
        rec = store.get_record(self.source_key, self.vod_id)
        if not rec or not rec.get("data_json"):
            return None
        data = rec["data_json"]
        flags = [f for f, _ in self.info["series_flags"]]
        try:
            f_idx = flags.index(data.get("flag", ""))
        except ValueError:
            return None
        ep_idx = int(data.get("ep_index", 0) or 0)
        eps = self.info["series_flags"][f_idx][1]
        if ep_idx >= len(eps):
            ep_idx = 0
        self._resume_txt = rec.get("play_ep", "")
        self._resume_pos = rec.get("pos") or 0
        return (f_idx, ep_idx)

    def _select_flag(self, idx, resume_ep=None):
        self.cur_flag = idx
        for w in self.ep_area.winfo_children():
            w.destroy()
        names = self.info["series_flags"][idx][1]
        urls = self.info["series_urls"][idx]
        # 播放地址行（对应原版 tvPlayUrl）：显示当前选中集的真实地址
        try:
            sel = resume_ep if resume_ep is not None else 0
            if urls and sel < len(urls):
                self.playurl_lbl.configure(
                    text=f"播放地址：{urls[sel][:120]}")
        except Exception:
            pass
        cols = 8
        btns = []
        for i, (n, u) in enumerate(zip(names, urls)):
            mark = " ▸" if resume_ep is not None and i == resume_ep else ""
            b = FocusLabel(self.ep_area, text=(n[:14] + mark), bg=PANEL, fg=FG,
                           font=tv_font(11), on_select=lambda uu=u, ii=i: self._play(ii, uu))
            b.grid(row=i // cols, column=i % cols, padx=4, pady=4)
            btns.append(b)
        grid_key_nav(btns, cols)
        if resume_ep is not None and resume_ep < len(btns):
            btns[resume_ep].focus_set()
            self._resume_ep = resume_ep
        elif btns:
            btns[0].focus_set()

    def _play(self, ep_index, play_url):
        from .ui_play import Page as PlayPage
        names = self.info["series_flags"][self.cur_flag][1]
        ep_name = names[ep_index] if ep_index < len(names) else ""
        flag = self.info["series_flags"][self.cur_flag][0]
        self.app.switch(PlayPage, source_key=self.source_key, vod_id=self.vod_id,
                        vod_name=self.info["name"], play_flag=flag,
                        play_ep=ep_name, play_url=play_url,
                        series=(self.info["series_flags"][self.cur_flag],
                                self.info["series_urls"][self.cur_flag]),
                        ep_index=ep_index)

    def _collect(self):
        on = store.save_collect(self.source_key, self.vod_id, self.info["name"],
                                self.info["pic"])
        self.app.title("TVBox" + ("（已收藏）" if on else "（已取消收藏）"))

    def _reverse_eps(self):
        """倒序选集（对应 Java tvSort / VodInfo.reverse）"""
        self.info["series_flags"] = [(f, list(reversed(n))) for f, n in
                                     self.info["series_flags"]]
        self.info["series_urls"] = [list(reversed(u)) for u in
                                    self.info["series_urls"]]
        self._select_flag(self.cur_flag)

    def _quick_search(self):
        """快速搜索：跳搜索页搜片名（对应原版 tvQuickSearch → FastSearchActivity）"""
        from .ui_search import Page as SearchPage, clean_keyword
        name = clean_keyword(self.info.get("name") or self.vod_name)
        self.app.switch(SearchPage, pre_key=None)
        page = self.app.current
        page.kw.delete(0, "end")
        page.kw.insert(0, name)
        page.do_search()
