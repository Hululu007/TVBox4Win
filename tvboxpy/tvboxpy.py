"""tvboxpy — TVBox 复刻（Python 版）

功能：加载 TVBox 接口配置 → 站点 → 分类 → 影片 → 剧集 → libmpv 播放，支持搜索。
用法：python tvboxpy.py [配置URL或本地json路径]
默认接口可用环境变量 TVBOX_CFG 覆盖。
"""
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import requests

# libmpv-2.dll 位置（与脚本同目录的 third_party/mpv，或 PyInstaller 解包目录）
_DLL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "third_party", "mpv")
os.environ["PATH"] = _DLL_DIR + os.pathsep + os.environ.get("PATH", "")
if getattr(sys, "_MEIPASS", None):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ["PATH"]

import mpv  # noqa: E402

DEFAULT_CFG_URL = "https://dxawi.github.io/0/0.json"
UA = {"User-Agent": "okhttp/4.9.3"}
SESSION = requests.Session()
SESSION.headers.update(UA)


def fetch(url: str) -> str | None:
    try:
        r = SESSION.get(url, timeout=10, verify=False)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
    except requests.RequestException:
        pass
    return None


# ---------------- TVBox config / catalog model ----------------

class Site:
    def __init__(self, name: str, api: str, stype: int):
        self.name, self.api, self.type = name, api, stype

    def url(self, query: str) -> str:
        return f"{self.api}?{query}"


def load_sites(cfg_source: str) -> list[Site]:
    text = None
    if os.path.isfile(cfg_source):
        text = open(cfg_source, encoding="utf-8", errors="ignore").read()
    else:
        text = fetch(cfg_source)
        if text and os.path.basename(cfg_source):
            try:
                with open("tvbox.json", "w", encoding="utf-8") as f:
                    f.write(text)
            except OSError:
                pass
    if not text:
        return []
    # 配置可能不是纯 JSON（含注释/前缀），容错截取
    try:
        cfg = json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s < 0 or e <= s:
            return []
        try:
            cfg = json.loads(text[s:e + 1])
        except json.JSONDecodeError:
            return []
    sites = []
    for it in cfg.get("sites", []):
        try:
            stype = int(it.get("type", -1))
        except (TypeError, ValueError):
            continue
        if stype not in (0, 1):
            continue  # spider(3) 等不支持
        if it.get("active") is False:
            continue
        sites.append(Site(str(it.get("name", "")), str(it.get("api", "")), stype))
    return sites


def parse_classes(data: dict) -> list[tuple[str, str]]:
    return [(str(c.get("type_id", "")), str(c.get("type_name", "")))
            for c in data.get("class", [])]


def parse_vods(data: dict) -> list[tuple[str, str]]:
    return [(str(v.get("vod_id", "")), str(v.get("vod_name", "")))
            for v in data.get("list", [])]


def parse_detail(data: dict) -> list[tuple[str, str]]:
    """返回 [(剧集名, 播放URL)]，取第一个播放源分组。"""
    lst = data.get("list") or []
    if not lst:
        return []
    play_url = lst[0].get("vod_play_url", "")
    group = play_url.split("$$$")[0]
    if "$" in group:
        group = group.split("$", 1)[1]
    eps = []
    for ep in group.split("#"):
        if "$" in ep:
            name, url = ep.split("$", 1)
            if url:
                eps.append((name, url))
    return eps


def try_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if 0 <= s < e:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                return None
    return None


# ---------------- UI ----------------

class App(tk.Tk):
    def __init__(self, cfg_source: str):
        super().__init__()
        self.title("TVBox Python 版")
        self.geometry("1100x680")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.player = None
        self.sites: list[Site] = []
        self.classes: list[tuple[str, str]] = []
        self.vods: list[tuple[str, str]] = []
        self.episodes: list[tuple[str, str]] = []
        self.cur_site = None
        self.stack: list[str] = []  # 导航状态: sites/classes/videos/episodes

        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        ttk.Button(top, text="返回", command=self.go_back).pack(side="left")
        self.kw = tk.StringVar()
        ttk.Entry(top, textvariable=self.kw, width=28).pack(side="left", padx=6)
        ttk.Button(top, text="搜索", command=self.do_search).pack(side="left")
        ttk.Button(top, text="停止播放", command=self.stop).pack(side="left", padx=6)
        self.status = tk.StringVar(value="加载配置...")
        ttk.Label(top, textvariable=self.status).pack(side="left", padx=10)

        body = ttk.Frame(self); body.pack(fill="both", expand=True)
        self.lb_sites = self._listbox(body, side="left", lb_width=26)
        self.lb_main = self._listbox(body, side="left", fill="both", expand=True)
        self.video = tk.Frame(body, background="black")
        self.video.pack_forget()

        self.lb_sites.bind("<Double-Button-1>", self.on_site)
        self.lb_main.bind("<Double-Button-1>", self.on_main)
        self.bind("<Escape>", lambda e: self.go_back())

        threading.Thread(target=self._load_sites, args=(cfg_source,), daemon=True).start()

    def _listbox(self, parent, lb_width=None, **pack_kw):
        f = ttk.Frame(parent)
        lb = tk.Listbox(f, font=("Microsoft YaHei UI", 11),
                        width=lb_width if lb_width else 30)
        sb = ttk.Scrollbar(f, command=lb.yview)
        lb.config(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        f.pack(**pack_kw, padx=2, pady=2)
        return lb

    def _fill(self, lb, items):
        lb.delete(0, "end")
        for name, _ in items:
            lb.insert("end", name)

    def _set_status(self, s):
        self.status.set(s)

    # ---- config loading ----
    def _load_sites(self, src):
        self.sites = load_sites(src)
        if not self.sites:
            self.after(0, lambda: self._set_status("配置加载失败（检查网络或 tvbox.json）"))
            return
        items = [(s.name, "") for s in self.sites]
        self.after(0, lambda: (self._fill(self.lb_sites, items),
                               self._set_status(f"已加载 {len(self.sites)} 个源，双击选择")))

    # ---- navigation ----
    def on_site(self, _e):
        sel = self.lb_sites.curselection()
        if not sel:
            return
        self.cur_site = self.sites[sel[0]]
        self.stack = ["classes"]
        self._fill(self.lb_main, [])
        self._set_status("加载分类...")
        threading.Thread(target=self._load_classes, daemon=True).start()

    def _load_classes(self):
        data = try_json(fetch(self.cur_site.url("ac=class")))
        if not data:
            self.after(0, lambda: self._set_status("分类加载失败"))
            return
        self.classes = parse_classes(data)
        items = [(n, i) for i, n in self.classes]
        self.after(0, lambda: (self._fill(self.lb_main, items),
                               self._set_status("双击分类")))

    def _open_videos(self, query):
        data = try_json(fetch(self.cur_site.url(query)))
        if not data:
            self.after(0, lambda: self._set_status("无结果"))
            return
        self.vods = parse_vods(data)
        items = [(n, i) for i, n in self.vods]
        self.after(0, lambda: (self._fill(self.lb_main, items),
                               self._set_status("双击影片查看剧集")))

    def on_main(self, _e):
        sel = self.lb_main.curselection()
        if not sel:
            return
        idx = sel[0]
        state = self.stack[-1]
        if state == "classes":
            cid, _ = self.classes[idx]
            self.stack.append("videos")
            self._fill(self.lb_main, [])
            self._set_status("加载列表...")
            threading.Thread(target=self._open_videos,
                             args=(f"ac=detail&t={cid}",), daemon=True).start()
        elif state == "videos":
            vid, _ = self.vods[idx]
            self.stack.append("episodes")
            self._fill(self.lb_main, [])
            self._set_status("加载详情...")
            threading.Thread(
                target=self._open_episodes,
                args=(f"ac=detail&ids={vid}",), daemon=True).start()
        elif state == "episodes":
            _, url = self.episodes[idx]
            self.play(url)

    def _open_episodes(self, query):
        data = try_json(fetch(self.cur_site.url(query)))
        eps = parse_detail(data) if data else []
        if not eps:
            self.after(0, lambda: self._set_status("无剧集"))
            self.stack.pop()
            return
        self.episodes = eps
        items = [(n, u) for n, u in eps]
        self.after(0, lambda: (self._fill(self.lb_main, items),
                               self._set_status("双击剧集播放")))

    def do_search(self):
        kw = self.kw.get().strip()
        if not kw or not self.cur_site:
            return
        self.stack = ["videos"]
        self._fill(self.lb_main, [])
        self._set_status(f"搜索 {kw} ...")
        threading.Thread(target=self._open_videos,
                         args=(f"ac=detail&wd={requests.utils.quote(kw)}",),
                         daemon=True).start()

    def go_back(self):
        if self.player and self.video.winfo_ismapped():
            self.stop()
            return
        if len(self.stack) > 1:
            self.stack.pop()
            prev = self.stack[-1]
            if prev == "classes":
                self._fill(self.lb_main, [(n, i) for i, n in self.classes])
            elif prev == "videos":
                self._fill(self.lb_main, [(n, i) for i, n in self.vods])
            self._set_status("已返回")
        elif self.stack:
            self.stack = []
            self._fill(self.lb_main, [])
            self._set_status("双击左侧站点选择源")

    # ---- playback ----
    def _ensure_player(self):
        if self.player:
            return
        self.player = mpv.MPV(wid=str(int(self.video.winfo_id())),
                              osc="yes", force_window="no")

    def play(self, url):
        try:
            self._ensure_player()
        except OSError as e:
            messagebox.showerror("播放错误", f"libmpv 加载失败：{e}")
            return
        self.lb_main.master.pack_forget()
        self.lb_sites.master.pack_forget()
        self.video.pack(fill="both", expand=True)
        self._set_status("正在播放 (Esc 返回列表)")
        self.player.command("loadfile", url)

    def stop(self):
        if self.player:
            self.player.command("stop")
        self.video.pack_forget()
        self.lb_sites.master.pack(fill="both", expand=True, padx=2, pady=2)
        self.lb_main.master.pack(fill="both", expand=True, padx=2, pady=2)
        self._set_status("已停止")

    def on_close(self):
        if self.player:
            self.player.terminate()
        self.destroy()


def main():
    requests.packages.urllib3.disable_warnings()
    cfg = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TVBOX_CFG", DEFAULT_CFG_URL)
    App(cfg).mainloop()


if __name__ == "__main__":
    main()
