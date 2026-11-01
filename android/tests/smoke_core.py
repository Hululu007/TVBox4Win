"""安卓版业务链路自测（不需要 Kivy、不需要安卓设备）。

验证 vendor/tvboxosc 里的复用模块在「安卓数据目录」下能完整跑通：
    加载配置 → 站点源 → 分类 → 影片列表 → 详情 → 播放地址

用法：
    python sync_core.py
    python tests/smoke_core.py [配置文件URL]
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "vendor"))

from tvboxosc import apiconfig, data_api, hawk, paths    # noqa: E402

DEFAULT_API = "https://cyao2q.github.io/files/m.json"

fails = []
passed = 0


def ok(msg):
    global passed
    passed += 1
    print("OK   " + msg)


def bad(msg):
    fails.append(msg)
    print("FAIL " + msg)


def wait(flag, timeout=30, step=0.2):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if flag.get("done"):
            return True
        time.sleep(step)
    return False


def main():
    api_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_API

    # 1. 数据目录落在私有目录里（安卓上就是 /data/data/<pkg>/files）
    print("数据目录:", paths.APP_BASE)
    if os.path.isdir(paths.APP_BASE):
        ok("数据目录可用")
    else:
        bad("数据目录不存在：%s" % paths.APP_BASE)

    # 2. 加载配置
    cfg = apiconfig.ApiConfig()
    flag = {}
    cfg.load(api_url,
             lambda: flag.setdefault("done", "ok"),
             lambda m: flag.setdefault("done", "err:%s" % m))
    if not wait(flag):
        bad("配置加载超时（30s）")
        return summary()
    if flag["done"] != "ok":
        bad("配置加载失败：%s" % flag["done"])
        return summary()
    ok("配置加载成功（%d 个站点）" % len(cfg.source_bean_list))

    # 3. 过滤出安卓可用的 CMS 源
    beans = [b for b in cfg.source_bean_list if b.is_type012()]
    if beans:
        ok("可用 CMS 源 %d 个，例如：%s" % (len(beans), beans[0].name))
    else:
        bad("配置里没有 type 0/1/2 的 CMS 源")
        return summary()

    # 4. 挑一个能出分类的源（不同源稳定性差异大，逐个试）
    bean = None
    for b in beans[:6]:
        try:
            classes = data_api.get_classes(b)
        except Exception as e:
            print("     跳过 %s：%s" % (b.name, e))
            continue
        if classes:
            bean, cls = b, classes
            ok("取到分类 %d 个（源：%s）" % (len(cls), b.name))
            break
        print("     跳过 %s：没有分类" % b.name)
    if bean is None:
        bad("前 6 个源都没取到分类，换配置源再试")
        return summary()

    # 5. 影片列表
    cid = cls[0][0]
    vods, page, pagecount = data_api.get_vods(bean, cid, 1)
    if vods:
        ok("分类「%s」取到 %d 部影片（第 %d/%d 页）"
           % (cls[0][1], len(vods), page, pagecount))
    else:
        bad("分类「%s」没有影片" % cls[0][1])
        return summary()

    # 6. 详情
    vid, name, pic, remark = vods[0]
    info = data_api.get_detail(bean, vid)
    if info.get("name") and info.get("series_flags"):
        ok("详情「%s」：%d 条线路" % (info["name"], len(info["series_flags"])))
    else:
        bad("详情为空：%s" % (name or vid))
        return summary()

    # 7. 播放地址
    flag_name, eps = info["series_flags"][0]
    urls = info["series_urls"][0] if info["series_urls"] else []
    if not eps or not urls:
        bad("第一条线路没有剧集")
        return summary()
    url, headers = data_api.get_play_url(bean, flag_name, urls[0])
    if url and url.startswith(("http", "rtmp", "rtsp")):
        ok("播放地址解析成功：%s…" % url[:60])
    else:
        bad("播放地址解析结果可疑：%r" % (url,))

    # 8. hawk / store 可读写（安卓上写的是私有目录）
    hawk.put("smoke_probe", "安卓自测")
    if hawk.get("smoke_probe") == "安卓自测":
        ok("hawk.json 读写正常")
    else:
        bad("hawk.json 写入后读不回来")
    hawk.delete("smoke_probe")

    return summary()


def summary():
    print("\n== 通过 %d / 失败 %d ==" % (passed, len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
