"""tvboxosc 主入口（对应 App.java 启动流程：初始化 ApiConfig → HomeActivity）"""
import sys
import tkinter as tk

from tvboxosc import hawk, apiconfig, ui_thread
from tvboxosc.app import App
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


def _pick_default_site():
    """选默认站点：优先 CMS(type 0/1/2)，其次爬虫源"""
    keys = apiconfig.api_config.source_key_list
    if not keys:
        return ""
    usable = []
    for k in keys:
        b = apiconfig.api_config.get(k)
        if b is not None:
            usable.append(b)
    for b in usable:
        if b.type in (0, 1, 2):
            return b.key
    return usable[0].key if usable else keys[0]


def main():
    if "--check" in sys.argv:
        self_check()
    # 老用户迁移：仍指向旧默认源的直接切到新默认源
    if hawk.get(hawk.DEFAULT_API, "http://xhztv.top/4k.json") == "http://xhztv.top/4k.json":
        hawk.put(hawk.DEFAULT_API, DEFAULT_CONFIG)
    if hawk.get(hawk.HOME_API, "") in ("", "http://xhztv.top/4k.json"):
        hawk.put(hawk.HOME_API, DEFAULT_CONFIG)
    cfg_url = sys.argv[1] if len(sys.argv) > 1 else \
        hawk.get(hawk.DEFAULT_API, DEFAULT_CONFIG)

    app = App()

    loading = tk.Label(app.container, text="TVBox\n正在加载接口配置...",
                       bg="#000000", fg="#FFFFFF", font=("Microsoft YaHei UI", 18))
    loading.pack(fill="both", expand=True)

    def on_ok():
        # 直接进界面，绝不做站点探测（探测太慢，用户等着急）
        # 没有默认源就用第一个站点，失效了用户可用「切换源」自行换
        key = hawk.get(hawk.HOME_SOURCE)
        if not key or apiconfig.api_config.get(key) is None:
            # 当前源不存在 → 自动换可用站点
            key = _pick_default_site()
            hawk.put(hawk.HOME_SOURCE, key)
        loading.destroy()
        if hawk.get("home_page", "vod") == "live":
            # 设置页「下次进入」选了直播：启动直达直播页
            from tvboxosc.ui_live import Page as LivePage
            app.switch(LivePage)
        else:
            # 对应原版 HomeActivity 默认 tab：启动直达点播首页（GridFragment）
            from tvboxosc.ui_grid import Page as GridPage
            app.switch(GridPage)

    def on_err(msg):
        ui_thread.run(lambda: loading.configure(
            text=f"配置加载失败：{msg}\n请检查网络后重启"))

    apiconfig.api_config.load(cfg_url, on_ok, on_err)
    app.mainloop()


if __name__ == "__main__":
    main()
