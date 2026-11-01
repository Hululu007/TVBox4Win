"""后台任务：所有网络请求与解析都在线程池里跑，结果经 Kivy 的 Clock 回主线程。

桌面版是自己写 ui_thread 泵，Kivy 用 Clock.schedule_once 更省事（可从任意线程调用）。
"""
from concurrent.futures import ThreadPoolExecutor

from kivy.clock import Clock

_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="tvbox")


def run(fn, ok=None, err=None):
    """在线程池执行 fn；成功回调 ok(结果)，异常回调 err(错误文本)"""

    def _work():
        try:
            res = fn()
        except Exception as e:          # 线程里抛异常会静默丢失，必须转成回调
            if err is not None:
                Clock.schedule_once(lambda _dt: err("%s: %s" % (
                    type(e).__name__, e)), 0)
            return
        if ok is not None:
            Clock.schedule_once(lambda _dt: ok(res), 0)

    _pool.submit(_work)
