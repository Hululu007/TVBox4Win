# -*- coding: utf-8 -*-
"""P0-2 播放失败容错回归：重试 → 换线路 → 放弃的决策顺序。

不启动播放器，只测纯逻辑（Failover），外加 ui_play 关键接口的静态检查。
用法：python tests/test_play_failover.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tvboxosc.ui_play import Failover, _short_reason


def test_single_line_retries_then_gives_up():
    f = Failover(1)
    assert f.next_action(0, 0, [10]) == ("retry", None)
    assert f.next_action(0, 0, [10]) == ("give_up", None)


def test_switch_to_next_line_after_retry():
    f = Failover(2)
    counts = [10, 10]
    assert f.next_action(0, 3, counts) == ("retry", None)
    assert f.next_action(0, 3, counts) == ("switch", 1)
    # 新线路同样先重载一次
    assert f.next_action(1, 3, counts) == ("retry", None)
    assert f.next_action(1, 3, counts) == ("give_up", None)


def test_skip_line_without_that_episode():
    """集数较少的线路直接跳过，不在上面白等一个超时"""
    f = Failover(3)
    counts = [20, 0, 20]
    assert f.next_action(0, 5, counts) == ("retry", None)
    assert f.next_action(0, 5, counts) == ("switch", 2)


def test_no_line_has_episode():
    f = Failover(2)
    counts = [3, 2]
    assert f.next_action(0, 2, counts) == ("retry", None)
    assert f.next_action(0, 2, counts) == ("give_up", None)


def test_reset_after_success_reopens_all_lines():
    f = Failover(2)
    counts = [10, 10]
    assert f.next_action(0, 0, counts) == ("retry", None)
    assert f.next_action(0, 0, counts) == ("switch", 1)
    f.reset()  # 出画面后调用
    assert f.next_action(0, 0, counts) == ("retry", None)
    assert f.next_action(0, 0, counts) == ("switch", 1)


def test_short_reason_single_line():
    assert _short_reason("a\nb\tc") == "a b c"
    long = "x" * 50
    out = _short_reason(long)
    assert len(out) == 25 and out.endswith("…")


def test_page_accepts_all_lines_kwargs():
    """详情页靠这三个参数完成自动换线，签名不能丢"""
    import inspect
    from tvboxosc.ui_play import Page
    params = inspect.signature(Page.__init__).parameters
    for name in ("all_flags", "all_urls", "line_index"):
        assert name in params, name
    from tvboxosc import ui_detail
    src = inspect.getsource(ui_detail.Page._play)
    for name in ("all_flags=", "all_urls=", "line_index="):
        assert name in src, name


if __name__ == "__main__":
    test_single_line_retries_then_gives_up()
    test_switch_to_next_line_after_retry()
    test_skip_line_without_that_episode()
    test_no_line_has_episode()
    test_reset_after_success_reopens_all_lines()
    test_short_reason_single_line()
    test_page_accepts_all_lines_kwargs()
    print("ALL PASS")
