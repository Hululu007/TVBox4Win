"""macOS 原生播放后端：AVFoundation（AVPlayer + AVPlayerLayer）

为什么不用 mpv
--------------
1. macOS 的 vo(cocoa) 不支持 ``wid`` 嵌入，想复用 Windows 的嵌入方案不可行；
2. 现成的 mpv.app 预编译包（0.39/0.40）都按较新的 macOS SDK 构建，
   在 Monterey(12) 上缺 AppKit 的 Swift 符号，直接 dyld 报错起不来。

因此 macOS 走系统自带的 AVFoundation：
- 无任何外部二进制依赖，.app 打包体积小、签名干净；
- HLS(m3u8) / MP4 / MOV / HEVC 走 VideoToolbox 硬解，直播秒开；
- 画面放在一个「无边框 + 置顶 + 鼠标穿透」的 NSWindow 里，位置跟随
  tkinter 视频容器的屏幕矩形，因此页面自绘的顶栏/底栏既不会被遮挡，
  也依然可以点击（鼠标事件穿透到下面的 tkinter 窗口）。

支持格式以系统解码器为准：m3u8/mp4/mov/m4v 没问题；mkv、avi 这类容器
AVPlayer 不支持 —— 装了 mpv 时 player.py 会优先用 mpv 后端。

对外接口刻意与 python-mpv 的 ``MPV`` 对象保持一致（``obj["speed"]=1.5``、
``obj.command("loadfile", url)``、``obj.pause``），player.py 的其余逻辑
因此可以完全复用。
"""
from __future__ import annotations

import threading
import time

import AppKit
import AVFoundation
import Foundation

_NSWindowStyleMaskBorderless = 0
_NSBackingStoreBuffered = 2

# AVPlayerLayer 的填充方式
_GRAVITY_FIT = "AVLayerVideoGravityResizeAspect"
_GRAVITY_FILL = "AVLayerVideoGravityResizeAspectFill"


def _seconds(cmtime) -> float:
    """CMTime → 秒（不依赖 CoreMedia 的 C 函数，按 value/timescale 换算）"""
    if cmtime is None:
        return 0.0
    try:
        ts = cmtime.timescale
        return float(cmtime.value) / float(ts) if ts else 0.0
    except Exception:
        return 0.0


class AvCore:
    """等价于 python-mpv 的 ``mpv.MPV`` 对象（AVFoundation 实现）"""

    def __init__(self, rect=None):
        object.__setattr__(self, "_lock", threading.RLock())
        object.__setattr__(self, "_player", None)
        object.__setattr__(self, "_window", None)
        object.__setattr__(self, "_layer", None)
        object.__setattr__(self, "_item", None)
        object.__setattr__(self, "_headers", {})
        object.__setattr__(self, "_url", None)
        object.__setattr__(self, "_rate", 1.0)
        object.__setattr__(self, "_paused", True)
        object.__setattr__(self, "_volume", 1.0)
        object.__setattr__(self, "_geom", None)
        object.__setattr__(self, "_hidden", True)
        self._ensure_window(rect)

    # ---- 窗口 ----

    def _ensure_window(self, rect):
        if self._window is not None:
            if rect:
                self.set_rect(*rect)
            return
        player = AVFoundation.AVPlayer.alloc().init()
        layer = AVFoundation.AVPlayerLayer.playerLayerWithPlayer_(player)
        layer.setVideoGravity_(_GRAVITY_FIT)
        view = AppKit.NSView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, 640, 360))
        view.setWantsLayer_(True)
        view.setLayer_(layer)
        win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(0, 0, 640, 360),
            _NSWindowStyleMaskBorderless, _NSBackingStoreBuffered, False)
        win.setContentView_(view)
        win.setOpaque_(True)
        win.setBackgroundColor_(AppKit.NSColor.blackColor())
        win.setLevel_(AppKit.NSFloatingWindowLevel)   # 浮在 tkinter 全屏窗口之上
        win.setIgnoresMouseEvents_(True)              # 鼠标穿透，下面页面控件可点
        win.setReleasedWhenClosed_(False)
        win.setHasShadow_(False)
        win.setCollectionBehavior_(1)                 # canJoinAllSpaces
        object.__setattr__(self, "_player", player)
        object.__setattr__(self, "_layer", layer)
        object.__setattr__(self, "_window", win)
        if rect:
            self.set_rect(*rect)

    def set_rect(self, x, y, w, h):
        """把播放窗口摆到指定屏幕矩形（tkinter 坐标为左上原点，Cocoa 为左下）"""
        with self._lock:
            win = self._window
            if win is None:
                return
            self._ensure_window(None)
            w, h = max(int(w), 16), max(int(h), 16)
            screen_h = AppKit.NSScreen.mainScreen().frame().size.height
            rect = AppKit.NSMakeRect(x, screen_h - y - h, w, h)
            geom = (x, y, w, h)
            if geom == self._geom:
                return
            object.__setattr__(self, "_geom", geom)
            win.setFrame_display_(rect, True)
            self._layer.setFrame_(AppKit.NSMakeRect(0, 0, w, h))

    def show(self):
        with self._lock:
            if self._window is not None and self._hidden:
                self._window.orderFrontRegardless()
                object.__setattr__(self, "_hidden", False)

    def hide(self):
        with self._lock:
            if self._window is not None and not self._hidden:
                self._window.orderOut_(None)
                object.__setattr__(self, "_hidden", True)

    def alive(self) -> bool:
        return self._player is not None

    def terminate(self):
        with self._lock:
            try:
                if self._player is not None:
                    self._player.pause()
                if self._window is not None:
                    self._window.orderOut_(None)
                    self._window.setContentView_(None)
                    self._window.close()
            except Exception:
                pass
            object.__setattr__(self, "_window", None)
            object.__setattr__(self, "_player", None)

    # ---- 命令 / 属性 ----

    def command(self, *args):
        if not args:
            return None
        cmd = args[0]
        with self._lock:
            if cmd == "loadfile":
                self._load(args[1])
            elif cmd == "seek":
                self._seek(float(args[1]))
            elif cmd == "stop":
                self._pause(True)
                self._seek(0.0)
            elif cmd == "quit":
                self.terminate()
        return None

    def _load(self, url):
        if not url:
            return
        object.__setattr__(self, "_url", url)
        nsurl = Foundation.NSURL.URLWithString_(url)
        if nsurl is None:
            raise OSError("非法播放地址：%s" % url)
        opts = {}
        if self._headers:
            opts["AVURLAssetHTTPHeaderFieldsKey"] = dict(self._headers)
        asset = AVFoundation.AVURLAsset.URLAssetWithURL_options_(
            nsurl, opts or None)
        item = AVFoundation.AVPlayerItem.playerItemWithAsset_(asset)
        self._player.replaceCurrentItemWithPlayerItem_(item)
        object.__setattr__(self, "_item", item)
        self._player.setVolume_(self._volume)
        self._player.play()
        self._player.setRate_(self._rate)
        object.__setattr__(self, "_paused", False)
        self.show()

    def _seek(self, sec):
        if self._player is None:
            return
        cm = self._cm_time(sec)
        if cm is not None:
            self._player.seekToTime_(cm)

    @staticmethod
    def _cm_time(sec):
        try:
            from CoreMedia import CMTimeMakeWithSeconds
            return CMTimeMakeWithSeconds(float(sec), 600)
        except Exception:
            pass
        try:
            return AVFoundation.CMTimeMakeWithSeconds(float(sec), 600)
        except Exception:
            return None

    def _pause(self, val):
        if self._player is None:
            return
        object.__setattr__(self, "_paused", bool(val))
        if val:
            self._player.pause()
        else:
            self._player.play()
            self._player.setRate_(self._rate)

    # 属性读写：对齐 python-mpv 的写法
    def __setitem__(self, name, value):
        if name == "http-header-fields":
            hdrs = {}
            for line in (value or []):
                if ":" in str(line):
                    k, v = str(line).split(":", 1)
                    hdrs[k.strip()] = v.strip()
            object.__setattr__(self, "_headers", hdrs)
        elif name == "speed":
            object.__setattr__(self, "_rate", float(value))
            if self._player is not None and not self._paused:
                self._player.setRate_(float(value))
        elif name == "volume":
            vol = max(0.0, min(1.0, float(value) / 100.0))
            object.__setattr__(self, "_volume", vol)
            if self._player is not None:
                self._player.setVolume_(vol)
        elif name == "pause":
            self._pause(value)
        elif name == "panscan":
            fill = float(value or 0) > 0
            self._layer.setVideoGravity_(_GRAVITY_FILL if fill else _GRAVITY_FIT)
        elif name == "window-minimized":
            self.hide() if value else self.show()
        # 其余 mpv 专有选项（hwdec / video-unscaled / ao / wid …）忽略

    def __getitem__(self, name):
        return getattr(self, name.replace("-", "_"), None)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self.__setitem__(name.replace("_", "-"), value)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        p = self._player
        if p is None:
            return None
        try:
            if name in ("playback_time",):
                return _seconds(p.currentTime())
            if name == "duration":
                it = p.currentItem()
                return _seconds(it.duration()) if it is not None else 0.0
            if name == "pause":
                return self._paused or p.rate() == 0
            if name == "volume":
                return int(round(p.volume() * 100))
            if name == "speed":
                return self._rate
            if name == "idle_active":
                return p.currentItem() is None
            if name == "core_idle":
                return p.currentItem() is None or (
                    p.rate() == 0 and _seconds(p.currentTime()) <= 0.01)
            if name == "eof_reached":
                dur = _seconds(p.currentItem().duration()) if p.currentItem() else 0
                cur = _seconds(p.currentTime())
                return bool(dur and cur >= dur - 0.8 and p.rate() == 0)
        except Exception:
            return None
        return None
