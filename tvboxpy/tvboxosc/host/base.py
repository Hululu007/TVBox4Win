"""平台后端接口约定。

共享代码（ui_*.py / spider / apiconfig …）**不得**出现 sys.platform 判断，
所有平台差异都从这里转发到 host/win.py 或 host/mac.py。

新增一个平台 = 新增 host/<name>.py 实现下面这组函数，
共享代码与 player.py 都不需要改：

    NAME                      后端名（诊断用，如 "libmpv" / "av" / "mpv-process"）
    app_base(frozen, exe_dir, src_dir) -> str
                              持久化数据目录（hawk.json / tvbox.db / error.log）
    font_candidates() -> list[str]
                              中文字体候选（按优先级）
    node_candidates() -> list[str]
                              node 可执行文件候选路径
    chrome_insets() -> tuple  页面自绘控制栏占用的边距 (上,右,下,左)
    make_player() -> PlayerBackend
                              播放后端实例

PlayerBackend 的方法集合由 tests/verify_platform_isolation.py 断言一致，
某一平台加了方法却忘了另一平台时测试会失败。

后端方法语义（宽严都以「失败不抛」为准，实现内部自行 try/except）：

    attach_widget(widget, insets) -> rect|None
        player 拿到 tkinter 容器后第一步调用。返回初始屏幕矩形（无独立
        窗口的平台返回 None）。需要跟随容器尺寸的平台在这里绑 <Configure>。
    acquire(wid, rect=None) -> core
        取出可用的播放核心：复用存活核心（必要时重绑嵌入窗口）或新建。
    release(core) -> None
        播放页销毁时收尾：解绑嵌入窗口 / 收起独立窗口。
    stop(core) -> None
        停止播放但保留核心（核心销毁后重建会崩）。
    shutdown() -> None
        进程退出时真正销毁核心。
    warmup() -> bool
        启动时预热（可选，失败返回 False 即可）。
"""
from __future__ import annotations


class PlayerBackend:
    """接口说明用；实际实现是模块级函数，不强制继承。"""

    NAME = "abstract"

    def attach_widget(self, widget, insets=(0, 0, 0, 0)):
        return None

    def acquire(self, wid, rect=None):
        raise NotImplementedError

    def release(self, core):
        raise NotImplementedError

    def stop(self, core):
        raise NotImplementedError

    def shutdown(self):
        raise NotImplementedError

    def warmup(self):
        return False


# 后端必须实现的函数名（tests 用它做跨平台一致性断言）
BACKEND_API = ("attach_widget", "acquire", "release", "stop", "shutdown",
               "warmup", "NAME")
