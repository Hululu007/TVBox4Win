"""jar 爬虫冒烟测试：csp_DouDouGuard（Bee.jar 鱼妖）全链路"""
import sys, time, json
sys.path.insert(0, ".")

from tvboxosc.apiconfig import SourceBean
from tvboxosc import jar_spider

bean = SourceBean()
bean.key = "doudou"
bean.name = "豆豆推荐"
bean.type = 3
bean.api = "csp_DouDouGuard"
bean.jar = "https://cyao2q.github.io/files/jar/Bee.jar;md5;8F59443D53D73EF5E34581B77E3C5A15"
bean.ext = None

t0 = time.time()
sp = jar_spider.get_jar_spider(bean)
print(f"[+] 站点代理就绪 {time.time()-t0:.1f}s")

t0 = time.time()
home = sp.home_content(True)
print(f"[+] homeContent {time.time()-t0:.1f}s")
cls = home.get("class") or []
print("    分类数:", len(cls))
for c in cls[:8]:
    print("   -", c.get("type_name"), c.get("type_id"))
vods = home.get("list") or []
if isinstance(vods, dict):
    vods = vods.get("list") or []
print("    首页影片数:", len(vods))
for v in vods[:5]:
    print("   -", v.get("vod_name"), "|", v.get("vod_id"))

if cls:
    t0 = time.time()
    cat = sp.category_content(cls[0]["type_id"], 1, True, {})
    print(f"[+] categoryContent {time.time()-t0:.1f}s")
    lst = cat.get("list") or []
    if isinstance(lst, dict):
        lst = lst.get("list") or []
    print("    分类影片数:", len(lst))
    if lst:
        vid = lst[0].get("vod_id")
        t0 = time.time()
        det = sp.detail_content([str(vid)])
        print(f"[+] detailContent {time.time()-t0:.1f}s")
        info = (det.get("list") or [{}])[0]
        print("    详情:", info.get("vod_name"), "| 播放源:", len(info.get("vod_play_from", "") or ""))
        print("    vod_play_url 前120字:", (info.get("vod_play_url") or "")[:120])

jar_spider.shutdown()
print("DONE")
