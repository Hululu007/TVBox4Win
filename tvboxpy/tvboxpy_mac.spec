# -*- mode: python ; coding: utf-8 -*-
"""macOS 打包配置（PyInstaller）

用法（在 tvboxpy/ 目录下）：
    ../.venv/bin/pyinstaller tvboxpy_mac.spec --noconfirm
产物：dist/TVBox4Win.app
"""
import os
import re
import sysconfig

PREFIX = sysconfig.get_config_var("prefix") or ""

# 版本号跟随 tvboxosc/__init__.py 的 VERSION，发版时不用再改本文件
with open(os.path.join("tvboxosc", "__init__.py"), encoding="utf-8") as _f:
    VER = re.search(r'VERSION\s*=\s*"([^"]+)"', _f.read()).group(1)

hidden = [
    "tvboxosc.ui_grid", "tvboxosc.ui_search", "tvboxosc.ui_history",
    "tvboxosc.ui_collect", "tvboxosc.ui_detail", "tvboxosc.ui_play",
    "tvboxosc.ui_live", "tvboxosc.ui_push", "tvboxosc.ui_setting",
    "tvboxosc.spider", "tvboxosc.spider_runtime", "tvboxosc.player",
    "tvboxosc.player_av", "tvboxosc.player_mac", "tvboxosc.imgcache",
    "tvboxosc.store", "tvboxosc.theme", "tvboxosc.data_api", "tvboxosc.hawk",
    "tvboxosc.apiconfig", "tvboxosc.ui_thread", "tvboxosc.app",
    "tvboxosc.epg", "tvboxosc.jar_spider", "tvboxosc.py_spider",
    "requests", "PIL.Image", "PIL.ImageTk",
    # PyObjC：AVFoundation 播放后端
    "objc", "AppKit", "Foundation", "AVFoundation", "CoreMedia", "Quartz",
]

datas = [
    ("tvboxosc/spider_runtime", "tvboxosc/spider_runtime"),
    ("tvboxosc/assets", "tvboxosc/assets"),
]

# uv 的 python-build-standalone 用 Tcl/Tk 9.0，目录名不是 PyInstaller 默认的 8.6
for _name in ("tcl9.0", "tk9.0", "tcl9", "tk8.6", "tk8.6"):
    _p = os.path.join(PREFIX, "lib", _name)
    if PREFIX and os.path.isdir(_p):
        datas.append((_p, os.path.join("lib", _name)))

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["rthook_tcl.py"],
    excludes=["pytest", "numpy", "matplotlib"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TVBox4Win",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",
    icon="../build/tvbox4win.icns",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="TVBox4Win",
)

app = BUNDLE(
    coll,
    name="TVBox4Win.app",
    icon="../build/tvbox4win.icns",
    bundle_identifier="com.tvbox4win.mac",
    version=VER,
    info_plist={
        "CFBundleName": "TVBox4Win",
        "CFBundleDisplayName": "TVBox4Win",
        "CFBundleShortVersionString": VER,
        "CFBundleVersion": VER,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.entertainment",
        # 影视源大量走 http，必须放开 ATS，否则全部被系统拦掉
        "NSAppTransportSecurity": {
            "NSAllowsArbitraryLoads": True,
            "NSAllowsArbitraryLoadsInWebContent": True,
            "NSAllowsLocalNetworking": True,
        },
    },
)
