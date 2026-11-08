# -*- coding: utf-8 -*-
"""海报图片内存回归：控件销毁后 PhotoImage 必须被回收

背景：早期用模块级 `_keep = {}` 存所有 PhotoImage，只在同 key 重渲染或控件
已销毁时 pop，页面 destroy 时没人清理。一张 238x312 海报常驻约 307KB，
逛几百部片就是上百 MB。现在改为挂在控件身上（imgcache.attach）。

断言：
1. imgcache 不再持有任何全局 PhotoImage 注册表
2. 控件活着时图片不会被提前 GC（Tk 图像名仍然有效）
3. 控件销毁 + gc 后，所有 PhotoImage 都能被回收
"""
import gc
import os
import sys
import tkinter as tk
import weakref

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tvboxosc import imgcache

N = 60
W, H = 60, 78          # 小图即可验证生命周期，不必真下载海报
fail = []


def check(name, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + name + (("：" + detail) if detail else ""))
    if not ok:
        fail.append(name)


def sample_png(path):
    """造一张纯色 PNG 当海报源图（不联网）"""
    try:
        from PIL import Image
    except ImportError:
        return None
    Image.new("RGB", (W, H), (40, 60, 90)).save(path)
    return path


def main():
    # 1. 静态：不能残留全局注册表
    leftovers = [n for n in ("_keep",) if hasattr(imgcache, n)]
    check("imgcache 无全局 PhotoImage 注册表", not leftovers,
          "残留 %s" % leftovers)
    check("对外接口是 attach(widget, photo)",
          callable(getattr(imgcache, "attach", None)))

    tmp = os.path.join(os.environ.get("TEMP", ROOT), "_verify_poster.png")
    if not sample_png(tmp):
        print("SKIP Pillow 不可用，跳过运行期用例")
        return report()
    if not os.path.isfile(tmp):
        print("SKIP 无法生成测试图")
        return report()

    root = tk.Tk()
    root.geometry("400x300")
    root.update()
    frame = tk.Frame(root)
    frame.pack()

    labels, refs = [], []
    for i in range(N):
        lb = tk.Label(frame, bg="#101828")
        lb.pack()
        photo = tk.PhotoImage(file=tmp)
        imgcache.attach(lb, photo)
        lb.configure(image=photo)
        labels.append(lb)
        refs.append(weakref.ref(photo))
        del photo            # 只留控件上的引用

    root.update()

    # 2. 控件活着 → 图片必须还活着（否则海报会变空白）
    alive_while_shown = sum(1 for r in refs if r() is not None)
    check("控件存活期间图片未被 GC", alive_while_shown == N,
          "%d/%d 存活" % (alive_while_shown, N))
    # Tk 侧的图像对象也要在（Python 引用还在但 Tk 图像被删同样是白图）
    bad = 0
    for lb in labels:
        name = str(lb.cget("image"))
        try:
            if not name or int(root.tk.call("image", "width", name)) != W:
                bad += 1
        except tk.TclError:
            bad += 1
    check("Tk 图像对象仍可解析（海报不会变白）", bad == 0, "%d 个异常" % bad)

    # 3. 销毁后必须全部可回收
    for lb in labels:
        lb.destroy()
    del lb               # 循环变量还指着最后一个控件，会拖住它的图片
    labels = []
    frame.destroy()
    root.update()
    gc.collect()
    alive_after = sum(1 for r in refs if r() is not None)
    check("控件销毁后图片全部释放", alive_after == 0,
          "%d/%d 仍被持有" % (alive_after, N))

    root.destroy()
    del root
    gc.collect()
    try:
        os.remove(tmp)
    except OSError:
        pass
    return report()


def report():
    print()
    if fail:
        print("失败 %d 项：%s" % (len(fail), ", ".join(fail)))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
