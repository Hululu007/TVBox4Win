# -*- coding: utf-8 -*-
"""模拟 app 真实流程：load 配置 → 取鱼妖 bean → get_classes → get_category"""
import sys, threading, time, traceback

sys.path.insert(0, r"D:\code\tvbox2exe\tvboxpy")

from tvboxosc import apiconfig
from tvboxosc import data_api

done = threading.Event()
result = {}

def ok(*a, **k):
    result["ok"] = True
    done.set()

def err(*a, **k):
    result["err"] = a
    done.set()

URL = "https://cyao2q.github.io/files/m.json"

apiconfig.api_config.load(URL, ok_cb=ok, err_cb=err)
if not done.wait(30):
    print("FAIL: load timeout")
    sys.exit(1)
print("load:", result)

from tvboxosc.apiconfig import api_config
bean = None
for b in api_config.source_bean_list:
    if "鱼" in (b.name or ""):
        bean = b
        break
print("bean:", bean and (bean.name, bean.key, bean.type, bean.api, bean.jar))
if not bean:
    sys.exit(1)

t0 = time.time()
try:
    classes = data_api.get_classes(bean)
    print("get_classes: %.1fs, %d classes" % (time.time() - t0, len(classes)))
    for c in classes[:8]:
        print("  ", c)
    if classes:
        tid = classes[0][0]
        t1 = time.time()
        vods = data_api.get_vods(bean, tid, 1)
        print("get_vods: %.1fs, %d items" % (time.time() - t1, len(vods)))
        for v in vods[:3]:
            print("  ", v)
except Exception:
    traceback.print_exc()
