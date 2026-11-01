"""播放页 PlayActivity 复刻：mpv 播放 + 选集/线路切换 + 进度显示 + 历史记录"""
import os
import time
import threading
import tkinter as tk
import urllib.parse

from . import hawk, store, ui_thread
from .paths import data_path
from .theme import ACCENT, BG, FG, FG_DIM, FocusLabel, tv_font
from .player import MpvPlayer

CHROME_BG = "#0B0F1C"   # 控制栏底色（近黑，覆在视频上）
BTN_BG = "#26325C"      # 按钮底色（theme.PANEL_HI）

# 起播看门狗：play() 后这么久还没出画面就当失败（对应原版解析超时 20s）
START_TIMEOUT_MS = 20000
# 解析看门狗：解析接口卡住超过这么久也当失败，避免「正在获取播放信息」无限等
RESOLVE_TIMEOUT_MS = 20000

# 倍速档位（对应原版 speedArray，补足 0.75/3.0）
SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
# 画面缩放档位（0 默认 / 1 16:9 / 2 4:3 / 3 填充 / 4 裁剪 / 5 原始）
SCALES = [0, 1, 2, 3, 4, 5]
# 选集面板每页个数（集数很多时避免一次创建上千个控件）
EPS_PER_PAGE = 60


class Failover:
    """播放失败后的重试/换线路决策（对应 PlayFragment.autoRetry + tryNextLineIfEnabled）

    与原版差异：桌面端只有一个播放内核，没有「换内核重试」这一步，所以先在本线路
    重载一次，再依次尝试其它线路的同一集；全部试完才交给用户手动重试。
    """

    def __init__(self, line_count, retry_same=1):
        self.line_count = max(1, int(line_count or 1))
        self.retry_same = retry_same
        self.reset()

    def reset(self):
        self.retries = 0
        self.failed = set()

    def next_action(self, line_index, ep_index, ep_counts):
        """返回 ("retry", None) / ("switch", 线路下标) / ("give_up", None)"""
        if self.retries < self.retry_same:
            self.retries += 1
            return "retry", None
        self.failed.add(line_index)
        for off in range(1, self.line_count):
            li = (line_index + off) % self.line_count
            if li in self.failed:
                continue
            if ep_index >= (ep_counts[li] if li < len(ep_counts) else 0):
                continue  # 该线路没有这一集
            self.retries = 0
            return "switch", li
        return "give_up", None


def _short_reason(text, limit=24):
    """异常信息压成一行短提示（完整内容仍写 error.log）"""
    s = " ".join(str(text or "播放失败").split())
    return s[:limit] + ("…" if len(s) > limit else "")


def resolve_source_text():
    """最近一次解析来源（直链/网页嗅探/解析接口名/爬虫），OSD 显示用"""
    try:
        from . import data_api
        kind = data_api.LAST_RESOLVE.get("kind") or ""
        name = data_api.LAST_RESOLVE.get("name") or ""
        return f"{kind} {name}".strip()
    except Exception:
        return ""


def _danmaku_ass_path():
    return data_path("danmaku.ass")


def _write_text(path, text):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8-sig") as f:
            f.write(text)
        os.replace(tmp, path)
        return path
    except OSError:
        return ""


def _write_danmaku_ass(text):
    """弹幕原文 → ASS 文件；解析为空返回空串"""
    from . import danmaku
    ass = danmaku.build_from_text(text)
    if not ass:
        return ""
    return _write_text(_danmaku_ass_path(), ass)


class Page(tk.Frame):
    """对应 ui/activity/PlayActivity.java"""

    def __init__(self, master, app, source_key, vod_id, vod_name,
                 play_flag, play_ep, play_url, series=None, ep_index=0,
                 vod_pic="", all_flags=None, all_urls=None, line_index=None):
        super().__init__(master, bg="#000000")
        self.app = app
        self.source_key, self.vod_id, self.vod_name = source_key, vod_id, vod_name
        self.vod_pic = vod_pic  # 写历史记录用（首页「观看历史」推荐位显示海报）
        self.play_flag, self.ep_index = play_flag, ep_index
        self.series = series  # ((flag, names), urls)
        # 详情页传入的全部线路：(flags, urls)，用于播放失败时自动换线
        self.all_flags = all_flags or []
        self.all_urls = all_urls or []
        self.line_index = line_index if isinstance(line_index, int) else 0
        self._failover = Failover(len(self.all_urls))
        self._cur_ep_url = play_url
        self._started = False       # 本次尝试是否真正出过画面
        self._watchdog = None       # 起播超时看门狗
        self._resolve_job = None    # 解析超时看门狗
        self.player = None
        self._pos_job = None
        self._hdr = None
        self._last_real = None
        self._seek_job = None
        self._save_job = None
        self._speed = 1.0
        self._speeds = SPEEDS
        self._scale = 0
        self._locked = False
        self._osd_on = False
        self._osd_job = None
        self._sub_path = None      # 用户加载的本地字幕，换集后自动重挂
        self._dm_path = None       # 弹幕合成的 ASS 文件
        self._dm_ep = None         # 弹幕对应的集名（避免重复拉取）
        self._app_binds = []
        self._seq = 0  # 播放请求序号：后台解析返回时页面可能已切集/销毁
        self._hide_job = None
        self._cur_pos = 0.0
        self._dur = 0.0
        self._t_start = None  # 起播计时（TVBOXPY_DEBUG 时打印）
        self._speed = self._initial_speed()
        try:
            self._scale = int(hawk.get(hawk.PLAY_SCALE, 0) or 0)
        except (TypeError, ValueError):
            self._scale = 0
        if self._scale not in SCALES:
            self._scale = 0

        # 全屏沉浸播放（对应原版 PlayActivity 全屏）：进入播放页自动全屏，
        # 返回时恢复之前的窗口状态
        self._was_full = False
        try:
            self._was_full = bool(self.app.attributes("fullscreen"))
            self.app.attributes("-fullscreen", True)
        except Exception:
            pass

        # 视频区域铺满整页；控制栏悬浮其上（自动隐藏）
        self.video = tk.Frame(self, bg="#000000", highlightthickness=0)
        self.video.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.video.configure(width=100, height=100)

        # 顶部信息栏（对应原版 tv_info_name1：片名 · 线路 · 集名）
        self.top = tk.Frame(self, bg=CHROME_BG)
        self.top.place(x=0, y=0, relwidth=1.0, height=42)
        self._top_widgets(self.top)
        self.top.lift()  # 与 video 重叠，必须保持在 mpv 之上

        # 底部控制栏（对应原版 bottom_container：按钮行 + 进度行）
        self.bottom = tk.Frame(self, bg=CHROME_BG)
        self.bottom.place(x=0, rely=1.0, relwidth=1.0, height=96, anchor="sw")
        self._bottom_widgets(self.bottom)
        self.bottom.lift()

        # 中下部提示（「正在获取播放信息...」等），不随控制栏隐藏
        self.status = tk.Label(self, text="", bg="#000000", fg=FG_DIM,
                               font=tv_font(12))
        self.status.place(relx=0.5, rely=0.86, anchor="center")
        # 失败提示可点击重试（对应原版 setTip 的点击重播）
        self.status.bind("<Button-1>", self._retry_now)

        # 右上角 OSD（分辨率/帧率/倍速/缓冲/时间），按 i 开关
        self.osd = tk.Label(self, text="", bg="#000000", fg="#DCEEFF",
                            justify="right", anchor="ne", font=tv_font(11))
        self.osd.bind("<Button-1>", lambda e: self._toggle_osd())

        # 锁屏遮罩（按 L 解锁）
        self.lock = tk.Label(self, text="🔒 已锁定\n按 L 键解锁", bg="#000000",
                             fg=FG_DIM, font=tv_font(18, True))
        self.lock.bind("<Button-1>", lambda e: self._toggle_lock())

        # 沉浸式控制栏：无操作 4 秒后隐藏，鼠标移动/按键/点击唤出
        for seq in ("<Motion>", "<Any-KeyPress>", "<Button-1>"):
            try:
                fid = self.app.bind(seq, self._show_chrome, add="+")
                self._app_binds.append((seq, fid))
            except Exception:
                pass
        self._show_chrome()

        # 播放快捷键（对应原版遥控器/键盘操作）；锁定后除 L 外全部屏蔽
        hotkeys = {
            "<space>": self._toggle_pause,      # 播放/暂停
            "<Left>": lambda: self._seek_rel(-10),
            "<Right>": lambda: self._seek_rel(10),
            "<Up>": lambda: self._volume_rel(5),
            "<Down>": lambda: self._volume_rel(-5),
            "<Prior>": self._prev_ep,           # PageUp 上一集
            "<Next>": self._next_ep,            # PageDown 下一集
            "<Key-f>": self._toggle_fullscreen,
            "<Key-F>": self._toggle_fullscreen,
            "<Key-i>": self._toggle_osd,
            "<Key-I>": self._toggle_osd,
        }
        for seq, cb in hotkeys.items():
            try:
                fid = self.app.bind(seq, self._guard(cb), add="+")
                self._app_binds.append((seq, fid))
            except Exception:
                pass
        # 锁屏键不经过 guard（否则锁上就解不开）
        for seq in ("<Key-l>", "<Key-L>"):
            try:
                fid = self.app.bind(seq, lambda e: (self._toggle_lock(), "break")[1],
                                    add="+")
                self._app_binds.append((seq, fid))
            except Exception:
                pass

        # Esc / BackSpace 也能返回（绑在顶层窗口，播放时焦点常在 mpv 子窗口，
        # 绑在本 Frame 上收不到按键）
        for seq in ("<Escape>", "<BackSpace>"):
            try:
                fid = self.app.bind(seq, self._back, add="+")
                self._app_binds.append((seq, fid))
            except Exception:
                pass
        self.focus_set()
        self.after(200, lambda: self._start(play_url))

    # ---- 控制栏构建（复刻原版 player_vod_control_view.xml） ----

    def _mk_btn(self, parent, text, cb, accent=False, side="left"):
        w = FocusLabel(parent, text=text, font=tv_font(12),
                       bg=ACCENT if accent else BTN_BG, fg="#FFFFFF",
                       on_select=cb, padx=14, pady=5)
        w.pack(side=side, padx=4)
        return w

    def _top_widgets(self, top):
        FocusLabel(top, text="← 返回", font=tv_font(12, True), bg=BTN_BG,
                   fg="#FFFFFF", on_select=self._back,
                   padx=12, pady=5).pack(side="left", padx=(12, 8), pady=7)
        self.info_lbl = tk.Label(
            top, text=f"{self.vod_name} · {self.play_flag} · "
                      f"{self.series[0][1][self.ep_index] if self.series else ''}",
            bg=CHROME_BG, fg=FG, font=tv_font(12, True))
        self.info_lbl.pack(side="left")

    def _bottom_widgets(self, b):
        row = tk.Frame(b, bg=CHROME_BG)
        row.pack(fill="x", padx=12, pady=(8, 4))
        self.play_btn = self._mk_btn(row, "⏸ 暂停", self._toggle_pause)
        self._mk_btn(row, "⏮ 上一集", self._prev_ep)
        self._mk_btn(row, "⏭ 下一集", self._next_ep)
        self._mk_btn(row, "↻ 重播", self._replay)
        self._mk_btn(row, "⛶ 窗口/全屏", self._toggle_fullscreen)
        self.vol_lbl = tk.Label(row, text="🔊 100", bg=CHROME_BG, fg=FG_DIM,
                                font=tv_font(11))
        self.vol_lbl.pack(side="left", padx=(12, 0))

        if self.series:
            self._mk_btn(row, "选集", self._show_series, side="right")
        if len(self.all_urls) > 1:
            self._mk_btn(row, "线路", self._show_lines, side="right")
        self.speed_btn = FocusLabel(row, text=f"倍速 {self._speed:g}x",
                                    font=tv_font(12), bg=BTN_BG, fg="#FFFFFF",
                                    on_select=self._cycle_speed, padx=14, pady=5)
        self.speed_btn.pack(side="right", padx=4)
        # 字幕/音轨/弹幕/画面/OSD/锁屏等次要功能收进「更多」，避免按钮溢出
        self._mk_btn(row, "更多 ▾", self._show_more, side="right")

        # 进度行：当前时间 | 进度条 | 总时长（对应 curr_time / seekBar / total_time）
        prow = tk.Frame(b, bg=CHROME_BG)
        prow.pack(fill="x", padx=14, pady=(0, 8))
        self.cur_lbl = tk.Label(prow, text="00:00", bg=CHROME_BG, fg=FG,
                                font=tv_font(11), width=7, anchor="e")
        self.cur_lbl.pack(side="left")
        self.seek = tk.Canvas(prow, bg=CHROME_BG, height=18,
                              highlightthickness=0)
        self.seek.pack(side="left", fill="x", expand=1, padx=10)
        self.tot_lbl = tk.Label(prow, text="00:00", bg=CHROME_BG, fg=FG_DIM,
                                font=tv_font(11), width=7, anchor="w")
        self.tot_lbl.pack(side="left")

        self._seeking = False
        self._seek_preview = 0.0
        self.seek.bind("<Button-1>", self._seek_click)
        self.seek.bind("<B1-Motion>", self._seek_drag)
        self.seek.bind("<ButtonRelease-1>", self._seek_release)
        self.seek.bind("<Configure>", lambda e: self._draw_seek(
            self._seek_preview if self._seeking else self._cur_pos, self._dur))

    def _draw_seek(self, pos, dur):
        """绘制进度条（已播放橙色 + 圆点 thumb），对应 shape_player_control_vod_seek"""
        c = self.seek
        w = max(c.winfo_width(), 10)
        cy, hh = 9, 3
        ratio = 0.0 if not dur else max(0.0, min(1.0, pos / dur))
        x = int(w * ratio)
        c.delete("all")
        c.create_rectangle(0, cy - hh, w, cy + hh, fill="#39415C", outline="")
        if x > 0:
            c.create_rectangle(0, cy - hh, x, cy + hh, fill=ACCENT, outline="")
        c.create_oval(x - 6, cy - 6, x + 6, cy + 6, fill=ACCENT, outline="")

    def _seek_to_event(self, e):
        w = max(self.seek.winfo_width(), 10)
        ratio = max(0.0, min(1.0, e.x / w))
        return ratio * (self._dur or 0)

    def _seek_click(self, e):
        if not self._dur:
            return "break"
        self._seeking = True
        self._seek_preview = self._seek_to_event(e)
        self.cur_lbl.configure(text=self._fmt(self._seek_preview))
        self._draw_seek(self._seek_preview, self._dur)
        self._show_chrome()
        return "break"

    def _seek_drag(self, e):
        if not self._seeking:
            return "break"
        self._seek_preview = self._seek_to_event(e)
        self.cur_lbl.configure(text=self._fmt(self._seek_preview))
        self._draw_seek(self._seek_preview, self._dur)
        return "break"

    def _seek_release(self, e):
        if not self._seeking:
            return "break"
        self._seeking = False
        pos = self._seek_to_event(e)
        if self.player and pos:
            self.player.seek(pos)
            self._cur_pos = pos
        self._show_chrome()
        return "break"

    def destroy(self):
        """页面被销毁时统一收尾：解绑全局快捷键、停掉定时任务、解绑播放器。

        不这样做的话，已销毁页面上的 after 回调/全局 <Motion> 绑定还会被触发，
        报 "bad window path name"（macOS 上更明显，因为播放窗口是独立窗口）"""
        for seq, fid in getattr(self, "_app_binds", []):
            try:
                self.app.unbind(seq, fid)
            except Exception:
                pass
        self._app_binds = []
        for job in (getattr(self, "_pos_job", None), getattr(self, "_seek_job", None),
                    getattr(self, "_save_job", None), getattr(self, "_hide_job", None),
                    getattr(self, "_watchdog", None), getattr(self, "_resolve_job", None),
                    getattr(self, "_osd_job", None)):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._pos_job = self._seek_job = self._save_job = self._hide_job = None
        self._watchdog = None
        self._resolve_job = None
        self._osd_job = None
        self._release_awake()
        try:
            if self.player:
                self.player.detach()
        except Exception:
            pass
        super().destroy()

    def _show_chrome(self, _e=None):
        """唤出控制栏并重置自动隐藏计时（沉浸式，对应原版触摸唤出控制栏）"""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if self._locked:      # 锁屏时不弹控制栏
            return
        self.top.place(x=0, y=0, relwidth=1.0, height=42)
        self.bottom.place(x=0, rely=1.0, relwidth=1.0, height=96, anchor="sw")
        self.top.lift()
        self.bottom.lift()
        if self._hide_job:
            try:
                self.after_cancel(self._hide_job)
            except Exception:
                pass
        self._hide_job = self.after(4000, self._hide_chrome)

    def _hide_chrome(self):
        self._hide_job = None
        if self._seeking:  # 拖动进度条时不隐藏
            self._hide_job = self.after(2000, self._hide_chrome)
            return
        self.top.place_forget()
        self.bottom.place_forget()

    # ---- 锁屏 / OSD / 画面比例 / 更多菜单（P1） ----

    def _guard(self, cb):
        """快捷键包装：锁屏时只放行锁屏键，其余按键吞掉"""
        def handler(_e=None):
            if self._locked:
                return "break"
            cb()
            return "break"
        return handler

    def _toggle_lock(self):
        self._locked = not getattr(self, "_locked", False)
        if self._locked:
            self.top.place_forget()
            self.bottom.place_forget()
            self.lock.place(x=0, y=0, relwidth=1.0, relheight=1.0)
            self.lock.lift()
        else:
            self.lock.place_forget()
            self._show_chrome()
        return "break"

    def _toggle_osd(self):
        self._osd_on = not self._osd_on
        if self._osd_on:
            self.osd.place(relx=1.0, x=-14, y=52, anchor="ne")
            self.osd.lift()
            self._update_osd()
            self.status.configure(text="OSD 已开启（i 关闭）")
            self.after(1500, lambda: self.status.configure(text=""))
        else:
            self.osd.place_forget()
            if self._osd_job:
                try:
                    self.after_cancel(self._osd_job)
                except Exception:
                    pass
                self._osd_job = None

    def _update_osd(self):
        self._osd_job = None
        if not self._osd_on:
            return
        lines = []
        try:
            if self.player:
                info = self.player.video_info()
                if info["width"] and info["height"]:
                    res = f"{info['width']}x{info['height']}"
                    if info["fps"]:
                        res += f" @{info['fps']:.2f}fps"
                    lines.append(res)
                if info["codec"]:
                    lines.append(info["codec"])
                lines.append(f"倍速 {self._speed:g}x · 画面 "
                             f"{MpvPlayer.scale_name(self._scale)}")
                spd = self.player.cache_speed()
                if spd > 0:
                    lines.append(f"缓冲 {spd / 1024 / 1024:.1f} MB/s")
                src = resolve_source_text()
                if src:
                    lines.append(f"解析来自 {src}")
        except Exception:
            pass
        lines.append(time.strftime("%H:%M:%S"))
        try:
            self.osd.configure(text="\n".join(lines))
        except tk.TclError:
            return
        self._osd_job = self.after(1000, self._update_osd)

    def _cycle_scale(self):
        """画面比例循环（对应原版 SCREEN_SCALE_* 六种模式）"""
        i = SCALES.index(self._scale) if self._scale in SCALES else 0
        self._scale = SCALES[(i + 1) % len(SCALES)]
        hawk.put(hawk.PLAY_SCALE, self._scale)
        if self.player:
            w = max(1, self.video.winfo_width())
            h = max(1, self.video.winfo_height())
            self.player.apply_scale(self.player.mpv, self._scale, (w, h))
        name = MpvPlayer.scale_name(self._scale)
        self.status.configure(text=f"画面：{name}")
        self.after(1500, lambda: self.status.configure(text=""))
        self._show_chrome()

    def _show_more(self):
        """更多功能面板：字幕/音轨/弹幕/画面/OSD/锁屏"""
        panel = tk.Toplevel(self)
        panel.title("更多")
        panel.configure(bg="#101010")
        try:
            panel.attributes("-topmost", True)  # 全屏时保持可见
        except Exception:
            pass
        items = [
            ("字幕", self._sub_menu),
            ("音轨", self._audio_menu),
            ("弹幕", self._danmaku_menu),
            ("画面比例", self._cycle_scale),
            ("显示信息 (i)", self._toggle_osd),
            ("锁屏 (L)", self._toggle_lock),
            ("关闭", panel.destroy),
        ]
        for i, (text, cb) in enumerate(items):
            FocusLabel(panel, text=text, bg="#1E1E1E", fg=FG, font=tv_font(11),
                       on_select=lambda c=cb, p=panel: (p.destroy(), c())
                       ).grid(row=i // 4, column=i % 4, padx=6, pady=6,
                              ipadx=10, ipady=2)

    # ---- 字幕（P1） ----

    def _sub_tracks(self):
        return [t for t in (self.player.track_list("sub") if self.player else [])
                if t.get("id") is not None]

    def _sub_menu(self):
        panel = tk.Toplevel(self)
        panel.title("字幕")
        panel.configure(bg="#101010")
        try:
            panel.attributes("-topmost", True)
        except Exception:
            pass
        row = 0
        FocusLabel(panel, text="关闭字幕", bg="#1E1E1E", fg=FG, font=tv_font(11),
                   on_select=lambda p=panel: (p.destroy(), self._sub_off())
                   ).grid(row=row, column=0, padx=6, pady=4, sticky="w")
        row += 1
        for t in self._sub_tracks():
            label = (t.get("title") or t.get("external-filename")
                     or f"字幕 {t.get('id')}")
            label = str(label).split("/")[-1][:28]
            FocusLabel(panel, text=label, bg="#1E1E1E", fg=FG, font=tv_font(11),
                       on_select=lambda p=panel, tid=t.get("id"):
                       (p.destroy(), self._pick_sub(tid))
                       ).grid(row=row, column=0, padx=6, pady=4, sticky="w")
            row += 1
        FocusLabel(panel, text="加载本地字幕…", bg="#1E1E1E", fg=FG,
                   font=tv_font(11),
                   on_select=lambda p=panel: (p.destroy(), self._load_sub_file())
                   ).grid(row=row, column=0, padx=6, pady=4, sticky="w")
        row += 1
        FocusLabel(panel, text="字幕延迟 -0.5s", bg="#1E1E1E", fg=FG,
                   font=tv_font(11),
                   on_select=lambda: self._sub_delay(-0.5)
                   ).grid(row=row, column=0, padx=6, pady=4, sticky="w")
        FocusLabel(panel, text="字幕延迟 +0.5s", bg="#1E1E1E", fg=FG,
                   font=tv_font(11),
                   on_select=lambda: self._sub_delay(0.5)
                   ).grid(row=row, column=1, padx=6, pady=4, sticky="w")
        row += 1
        FocusLabel(panel, text="字号 -2", bg="#1E1E1E", fg=FG, font=tv_font(11),
                   on_select=lambda: self._sub_font(-2)
                   ).grid(row=row, column=0, padx=6, pady=4, sticky="w")
        FocusLabel(panel, text="字号 +2", bg="#1E1E1E", fg=FG, font=tv_font(11),
                   on_select=lambda: self._sub_font(2)
                   ).grid(row=row, column=1, padx=6, pady=4, sticky="w")

    def _pick_sub(self, track_id):
        if self.player:
            self.player.set_track("sub", track_id)
            self.status.configure(text="已切换字幕")
            self.after(1500, lambda: self.status.configure(text=""))

    def _sub_off(self):
        if self.player:
            self.player.set_track("sub", None)
            self._sub_path = None
            self.status.configure(text="字幕已关闭")
            self.after(1500, lambda: self.status.configure(text=""))

    def _load_sub_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self, title="选择字幕文件",
            filetypes=[("字幕", "*.srt *.ass *.ssa *.vtt *.sub"),
                       ("全部文件", "*.*")])
        if not path:
            return
        self._sub_path = path
        if self.player:
            self.player.add_subtitle(path)

    def _sub_delay(self, delta):
        if not self.player:
            return
        val = round(self.player.get_sub_delay() + delta, 1)
        self.player.set_sub_delay(val)
        hawk.put(hawk.SUB_DELAY, val)
        self.status.configure(text=f"字幕延迟 {val:+.1f}s")
        self.after(1500, lambda: self.status.configure(text=""))

    def _sub_font(self, delta):
        if not self.player:
            return
        from .player import MpvPlayer as _P
        cur = int(hawk.get(hawk.SUB_FONT_SIZE, 0) or 0) or 42
        size = max(18, min(96, cur + delta))
        hawk.put(hawk.SUB_FONT_SIZE, size)
        self.player.set_sub_font_size(size)
        self.status.configure(text=f"字幕字号 {size}")
        self.after(1500, lambda: self.status.configure(text=""))

    # ---- 音轨（P1） ----

    def _audio_menu(self):
        if not self.player:
            return
        tracks = self.player.track_list("audio")
        if len(tracks) <= 1:
            self.status.configure(text="当前视频只有一条音轨")
            self.after(1500, lambda: self.status.configure(text=""))
            return
        panel = tk.Toplevel(self)
        panel.title("音轨")
        panel.configure(bg="#101010")
        try:
            panel.attributes("-topmost", True)
        except Exception:
            pass
        for i, t in enumerate(tracks):
            label = t.get("title") or t.get("lang") or f"音轨 {i + 1}"
            FocusLabel(panel, text=str(label)[:24], bg="#1E1E1E", fg=FG,
                       font=tv_font(11),
                       on_select=lambda p=panel, tid=t.get("id"):
                       (p.destroy(), self._pick_audio(tid))
                       ).grid(row=i, column=0, padx=6, pady=4, sticky="w")

    def _pick_audio(self, track_id):
        if self.player:
            self.player.set_track("audio", track_id)
            self.status.configure(text="已切换音轨")
            self.after(1500, lambda: self.status.configure(text=""))

    # ---- 弹幕（P1） ----

    def _danmaku_menu(self):
        panel = tk.Toplevel(self)
        panel.title("弹幕")
        panel.configure(bg="#101010")
        try:
            panel.attributes("-topmost", True)
        except Exception:
            pass
        on = bool(hawk.get(hawk.DANMAKU_ENABLE, 0))
        items = [
            ("关闭弹幕" if on else "开启弹幕", self._toggle_danmaku),
            ("加载本地弹幕…", self._load_danmaku_file),
            ("重新加载", self._reload_danmaku),
            ("关闭", panel.destroy),
        ]
        for i, (text, cb) in enumerate(items):
            FocusLabel(panel, text=text, bg="#1E1E1E", fg=FG, font=tv_font(11),
                       on_select=lambda c=cb, p=panel: (p.destroy(), c())
                       ).grid(row=i // 2, column=i % 2, padx=6, pady=4,
                              ipadx=8, ipady=1)

    def _toggle_danmaku(self):
        on = not bool(hawk.get(hawk.DANMAKU_ENABLE, 0))
        hawk.put(hawk.DANMAKU_ENABLE, 1 if on else 0)
        if on:
            self._reload_danmaku()
        else:
            self._remove_danmaku()
        self.status.configure(text="弹幕已开启" if on else "弹幕已关闭")
        self.after(1500, lambda: self.status.configure(text=""))

    def _load_danmaku_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self, title="选择弹幕文件",
            filetypes=[("弹幕", "*.xml *.json *.txt"), ("全部文件", "*.*")])
        if not path:
            return
        hawk.put(hawk.DANMAKU_FILE, path)
        hawk.put(hawk.DANMAKU_ENABLE, 1)
        self._apply_danmaku_file(path)

    def _reload_danmaku(self):
        """按设置里的本地文件或接口模板拉取弹幕并合成 ASS"""
        path = str(hawk.get(hawk.DANMAKU_FILE, "") or "")
        if path and os.path.isfile(path):
            self._apply_danmaku_file(path)
            return
        template = str(hawk.get(hawk.DANMAKU_API, "") or "").strip()
        if not template:
            self.status.configure(text="未配置弹幕接口（设置→弹幕接口）")
            self.after(2000, lambda: self.status.configure(text=""))
            return
        ep_name = (self.series[0][1][self.ep_index]
                   if self.series and self.ep_index < len(self.series[0][1]) else "")
        url = (template.replace("{name}", urllib.parse.quote(self.vod_name))
               .replace("{ep}", urllib.parse.quote(ep_name)))
        self.status.configure(text="正在加载弹幕...")
        tag = self._dm_ep = f"{self.vod_name}|{ep_name}|{url}"

        def work():
            from .apiconfig import fetch_text
            try:
                text = fetch_text(url, timeout=8, retries=1)
            except Exception:
                text = ""
            ui_thread.run(lambda: self._on_danmaku_text(text, tag))
        threading.Thread(target=work, daemon=True).start()

    def _on_danmaku_text(self, text, tag):
        if tag != self._dm_ep:
            return  # 已切集/换了弹幕源
        if not text:
            self.status.configure(text="未获取到弹幕")
            self.after(1500, lambda: self.status.configure(text=""))
            return
        try:
            path = _write_danmaku_ass(text)
        except Exception:
            path = ""
        if path:
            self._apply_danmaku_file(path)
            self.status.configure(text="弹幕已加载")
            self.after(1500, lambda: self.status.configure(text=""))
        else:
            self.status.configure(text="弹幕解析为空")
            self.after(1500, lambda: self.status.configure(text=""))

    def _apply_danmaku_file(self, path):
        try:
            with open(path, encoding="utf-8-sig", errors="ignore") as f:
                text = f.read()
        except OSError:
            text = ""
        ass = ""
        if path.lower().endswith(".ass"):
            ass = text
        elif text:
            from . import danmaku
            ass = danmaku.build_from_text(text)
        if not ass:
            self.status.configure(text="弹幕解析为空")
            self.after(1500, lambda: self.status.configure(text=""))
            return
        out = _write_text(_danmaku_ass_path(), ass)
        if not out:
            return
        if self._dm_path:          # 重复加载时先摘掉旧轨，避免叠加
            self._remove_danmaku()
        self._dm_path = out
        if self.player:
            self.player.add_subtitle(out)

    def _remove_danmaku(self):
        if self.player and self._dm_path:
            for t in self.player.track_list("sub"):
                if str(t.get("external-filename") or "") == self._dm_path:
                    self.player.remove_subtitle(t.get("id"))
                    break
        self._dm_path = None

    def _restore_ext_subs(self):
        """换集后重新挂上本地字幕与弹幕（loadfile 会清空外挂轨道）"""
        if not self.player:
            return
        if self._sub_path and os.path.isfile(self._sub_path):
            self.player.add_subtitle(self._sub_path, select=not self._dm_path)
        if self._dm_path and os.path.isfile(self._dm_path):
            self.player.add_subtitle(self._dm_path)
        if bool(hawk.get(hawk.DANMAKU_ENABLE, 0)) and not self._dm_path:
            self._reload_danmaku()

    # ---- 播放控制（对应原版 play_label / play_next / play_pre / seekBar） ----

    def _toggle_pause(self):
        if not self.player:
            return
        paused = self.player.toggle_pause()
        self.play_btn.configure(text="▶ 播放" if paused else "⏸ 暂停")
        if paused:
            self.status.configure(text="已暂停")
        else:
            self.status.configure(text="")
        self._show_chrome()

    def _prev_ep(self):
        if not self.series or self.ep_index <= 0:
            self.status.configure(text="已经是第一集")
            self.after(1500, lambda: self.status.configure(text=""))
            return
        idx = self.ep_index - 1
        self._switch_ep(idx, self.series[1][idx])

    def _next_ep(self):
        if not self.series or self.ep_index >= len(self.series[1]) - 1:
            self.status.configure(text="已经是最后一集")
            self.after(1500, lambda: self.status.configure(text=""))
            return
        idx = self.ep_index + 1
        self._switch_ep(idx, self.series[1][idx])

    def _replay(self):
        if self.player:
            self.player.seek(0)
            self.player.set_pause(False)
            self.play_btn.configure(text="⏸ 暂停")
        self._show_chrome()

    def _toggle_fullscreen(self):
        try:
            self.app.attributes("-fullscreen",
                                not self.app.attributes("fullscreen"))
        except Exception:
            pass
        self._show_chrome()

    def _seek_rel(self, delta):
        if not self.player:
            return
        pos, dur, _ = self.player.status()
        target = max(0.0, min((dur or 0) - 1, (pos or 0) + delta))
        self.player.seek(target)
        self.status.configure(text=f"{'+' if delta > 0 else ''}{delta} 秒")
        self.after(1200, lambda: self.status.configure(text=""))
        self._show_chrome()

    def _volume_rel(self, delta):
        if not self.player:
            return
        vol = max(0, min(150, self.player.get_volume() + delta))
        self.player.set_volume(vol)
        self.vol_lbl.configure(text=f"🔊 {vol}")

    def _initial_speed(self):
        """初始倍速：记住倍速开启时沿用本片上次倍速，否则用设置里的默认值"""
        try:
            if not bool(hawk.get(hawk.SPEED_MEMORY, 0)):
                return 1.0
            rec = store.get_record(self.source_key, self.vod_id) or {}
            sp = (rec.get("data_json") or {}).get("speed")
            sp = float(sp or hawk.get(hawk.PLAY_SPEED, 1.0) or 1.0)
            return sp if 0.25 <= sp <= 4.0 else 1.0
        except (TypeError, ValueError):
            return 1.0

    def _cycle_speed(self):
        """倍速循环（对应 resetSpeed 面板）；记住倍速时写回设置"""
        i = (self._speeds.index(self._speed) if self._speed in self._speeds
             else self._speeds.index(1.0))
        self._speed = self._speeds[(i + 1) % len(self._speeds)]
        self.speed_btn.configure(text=f"倍速 {self._speed:g}x")
        if self.player:
            self.player.set_speed(self._speed)
        if bool(hawk.get(hawk.SPEED_MEMORY, 0)):
            try:
                hawk.put(hawk.PLAY_SPEED, self._speed)
            except Exception:
                pass
        self._show_chrome()

    def _ensure_player(self):
        if self.player:
            return
        # 等 video 布局完成再取 wid
        self.update_idletasks()
        # 边距由平台层给出（Windows 为 0，macOS 需避开自绘控制栏）
        self.player = MpvPlayer(self.video)

    def _resolve(self, url):
        """选集地址 → (真实媒体地址, 请求头)。含网络请求，须在后台线程调用"""
        from . import data_api, apiconfig
        bean = apiconfig.api_config.get(self.source_key)
        if bean:
            try:
                return data_api.get_play_url(bean, self.play_flag, url)
            except Exception as e:
                from .paths import log_error
                log_error("[play] 解析播放地址失败", e)
                return url, None
        return url, None

    def _start(self, play_url):
        self._t_start = time.time()
        try:
            self._ensure_player()
        except OSError as e:
            self.status.configure(text=f"播放器初始化失败：{e}")
            return
        # 播放期间阻止系统休眠（设置项开启时）
        try:
            if bool(hawk.get(hawk.KEEP_AWAKE, 0)):
                from .host import keep_awake
                keep_awake(True)
        except Exception:
            pass
        self._seq += 1
        self._load(play_url, self._seq)

    @staticmethod
    def _release_awake():
        try:
            from .host import keep_awake
            keep_awake(False)
        except Exception:
            pass

    def _load(self, url, seq, status="正在获取播放信息..."):
        """解析 + 播放一次（解析含网络请求，放后台线程，避免 UI 卡「没反应」）"""
        if seq != self._seq:
            return  # 迟到的重试/换线（用户已切集或返回）
        self._cur_ep_url = url
        self._started = False
        self.status.configure(text=status)
        self._cancel_resolve()
        self._resolve_job = self.after(
            RESOLVE_TIMEOUT_MS, lambda: self._check_resolve(seq))
        def work():
            real, hdr = self._resolve(url)
            if not str(real or "").strip():
                ui_thread.run(lambda: self._handle_fail("获取播放地址为空", seq))
                return
            ui_thread.run(lambda: self._do_play(real, hdr, seq))
        threading.Thread(target=work, daemon=True).start()

    def _do_play(self, real, hdr, seq):
        if seq != self._seq or self.player is None:
            return  # 页面已切集/返回
        self._cancel_resolve()
        self._hdr = hdr
        self._last_real = real
        self._started = False
        self._arm_watchdog(seq)
        self.player.apply_codec(self.player.mpv)
        w = max(1, self.video.winfo_width())
        h = max(1, self.video.winfo_height())
        self.player.apply_scale(self.player.mpv, self._scale, (w, h))
        self.player.apply_subtitle_style(self.player.mpv)
        self.player.apply_cache(self.player.mpv)
        self.player.play(real, hdr)
        self.player.set_speed(self._speed)
        # 换集后重新挂接本地字幕/弹幕（loadfile 会清空外挂轨道）
        self.after(1200, lambda s=seq: self._restore_ext_subs()
                   if s == self._seq else None)
        # 恢复进度（对应 Java getSavedProgress：按 progressKey=MD5(url) 精确 seek）
        prog = store.get_progress(real)
        if prog and prog.get("pos") and prog["pos"] > 5:
            if self._seek_job:
                try:
                    self.after_cancel(self._seek_job)
                except Exception:
                    pass
            self._seek_job = self.after(1500, lambda: self.player.seek(prog["pos"]))
        # 每次起播只保留一条轮询链：重试/换线会重新 _do_play，
        # 旧链若不取消，会和新的并跑（进度条抖动、自动连播可能触发两次）
        if self._pos_job:
            try:
                self.after_cancel(self._pos_job)
            except Exception:
                pass
            self._pos_job = None
        self._poll_pos()
        # 周期性保存进度（对应内核定期 saveProgress）；换线/重试后仍继续
        if self._save_job is None:
            self._save_job = self.after(10000, self._auto_save)

    def _auto_save(self):
        if not self.player or not self._last_real:
            return
        pos, dur, _ = self.player.status()
        if pos > 0:
            store.save_progress(self._last_real, pos, dur or 0)
        self._save_job = self.after(10000, self._auto_save)

    def _poll_pos(self):
        self._pos_job = None
        if not self.player:
            return
        pos, dur, pause = self.player.status()
        # 真正出过画面：清掉失败记忆，避免以后偶发失败时误判线路不可用
        if pos > 1.0 and not self._started:
            self._started = True
            self._failover.reset()
            # 看门狗判失败后又迟到起播的流：把 ⚠ 提示收掉，别一直挂在画面上
            try:
                if self.status.cget("text").startswith("⚠"):
                    self.status.configure(text="")
            except Exception:
                pass
        # 自动连播（对应 Java playNext：播完自动下一集）
        # 必须确认本集真播过，否则打开失败时的 eof 会被当成「播完」直接跳集
        if self.player.is_eof() and self.series and self._started:
            urls = self.series[1]
            if self.ep_index < len(urls) - 1:
                nxt = self.ep_index + 1
                self.status.configure(text="本集播放结束，自动播放下一集...")
                self.after(800, lambda: self._switch_ep(
                    nxt, urls[nxt]))
                self._pos_job = self.after(1000, self._poll_pos)
                return
            self.status.configure(text="全部播放完毕")
            return
        # 刷新进度条与时间（对应原版 seekBar / curr_time / total_time）
        self._cur_pos, self._dur = pos or 0, dur or 0
        self.cur_lbl.configure(text=self._fmt(self._cur_pos))
        self.tot_lbl.configure(text=self._fmt(self._dur))
        if not self._seeking:
            self._draw_seek(self._cur_pos, self._dur)
        self.play_btn.configure(text="▶ 播放" if pause else "⏸ 暂停")
        # 起播后清掉加载/重试/换线提示（别把「已暂停」等用户提示也清掉）
        if self._cur_pos > 0.5:
            txt = self.status.cget("text")
            if (txt == "正在获取播放信息..." or txt.startswith("播放失败，正在重试")
                    or txt.startswith("本线路播放失败")
                    or txt.startswith("正在切换线路")):
                self.status.configure(text="")
        if self._t_start and self._cur_pos > 0.5:
            if os.environ.get("TVBOXPY_DEBUG"):
                print("[startup] click->first frame: %.1fs"
                      % (time.time() - self._t_start), flush=True)
            self._t_start = None
        self._pos_job = self.after(1000, self._poll_pos)

    @staticmethod
    def _fmt(sec):
        if not sec or sec <= 0:
            return "00:00"
        sec = int(sec)
        h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def _show_series(self):
        panel = tk.Toplevel(self)
        panel.title("选集")
        panel.configure(bg="#101010")
        try:
            panel.attributes("-topmost", True)  # 全屏时保持可见
        except Exception:
            pass
        names, urls = self.series[0][1], self.series[1]
        total = min(len(names), len(urls))
        pages = max(1, (total + EPS_PER_PAGE - 1) // EPS_PER_PAGE)
        cols = 8
        state = {"page": min(self.ep_index // EPS_PER_PAGE, pages - 1)}

        grid = tk.Frame(panel, bg="#101010")
        grid.pack(padx=10, pady=(10, 4))
        nav = tk.Frame(panel, bg="#101010")
        nav.pack(padx=10, pady=(0, 10))
        page_lbl = tk.Label(nav, text="", bg="#101010", fg=FG_DIM,
                            font=tv_font(11), width=12)

        def render():
            for w in grid.winfo_children():
                w.destroy()
            start = state["page"] * EPS_PER_PAGE
            end = min(total, start + EPS_PER_PAGE)
            for k, i in enumerate(range(start, end)):
                FocusLabel(grid, text=names[i][:14],
                           bg="#FF5722" if i == self.ep_index else "#1E1E1E",
                           fg=FG, font=tv_font(11),
                           on_select=lambda uu=urls[i], ii=i, p=panel:
                           (p.destroy(), self._switch_ep(ii, uu))
                           ).grid(row=k // cols, column=k % cols, padx=5, pady=5)
            page_lbl.configure(text=f"{state['page'] + 1} / {pages} 页")

        def flip(delta):
            state["page"] = max(0, min(pages - 1, state["page"] + delta))
            render()

        FocusLabel(nav, text="上一页", bg="#1E1E1E", fg=FG, font=tv_font(11),
                   on_select=lambda: flip(-1)).pack(side="left", padx=5)
        page_lbl.pack(side="left", padx=5)
        FocusLabel(nav, text="下一页", bg="#1E1E1E", fg=FG, font=tv_font(11),
                   on_select=lambda: flip(1)).pack(side="left", padx=5)
        render()

    def _switch_ep(self, idx, url):
        # 切集前保存当前集进度（对应 Java 切集时 saveProgress）
        if self._last_real and self.player:
            pos, dur, _ = self.player.status()
            if pos > 0:
                store.save_progress(self._last_real, pos, dur or 0)
        self.ep_index = idx
        self._dm_path = None      # 弹幕按集生成，换集后重新获取
        self._dm_ep = None
        self._failover.reset()  # 用户主动换集：重新给所有线路机会
        self._update_info()
        self._seq += 1
        self._load(url, self._seq)

    def _update_info(self):
        """顶部信息栏：片名 · 线路 · 集名（对应原版 tv_info_name1）"""
        try:
            name = (self.series[0][1][self.ep_index]
                    if self.series and self.ep_index < len(self.series[0][1]) else "")
            self.info_lbl.configure(text=f"{self.vod_name} · {self.play_flag} · {name}")
        except Exception:
            pass

    # ---- 播放失败容错（对应原版 handleResolvePlayUrlFailed / autoRetry） ----

    def _arm_watchdog(self, seq):
        self._cancel_watchdog()
        self._watchdog = self.after(
            START_TIMEOUT_MS, lambda: self._check_watchdog(seq))

    def _cancel_watchdog(self):
        if self._watchdog:
            try:
                self.after_cancel(self._watchdog)
            except Exception:
                pass
        self._watchdog = None

    def _check_resolve(self, seq):
        """解析超时：后台线程可能还卡在网络请求上，靠 seq 丢弃它的迟到结果"""
        self._resolve_job = None
        if seq != self._seq:
            return
        self._handle_fail("解析超时", seq)

    def _cancel_resolve(self):
        if self._resolve_job:
            try:
                self.after_cancel(self._resolve_job)
            except Exception:
                pass
        self._resolve_job = None

    def _check_watchdog(self, seq):
        self._watchdog = None
        if seq != self._seq or not self.player:
            return
        if self._started:
            return  # 已出画面，起播看门狗到此为止
        pos, _dur, pause = self.player.status()
        if pos > 1.0:
            return
        if pause:
            return  # 用户自己按了暂停，不算失败
        self._handle_fail("播放超时", seq)

    def _handle_fail(self, reason, seq=None):
        """解析为空 / 起播超时：同线路重载 → 换线路 → 交给用户点击重试"""
        if seq is not None and seq != self._seq:
            return
        if self.player is None:
            return
        self._cancel_watchdog()
        self._cancel_resolve()
        self._started = False
        counts = [len(u) for u in self.all_urls]
        action, target = self._failover.next_action(
            self.line_index, self.ep_index, counts)
        if action == "switch" and not bool(hawk.get(hawk.AUTO_SWITCH_LINE, 1)):
            action, target = "give_up", None  # 设置里关了自动换线
        if action == "retry":
            self.status.configure(
                text=f"播放失败，正在重试…（{_short_reason(reason)}）")
            self._seq += 1
            seq2 = self._seq
            self.after(1000, lambda: self._load(self._cur_ep_url, seq2))
        elif action == "switch":
            self.status.configure(text="本线路播放失败，正在切换线路…")
            self.after(600, lambda: self._switch_line(target, auto=True))
        else:
            self.status.configure(
                text=f"⚠ 播放失败（{_short_reason(reason)}），点击重试")
            from .paths import log_error
            log_error("[play] 所有线路均播放失败", reason)

    def _switch_line(self, li, auto=False, ep_index=None):
        """切到另一条线路的同一集（自动容错或用户手动选择）"""
        if not (0 <= li < len(self.all_urls)):
            return
        urls = self.all_urls[li]
        idx = self.ep_index if ep_index is None else ep_index
        if not urls or idx >= len(urls):
            return
        self.line_index = li
        self.series = (self.all_flags[li], urls)
        self.play_flag = self.all_flags[li][0]
        self.ep_index = idx
        if not auto:
            self._failover.reset()
        self._update_info()
        self._seq += 1
        self._load(urls[idx], self._seq,
                   status="正在获取播放信息..." if not auto
                   else "正在切换线路...")

    def _show_lines(self):
        """线路选择面板（对应原版线路切换）"""
        if len(self.all_urls) < 2:
            return
        panel = tk.Toplevel(self)
        panel.title("线路")
        panel.configure(bg="#101010")
        try:
            panel.attributes("-topmost", True)
        except Exception:
            pass
        for i, (flag, _names) in enumerate(self.all_urls):
            FocusLabel(
                panel, text=(flag or f"线路{i + 1}")[:14],
                bg="#FF5722" if i == self.line_index else "#1E1E1E",
                fg=FG, font=tv_font(11),
                on_select=lambda ii=i, p=panel: self._pick_line(p, ii)
            ).grid(row=i // 6, column=i % 6, padx=5, pady=5)

    def _pick_line(self, panel, li):
        panel.destroy()
        urls = self.all_urls[li]
        if urls:
            self._switch_line(li, ep_index=min(self.ep_index, len(urls) - 1))

    def _retry_now(self, _e=None):
        """点击状态提示重试当前集（对应原版 setTip 点击重播）"""
        try:
            if not self.status.cget("text").startswith("⚠"):
                return
        except Exception:
            return
        self._failover.reset()
        self._seq += 1
        self._load(self._cur_ep_url, self._seq)

    def _back(self, _e=None):
        """返回详情页。UI 立即切换，mpv 停止与历史写库放到后台线程，
        避免 mpv 同步命令/数据库写在 UI 线程阻塞导致「点了没反应」"""
        from .paths import log_error
        import threading
        if self._locked:      # 锁屏时先解锁，避免「一键退出」
            self._toggle_lock()
            return

        for seq, fid in getattr(self, "_app_binds", []):
            try:
                self.app.unbind(seq, fid)
            except Exception:
                pass
        self._app_binds = []

        # 1) 停掉定时任务（必须在切页前，否则回调打到已销毁的控件）
        for job in (self._pos_job, self._seek_job, self._save_job,
                    self._hide_job, self._watchdog, self._resolve_job,
                    self._osd_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._pos_job = self._seek_job = self._save_job = self._hide_job = None
        self._watchdog = None
        self._resolve_job = None
        self._osd_job = None
        self._release_awake()

        # 恢复进入播放页前的窗口状态（退出全屏沉浸）
        try:
            self.app.attributes("-fullscreen", self._was_full)
        except Exception:
            pass

        player = self.player
        self.player = None
        # 2) 读取进度（纯内存属性，快），随后把 mpv 从本页窗口解绑，
        #    防止页面销毁后 mpv 继续向失效 HWND 渲染
        pos = dur = 0.0
        if player:
            try:
                pos, dur, _ = player.status()
            except Exception as e:
                log_error("[play] 读取进度失败", e)
            try:
                player.detach()
            except Exception as e:
                log_error("[play] mpv 解绑窗口失败", e)

        source_key, vod_id, vod_name = self.source_key, self.vod_id, self.vod_name
        flag, ep_name = self.play_flag, (
            self.series[0][1][self.ep_index] if self.series else "")
        speed = self._speed
        last_real = self._last_real

        # 3) 立即切回详情页（构造失败则退回点播页，绝不空窗）
        try:
            from .ui_detail import Page as DetailPage
            self.app.go_back(
                DetailPage,
                fallback_kwargs={
                    "source_key": source_key,
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                },
            )
        except Exception as e:
            log_error("[play] 返回详情页失败", e)
            try:
                from .ui_grid import Page as GridPage
                self.app.go_back(
                    GridPage, fallback_kwargs={"source_key": source_key})
            except Exception as e:
                log_error("[play] 退回点播页失败", e)

        # 4) 后台收尾：停 mpv + 写历史记录
        def cleanup():
            try:
                if player:
                    player.terminate()
            except Exception as e:
                log_error("[play] 停止播放失败", e)
            try:
                data_json = __import__("json").dumps(
                    {"flag": flag, "ep_index": self.ep_index,
                     "speed": speed}, ensure_ascii=False)
                store.save_record(source_key, vod_id, vod_name, "", flag,
                                  ep_name, pos or 0, dur or 0, data_json,
                                  self.vod_pic)
                if last_real and pos:
                    store.save_progress(last_real, pos, dur or 0)
            except Exception as e:
                log_error("[play] 保存播放记录失败", e)
        threading.Thread(target=cleanup, daemon=True).start()

    def _save_record(self):
        if not self.player:
            return
        pos, dur, _ = self.player.status()
        ep_name = self.series[0][1][self.ep_index] if self.series else ""
        # dataJson 模式（对应 Java VodInfo 序列化）：恢复上次线路/集数用
        data_json = {"flag": self.play_flag, "ep_index": self.ep_index,
                     "speed": self._speed}
        store.save_record(self.source_key, self.vod_id, self.vod_name,
                          "", self.play_flag, ep_name, pos or 0, dur or 0,
                          __import__("json").dumps(data_json, ensure_ascii=False),
                          self.vod_pic)
        if self._last_real and pos:
            store.save_progress(self._last_real, pos, dur or 0)
