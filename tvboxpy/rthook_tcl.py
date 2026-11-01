"""PyInstaller 运行时钩子：把 Tcl/Tk 资源目录指给 _tkinter

uv 提供的 python-build-standalone 用的是 Tcl/Tk 9.0（目录名 tcl9.0 / tk9.0），
PyInstaller 默认只认 tcl8.6。打包后若找不到 init.tcl，启动会报
"Cannot find a usable init.tcl"，这里在导入 tkinter 之前把环境变量补齐。
"""
import os
import sys

_base = getattr(sys, "_MEIPASS", None)
if _base and "TCL_LIBRARY" not in os.environ:
    for name in ("tcl9.0", "tcl8.6", "tcl9", "tcl8"):
        path = os.path.join(_base, "lib", name)
        if os.path.isdir(path):
            os.environ["TCL_LIBRARY"] = path
            break
    for name in ("tk9.0", "tk8.6", "tk9", "tk8"):
        path = os.path.join(_base, "lib", name)
        if os.path.isdir(path):
            os.environ["TK_LIBRARY"] = path
            break
