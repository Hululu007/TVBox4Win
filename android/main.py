"""TVBox4Win 安卓版入口（Kivy）。

构建前先跑 `python sync_core.py` 把桌面版的业务模块同步到 vendor/。
本地桌面调试：装好 kivy 后直接 `python main.py` 即可开窗口预览界面。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# 业务层（vendor/tvboxosc，由 sync_core.py 生成）
_VENDOR = os.path.join(HERE, "vendor")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)


def main():
    from androidui.app import TVBoxApp
    TVBoxApp().run()


if __name__ == "__main__":
    main()
