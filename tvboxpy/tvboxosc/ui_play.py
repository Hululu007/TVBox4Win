"""播放页 PlayActivity 复刻：mpv 播放 + 选集/线路切换 + 进度显示 + 历史记录"""
import tkinter as tk

from . import store
from .theme import BG, FG, FG_DIM, FocusLabel, tv_font
from .player import MpvPlayer


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

        # 顶部悬浮：返回 + 标题 + 选集面板开关
        bar = tk.Frame(self, bg="#000000")
        bar.place(x=0, y=0, relwidth=1.0)
        self._bar_widgets(bar)

        self.video = tk.Frame(self, bg="#000000", highlightthickness=0)
        self.video.place(x=0, y=34, relwidth=1.0, relheight=1.0, height=-34)
        self.video.configure(width=100, height=100)

        # 底部状态：进度 + 集名
        self.status = tk.Label(self, text="", bg="#000000", fg=FG_DIM,
                               font=tv_font(11))
        self.status.place(x=16, rely=0.94)

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

    def _bar_widgets(self, bar):
        FocusLabel(bar, text="← 返回", font=tv_font(12, True),
                   on_select=self._back).pack(side="left", padx=12, pady=6)
        tk.Label(bar, text=f"{self.vod_name} · {self.play_flag} · "
                 f"{self.series[0][1][self.ep_index] if self.series else ''}",
                 bg="#000000", fg=FG, font=tv_font(13, True)).pack(side="left", padx=10)
        if self.series:
            FocusLabel(bar, text="选集", font=tv_font(12),
                       on_select=self._show_series).pack(side="right", padx=12)
        self.speed_btn = FocusLabel(bar, text="倍速 1.0x", font=tv_font(12),
                                    on_select=self._cycle_speed)
        self.speed_btn.pack(side="right", padx=12)

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
        self.player = MpvPlayer(int(self.video.winfo_id()))

    def _resolve(self, url):
        """type3 spider 站点：选集 id → 真实播放地址 + 请求头"""
        from . import data_api, apiconfig
        bean = apiconfig.api_config.get(self.source_key)
        if bean:
            try:
                real, hdr = data_api.get_play_url(bean, self.play_flag, url)
            except Exception as e:
                real, hdr = url, None
                self.status.configure(text=f"解析播放地址失败：{e}")
            self._hdr = hdr
            self._last_real = real
            return real
        self._hdr = None
        self._last_real = url
        return url

    def _start(self, play_url):
        try:
            self._ensure_player()
        except OSError as e:
            self.status.configure(text=f"播放器初始化失败：{e}")
            return
        real = self._resolve(play_url)
        self.player.play(real, self._hdr)
        # 恢复进度（对应 Java getSavedProgress：按 progressKey=MD5(url) 精确 seek）
        prog = store.get_progress(real)
        if prog and prog.get("pos") and prog["pos"] > 5:
            self._seek_job = self.after(1500, lambda: self.player.seek(prog["pos"]))
        self._poll_pos()
        # 周期性保存进度（对应内核定期 saveProgress）
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
        flag = " ⏸" if pause else ""
        spd = f" {self._speed}x" if self._speed != 1.0 else ""
        self.status.configure(
            text=f"{self._fmt(pos)} / {self._fmt(dur)}{flag}{spd}")
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
        real = self._resolve(url)
        self.player.play(real, self._hdr)
        self.player.set_speed(self._speed)
        # 恢复该集上次进度（对应 getSavedProgress）
        prog = store.get_progress(real)
        if prog and prog.get("pos") and prog["pos"] > 5:
            if self._seek_job:
                self.after_cancel(self._seek_job)
            self._seek_job = self.after(1500, lambda: self.player.seek(prog["pos"]))

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
        for job in (self._pos_job, self._seek_job, self._save_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._pos_job = self._seek_job = self._save_job = None

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
