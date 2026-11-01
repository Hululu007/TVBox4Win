"""tvboxosc 主入口（对应 App.java 启动流程：初始化 ApiConfig → HomeActivity）"""
import sys
import tkinter as tk

from tvboxosc import hawk, apiconfig, ui_thread
from tvboxosc.app import App
from tvboxosc.theme import FocusLabel, tv_font
from tvboxosc.ui_user import UserFragment
from tvboxosc.ui_user import PlaceholderPage


def self_check():
    """打包自检：验证所有页面模块可导入，结果写入 check_result.txt"""
    import os, traceback
    lines = []
    for m in ["ui_grid", "ui_search", "ui_history", "ui_collect", "ui_detail",
              "ui_play", "ui_live", "ui_push", "ui_setting", "spider", "player"]:
        try:
            __import__(f"tvboxosc.{m}", fromlist=["*"])
            lines.append(f"{m}: OK")
        except Exception as e:
            lines.append(f"{m}: FAIL {e.__class__.__name__}: {e}")
            lines.append(traceback.format_exc())
    with open("check_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    sys.exit(0)


DEFAULT_CONFIG = "https://cyao2q.github.io/files/m.json"

# 冒烟自检用的公开测试流（HLS，与业务源无关）
SMOKE_URL = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"


def smoke_test():
    """打包后冒烟自检：真建窗口 + 播一段测试流，检查解码/seek/暂停链路。

    用法：TVBox4Win.app/Contents/MacOS/TVBox4Win --smoke
    结果写 smoke_result.txt（EXE 同级），无界面环境下也能跑。"""
    import time
    from tvboxosc.app import App
    from tvboxosc.ui_play import Page as PlayPage

    app = App()
    series = (("测试线路", ["第01集"]), [SMOKE_URL])
    page = app.switch(PlayPage, "smoke", "smoke", "冒烟自检", "测试线路",
                      "第01集", SMOKE_URL, series=series, ep_index=0)

    def pump(sec):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.05)

    def wait_playback(timeout=30.0):
        """轮询等待真正出画面：首启要加载解码器，固定 sleep 会误判失败"""
        end = time.time() + timeout
        while time.time() < end:
            app.update()
            time.sleep(0.1)
            if page.player and page.player.status()[0] > 1.0:
                return True
        return False

    ok = wait_playback()
    _, dur0, _ = page.player.status() if page.player else (0, 0, True)
    if page.player:
        page.player.seek(max(0, min(dur0 - 5, 30)))
    # 拖动后 HLS 要重新取分片，同样轮询而不是固定等 2 秒
    ok_seek = False
    end = time.time() + 15
    while time.time() < end:
        app.update()
        time.sleep(0.1)
        if page.player and page.player.status()[0] > 5.0:
            ok_seek = True
            break
    # 放在最后读：刚出画面时 AVPlayer 可能还没报出总时长
    pos, dur, _ = page.player.status() if page.player else (0, 0, True)
    lines = [
        "player_backend: %s" % (page.player.backend_name if page.player else "-"),
        "position: %.1f" % pos,
        "duration: %.1f" % dur,
        "decode_ok: %s" % ("YES" if ok else "NO"),
        "seek_ok: %s" % ("YES" if ok_seek else "NO"),
    ]
    from tvboxosc.paths import data_path
    out = data_path("smoke_result.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines) + "\n-> " + out, flush=True)
    try:
        app.destroy()
    except Exception:
        pass


def _java_available():
    """本机是否有可用 JDK（jar 爬虫源依赖它，macOS 上多半没有）"""
    import glob
    import os
    if os.environ.get("JAVA_HOME"):
        return True
    try:
        return bool(glob.glob("/Library/Java/JavaVirtualMachines/*"))
    except Exception:
        return False


def _is_jar_source(bean):
    """api 以 csp_ 开头的站点走 jar 爬虫（见 spider.get_spider 的判定）"""
    return str(getattr(bean, "api", "") or "").startswith("csp_") or \
        bool(getattr(bean, "jar", ""))


def _pick_default_site():
    """选默认站点：优先不需要额外运行时的 CMS(type 0/1/2)，
    没有 JDK 时跳过 jar 爬虫源，避免首页直接报「分类加载失败」"""
    keys = apiconfig.api_config.source_key_list
    if not keys:
        return ""
    usable = [b for b in (apiconfig.api_config.get(k) for k in keys) if b is not None]
    has_java = _java_available()
    for b in usable:
        if b.type in (0, 1, 2) and not _is_jar_source(b):
            return b.key
    for b in usable:
        if not _is_jar_source(b):
            return b.key
    if not has_java:
        for b in usable:
            if b.type in (0, 1, 2):
                return b.key
    return usable[0].key if usable else keys[0]


def main():
    if "--check" in sys.argv:
        self_check()
    if "--smoke" in sys.argv:
        smoke_test()
        sys.exit(0)
    # 老用户迁移：仍指向旧默认源的直接切到新默认源
    if hawk.get(hawk.DEFAULT_API, "http://xhztv.top/4k.json") == "http://xhztv.top/4k.json":
        hawk.put(hawk.DEFAULT_API, DEFAULT_CONFIG)
    if hawk.get(hawk.HOME_API, "") in ("", "http://xhztv.top/4k.json"):
        hawk.put(hawk.HOME_API, DEFAULT_CONFIG)
    cfg_url = sys.argv[1] if len(sys.argv) > 1 else \
        hawk.get(hawk.DEFAULT_API, DEFAULT_CONFIG)

    app = App()

    # 预热 mpv 核心：DLL 加载 + 核心 init 是首次点播放 1~2 秒的固定开销，
    # 启动时后台做掉，用户点播放即可立即起播（原版 ijk 内核随进程初始化）
    def _warmup():
        try:
            from tvboxosc.player import MpvPlayer
            MpvPlayer.warmup()
        except Exception:
            pass
    import threading
    threading.Thread(target=_warmup, daemon=True).start()

    # 启动页：加载失败时留在本页给「重试 / 更换配置」，而不是让人重启程序
    loading = tk.Frame(app.container, bg="#000000")
    loading.pack(fill="both", expand=True)
    box = tk.Frame(loading, bg="#000000")
    box.place(relx=0.5, rely=0.42, anchor="center")
    tk.Label(box, text="TVBox", bg="#000000", fg="#FFFFFF",
             font=tv_font(26, True)).pack(pady=(0, 14))
    tip = tk.Label(box, text="正在加载接口配置...", bg="#000000", fg="#BFBFBF",
                   font=tv_font(14), justify="center", wraplength=720)
    tip.pack()
    actions = tk.Frame(box, bg="#000000")
    # takefocus：Label 默认不参与 Tab 遍历，键盘用户会卡在「重试」上
    btn_retry = FocusLabel(actions, text="重试", bg="#1C1C1C", fg="#FFFFFF",
                           font=tv_font(12), on_select=lambda: _retry(),
                           takefocus=1)
    btn_retry.pack(side="left", padx=(0, 20))
    FocusLabel(actions, text="更换配置", bg="#1C1C1C", fg="#FFFFFF",
               font=tv_font(12), on_select=lambda: _change_config(),
               takefocus=1).pack(side="left")

    state = {"url": cfg_url, "save_default": False}

    def _loading_alive():
        try:
            return bool(loading.winfo_exists())
        except Exception:
            return False

    def _show_actions(show):
        if not _loading_alive():
            return
        if show:
            actions.pack(pady=(18, 0))
            btn_retry.focus_set()
        else:
            actions.pack_forget()

    def _enter():
        try:
            if not app.winfo_exists():   # 缓存提示延迟期间用户可能已关窗
                return
        except Exception:
            return
        if _loading_alive():
            loading.destroy()
        if hawk.get("home_page", "vod") == "live":
            # 设置页「下次进入」选了直播：启动直达直播页
            from tvboxosc.ui_live import Page as LivePage
            app.switch(LivePage)
        else:
            # 对应原版 HomeActivity 默认 tab：启动直达点播首页（GridFragment）
            from tvboxosc.ui_grid import Page as GridPage
            app.switch(GridPage)

    def on_ok():
        # 直接进界面，绝不做站点探测（探测太慢，用户等着急）
        # 没有默认源就用第一个站点，失效了用户可用「切换源」自行换
        key = hawk.get(hawk.HOME_SOURCE)
        bean = apiconfig.api_config.get(key) if key else None
        if bean is None:
            # 当前源不存在 → 自动换可用站点
            key = _pick_default_site()
            hawk.put(hawk.HOME_SOURCE, key)
        elif _is_jar_source(bean) and not _java_available():
            # 上次用的 jar 源，但这台机器没有 JDK → 换成能打开的站点
            new_key = _pick_default_site()
            if new_key and new_key != key:
                key = new_key
                hawk.put(hawk.HOME_SOURCE, key)
        if state["save_default"]:
            hawk.put(hawk.DEFAULT_API, state["url"])
            state["save_default"] = False
        if not _loading_alive():
            _enter()
            return
        if apiconfig.api_config.last_from_cache:
            # 网络挂了但缓存可用：明确告知来源，短暂停留后自动进入
            _show_actions(False)
            tip.configure(text="网络不可用，正在使用上次缓存的配置…")
            loading.after(1200, _enter)
        else:
            _enter()

    def on_err(msg):
        if not _loading_alive():
            # 已经进了界面（首页建好了再报错），别去动已销毁的控件
            from tvboxosc.paths import log_error
            log_error("[main] 配置加载失败", msg)
            return
        tip.configure(text=f"配置加载失败\n{msg}")
        _show_actions(True)

    def _start(url, note="正在加载接口配置..."):
        state["url"] = url
        if not _loading_alive():
            return
        tip.configure(text=note)
        _show_actions(False)
        apiconfig.api_config.load(url, on_ok, on_err)

    def _retry():
        _start(state["url"], note="正在重新加载配置...")

    def _change_config():
        from tkinter import filedialog
        win = tk.Toplevel(app)
        win.title("更换接口配置")
        win.configure(bg="#000000")
        win.transient(app)
        win.grab_set()
        tk.Label(win, text="配置地址（支持 http / clan:// / 本地文件，"
                           "加密配置可带 ;pk;密钥）",
                 bg="#000000", fg="#BFBFBF", font=tv_font(10)
                 ).pack(padx=20, pady=(14, 4), anchor="w")
        row = tk.Frame(win, bg="#000000")
        row.pack(fill="x", padx=20)
        ent = tk.Entry(row, bg="#1C1C1C", fg="#FFFFFF", font=("Consolas", 11),
                       insertbackground="#FFFFFF", highlightthickness=1,
                       highlightbackground="#333", width=56)
        ent.insert(0, state["url"])
        ent.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def browse():
            p = filedialog.askopenfilename(
                parent=win, title="选择配置文件",
                filetypes=[("配置文件", "*.json *.txt"), ("所有文件", "*.*")])
            if p:
                ent.delete(0, "end")
                ent.insert(0, p)

        FocusLabel(row, text="浏览", bg="#1C1C1C", fg="#FFFFFF", font=tv_font(10),
                   on_select=browse, takefocus=1).pack(side="left")

        def confirm(_e=None):
            u = ent.get().strip()
            if not u:
                return
            state["save_default"] = True
            win.destroy()
            _start(u, note="正在加载新配置...")

        bar = tk.Frame(win, bg="#000000")
        bar.pack(fill="x", padx=20, pady=(14, 12))
        FocusLabel(bar, text="确定", bg="#FFB300", fg="#000000",
                   font=tv_font(11, True), on_select=confirm,
                   takefocus=1).pack(side="right")
        FocusLabel(bar, text="取消", bg="#1C1C1C", fg="#FFFFFF", font=tv_font(10),
                   on_select=win.destroy, takefocus=1).pack(side="right", padx=(0, 8))
        ent.bind("<Return>", confirm)
        win.bind("<Escape>", lambda e: win.destroy())
        # Toplevel 默认位置可能落到屏幕外（主窗被移到别处时），显式居中
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x = app.winfo_rootx() + (app.winfo_width() - w) // 2
        y = app.winfo_rooty() + (app.winfo_height() - h) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        ent.focus_set()

    _start(cfg_url)
    app.mainloop()


if __name__ == "__main__":
    main()
