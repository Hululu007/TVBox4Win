# -*- coding: utf-8 -*-
"""P0-4 配置协议/加密 + P0-5 启动失败交互 验证

覆盖：
- AES-128 标准向量（FIPS-197 ECB、NIST CBC）
- decode_config：纯 JSON / Base64 包裹 / ;pk; AES-ECB / 2423 AES-CBC
- config_address / clan_to_address / local_path_of / resolve_ref
- fetch_text 读本地文件（含 BOM）
- ApiConfig.load：本地配置、相对路径解析、缓存回退
- 启动页失败后「重试 / 更换配置」文案与按钮存在
"""
import base64
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from tvboxosc import apiconfig, hawk, ui_thread
from tvboxosc.aeslite import (aes_cbc_encrypt, aes_ecb_encrypt,
                              aes_ecb_decrypt, bytes_from_hex)

_fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name +
          (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def eq(name, got, want):
    check(name, got == want, f"got={got!r} want={want!r}")


def pump_until(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        ui_thread._pump()          # 测试里没有 Tk 主循环，手动抽回调
        if pred():
            return True
        time.sleep(0.03)
    return False


# ------------------------------------------------------------ AES 向量 ----
key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
plain = bytes.fromhex("00112233445566778899aabbccddeeff")
eq("AES FIPS-197 ECB",
   aes_ecb_decrypt(bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a"), key,
                   unpad=False), plain)

iv = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
ct = bytes.fromhex("7649abac8119b246cee98e9b12e9197d")
from tvboxosc.aeslite import aes_cbc_decrypt
eq("AES NIST CBC",
   aes_cbc_decrypt(ct, bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c"), iv,
                   unpad=False),
   bytes.fromhex("6bc1bee22e409f96e93d7e117393172a"))

# --------------------------------------------------------- decode_config ----
cfg_text = json.dumps({"spider": "x", "sites": []}, ensure_ascii=False)
cf = json.dumps({"spider": "中文源"}, ensure_ascii=False)

eq("decode: 纯 JSON 原样", apiconfig.decode_config(cfg_text), cfg_text)

b64 = "ABCD1234**" + base64.b64encode(cf.encode()).decode()
eq("decode: Base64 包裹", apiconfig.decode_config(b64), cf)

ecb_key = "abcd1234"
ecb_hex = aes_ecb_encrypt(cf.encode(), (ecb_key + "0" * 8).encode()).hex()
eq("decode: ;pk; AES-ECB", apiconfig.decode_config(ecb_hex, ecb_key), cf)

cbc_key = b"1234567890abcdef"
cbc_iv13 = b"abcdefghijklm"
cipher = aes_cbc_encrypt(cf.encode(), cbc_key, cbc_iv13 + b"000")
raw = b"$#" + cbc_key + b"#$" + cipher + cbc_iv13
wrapped = raw.hex()
check("decode: 2423 前缀", wrapped.startswith("2423"), wrapped[:8])
eq("decode: 2423 AES-CBC", apiconfig.decode_config(wrapped), cf)

eq("decode: 坏数据不抛异常", apiconfig.decode_config("2423zzzz"), "2423zzzz")
eq("decode: 空串", apiconfig.decode_config(""), "")

# ------------------------------------------------ 地址 / 相对路径解析 ----
eq("clan: 远程补 /file/",
   apiconfig.clan_to_address("clan://1.2.3.4/box/cfg.json"),
   "http://1.2.3.4/file/box/cfg.json")
p = apiconfig.clan_to_address("clan://localhost/box/cfg.json")
check("clan: localhost → 本地文件", os.path.isabs(p) and p.endswith(os.path.join("box", "cfg.json")), p)

eq("config: http 原样",
   apiconfig.config_address("https://a.com/b.json")[0], "https://a.com/b.json")
eq("config: 裸域名补 http",
   apiconfig.config_address("a.com/b.json")[0], "http://a.com/b.json")
eq("config: ;pk; 拆分",
   apiconfig.config_address("a.com/b.json;pk;secret"),
   ("http://a.com/b.json", "secret"))
eq("config: clan 远程",
   apiconfig.config_address("clan://h/box/c.json")[0],
   "http://h/file/box/c.json")
p = apiconfig.config_address("file:///C:/tmp/cfg.json")[0]
eq("config: file:// → 本地路径", p, os.path.normpath("C:/tmp/cfg.json"))
p = apiconfig.config_address("clan://localhost/cfg.json")[0]
check("config: clan localhost 本地", os.path.isabs(p) and p.endswith("cfg.json"), p)
eq("config: 本地绝对路径", apiconfig.config_address("D:/x/cfg.json")[0], "D:/x/cfg.json")

eq("ref: http ./", apiconfig.resolve_ref("http://h/a/b/c.json", "./s.py"),
   "http://h/a/b/s.py")
eq("ref: http ../", apiconfig.resolve_ref("http://h/a/b/c.json", "../s.py"),
   "http://h/a/s.py")
eq("ref: 本地 ../",
   apiconfig.resolve_ref(os.path.join("D:", os.sep, "a", "b", "c.json"), "../s.py"),
   os.path.normpath(os.path.join("D:", os.sep, "a", "s.py")))
eq("ref: 非相对路径不动", apiconfig.resolve_ref("http://h/a/c.json", "csp_X"), "csp_X")

# ------------------------------------------------------- fetch_text 本地 ----
tmp = tempfile.mkdtemp(prefix="tvbox_cfg_")
cfg_path = os.path.join(tmp, "bom.json")
with open(cfg_path, "w", encoding="utf-8-sig") as f:
    f.write('{"sites": []}')
eq("fetch_text: 本地文件去 BOM", apiconfig.fetch_text(cfg_path), '{"sites": []}')
eq("fetch_text: 缺失文件返回 None",
   apiconfig.fetch_text(os.path.join(tmp, "no.json")), None)

# ------------------------------------------------------ ApiConfig.load ----
old_home_api = hawk.get(hawk.HOME_API)
# load() 会原地 insert 历史列表，必须拷贝，否则恢复时仍是脏数据
old_hist = list(hawk.get(hawk.API_HISTORY) or [])
old_cache = None
try:
    with open(apiconfig.STORE_PATH, "rb") as f:
        old_cache = f.read()
except OSError:
    pass

try:
    # 1) 本地配置 + ./ 相对路径
    spider_file = os.path.join(tmp, "spider.jar")
    open(spider_file, "wb").close()
    site_file = os.path.join(tmp, "site.py")
    open(site_file, "w", encoding="utf-8").close()
    cfg = {
        "spider": "./spider.jar",
        "sites": [{"key": "s1", "name": "站点1", "api": "./site.py", "type": 3}],
        "parses": [{"name": "p1", "url": "./parse.json", "type": 1}],
        "wallpaper": "./bg.jpg",
        "lives": [{"name": "l1", "url": "./live.txt",
                   "api": "./live.py", "epg": "./epg.xml"}],
    }
    with open(os.path.join(tmp, "cfg.json"), "w", encoding="utf-8-sig") as f:
        json.dump(cfg, f)

    state = {}

    def ok():
        state["ok"] = True

    def err(msg):
        state["err"] = msg

    apiconfig.api_config.load(os.path.join(tmp, "cfg.json"), ok, err)
    pump_until(lambda: "ok" in state or "err" in state)
    check("load: 本地配置成功", state.get("ok") is True, state.get("err"))
    eq("load: spider 相对路径", apiconfig.api_config.spider, spider_file)
    b = apiconfig.api_config.get("s1")
    eq("load: site api 相对路径", b.api if b else None, site_file)
    eq("load: parse url 相对路径",
       apiconfig.api_config.parse_bean_list[0].url, os.path.join(tmp, "parse.json"))
    eq("load: wallpaper 相对路径",
       apiconfig.api_config.wallpaper, os.path.join(tmp, "bg.jpg"))
    lv = apiconfig.api_config.lives[0] if apiconfig.api_config.lives else {}
    eq("load: live url 相对路径", lv.get("url"), os.path.join(tmp, "live.txt"))
    eq("load: live epg 相对路径", lv.get("epg"), os.path.join(tmp, "epg.xml"))
    eq("load: 非缓存来源", apiconfig.api_config.last_from_cache, False)

    # 1b) 加密本地配置：;pk; AES-ECB / 2423 AES-CBC
    enc_cfg = json.dumps({"sites": [{"key": "enc", "name": "加密源",
                                     "api": "csp_Enc"}]}, ensure_ascii=False)
    enc_hex = aes_ecb_encrypt(enc_cfg.encode(), (ecb_key + "0" * 8).encode()).hex()
    enc_path = os.path.join(tmp, "enc.txt")
    with open(enc_path, "w", encoding="utf-8") as f:
        f.write(enc_hex)
    state.clear()
    apiconfig.api_config.load(enc_path + ";pk;" + ecb_key, ok, err)
    pump_until(lambda: "ok" in state or "err" in state)
    check("load: 本地 ;pk; 解密", state.get("ok") is True, state.get("err"))
    check("load: 解密站点生效", apiconfig.api_config.get("enc") is not None)

    enc2 = json.dumps({"sites": [{"key": "enc2", "name": "2423源",
                                  "api": "csp_Enc2"}]}, ensure_ascii=False)
    raw2 = (b"$#" + cbc_key + b"#$" +
            aes_cbc_encrypt(enc2.encode(), cbc_key, cbc_iv13 + b"000") + cbc_iv13)
    with open(os.path.join(tmp, "enc2423.txt"), "w", encoding="utf-8") as f:
        f.write(raw2.hex())
    state.clear()
    apiconfig.api_config.load(os.path.join(tmp, "enc2423.txt"), ok, err)
    pump_until(lambda: "ok" in state or "err" in state)
    check("load: 本地 2423 解密", state.get("ok") is True, state.get("err"))
    check("load: 2423 站点生效", apiconfig.api_config.get("enc2") is not None)

    # 2) 本地文件不存在 → 明确报错（不走网络）
    state.clear()
    missing = os.path.join(tmp, "missing.json")
    apiconfig.api_config.load(missing, ok, err)
    pump_until(lambda: "ok" in state or "err" in state)
    check("load: 本地缺失提示", "不存在" in state.get("err", ""), state)

    # 3) 新配置损坏但缓存可用 → 回退缓存并标记
    good_cfg = {"sites": [{"key": "cache", "name": "缓存源", "api": "csp_X"}]}
    with open(apiconfig.STORE_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(good_cfg))
    bad_path = os.path.join(tmp, "bad.json")
    with open(bad_path, "w", encoding="utf-8") as f:
        f.write("这不是 JSON")
    state.clear()
    apiconfig.api_config.load(bad_path, ok, err)
    pump_until(lambda: "ok" in state or "err" in state)
    check("load: 坏配置回退缓存", state.get("ok") is True, state.get("err"))
    eq("load: 缓存标记", apiconfig.api_config.last_from_cache, True)
    check("load: 缓存站点生效", apiconfig.api_config.get("cache") is not None)
finally:
    hawk.put(hawk.HOME_API, old_home_api) if old_home_api is not None \
        else hawk.delete(hawk.HOME_API)
    hawk.put(hawk.API_HISTORY, old_hist) if old_hist is not None \
        else hawk.delete(hawk.API_HISTORY)
    if old_cache is not None:
        with open(apiconfig.STORE_PATH, "wb") as f:
            f.write(old_cache)

# ------------------------------------------------------ P0-5 启动页交互 ----
with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as f:
    main_src = f.read()
for token in ("重试", "更换配置", "上次缓存的配置", "filedialog",
              "last_from_cache", "FocusLabel"):
    check(f"startup: 含 {token}", token in main_src)

print("\n" + ("ALL PASS" if not _fails else f"FAILED {len(_fails)}: {_fails}"))
sys.exit(1 if _fails else 0)
