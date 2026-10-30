# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[('third_party/mpv/libmpv-2.dll', '.')],
    datas=[
        ('tvboxosc/spider_runtime', 'tvboxosc/spider_runtime'),
        ('tvboxosc/assets', 'tvboxosc/assets'),
    ],
    hiddenimports=[
        'tvboxosc.ui_grid', 'tvboxosc.ui_search', 'tvboxosc.ui_history',
        'tvboxosc.ui_collect', 'tvboxosc.ui_detail', 'tvboxosc.ui_play',
        'tvboxosc.ui_live', 'tvboxosc.ui_push', 'tvboxosc.ui_setting',
        'tvboxosc.spider', 'tvboxosc.player', 'tvboxosc.imgcache', 'tvboxosc.store',
        'tvboxosc.theme', 'tvboxosc.data_api', 'tvboxosc.hawk',
        'tvboxosc.apiconfig', 'tvboxosc.ui_thread', 'tvboxosc.app',
        'mpv', 'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='tvboxpy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
