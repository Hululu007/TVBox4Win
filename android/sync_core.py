"""把桌面版的业务模块同步到 Android 工程的 vendor/ 目录。

Android 版只复用与界面无关的部分：
    配置解析（apiconfig） / CMS 请求（data_api） / 本地存储（hawk·store） / EPG（epg）
桌面 UI（tkinter）、播放器（libmpv / AVFoundation）、爬虫运行时（node / JVM）
在安卓上都没有对应实现，分别由 androidui/（Kivy）与系统 MediaPlayer 承担。

两个只在安卓需要不同实现的模块由本脚本生成：
    paths.py      数据目录改到 App 私有目录（APK 内部只读）
    ui_thread.py  主线程调度改用 Kivy 的 Clock（桌面版是 tkinter 的 after 泵）

用法（本地调试与 CI 构建前都要执行，生成物不入库）：

    python sync_core.py
"""
import io
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DESKTOP_PKG = os.path.join(HERE, "..", "tvboxpy", "tvboxosc")
DST = os.path.join(HERE, "vendor", "tvboxosc")

# 原样复制：这几个模块只依赖 requests / sqlite3 / json，与界面无关
COPY = ["apiconfig.py", "hawk.py", "store.py", "data_api.py", "epg.py"]

PATHS_PY = '''"""Android 数据路径：可写文件全部落在 App 私有目录。

APK 内部是只读的，因此 hawk.json / tvbox.db / error.log 统一写到
p4a 提供的 ANDROID_PRIVATE（/data/data/<package>/files/TVBox4Win/），
卸载应用时随之清理，符合安卓的沙箱惯例。

本文件由 android/sync_core.py 生成，请勿手改。
"""
import os

_PRIVATE = (os.environ.get("ANDROID_PRIVATE")
            or os.environ.get("HOME")
            or os.path.expanduser("~"))
APP_BASE = os.path.join(_PRIVATE, "TVBox4Win")
try:
    os.makedirs(APP_BASE, exist_ok=True)
except OSError:
    pass


def resource_path(*names):
    """随包分发的只读资源"""
    base = os.environ.get("ANDROID_APP_PATH") or os.path.dirname(
        os.path.abspath(__file__))
    return os.path.join(base, *names)


def data_path(*names):
    """持久化文件路径（hawk.json / tvbox.db / error.log）"""
    return os.path.join(APP_BASE, *names)


def log_error(*parts):
    """把异常追加到 error.log（手机上排查问题唯一可靠的落盘手段）"""
    import time
    import traceback
    try:
        with open(data_path("error.log"), "a", encoding="utf-8") as f:
            f.write("---- %s ----\\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            for p in parts:
                if isinstance(p, BaseException):
                    traceback.print_exception(type(p), p, p.__traceback__, file=f)
                else:
                    f.write(str(p) + "\\n")
    except OSError:
        pass
'''

UI_THREAD_PY = '''"""工作线程 -> 主线程的回调调度（Android / Kivy 版）。

Kivy 用 Clock.schedule_once 把回调送回主线程（可从任意线程调用）；
桌面上做纯业务自测（没装 kivy）时退化为同步执行，方便跑无界面的链路验证。

本文件由 android/sync_core.py 生成，请勿手改。
"""
try:
    from kivy.clock import Clock
except ImportError:          # 桌面纯业务自测环境：没有 kivy 就直接执行
    Clock = None


def bind(app=None):
    """Kivy 不需要显式启动泵，保留该函数以兼容调用方"""
    return None


def run(fn):
    """任意线程调用：把 fn 投递到主线程执行"""
    if Clock is None:
        _safe(fn)
        return
    Clock.schedule_once(lambda _dt: _safe(fn), 0)


def _safe(fn):
    try:
        fn()
    except Exception:
        import sys
        try:
            from .paths import log_error
            log_error("[ui_thread] 回调异常", sys.exc_info()[1])
        except Exception:
            pass
'''

INIT_PY = '''"""TVBox4Win 业务层（Android 子集）。

本目录由 android/sync_core.py 从 tvboxpy/tvboxosc 同步生成，请勿手改；
要改逻辑请改桌面版源文件后重新执行同步。
"""
VERSION = %r
'''


def _read_version():
    """版本号从桌面版 __init__.py 读，避免两处不一致"""
    import re
    p = os.path.join(DESKTOP_PKG, "__init__.py")
    with io.open(p, encoding="utf-8") as f:
        m = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', f.read())
    return m.group(1) if m else "0.0.0"


def main():
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST)
    for name in COPY:
        src = os.path.join(DESKTOP_PKG, name)
        if not os.path.isfile(src):
            raise SystemExit("缺少业务模块: %s" % src)
        shutil.copy2(src, os.path.join(DST, name))
    gen = {"paths.py": PATHS_PY,
           "ui_thread.py": UI_THREAD_PY,
           "__init__.py": INIT_PY % _read_version()}
    for name, body in gen.items():
        with io.open(os.path.join(DST, name), "w",
                     encoding="utf-8", newline="\n") as f:
            f.write(body)
    print("同步完成 -> %s" % DST)
    print("  复制: " + ", ".join(COPY))
    print("  生成: " + ", ".join(gen))
    print("  版本: " + _read_version())


if __name__ == "__main__":
    main()
