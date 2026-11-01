# -*- coding: utf-8 -*-
"""发布 v0.9.6.1：**新建** Release，保留 v0.9.3 / v0.9.4 / v0.9.5 不变（token 只在内存中）

步骤：
1. 若 v0.9.6.1 的 release 已存在 → 只同步说明；否则 POST 创建（复用已推送的 tag）
2. 上传 TVBox4Win-v0.9.6.1-win64.zip（完整包，缺则跳过）
3. 上传 tvboxpy-runtime-assets.zip（仅 JVM 资产，可复用）
4. 打印资产清单
"""
import os
import subprocess

import requests

REPO = "lddxmyg/TVBox4Win"
TAG = "v0.9.6.1"
NAME = "TVBox4Win v0.9.6.1"
BASE = r"D:\code\tvbox2exe\tvboxpy"
ASSETS = [
    (BASE + r"\dist\TVBox4Win-v0.9.6.1-win64.zip", "TVBox4Win-v0.9.6.1-win64.zip"),
    (BASE + r"\tvboxpy-runtime-assets.zip", "tvboxpy-runtime-assets.zip"),
]

BODY = r"""TVBox4Win v0.9.6.1 — 下载即用版（Windows 64 位）

> ⚠️ **强烈建议先安装 Java 环境（JDK 17+）**：现代影视源大多是 Jar 爬虫站点，
> 不装 Java 这些源会打不开（报「未找到 java 运行时」）。
> 请安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)，
> JS 爬虫站点还需 [Node.js](https://nodejs.org/) 16+。

## 📦 TVBox4Win-v0.9.6.1-win64.zip（推荐，解压即玩）

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

## 本版更新（v0.9.6.1）

这一版是**工程结构修复**，功能行为与 v0.9.5 一致，但把 Windows 与 macOS
的差异彻底隔离开，从此两个平台的改动互不影响。

### 🧱 新增平台层 `tvboxosc/host/`

以前平台判断（`sys.platform`）散落在播放器、路径、字体、node 查找等多处，
改 Windows 一不小心就会踩到 macOS 的逻辑。现在集中为一层：

```
UI / 业务代码            ← 零平台判断（只能 from .host import …）
      │
tvboxosc/host/__init__.py ← 唯一的平台判定点（门面）
      ├── host/win.py     Windows：libmpv 单例 + wid 嵌入、数据存 EXE 目录、雅黑
      └── host/mac.py     macOS：AVFoundation / 独立 mpv 进程、Application Support、苹方
```

- `player.py` 变成薄门面（17 个公开接口不变），只做播放控制，不含任何平台分支
- 规则：**改 Windows 只碰 `host/win.py`，改 macOS 只碰 `host/mac.py`**

### 📦 安装包瘦身 3.3MB

之前 Windows 包里被 PyInstaller 误打进了 macOS 播放后端（静态分析会跟踪条件
import），导致 exe 从 67.7MB 涨到 71.0MB，还带几条 AppKit 缺失警告。
现在两个平台的打包配置互相排除对侧后端：Windows 包回到 **67.7MB**，警告清零。

### 🧪 两份新的自动化测试（防回归）

- `tests/verify_platform_isolation.py`：静态断言「共享代码不得出现平台判断」、
  「两个平台实现接口必须一致」、「播放器公开接口固定」——
  以后某一平台加了功能却漏了另一边，测试直接失败
- `tests/verify_playback_backend.py`：用 mpv 的 lavfi 本地测试信号走完整播放页，
  验证出画面 / 暂停 / seek / 倍速音量 / 切页，**不需要网络**，断网也能自查

### ♻️ 其它

- 修掉 macOS 分支里误放的 Windows node 路径（复制粘贴残留）
- 版本号升级至 0.9.6.1（支持四段式补丁版本号）

---

## 📚 历史版本（各自独立保留）

| 版本 | 主要变化 |
|---|---|
| **v0.9.6.1**（本版） | 平台层重构（`host/`）、Windows 包瘦身 3.3MB、平台隔离 + 离线播放测试 |
| [v0.9.6](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6) | macOS 原生支持（AVFoundation 后端、`.app` 打包、苹方字体） |
| [v0.9.5](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.5) | 海报网格自适应窗口宽度、原版 244:320 比例、片名叠加海报底部、按钮均分整行 |
| [v0.9.4](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.4) | 直播页整页重构、退出入口修复、全局台号 + EPG 节目单 |
| [v0.9.3](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.3) | 自定义直播源（点播/直播双输入、直播历史、txt/m3u/JSON 解析） |

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
