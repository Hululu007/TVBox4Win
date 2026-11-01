"""播放页：Kivy Video（安卓上走系统 MediaPlayer，支持 m3u8 / mp4）。

与桌面版的差异：
- 桌面版用 libmpv 嵌入 tkinter 子窗口，安卓没有窗口嵌入的概念，直接用 Video 控件
- MediaPlayer 不支持自定义请求头，需要 Referer/UA 的源可能播不了（后续可接 mpv android）
"""
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.slider import Slider
from kivy.uix.video import Video

from tvboxosc import data_api

from . import theme
from .app import BaseScreen, toast
from .net import run
from .widgets import AutoLabel, FlatButton


class PlayScreen(BaseScreen):

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bean = None
        self.info = None
        self.flag = ""
        self.flag_index = 0
        self.ep_index = 0
        self._tick = None
        self._build()

    def _build(self):
        self.add_top_button("←", self._back, dp(40))
        self.add_top_title("播放", "")

        # 视频区垫深色底（桌面无解码器 / 加载中不至于白屏刺眼）
        from kivy.graphics import Color, Rectangle
        self.video_box = BoxLayout()
        with self.video_box.canvas.before:
            Color(*theme.BG)
            self._vrect = Rectangle(pos=self.video_box.pos,
                                    size=self.video_box.size)
        self.video_box.bind(pos=lambda w, p: setattr(self._vrect, "pos", p),
                            size=lambda w, s: setattr(self._vrect, "size", s))
        self.video = Video(state="stop", allow_stretch=True,
                           keep_ratio=True, size_hint_y=1)
        self.video_box.add_widget(self.video)
        self.root_box.add_widget(self.video_box)
        # 视频纹理就绪才显示控件：桌面预览无解码器、安卓加载中都不会白屏
        self.video.bind(texture=lambda _v, tex: setattr(
            self.video, "opacity", 1 if tex else 0))

        self.hint = AutoLabel(text="", color=theme.FG_DIM, font_size="11sp",
                              size_hint_y=None, height=dp(20),
                              halign="center")
        self.root_box.add_widget(self.hint)

        bar = BoxLayout(size_hint_y=None, height=dp(82), orientation="vertical",
                        padding=(dp(8), dp(4)), spacing=dp(2))
        self.slider = Slider(min=0, max=1, value=0)
        self.slider.bind(on_touch_up=self._seek)
        bar.add_widget(self.slider)

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.btn_play = FlatButton(text="暂停", bg=theme.BLUE)
        self.btn_play.bind(on_release=lambda *_: self._toggle())
        self.btn_prev = FlatButton(text="上一集")
        self.btn_prev.bind(on_release=lambda *_: self._step(-1))
        self.btn_next = FlatButton(text="下一集")
        self.btn_next.bind(on_release=lambda *_: self._step(1))
        for w in (self.btn_prev, self.btn_play, self.btn_next):
            row.add_widget(w)
        bar.add_widget(row)
        self.root_box.add_widget(bar)

    # ------------------------------------------------------------ 播放控制

    def open(self, bean, flag, ep_name, ep_url, info, flag_index, ep_index):
        self.bean = bean
        self.info = info
        self.flag = flag
        self.flag_index = flag_index
        self.ep_index = ep_index
        self.set_sub(ep_name or "")
        self.hint.text = "正在解析播放地址…"
        self.video.state = "stop"
        self.video.source = ""
        self.video.opacity = 0
        run(lambda: data_api.get_play_url(bean, flag, ep_url),
            self._start, lambda e: setattr(self.hint, "text", "解析失败：" + e))

    def _start(self, res):
        url, _headers = res
        if not url:
            self.hint.text = "没有拿到播放地址"
            return
        self.hint.text = ""
        self.video.source = url
        self.video.state = "play"
        self.btn_play.text = "暂停"
        self._start_tick()

    def _toggle(self):
        if self.video.state == "play":
            self.video.state = "pause"
            self.btn_play.text = "播放"
        else:
            self.video.state = "play"
            self.btn_play.text = "暂停"

    def _seek(self, _slider, touch):
        if touch.grab_current is not _slider:
            return
        if self.video.duration > 0:
            self.video.seek(self.slider.value * self.video.duration)

    def _start_tick(self):
        if self._tick is not None:
            return
        self._tick = Clock.schedule_interval(self._update_progress, 1.0)

    def _stop_tick(self):
        if self._tick is not None:
            self._tick.cancel()
            self._tick = None

    def _update_progress(self, _dt):
        dur = self.video.duration or 0
        if dur > 0:
            self.slider.max = dur
            self.slider.value = self.video.position
        if self.video.eos:
            self._step(1)          # 自动连播下一集

    def _episodes(self):
        """当前线路的 (剧集名, 地址) 列表"""
        if not self.info:
            return [], []
        flags = self.info.get("series_flags") or []
        urls = self.info.get("series_urls") or []
        names = flags[self.flag_index][1] if self.flag_index < len(flags) else []
        links = urls[self.flag_index] if self.flag_index < len(urls) else []
        return names, links

    def _step(self, delta):
        names, links = self._episodes()
        idx = self.ep_index + delta
        if idx < 0:
            toast("已经是第一集")
            return
        if idx >= len(names):
            toast("已经是最后一集")
            return
        self.ep_index = idx
        self.open(self.bean, self.flag, names[idx],
                  links[idx] if idx < len(links) else "",
                  self.info, self.flag_index, idx)

    def stop(self):
        self._stop_tick()
        try:
            self.video.state = "stop"
            self.video.source = ""
            self.video.opacity = 0
        except Exception:
            pass
        self.hint.text = ""

    def _back(self):
        self.stop()
        self.manager.current = "detail"
