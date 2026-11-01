"""直播页 LivePlayActivity 复刻：txt/m3u 频道列表解析 + mpv 播放 + 分组/换台"""
import os
import threading
import tkinter as tk

from . import apiconfig, hawk, ui_thread
from .player import MpvPlayer
from .theme import BG, FG, FG_DIM, FocusLabel, tv_font, grid_key_nav, PANEL, ACCENT


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
    """对应 ui/activity/LivePlayActivity.java（简化：分组tab + 频道网格 + 播放）"""

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.channels = []      # [(group, name, [(url, src)...])]
        self.groups = []        # [group]
        self.cur_group = None
        self.cur_ch = None      # 当前播放频道 (g, n, srcs)
        self.cur_src = 0        # 当前线路下标
        self.player = None

        # 顶栏与点播首页（ui_grid）平行：← + ACCENT 大标题（直播源名）
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", pady=(8, 2))
        FocusLabel(bar, text="←", font=tv_font(14, True),
                   on_select=app.go_home).pack(side="left", padx=(20, 6))
        self.title = tk.Label(bar, text="直播", bg=BG, fg=ACCENT, font=tv_font(16, True))
        self.title.pack(side="left")
        self.status = tk.Label(bar, text="加载频道中...", bg=BG, fg=FG_DIM,
                               font=tv_font(11))
        self.status.pack(side="right", padx=16)

        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True)
        # 换台键（对应 Java 上下键 playPre/playNext 频道）+ 数字键选台
        self.bind("<Up>", lambda e: self._play_pre())
        self.bind("<Down>", lambda e: self._play_next())
        for d in "0123456789":
            self.bind(d, lambda e, ch=d: self._digit(ch))
        self._digits = ""
        self._digit_job = None
        self.bind("<Escape>", lambda e: self._stop_and_back())
        self.after(100, self._load)

    def _digit(self, ch):
        """数字键选台（对应 Java 数字遥控器选台，1.2 秒内连按组成台号）"""
        self._digits += ch
        self.status.configure(text=f"选台：{self._digits}")
        if self._digit_job:
            self.after_cancel(self._digit_job)
        self._digit_job = self.after(1200, self._digit_go)

    def _digit_go(self):
        num = self._digits
        self._digits = ""
        self._digit_job = None
        if not num or not self.channels:
            return
        chs = [c for c in self.channels if c[0] == self.cur_group] or self.channels
        try:
            idx = int(num) - 1
        except ValueError:
            return
        if 0 <= idx < len(chs):
            self._play(chs[idx])
        else:
            self.status.configure(text=f"无 {num} 号频道")

    # ---------- 数据加载 ----------
    def _live_url(self):
        for l in apiconfig.api_config.lives:
            if str(l.get("type", "0")) == "0" and l.get("url"):
                return l["url"], l.get("name", "直播")
        return None, None

    def _load(self):
        # 优先使用设置里自定义的直播源（对应 HawkConfig.LIVE_API_URL），
        # 未设置或解析失败则回落到接口配置里的 lives
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

    def _render(self, chs, name=None):
        if name:
            self.title.configure(text=name)
        else:
            self.status.configure(text="配置无可用直播源")
            tk.Label(self.body, text="当前接口配置不含可用直播源", bg=BG, fg=FG,
                     font=tv_font(14)).pack(expand=True)
            return
        self.channels = chs
        self.groups = []
        for g, n, u in chs:
            if g not in self.groups:
                self.groups.append(g)
        self.status.configure(text=f"{len(chs)} 个频道")
        if not chs:
            tk.Label(self.body, text="频道列表为空", bg=BG, fg=FG,
                     font=tv_font(14)).pack(expand=True)
            return
        # 恢复上次频道（对应 Java HawkConfig.LIVE_CHANNEL 记忆）
        last = hawk.get(hawk.LIVE_CHANNEL)
        if last:
            match = [c for c in chs if c[0] == last.get("group") and
                     c[1] == last.get("name")]
            if match:
                hint = tk.Frame(self.body, bg=BG)
                hint.pack()
                FocusLabel(hint, text=f"▶ 继续上次：{last.get('name')}",
                           bg=ACCENT, fg="#FFFFFF", font=tv_font(13, True),
                           on_select=lambda c=match[0]: (hint.destroy(),
                                                         self._play(c))
                           ).pack(pady=6)
        self._show_groups()

    # ---------- 分组列表 ----------
    def _show_groups(self):
        for w in self.body.winfo_children():
            w.destroy()
        self._stop_player()
        inner = tk.Frame(self.body, bg=BG)
        inner.pack(expand=True)
        tk.Label(inner, text="选择频道分组", bg=BG, fg=FG_DIM,
                 font=tv_font(13)).grid(row=0, column=0, columnspan=6, pady=8)
        btns = []
        for i, g in enumerate(self.groups):
            b = FocusLabel(inner, text=g[:10], bg=PANEL, fg=FG,
                           font=tv_font(13), padx=18, pady=10,
                           on_select=lambda gg=g: self._show_channels(gg))
            b.grid(row=(i + 1) // 6, column=(i + 1) % 6, padx=6, pady=6)
            btns.append(b)
        grid_key_nav(btns, 6)
        if btns:
            btns[0].focus_set()

    # ---------- 频道网格 ----------
    def _show_channels(self, group):
        self.cur_group = group
        for w in self.body.winfo_children():
            w.destroy()
        self._stop_player()
        chs = [c for c in self.channels if c[0] == group]
        inner = tk.Frame(self.body, bg=BG)
        inner.pack(fill="both", expand=True)
        bar = tk.Frame(inner, bg=BG)
        bar.pack(fill="x")
        FocusLabel(bar, text="‹ 分组", font=tv_font(11),
                   on_select=self._show_groups).pack(side="left", padx=10, pady=4)
        tk.Label(bar, text=f"{group}（{len(chs)}）", bg=BG, fg=FG_DIM,
                 font=tv_font(12)).pack(side="left")
        grid = tk.Frame(inner, bg=BG)
        grid.pack(expand=True)
        btns = []
        for i, (g, n, u) in enumerate(chs):
            b = FocusLabel(grid, text=n[:14], bg=PANEL, fg=FG,
                           font=tv_font(12), padx=14, pady=8,
                           on_select=lambda c=(g, n, u): self._play(c))
            b.grid(row=i // 6, column=i % 6, padx=5, pady=5)
            btns.append(b)
        grid_key_nav(btns, 6)
        if btns:
            btns[0].focus_set()

    # ---------- 播放 ----------
    def _play(self, ch, src_idx=0):
        g, n, srcs = ch
        self.cur_ch, self.cur_src = ch, src_idx % len(srcs)
        u, src_name = srcs[self.cur_src]
        for w in self.body.winfo_children():
            w.destroy()
        video = tk.Frame(self.body, bg="#000000", highlightthickness=0)
        video.pack(fill="both", expand=True)
        bar = tk.Frame(self.body, bg="#000000")
        bar.pack(fill="x")
        FocusLabel(bar, text="← 返回频道", font=tv_font(12, True),
                   on_select=self._show_channels_cur).pack(side="left", padx=12, pady=6)
        tk.Label(bar, text=n, bg="#000000", fg=FG, font=tv_font(13, True)
                 ).pack(side="left", padx=10)
        if len(srcs) > 1:  # 频道多源切换（对应 playNextSource/playPreSource）
            FocusLabel(bar, text="⟳ 换源", font=tv_font(12),
                       on_select=lambda: self._play(
                           self.cur_ch, (self.cur_src + 1) % len(srcs))
                       ).pack(side="right", padx=12, pady=6)
        tk.Label(bar, text=src_name, bg="#000000", fg=FG_DIM,
                 font=tv_font(11)).pack(side="right")
        self.status.configure(text=f"正在播放 {n} · {src_name}")
        self._ensure_player(int(video.winfo_id()))
        self.player.play(u)
        # 记忆上次频道（对应 HawkConfig.LIVE_CHANNEL）
        hawk.put(hawk.LIVE_CHANNEL, {"group": g, "name": n})

    def _ch_index(self):
        """当前频道在分组频道列表中的下标（用于上下键换台）"""
        chs = [c for c in self.channels if c[0] == self.cur_group]
        if self.cur_ch in chs:
            return chs.index(self.cur_ch), chs
        return -1, chs

    def _play_pre(self):
        if not self.cur_ch:
            return
        idx, chs = self._ch_index()
        if chs:
            self._play(chs[(idx - 1) % len(chs)])

    def _play_next(self):
        if not self.cur_ch:
            return
        idx, chs = self._ch_index()
        if chs:
            self._play(chs[(idx + 1) % len(chs)])

    def _show_channels_cur(self):
        self._stop_player()
        if self.cur_group:
            self._show_channels(self.cur_group)
        else:
            self._show_groups()

    def _ensure_player(self, wid):
        if not self.player:
            self.player = MpvPlayer(wid)

    def _stop_player(self):
        if self.player:
            self.player.terminate()
            self.player = None

    def _stop_and_back(self):
        self._stop_player()
        self.app.go_home()

    def destroy(self):
        self._stop_player()
        super().destroy()
