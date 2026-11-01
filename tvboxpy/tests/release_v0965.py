# -*- coding: utf-8 -*-
"""发布 v0.9.6.5：**新建** Release，保留 v0.9.6.4 等旧版不变（token 只在内存中）

步骤：
1. 若 v0.9.6.5 的 release 已存在 → 只同步说明；否则 POST 创建（复用已推送的 tag）
2. 上传 TVBox4Win-v0.9.6.5-win64.zip（完整包，缺则跳过）
3. 上传 tvboxpy-runtime-assets.zip（仅 JVM 资产，可复用）
4. 打印资产清单
"""
import os
import subprocess

import requests

REPO = "lddxmyg/TVBox4Win"
TAG = "v0.9.6.5"
NAME = "TVBox4Win v0.9.6.5"
BASE = r"D:\code\tvbox2exe\tvboxpy"
ASSETS = [
    (BASE + r"\dist\TVBox4Win-v0.9.6.5-win64.zip", "TVBox4Win-v0.9.6.5-win64.zip"),
    (BASE + r"\tvboxpy-runtime-assets.zip", "tvboxpy-runtime-assets.zip"),
]

BODY = r"""TVBox4Win v0.9.6.5 — 下载即用版（Windows 64 位）

> ⚠️ **强烈建议先安装 Java 环境（JDK 17+）**：现代影视源大多是 Jar 爬虫站点，
> 不装 Java 这些源会打不开（报「未找到 java 运行时」）。
> 请安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)，
> JS 爬虫站点还需 [Node.js](https://nodejs.org/) 16+。

## 📦 TVBox4Win-v0.9.6.5-win64.zip（推荐，解压即玩）

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

## 本版更新（v0.9.6.5）

### 🔐 支持加密 / 特殊协议配置

以前只能加载明文 HTTP JSON，遇到加密配置或 `clan://` 地址会直接失败。现在：

- **Base64 包裹**配置（`xxxxxxxx**` 前缀）自动解码
- **`2423` 格式**：AES-128-CBC 解密（密钥/IV 从密文内按原版规则提取）
- **`;pk;密钥` 后缀**：AES-128-ECB 解密
- AES 使用纯 Python 实现，不新增依赖、不增大安装包
- 支持 `clan://localhost/...`、`file://` 和本地 JSON 配置文件路径
- `clan://主机/路径` 统一转换为 `http://主机/file/路径`，配置内引用同源资源自动修正
- 配置里的 `./`、`../` 相对路径（爬虫 `api`/`ext`/`jar`、解析接口、`lives[]`、壁纸）按配置所在位置解析

### 🚑 启动失败不再只能重启

- 加载失败时停在启动页，显示具体原因（文件不存在 / 网络不可达 / 解析或解密失败）
- 提供「重试」按钮，网络恢复后不必关闭程序
- 提供「更换配置」按钮：可直接输入新地址，或浏览选择本地配置文件，成功后自动记住
- 网络不可用但本地有缓存时，明确提示「正在使用上次缓存的配置」后自动进入
- 按钮支持键盘 Tab / Enter 操作

---

## 📚 历史版本（各自独立保留）

| 版本 | 主要变化 |
|---|---|
| **v0.9.6.5**（本版） | 加密配置（Base64 / 2423 / `;pk;`）+ clan/本地配置 + 相对路径解析；启动失败可重试/更换配置、缓存回退提示 |
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
