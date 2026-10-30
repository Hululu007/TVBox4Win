"""推送页 PushActivity 复刻：本地 HTTP 服务接收推送 + 播放

对应原版 RemoteServer(9978端口)：手机浏览器访问 http://TV的IP:9978
输入视频链接提交 → 电视端列表出现 → 选中播放
"""
import ipaddress
import json
import os
import socket
import threading
import tkinter as tk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from . import apiconfig, ui_thread
from .player import MpvPlayer
from .theme import BG, FG, FG_DIM, ACCENT, FocusLabel, tv_font, PANEL, POSTER_BG

PORT = 9978

# 全局常驻推送服务状态（对应 Java ControlManager.startServer 主页即启动）
PUSHED = []            # [(title, url)]
_SERVER = [None]
_UI_CB = [None]        # 推送页注册的刷新回调


def _notify_ui(msg):
    if _UI_CB[0]:
        ui_thread.run(lambda: _UI_CB[0](msg))


def start_global_server():
    """启动全局推送服务（只启动一次，页面开关不影响）"""
    if _SERVER[0] is not None:
        return
    import urllib.parse as _up

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, body, code=200):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _handle_push(self, url, title):
            if not url.startswith(("http", "rtmp", "rtp", "udp")):
                self._reply("<h2>链接无效</h2>".encode(), 400)
                return
            PUSHED.insert(0, (title, url))
            del PUSHED[20:]
            _notify_ui(f"收到推送：{title}")
            self._reply("<html><body style='text-align:center'>"
                        "<h2>推送成功！请在电视上查看</h2></body></html>".encode())

        def _handle_api(self, url):
            """远程换源（对应 Java onApiReceived）"""
            _notify_ui(f"收到远程配置：{url[:40]}")

            def ok():
                def apply():
                    from . import data_api, hawk
                    data_api.clear_caches()
                    first = apiconfig.api_config.source_key_list[0] \
                        if apiconfig.api_config.source_key_list else ""
                    hawk.put(hawk.HOME_SOURCE, first)
                    _notify_ui("远程换源成功")
                ui_thread.run(apply)
            apiconfig.api_config.load(url, ok_cb=ok)
            self._reply("<h2>配置已提交</h2>".encode())

        def _dispatch(self, params):
            url = unquote(params.get("url", [""])[0])
            title = unquote(params.get("title", ["手机推送"])[0])
            if params.get("do", [""])[0] == "api" or \
                    self.path.startswith("/api"):
                self._handle_api(url)
            else:
                self._handle_push(url, title)

        def do_GET(self):
            if self.path.startswith(("/push", "/api")):
                self._dispatch(parse_qs(urlparse(self.path).query))
            else:
                self._reply(_FORM)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
            ctype = self.headers.get("Content-Type", "")
            if "json" in ctype:  # 原版 App 的 JSON 协议 {"do":"push","url":..}
                try:
                    data = json.loads(raw)
                    params = {k: [str(v)] for k, v in data.items()}
                except (json.JSONDecodeError, AttributeError):
                    params = {}
            else:
                params = parse_qs(raw)
            if params.get("do", [""])[0] == "api" and \
                    not self.path.startswith("/push"):
                self._handle_api(params.get("url", [""])[0])
            else:
                self._dispatch(params)

        def log_message(self, *a):
            pass

    def run():
        try:
            _SERVER[0] = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
            _SERVER[0].serve_forever()
        except OSError:
            pass
    threading.Thread(target=run, daemon=True).start()


_FORM = ("<html><head><meta charset='utf-8'><title>TVBox 推送</title></head>"
         "<body style='text-align:center;max-width:480px;margin:40px auto;font-size:18px'>"
         "<h2>TVBox 推送</h2>"
         "<form action='/push' method='get'>"
         "<input name='title' placeholder='标题(可选)' style='width:100%;padding:8px;margin:6px 0'>"
         "<input name='url' placeholder='视频链接' required style='width:100%;padding:8px;margin:6px 0'>"
         "<button style='width:100%;padding:10px'>推送到电视</button>"
         "</form>"
         "<form action='/api' method='get' style='margin-top:24px'>"
         "<input name='url' placeholder='接口配置地址(远程换源)' required style='width:100%;padding:8px;margin:6px 0'>"
         "<button style='width:100%;padding:10px'>切换电视上的配置</button>"
         "</form></body></html>").encode()


def _local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if "." in ip and not ip.startswith("127."):
                try:
                    ipaddress.IPv4Address(ip)
                    ips.add(ip)
                except ValueError:
                    pass
    except OSError:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("223.5.5.5", 80))
            ips.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    return sorted(ips)


class Page(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.player = None
        start_global_server()  # 服务全局常驻，进页面只是注册刷新回调
        self._register()

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x")
        FocusLabel(bar, text="← 返回", font=tv_font(12, True),
                   on_select=self._back).pack(side="left", padx=12, pady=6)
        tk.Label(bar, text="推送", bg=BG, fg=FG, font=tv_font(16, True)
                 ).pack(side="left", padx=10)

        ips = _local_ips()
        tip = "\n".join(f"http://{ip}:{PORT}" for ip in ips) or "未获取到局域网 IP"
        tk.Label(self, text=f"手机浏览器打开：\n{tip}\n提交视频链接后，在下方列表选中播放",
                 bg=BG, fg=FG_DIM, font=tv_font(12), justify="center").pack(pady=8)

        self.status = tk.Label(self, text="等待推送...", bg=BG, fg=ACCENT,
                               font=tv_font(11))
        self.status.pack()

        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True)
        self._show_list()

        sample = os.path.join(os.path.dirname(__file__), "assets", "sample.wav")
        if os.path.isfile(sample):
            FocusLabel(self, text="▶ 播放内置示例（测试播放器/声音）",
                       bg=POSTER_BG, fg=ACCENT, font=tv_font(12),
                       on_select=lambda: self._play(sample, "内置示例")
                       ).pack(pady=6)

    @property
    def pushed(self):
        """兼容：推送列表已提升为模块级 PUSHED（全局常驻服务共用）"""
        return PUSHED

    # ---------- 推送列表 ----------
    def _register(self):
        """注册全局服务回调：推送到达时刷新列表（离开页面自动注销）"""
        def on_msg(msg):
            if self.winfo_exists():
                self.status.configure(text=msg)
                self._show_list()
        self._cb = on_msg
        _UI_CB[0] = on_msg

    def _show_list(self):
        for w in self.body.winfo_children():
            w.destroy()
        if not PUSHED:
            tk.Label(self.body, text="暂无推送内容", bg=BG, fg=FG_DIM,
                     font=tv_font(13)).pack(expand=True)
            return
        btns = []
        for i, (title, url) in enumerate(PUSHED):
            b = FocusLabel(self.body, text=f"▶ {title[:40]}", bg=PANEL, fg=FG,
                           font=tv_font(12), padx=16, pady=8,
                           on_select=lambda u=url, t=title: self._play(u, t))
            b.pack(fill="x", padx=40, pady=4)
            btns.append(b)
        if btns:
            btns[0].focus_set()

    # ---------- 播放 ----------
    def _play(self, url, title):
        for w in self.body.winfo_children():
            w.destroy()
        video = tk.Frame(self.body, bg="#000000", highlightthickness=0)
        video.pack(fill="both", expand=True)
        bar = tk.Frame(self.body, bg="#000000")
        bar.pack(fill="x")
        FocusLabel(bar, text="← 返回列表", font=tv_font(12, True),
                   on_select=self._stop_and_list).pack(side="left", padx=12, pady=6)
        tk.Label(bar, text=title[:40], bg="#000000", fg=FG,
                 font=tv_font(13, True)).pack(side="left", padx=10)
        self.status.configure(text=f"正在播放 {title[:30]}")
        # 每次 _play 都新建 video 容器，旧 mpv 的嵌入窗口已随旧容器销毁，
        # 必须重建播放器实例，否则画面黑屏且无进度
        if self.player:
            self.player.terminate()
            self.player = None
        self.update_idletasks()
        self.player = MpvPlayer(int(video.winfo_id()))
        self.player.play(url)

    def _stop_and_list(self):
        if self.player:
            self.player.terminate()
            self.player = None
        self._show_list()

    def _back(self):
        if self.player:
            self.player.terminate()
            self.player = None
        self.app.go_home()

    def destroy(self):
        if getattr(self, "_cb", None) is not None and _UI_CB[0] is self._cb:
            _UI_CB[0] = None
        if self.player:
            self.player.terminate()
            self.player = None
        super().destroy()
