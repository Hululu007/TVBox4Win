"""应用数据路径：冻结（PyInstaller 单文件）时资源在临时 _MEI 目录，
每次启动都会更换；所有需要持久化的文件必须放到 EXE 所在目录。"""
import os
import sys

if getattr(sys, "frozen", False):
    APP_BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_path(*names):
    """EXE（或项目根）目录下的持久化文件路径"""
    return os.path.join(APP_BASE, *names)


def log_error(*parts):
    """把异常/诊断信息追加到 EXE 旁 error.log（排查打包后问题时用）"""
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
