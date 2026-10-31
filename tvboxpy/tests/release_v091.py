# -*- coding: utf-8 -*-
"""把现有 Release 改版为 v0.9.1 并上传完整可玩包（token 只在内存中）"""
import subprocess

import requests

REPO = "lddxmyg/TVBox4Win"
OLD_TAG = "v1.0.0"
NEW_TAG = "v0.9.1"
ASSET = r"D:\code\tvbox2exe\tvboxpy\tvboxpy-v0.9.1-win64.zip"

BODY = """tvboxpy v0.9.1 — 下载即用版（Windows 64 位）

## 📦 tvboxpy-v0.9.1-win64.zip（推荐，解压即玩）

包含完整运行环境，**无需安装 Python / mpv**：

```
tvboxpy.exe          主程序（libmpv 播放内核已内嵌）
jvmrt/               Jar 爬虫运行时
dex-tools-v2.4/      dex→jar 转换工具链
```

**使用方法**：解压到任意可写目录 → 双击 `tvboxpy.exe`。

- CMS 类站点开箱即用；JS 爬虫站点需本机安装 Node.js
- Jar 爬虫站点需本机安装 JDK 17+（本包已含 jvmrt 资产）
- 首次运行可能被 SmartScreen 拦截：点「更多信息 → 仍要运行」
- 详细说明见仓库 [README](https://github.com/lddxmyg/TVBox4Win#readme)

## 🧩 tvboxpy-runtime-assets.zip

仅含 JVM 运行时资产（jvmrt + dex-tools），适合自行从源码打包的用户。
"""


def get_token():
    r = subprocess.run(["git", "credential", "fill"],
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

    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{OLD_TAG}", headers=h)
    r.raise_for_status()
    rel = r.json()

    r = requests.patch(f"https://api.github.com/repos/{REPO}/releases/{rel['id']}",
                       headers=h, json={"tag_name": NEW_TAG, "target_commitish": "main",
                                        "name": "tvboxpy v0.9.1", "body": BODY})
    r.raise_for_status()
    rel = r.json()
    print("release now:", rel["html_url"])

    # 删除旧 tag 引用
    d = requests.delete(f"https://api.github.com/repos/{REPO}/git/refs/tags/{OLD_TAG}", headers=h)
    print("old tag removed:", d.status_code in (200, 204, 404))

    upload = rel["upload_url"].split("{")[0]
    names = [a["name"] for a in rel.get("assets", [])]
    if "tvboxpy-v0.9.1-win64.zip" not in names:
        with open(ASSET, "rb") as f:
            r = requests.post(upload, headers={**h, "Content-Type": "application/zip"},
                              params={"name": "tvboxpy-v0.9.1-win64.zip"}, data=f)
        r.raise_for_status()
        print("uploaded:", r.json()["browser_download_url"])
    else:
        print("asset already uploaded")


if __name__ == "__main__":
    main()
