"""应用数据路径：冻结（PyInstaller 单文件）时资源在临时 _MEI 目录，
每次启动都会更换；所有需要持久化的文件必须放到固定位置。

- Windows：EXE 所在目录（沿用原设计，用户习惯「绿色版」）
- macOS：.app 内部是不可写的签名包，改放
  ~/Library/Application Support/TVBox4Win（沙盒外仍可直接编辑）
"""
import os
import sys

IS_MAC = sys.platform == "darwin"

if getattr(sys, "frozen", False):
    if IS_MAC:
        APP_BASE = os.path.join(
            os.path.expanduser("~/Library/Application Support"), "TVBox4Win")
        try:
            os.makedirs(APP_BASE, exist_ok=True)
        except OSError:
            APP_BASE = os.path.dirname(os.path.abspath(sys.executable))
    else:
        APP_BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*names):
    """随包分发的只读资源（assets / spider_runtime）路径"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, *names)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *names)


def data_path(*names):
    """持久化文件路径（hawk.json / tvbox.db / error.log）"""
    return os.path.join(APP_BASE, *names)


def log_error(*parts):
    """把异常/诊断信息追加到 error.log（排查打包后问题时用）"""
    import time
    import traceback
    try:
        with open(data_path("error.log"), "a", encoding="utf-8") as f:
            f.write("---- %s ----\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            for p in parts:
                if isinstance(p, BaseException):
                    traceback.print_exception(type(p), p, p.__traceback__, file=f)
                else:
                    f.write(str(p) + "\n")
    except OSError:
        pass
