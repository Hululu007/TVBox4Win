"""主窗口 + 页面路由（对应 AppManager / HomeActivity 的页面切换）"""
import os
import sys
import tkinter as tk
from . import ui_thread, VERSION

from .theme import BG


def _icon_path():
    """应用图标路径：冻结时资源在 _MEIPASS/tvboxosc/assets，开发时在模块旁 assets"""
    base = getattr(sys, "_MEIPASS", None)
    root = (os.path.join(base, "tvboxosc", "assets") if base
            else os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"))
    return os.path.join(root, "tvbox4win.ico")


class App(tk.Tk):
    """对应 HomeActivity：承载所有页面 Frame，模拟 Android Activity 栈"""
    def __init__(self):
        super().__init__()
        self.title(f"TVBox4Win v{VERSION}")
        self.geometry("1280x720")
        self.configure(bg=BG)
        _ico = _icon_path()
        if os.path.exists(_ico):
            try:
                self.iconbitmap(_ico)
            except Exception:
                pass
        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)
        self.current = None
        self._current_route = None
        self._history = []
        self._classes = {"page": ""}
        ui_thread.bind(self)
        self.bind("<F11>", lambda e: self.attributes(
            "fullscreen", not self.attributes("fullscreen")))
        # 推送服务全局常驻（对应 ControlManager.startServer）
        try:
            from .ui_push import start_global_server
            start_global_server()
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def attributes(self, *args):
        """兼容层：Tk 9（macOS）要求属性名带前导横线，Windows 上不带也行。
        统一把 "fullscreen" 规范成 "-fullscreen"，各页面无需分别处理"""
        if args and args[0] == "fullscreen":
            args = ("-fullscreen",) + args[1:]
        return super().attributes(*args)

    def _on_close(self):
        """退出清理：回收 node/java 爬虫子进程（否则越积越多，越用越卡）"""
        try:
            from .spider import shutdown as _spider_shutdown
            _spider_shutdown()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def _destroy_current(self):
        if self.current is not None:
            try:
                self.current.destroy()
            finally:
                self.current = None

    def _capture_current_route(self):
        """记录当前页面的可恢复参数；页面可通过 capture_state() 更新。"""
        route = self._current_route
        if route is None or self.current is None:
            return None
        cls, args, kw = route
        capture = getattr(self.current, "capture_state", None)
        if capture is not None:
            try:
                state = capture()
                if state is not None:
                    saved_args, saved_kw = state
                    return cls, tuple(saved_args), dict(saved_kw)
            except Exception:
                from .paths import log_error
                log_error("[nav] 捕获页面状态失败", cls)
        return route

    def _show_route(self, route):
        cls, args, kw = route
        self._current_route = route
        self.current = cls(self.container, self, *args, **kw)
        self.current.pack(fill="both", expand=True)
        return self.current

    def switch(self, frame_cls, *args, push=True, **kw):
        """切换页面（对应 startActivity）；push=False 用于替换当前页面。"""
        if self.current is not None:
            if push:
                route = self._capture_current_route()
                if route is not None:
                    self._history.append(route)
            self._destroy_current()
        return self._show_route((frame_cls, args, kw))

    def go_back(self, fallback_cls=None, fallback_args=None, fallback_kwargs=None):
        """返回上一页；没有历史时进入指定兜底页面，再没有则回主页。"""
        self._destroy_current()
        if self._history:
            return self._show_route(self._history.pop())
        if fallback_cls is not None:
            return self._show_route((
                fallback_cls,
                tuple(fallback_args or ()),
                dict(fallback_kwargs or {}),
            ))
        return self.go_home()

    def go_home(self):
        """回到点播首页并清空导航栈，对应原版回到 HomeActivity。"""
        from .ui_grid import Page as GridPage
        self._history.clear()
        if self.current is not None:
            self._destroy_current()
        return self._show_route((GridPage, (), {}))

    def report_callback_exception(self, exc, val, tb):
        """Tk 回调异常兜底：打包成窗口程序后 stderr 丢失，
        异常会导致「点了没反应」，统一落 error.log 便于排查"""
        import traceback
        try:
            from .paths import log_error
            log_error("[tk] 回调异常", val)
        except Exception:
            pass
        traceback.print_exception(exc, val, tb)
