"""macOS 播放后端：独立 mpv 进程 + JSON IPC 控制

为什么不能照搬 Windows 的做法
------------------------------
Windows 版把 libmpv 的 ``wid`` 设成 tkinter 子窗口的 HWND，画面直接嵌进
页面。macOS 的 vo(cocoa) **不支持 wid 嵌入**（只有 X11/win32 后端支持），
所以这里换一种等效方案：

- 启动一个独立 mpv 进程，窗口设为无边框 + 置顶 + 不抢焦点；
- 窗口位置/尺寸跟随 tkinter 里视频容器的屏幕矩形，并扣除控制栏高度，
  这样页面自绘的顶栏/底栏不会被 mpv 窗口盖住；
- 播放控制（播放/暂停/seek/音量/倍速/换集）全部走
  ``--input-ipc-server`` 的 JSON IPC；
- 对外暴露的属性和方法刻意与 python-mpv 的 ``MPV`` 对象保持一致
  （``obj["speed"] = 1.5`` / ``obj.command("loadfile", ...)`` /
  ``obj.pause``），因此 player.py 里其余逻辑可以完全复用。
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

# python-mpv 的属性名（下划线）→ mpv 属性名（连字符）
_PROPS = {
    "idle_active": "idle-active",
    "core_idle": "core-idle",
    "eof_reached": "eof-reached",
    "playback_time": "playback-time",
}


def find_mpv() -> str | None:
    """按优先级找 mpv 可执行文件：打包内置 → 工程内置 → /Applications → PATH"""
    exe = "mpv"
    cands = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cands.append(os.path.join(base, "mpv", "mpv"))
        cands.append(os.path.join(base, "mpv", "bin", "mpv"))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cands += [
        os.path.join(here, "third_party", "mpv", "bin", "mpv"),
        "/Applications/mpv.app/Contents/MacOS/mpv",
        "/opt/homebrew/bin/mpv",
        "/usr/local/bin/mpv",
    ]
    found = shutil.which(exe)
    if found:
        cands.append(found)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


class _IPC:
    """mpv JSON IPC 的同步请求/响应封装（多线程共用一把锁）"""

    def __init__(self, path: str, timeout: float = 5.0):
        self._lock = threading.RLock()
        self._rid = 0
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        self._sock.connect(path)
        self._f = self._sock.makefile("rwb")

    def request(self, *cmd):
        """发一条命令，返回 (ok, data)；事件消息会被跳过"""
        with self._lock:
            self._rid += 1
            rid = self._rid
            payload = json.dumps({"command": list(cmd), "request_id": rid})
            try:
                self._f.write((payload + "\n").encode())
                self._f.flush()
            except OSError:
                return False, None
            deadline = time.time() + 5.0
            while time.time() < deadline:
                try:
                    line = self._f.readline()
                except (socket.timeout, OSError):
                    return False, None
                if not line:
                    return False, None
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("request_id") != rid:
                    continue  # 事件或无 id 的响应
                return msg.get("error") == "success", msg.get("data")
        return False, None

    def close(self):
        with self._lock:
            for obj in (self._f, self._sock):
                try:
                    obj.close()
                except Exception:
                    pass


class MpvProcess:
    """等价于 python-mpv 的 ``mpv.MPV`` 对象（macOS 实现）"""

    def __init__(self, rect=None):
        object.__setattr__(self, "_proc", None)
        object.__setattr__(self, "_ipc", None)
        object.__setattr__(self, "_geometry", "")
        object.__setattr__(self, "_hidden", False)
        object.__setattr__(self, "_ready", False)
        self._start(rect)

    # ---- 进程生命周期 ----

    def _start(self, rect):
        binpath = find_mpv()
        if not binpath:
            raise OSError("未找到 mpv（macOS 需要 mpv.app 或 brew install mpv）")
        sock_path = os.path.join(
            tempfile.gettempdir(), "tvbox4win-%d.sock" % os.getpid())
        try:
            os.unlink(sock_path)
        except OSError:
            pass
        if rect:
            self._geometry = _fmt_geometry(*rect)
        args = [
            binpath,
            "--input-ipc-server=" + sock_path,
            "--idle=yes",
            "--force-window=yes",
            "--keep-open=yes",
            "--osc=no",
            "--no-border",          # 无边框，看起来像页面的一部分
            "--ontop",              # 置顶，避免被 tkinter 黑底窗口盖住
            "--focus-on-open=no",   # 不抢焦点，键盘快捷键仍由主窗口处理
            "--no-config",          # 不读用户 mpv.conf，行为可预期
            "--cursor-autohide=no",
            "--hwdec=auto-safe",
            "--title=TVBox4Win",
            "--volume=100",
        ]
        if self._geometry:
            args.append("--geometry=" + self._geometry)
        else:
            args.append("--geometry=64x64+6000+6000")  # 预热时放到屏幕外
        proc = subprocess.Popen(
            args, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        object.__setattr__(self, "_proc", proc)
        # 等 ipc socket 就绪并连上
        for _ in range(120):
            if proc.poll() is not None:
                raise OSError("mpv 进程异常退出（returncode=%s）" % proc.returncode)
            if os.path.exists(sock_path):
                try:
                    object.__setattr__(self, "_ipc", _IPC(sock_path))
                    break
                except OSError:
                    pass
            time.sleep(0.05)
        if self._ipc is None:
            raise OSError("mpv IPC 连接超时")
        object.__setattr__(self, "_ready", True)

    def alive(self) -> bool:
        p = self._proc
        return bool(p and p.poll() is None and self._ipc is not None)

    def terminate(self):
        ipc, proc = self._ipc, self._proc
        if ipc is not None:
            try:
                ipc.request("quit")
            except Exception:
                pass
            ipc.close()
        object.__setattr__(self, "_ipc", None)
        if proc is not None:
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        object.__setattr__(self, "_proc", None)
        object.__setattr__(self, "_ready", False)

    # ---- 命令 / 属性（对齐 python-mpv 的调用风格）----

    def command(self, *args):
        if self._ipc is None:
            return None
        ok, data = self._ipc.request(*args)
        if not ok:
            raise RuntimeError("mpv 命令失败: %r" % (args,))
        return data

    def _get(self, name):
        if self._ipc is None:
            return None
        ok, data = self._ipc.request("get_property", name)
        return data if ok else None

    def _set(self, name, value):
        if self._ipc is None:
            return
        self._ipc.request("set_property", name, value)

    def __setitem__(self, name, value):
        self._set(name, value)

    def __getitem__(self, name):
        return self._get(name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self._set(name.replace("_", "-"), value)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        prop = _PROPS.get(name, name.replace("_", "-"))
        return self._get(prop)

    # ---- 窗口位置（macOS 专用）----

    def set_rect(self, x, y, w, h):
        """把 mpv 窗口摆到指定屏幕矩形上（跟随视频容器变化）"""
        geom = _fmt_geometry(x, y, w, h)
        if geom == self._geometry or self._ipc is None:
            return
        object.__setattr__(self, "_geometry", geom)
        self._set("geometry", geom)

    def show(self):
        if self._hidden and self._ready:
            object.__setattr__(self, "_hidden", False)
            self._set("window-minimized", False)

    def hide(self):
        if not self._hidden and self._ready:
            object.__setattr__(self, "_hidden", True)
            try:
                self._ipc.request("set_property", "window-minimized", True)
            except Exception:
                pass


def _fmt_geometry(x, y, w, h) -> str:
    return "%dx%d+%d+%d" % (max(int(w), 16), max(int(h), 16), int(x), int(y))
