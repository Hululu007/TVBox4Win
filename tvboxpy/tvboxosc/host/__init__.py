"""平台门面：共享代码获取平台能力的唯一入口。

共享代码（ui_*.py / spider.py / apiconfig.py / main.py …）只允许：

    from .host import app_base, font_candidates, chrome_insets, node_path, player

不允许出现 ``sys.platform`` / ``darwin`` / ``win32`` 判断，
tests/verify_platform_isolation.py 会断言这一点。

平台实现在 host/win.py 与 host/mac.py，两者互不引用；改一边不会碰到另一边。
"""
import os
import sys

IS_MAC = sys.platform == "darwin"
IS_WIN = not IS_MAC

if IS_MAC:
    from . import mac as _impl
else:
    from . import win as _impl


# ---------------------------------------------------------------- 基础环境

def app_base(frozen, exe_dir, src_dir):
    return _impl.app_base(frozen, exe_dir, src_dir)


def font_candidates():
    return _impl.font_candidates()


def chrome_insets():
    return _impl.chrome_insets()


def node_path():
    """第一个存在的 node 可执行文件；找不到返回 None（调用方决定怎么报错）"""
    import shutil
    cand = shutil.which("node")
    if cand and os.path.isfile(cand):
        return cand
    for c in _impl.node_candidates():
        if c and os.path.isfile(c):
            return c
    return None


# ---------------------------------------------------------------- 播放后端

class _PlayerFacade:
    """把平台后端包一层，屏蔽差异（也方便测试替换）"""

    def attach_widget(self, widget, insets=(0, 0, 0, 0)):
        return _impl.attach_widget(widget, insets)

    def acquire(self, wid, rect=None):
        return _impl.acquire(wid, rect)

    def release(self, core):
        return _impl.release(core)

    def stop(self, core):
        return _impl.stop(core)

    def shutdown(self):
        return _impl.shutdown()

    def warmup(self):
        return _impl.warmup()

    @property
    def name(self):
        getter = getattr(_impl, "backend_name", None)
        return getter() if getter else _impl.NAME


player = _PlayerFacade()
