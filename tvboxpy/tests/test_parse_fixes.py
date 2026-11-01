# -*- coding: utf-8 -*-
"""P0-1 解析链路回归：parse type、嗅探规则、hosts、proxy 重写。

全部走本地 HTTP 服务，不访问外网。
用法：python tests/test_parse_fixes.py
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tvboxosc import apiconfig, data_api, local_proxy

VIDEO = "/media/video.m3u8"


class _Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype="text/html; charset=utf-8", code=200):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        port = self.server.server_address[1]
        base = "http://127.0.0.1:%d" % port
        if parsed.path == "/page":
            self._send('<html>var main = "%s";</html>' % VIDEO)
        elif parsed.path == "/plain":
            self._send("<html>no media here</html>")
        elif parsed.path == "/parse":
            target = parse_qs(parsed.query).get("url", [""])[0]
            if target.endswith("/plain"):
                self._send(json.dumps({
                    "url": base + VIDEO,
                    "header": {"Referer": base + "/"},
                }), "application/json")
            else:
                self._send("{}", "application/json")
        elif parsed.path == "/sniff":
            self._send('<html>x = "/media/video.m3u8?sign=1"</html>')
        elif parsed.path == "/live.m3u8":
            self._send(
                "#EXTM3U\n"
                '#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n'
                "#EXTINF:5,\n"
                "seg1.ts\n"
                "#EXT-X-STREAM-INF:BANDWIDTH=1\n"
                "sub.m3u8\n",
                "application/vnd.apple.mpegurl")
        else:
            self._send("not found", code=404)

    def log_message(self, *args):
        pass


def _serve():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def test_parse_config_semantics():
    cfg = {
        "sites": [{"key": "s", "name": "s", "type": 1,
                   "api": "http://example/api.php/provide/vod/"}],
        "parses": [
            {"name": "json", "url": "http://jx/?url=", "type": 1,
             "ext": {"header": {"User-Agent": "ParseUA"}}},
            {"name": "sniff", "url": "http://sniff/?url=", "type": 0},
        ],
        "hosts": ["a.example=10.0.0.8"],
        "rules": [
            {"host": "page.example", "rule": [r"\.mp4", r"sign="]},
            {"host": "page.example", "filter": [r"/ads/"]},
        ],
    }
    apiconfig.api_config._parse(cfg, "")
    beans = apiconfig.api_config.parse_bean_list
    assert beans[0].type == 1 and beans[0].flag == 1
    assert beans[0].headers == {"User-Agent": "ParseUA"}
    assert beans[1].type == 0
    assert data_api._join_parse_url(beans[0].url, "http://p/1") == \
        "http://jx/?url=http%3A%2F%2Fp%2F1"
    assert data_api._join_parse_url(beans[1].url, "http://p/1",
                                    encoded=False) == \
        "http://sniff/?url=http://p/1"


def test_video_format_parity():
    assert data_api.is_video_format("http://a/1.m3u8")
    assert data_api.is_video_format("http://a/video/tos/x")
    assert data_api.is_video_format("https://v.default.ixigua.com/x")
    assert data_api.is_video_format("http://a/player/m3u8play.php?url=abc")
    assert data_api.is_video_format("http://a/player/play.php?url=abc")
    assert data_api.is_video_format("http://a/download.aspx?id=1")
    assert data_api.is_video_format("rtmp://a/live")
    assert not data_api.is_video_format("http://a/watch?id=1")


def test_sniff_rules_and_filters():
    cfg = {"sites": [], "rules": [
        {"host": "page.example", "rule": [r"\.php", r"token="]},
        {"host": "page.example", "filter": [r"/ads/"]},
    ]}
    apiconfig.api_config._parse(cfg, "")
    # 规则命中：无扩展名的 .php 直链也能被识别
    assert data_api._sniff_text(
        'x="http://cdn/play.php?token=2"', "http://page.example/a") == \
        "http://cdn/play.php?token=2"
    # 规则不全命中：不当作视频
    assert data_api._sniff_text(
        'x="http://cdn/play.php?nosign"', "http://page.example/a") is None
    # 默认 isVideoFormat 命中的 .mp4 仍可播
    assert data_api._sniff_text(
        'x="http://cdn/v/1.mp4?nosign"', "http://page.example/a") == \
        "http://cdn/v/1.mp4?nosign"
    # filter 优先丢弃
    assert data_api._sniff_text(
        'x="http://cdn/ads/1.mp4?sign=2"', "http://page.example/a") is None
    # 无规则的 host 仍按扩展名嗅探
    assert data_api._sniff_text(
        'var main = "/live/index.m3u8?sign=x"', "http://other/a") == \
        "http://other/live/index.m3u8?sign=x"


def test_hosts_mapping():
    apiconfig.api_config._parse(
        {"sites": [], "hosts": ["a.example=10.0.0.8"]}, "")
    url, header = apiconfig.apply_host_mapping(
        "https://a.example:8443/v.m3u8?x=1", None)
    assert url == "https://10.0.0.8:8443/v.m3u8?x=1"
    assert header == {"Host": "a.example"}
    # 非 hosts 域名原样返回
    url2, header2 = apiconfig.apply_host_mapping("https://b.example/v", None)
    assert url2 == "https://b.example/v" and header2 is None


def test_proxy_rewrite_and_headers():
    base = "http://127.0.0.1:9978/"
    content = (
        "#EXTM3U\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n'
        "#EXTINF:5,\n"
        "seg1.ts\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1\n"
        "sub.m3u8\n")
    out = local_proxy.rewrite_m3u8(
        content, "http://cdn.example/live/main.m3u8", base,
        {"User-Agent": "UA"})
    assert 'type=key&ua=UA&url=http%3A%2F%2Fcdn.example%2Flive%2Fkey.bin' in out
    assert 'type=media&ua=UA&url=http%3A%2F%2Fcdn.example%2Flive%2Fseg1.ts' in out
    assert 'type=m3u8&ua=UA&url=http%3A%2F%2Fcdn.example%2Flive%2Fsub.m3u8' in out
    params = {"ua": ["Mozilla"], "referer": ["http://ref/"],
              "url": ["http://cdn.example/a.m3u8"]}
    assert local_proxy.header_params(params) == {
        "User-Agent": "Mozilla", "Referer": "http://ref/"}
    assert apiconfig.check_replace_proxy("proxy://go=bom&url=x").endswith(
        "/proxy?go=bom&url=x")


def test_parse_pipeline_against_local_server():
    server, port = _serve()
    base = "http://127.0.0.1:%d" % port
    try:
        # 1) 页面里直接有媒体地址：嗅探命中
        bean = type("B", (), {"type": 1, "player_url": ""})()
        url, header = data_api.get_play_url(bean, "", base + "/page")
        assert url == base + VIDEO and header is None

        # 2) 页面没有媒体地址：走 parses JSON 接口，并带回 header
        apiconfig.api_config._parse({
            "sites": [],
            "parses": [{"name": "json", "url": base + "/parse?url=",
                        "type": 1}],
        }, "")
        url, header = data_api.get_play_url(bean, "", base + "/plain")
        assert url == base + VIDEO
        assert header == {"Referer": base + "/"}
    finally:
        server.shutdown()
        server.server_close()


def test_proxy_live_against_local_server():
    server, port = _serve()
    base = "http://127.0.0.1:%d/" % port
    proxy_base = "http://127.0.0.1:9978/"
    try:
        code, ctype, body, _ = local_proxy.handle(
            {"go": ["live"], "type": ["m3u8"],
             "url": [base + "live.m3u8"]}, proxy_base)
        assert code == 200
        assert ctype == "application/vnd.apple.mpegurl"
        text = body.decode("utf-8")
        assert text.startswith("#EXTM3U")
        assert "proxy?go=live&type=media" in text
        assert "\nseg1.ts\n" not in text  # 已改写为代理地址
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    test_parse_config_semantics()
    test_video_format_parity()
    test_sniff_rules_and_filters()
    test_hosts_mapping()
    test_proxy_rewrite_and_headers()
    test_parse_pipeline_against_local_server()
    test_proxy_live_against_local_server()
    print("ALL PASS")
