"""自动页面走查：加载配置 → 各页面实例化 → 断言无异常"""
import os, sys
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
import requests
requests.packages.urllib3.disable_warnings()

from tvboxosc import hawk, apiconfig, store
from tvboxosc.app import App

results = []

def check(name, fn):
    try:
        fn()
        results.append((name, "OK"))
    except Exception as e:
        import traceback; traceback.print_exc()
        results.append((name, f"FAIL: {e}"))

cfg = apiconfig.extract_json(apiconfig.fetch_text("http://xhztv.top/4k.json"))
apiconfig.api_config._parse(cfg)
from tvboxosc import data_api as _da
bean = None
for _c in apiconfig.api_config.source_bean_list:
    if _c.is_type012():
        try:
            if _da.get_classes(_c):
                bean = _c; break
        except Exception:
            continue
hawk.put(hawk.HOME_SOURCE, bean.key)

app = App()

def t_user():
    from tvboxosc.ui_user import UserFragment
    app.switch(UserFragment)
    app.update_idletasks()

def t_grid():
    from tvboxosc.ui_grid import Page
    page = app.switch(Page, source_key=bean.key)
    # 同步等分类+列表
    import time
    for _ in range(240):
        app.update()
        if page.vods:
            break
        time.sleep(0.4)
    assert page.vods, "网格无数据"
    assert len(page.classes) > 0, "无分类"

def t_detail():
    from tvboxosc.ui_grid import Page
    import time
    page = app.switch(Page, source_key=bean.key)
    for _ in range(240):
        app.update()
        if page.vods: break
        time.sleep(0.4)
    vid = page.vods[0][0]
    from tvboxosc.ui_detail import Page as D
    dp = app.switch(D, source_key=bean.key, vod_id=vid)
    for _ in range(240):
        app.update()
        if dp.info: break
        time.sleep(0.4)
    assert dp.info and dp.info["series_flags"], "详情无剧集"

def t_search():
    from tvboxosc.ui_search import Page
    sp = app.switch(Page)
    sp.kw.insert(0, "斗罗大陆")
    sp.do_search()
    import time
    t0 = time.time()
    while time.time() - t0 < 20:
        app.update()
        txt = sp.status.cget("text")
        if "共" in txt: break
        time.sleep(0.2)

def t_history_collect():
    from tvboxosc.ui_history import Page as H
    from tvboxosc.ui_collect import Page as C
    store.save_record(bean.key, "99999", "测试片", "", "线路1", "第01集", 12.3, 100)
    app.switch(H); app.update_idletasks()
    store.save_collect(bean.key, "99999", "测试片")
    app.switch(C); app.update_idletasks()
    assert store.is_collect(bean.key, "99999")
    store.save_collect(bean.key, "99999", "测试片")  # toggle off
    store.delete_record("99999", bean.key)

check("主页UserFragment", t_user)
check("点播GridFragment", t_grid)
check("详情DetailActivity", t_detail)
check("搜索SearchActivity", t_search)
check("历史/收藏", t_history_collect)

app.destroy()
print("\n===== 走查结果 =====")
for n, r in results:
    print(f"{n}: {r}")
