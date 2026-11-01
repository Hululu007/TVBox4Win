"""播放页 PlayActivity 复刻：mpv 播放 + 选集/线路切换 + 进度显示 + 历史记录"""
import os
import time
import threading
import tkinter as tk

from . import store, ui_thread
from .theme import ACCENT, BG, FG, FG_DIM, FocusLabel, tv_font
from .player import MpvPlayer

CHROME_BG = "#0B0F1C"   # 控制栏底色（近黑，覆在视频上）
BTN_BG = "#26325C"      # 按钮底色（theme.PANEL_HI）


class Page(tk.Frame):
    """对应 ui/activity/PlayActivity.java"""

    def __init__(self, master, app, source_key, vod_id, vod_name,
                 play_flag, play_ep, play_url, series=None, ep_index=0,
                 vod_pic=""):
        super().__init__(master, bg="#000000")
        self.app = app
        self.source_key, self.vod_id, self.vod_name = source_key, vod_id, vod_name
        self.vod_pic = vod_pic  # 写历史记录用（首页「观看历史」推荐位显示海报）
        self.play_flag, self.ep_index = play_flag, ep_index
        self.series = series  # ((flag, names), urls)
        self.player = None
        self._pos_job = None
        self._hdr = None
        self._last_real = None
        self._seek_job = None
        self._save_job = None
        self._speed = 1.0
        self._speeds = [1.0, 1.25, 1.5, 2.0, 0.5]
        self._app_binds = []
        self._seq = 0  # 播放请求序号：后台解析返回时页面可能已切集/销毁
        self._hide_job = None
        self._cur_pos = 0.0
        self._dur = 0.0
        self._t_start = None  # 起播计时（TVBOXPY_DEBUG 时打印）

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

        # 沉浸式控制栏：无操作 4 秒后隐藏，鼠标移动/按键/点击唤出
        for seq in ("<Motion>", "<Any-KeyPress>", "<Button-1>"):
            try:
                fid = self.app.bind(seq, self._show_chrome, add="+")
                self._app_binds.append((seq, fid))
            except Exception:
                pass
        self._show_chrome()

        # 播放快捷键（对应原版遥控器/键盘操作）
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
        }
        for seq, cb in hotkeys.items():
            try:
                fid = self.app.bind(seq, lambda e, c=cb: (c(), "break")[1], add="+")
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
        self.speed_btn = FocusLabel(row, text="倍速 1.0x", font=tv_font(12),
                                    bg=BTN_BG, fg="#FFFFFF",
                                    on_select=self._cycle_speed, padx=14, pady=5)
        self.speed_btn.pack(side="right", padx=4)

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
                    getattr(self, "_save_job", None), getattr(self, "_hide_job", None)):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._pos_job = self._seek_job = self._save_job = self._hide_job = None
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

    def _cycle_speed(self):
        """倍速循环（对应 resetSpeed 面板）"""
        i = self._speeds.index(self._speed) if self._speed in self._speeds else 0
        self._speed = self._speeds[(i + 1) % len(self._speeds)]
        self.speed_btn.configure(text=f"倍速 {self._speed}x")
        if self.player:
            self.player.set_speed(self._speed)

    def _ensure_player(self):
        if self.player:
            return
        # 等 video 布局完成再取 wid
        self.update_idletasks()
        self.player = MpvPlayer(self.video, insets=(42, 0, 96, 0))

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
        # 解析含网络请求（分享页嗅探等），放后台线程，避免 UI 卡「没反应」
        self._seq += 1
        seq = self._seq
        self.status.configure(text="正在获取播放信息...")
        def work():
            real, hdr = self._resolve(play_url)
            ui_thread.run(lambda: self._do_play(real, hdr, seq, first=True))
        threading.Thread(target=work, daemon=True).start()

    def _do_play(self, real, hdr, seq, first=False):
        if seq != self._seq or self.player is None:
            return  # 页面已切集/返回
        self._hdr = hdr
        self._last_real = real
        self.player.apply_codec(self.player.mpv)
        self.player.apply_scale(self.player.mpv)
        self.player.play(real, hdr)
        self.player.set_speed(self._speed)
        # 恢复进度（对应 Java getSavedProgress：按 progressKey=MD5(url) 精确 seek）
        prog = store.get_progress(real)
        if prog and prog.get("pos") and prog["pos"] > 5:
            if self._seek_job:
                try:
                    self.after_cancel(self._seek_job)
                except Exception:
                    pass
            self._seek_job = self.after(1500, lambda: self.player.seek(prog["pos"]))
        self._poll_pos()
        if first:  # 周期性保存进度（对应内核定期 saveProgress）
            self._save_job = self.after(10000, self._auto_save)

    def _auto_save(self):
        if not self.player or not self._last_real:
            return
        pos, dur, _ = self.player.status()
        if pos > 0:
            store.save_progress(self._last_real, pos, dur or 0)
        self._save_job = self.after(10000, self._auto_save)

    def _poll_pos(self):
        if not self.player:
            return
        pos, dur, pause = self.player.status()
        # 自动连播（对应 Java playNext：播完自动下一集）
        if self.player.is_eof() and self.series:
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
        # 起播后清掉「正在获取播放信息」提示
        if self._cur_pos > 0.5 and self.status.cget("text") == "正在获取播放信息...":
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
        cols = 6
        for i, (n, u) in enumerate(zip(names, urls)):
            FocusLabel(panel, text=n[:14],
                       bg="#1E1E1E" if i != self.ep_index else "#FF5722",
                       fg=FG, font=tv_font(11),
                       on_select=lambda uu=u, ii=i, p=panel: (p.destroy(), self._switch_ep(ii, uu))
                       ).grid(row=i // cols, column=i % cols, padx=5, pady=5)

    def _switch_ep(self, idx, url):
        # 切集前保存当前集进度（对应 Java 切集时 saveProgress）
        if self._last_real and self.player:
            pos, dur, _ = self.player.status()
            if pos > 0:
                store.save_progress(self._last_real, pos, dur or 0)
        self.ep_index = idx
        # 顶部信息栏跟着切集更新（对应原版 tv_info_name1）
        try:
            self.info_lbl.configure(
                text=f"{self.vod_name} · {self.play_flag} · "
                     f"{self.series[0][1][idx] if self.series else ''}")
        except Exception:
            pass
        self._seq += 1
        seq = self._seq
        self.status.configure(text="正在获取播放信息...")
        def work():
            real, hdr = self._resolve(url)
            ui_thread.run(lambda: self._do_play(real, hdr, seq))
        threading.Thread(target=work, daemon=True).start()

    def _back(self, _e=None):
        """返回详情页。UI 立即切换，mpv 停止与历史写库放到后台线程，
        避免 mpv 同步命令/数据库写在 UI 线程阻塞导致「点了没反应」"""
        from .paths import log_error
        import threading

        for seq, fid in getattr(self, "_app_binds", []):
            try:
                self.app.unbind(seq, fid)
            except Exception:
                pass
        self._app_binds = []

        # 1) 停掉定时任务（必须在切页前，否则回调打到已销毁的控件）
        for job in (self._pos_job, self._seek_job, self._save_job,
                    self._hide_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._pos_job = self._seek_job = self._save_job = self._hide_job = None

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
            self.app.switch(DetailPage, source_key=source_key,
                            vod_id=vod_id, vod_name=vod_name)
        except Exception as e:
            log_error("[play] 返回详情页失败", e)
            try:
                from .ui_grid import Page as GridPage
                self.app.switch(GridPage, source_key=source_key)
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
