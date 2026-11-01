[app]

title = TVBox4Win
package.name = tvbox4win
package.domain = org.lddxmyg

# 源码目录：本工程的 main.py / androidui/ / vendor/（vendor 由 sync_core.py 生成）
source.dir = .
source.include_exts = py,png,jpg,atlas,json
source.exclude_dirs = build, bin, .buildozer, vendor/__pycache__, androidui/__pycache__, __pycache__
source.exclude_patterns = *.spec, sync_core.py, README*.md

version = 0.9.6.1

# kivy 负责界面；requests 供 apiconfig/data_api 发 HTTP（openssl 由 p4a 自动带上）
requirements = python3,kivy==2.3.0,requests,urllib3,certifi,charset-normalizer,idna,openssl

orientation = portrait
fullscreen = 0

# api 33 覆盖 Android 13；minapi 24 = Android 7.0，覆盖面足够
android.api = 33
android.minapi = 24
android.ndk = 25b
# 真机多为 arm64；模拟器（x86_64）需要时再加 x86_64（部分 recipe 不支持）
android.archs = arm64-v8a, armeabi-v7a
android.permissions = INTERNET, ACCESS_NETWORK_STATE
android.accept_sdk_license = True
android.release_artifact = apk
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 1
