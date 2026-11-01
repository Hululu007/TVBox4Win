# -*- coding: utf-8 -*-
"""诊断：逐秒跟踪 TVBox4Win 窗口生命周期（不负责启动，由调用方先拉起进程）

用法：python tests/diag_exe.py [秒数]
"""
import subprocess
import sys
import time

import win32gui
import win32process

SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 25


def wins():
    out = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h) or ""
            if t.startswith("TVBox4Win"):
                _, pid = win32process.GetWindowThreadProcessId(h)
                out.append((h, t, pid))
    win32gui.EnumWindows(cb, None)
    return out


for i in range(1, SECS + 1):
    time.sleep(1)
    w = wins()
    procs = subprocess.run(["tasklist", "/FI", "IMAGENAME eq TVBox4Win.exe", "/NH"],
                           capture_output=True, text=True, encoding="gbk",
                           errors="ignore").stdout
    n = procs.count("TVBox4Win.exe")
    if w:
        h, t, pid = w[0]
        try:
            state = "rect=%s" % (win32gui.GetWindowRect(h),)
        except Exception as e:
            state = "rect失效(%s)" % e
        print("%2ds 窗口=%s [%s] pid=%s %s 进程数=%d" % (i, h, t, pid, state, n), flush=True)
    else:
        print("%2ds 无窗口 进程数=%d" % (i, n), flush=True)
