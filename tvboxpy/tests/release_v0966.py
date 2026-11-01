# -*- coding: utf-8 -*-
"""发布 v0.9.6.6：**新建** Release，保留 v0.9.6.5 等旧版不变（token 只在内存中）

步骤：
1. 若 v0.9.6.6 的 release 已存在 → 只同步说明；否则 POST 创建（复用已推送的 tag）
2. 上传 TVBox4Win-v0.9.6.6-win64.zip（完整包，缺则跳过）
3. 上传 tvboxpy-runtime-assets.zip（仅 JVM 资产，可复用）
4. 打印资产清单
"""
import os
import subprocess

import requests

REPO = "lddxmyg/TVBox4Win"
TAG = "v0.9.6.6"
NAME = "TVBox4Win v0.9.6.6"
BASE = r"D:\code\tvbox2exe\tvboxpy"
ASSETS = [
    (BASE + r"\dist\TVBox4Win-v0.9.6.6-win64.zip", "TVBox4Win-v0.9.6.6-win64.zip"),
    (BASE + r"\tvboxpy-runtime-assets.zip", "tvboxpy-runtime-assets.zip"),
]

BODY = r"""TVBox4Win v0.9.6.6 — 下载即用版（Windows 64 位）

> ⚠️ **强烈建议先安装 Java 环境（JDK 17+）**：现代影视源大多是 Jar 爬虫站点，
> 不装 Java 这些源会打不开（报「未找到 java 运行时」）。
> 请安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)，
> JS 爬虫站点还需 [Node.js](https://nodejs.org/) 16+。

## 📦 TVBox4Win-v0.9.6.6-win64.zip（推荐，解压即玩）

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

## 本版更新（v0.9.6.6）

### 🎬 弹幕与二维码

- **弹幕播放**：支持 XML（B 站格式）、JSON、纯文本弹幕源，自动解析并在播放页合成 ASS 字幕叠加显示
- **纯 Python 二维码**：推送页直接生成手机扫码地址，不依赖额外库
- 推送页新增「📋 剪贴板推送」「🔗 复制服务地址」

### 📺 直播增强

- m3u 扩展：`group-title` 分组、`group-password` 加密分组、`#EXTVLCOPT` / 管道请求头
- 回看（catchup）模板解析，节目单可直接回看
- txt 直播源同样支持管道请求头

### 🗂 首页 / 搜索 / 历史 / 收藏

- 首页支持 `vod_tag` **文件夹下钻**与**动作条目**，分类可再加「加载更多」翻页
- 豆瓣推荐改用新接口并支持**年份筛选**（记住上次选择）
- 可设置**首页壁纸**（内置渐变或自定义图片）
- 搜索只请求支持搜索的站源，「快速搜索」开关控制是否扩展关键词
- 历史页改为**海报网格**：显示「源 · 上次看到第 N 集」、多选删除、清空二次确认；源失效时自动按片名重新搜索
- 收藏页改为海报网格，右键取消收藏

### ⚙️ 设置页

- 设置卡片增加到 31 项并支持滚动：画面缩放（6 种）、字幕字号、默认倍速、解码方式、历史上限、防休眠、播放缓存、历史合并、直播倒序、弹幕与弹幕源、自动换线/自动播放等
- 新增**数据备份 / 恢复**（观看历史 + 设置打包为 zip）
- 新增开发者工具：查看日志、打开数据目录、清空缓存

### 📡 推送服务接口

- 新增 `/action`（远程触发首页/直播/点播/搜索/清空）、`/upload`（手机上传文件）、`/file` `/media`（局域网取文件，防目录穿越）、`/dns-query`（DoH 转发）、`/proxyM3u8`（m3u8 本地改写）、`/cache`（图床缓存管理）

---

## 📚 历史版本（各自独立保留）

| 版本 | 主要变化 |
|---|---|
| **v0.9.6.6**（本版） | 弹幕播放 / 二维码推送 / EPG 回看 / 直播 m3u 扩展 / 首页文件夹与翻页 / 历史收藏海报页 / 31 项设置 / 推送服务新接口 |
| [v0.9.6.5](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.5) | 加密配置（Base64 / 2423 / `;pk;`）+ clan/本地配置 + 相对路径解析；启动失败可重试/更换配置、缓存回退提示 |
| [v0.9.6.4](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.4) | 播放失败自动重试/换线 + `lives[]` type=3 爬虫直播源 |
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
