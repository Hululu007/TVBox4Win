"""type3 二次解析端到端测试：找 parse==1 的站点，验证解析链输出真实媒体地址"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "D:/code/tvbox2exe/tvboxpy")

from tvboxosc import data_api, apiconfig

cfg = apiconfig.extract_json(open("D:/code/tvbox2exe/tvboxpy/tvbox.json", encoding="utf-8").read())
apiconfig.api_config._parse(cfg)
print("parses:", [(p.name, p.flag, p.url) for p in apiconfig.api_config.parse_bean_list][:5])

tested = 0
for bean in apiconfig.api_config.source_bean_list:
    if getattr(bean, "type", 0) != 3:
        continue
    try:
        classes = data_api.get_classes(bean)
        if not classes:
            continue
        vods, _, _ = data_api.get_vods(bean, classes[0][0], 1)
        if not vods:
            continue
        detail = data_api.get_detail(bean, vods[0][0])
        if not detail["series_urls"] or not detail["series_urls"][0]:
            continue
        flag = detail["series_flags"][0][0]
        url = detail["series_urls"][0][0]
        real, hdr = data_api.get_play_url(bean, flag, url)
        tested += 1
        media = data_api._looks_media(real)
        print(f"[{'OK' if media else '??'}] {bean.key}: {url[:60]} -> {real[:90]} hdr={bool(hdr)}")
    except Exception as e:
        print(f"[ERR] {bean.key}: {e}")
    if tested >= 6:
        break
