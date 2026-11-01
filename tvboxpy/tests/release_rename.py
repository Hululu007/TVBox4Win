# -*- coding: utf-8 -*-
"""Release v0.9.1 更名为 TVBox4Win：替换主附件与说明（token 只在内存中）"""
import subprocess

import requests

REPO = "lddxmyg/TVBox4Win"
TAG = "v0.9.1"
ASSET = r"D:\code\tvbox2exe\tvboxpy\TVBox4Win-v0.9.1-win64.zip"

BODY = """TVBox4Win v0.9.1 — 下载即用版（Windows 64 位）

**TVBox4Win** = TVBox for Windows：安卓 TV 影视聚合播放器 TVBox 的 Windows 桌面复刻。

## 📦 TVBox4Win-v0.9.1-win64.zip（推荐，解压即玩）

包含完整运行环境，**无需安装 Python / mpv**：

```
TVBox4Win.exe        主程序（libmpv 播放内核已内嵌）
jvmrt/               Jar 爬虫运行时
dex-tools-v2.4/      dex→jar 转换工具链
```

**使用方法**：解压到任意可写目录 → 双击 `TVBox4Win.exe`。

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

    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}", headers=h)
    r.raise_for_status()
    rel = r.json()

    r = requests.patch(f"https://api.github.com/repos/{REPO}/releases/{rel['id']}",
                       headers=h, json={"name": "TVBox4Win v0.9.1", "body": BODY})
    r.raise_for_status()
    rel = r.json()
    print("release:", rel["html_url"])

    for a in rel.get("assets", []):
        if a["name"] == "tvboxpy-v0.9.1-win64.zip":
            d = requests.delete(f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}", headers=h)
            print("old asset deleted:", d.status_code)

    upload = rel["upload_url"].split("{")[0]
    with open(ASSET, "rb") as f:
        r = requests.post(upload, headers={**h, "Content-Type": "application/zip"},
                          params={"name": "TVBox4Win-v0.9.1-win64.zip"}, data=f)
    r.raise_for_status()
    print("uploaded:", r.json()["browser_download_url"])


if __name__ == "__main__":
    main()
