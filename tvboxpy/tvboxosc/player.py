"""播放器门面（对应原版 player/IjkMediaPlayer 的角色）

本文件只做两件事：
1. 把公开播放接口（play / pause / seek / volume / speed / status …）绑定到底层 core；
2. 把平台相关的部分（核心创建、嵌入方式、窗口几何）全部转发给 host 门面。

**这里不允许出现任何平台判断**：改 Windows 播放只动 host/win.py，
改 macOS 播放只动 host/mac.py + player_mac.py / player_av.py。
"""
import threading

from .host import player as _host


class MpvPlayer:
    def __init__(self, wid, insets=None):
        """wid 可传 tkinter 控件或整数窗口 id；insets=(上,右,下,左) 是页面自绘
        控制栏占用的边距（仅独立视频窗口的平台使用，如 macOS）"""
        from .host import chrome_insets
        self._widget = wid if hasattr(wid, "winfo_id") else None
        self._wid = (int(wid.winfo_id()) if self._widget is not None
                     else int(wid))
        self._last_url = None
        # 先让后端记录容器（独立窗口平台要靠它算初始矩形并跟随尺寸）
        rect = _host.attach_widget(self._widget,
                                   insets if insets is not None else chrome_insets())
        self.mpv = _host.acquire(self._wid, rect)

    @classmethod
    def warmup(cls):
        """预热播放核心（启动时后台调用），失败不影响使用"""
        try:
            return bool(_host.warmup())
        except Exception:
            return False

    @property
    def backend_name(self):
        try:
            return _host.name
        except Exception:
            return "unknown"

    # ---- 播放设置（对应原版 IJK_CODEC / PLAY_SCALE）----

    @staticmethod
    def apply_codec(core):
        """解码方式：硬解码 → hwdec=auto，软解码 → hwdec=no"""
        try:
            from . import hawk
            hard = hawk.get(hawk.IJK_CODEC, "硬解码") != "软解码"
        except Exception:
            hard = True
        try:
            core["hwdec"] = "auto" if hard else "no"
        except Exception:
            pass

    @staticmethod
    def apply_scale(core, scale=None, size=None):
        """画面缩放（对应 PlayerHelper.getScaleName / VideoView SCREEN_SCALE_*）

        0 默认 / 1 16:9 / 2 4:3 / 3 填充（拉伸铺满，不裁切）/ 4 裁剪（保持比例
        裁边铺满）/ 5 原始（不缩放）。原版把「填充」实现成裁剪，这里按字面
        语义拆成两个模式，避免拉伸和裁剪被混为一谈。
        """
        if scale is None:
            try:
                from . import hawk
                scale = int(hawk.get(hawk.PLAY_SCALE, 0))
            except (TypeError, ValueError):
                scale = 0
        try:
            core["panscan"] = 0.0
            core["video-unscaled"] = "no"
            core["video-aspect-override"] = "no"
        except Exception:
            return
        try:
            if scale == 1:      # 16:9
                core["video-aspect-override"] = "16:9"
            elif scale == 2:    # 4:3
                core["video-aspect-override"] = "4:3"
            elif scale == 3:    # 填充：强制成窗口比例 = 拉伸铺满
                w = h = 0
                if size:
                    w, h = int(size[0] or 0), int(size[1] or 0)
                if not (w and h):
                    w = int(core["osd-width"] or 0)
                    h = int(core["osd-height"] or 0)
                if w and h:
                    core["video-aspect-override"] = "%d:%d" % (w, h)
            elif scale == 4:    # 裁剪：保持比例放大到铺满窗口后裁边
                core["panscan"] = 1.0
            elif scale == 5:    # 原始：按源码分辨率显示
                core["video-unscaled"] = "yes"
        except Exception:
            pass

    @staticmethod
    def scale_name(scale):
        return {0: "默认", 1: "16:9", 2: "4:3", 3: "填充", 4: "裁剪",
                5: "原始"}.get(scale, "默认")

    # ---- 通用属性 / 轨道 / 字幕 / 缓存 ----

    def get_property(self, name, default=None):
        try:
            val = self.mpv[name]
            return default if val is None else val
        except Exception:
            return default

    def set_property(self, name, value):
        try:
            self.mpv[name] = value
            return True
        except Exception:
            return False

    def track_list(self, kind=None):
        """mpv 轨道列表（kind=audio/sub/video 时过滤）"""
        try:
            tracks = self.mpv.track_list or []
        except Exception:
            return []
        out = []
        for t in tracks:
            if not isinstance(t, dict):
                try:
                    t = dict(t)
                except Exception:
                    continue
            if kind and t.get("type") != kind:
                continue
            out.append(t)
        return out

    def set_track(self, kind, track_id):
        """选择轨道：kind=audio/sub/video；track_id=None 表示关闭该类型"""
        prop = {"audio": "aid", "video": "vid", "sub": "sid"}.get(kind)
        if not prop:
            return False
        return self.set_property(prop, "no" if track_id is None else track_id)

    def current_track(self, kind):
        try:
            prop = {"audio": "aid", "video": "vid", "sub": "sid"}[kind]
            return self.mpv[prop]
        except Exception:
            return None

    def add_subtitle(self, path, select=True):
        """加载外挂字幕/弹幕 ASS，返回新轨道 id（失败 None）"""
        try:
            self.mpv.command("sub-add", str(path), "select" if select else "auto")
        except Exception:
            return None
        for t in self.track_list("sub"):
            try:
                if str(t.get("external-filename") or "") == str(path):
                    return t.get("id")
            except Exception:
                continue
        return self.current_track("sub")

    def remove_subtitle(self, track_id):
        try:
            self.mpv.command("sub-remove", str(track_id))
            return True
        except Exception:
            return False

    def set_subtitle_visible(self, on):
        return self.set_property("sub-visibility", bool(on))

    def get_sub_delay(self):
        try:
            return float(self.mpv["sub-delay"] or 0)
        except Exception:
            return 0.0

    def set_sub_delay(self, seconds):
        try:
            self.mpv["sub-delay"] = float(seconds)
            return True
        except Exception:
            return False

    def set_sub_font_size(self, size):
        try:
            self.mpv["sub-font-size"] = int(size or 0)
            return True
        except Exception:
            return False

    @staticmethod
    def apply_subtitle_style(core):
        """应用设置里的字幕字号/延迟"""
        try:
            from . import hawk
            size = int(hawk.get(hawk.SUB_FONT_SIZE, 0) or 0)
            delay = float(hawk.get(hawk.SUB_DELAY, 0) or 0)
        except (TypeError, ValueError):
            size, delay = 0, 0.0
        try:
            core["sub-font-size"] = size
            core["sub-delay"] = delay
        except Exception:
            pass

    def set_cache(self, enabled):
        """播放缓存（对应 IJK_CACHE_PLAY）：开启后允许网络流预读缓冲"""
        try:
            if enabled:
                self.mpv["cache"] = "yes"
                self.mpv["cache-secs"] = 20
                self.mpv["demuxer-readahead-secs"] = 20
            else:
                self.mpv["cache"] = "no"
            return True
        except Exception:
            return False

    @staticmethod
    def apply_cache(core):
        try:
            from . import hawk
            enabled = bool(hawk.get(hawk.PLAYER_CACHE, 0))
        except Exception:
            enabled = False
        if enabled:
            try:
                core["cache"] = "yes"
                core["cache-secs"] = 20
                core["demuxer-readahead-secs"] = 20
            except Exception:
                pass

    def cache_speed(self):
        """当前缓冲速度（字节/秒），拿不到返回 0"""
        val = self.get_property("cache-speed", 0)
        try:
            return float(val or 0)
        except (TypeError, ValueError):
            return 0.0

    def video_info(self):
        """分辨率 / 帧率 / 编码 / 硬解状态（OSD 用）"""
        w = self.get_property("width", 0) or 0
        h = self.get_property("height", 0) or 0
        fps = self.get_property("estimated-vf-fps", 0) or \
            self.get_property("container-fps", 0) or 0
        return {
            "width": int(w or 0), "height": int(h or 0),
            "fps": float(fps or 0),
            "codec": str(self.get_property("video-codec", "") or ""),
            "hwdec": str(self.get_property("hwdec-current", "") or ""),
        }

    def play(self, url, headers=None):
        # 页面复用/核心重建后，确保拿到可用核心
        self.mpv = _host.acquire(self._wid)
        self._last_url = url
        try:
            if headers:
                self.mpv["http-header-fields"] = [f"{k}: {v}" for k, v in headers.items()]
            else:
                self.mpv["http-header-fields"] = []
        except Exception:  # mpv 会抛 MPVError/ShutdownError，不止 RuntimeError
            pass
        try:
            self.mpv.command("loadfile", url, "replace")
        except Exception:  # 含 mpv.ShutdownError
            return
        # 后台看护：只有在确实回到 idle（首条 loadfile 被丢弃或打开失败）时才重试。
        # 原先每 0.5 秒检查一次并重复 loadfile，会打断正在打开的流 → 起播反而变慢；
        # 现改为 2 秒一轮，且非 idle 立即退出。
        def _ensure():
            import time
            for i in range(8):
                time.sleep(2)
                try:
                    if self._last_url != url:
                        return  # 已切到别的文件
                    if not self.mpv.idle_active:
                        return  # 已进入加载/播放
                    self.mpv.command("loadfile", url, "replace")
                    if i >= 2:
                        self.mpv["ao"] = "null"  # 音频设备故障兜底：无声播放
                except Exception:  # 含 mpv.ShutdownError
                    return
        threading.Thread(target=_ensure, daemon=True).start()

    # ---- 播放控制（对应原版 play_label / seekBar / 音量） ----

    def paused(self):
        try:
            return bool(self.mpv.pause)
        except Exception:
            return False

    def toggle_pause(self):
        """播放/暂停切换，返回切换后的暂停状态"""
        try:
            self.mpv.pause = not bool(self.mpv.pause)
            return bool(self.mpv.pause)
        except Exception:
            return False

    def set_pause(self, val):
        try:
            self.mpv.pause = bool(val)
        except Exception:
            pass

    def get_volume(self):
        try:
            return int(self.mpv.volume)
        except Exception:
            return 100

    def set_volume(self, vol):
        try:
            self.mpv.volume = max(0, min(150, int(vol)))
        except Exception:
            pass

    def core_idle(self):
        """True 表示尚未出画面（用于起播计时/诊断）"""
        try:
            return bool(self.mpv.core_idle)
        except Exception:
            return True

    def status(self):
        try:
            pos = self.mpv.playback_time or 0
            dur = self.mpv.duration or 0
            pause = bool(self.mpv.pause)
            return pos, dur, pause
        except Exception:  # 含 mpv.ShutdownError
            return 0, 0, False

    def seek(self, sec):
        try:
            self.mpv.command("seek", str(sec), "absolute")
        except Exception:  # 含 mpv.ShutdownError
            pass

    def set_speed(self, speed):
        """倍速（对应 mController.resetSpeed）"""
        try:
            self.mpv["speed"] = float(speed)
        except Exception:  # 含 mpv.ShutdownError
            pass

    def is_eof(self):
        try:
            return bool(self.mpv.eof_reached)
        except Exception:  # mpv 会抛 MPVError/ShutdownError，不止 RuntimeError
            return False

    # ---- 生命周期（实现由平台后端决定） ----

    def detach(self):
        """播放页销毁时解绑：Windows 改 wid=0，macOS 收起独立窗口"""
        try:
            _host.release(self.mpv)
        except Exception:
            pass

    def terminate(self):
        """只停止播放，不销毁共享核心（销毁会导致后续核心崩溃）"""
        self._last_url = None  # 让 play() 里的重试线程自行退出
        try:
            _host.stop(self.mpv)
        except Exception:
            pass

    @classmethod
    def shutdown(cls):
        """进程退出时调用，真正销毁核心"""
        try:
            _host.shutdown()
        except Exception:
            pass


import atexit  # noqa: E402

atexit.register(MpvPlayer.shutdown)
