# -*- coding: utf-8 -*-
"""发布 v0.9.6.4：**新建** Release，保留 v0.9.6.3 / v0.9.6.2 等旧版不变（token 只在内存中）

步骤：
1. 若 v0.9.6.4 的 release 已存在 → 只同步说明；否则 POST 创建（复用已推送的 tag）
2. 上传 TVBox4Win-v0.9.6.4-win64.zip（完整包，缺则跳过）
3. 上传 tvboxpy-runtime-assets.zip（仅 JVM 资产，可复用）
4. 打印资产清单
"""
import os
import subprocess

import requests

REPO = "lddxmyg/TVBox4Win"
TAG = "v0.9.6.4"
NAME = "TVBox4Win v0.9.6.4"
BASE = r"D:\code\tvbox2exe\tvboxpy"
ASSETS = [
    (BASE + r"\dist\TVBox4Win-v0.9.6.4-win64.zip", "TVBox4Win-v0.9.6.4-win64.zip"),
    (BASE + r"\tvboxpy-runtime-assets.zip", "tvboxpy-runtime-assets.zip"),
]

BODY = r"""TVBox4Win v0.9.6.4 — 下载即用版（Windows 64 位）

> ⚠️ **强烈建议先安装 Java 环境（JDK 17+）**：现代影视源大多是 Jar 爬虫站点，
> 不装 Java 这些源会打不开（报「未找到 java 运行时」）。
> 请安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)，
> JS 爬虫站点还需 [Node.js](https://nodejs.org/) 16+。

## 📦 TVBox4Win-v0.9.6.4-win64.zip（推荐，解压即玩）

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

---

## 本版更新（v0.9.6.4）

### 🔁 播放失败自动重试与换线

以前播放地址解析失败、或者播放器迟迟起不来时，只能停在「正在获取播放信息…」，
需要用户自己返回重进。现在：

- 同一线路自动重试 1 次（解析超时 / 起播超时 20 秒都会触发）
- 仍失败则自动切到其它线路的同一集，逐条尝试
- 全部线路都失败后，状态栏显示可点击的 `⚠ 播放失败（原因），点击重试`
- 切换线路时自动跳转到对应集数，不会回到第一集
- 异步解析结果带序号校验，快速换集/换线时旧结果不会覆盖新播放

### 📡 支持爬虫直播源（lives[] type=3）

接口配置里 `lives` 的类型 3（由 py/js/jar 爬虫提供频道列表）现在可以直接使用：

- 调爬虫的 `liveContent(url)` 获取频道，兼容 JSON 数组、m3u、txt 三种返回格式
- 频道多线路、分组、每频道请求头（`header`）均已支持，请求头会传给 mpv
- `lives[].epg` 节目单地址同样生效；爬虫源失败会自动尝试下一个直播源
- 原有 txt/m3u 直播源行为不变

> 已知限制：JS 直播源需要站点自身实现 `live()`；仅配置 `jar` 字段而 `api`
> 不是 `csp_` 类名的直播条目无法确定爬虫类，会自动跳过。

---

## 📚 历史版本（各自独立保留）

| 版本 | 主要变化 |
|---|---|
| **v0.9.6.4**（本版） | 播放失败自动重试/换线 + `lives[]` type=3 爬虫直播源 |
| [v0.9.6.3](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.3) | 修 Jar 爬虫「分类加载失败」（关闭 JVM 字节码校验）、错误提示可读化 + 点击重试 |
| [v0.9.6.2](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.2) | 解析链路对齐原版（parse type 全语义、hosts/嗅探规则、本地 `/proxy`、py `localProxy`） |
| [v0.9.6.1](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.1) | 平台层重构（`host/`）、Windows 包瘦身 3.3MB、平台隔离 + 离线播放测试 |
| [v0.9.6](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6) | macOS 原生支持（AVFoundation 后端、`.app` 打包、苹方字体） |
| [v0.9.5](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.5) | 海报网格自适应窗口宽度、原版 244:320 比例、片名叠加海报底部、按钮均分整行 |

想留在旧版就从上面的版本链接下载对应包，每个 Release 的附件互不覆盖。
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
    if r.status_code == 200:
        rel = r.json()
        print("release exists:", rel["html_url"])
        r = requests.patch(f"https://api.github.com/repos/{REPO}/releases/{rel['id']}",
                           headers=h, json={"name": NAME, "body": BODY})
        r.raise_for_status()
        rel = r.json()
    else:
        r = requests.post(f"https://api.github.com/repos/{REPO}/releases",
                          headers=h, json={
                              "tag_name": TAG,
                              "target_commitish": "main",
                              "name": NAME,
                              "body": BODY,
                              "draft": False,
                              "prerelease": False,
                          })
        r.raise_for_status()
        rel = r.json()
        print("created:", rel["html_url"])

    upload = rel["upload_url"].split("{")[0]
    names = [a["name"] for a in rel.get("assets", [])]
    for path, name in ASSETS:
        if name in names:
            print("skip (exists):", name)
            continue
        if not os.path.isfile(path):
            print("missing, skipped:", path)
            continue
        with open(path, "rb") as f:
            r = requests.post(upload,
                              headers={**h, "Content-Type": "application/zip"},
                              params={"name": name}, data=f)
        r.raise_for_status()
        print("uploaded:", name, r.json()["browser_download_url"])

    r = requests.get(f"https://api.github.com/repos/{REPO}/releases", headers=h)
    print("== 远端 release 清单 ==")
    for rel in r.json():
        print(" -", rel["tag_name"], "|", len(rel["assets"]), "assets")
        for a in rel["assets"]:
            print("     ", a["name"], round(a["size"] / 1048576, 1), "MB")


if __name__ == "__main__":
    main()
