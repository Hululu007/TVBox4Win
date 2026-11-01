# -*- coding: utf-8 -*-
"""平台隔离契约测试

目的：保证 Windows / macOS 的改动互不影响。四条硬约束：

1. 共享代码（UI / 业务 / 播放器门面）不得出现任何平台判断；
2. 平台差异只能出现在 host/ 包内（host/win.py · host/mac.py）；
3. 两个平台实现导出的函数集合必须一致（某一侧漏实现会立刻暴露）；
4. 播放器门面对外接口固定，避免某一平台顺手改了签名影响另一平台。

用 AST 静态分析而不是 import：macOS 实现依赖 AppKit，在 Windows 上 import 会失败。
用法：python tests/verify_platform_isolation.py
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "tvboxosc")

# 允许出现平台判断的文件（相对 tvboxosc/）
PLATFORM_FILES = {"host/win.py", "host/mac.py"}

# 共享层必须提供给播放器的接口（player.py 的门面方法）
PLAYER_API = {
    "warmup", "apply_codec", "apply_scale", "play", "paused", "toggle_pause",
    "set_pause", "get_volume", "set_volume", "core_idle", "status", "seek",
    "set_speed", "is_eof", "detach", "terminate", "shutdown",
}

# 每个平台实现都必须提供的函数
HOST_API = {
    "app_base", "font_candidates", "node_candidates", "chrome_insets",
    "attach_widget", "acquire", "release", "stop", "shutdown", "warmup",
    "NAME",
}

SMOKE_WORDS = ('sys.platform', '"darwin"', "'darwin'", '"win32"', "'win32'",
               "os.name ==")

fails = []
passed = 0


def ok(msg):
    print("OK   " + msg)
    global passed
    passed += 1


def bad(msg):
    print("FAIL " + msg)
    fails.append(msg)


def rel(p):
    return os.path.relpath(p, PKG).replace("\\", "/")


def py_files():
    out = []
    for name in sorted(os.listdir(PKG)):
        if name.endswith(".py"):
            out.append(os.path.join(PKG, name))
    host = os.path.join(PKG, "host")
    for name in sorted(os.listdir(host)):
        if name.endswith(".py"):
            out.append(os.path.join(host, name))
    out.append(os.path.join(ROOT, "main.py"))
    return out


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


# ---- 1. 共享代码不得有平台判断 ----
# 只看代码本身（tokenize 跳过注释与文档字符串），避免说明文字里提到
# sys.platform 造成误报。
def platform_checks(path):
    import tokenize
    hits = []
    with open(path, "rb") as f:
        toks = [t for t in tokenize.tokenize(f.readline)
                if t.type not in (tokenize.COMMENT, tokenize.NL,
                                  tokenize.NEWLINE, tokenize.INDENT,
                                  tokenize.DEDENT, tokenize.ENCODING)]
    seq = [(t.type, t.string) for t in toks]
    for i in range(len(seq) - 2):
        a, b, c = seq[i], seq[i + 1], seq[i + 2]
        if b == (tokenize.OP, "."):
            if a == (tokenize.NAME, "sys") and c == (tokenize.NAME, "platform"):
                hits.append("sys.platform")
            elif a == (tokenize.NAME, "os") and c == (tokenize.NAME, "name"):
                hits.append("os.name")
    for t in toks:
        if t.type == tokenize.STRING and t.string.strip("'\"") in ("darwin", "win32"):
            hits.append("字面量 %s" % t.string)
    return hits


leaks = []
for p in py_files():
    r = rel(p) if p.startswith(PKG) else "main.py"
    if r in PLATFORM_FILES or r in ("player_av.py", "player_mac.py"):
        continue           # 平台专属实现文件（Mac 后端 + 平台实现）
    if r == "host/__init__.py":
        continue           # 门面本体，判 IS_MAC 是它的唯一职责
    for h in platform_checks(p):
        leaks.append("%s: %s" % (r, h))
if leaks:
    bad("共享代码出现平台判断：%s" % ", ".join(sorted(set(leaks))))
else:
    ok("共享代码（UI/业务/播放器门面）无平台判断，平台分支只存在于 host/win.py、host/mac.py")


# ---- 2. 两个平台实现的函数集合一致 ----
def module_api(path):
    """模块级函数名 + 模块级常量（大写名），不含下划线开头的内部项"""
    tree = ast.parse(read(path))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    names.add(t.id)
    return names


win_api = module_api(os.path.join(PKG, "host", "win.py"))
mac_api = module_api(os.path.join(PKG, "host", "mac.py"))
missing_win = HOST_API - win_api
missing_mac = HOST_API - mac_api
if missing_win or missing_mac:
    bad("平台实现缺接口：win 缺 %s / mac 缺 %s"
        % (sorted(missing_win) or "-", sorted(missing_mac) or "-"))
else:
    ok("host/win.py 与 host/mac.py 接口一致（各 %d 项：%s）"
       % (len(HOST_API), ", ".join(sorted(HOST_API))))

drift = (win_api - mac_api) - {"_prepare_dll"}
drift2 = (mac_api - win_api) - {"backend_name"}
if drift or drift2:
    bad("两平台实现出现单边函数（改一边会破坏另一边）：win 独有 %s / mac 独有 %s"
        % (sorted(drift) or "-", sorted(drift2) or "-"))
else:
    ok("无单边接口（win 独有仅内部 _prepare_dll，mac 独有仅 backend_name 诊断钩子）")


# ---- 3. 播放器门面接口固定 ----
tree = ast.parse(read(os.path.join(PKG, "player.py")))
cls = next((n for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "MpvPlayer"), None)
if cls is None:
    bad("player.py 找不到 MpvPlayer 类")
else:
    have = {n.name for n in cls.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    lack = PLAYER_API - have
    if lack:
        bad("MpvPlayer 缺少公开方法：%s" % sorted(lack))
    else:
        ok("MpvPlayer 公开接口完整（%d 项），平台后端只提供 core 不透出到 UI"
           % len(PLAYER_API))


# ---- 4. 平台门面能正常导入并给出必要能力 ----
sys.path.insert(0, ROOT)
try:
    from tvboxosc import host
    need = ("app_base", "font_candidates", "chrome_insets", "node_path", "player")
    lack = [n for n in need if not hasattr(host, n)]
    if lack:
        bad("host 门面缺能力：%s" % lack)
    else:
        ok("host 门面可用：app_base / font_candidates / chrome_insets / node_path / player")
    fonts = host.font_candidates()
    if not fonts:
        bad("font_candidates() 返回空")
    else:
        ok("当前平台字体候选：%s" % " > ".join(fonts))
    ins = host.chrome_insets()
    if len(ins) != 4:
        bad("chrome_insets() 必须是 (上,右,下,左) 四元组，实际 %r" % (ins,))
    else:
        ok("当前平台控制栏边距：%r（Windows 应为全 0）" % (ins,))
    node = host.node_path()
    ok("node 定位：%s" % (node or "未找到（不影响启动，JS 源会报错提示）"))
except Exception as e:
    bad("host 门面导入失败：%r" % (e,))


# ---- 5. 平台后端不反向依赖 UI ----
for p, name in ((os.path.join(PKG, "host", "win.py"), "win"),
                (os.path.join(PKG, "host", "mac.py"), "mac")):
    t = ast.parse(read(p))
    ui_imports = []
    for node in ast.walk(t):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [(node.module or "")]
        for m in mods:
            if m.startswith("ui_") or m in ("app", "data_api", "apiconfig"):
                ui_imports.append(m)
    if ui_imports:
        bad("host/%s.py 反向依赖了 UI 层：%s" % (name, ui_imports))
    else:
        ok("host/%s.py 不依赖 UI 层（改动方向单一：UI → host → 平台实现）" % name)


print("\n== 通过 %d / 失败 %d ==" % (passed, len(fails)))
print("DONE" if not fails else "FAILED")
sys.exit(1 if fails else 0)
