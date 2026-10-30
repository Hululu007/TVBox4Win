"""线程安全的 UI 调度（工作线程 -> 主线程回调）"""
import queue

_q = queue.Queue()
_app = None


def bind(app):
    """主窗口创建后调用，启动主线程泵"""
    global _app
    _app = app
    _pump()


def _pump():
    while True:
        try:
            fn = _q.get_nowait()
        except queue.Empty:
            break
        try:
            fn()
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                from .paths import log_error
                import sys
                log_error("[ui_thread] 回调异常", sys.exc_info()[1])
            except Exception:
                pass
    if _app is not None and _app.winfo_exists():
        _app.after(40, _pump)


def run(fn):
    """任意线程调用：把 fn 投递到主线程执行"""
    _q.put(fn)
