# -*- coding: utf-8 -*-
"""发布 v0.9.6.7：**新建** Release，保留 v0.9.6.6 等旧版不变（token 只在内存中）

步骤：
1. 若 v0.9.6.7 的 release 已存在 → 只同步说明；否则 POST 创建（复用已推送的 tag）
2. 上传 TVBox4Win-v0.9.6.7-win64.zip（完整包，缺则跳过）
3. 上传 tvboxpy-runtime-assets.zip（仅 JVM 资产，可复用）
4. 打印资产清单
"""
import os
import socket
import subprocess

import requests

# 本机 hosts 把 api.github.com 指到了一台会 301 的节点，这里单独把 API 域名
# 固定到可用 IP（可用环境变量 GITHUB_API_IP 覆盖）
_API_IP = os.environ.get("GITHUB_API_IP", "140.82.114.6")
_orig_gai = socket.getaddrinfo


def _gai(host, port, *args, **kwargs):
    if host == "api.github.com":
        host = _API_IP
    return _orig_gai(host, port, *args, **kwargs)


socket.getaddrinfo = _gai

REPO = "lddxmyg/TVBox4Win"
TAG = "v0.9.6.7"
NAME = "TVBox4Win v0.9.6.7"
BASE = r"D:\code\tvbox2exe\tvboxpy"
ASSETS = [
    (BASE + r"\dist\TVBox4Win-v0.9.6.7-win64.zip", "TVBox4Win-v0.9.6.7-win64.zip"),
    (BASE + r"\tvboxpy-runtime-assets.zip", "tvboxpy-runtime-assets.zip"),
]

BODY = r"""TVBox4Win v0.9.6.7 — 下载即用版（Windows 64 位）

> ⚠️ **强烈建议先安装 Java 环境（JDK 17+）**：现代影视源大多是 Jar 爬虫站点，
> 不装 Java 这些源会打不开（报「未找到 java 运行时」）。
> 请安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)，
> JS 爬虫站点还需 [Node.js](https://nodejs.org/) 16+。

## 📦 TVBox4Win-v0.9.6.7-win64.zip（推荐，解压即玩）

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

## 本版更新（v0.9.6.7）

### ⌨️ 搜索页：原版虚拟键盘 + 拼音首字母搜索

- 搜索页底部新增虚拟键盘（对应原版 `SearchKeyboard`）：
  `远程搜索` / `删除` + `A-Z` + `0-9`，鼠标点击即可拼首字母
- 输入首字母自动请求联想接口，显示「猜你想搜」词条
  （例如 `XLT` → 夏洛特烦恼 / 夏洛特的网…），点词条直接按中文片名搜索
- 点完键盘自动把焦点还给输入框，物理键盘可继续输入
- 「远程搜索」在桌面端改为输入/粘贴关键词对话框，回车即搜

### 🐛 播放页：修复「更多」面板重复弹出

- 连续点击「更多」不会再叠加多个相同窗口，改为开关式：打开后再点收起
- 字幕 / 音轨 / 弹幕 / 选集 / 线路面板统一管理，同一时间只保留一个
- 支持 Esc 和窗口关闭按钮收起，退出播放页时自动关闭

---

## 📚 历史版本（各自独立保留）

| 版本 | 主要变化 |
|---|---|
| **v0.9.6.7**（本版） | 搜索页虚拟键盘 + 拼音首字母「猜你想搜」；修复播放页「更多」重复弹窗 |
| [v0.9.6.6](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.6) | 弹幕播放 / 二维码推送 / EPG 回看 / 直播 m3u 扩展 / 首页文件夹与翻页 / 历史收藏海报页 / 31 项设置 / 推送服务新接口 |
| [v0.9.6.5](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.5) | 加密配置（Base64 / 2423 / `;pk;`）+ clan/本地配置 + 相对路径解析；启动失败可重试/更换配置、缓存回退提示 |
| [v0.9.6.4](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.4) | 播放失败自动重试/换线 + `lives[]` type=3 爬虫直播源 |
| [v0.9.6.3](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.3) | 修 Jar 爬虫「分类加载失败」（关闭 JVM 字节码校验）、错误提示可读化 + 点击重试 |
| [v0.9.6.2](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.2) | 解析链路对齐原版（parse type 全语义、hosts/嗅探规则、本地 `/proxy`、py `localProxy`） |
| [v0.9.6.1](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6.1) | 平台层重构（`host/`）、Windows 包瘦身 3.3MB、平台隔离 + 离线播放测试 |
| [v0.9.6](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6) | macOS 原生支持（AVFoundation 后端、`.app` 打包、苹方字体） |

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
    for rel in r.json()[:5]:
        print(" -", rel["tag_name"], "|", len(rel["assets"]), "assets")
        for a in rel["assets"]:
            print("     ", a["name"], round(a["size"] / 1048576, 1), "MB")


if __name__ == "__main__":
    main()
