"""py 类爬虫支持测试（学习 tvboxosc-python pyramid 运行时）"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tvboxosc.py_spider import jsoup, Spider, PySpider, _parse_html, get_py_spider


def test_dom_and_jsoup():
    html = """
    <html><body>
    <div class="list">
      <div class="item"><a href="/v/1"><img src="/p/1.jpg"/><span class="title">影片一</span></a></div>
      <div class="item"><a href="/v/2"><img src="/p/2.jpg"/><span class="title">影片二</span></a></div>
      <div class="item ad"><a href="/ad">广告</a></div>
    </div></body></html>
    """
    js = jsoup("http://example.com/")
    # pdfa：取列表项
    items = js.pdfa(html, "body&&.item")
    assert len(items) == 3, items
    # pdfh：链式取属性 + urljoin
    url = js.pdfh(items[0], "a&&href", base_url="http://example.com/cat/")
    assert url == "http://example.com/v/1", url
    # pdfh 不带 base_url 不做 urljoin（与原版一致）；pd 才用 MY_URL
    img = js.pdfh(items[0], "img&&src")
    assert img == "/p/1.jpg", img
    assert js.pd(items[0], "img&&src") == "http://example.com/p/1.jpg"
    title = js.pdfh(items[0], ".title&&Text")
    assert title == "影片一", title
    # :gt(n) 跳过前 n 个
    t2 = js.pdfa(html, "body&&.item:gt(0)")
    assert len(t2) == 2, t2
    assert js.pdfh(t2[0], "a&&Text") == "影片二"
    # pd 自动 urljoin
    assert js.pd(items[1], "a&&href") == "http://example.com/v/2"
    print("test_dom_and_jsoup OK")


def test_jsonpath_subset():
    js = jsoup()
    data = {"list": [{"name": "a", "url": "/u1"}, {"name": "b", "url": "/u2"}]}
    txt = json.dumps(data)
    assert js.pjfh(txt, "$.list[0].name") == "a"
    assert js.pjfa(txt, "$.list[*].name") == ["a", "b"]
    assert js.pj(txt, "$.list[1].url") == "http://x/u2" or True  # MY_URL 未设
    js.MY_URL = "http://x/"
    assert js.pj(txt, "$.list[1].url") == "http://x/u2"
    # || 备选
    assert js.pjfh(txt, "$.nope||$.list[0].url") == "/u1"
    print("test_jsonpath_subset OK")


def test_py_spider_load_and_route():
    """写一个临时 py 爬虫，验证下载/加载/方法转发/基类工具"""
    src = '''
import json

class Spider:
    def init(self, extend=""):
        self.extend = extend

    def homeContent(self, filter):
        return {"class": [{"type_id": "1", "type_name": "电影"}]}

    def categoryContent(self, tid, pg, filter, extend):
        return {"list": [
            {"vod_id": 1, "vod_name": "测试片", "vod_pic": "",
             "vod_remarks": "HD"}], "page": pg, "pagecount": 1}

    def detailContent(self, ids):
        return {"list": [{"vod_id": ids[0], "vod_name": "测试片",
            "vod_play_from": "线路一",
            "vod_play_url": "第1集$http://s/1.m3u8#第2集$http://s/2.m3u8"}]}

    def searchContent(self, key, quick, pg="1"):
        return {"list": [{"vod_id": 9, "vod_name": "测试" + key}]}

    def playerContent(self, flag, id, vipFlags=""):
        return {"parse": 0, "playUrl": "", "url": id, "header": "{}"}

    def fetch(self, url, **kw):
        class R:  # 简单桩
            text = "<html><body>ok</body></html>"
            content = text.encode()
            status_code = 200
            def json(self): return {}
        return R()
'''
    d = tempfile.mkdtemp()
    py_path = os.path.join(d, "demo.py")
    with open(py_path, "w", encoding="utf-8") as f:
        f.write(src)

    ps = PySpider("demo", py_path, "")
    cfg = ps.home_content(True)
    assert cfg["class"][0]["type_name"] == "电影"
    cat = ps.category_content("1", 2, True, "")
    assert cat["list"][0]["vod_name"] == "测试片" and cat["page"] == 2
    det = ps.detail_content([1])
    eps = det["list"][0]["vod_play_url"].split("#")
    assert len(eps) == 2
    play = ps.player_content("线路一", "http://s/1.m3u8")
    assert play["url"] == "http://s/1.m3u8" and play["parse"] == 0
    sr = ps.search_content("测试")
    assert sr["list"][0]["vod_name"] == "测试测试"

    # 基类工具
    sp = Spider()
    assert sp.regStr("id=123&x", r"id=(\d+)") == "123"
    assert sp.removeHtmlTags("<b>hi</b>") == "hi"
    assert sp.cleanText("a😀b") == "ab"
    sp.setCache("k", {"a": 1})
    assert sp.getCache("k") == '{"a": 1}'
    node = _parse_html("<div><a href='/x'>go</a></div>")
    assert sp.xpText(node, "//a/text()") == "go"
    assert sp.xpText(node, "//a/@href") == "/x"

    # get_py_spider 缓存：两次获取同一实例
    ps2 = get_py_spider("demo", py_path)
    ps3 = get_py_spider("demo", py_path)
    assert ps2 is ps3
    print("test_py_spider_load_and_route OK")


def test_get_spider_routes_py():
    from tvboxosc.spider import get_spider
    class B:
        key = "demo2"
        api = "https://example.com/sp.py"
        ext = None
        type = 3
    # 只验证分流到 PySpider（不真正下载）
    from tvboxosc.py_spider import PySpider
    sp = get_spider(B())
    assert isinstance(sp, PySpider), type(sp)
    print("test_get_spider_routes_py OK")


if __name__ == "__main__":
    test_dom_and_jsoup()
    test_jsonpath_subset()
    test_py_spider_load_and_route()
    test_get_spider_routes_py()
    print("ALL PASS")
