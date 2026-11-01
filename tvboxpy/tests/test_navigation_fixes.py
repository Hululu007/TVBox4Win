# -*- coding: utf-8 -*-
"""Regression checks for live controls, empty details and navigation history."""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tvboxosc.app import App
from tvboxosc.ui_detail import Page as DetailPage


class DummyLabel:
    def __init__(self):
        self.text = ""

    def configure(self, **kw):
        self.text = kw.get("text", self.text)


class DummyPage:
    def __init__(self, state=None):
        self.state = state or {}
        self.destroyed = False

    def capture_state(self):
        return (), {"state": self.state}

    def destroy(self):
        self.destroyed = True


class DummyApp:
    def switch(self, *_args, **_kw):
        raise AssertionError("invalid episode must not open player")


def test_no_tk_configure_on_select():
    """on_select is a Python attribute on FocusLabel, not a Tk option."""
    bad = []
    pkg = os.path.join(ROOT, "tvboxosc")
    for name in os.listdir(pkg):
        if not name.endswith(".py"):
            continue
        path = os.path.join(pkg, name)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr not in ("configure", "config"):
                continue
            if any(k.arg == "on_select" for k in node.keywords):
                bad.append("%s:%s" % (name, node.lineno))
    assert not bad, bad


def test_empty_detail_does_not_play():
    page = object.__new__(DetailPage)
    page.info = {"series_flags": [], "series_urls": []}
    page.cur_flag = 0
    page.app = DummyApp()
    page.playurl_lbl = DummyLabel()
    page._play(0, "")
    assert page.playurl_lbl.text == "该线路没有可播放地址"


def test_detail_series_normalized():
    info = {
        "series_flags": [("线路一", []), ("空线路", ["一"])],
        "series_urls": [["http://example/1.m3u8"], []],
    }
    DetailPage._normalize_series(info)
    assert info["series_flags"] == [("线路一", ["第1集"])]
    assert info["series_urls"] == [["http://example/1.m3u8"]]


def test_navigation_stack_restores_state():
    app = App.__new__(App)
    app.current = DummyPage({"page": 3})
    app._current_route = (DummyPage, (), {})
    app._history = []
    shown = []

    app._destroy_current = App._destroy_current.__get__(app, App)

    def show(route):
        shown.append(route)
        app._current_route = route
        app.current = DummyPage(dict(route[2].get("state") or {}))
        return app.current

    app._show_route = show
    app.switch(DummyPage, state={"page": 4})
    assert len(app._history) == 1
    assert app._history[0][2]["state"] == {"page": 3}

    app.go_back()
    assert app._current_route[2]["state"] == {"page": 3}
    assert not app._history

    app.switch(DummyPage, state={"page": 5}, push=False)
    assert not app._history


if __name__ == "__main__":
    test_no_tk_configure_on_select()
    test_empty_detail_does_not_play()
    test_detail_series_normalized()
    test_navigation_stack_restores_state()
    print("ALL PASS")
