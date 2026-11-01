# -*- coding: utf-8 -*-
"""发布 v0.9.6.2：**新建** Release，保留 v0.9.6.1 / v0.9.6 / v0.9.5 不变（token 只在内存中）

步骤：
1. 若 v0.9.6.2 的 release 已存在 → 只同步说明；否则 POST 创建（复用已推送的 tag）
2. 上传 TVBox4Win-v0.9.6.2-win64.zip（完整包，缺则跳过）
3. 上传 tvboxpy-runtime-assets.zip（仅 JVM 资产，可复用）
4. 打印资产清单
"""
import os
import subprocess

import requests

REPO = "lddxmyg/TVBox4Win"
TAG = "v0.9.6.2"
NAME = "TVBox4Win v0.9.6.2"
BASE = r"D:\code\tvbox2exe\tvboxpy"
ASSETS = [
    (BASE + r"\dist\TVBox4Win-v0.9.6.2-win64.zip", "TVBox4Win-v0.9.6.2-win64.zip"),
    (BASE + r"\tvboxpy-runtime-assets.zip", "tvboxpy-runtime-assets.zip"),
]

BODY = r"""TVBox4Win v0.9.6.2 — 下载即用版（Windows 64 位）

> ⚠️ **强烈建议先安装 Java 环境（JDK 17+）**：现代影视源大多是 Jar 爬虫站点，
> 不装 Java 这些源会打不开（报「未找到 java 运行时」）。
> 请安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)，
> JS 爬虫站点还需 [Node.js](https://nodejs.org/) 16+。

## 📦 TVBox4Win-v0.9.6.2-win64.zip（推荐，解压即玩）

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

## 本版更新（v0.9.6.2）

这一版把**播放地址解析**对齐了原版 TVBox 的完整链路，重点解决
「源能打开、点进去却播不了 / 直播花屏黑屏」的问题。

### 🔎 解析接口按原版语义执行

- `parses` 的 `type` 字段按原版语义解析（此前误读 `flag`）：
  - `0` WebView 直开播放页（不 encode）
  - `1` JSON 接口（`api + encodeUrl(url)`）
  - `2` JSON 扩展（`mixUrl()` 注入 `cat_ext`）
  - `3` JSON 聚合
  - `4` SuperParse（encode 与裸拼都试）
- 解析接口**并发执行**，谁先返回可用地址用谁，12 秒超时后回落页面嗅探
- `playerContent` 返回的 `playUrl` 按原版 `playUrl + url` 当解析前缀
- `ext.header/headers` 里的请求头会带到解析请求和播放请求上

### 🌐 配置 hosts 与嗅探/过滤规则

- 支持配置里的 `hosts`（`域名=IP`）：DNS 解析与播放地址都会走映射，并保留 Host/SNI
- 支持 `rules`：按页面 host 的 `rule`（全部正则命中）/ `filter`（任一命中即丢弃）分组
- 嗅探正则对齐原版 `DefaultConfig.isVideoFormat`（优酷/TOS、西瓜、抖音 CDN、
  `m3u8play.php`、`download.aspx`、`up_api.php`、66yk、网易等特殊直链）

### 🎬 本地 `/proxy` 播放代理（对应原版 `Proxy.java`）

- `m3u8` 播放列表自动改写：分片、密钥、子播放列表全换成代理地址
- 请求头（UA / Referer / Origin / Cookie / Range）随代理链接透传
- 支持 `go=bom`（去 BOM）与 `do=py`（转给 py 爬虫的 `localProxy`）
- 推送服务端口在 9978–9999 间自动择可用端口，与 `/proxy` 共用

### 🐍 py 爬虫 `localProxy` 接入

- `getProxyUrl()` 现在返回本地代理地址（此前指向不存在的服务）
- `localProxy` 返回值兼容列表/字典、bytes/base64、`contentType` 等原版写法

### 🧪 验证

- 新增离线回归 `tests/test_parse_fixes.py`（parse 语义 / 嗅探规则 / hosts /
  m3u8 改写 / 解析全链路 / `/proxy` 服务），全部通过
- 导航、平台隔离、py 爬虫既有测试全部通过
- 打包 exe 自检 11 个模块 OK，`--smoke` 出画面 + seek 正常

> 已知差异：原版 type 0 是在 WebView 里执行 JS 后嗅探，桌面端没有内嵌浏览器，
> 这里改为「拉取解析页 + 静态嗅探」。依赖 JS 动态生成地址的站点仍可能解析失败。

---

## 📚 历史版本（各自独立保留）

| 版本 | 主要变化 |
|---|---|
| **v0.9.6.2**（本版） | 解析链路对齐原版（parse type 全语义、hosts/嗅探规则、本地 `/proxy`、py `localProxy`） |
| [v0.9.6.1](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.1) | 平台层重构（`host/`）、Windows 包瘦身 3.3MB、平台隔离 + 离线播放测试 |
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
