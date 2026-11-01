"""设置页 SettingActivity 复刻（布局对照原版截图：网格卡片，每项
「标签 + 当前值 ›」，2 列排布，方向键移动焦点）

卡片项：配置地址 / 配置历史 / 首页站源 / 首页推荐 / 下次进入 / 清空缓存 / 关于
"""
import os
import shutil
import threading
import tkinter as tk
from tkinter import filedialog

from . import hawk, ui_thread, VERSION
from .apiconfig import api_config
from .theme import (BG, FG, FG_DIM, ACCENT, FOCUS_BG, FOCUS_FG,
                    FocusLabel, tv_font, PANEL, PANEL_HI)

DEFAULT_API = "https://cyao2q.github.io/files/m.json"

# 首页推荐（对应 HawkConfig.HOME_REC：0 豆瓣热播 / 1 站点推荐 / 2 观看历史）
HOME_REC_NAMES = {0: "豆瓣热播", 1: "站点推荐", 2: "观看历史"}
# 解码方式（对应 IJK_CODEC：硬解码 / 软解码，映射 mpv hwdec auto/no）
CODEC_NAMES = ("硬解码", "软解码")
# 画面缩放（对应 PLAY_SCALE / PlayerHelper.getScaleName）
SCALE_NAMES = {0: "默认", 1: "16:9", 2: "4:3", 3: "填充", 4: "裁剪", 5: "原始"}
# 字幕字号（0=跟随视频，其余为像素）
SUB_FONT_NAMES = {0: "跟随视频", 28: "小", 36: "中", 42: "大", 48: "特大"}
# 历史记录上限（对应 HISTORY_NUM / HistoryHelper.hisNumArray）
HIS_NUM_ARRAY = (30, 50, 100)


class Page(tk.Frame):
    """对应 ui/activity/SettingActivity.java"""

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self._vars = {}

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x")
        FocusLabel(bar, text="← 返回", font=tv_font(12, True),
                   on_select=lambda: self._back()).pack(side="left", padx=12, pady=6)
        tk.Label(bar, text="设置", bg=BG, fg=FG, font=tv_font(16, True)
                 ).pack(side="left", padx=10)

        self.status = tk.Label(self, text="", bg=BG, fg=FG_DIM, font=tv_font(11))
        self.status.pack(side="bottom", fill="x", padx=24, pady=4)

        # 网格卡片（截图同款：2 列，方向键导航）；卡片变多后需要滚动
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
        grid = tk.Frame(canvas, bg=BG)
        grid.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        self._win = canvas.create_window((0, 0), window=grid, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(
            self._win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._canvas = canvas
        self._scroll_inner = grid

        def _wheel(e):
            try:
                canvas.yview_scroll(-e.delta // 120, "units")
            except tk.TclError:
                pass
        canvas.bind_all("<MouseWheel>", _wheel)
        for c in range(2):
            grid.grid_columnconfigure(c, weight=1)

        self._cards = []
        self._row, self._col = 0, 0
        self._add_card(grid, "配置地址", full=True, cb=self._edit_api)
        self._add_card(grid, "直播地址", full=True, cb=self._edit_live)
        self._add_card(grid, "配置历史", full=True, cb=self._pick_hist)
        self._add_card(grid, "数据备份", full=True, cb=self._backup_data)
        self._add_card(grid, "数据恢复", full=True, cb=self._restore_data)
        self._add_card(grid, "首页站源", cb=self._goto_grid)
        self._add_card(grid, "首页推荐", cb=self._pick_home_rec)
        self._add_card(grid, "解码方式", cb=self._pick_codec)
        self._add_card(grid, "画面缩放", cb=self._pick_scale)
        self._add_card(grid, "历史上限", cb=self._pick_his_num)
        self._add_card(grid, "下次进入", cb=self._toggle_home_page)
        self._add_card(grid, "默认倍速", cb=self._pick_speed)
        self._add_card(grid, "字幕字号", cb=self._pick_sub_size)
        self._add_card(grid, "弹幕源", cb=self._edit_danmaku_api)
        self._add_card(grid, "直播加密分组", cb=self._clear_live_groups)
        self._add_card(grid, "快速搜索", cb=lambda: self._toggle_flag(
            "快速搜索", hawk.FAST_SEARCH, True))
        self._add_card(grid, "自动换线", cb=lambda: self._toggle_flag(
            "自动换线", hawk.AUTO_SWITCH_LINE, True))
        self._add_card(grid, "自动播放", cb=lambda: self._toggle_flag(
            "自动播放", hawk.AUTO_PLAY, False))
        self._add_card(grid, "弹幕", cb=lambda: self._toggle_flag(
            "弹幕", hawk.DANMAKU_ENABLE, False))
        self._add_card(grid, "记住倍速", cb=lambda: self._toggle_flag(
            "记住倍速", hawk.SPEED_MEMORY, False))
        self._add_card(grid, "防休眠", cb=lambda: self._toggle_flag(
            "防休眠", hawk.KEEP_AWAKE, False))
        self._add_card(grid, "播放缓存", cb=lambda: self._toggle_flag(
            "播放缓存", hawk.PLAYER_CACHE, False))
        self._add_card(grid, "历史合并", cb=lambda: self._toggle_flag(
            "历史合并", hawk.HISTORY_MERGE, False))
        self._add_card(grid, "直播倒序", cb=lambda: self._toggle_flag(
            "直播倒序", hawk.LIVE_REVERSE, False))
        self._add_card(grid, "首页壁纸", cb=lambda: self._toggle_flag(
            "首页壁纸", hawk.WALLPAPER, False))
        self._add_card(grid, "壁纸图片", cb=self._pick_wallpaper)
        self._add_card(grid, "开发者模式", cb=lambda: self._toggle_flag(
            "开发者模式", hawk.DEVELOPER_MODE, False))
        self._add_card(grid, "查看日志", cb=self._open_log)
        self._add_card(grid, "打开数据目录", cb=self._open_data_dir)
        self._add_card(grid, "清空缓存", cb=self._clear_cache)
        self._add_card(grid, "关于", cb=self._show_about)
        self._refresh_values()
        if self._cards:
            self._cards[0].focus_set()
        # 方向键导航（2 列）
        from .theme import grid_key_nav
        grid_key_nav(self._cards, 2, up_down_rows=1)

    def _back(self):
        from .ui_grid import Page as GridPage
        self.app.go_back(GridPage)

    # ------------------------------------------------ 卡片构建 ----
    def _add_card(self, grid, name, full=False, cb=None):
        var = tk.StringVar(value=name)
        if full:
            if self._col:  # 半宽行未满时先换行，通栏独占一行
                self._row, self._col = self._row + 1, 0
            card = FocusLabel(grid, textvariable=var, bg=PANEL, fg=FG,
                              font=tv_font(13, True), padx=18, pady=14,
                              anchor="w", on_select=cb)
            card.grid(row=self._row, column=0, columnspan=2,
                      sticky="ew", padx=24, pady=5)
            self._row += 1
        else:
            card = FocusLabel(grid, textvariable=var, bg=PANEL, fg=FG,
                              font=tv_font(13, True), padx=18, pady=14,
                              anchor="w", on_select=cb)
            card.grid(row=self._row, column=self._col, sticky="ew",
                      padx=(24, 8) if self._col == 0 else (8, 24), pady=5)
            self._col += 1
            if self._col == 2:
                self._row, self._col = self._row + 1, 0
        card._var, card._name = var, name
        try:  # 键盘移动焦点时自动滚动到可见区域
            card.bind("<FocusIn>", lambda e, c=card: self._ensure_visible(c),
                      add="+")
        except tk.TclError:
            pass
        self._cards.append(card)
        self._vars[name] = var
        return card

    def _ensure_visible(self, card):
        try:
            y = card.winfo_y()
            total = self._scroll_inner.winfo_height() or 1
            view_h = self._canvas.winfo_height() or 1
            first = self._canvas.canvasy(0)
            if y < first or y + card.winfo_height() > first + view_h:
                self._canvas.yview_moveto(max(0.0, (y - 12) / total))
        except (tk.TclError, AttributeError):
            pass

    def _set_value(self, name, value):
        if name in self._vars:
            self._vars[name].set(f"{name}　　{value}　›" if value else f"{name}　　›")

    def _refresh_values(self):
        api = hawk.get(hawk.HOME_API, DEFAULT_API)
        self._set_value("配置地址", self._short(api))
        live = str(hawk.get(hawk.LIVE_API_URL, "") or "")
        self._set_value("直播地址", self._short(live) if live else "跟随配置")
        hist = hawk.get(hawk.API_HISTORY, []) or []
        self._set_value("配置历史", f"{len(hist)} 条" if hist else "")
        self._set_value("首页站源", self._home_source_name())
        self._set_value("首页推荐", HOME_REC_NAMES.get(self._home_rec(),
                                                       HOME_REC_NAMES[1]))
        try:
            scale = int(hawk.get(hawk.PLAY_SCALE, 0))
        except (TypeError, ValueError):
            scale = 0
        self._set_value("画面缩放", SCALE_NAMES.get(scale, "默认"))
        self._set_value("解码方式",
                        "软解码" if hawk.get(hawk.IJK_CODEC, "硬解码") == "软解码"
                        else "硬解码")
        try:
            hn = int(hawk.get(hawk.HISTORY_NUM, 0))
        except (TypeError, ValueError):
            hn = 0
        self._set_value("历史上限",
                        f"{HIS_NUM_ARRAY[hn]} 条" if 0 <= hn < 3 else "30 条")
        self._set_value("下次进入", "直播" if self._home_page() == "live" else "点播")
        try:
            sp = float(hawk.get(hawk.PLAY_SPEED, 1.0) or 1.0)
        except (TypeError, ValueError):
            sp = 1.0
        self._set_value("默认倍速", f"{sp:g}x")
        try:
            fs = int(hawk.get(hawk.SUB_FONT_SIZE, 0) or 0)
        except (TypeError, ValueError):
            fs = 0
        self._set_value("字幕字号", SUB_FONT_NAMES.get(fs, f"{fs}px"))
        dm_api = str(hawk.get(hawk.DANMAKU_API, "") or "")
        self._set_value("弹幕源", self._short(dm_api) if dm_api else "未设置")
        groups = hawk.get(hawk.LIVE_PASSWORD_GROUPS, []) or []
        self._set_value("直播加密分组", f"已解锁 {len(groups)} 组" if groups else "")
        self._set_value("快速搜索", self._on_off(hawk.get(hawk.FAST_SEARCH, True)))
        self._set_value("自动换线", self._on_off(hawk.get(hawk.AUTO_SWITCH_LINE, True)))
        self._set_value("自动播放", self._on_off(hawk.get(hawk.AUTO_PLAY, False)))
        self._set_value("弹幕", self._on_off(hawk.get(hawk.DANMAKU_ENABLE, False)))
        self._set_value("记住倍速", self._on_off(hawk.get(hawk.SPEED_MEMORY, False)))
        self._set_value("防休眠", self._on_off(hawk.get(hawk.KEEP_AWAKE, False)))
        self._set_value("播放缓存", self._on_off(hawk.get(hawk.PLAYER_CACHE, False)))
        self._set_value("历史合并", self._on_off(hawk.get(hawk.HISTORY_MERGE, False)))
        self._set_value("直播倒序", self._on_off(hawk.get(hawk.LIVE_REVERSE, False)))
        self._set_value("首页壁纸", self._on_off(hawk.get(hawk.WALLPAPER, False)))
        wp = str(hawk.get(hawk.WALLPAPER_OVERRIDE, "") or "")
        self._set_value("壁纸图片",
                        self._short(os.path.basename(wp), 24) if wp else "默认渐变")
        self._set_value("开发者模式", self._on_off(hawk.get(hawk.DEVELOPER_MODE, False)))
        self._set_value("关于", f"v{VERSION}")

    @staticmethod
    def _on_off(value):
        return "开" if value else "关"

    @staticmethod
    def _short(url, n=44):
        return url if len(url) <= n else url[:n] + "…"

    def _alive(self):
        """页面是否还活着（异步回调回来时用户可能已经切走，控件已销毁）"""
        try:
            return bool(self.winfo_exists()) and bool(self.status.winfo_exists())
        except Exception:
            return False

    def _set_status(self, text):
        """带存活检查的状态栏写入，避免 TclError: invalid command name"""
        if self._alive():
            self.status.configure(text=text)

    @staticmethod
    def _home_source_name():
        key = hawk.get(hawk.HOME_SOURCE)
        bean = api_config.get(key) if key else None
        return bean.name if bean else ""

    @staticmethod
    def _home_page():
        return hawk.get("home_page", "vod") or "vod"

    @staticmethod
    def _home_rec():
        """首页推荐类型：0 豆瓣热播 / 1 站点推荐 / 2 观看历史"""
        try:
            return int(hawk.get(hawk.HOME_REC, hawk.DEFAULT_HOME_REC))
        except (TypeError, ValueError):
            return hawk.DEFAULT_HOME_REC

    # ------------------------------------------------ 功能动作 ----
    def _edit_api(self, focus_live=False):
        """配置地址弹窗（对应原版 ApiDialog：点播 + 直播 两行输入 + 直播历史）"""
        api = hawk.get(hawk.HOME_API, DEFAULT_API)
        live = str(hawk.get(hawk.LIVE_API_URL, "") or "")
        self._api_dialog(api, live, self._load_api, focus_live=focus_live)

    def _edit_live(self):
        self._edit_api(focus_live=True)

    def _save_live(self, url):
        """保存自定义直播源（对应 HawkConfig.LIVE_API_URL + LIVE_API_HISTORY）"""
        url = (url or "").strip()
        if not url:
            hawk.delete(hawk.LIVE_API_URL)
            self._refresh_values()
            self._set_status("直播地址已清空：直播页将使用接口配置里的直播源")
            return
        hist = [u for u in (hawk.get(hawk.LIVE_API_HISTORY, []) or []) if u != url]
        hist.insert(0, url)
        hawk.put(hawk.LIVE_API_HISTORY, hist[:10])
        hawk.put(hawk.LIVE_API_URL, url)
        self._refresh_values()
        self._set_status(f"直播地址已保存：{url}（正在校验…）")

        # 后台校验能不能解析出频道（不阻塞 UI）
        def check():
            from .ui_live import read_live_source, parse_live_source
            try:
                name, chs = parse_live_source(read_live_source(url), url)
            except Exception as e:
                msg = f"直播地址已保存，但读取失败：{e}"
                ui_thread.run(lambda: self._set_status(msg))
                return
            if chs:
                msg = f"直播地址已保存：{name or '直播源'} · {len(chs)} 个频道"
            else:
                msg = "直播地址已保存，但未解析到频道（可检查地址或格式）"
            ui_thread.run(lambda: self._set_status(msg))
        threading.Thread(target=check, daemon=True).start()

    def _pick_live_hist(self):
        urls = hawk.get(hawk.LIVE_API_HISTORY, []) or []
        if not urls:
            self._set_status("暂无直播历史")
            return
        self._list_dialog("历史直播", urls, self._save_live)

    def _api_dialog(self, api, live, on_point_ok, focus_live=False):
        """双输入弹窗：点播地址 + 直播地址（布局对照 dialog_api.xml）"""
        win = tk.Toplevel(self)
        win.title("配置地址")
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()

        tk.Label(win, text="配置地址", bg=BG, fg=FG, font=tv_font(14, True)
                 ).pack(padx=20, pady=(14, 2), anchor="w")
        tk.Label(win, text="点播：TVBox 接口配置地址　　直播：txt/m3u 直播源或含 lives 的配置"
                           "（留空则跟随接口配置）",
                 bg=BG, fg=FG_DIM, font=tv_font(10)).pack(padx=20, anchor="w")

        def add_row(label, value):
            fr = tk.Frame(win, bg=BG)
            fr.pack(fill="x", padx=20, pady=5)
            tk.Label(fr, text=label, bg=BG, fg=FG, font=tv_font(11, True),
                     width=4, anchor="w").pack(side="left")
            ent = tk.Entry(fr, bg=PANEL, fg=FG, font=("Consolas", 11, ), width=64,
                           insertbackground=FG, highlightthickness=1,
                           highlightbackground="#333")
            ent.insert(0, value)
            ent.pack(side="left", fill="x", expand=True, padx=(4, 6))

            def browse():
                p = filedialog.askopenfilename(
                    parent=win, title=f"选择{label}文件",
                    filetypes=[("直播/配置文件", "*.txt *.m3u *.m3u8 *.json"),
                               ("所有文件", "*.*")])
                if p:
                    ent.delete(0, "end")
                    ent.insert(0, p)
            FocusLabel(fr, text="选择", bg=PANEL_HI, fg=FG, font=tv_font(10),
                       on_select=browse).pack(side="left")
            return ent

        ent_api = add_row("点播", api)
        ent_live = add_row("直播", live)

        def confirm(_e=None):
            a = ent_api.get().strip()
            l = ent_live.get().strip()
            win.destroy()
            self._save_live(l)          # 先存直播源（不动页面）
            if a:
                on_point_ok(a)          # 再加载点播配置（成功后回主页）
            elif not l:
                self._set_status("点播与直播地址均为空，未做改动")

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=20, pady=(10, 0))
        FocusLabel(bar, text="直播历史", bg=PANEL_HI, fg=FG, font=tv_font(10),
                   on_select=lambda: (win.destroy(), self._pick_live_hist())
                   ).pack(side="left")
        FocusLabel(bar, text="确定", bg=FOCUS_BG, fg=FOCUS_FG, font=tv_font(11, True),
                   on_select=confirm).pack(side="right")
        FocusLabel(bar, text="取消", bg=PANEL_HI, fg=FG, font=tv_font(10),
                   on_select=win.destroy).pack(side="right", padx=(0, 8))

        for ent in (ent_api, ent_live):
            ent.bind("<Return>", confirm)
        win.bind("<Escape>", lambda e: win.destroy())
        (ent_live if focus_live else ent_api).focus_set()

    def _load_api(self, url):
        url = (url or "").strip()
        if not url:
            self._set_status("请输入接口地址")
            return
        self._set_status(f"正在加载 {url} ...")

        def ok():
            def apply():
                from . import data_api
                data_api.clear_caches()
                hawk.delete(hawk.HOME_SOURCE)
                first = api_config.source_key_list[0] if api_config.source_key_list else ""
                hawk.put(hawk.HOME_SOURCE, first)
                if self._alive():
                    self._set_status("配置加载成功，正在返回主页…")
                    self._refresh_values()
                    self.app.go_home()
            ui_thread.run(apply)

        def err(msg):
            # 失败必须让用户看到，否则弹窗一关就像「点了没反应」
            ui_thread.run(lambda: self._set_status(f"配置加载失败：{msg}"))
        api_config.load(url, ok_cb=ok, err_cb=err)

    def _pick_hist(self):
        urls = hawk.get(hawk.API_HISTORY, []) or []
        if not urls:
            self._set_status("暂无配置历史")
            return
        self._list_dialog("配置历史", urls, self._load_api)

    def _goto_grid(self):
        # 首页站源在主页「切换源」里管理，此处快捷进入点播页
        from .ui_grid import Page as GridPage
        self.app.switch(GridPage)

    def _pick_home_rec(self):
        """首页推荐选择（对应 ModelSettingFragment llHomeRec → SelectDialog）"""
        cur = self._home_rec()
        self._select_dialog("请选择首页列表数据",
                            [(v, HOME_REC_NAMES[v]) for v in (0, 1, 2)],
                            cur, self._apply_home_rec)

    def _apply_home_rec(self, value):
        hawk.put(hawk.HOME_REC, value)
        self._refresh_values()
        self._set_status(f"首页推荐已切换为「{HOME_REC_NAMES[value]}」，"
                                   f"返回主页即可看到效果")
        # 立刻回主页让用户看到效果（对应原版 Hawk 改动后首页重刷）
        self.after(260, self.app.go_home)

    def _pick_codec(self):
        """解码方式（对应 llMediaCodec → IJK_CODEC，映射 mpv hwdec）"""
        cur = 0 if hawk.get(hawk.IJK_CODEC, "硬解码") != "软解码" else 1
        self._select_dialog("请选择解码方式",
                            list(enumerate(CODEC_NAMES)),
                            cur, self._apply_codec)

    def _apply_codec(self, value):
        hawk.put(hawk.IJK_CODEC, CODEC_NAMES[value])
        self._refresh_values()
        self._set_status(f"解码方式已切换为「{CODEC_NAMES[value]}」，"
                                   f"下次播放生效")

    def _pick_scale(self):
        """画面缩放（对应 llScale → PLAY_SCALE）"""
        try:
            cur = int(hawk.get(hawk.PLAY_SCALE, 0))
        except (TypeError, ValueError):
            cur = 0
        if cur not in SCALE_NAMES:
            cur = 0
        self._select_dialog("请选择默认画面缩放",
                            [(v, SCALE_NAMES[v]) for v in sorted(SCALE_NAMES)],
                            cur, self._apply_scale)

    def _apply_scale(self, value):
        hawk.put(hawk.PLAY_SCALE, value)
        self._refresh_values()
        self._set_status(f"画面缩放已切换为「{SCALE_NAMES[value]}」，"
                                   f"下次播放生效")

    def _pick_his_num(self):
        """历史记录上限（对应 llHistoryNum → HISTORY_NUM）"""
        try:
            cur = int(hawk.get(hawk.HISTORY_NUM, 0))
        except (TypeError, ValueError):
            cur = 0
        if cur not in (0, 1, 2):
            cur = 0
        self._select_dialog("保留历史记录数量",
                            [(v, f"{HIS_NUM_ARRAY[v]} 条") for v in (0, 1, 2)],
                            cur, self._apply_his_num)

    def _apply_his_num(self, value):
        hawk.put(hawk.HISTORY_NUM, value)
        self._refresh_values()
        self._set_status(f"历史记录最多保留 {HIS_NUM_ARRAY[value]} 条，"
                                   f"超出部分自动清理")

    def _toggle_home_page(self):
        cur = self._home_page()
        hawk.put("home_page", "vod" if cur == "live" else "live")
        self._refresh_values()
        self._set_status("下次进入将打开 " +
                              ("直播" if cur != "live" else "点播"))

    # ------------------------------------------------ 开关类 ----
    def _toggle_flag(self, name, key, default=False):
        """通用开/关切换卡片"""
        on = not bool(hawk.get(key, default))
        hawk.put(key, 1 if on else 0)
        self._refresh_values()
        self._set_status(f"{name}已{'开启' if on else '关闭'}")

    def _pick_speed(self):
        """默认倍速（对应 HawkConfig.PLAY_SPEED）"""
        from .ui_play import SPEEDS
        try:
            cur = float(hawk.get(hawk.PLAY_SPEED, 1.0) or 1.0)
        except (TypeError, ValueError):
            cur = 1.0
        idx = min(range(len(SPEEDS)), key=lambda i: abs(SPEEDS[i] - cur))
        self._select_dialog("默认播放倍速",
                            list(enumerate(f"{s:g}x" for s in SPEEDS)),
                            idx, lambda v: self._apply_speed(SPEEDS[v]))

    def _apply_speed(self, speed):
        hawk.put(hawk.PLAY_SPEED, float(speed))
        self._refresh_values()
        self._set_status(f"默认倍速已设为 {speed:g}x")

    def _pick_sub_size(self):
        """字幕字号（对应 HawkConfig.SUB_FONT_SIZE）"""
        try:
            cur = int(hawk.get(hawk.SUB_FONT_SIZE, 0) or 0)
        except (TypeError, ValueError):
            cur = 0
        items = list(SUB_FONT_NAMES.items())
        idx = next((i for i, (v, _n) in enumerate(items) if v == cur), 0)
        self._select_dialog("字幕字号",
                            [(i, n) for i, (_v, n) in enumerate(items)],
                            idx, lambda i: self._apply_sub_size(items[i][0]))

    def _apply_sub_size(self, size):
        hawk.put(hawk.SUB_FONT_SIZE, int(size))
        self._refresh_values()
        self._set_status(f"字幕字号已设为「{SUB_FONT_NAMES.get(size, size)}」")

    def _edit_danmaku_api(self):
        """弹幕接口模板（留空=只用本地弹幕文件）"""
        cur = str(hawk.get(hawk.DANMAKU_API, "") or "")

        def save(text):
            if text:
                hawk.put(hawk.DANMAKU_API, text)
                self._set_status("弹幕接口已保存")
            else:
                hawk.delete(hawk.DANMAKU_API)
                self._set_status("弹幕接口已清空")
            self._refresh_values()
        self._text_dialog("弹幕源", "弹幕接口地址（可用 {name} / {ep} 占位符，留空清除）",
                          cur, save)

    def _clear_live_groups(self):
        """清除已解锁的直播加密分组（下次需要重新输入密码）"""
        groups = hawk.get(hawk.LIVE_PASSWORD_GROUPS, []) or []
        if not groups:
            self._set_status("暂无已解锁的加密分组")
            return

        def do_clear():
            hawk.delete(hawk.LIVE_PASSWORD_GROUPS)
            self._refresh_values()
            self._set_status("已清除直播加密分组密码")
        self._confirm_dialog("直播加密分组",
                             f"已解锁 {len(groups)} 个加密分组，清除后需要重新输入密码。确定清除？",
                             do_clear)

    def _pick_wallpaper(self):
        """自定义首页壁纸：选择本地图片 / 恢复默认渐变"""
        win = tk.Toplevel(self)
        win.title("壁纸图片")
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text="壁纸图片", bg=BG, fg=FG,
                 font=tv_font(14, True)).pack(padx=24, pady=(14, 4), anchor="w")
        cur = str(hawk.get(hawk.WALLPAPER_OVERRIDE, "") or "")
        tk.Label(win, text=cur or "当前使用默认渐变", bg=BG, fg=FG_DIM,
                 font=tv_font(10), wraplength=420).pack(padx=24, anchor="w")

        def choose():
            win.destroy()
            p = filedialog.askopenfilename(
                parent=self.winfo_toplevel(), title="选择壁纸",
                filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.gif"),
                           ("所有文件", "*.*")])
            if not p:
                return
            hawk.put(hawk.WALLPAPER_OVERRIDE, p)
            hawk.put(hawk.WALLPAPER, 1)
            self._refresh_values()
            self._set_status("壁纸已设置：" + p)

        def clear():
            win.destroy()
            hawk.delete(hawk.WALLPAPER_OVERRIDE)
            self._refresh_values()
            self._set_status("已恢复默认渐变壁纸")

        row = tk.Frame(win, bg=BG)
        row.pack(padx=24, pady=12)
        FocusLabel(row, text="选择图片…", bg=FOCUS_BG, fg=FOCUS_FG,
                   font=tv_font(11, True), padx=16, pady=6,
                   on_select=choose).pack(side="left", padx=6)
        FocusLabel(row, text="恢复默认", bg=PANEL, fg=FG, font=tv_font(11),
                   padx=16, pady=6, on_select=clear).pack(side="left", padx=6)
        FocusLabel(row, text="取消", bg=PANEL, fg=FG, font=tv_font(11),
                   padx=16, pady=6,
                   on_select=win.destroy).pack(side="left", padx=6)
        win.bind("<Escape>", lambda e: win.destroy())

    # ------------------------------------------------ 数据备份/恢复 ----
    def _backup_data(self):
        """把 tvbox.db + hawk.json 打包成 zip（换机/重装前一键留档）"""
        from .paths import data_path
        import time as _t
        import zipfile
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(), title="备份数据",
            defaultextension=".zip",
            initialfile="tvbox_backup_%s.zip" % _t.strftime("%Y%m%d"),
            filetypes=[("Zip 备份", "*.zip")])
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for name in ("tvbox.db", "hawk.json"):
                    p = data_path(name)
                    if os.path.isfile(p):
                        z.write(p, name)
        except Exception as ex:
            self._set_status(f"备份失败：{ex}")
            return
        self._set_status(f"已备份到 {path}")

    def _restore_data(self):
        path = filedialog.askopenfilename(
            parent=self.winfo_toplevel(), title="恢复数据",
            filetypes=[("Zip 备份", "*.zip"), ("所有文件", "*.*")])
        if not path:
            return
        self._confirm_dialog(
            "恢复数据", "恢复将覆盖当前的观看历史、收藏和全部设置，确定继续？",
            lambda: self._do_restore(path))

    def _do_restore(self, path):
        import zipfile
        from .paths import data_path
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                wanted = [n for n in ("tvbox.db", "hawk.json") if n in names]
                if not wanted:
                    raise ValueError("不是有效的备份文件（缺少 tvbox.db / hawk.json）")
                # 先关掉 sqlite 连接，释放文件句柄再覆盖
                from . import store
                store.reset_connection()
                for name in wanted:
                    with z.open(name) as src, open(data_path(name), "wb") as dst:
                        shutil.copyfileobj(src, dst)
        except Exception as ex:
            self._set_status(f"恢复失败：{ex}")
            return
        hawk.reload()
        try:
            from . import data_api, store
            data_api.clear_caches()
            store.reset_connection()   # 下次访问时按新库重建连接
        except Exception:
            pass
        self._refresh_values()
        self._set_status("数据已恢复，返回主页后生效")

    # ------------------------------------------------ 开发者 ----
    def _open_log(self):
        from .paths import data_path
        p = data_path("error.log")
        try:
            if not os.path.isfile(p):
                open(p, "w", encoding="utf-8").close()
            os.startfile(p)
            self._set_status(f"已打开日志：{p}")
        except (AttributeError, OSError) as ex:
            self._set_status(f"日志位置：{p}（{ex}）")

    def _open_data_dir(self):
        from .paths import APP_BASE
        try:
            os.startfile(APP_BASE)
            self._set_status(f"已打开数据目录：{APP_BASE}")
        except (AttributeError, OSError) as ex:
            self._set_status(f"数据目录：{APP_BASE}（{ex}）")

    def _clear_cache(self):
        try:
            from . import data_api
            data_api.clear_caches()
        except Exception:
            pass
        from .paths import data_path
        cache_dir = data_path(".spider_cache")
        try:
            if os.path.isdir(cache_dir):
                shutil.rmtree(cache_dir)
        except Exception:
            pass
        self._set_status("缓存已清空（配置/分类缓存 + 爬虫缓存）")

    def _show_about(self):
        n_sites = len(api_config.source_bean_list)
        n_lives = len(api_config.lives)
        self._info_dialog("关于", (
            f"TVBox4Win v{VERSION}（Python + tkinter + libmpv）\n"
            f"当前配置：{n_sites} 个点播源 · {n_lives} 个直播源\n"
            f"功能：点播(CMS/Spider/py) · 直播 · 搜索 · 历史收藏 · 推送 · 设置"))

    # ------------------------------------------------ 弹窗 ----
    def _list_dialog(self, title, items, on_pick):
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text=title, bg=BG, fg=FG, font=tv_font(14, True)
                 ).pack(padx=20, pady=(14, 2), anchor="w")
        tk.Label(win, text="双击条目，或选中后按回车 / 点「确定」", bg=BG, fg=FG_DIM,
                 font=tv_font(10)).pack(padx=20, pady=(0, 6), anchor="w")
        box = tk.Listbox(win, bg=PANEL, fg=FG, width=70, height=min(8, len(items)),
                         font=("Consolas", 10), highlightthickness=1,
                         highlightbackground="#333", selectbackground=ACCENT)
        for it in items:
            box.insert("end", it)
        box.pack(padx=20, pady=4)
        box.selection_set(0)          # 默认选中第一条，回车即可确认
        box.activate(0)
        box.focus_set()

        def pick(_e=None):
            sel = box.curselection()
            if not sel:
                return
            # 关键：必须先取值再 destroy —— win.destroy() 会连带销毁 Listbox，
            # 之后再 box.get() 会抛 TclError，导致 on_pick 永远不被调用
            value = box.get(sel[0])
            win.destroy()
            on_pick(value)
        box.bind("<Return>", pick)
        box.bind("<Double-Button-1>", pick)

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=20, pady=(10, 14))
        FocusLabel(bar, text="确定", bg=FOCUS_BG, fg=FOCUS_FG, font=tv_font(11, True),
                   on_select=pick, padx=18, pady=6).pack(side="right")
        FocusLabel(bar, text="取消", bg=PANEL_HI, fg=FG, font=tv_font(10),
                   on_select=win.destroy, padx=14, pady=6).pack(side="right", padx=(0, 8))
        win.bind("<Escape>", lambda e: win.destroy())

    def _select_dialog(self, tip, options, current, on_pick):
        """单选弹窗（对应 SelectDialog：竖排选项，当前项高亮，方向键选择）"""
        win = tk.Toplevel(self)
        win.title(tip)
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text=tip, bg=BG, fg=FG, font=tv_font(14, True)
                 ).pack(padx=26, pady=(16, 8), anchor="w")
        box = tk.Frame(win, bg=BG)
        box.pack(fill="both", expand=True, padx=26, pady=(0, 16))
        btns = []
        focus_first = None
        for val, name in options:
            on = val == current
            b = FocusLabel(box, text=("● " if on else "　") + name,
                           bg=ACCENT if on else PANEL,
                           fg="#FFFFFF" if on else FG, font=tv_font(13, on),
                           padx=18, pady=10, anchor="w",
                           on_select=lambda v=val: (win.destroy(), on_pick(v)))
            b.pack(fill="x", pady=4)
            btns.append(b)
            if on and focus_first is None:
                focus_first = b
        if focus_first is not None:  # 焦点停在当前选中项（对应原版 defaultPos）
            focus_first.focus_set()
        elif btns:
            btns[0].focus_set()
        from .theme import grid_key_nav
        grid_key_nav(btns, 1, up_down_rows=1)
        win.bind("<Escape>", lambda e: win.destroy())

    def _info_dialog(self, title, text):
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text=text, bg=BG, fg=FG, font=tv_font(12),
                 justify="left").pack(padx=24, pady=20)
        FocusLabel(win, text="关闭", font=tv_font(12, True),
                   on_select=win.destroy).pack(pady=(0, 14))

    def _text_dialog(self, title, tip, value, on_ok):
        """单行文本输入弹窗（弹幕接口等）"""
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text=title, bg=BG, fg=FG,
                 font=tv_font(14, True)).pack(padx=20, pady=(14, 2), anchor="w")
        tk.Label(win, text=tip, bg=BG, fg=FG_DIM,
                 font=tv_font(10)).pack(padx=20, anchor="w")
        ent = tk.Entry(win, bg=PANEL, fg=FG, font=("Consolas", 11), width=70,
                       insertbackground=FG, highlightthickness=1,
                       highlightbackground="#333")
        ent.insert(0, value or "")
        ent.pack(padx=20, pady=8, fill="x")
        ent.focus_set()
        ent.icursor("end")

        def confirm(_e=None):
            text = ent.get().strip()
            win.destroy()
            on_ok(text)
        ent.bind("<Return>", confirm)
        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=20, pady=(4, 14))
        FocusLabel(bar, text="确定", bg=FOCUS_BG, fg=FOCUS_FG,
                   font=tv_font(11, True), padx=18, pady=6,
                   on_select=confirm).pack(side="right")
        FocusLabel(bar, text="取消", bg=PANEL_HI, fg=FG, font=tv_font(10),
                   padx=14, pady=6,
                   on_select=win.destroy).pack(side="right", padx=(0, 8))
        win.bind("<Escape>", lambda e: win.destroy())

    def _confirm_dialog(self, title, message, on_yes):
        """确认弹窗（不可撤销操作）"""
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.geometry("540x210")
        tk.Label(win, text=title, bg=BG, fg=FG,
                 font=tv_font(15, True)).pack(pady=(22, 8))
        tk.Label(win, text=message, bg=BG, fg=FG_DIM, font=tv_font(12),
                 wraplength=460, justify="center").pack(pady=(0, 18))

        def yes():
            win.destroy()
            on_yes()
        row = tk.Frame(win, bg=BG)
        row.pack()
        FocusLabel(row, text="取消", bg=PANEL, fg=FG, font=tv_font(12),
                   padx=24, pady=6,
                   on_select=win.destroy).pack(side="left", padx=10)
        FocusLabel(row, text="确定", bg=ACCENT, fg="#FFFFFF",
                   font=tv_font(12, True), padx=24, pady=6,
                   on_select=yes).pack(side="left", padx=10)
        win.bind("<Escape>", lambda e: win.destroy())
        try:
            win.focus_force()
        except tk.TclError:
            pass
