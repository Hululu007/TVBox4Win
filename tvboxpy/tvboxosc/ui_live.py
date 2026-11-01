"""直播页 LivePlayActivity 复刻：txt/m3u 频道列表解析 + mpv 播放 + 分组/换台 + EPG"""
import os
import re
import threading
import tkinter as tk

from . import apiconfig, epg, hawk, ui_thread
from .player import MpvPlayer
from .theme import ACCENT, FG, FG_DIM, FocusLabel, PANEL_HI, tv_font

CHROME_BG = "#0B0F1C"   # 顶栏/控制栏底色（近黑，覆在视频上）


def extract_epg_url(text):
    """从 m3u 头提取节目单地址（对应原版 extractLiveTextEpg：
    x-tvg-url / tvg-url / url-tvg）"""
    for line in (text or "").splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line.upper().startswith("#EXTM3U"):
            continue
        for key in ("x-tvg-url", "tvg-url", "url-tvg"):
            m = re.search(key + r'\s*=\s*"([^"]+)"', line, re.I)
            if m and m.group(1).strip():
                return m.group(1).strip()
    return ""


def read_live_source(url):
    """读取直播源文本（对应原版 LIVE_API_URL 的加载）：支持 http(s) 与本地文件"""
    u = str(url or "").strip()
    if u.startswith(("http://", "https://")):
        from .apiconfig import fetch_text
        return fetch_text(u)
    path = u[8:] if u.startswith("file:///") else u
    path = path.replace("/", os.sep)
    if not os.path.isabs(path):
        from .paths import data_path
        path = data_path(path)
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def parse_live_source(text, url=""):
    """解析直播源 → (源名, [(group, name, [(url, src)...])])

    兼容三种形态（与 ApiConfig.parseLiveJson / loadLiveApi 等价）：
    1. 直接是 txt(#genre#)/m3u 频道列表
    2. TVBox 配置 JSON（含 lives 数组）→ 递归加载第一个可用直播源
    3. 单个直播源 JSON（含 name/url）
    """
    text = text or ""
    name = ""
    if url:
        base = os.path.basename(str(url).split("?")[0].replace("\\", "/"))
        name = os.path.splitext(base)[0]
    # 直播源自带节目单地址（m3u 头），对应原版 parseLiveText → EPG_URL
    epg_addr = extract_epg_url(text)
    if epg_addr:
        hawk.put(hawk.EPG_URL, epg_addr)
    s = text.lstrip("\ufeff \r\n\t")
    if s.startswith("{"):
        cfg = apiconfig.extract_json(s)
        if not isinstance(cfg, dict):
            cfg = None
        if isinstance(cfg, dict):
            lives = cfg.get("lives")
            if isinstance(lives, list) and lives:
                for l in lives:
                    if not isinstance(l, dict):
                        continue
                    if str(l.get("type", "0") or "0") not in ("0", ""):
                        continue
                    u = str(l.get("url") or l.get("api") or "").strip()
                    if not u or "127.0.0.1" in u or "localhost" in u:
                        continue
                    live_epg = str(l.get("epg") or "").strip()
                    if live_epg:
                        hawk.put(hawk.EPG_URL, live_epg)   # 对应 lives[].epg
                    try:
                        chs = _parse_live_text(read_live_source(u))
                    except Exception:
                        continue
                    if chs:
                        return l.get("name") or name, chs
                return name, []
            u = str(cfg.get("url") or cfg.get("api") or "").strip()
            if u:
                if u.startswith("---"):  # 原版 json 内嵌列表
                    return cfg.get("name") or name, _parse_live_text(
                        u.lstrip("-").strip())
                try:
                    chs = _parse_live_text(read_live_source(u))
                except Exception:
                    chs = []
                if chs:
                    return cfg.get("name") or name, chs
                if u.startswith(("http://", "https://", "rtmp://", "rtp://", "udp://")):
                    n = cfg.get("name") or name or "直播"
                    return n, [[cfg.get("group") or "直播", n, [(u, "线路1")]]]
                return name, []
    return name, _parse_live_text(text)


def _parse_live_text(text):
    """解析 txt(#genre#) 或 m3u 频道列表 → [(分组, 频道名, [(url, 源名)...])]
    对应 Java loadLives：频道多源 url$源名（逗号/# 分隔多个地址）"""
    channels = []
    if not text:
        return channels
    lines = text.splitlines()
    if any(l.startswith("#EXTINF") for l in lines):  # m3u
        import re
        for l in lines:
            l = l.strip()
            if l.startswith("#EXTINF"):
                name = l.split(",")[-1].strip()
                group = "直播"
                m = re.search(r'tvg-group="([^"]*)"', l)
                if m and m.group(1):
                    group = m.group(1)
                elif "cctv" in name.lower() or "央视" in name:
                    group = "央视"
                elif "卫视" in name:
                    group = "卫视"
                channels.append([group, name, []])
            elif l and not l.startswith("#") and channels and not channels[-1][2]:
                channels[-1][2].append((l, "线路1"))
    else:  # txt: 分组,#genre# / 频道名,url1$源1#url2$源2（或逗号分隔多地址）
        group = "直播"
        for l in lines:
            l = l.strip()
            if not l or l.startswith("#"):
                continue
            if l.endswith("#genre#"):
                group = l.split(",")[0].strip()
                continue
            if "," in l:
                name, urls = l.split(",", 1)
                srcs = []
                # 支持逗号或 # 分隔多地址，url$源名 后缀
                for u in urls.replace("#", ",").split(","):
                    u = u.strip()
                    if not u:
                        continue
                    if "$" in u:
                        u, src = u.split("$", 1)
                        srcs.append((u.strip(), src.strip() or "线路"))
                    else:
                        srcs.append((u, f"线路{len(srcs) + 1}"))
                if srcs:
                    channels.append([group, name.strip(), srcs])
    # 保留 http/rtmp/rtp/udp（对应 Java IJK 支持的协议）
    out = []
    for g, n, srcs in channels:
        srcs = [(u, s) for u, s in srcs if u and (u.startswith(("http://", "https://",
                "rtmp://", "rtp://", "udp://")))]
        if srcs:
            out.append((g, n, srcs))
    return out

class Page(tk.Frame):
    """对应 ui/activity/LivePlayActivity.java

    全屏播放 + 左侧两层列表（一级分组列 → 二级频道列），进入即自动播放默认频道
    （上次频道 → CCTV1 → 第一个分组第一个频道，对应 Java initLiveState）。
    顶部常驻状态栏（返回按钮 + 台标 + 时钟，对应 tv_top_status）、底部悬浮控制栏
    （上一台/暂停/下一台/换源/列表/全屏/退出，对应 backcontroller）；列表与控制栏
    5 秒无操作自动隐藏，鼠标移动/按键唤出；↑↓ 换台、←→ 切列、数字键选台。
    """

    TOP_H = 46         # 顶部常驻状态栏高度
    BAR_H = 110        # 底部悬浮控制栏高度（节目单行 + 按钮行）
    GROUP_W = 176      # 一级：分组列宽
    CH_W = 300         # 二级：频道列宽
    HIDE_MS = 5000     # 列表空闲自动隐藏

    def __init__(self, master, app):
        super().__init__(master, bg="#000000")
        self.app = app
        self.channels = []      # [(group, name, [(url, src), ...])]
        self.groups = []
        self.cur_group = None
        self.cur_ch = None
        self.cur_src = 0
        self.player = None
        self._group_btns = []   # [(btn, group)]
        self._ch_btns = []      # [(btn, channel)]
        self._app_binds = []
        self._hide_job = None
        self._digits = ""
        self._digit_job = None
        self._clock_job = None
        self._epg_seq = 0       # 节目单请求序号（防切台串台）
        self._epg_job = None
        self._epg_progs = []
        self._visible = True

        # 全屏沉浸（对应 LivePlayActivity 全屏）
        self._was_full = False
        try:
            self._was_full = bool(self.app.attributes("fullscreen"))
            self.app.attributes("-fullscreen", True)
        except Exception:
            pass

        # 视频层铺满整页（对应 mVideoView）
        self.video = tk.Frame(self, bg="#000000", highlightthickness=0)
        self.video.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        # 顶部常驻状态栏（对应 tv_top_status + tvChannel）：返回按钮常驻可见。
        # 原版靠遥控器/系统返回键退出，Windows 没有这个键，必须给鼠标和键盘
        # 都能一眼看到的出口，否则全屏后没有任何可点的退出入口。
        self.top = tk.Frame(self, bg=CHROME_BG)
        self.top.place(x=0, y=0, relwidth=1.0, height=self.TOP_H)
        self._top_widgets(self.top)
        self.top.lift()

        # 右上角大号台标（对应 tv_selected_channel）
        self.big = tk.Label(self, text="", bg="#000000", fg="#FFFFFF",
                            font=tv_font(40, True))
        self.big.place(relx=0.985, y=self.TOP_H + 14, anchor="ne")

        # 底部悬浮控制栏（对应 backcontroller：上一行节目单 + 一行按钮）。
        # 节目单并入控制栏：单独的面板会被 mpv 视频窗口持续压住（实测），
        # 而控制栏本身显示稳定
        self.bottom = tk.Frame(self, bg=CHROME_BG)
        self._bottom_widgets(self.bottom)
        self.bottom.lift()

        # 左侧两层列表（对应 tvLeftChannnelListLayout）
        self.overlay = tk.Frame(self, bg="#0B1020", highlightthickness=0)
        self._place_overlay()

        # 三个面板区域标记：鼠标点在其上时不当作「唤出」处理
        for w in (self.top, self.bottom, self.overlay):
            w._is_chrome = True

        self.group_col = tk.Frame(self.overlay, bg="#0B1020", width=self.GROUP_W)
        self.group_col.pack(side="left", fill="y")
        self.group_col.pack_propagate(False)
        tk.Label(self.group_col, text="频道分类", bg="#0B1020", fg=FG_DIM,
                 font=tv_font(10), anchor="w").pack(fill="x", padx=12, pady=(14, 6))
        self.group_canvas, self.group_inner = self._scroll(self.group_col, "#0B1020")

        self.ch_col = tk.Frame(self.overlay, bg="#141B33", width=self.CH_W)
        self.ch_col.pack(side="left", fill="y")
        self.ch_col.pack_propagate(False)
        self.ch_title = tk.Label(self.ch_col, text="频道", bg="#141B33", fg=FG,
                                 font=tv_font(11, True), anchor="w")
        self.ch_title.pack(fill="x", padx=12, pady=(14, 6))
        self.ch_canvas, self.ch_inner = self._scroll(self.ch_col, "#141B33")

        self.loading = tk.Label(self, text="正在加载频道列表...", bg="#000000",
                                fg=FG_DIM, font=tv_font(14))
        self.loading.place(relx=0.5, rely=0.5, anchor="center")

        self.bind("<Configure>", self._on_resize)
        self._tick_clock()
        self._bind_keys()
        self.after(150, self._load)

    # ------------------------------------------------ 顶栏 / 控制栏 ----
    def _top_widgets(self, top):
        """顶部常驻：返回按钮 + 直播源信息（对应 tv_top_status）"""
        FocusLabel(top, text="← 返回", font=tv_font(12, True), bg=PANEL_HI,
                   fg="#FFFFFF", on_select=self._stop_and_back,
                   padx=14, pady=5).pack(side="left", padx=(12, 10), pady=8)
        self.status = tk.Label(top, text="加载频道中...", bg=CHROME_BG, fg=FG_DIM,
                               font=tv_font(11), anchor="w")
        self.status.pack(side="left", padx=(2, 12))
        self.clock = tk.Label(top, text="", bg=CHROME_BG, fg=FG_DIM,
                              font=tv_font(11))
        self.clock.pack(side="right", padx=14)

    def _bottom_widgets(self, b):
        """底部悬浮控制栏：上一行节目单（对应 ll_epg：台号+台名+当前/下一节目），
        下一行操作按钮（对应 backcontroller）；按钮右对齐，左侧留给频道列表"""
        # ---- 节目单行 ----
        epg_row = tk.Frame(b, bg=CHROME_BG)
        epg_row.pack(fill="x", pady=(4, 0))
        self.num_lbl = tk.Label(epg_row, text="", bg=CHROME_BG, fg=ACCENT,
                                font=tv_font(24, True), width=3, anchor="e")
        self.num_lbl.pack(side="left", padx=(16, 8))
        left = tk.Frame(epg_row, bg=CHROME_BG)
        left.pack(side="left")
        self.epg_name = tk.Label(left, text="", bg=CHROME_BG, fg=FG,
                                 font=tv_font(13, True), anchor="w")
        self.epg_name.pack(anchor="w")
        self.epg_src = tk.Label(left, text="", bg=CHROME_BG, fg=FG_DIM,
                                font=tv_font(9), anchor="w")
        self.epg_src.pack(anchor="w")
        right = tk.Frame(epg_row, bg=CHROME_BG)
        right.pack(side="left", padx=24)
        self.epg_cur = tk.Label(right, text="", bg=CHROME_BG, fg=FG,
                                font=tv_font(12), anchor="w")
        self.epg_cur.pack(anchor="w")
        self.epg_next = tk.Label(right, text="", bg=CHROME_BG, fg=FG_DIM,
                                 font=tv_font(10), anchor="w")
        self.epg_next.pack(anchor="w")
        # ---- 按钮行 ----
        row = tk.Frame(b, bg=CHROME_BG)
        row.pack(side="bottom", anchor="e", padx=14, pady=(2, 8))
        self.pause_btn = self._bar_btn(row, "⏸ 暂停", self._toggle_pause)
        self._bar_btn(row, "⏮ 上一台", lambda: self._step_channel(-1))
        self._bar_btn(row, "⏭ 下一台", lambda: self._step_channel(1))
        self._bar_btn(row, "⇄ 换源", self._switch_source)
        self._bar_btn(row, "☰ 频道列表", self._toggle_list)
        self._bar_btn(row, "⛶ 窗口/全屏", self._toggle_fullscreen)
        self._bar_btn(row, "✕ 退出直播", self._stop_and_back, accent=True)

    def _bar_btn(self, parent, text, cb, accent=False):
        w = FocusLabel(parent, text=text, font=tv_font(12), bg=ACCENT if accent else PANEL_HI,
                       fg="#FFFFFF", on_select=cb, padx=14, pady=6)
        w.pack(side="left", padx=5, pady=4)
        return w

    def _tick_clock(self):
        """顶部时钟（对应 tvTime）"""
        import time as _t
        try:
            self.clock.configure(text=_t.strftime("%H:%M:%S"))
        except Exception:
            return
        self._clock_job = self.after(1000, self._tick_clock)

    def _on_resize(self, e):
        if self._visible:
            self._place_overlay()

    def _place_overlay(self):
        # 底部给控制栏（节目单 + 按钮）留位，列表不会被压住
        h = max(120, (self.winfo_height() or 720) - self.TOP_H - self.BAR_H)
        self.overlay.place(x=0, y=self.TOP_H, width=self.GROUP_W + self.CH_W,
                           height=h, relheight=0)
        self.overlay.lift()

    # ------------------------------------------------ 列表容器 ----
    def _scroll(self, parent, bg):
        """竖排可滚动列表（Canvas + 内嵌 Frame）"""
        c = tk.Canvas(parent, bg=bg, highlightthickness=0, bd=0)
        c.pack(fill="both", expand=True)
        inner = tk.Frame(c, bg=bg)
        win = c.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: c.configure(scrollregion=c.bbox("all")))
        c.bind("<Configure>", lambda e: c.itemconfigure(win, width=e.width))
        c.bind("<MouseWheel>",
               lambda e: c.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        return c, inner

    # ------------------------------------------------ 数据加载 ----
    def _load(self):
        """优先自定义直播源（HawkConfig.LIVE_API_URL），否则用接口配置的 lives"""
        def run():
            name, chs = None, []
            custom = str(hawk.get(hawk.LIVE_API_URL, "") or "").strip()
            if custom:
                try:
                    name, chs = parse_live_source(read_live_source(custom), custom)
                except Exception:
                    name, chs = None, []
                if not chs:
                    name = None
            if not chs:
                for l in apiconfig.api_config.lives:
                    url = str(l.get("url", ""))
                    if str(l.get("type", "0")) != "0" or not url:
                        continue
                    if "127.0.0.1" in url or "localhost" in url:
                        continue  # 原版内置代理，不可用
                    try:
                        text = apiconfig.fetch_text(url)
                    except Exception:
                        continue
                    chs = _parse_live_text(text)
                    if chs:
                        name = l.get("name", "直播")
                        break
            ui_thread.run(lambda: self._render(chs, name))
        threading.Thread(target=run, daemon=True).start()

    def _render(self, chs, name):
        try:
            self.loading.destroy()
        except Exception:
            pass
        if not chs:
            tk.Label(self, text="当前接口配置不含可用直播源\n\n"
                                "可在「设置 › 配置地址」里填写直播源（txt/m3u）",
                     bg="#000000", fg=FG, font=tv_font(14)).place(
                relx=0.5, rely=0.5, anchor="center")
            self.status.configure(text="无可用直播源")
            return
        self.channels = chs
        self.groups = []
        for g, n, u in chs:
            if g not in self.groups:
                self.groups.append(g)
        self.status.configure(
            text=f"{name or '直播'} · {len(self.groups)} 个分组 · {len(chs)} 个频道")
        self._build_groups()
        first = self._pick_default()
        self._select_group(first[0])
        self.update_idletasks()
        self._play(first)          # 进入即自动播放（对应 initLiveState）
        self._show_overlay()
        self._reset_hide()

    def _pick_default(self):
        """默认频道：上次播放 → CCTV1 → 第一个频道（对应 Java initLiveState）"""
        last = hawk.get(hawk.LIVE_CHANNEL)
        if isinstance(last, dict):
            name, group = last.get("name"), last.get("group")
        else:
            name, group = last, None
        if name:
            for c in self.channels:
                if c[1] == name and (not group or c[0] == group):
                    return c
        for kw in ("CCTV1", "CCTV-1", "CCTV1综合", "CCTV-1综合"):
            for c in self.channels:
                if c[1].replace(" ", "").upper() == kw.upper():
                    return c
        return self.channels[0]

    # ------------------------------------------------ 一级：分组列 ----
    def _build_groups(self):
        for b, _ in self._group_btns:
            b.destroy()
        self._group_btns = []
        for g in self.groups:
            cnt = sum(1 for c in self.channels if c[0] == g)
            b = FocusLabel(self.group_inner, text=f"{g}　{cnt}", bg="#0B1020", fg=FG,
                           font=tv_font(11), padx=12, pady=7, anchor="w")
            b.on_select = lambda gg=g: self._pick_group(gg)
            b.pack(fill="x", padx=4, pady=1)
            b.bind("<FocusIn>", lambda e, gg=g: self._group_focused(gg), add="+")
            self._group_btns.append((b, g))

    def _group_focused(self, g):
        """分组列上下移动即切组并播放该组第一个频道（对应原版分组选中即切换）"""
        if g != self.cur_group:
            self._select_group(g, play=True)

    def _pick_group(self, g):
        """点击/回车分组：切组播放第一个，焦点进入二级频道列"""
        self._select_group(g, play=True)
        if self._ch_btns:
            self._ch_btns[0][0].focus_set()
            self._ensure_visible(self.ch_canvas, self._ch_btns[0][0])

    # ------------------------------------------------ 二级：频道列 ----
    def _select_group(self, group, play=False, play_index=0):
        """切换分组 → 重建二级频道列（对应 selectChannelGroup）"""
        self.cur_group = group
        self.ch_title.configure(text=group)
        for b, _ in self._ch_btns:
            b.destroy()
        self._ch_btns = []
        chs = [c for c in self.channels if c[0] == group]
        for i, c in enumerate(chs):
            # 编号用全局台号（与数字键选台一致，对应原版 selectedChannelNumber）
            num = self.ch_number(c)
            b = FocusLabel(self.ch_inner,
                           text=f"{'▶' if self._is_cur(c) else '　'} {num:>3}  {c[1]}",
                           bg="#141B33", fg=FG, font=tv_font(11),
                           padx=10, pady=6, anchor="w")
            b.on_select = lambda cc=c: self._play(cc)
            b.pack(fill="x", padx=4, pady=1)
            b.bind("<FocusIn>", lambda e, cc=c: self._channel_focused(cc), add="+")
            self._ch_btns.append((b, c))
        try:
            self.ch_canvas.yview_moveto(0)
        except Exception:
            pass
        if play and chs:
            self._play(chs[min(max(play_index, 0), len(chs) - 1)])
        return chs

    def _channel_focused(self, c):
        """频道列上下移动即换台（原版频道选中即播放）"""
        if not self._is_cur(c):
            self._play(c)

    def _is_cur(self, c):
        return bool(self.cur_ch) and self.cur_ch[1] == c[1] and self.cur_ch[0] == c[0]

    def ch_number(self, c):
        """频道台号（全局序号，1 起；对应原版 LiveChannelItem 的序号）"""
        try:
            return self.channels.index(c) + 1
        except ValueError:
            return 0

    def _mark_current(self):
        """刷新二级列表当前频道标记（不重建控件，避免丢焦点）"""
        for b, c in self._ch_btns:
            text = b.cget("text")
            body = text.lstrip("▶　 ")
            b.configure(text=f"{'▶' if self._is_cur(c) else '　'} {body}")

    # ------------------------------------------------ 播放 ----
    def _play(self, ch, src_idx=0):
        g, n, srcs = ch
        if not srcs:
            return
        self.cur_ch = ch
        self.cur_group = g
        self.cur_src = src_idx % len(srcs)
        u, src_name = srcs[self.cur_src]
        try:
            self.update_idletasks()
            if not self.player:
                self.player = MpvPlayer(
                    self.video, insets=(self.TOP_H, 0, self.BAR_H, 0))
                self._raise_chrome()   # mpv 视频窗口会盖住后 place 的面板，必须重置 z 序
            self.player.play(u)
        except Exception as e:
            self.status.configure(text=f"播放失败：{e}")
            return
        self.big.configure(text=n)
        extra = f" · 线路 {self.cur_src + 1}/{len(srcs)}" if len(srcs) > 1 else ""
        self.status.configure(text=f"{g} · {n} · {src_name}{extra}")
        hawk.put(hawk.LIVE_CHANNEL, {"group": g, "name": n})  # 记忆上次频道
        # 底部节目单条：台号 + 台名 + 线路（对应 ll_epg / channelinfo）
        self.num_lbl.configure(text=f"{self.ch_number(ch):02d}" if self.ch_number(ch) else "")
        self.epg_name.configure(text=n)
        self.epg_src.configure(text=f"{g} · {src_name}{extra}")
        self._mark_current()
        self._load_epg(ch)
        self._reset_hide()

    # ------------------------------------------------ 节目单 ----
    def _load_epg(self, ch):
        """后台拉取节目单（对应原版 getEpg），切台后更新底部两条节目"""
        self._epg_seq += 1
        seq, name = self._epg_seq, ch[1]
        self.epg_cur.configure(text="节目单加载中...", fg=FG_DIM)
        self.epg_next.configure(text="")

        def run():
            progs = []
            try:
                progs = epg.load(name)
            except Exception:
                pass
            cur, nxt = epg.current_next(progs)
            ui_thread.run(lambda: self._show_epg(seq, progs, cur, nxt))
        threading.Thread(target=run, daemon=True).start()

    def _show_epg(self, seq, progs, cur, nxt):
        """渲染当前/下一节目（对应原版 showBottomEpg）"""
        if seq != self._epg_seq:      # 已切到别的台，丢弃过期结果
            return
        self._epg_progs = progs or []
        self._schedule_epg_tick()
        if not progs:
            self.epg_cur.configure(text="暂无节目单（可在直播源 m3u 头配置 x-tvg-url）",
                                   fg=FG_DIM)
            self.epg_next.configure(text="")
            return
        if cur:
            self.epg_cur.configure(
                text=f"▶ {cur['title']}  {epg.hhmm(cur['start'])}-{epg.hhmm(cur['stop'])}",
                fg=FG)
        else:
            self.epg_cur.configure(text="当前时段暂无节目信息", fg=FG_DIM)
        if nxt:
            self.epg_next.configure(
                text=f"下一个 {nxt['title']}  {epg.hhmm(nxt['start'])}-{epg.hhmm(nxt['stop'])}")
        else:
            self.epg_next.configure(text="")

    def _raise_chrome(self):
        """把 UI 面板重新置顶：mpv 的视频子窗口创建后会把自己顶到 z 序最上，
        盖住晚于它显示的面板（节目单条因此整条被盖）"""
        self.top.lift()
        if self._visible:
            self.bottom.lift()
            self.overlay.lift()
        self.update_idletasks()

    def _schedule_epg_tick(self):
        """节目到点自动换行（每分钟用已取到的节目单重算，不再发请求）"""
        if self._epg_job:
            try:
                self.after_cancel(self._epg_job)
            except Exception:
                pass
        self._epg_job = self.after(60000, self._epg_tick)

    def _epg_tick(self):
        self._epg_job = None
        if self._epg_progs and self.cur_ch:
            cur, nxt = epg.current_next(self._epg_progs)
            self._show_epg(self._epg_seq, self._epg_progs, cur, nxt)
        else:
            self._schedule_epg_tick()

    def _switch_source(self):
        """换源（对应 playNextSource）"""
        if self.cur_ch and len(self.cur_ch[2]) > 1:
            self._play(self.cur_ch, (self.cur_src + 1) % len(self.cur_ch[2]))

    def _step_channel(self, delta):
        """CH+ / CH-：跨分组前后换台"""
        if not self.channels:
            return
        i = self.channels.index(self.cur_ch) if self.cur_ch in self.channels else -1
        ch = self.channels[(i + delta) % len(self.channels)]
        if ch[0] != self.cur_group:
            self._select_group(ch[0])
        self._play(ch)

    # ------------------------------------------------ 键盘 ----
    def _bind_keys(self):
        hotkeys = {
            "<Up>": lambda: self._move(-1),
            "<Down>": lambda: self._move(1),
            "<Left>": self._to_groups,        # 回到一级分组列
            "<Right>": self._to_channels,     # 进入二级频道列
            "<Prior>": lambda: self._step_channel(-1),
            "<Next>": lambda: self._step_channel(1),
            "<Key-r>": self._switch_source,
            "<Key-R>": self._switch_source,
            "<Key-p>": self._toggle_pause,
            "<Key-P>": self._toggle_pause,
            "<Key-f>": self._toggle_fullscreen,
            "<Key-F>": self._toggle_fullscreen,
        }
        for seq, cb in hotkeys.items():
            try:
                fid = self.app.bind(seq, lambda e, c=cb: (self._wake(), c(), "break")[2],
                                    add="+")
                self._app_binds.append((seq, fid))
            except Exception:
                pass
        # Esc / BackSpace 单独绑定：不能先 _wake()，否则会把列表重新弹出来，
        # _back() 看到列表可见就只收起列表，永远走不到退出分支（旧 bug）。
        for seq in ("<Escape>", "<BackSpace>"):
            try:
                fid = self.app.bind(seq, lambda e: (self._back(), "break")[1], add="+")
                self._app_binds.append((seq, fid))
            except Exception:
                pass
        for d in "0123456789":
            try:
                fid = self.app.bind(d, lambda e, k=d: (self._wake(), self._digit(k),
                                                       "break")[2], add="+")
                self._app_binds.append((d, fid))
            except Exception:
                pass
        for seq in ("<Motion>", "<Button-1>"):
            try:
                fid = self.app.bind(seq, self._on_pointer, add="+")
                self._app_binds.append((seq, fid))
            except Exception:
                pass

    @staticmethod
    def _in_chrome(w):
        """控件是否位于顶栏/控制栏/频道列表内部"""
        while w is not None:
            if isinstance(w, (tk.Frame, tk.Toplevel)) and getattr(w, "_is_chrome", False):
                return True
            w = getattr(w, "master", None)
        return False

    def _on_pointer(self, e):
        """鼠标移动/点击唤出面板；点在面板自身（如「☰ 频道列表」）时只重置
        隐藏计时，否则 toplevel 的点击回调会把刚收起的面板又弹出来"""
        if self._in_chrome(getattr(e, "widget", None)):
            self._reset_hide()
            return
        self._wake()

    def _focus_area(self):
        w = self.focus_get()
        for b, _ in self._ch_btns:
            if b is w:
                return "channel"
        for b, _ in self._group_btns:
            if b is w:
                return "group"
        return "channel" if self._ch_btns else "group"

    @staticmethod
    def _idx_of(pairs, w):
        for i, (b, _) in enumerate(pairs):
            if b is w:
                return i
        return -1

    def _move(self, delta):
        if self._focus_area() == "channel" and self._ch_btns:
            i = self._idx_of(self._ch_btns, self.focus_get())
            i = 0 if i < 0 else max(0, min(len(self._ch_btns) - 1, i + delta))
            self._ch_btns[i][0].focus_set()
            self._ensure_visible(self.ch_canvas, self._ch_btns[i][0])
        elif self._group_btns:
            i = self._idx_of(self._group_btns, self.focus_get())
            i = 0 if i < 0 else max(0, min(len(self._group_btns) - 1, i + delta))
            self._group_btns[i][0].focus_set()
            self._ensure_visible(self.group_canvas, self._group_btns[i][0])

    def _to_groups(self):
        if not self._group_btns:
            return
        for b, g in self._group_btns:
            if g == self.cur_group:
                b.focus_set()
                self._ensure_visible(self.group_canvas, b)
                return
        self._group_btns[0][0].focus_set()

    def _to_channels(self):
        if not self._ch_btns:
            return
        for b, c in self._ch_btns:
            if self._is_cur(c):
                b.focus_set()
                self._ensure_visible(self.ch_canvas, b)
                return
        self._ch_btns[0][0].focus_set()

    def _digit(self, d):
        """数字键选台（全局频道序号，1.2 秒内连按组成台号）"""
        self._digits += d
        self.big.configure(text=self._digits)
        if self._digit_job:
            try:
                self.after_cancel(self._digit_job)
            except Exception:
                pass
        self._digit_job = self.after(1200, self._digit_go)

    def _digit_go(self):
        num, self._digits, self._digit_job = self._digits, "", None
        if not num or not self.channels:
            return
        try:
            i = int(num) - 1
        except ValueError:
            return
        if 0 <= i < len(self.channels):
            ch = self.channels[i]
            if ch[0] != self.cur_group:
                self._select_group(ch[0])
            self._play(ch)
        else:
            self.big.configure(text="")

    # ------------------------------------------------ 列表显隐 ----
    def _wake(self):
        if not self._visible:
            self._show_overlay()
        self._reset_hide()

    def _reset_hide(self):
        if self._hide_job:
            try:
                self.after_cancel(self._hide_job)
            except Exception:
                pass
        self._hide_job = self.after(self.HIDE_MS, self._hide_overlay)

    def _show_overlay(self, _e=None):
        self._place_overlay()
        self.bottom.place(x=0, rely=1.0, relwidth=1.0, height=self.BAR_H, anchor="sw")
        self.top.lift()
        self.bottom.lift()
        self.overlay.lift()
        self._visible = True

    def _hide_overlay(self):
        self._hide_job = None
        if not self._visible:
            return
        self.overlay.place_forget()
        self.bottom.place_forget()
        self._visible = False
        self.focus_set()

    def _toggle_list(self):
        """☰ 频道列表：显隐两层列表（对应原版左右方向键呼出侧栏）"""
        if self._visible:
            self._hide_overlay()
        else:
            self._show_overlay()
            self._to_channels()
        self._reset_hide()

    def _toggle_pause(self):
        """直播暂停/继续（对应原版 iv_playpause）"""
        if not self.player:
            return
        paused = self.player.toggle_pause()
        try:
            self.pause_btn.configure(text="▶ 播放" if paused else "⏸ 暂停")
        except Exception:
            pass
        self.status.configure(text="已暂停" if paused else
                              f"{self.cur_group} · {self.cur_ch[1] if self.cur_ch else ''}")
        self._wake()

    def _toggle_fullscreen(self):
        """窗口/全屏切换（对应原版 F 键）"""
        try:
            self.app.attributes("-fullscreen", not self.app.attributes("fullscreen"))
        except Exception:
            pass
        self._wake()

    @staticmethod
    def _ensure_visible(canvas, w):
        """焦点项滚动到可视区"""
        try:
            canvas.update_idletasks()
            box = canvas.bbox("all")
            total = (box[3] if box else 0) or 1
            view_h = canvas.winfo_height() or 1
            if total <= view_h:
                return
            top, h = w.winfo_y(), (w.winfo_height() or 1)
            cur = canvas.yview()[0]
            ratio = view_h / total
            if top / total < cur:
                canvas.yview_moveto(max(0.0, top / total))
            elif (top + h) / total > cur + ratio:
                canvas.yview_moveto(min(1.0 - ratio, (top + h) / total - ratio))
        except Exception:
            pass

    # ------------------------------------------------ 生命周期 ----
    def _back(self):
        """Esc / BackSpace（对应原版 onBackPressed）：列表开着先收起，
        再按一次退出直播。顶栏「← 返回」按钮则是直接退出。"""
        if self._visible:
            self._hide_overlay()
            self.status.configure(text="再按 Esc 退出直播")
            self.after(2000, self._restore_status)
            return
        self._stop_and_back()

    def _restore_status(self):
        if self.cur_ch:
            self.status.configure(text=f"{self.cur_ch[0]} · {self.cur_ch[1]}")

    def _stop_and_back(self):
        from .ui_grid import Page as GridPage
        self.app.go_back(GridPage)

    def _stop_player(self):
        if self.player:
            try:
                self.player.terminate()
            except Exception:
                pass
            self.player = None

    def destroy(self):
        for seq, fid in getattr(self, "_app_binds", []):
            try:
                self.app.unbind(seq, fid)
            except Exception:
                pass
        self._app_binds = []
        for job in (self._hide_job, self._digit_job, self._clock_job, self._epg_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._hide_job = self._digit_job = self._clock_job = self._epg_job = None
        try:
            self.app.attributes("-fullscreen", self._was_full)
        except Exception:
            pass
        self._stop_player()
        super().destroy()
