"""macOS 平台实现。

改 macOS 行为只动本文件（播放后端 + 数据目录 + 字体 + node 路径）。
Windows 侧见 host/win.py，两边互不引用。

播放后端选型：装了 mpv（brew）优先用「独立 mpv 进程 + JSON IPC」（格式全），
否则退回系统自带 AVFoundation。两种后端的可见性/几何同步都在这里处理，
共享代码只拿到一个与 python-mpv 同形的 core 对象。
"""
import glob
import os
import sys

# 两个后端实现保持原位（player_mac.py / player_av.py），macOS 侧改动仍在原文件
from ..player_mac import find_mpv, MpvProcess
from ..player_av import AvCore

NAME = "mpv-process"          # 首次播放探测后可能变成 "av"，见 _backend_name()

# ---------------------------------------------------------------- 路径 / 字体

def app_base(frozen, exe_dir, src_dir):
    """.app 内部是只读签名包，数据改放 ~/Library/Application Support"""
    if not frozen:
        return src_dir
    base = os.path.join(os.path.expanduser("~/Library/Application Support"),
                        "TVBox4Win")
    try:
        os.makedirs(base, exist_ok=True)
        return base
    except OSError:
        return exe_dir


def font_candidates():
    return ["PingFang SC", "Hiragino Sans GB", "Heiti SC", "Songti SC"]


def node_candidates():
    home = os.path.expanduser("~")
    cands = ["/opt/homebrew/bin/node",      # Apple Silicon Homebrew
             "/usr/local/bin/node",         # Intel Homebrew
             os.path.join(home, ".local/bin/node")]
    # nvm / volta / 便携包这类版本管理器装的 node
    for pat in (os.path.join(home, ".nvm/versions/node/*/bin/node"),
                os.path.join(home, ".volta/bin/node"),
                os.path.join(home, ".workbuddy/binaries/node/versions/*/bin/node")):
        cands += sorted(glob.glob(pat), reverse=True)
    return cands


def chrome_insets():
    """独立视频窗口要避开页面自绘的顶栏(42)与底栏(96)，否则按钮被盖住"""
    return (42, 0, 96, 0)


# ---------------------------------------------------------------- 播放后端

_shared = None
_geom_job = None
_widget = None
_insets = (42, 0, 96, 0)
_backend = None          # "mpv" | "av"


def backend_name():
    """诊断用：实际选中的后端（首次播放后才确定）"""
    return _backend or NAME


def _rect():
    """视频容器的屏幕矩形（已扣除 insets）；拿不到就返回 None"""
    w = _widget
    if w is None:
        return None
    try:
        w.update_idletasks()
        top, right, bottom, left = _insets
        x = w.winfo_rootx() + left
        y = w.winfo_rooty() + top
        cw = w.winfo_width() - left - right
        ch = w.winfo_height() - top - bottom
        if cw < 32 or ch < 32:
            return None
        return (x, y, cw, ch)
    except Exception:
        return None


def _on_configure(_e=None):
    """容器尺寸变化（含进出全屏）时把视频窗口重新对齐，节流到 80ms"""
    global _geom_job
    if _geom_job is not None:
        return
    try:
        _geom_job = _widget.after(80, _sync_geometry)
    except Exception:
        _geom_job = None


def _sync_geometry():
    global _geom_job
    _geom_job = None
    rect = _rect()
    if rect and _shared is not None:
        try:
            _shared.set_rect(*rect)
        except Exception:
            pass


def _on_destroy(e=None):
    """容器被销毁：收起视频窗口，别让黑框留在桌面上"""
    if e is not None and getattr(e, "widget", None) is not _widget:
        return  # 子控件销毁事件，忽略
    try:
        if _shared is not None:
            _shared.hide()
    except Exception:
        pass


def attach_widget(widget, insets=(0, 0, 0, 0)):
    """记录容器并跟随其尺寸；返回初始矩形（新建视频窗口时用）"""
    global _widget, _insets
    _widget = widget
    _insets = insets or _insets
    if widget is None:
        return None
    try:
        widget.bind("<Configure>", _on_configure, add="+")
        widget.bind("<Destroy>", _on_destroy, add="+")
    except Exception:
        pass
    try:
        widget.winfo_toplevel().bind("<Configure>", _on_configure, add="+")
    except Exception:
        pass
    return _rect()


def _make_core(rect):
    """选后端：mpv 能起来就用 mpv（格式最全），否则退回系统 AVFoundation"""
    global _backend
    if _backend is None:
        force = os.environ.get("TVBOX_PLAYER", "").lower()
        if force == "av":
            _backend = "av"
        elif find_mpv() is None:
            _backend = "av"
        else:
            try:
                _backend = "mpv"
                return MpvProcess(rect)
            except Exception:
                _backend = "av"
    try:
        if _backend == "mpv":
            return MpvProcess(rect)
    except Exception:
        _backend = "av"
    return AvCore(rect)


def acquire(wid, rect=None):
    """复用存活核心（必要时重设矩形并显示）；否则按 rect 新建"""
    global _shared
    if _shared is not None:
        if not _shared.alive():
            try:
                _shared.terminate()
            except Exception:
                pass
            _shared = None
        else:
            if rect:
                try:
                    _shared.set_rect(*rect)
                except Exception:
                    pass
            _shared.show()
            return _shared
    _shared = _make_core(rect if rect is not None else _rect())
    return _shared


def release(core):
    """没有嵌入窗口，收起视频窗口即可"""
    try:
        core.hide()
    except Exception:
        pass


def stop(core):
    try:
        core.command("stop")
    except Exception:
        pass
    try:
        core.hide()
    except Exception:
        pass


def shutdown():
    global _shared
    if _shared is not None:
        try:
            _shared.terminate()
        except Exception:
            pass
        _shared = None


def warmup():
    """独立进程启动很快，提前拉起来反而会闪一个空窗口"""
    return find_mpv() is not None
