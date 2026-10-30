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
HOME_API = "home_api"
DEFAULT_API = "default_api"
API_HISTORY = "api_history"
SEARCH_HISTORY = "search_history"
LIVE_SOURCE = "live_source"
LIVE_HISTORY = "live_history"
PARSE_WEBVIEW = "parse_webview"
PLAY_TYPE = "play_type"
IJK_CODEC = "ijk_codec"
IJK_CACHE_PLAY = "ijk_cache_play"
LIVE_CHANNEL = "live_channel"          # 直播记忆上次频道（group/name）
LIVE_CONNECT_TIMEOUT = "live_connect_timeout"
