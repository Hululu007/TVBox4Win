# -*- coding: utf-8 -*-
"""发布 v0.9.5：**新建** Release，保留 v0.9.2 / v0.9.3 / v0.9.4 不变（token 只在内存中）

步骤：
1. 若 v0.9.5 的 release 已存在 → 只同步说明；否则 POST 创建（tag 指向 main 最新提交）
2. 上传 TVBox4Win-v0.9.5-win64.zip（完整包，缺则跳过）
3. 上传 tvboxpy-runtime-assets.zip（仅 JVM 资产，可复用）
4. 打印资产清单
"""
import os
import subprocess

import requests

REPO = "lddxmyg/TVBox4Win"
TAG = "v0.9.5"
NAME = "TVBox4Win v0.9.5"
BASE = r"D:\code\tvbox2exe\tvboxpy"
ASSETS = [
    (BASE + r"\dist\TVBox4Win-v0.9.5-win64.zip", "TVBox4Win-v0.9.5-win64.zip"),
    (BASE + r"\tvboxpy-runtime-assets.zip", "tvboxpy-runtime-assets.zip"),
]

BODY = r"""TVBox4Win v0.9.5 — 下载即用版（Windows 64 位）

> ⚠️ **强烈建议先安装 Java 环境（JDK 17+）**：现代影视源大多是 Jar 爬虫站点，
> 不装 Java 这些源会打不开（报「未找到 java 运行时」）。
> 请安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)，
> JS 爬虫站点还需 [Node.js](https://nodejs.org/) 16+。

## 📦 TVBox4Win-v0.9.5-win64.zip（推荐，解压即玩）

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

## 本版更新（v0.9.5）

本版专治**点播页布局**：之前海报固定 6 列、图片偏小，宽窗口下右侧一大片空白。
这次按安卓原版的网格逻辑重做，并逐帧对照原版（逍遥模拟器 1600×900 实机截图）校准。

### 🆕 海报网格自适应窗口宽度
- 列数按可用宽度自动计算（单格 200~320px），**每行均分整行宽度** → 右侧留白彻底消除
- 1280×720 窗口 = **5 列 / 海报 238px**（原版 1600 屏同为 5 列）；拉到 1720 宽自动变 6 列
- 拖拽窗口大小后 **350ms 防抖自动重排**，用已加载数据重画，不重新请求网络
- 分类网格补上**方向键焦点导航**（之前只有首页推荐位可以按方向键移动）

### 🎨 海报与文字对齐原版 `item_grid`
- 海报比例改为原版 `ImgUtil` 的 **244:320**（此前 2:3 偏瘦长），更方正饱满
- 海报按**目标像素精确出图**（PIL LANCZOS 等比缩放 + 居中裁边），按尺寸分别缓存，
  不再用整数倍 subsample，图片更清晰不变形
- **片名 / 备注（评分、已完结、更新至 xx 集）叠加在海报底部深色条**上，
  和原版一样不额外占用下方空间，一屏能多排一行
- 焦点框改为 3px 品牌蓝（原版 TV 端蓝色高亮）
- 首页功能按钮排（历史 / 直播 / 搜索 / 推送 / 收藏 / 设置）改为**大按钮均分整行**

### 🔍 搜索页同步
- 搜索结果卡片同样自适应列数并铺满结果区（1280 宽 → 4 列 / 237px）
- 搜索卡片保留「片名 + 源名」在海报下方的样式（对应原版 `item_search`，
  和分类网格的叠加样式本就是两种不同布局）
- 窗口尺寸变化后按新宽度重排，不重搜

### ♻️ 其它
- 版本号升级至 0.9.5（窗口标题 / 设置 → 关于 / README 同步）

---

## 📚 历史版本（各自独立保留）

| 版本 | 主要变化 |
|---|---|
| **v0.9.5**（本版） | 海报网格自适应窗口宽度、原版 244:320 比例、片名叠加海报底部、按钮均分整行 |
| [v0.9.4](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.4) | 直播页整页重构、退出入口修复、全局台号 + EPG 节目单 |
| [v0.9.3](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.3) | 自定义直播源（点播/直播双输入、直播历史、txt/m3u/JSON 解析） |
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
