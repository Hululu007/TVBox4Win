# -*- coding: utf-8 -*-
"""创建 GitHub Release 并上传运行资产（token 只在内存中使用，不打印）"""
import json
import subprocess
import sys

import requests

REPO = "lddxmyg/TVBox4Win"
TAG = "v1.0.0"
ASSET = r"D:\code\tvbox2exe\tvboxpy\tvboxpy-runtime-assets.zip"

BODY = """tvboxpy v1.0.0 首个发布

## 附件说明

**tvboxpy-runtime-assets.zip**（57 MB）—— Jar 爬虫站点运行时资产，与 EXE 同目录放置：

- `jvmrt/`：JVM 桥运行时（stubs.jar / native-bridge.jar / spiderrunner.jar / libs）
- `dex-tools-v2.4/`：dex→jar 转换工具链

## 使用方法

1. 从 Actions 或自行运行 `python build_exe.py` 得到 `tvboxpy.exe`（或直接使用 `dist/` 产物）
2. 将本压缩包解压到 `tvboxpy.exe` 同目录，目录结构：

```
your-dir/
├── tvboxpy.exe
├── jvmrt/
├── dex-tools-v2.4/
└── (third_party/mpv/libmpv-2.dll 已内嵌于 EXE，无需单独下载)
```

3. 需要 JDK 17+（java 在 PATH 中）

## 源码运行

见仓库 [README.md](https://github.com/lddxmyg/TVBox4Win#readme)。
"""


def get_token():
    r = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise RuntimeError("no credential found")


def main():
    tok = get_token()
    h = {"Authorization": "token " + tok,
         "Accept": "application/vnd.github+json"}

    # 已有同名 release 则复用
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}", headers=h)
    if r.status_code == 200:
        rel = r.json()
        print("release exists:", rel["html_url"])
    else:
        r = requests.post(f"https://api.github.com/repos/{REPO}/releases",
                          headers=h, json={
                              "tag_name": TAG, "target_commitish": "main",
                              "name": "tvboxpy v1.0.0", "body": BODY})
        r.raise_for_status()
        rel = r.json()
        print("created:", rel["html_url"])

    upload = rel["upload_url"].split("{")[0]
    names = [a["name"] for a in rel.get("assets", [])]
    if "tvboxpy-runtime-assets.zip" not in names:
        with open(ASSET, "rb") as f:
            r = requests.post(upload, headers={**h, "Content-Type": "application/zip"},
                              params={"name": "tvboxpy-runtime-assets.zip"}, data=f)
        r.raise_for_status()
        print("uploaded:", r.json()["browser_download_url"])
    else:
        print("asset already uploaded")


if __name__ == "__main__":
    main()
