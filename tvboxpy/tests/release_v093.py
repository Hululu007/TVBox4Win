# -*- coding: utf-8 -*-
"""把现有 Release 改版为 v0.9.3 并上传完整可玩包（token 只在内存中）

步骤：
1. 找到 tag v0.9.2 的 release
2. PATCH 为 v0.9.3（tag 指向 main 最新，GitHub 会自动建新 tag）
3. 删除旧 tag 引用 v0.9.2、删除旧资产 TVBox4Win-v0.9.2-win64.zip
4. 上传 TVBox4Win-v0.9.3-win64.zip（runtime-assets.zip 保留复用）
"""
import subprocess

import requests

REPO = "lddxmyg/TVBox4Win"
OLD_TAG = "v0.9.2"
NEW_TAG = "v0.9.3"
OLD_ASSET = "TVBox4Win-v0.9.2-win64.zip"
NEW_ASSET = "TVBox4Win-v0.9.3-win64.zip"
ASSET = r"D:\code\tvbox2exe\tvboxpy\dist" + "\\" + NEW_ASSET

BODY = """TVBox4Win v0.9.3 — 下载即用版（Windows 64 位）

> ⚠️ **强烈建议先安装 Java 环境（JDK 17+）**：现代影视源大多是 Jar 爬虫站点，
> 不装 Java 这些源会打不开（报「未找到 java 运行时」）。
> 请安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)，
> JS 爬虫站点还需 [Node.js](https://nodejs.org/) 16+。

## 📦 TVBox4Win-v0.9.3-win64.zip（推荐，解压即玩）

包含完整运行环境，**无需安装 Python / mpv**：

```
TVBox4Win.exe        主程序（libmpv 播放内核已内嵌，全新应用图标）
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

## 本版更新（v0.9.3）

### 🆕 自定义直播源（对齐原版 ApiDialog）
- 设置 → 配置地址弹窗改为**双输入**：「点播」配置地址 + 「直播」直播源地址
- 新增「直播地址」设置卡片，实时显示当前直播源（未设置显示「跟随配置」）
- 新增「直播历史」，保存过的直播源一键切换（上限 10 条）
- 直播源支持 txt（`分组,#genre#`）/ m3u / m3u8 / 含 `lives` 的 TVBox 配置 / 单源 JSON / 本地文件
- 保存后自动校验并提示解析到的频道数；直播页优先用自定义源，失败自动回落到接口配置

### ♻️ 其它
- 全新自绘应用图标（EXE 图标 + 窗口图标）
- 版本号升级至 0.9.3
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
                                        "name": f"TVBox4Win {NEW_TAG}", "body": BODY})
    r.raise_for_status()
    rel = r.json()
    print("release now:", rel["html_url"])

    d = requests.delete(f"https://api.github.com/repos/{REPO}/git/refs/tags/{OLD_TAG}", headers=h)
    print("old tag removed:", d.status_code in (200, 204, 404))

    old = [a for a in rel.get("assets", []) if a["name"] == OLD_ASSET]
    if old:
        dr = requests.delete(
            f"https://api.github.com/repos/{REPO}/releases/assets/{old[0]['id']}", headers=h)
        print("old asset removed:", dr.status_code in (200, 204))

    upload = rel["upload_url"].split("{")[0]
    names = [a["name"] for a in rel.get("assets", [])]
    if NEW_ASSET not in names:
        with open(ASSET, "rb") as f:
            r = requests.post(upload, headers={**h, "Content-Type": "application/zip"},
                              params={"name": NEW_ASSET}, data=f)
        r.raise_for_status()
        print("uploaded:", r.json()["browser_download_url"])
    else:
        print("asset already uploaded")

    # 最终资产清单
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{NEW_TAG}", headers=h)
    for a in r.json().get("assets", []):
        print("  asset:", a["name"], round(a["size"] / 1048576, 1), "MB")


if __name__ == "__main__":
    main()
