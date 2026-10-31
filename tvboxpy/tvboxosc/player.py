"""libmpv 封装（对应 player/IjkMediaPlayer 的角色，内核换成 mpv）

进程内共享一个 libmpv 核心反复 init/terminate 会崩溃（libmpv core has
been shutdown），且多实例会竞争音频设备。因此这里用进程级单例核心，
切换页面时通过运行时改 wid 重新嵌入新容器，terminate 只停止播放。
"""
import os
import sys

_DLL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "third_party", "mpv")
os.environ["PATH"] = _DLL_DIR + os.pathsep + os.environ.get("PATH", "")
if getattr(sys, "_MEIPASS", None):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ["PATH"]

import mpv  # noqa: E402
import threading  # noqa: E402


class MpvPlayer:
    _shared = None          # 进程级共享核心
    _core_lock = threading.Lock()

    def __init__(self, wid: int):
        self._wid = int(wid)
        self.mpv = self._get_core(self._wid)
        self._last_url = None

    @classmethod
    def _get_core(cls, wid):
        """复用现有核心；核心已 shutdown 则重建。切换嵌入窗口用运行时改 wid"""
        with cls._core_lock:
            if cls._shared is not None:
                try:
                    _ = cls._shared.idle_active  # 探测核心是否存活
                    try:
                        cls._shared["wid"] = str(wid)
                    except Exception:
                        pass
                    return cls._shared
                except Exception:
                    try:
                        cls._shared.terminate()
                    except Exception:
                        pass
                    cls._shared = None
            cls._shared = mpv.MPV(wid=str(wid), osc="yes",
                                  force_window="no", keep_open="yes")
            return cls._shared

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
    def apply_scale(core):
        """画面缩放（对应 PlayerHelper.getScaleName / VideoView SCREEN_SCALE_*）"""
        try:
            from . import hawk
            scale = int(hawk.get(hawk.PLAY_SCALE, 0))
        except Exception:
            scale = 0
        try:
            core["panscan"] = 0.0
            core["video-unscaled"] = "no"
            core["video-aspect-override"] = "no"
            if scale == 1:      # 16:9
                core["video-aspect-override"] = "16:9"
            elif scale == 2:    # 4:3
                core["video-aspect-override"] = "4:3"
            elif scale == 3:    # 填充（保持比例裁剪铺满窗口）
                core["panscan"] = 1.0
            elif scale == 4:    # 原始（不缩放）
                core["video-unscaled"] = "yes"
        except Exception:
            pass

    def play(self, url, headers=None):
        # 页面复用/核心重建后，确保拿到可用核心
        self.mpv = self._get_core(self._wid)
        self._last_url = url
        try:
            if headers:
                self.mpv["http-header-fields"] = [f"{k}: {v}" for k, v in headers.items()]
            else:
                self.mpv["http-header-fields"] = []
        except Exception:  # mpv 会抛 MPVError/ShutdownError，不止 RuntimeError
            pass
        try:
            self.mpv.command("loadfile", url)
        except Exception:  # 含 mpv.ShutdownError
            return
        # mpv 核心刚创建时首条 loadfile 可能被静默丢弃，循环重试直到开始播放；
        # 若音频输出设备故障导致始终播不起来，自动降级 ao=null（无声）保证画面正常
        def _ensure():
            import time
            retried = False
            for _ in range(20):
                time.sleep(0.5)
                try:
                    if self._last_url != url:
                        return  # 已切到别的文件
                    if self.mpv.idle_active:
                        self.mpv.command("loadfile", url)
                        if _ >= 5 and not retried:
                            retried = True
                            self.mpv["ao"] = "null"  # 降级：无声播放
                    else:
                        return
                except Exception:  # 含 mpv.ShutdownError
                    return
        threading.Thread(target=_ensure, daemon=True).start()

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

    def detach(self):
        """把 mpv 从当前嵌入窗口解绑（wid=0）。
        页面销毁后若 mpv 仍向失效 HWND 渲染，会拖住核心甚至卡死 UI 线程"""
        try:
            self.mpv["wid"] = "0"
        except Exception:
            pass

    def terminate(self):
        """只停止播放，不销毁共享核心（销毁会导致后续核心崩溃）"""
        self._last_url = None  # 让 play() 里的重试线程自行退出
        try:
            self.mpv.command("stop")
        except Exception:
            pass

    @classmethod
    def shutdown(cls):
        """进程退出时调用，真正销毁核心"""
        with cls._core_lock:
            if cls._shared is not None:
                try:
                    cls._shared.terminate()
                except Exception:
                    pass
                cls._shared = None


import atexit  # noqa: E402
atexit.register(MpvPlayer.shutdown)
