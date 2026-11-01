# -*- coding: utf-8 -*-
"""发布 v0.9.4：**新建** Release，保留 v0.9.3 不变（token 只在内存中）

与 v0.9.2 / v0.9.3 的脚本不同：这次不再 PATCH 旧 release、也不再删旧 tag/资产，
而是为每个版本单独建一个 Release，历史版本各自保留、各自可下载。

步骤：
1. 若 v0.9.4 的 release 不存在 → POST 创建（tag 指向 main 最新提交）
2. 上传 TVBox4Win-v0.9.4-win64.zip（完整包）
3. 上传 tvboxpy-runtime-assets.zip（仅 JVM 资产，可复用）
4. 打印资产清单
"""
import subprocess

import requests

REPO = "lddxmyg/TVBox4Win"
TAG = "v0.9.4"
NAME = "TVBox4Win v0.9.4"
BASE = r"D:\code\tvbox2exe\tvboxpy"
ASSETS = [
    (BASE + r"\dist\TVBox4Win-v0.9.4-win64.zip", "TVBox4Win-v0.9.4-win64.zip"),
    (BASE + r"\tvboxpy-runtime-assets.zip", "tvboxpy-runtime-assets.zip"),
]

BODY = r"""TVBox4Win v0.9.4 — 下载即用版（Windows 64 位）

> ⚠️ **强烈建议先安装 Java 环境（JDK 17+）**：现代影视源大多是 Jar 爬虫站点，
> 不装 Java 这些源会打不开（报「未找到 java 运行时」）。
> 请安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)，
> JS 爬虫站点还需 [Node.js](https://nodejs.org/) 16+。

## 📦 TVBox4Win-v0.9.4-win64.zip（推荐，解压即玩）

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

---

## 本版更新（v0.9.4）

本版把**直播**整块重做了一遍：从「只有一个频道列表」升级为对齐原版
`LivePlayActivity` 的完整直播页，并补上了节目单。

### 🆕 直播页整页重构（对齐原版 `activity_live_play.xml`）
- **左侧两层列表浮层**：分组列（176px）+ 频道列（300px），Canvas 滚动，频道上百也不卡
- **进入即自动播放**：上次观看频道 → CCTV1 → 第一组第一个（对齐原版 `initLiveState`）
- **键盘导航**：↑↓ 列表内移动（跨组自动切组并播放、频道移动即换台）、←→ 切换列、
  Prior/Next 跨组换台、数字键直接选台、R 换源、Esc 先收列表再退出
- **右上角大号台标** + 底部状态行（信号源 / 线路）
- 列表 **5 秒自动隐藏**，鼠标移动或按键唤出；操作时不重建控件，避免焦点丢失

### 🐞 直播退出入口补齐（修复「Esc 永远退不出」卡死）
- 修复真正的 bug：Esc 处理先唤出列表，`_back()` 见列表可见就只收起 → 一直退不回首页
- **顶栏常驻「← 返回」按钮**（46px，含状态文本 + 实时时钟）
- **底部悬浮控制栏**：⏸暂停 / ⏮⏭上下一台 / ⇄换源 / ☰频道列表 / ⛶全屏 / ✕退出直播，
  右对齐不遮挡列表，与列表同步 5 秒隐藏
- 新增 `P` 暂停、`F` 全屏快捷键；鼠标点在面板内只重置隐藏计时，不会把已收起的列表弹回

### 🆕 全局频道编号 + 节目单（EPG）
- 频道列表显示**全局台号**，与数字键选台序号完全一致
- 新增 `tvboxosc/epg.py`：支持 **XMLTV** 与 **JSON** 两种节目单格式，
  台名归一化（自动剥「高清 / HD」等后缀）、30 分钟缓存、支持 `{name}` / `{date}` 模板 URL，
  内置默认 diyp 接口
- EPG 地址自动识别：m3u 头 `x-tvg-url` / `tvg-url` / `url-tvg`、接口配置 `lives[].epg`、设置 `epg_url`
- 底部控制栏上行显示节目单：**橙色台号 + 台名 + 线路 + 当前节目 ▶ + 下一个节目 + 时段**，
  每分钟用已取数据重算，节目到点自动换行

### ♻️ 其它
- 版本号升级至 0.9.4（窗口标题 / 设置 → 关于 / README 同步）

---

## 📚 历史版本（各自独立保留）

| 版本 | 主要变化 |
|---|---|
| **v0.9.4**（本版） | 直播页整页重构、退出入口修复、全局台号 + EPG 节目单 |
| [v0.9.3](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.3) | 自定义直播源（点播/直播双输入、直播历史、txt/m3u/JSON 解析）、全新应用图标 |
| [v0.9.2](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.2) | 应用图标 + 版本号体系 |

想留在旧版就从上面的版本链接下载对应 zip，每个 Release 的附件互不覆盖。
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
        # 说明可能更新过，同步一遍
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
