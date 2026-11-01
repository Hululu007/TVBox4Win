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
