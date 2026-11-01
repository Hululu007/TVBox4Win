"""Windows 平台实现。

改 Windows 行为只动本文件（播放后端 + 数据目录 + 字体 + node 路径）。
macOS 侧见 host/mac.py，两边互不引用。
"""
import os
import sys
import threading

NAME = "libmpv"

# ---------------------------------------------------------------- 路径 / 字体

def app_base(frozen, exe_dir, src_dir):
    """Windows 沿用「绿色版」习惯：持久化数据放 EXE 所在目录"""
    return exe_dir if frozen else src_dir


def font_candidates():
    return ["Microsoft YaHei UI", "Microsoft YaHei", "SimHei"]


def node_candidates():
    home = os.path.expanduser("~")
    return [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     "nodejs", "node.exe"),
        os.path.join(home, "AppData", "Roaming", "npm", "node.exe"),
        # 本机随 WorkBuddy 分发的便携 node（存在才会命中）
        os.path.join(home, ".workbuddy", "binaries", "node",
                     "versions", "22.22.2-6", "node.exe"),
    ]


def chrome_insets():
    """mpv 直接嵌进 video 容器，不需要为自绘控制栏留边距"""
    return (0, 0, 0, 0)


# ---------------------------------------------------------------- 播放后端

_shared = None
_lock = threading.Lock()


def _prepare_dll():
    """把 third_party/mpv 与 PyInstaller 临时目录加进 PATH，libmpv-2.dll 才能被找到"""
    here = os.path.dirname(os.path.abspath(__file__))       # tvboxosc/host
    pkg_root = os.path.dirname(os.path.dirname(here))       # tvboxpy
    dll_dir = os.path.join(pkg_root, "third_party", "mpv")
    os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        os.environ["PATH"] = mei + os.pathsep + os.environ["PATH"]


def attach_widget(widget, insets=(0, 0, 0, 0)):
    """Windows 靠 wid 嵌入，容器尺寸由 mpv 自己跟随，无需返回矩形"""
    return None


def acquire(wid, rect=None):
    """复用存活核心（运行时改 wid 换嵌入窗口）；核心已 shutdown 则重建。"""
    global _shared
    with _lock:
        if _shared is not None:
            try:
                _ = _shared.idle_active  # 探测核心是否存活
                try:
                    _shared["wid"] = str(wid)
                except Exception:
                    pass
                return _shared
            except Exception:
                try:
                    _shared.terminate()
                except Exception:
                    pass
                _shared = None
        import mpv  # 延迟导入：DLL 路径准备好之后再加载
        # osc=no：播放页自带控制栏（原版 bottom_container），避免双进度条
        # network_timeout：网络流挂死保护；实测 cache=yes 反而拖慢起播
        # （mpv 默认 cache 策略最快），故不加
        _shared = mpv.MPV(wid=str(wid), osc="no",
                          force_window="no", keep_open="yes",
                          network_timeout=8)
        return _shared


def release(core):
    """把 mpv 从当前嵌入窗口解绑（wid=0）。

    页面销毁后若 mpv 仍向失效 HWND 渲染，会拖住核心甚至卡死 UI 线程。"""
    try:
        core["wid"] = "0"
    except Exception:
        pass


def stop(core):
    try:
        core.command("stop")
    except Exception:
        pass


def shutdown():
    global _shared
    with _lock:
        if _shared is not None:
            try:
                _shared.terminate()
            except Exception:
                pass
            _shared = None


def warmup():
    """预热：DLL 加载 + 核心 init 是首次点播放时 1~2 秒的固定开销"""
    _prepare_dll()
    try:
        acquire(0)
        return True
    except Exception:
        return False


_prepare_dll()
