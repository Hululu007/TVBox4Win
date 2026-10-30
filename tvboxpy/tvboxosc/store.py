"""数据存储复刻（对应 data/AppDataBase + cache/VodRecord + VodCollect）"""
import json
import sqlite3
import threading
import time

from . import hawk
from .paths import data_path

_lock = threading.Lock()
_db = None


def _conn():
    global _db
    if _db is None:
        _db = sqlite3.connect(data_path("tvbox.db"), check_same_thread=False)
        _db.execute("""CREATE TABLE IF NOT EXISTS vod_record (
            vod_id TEXT, vod_name TEXT, source_key TEXT,
            play_tag TEXT, play_flag TEXT, play_ep TEXT,
            pos REAL, duration REAL, update_time INTEGER,
            data_json TEXT DEFAULT '',
            PRIMARY KEY (vod_id, source_key))""")
        try:  # 旧库升级（对应 Java Room Migration）
            _db.execute("ALTER TABLE vod_record ADD COLUMN data_json TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        _db.execute("""CREATE TABLE IF NOT EXISTS vod_collect (
            vod_id TEXT, vod_name TEXT, source_key TEXT,
            vod_pic TEXT, update_time INTEGER,
            PRIMARY KEY (vod_id, source_key))""")
        # 对应 Java PlayActivity 进度按 progressKey=MD5(url) 每集一份（PlayActivity.java L131）
        _db.execute("""CREATE TABLE IF NOT EXISTS ep_progress (
            progress_key TEXT PRIMARY KEY, pos REAL, duration REAL,
            update_time INTEGER)""")
        _db.commit()
    return _db


def _progress_key(url):
    """对应 Java progressKey = MD5(playUrl)"""
    import hashlib
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def save_progress(url, pos, duration):
    """每集 URL 一份进度（对应 CacheManager.put(progressKey, VodInfo)）"""
    with _lock:
        c = _conn()
        c.execute("REPLACE INTO ep_progress VALUES (?,?,?,?)",
                  (_progress_key(url), pos, duration, int(time.time())))
        c.commit()


def get_progress(url):
    with _lock:
        row = _conn().execute(
            "SELECT pos, duration FROM ep_progress WHERE progress_key=?",
            (_progress_key(url),)).fetchone()
    return {"pos": row[0], "duration": row[1]} if row else None


def delete_progress(url):
    with _lock:
        c = _conn()
        c.execute("DELETE FROM ep_progress WHERE progress_key=?",
                  (_progress_key(url),))
        c.commit()


def save_record(source_key, vod_id, vod_name, play_tag, play_flag, play_ep,
                pos, duration, data_json=""):
    with _lock:
        c = _conn()
        c.execute("REPLACE INTO vod_record VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (vod_id, vod_name, source_key, play_tag, play_flag, play_ep,
                   pos, duration, int(time.time()), data_json or ""))
        c.commit()


def get_record(source_key, vod_id):
    with _lock:
        row = _conn().execute(
            "SELECT play_tag, play_flag, play_ep, pos, duration, data_json "
            "FROM vod_record WHERE vod_id=? AND source_key=?",
            (vod_id, source_key)).fetchone()
    if not row:
        return None
    data = {}
    if row[5]:
        try:
            data = json.loads(row[5])
        except json.JSONDecodeError:
            data = {}
    return {"play_tag": row[0], "play_flag": row[1], "play_ep": row[2],
            "pos": row[3], "duration": row[4], "data_json": data}


def all_records():
    with _lock:
        rows = _conn().execute(
            "SELECT vod_id, vod_name, source_key, play_tag, play_flag, play_ep, "
            "pos, duration, update_time FROM vod_record ORDER BY update_time DESC").fetchall()
    return [{"vod_id": r[0], "vod_name": r[1], "source_key": r[2], "play_tag": r[3],
             "play_flag": r[4], "play_ep": r[5], "pos": r[6], "duration": r[7],
             "update_time": r[8]} for r in rows]


def delete_record(vod_id, source_key):
    with _lock:
        c = _conn()
        c.execute("DELETE FROM vod_record WHERE vod_id=? AND source_key=?",
                  (vod_id, source_key))
        c.commit()


def remove_collect(source_key, vod_id):
    """删除收藏（对应 Java tvCollect 只删）"""
    with _lock:
        c = _conn()
        c.execute("DELETE FROM vod_collect WHERE vod_id=? AND source_key=?",
                  (vod_id, source_key))
        c.commit()


def save_collect(source_key, vod_id, vod_name, vod_pic=""):
    with _lock:
        c = _conn()
        exists = c.execute("SELECT 1 FROM vod_collect WHERE vod_id=? AND source_key=?",
                           (vod_id, source_key)).fetchone()
        if exists:
            c.execute("DELETE FROM vod_collect WHERE vod_id=? AND source_key=?",
                      (vod_id, source_key))
        else:
            c.execute("REPLACE INTO vod_collect VALUES (?,?,?,?,?)",
                      (vod_id, vod_name, source_key, vod_pic, int(time.time())))
        c.commit()
        return not exists  # True=已收藏


def is_collect(source_key, vod_id):
    with _lock:
        return bool(_conn().execute(
            "SELECT 1 FROM vod_collect WHERE vod_id=? AND source_key=?",
            (vod_id, source_key)).fetchone())


def all_collects():
    with _lock:
        rows = _conn().execute(
            "SELECT vod_id, vod_name, source_key, vod_pic, update_time "
            "FROM vod_collect ORDER BY update_time DESC").fetchall()
    return [{"vod_id": r[0], "vod_name": r[1], "source_key": r[2],
             "vod_pic": r[3], "update_time": r[4]} for r in rows]
