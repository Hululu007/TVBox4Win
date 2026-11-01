"""Hawk 配置存储的复刻 —— json 文件持久化（对应 util/HawkConfig.java + Hawk）"""
import json
import os
import threading

from .paths import data_path

_PATH = data_path("hawk.json")
_lock = threading.Lock()
_data = None


def _load():
    global _data
    if _data is None:
        try:
            with open(_PATH, encoding="utf-8") as f:
                _data = json.load(f)
        except (OSError, json.JSONDecodeError):
            _data = {}
    return _data


def get(key, default=None):
    return _load().get(key, default)


def put(key, value):
    global _data
    with _lock:
        _load()
        _data[key] = value
        tmp = _PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _PATH)


def delete(key):
    with _lock:
        _load()
        _data.pop(key, None)
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(_data, f, ensure_ascii=False, indent=1)


def reload():
    """丢弃内存缓存，重新从磁盘读取（数据恢复后调用）"""
    global _data
    with _lock:
        _data = None
        _load()


# HawkConfig 键位对照
HOME_SOURCE = "home_source"
HOME_REC = "home_rec"      # 首页推荐：0 豆瓣热播 / 1 站点推荐 / 2 观看历史
DEFAULT_HOME_REC = 1       # 对应 HawkConfig.DEFAULT_HOME_REC = 1
HOME_API = "home_api"
DEFAULT_API = "default_api"
API_HISTORY = "api_history"
SEARCH_HISTORY = "search_history"
LIVE_SOURCE = "live_source"
LIVE_HISTORY = "live_history"
LIVE_API_URL = "live_api_url"          # 自定义直播源地址（对应 HawkConfig.LIVE_API_URL）
LIVE_API_HISTORY = "live_api_history"  # 直播历史（对应 HawkConfig.LIVE_API_HISTORY）
PARSE_WEBVIEW = "parse_webview"
PLAY_TYPE = "play_type"
IJK_CODEC = "ijk_codec"
PLAY_SCALE = "play_scale"          # 画面缩放：0 默认 / 1 16:9 / 2 4:3 / 3 填充 / 4 原始
HISTORY_NUM = "history_num"        # 历史记录上限：0→30条 / 1→50条 / 2→100条
IJK_CACHE_PLAY = "ijk_cache_play"
LIVE_CHANNEL = "live_channel"          # 直播记忆上次频道（group/name）
LIVE_CONNECT_TIMEOUT = "live_connect_timeout"
EPG_URL = "epg_url"                    # 节目单地址（对应 HawkConfig.EPG_URL）
LIVE_PASSWORD_GROUPS = "live_password_groups"  # 已解锁的加密分组（直播 m3u group-password）
LIVE_REVERSE = "live_reverse"          # 频道列表倒序

# ---- P1 播放页 ----
PLAY_SPEED = "play_speed"              # 默认播放倍速
SPEED_MEMORY = "speed_memory"          # 记住上次倍速
AUTO_SWITCH_LINE = "auto_switch_line"  # 播放失败自动换线
SUB_FONT_SIZE = "sub_font_size"        # 字幕字号（0=跟随视频）
SUB_DELAY = "sub_delay"                # 字幕延迟（秒）
DANMAKU_ENABLE = "danmaku_enable"      # 弹幕开关
DANMAKU_API = "danmaku_api"            # 弹幕接口模板
DANMAKU_FILE = "danmaku_file"          # 弹幕文件（本地 xml/json）
KEEP_AWAKE = "keep_awake"              # 播放时阻止系统休眠
PLAYER_CACHE = "player_cache"          # 播放缓存开关

# ---- P1 首页/详情/搜索/历史 ----
FAST_SEARCH = "fast_search"            # 快速搜索模式（分词+精确匹配）
AUTO_PLAY = "auto_play"                # 详情页自动播放第一集
HISTORY_MERGE = "history_merge"        # 观看历史按片名合并
DOUBAN_YEAR = "douban_year"            # 豆瓣热播年份筛选（空=全部）
DEVELOPER_MODE = "developer_mode"      # 开发者模式（显示日志/数据目录）
WALLPAPER = "wallpaper_enable"         # 首页壁纸开关
WALLPAPER_OVERRIDE = "wallpaper_override"  # 自定义壁纸本地路径
