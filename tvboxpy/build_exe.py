# -*- coding: utf-8 -*-
"""一键打包 tvboxpy.exe（每次改完代码跑这个）

用法: python build_exe.py
产出: dist/TVBox4Win.exe（onefile，同目录带 jvmrt/dex-tools 资产）
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(os.path.dirname(HERE), "build")
DIST = os.path.join(HERE, "dist")

# 打包用的 Python（需已安装 PyInstaller）
PY = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"

# JVM 运行时资产（jar 类爬虫）：EXE 旁边的 jvmrt/ 与 dex-tools-v2.4/
ASSETS = [
    (os.path.join(BUILD, "jvmrt", "stubs.jar"), os.path.join("jvmrt", "stubs.jar")),
    (os.path.join(BUILD, "jvmrt", "native-bridge.jar"), os.path.join("jvmrt", "native-bridge.jar")),
    (os.path.join(BUILD, "jvmrt", "spiderrunner.jar"), os.path.join("jvmrt", "spiderrunner.jar")),
    (os.path.join(BUILD, "jvmrt", "libs"), os.path.join("jvmrt", "libs")),
    (os.path.join(BUILD, "dex-tools-v2.4"), "dex-tools-v2.4"),
]


def _pyinstaller_env():
    """给 PyInstaller 的 Tcl/Tk 探测提供 Windows Python 自带库路径。

    这套 Python 运行时能找到 tcl86t.dll，但 PyInstaller 的 hook 在未显式
    设置 TCL_LIBRARY/TK_LIBRARY 时会误判 tkinter 不可用并直接排除。
    """
    env = os.environ.copy()
    python_root = os.path.dirname(PY)
    candidates = (
        ("TCL_LIBRARY", os.path.join(python_root, "tcl", "tcl8.6")),
        ("TK_LIBRARY", os.path.join(python_root, "tcl", "tk8.6")),
    )
    for name, path in candidates:
        if os.path.isfile(os.path.join(path, "init.tcl" if name == "TCL_LIBRARY"
                                       else "tk.tcl")):
            env.setdefault(name, path)
    return env


def main():
    print("== PyInstaller ==")
    subprocess.check_call([PY, "-m", "PyInstaller", "tvboxpy.spec",
                           "--noconfirm", "--clean"],
                          cwd=HERE, env=_pyinstaller_env())
    print("== 复制 JVM 资产 ==")
    for src, rel in ASSETS:
        dst = os.path.join(DIST, rel)
        parent = os.path.dirname(dst)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        print("  +", rel)
    size = sum(
        os.path.getsize(os.path.join(r, f))
        for r, _, fs in os.walk(os.path.join(DIST, "jvmrt")) for f in fs)
    size += os.path.getsize(os.path.join(DIST, "TVBox4Win.exe"))
    print("== 完成: %s (exe+资产 %.0f MB) ==" % (
        os.path.join(DIST, "TVBox4Win.exe"), size / 1048576))


if __name__ == "__main__":
    main()
