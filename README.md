# TVBox4Win — TVBox 桌面复刻（Python 版，Windows + macOS）

**TVBox4Win**：把安卓 TV 上流行的影视聚合播放器 TVBox 完整搬到桌面。

当前版本：**v0.9.6**（macOS 首发版；版本号见窗口标题 / 设置 → 关于；发版从 [Releases](https://github.com/lddxmyg/TVBox4Win/releases) 下载）

把安卓 TV 上流行的影视聚合播放器 [TVBox](https://github.com/o0HalfLife0o/TVBoxOSC) 复刻到桌面：
**Python 3 + tkinter** 实现，UI 与交互按原版逐页对齐。同一份代码支持两个平台：

| 平台 | 播放内核 | 产物 |
|---|---|---|
| **Windows** | libmpv（`libmpv-2.dll`） | 单文件 `TVBox4Win.exe` |
| **macOS** 🆕 | AVFoundation（系统自带），可选 mpv | `TVBox4Win.app` |

> 本项目仅供学习交流，请勿用于商业用途。影片数据均来自用户自行配置的第三方接口，与本项目无关。

## 📥 免安装下载（推荐）

不想折腾环境？直接到 [**Releases**](https://github.com/lddxmyg/TVBox4Win/releases) 下载 Windows 安装包（当前最新为 `TVBox4Win-v0.9.5-win64.zip`；v0.9.6 只发布了 macOS 构建，Windows 二进制随后续版本更新）：

1. 解压到任意可写目录
2. 双击 `TVBox4Win.exe` 即可使用（libmpv 播放内核已内嵌，**无需安装 Python / mpv**）
3. 首次运行如遇 SmartScreen 拦截，点「更多信息 → 仍要运行」

> ### ⚠️ 强烈建议先安装 Java 环境（JDK 17+）
>
> 现代影视源的爬虫大多是 **Jar 爬虫**（`.jar` 类型的站点源），**不装 Java 这些源会全部打不开**（报「未找到 java 运行时」）。请先安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)（或任意 JDK/JRE 17+），安装后确保 `java` 命令在 PATH 中即可，无需其他配置。
>
> | 站点源类型 | 需要的环境 |
> |---|---|
> | CMS 站点（type 0/1） | 开箱即用 |
> | JS 爬虫站点 | 需安装 [Node.js](https://nodejs.org/) 16+ |
> | Jar 爬虫站点（最常见） | **需安装 JDK/JRE 17+** |
>
> 建议两个都装上：`Node.js` + `JDK 17+`，这样绝大多数接口配置里的源都能正常打开。

## 🍎 macOS 版（新增）

同一份代码原生跑在 Apple Silicon / Intel Mac 上，产物是 `TVBox4Win.app`——**双击即用，无需安装 Python，也无需 libmpv**。

1. 从 [Releases](https://github.com/lddxmyg/TVBox4Win/releases) 下载 `TVBox4Win-v0.9.6-macos-arm64.zip`
2. 解压得到 `TVBox4Win.app`，拖进「应用程序」
3. 首次打开若被 Gatekeeper 拦截：**右键 → 打开**；或执行
   `xattr -dr com.apple.quarantine /Applications/TVBox4Win.app`

### 和 Windows 版的差异

| 项目 | Windows | macOS |
|---|---|---|
| 播放内核 | libmpv（`libmpv-2.dll`，嵌入 tkinter 子窗口） | AVFoundation（系统自带） |
| 画面呈现 | 内嵌在播放页里 | 无边框置顶窗口，实时跟随播放页的视频区域 |
| 支持格式 | 全格式（mpv 解码） | m3u8 / mp4 / mov / m4v；**mkv、avi 播不了** |
| 全格式兜底 | 默认 | 装了 mpv（`brew install mpv`）会自动优先用 mpv 后端 |
| Jar 爬虫源 | 需 JDK 17+ | 同左；**没装 JDK 时自动跳过 jar 源，改用 CMS 源**（不会一进来就报错） |
| JS 爬虫源 | 需 Node.js | 同左（已补充 macOS 下的 node 路径查找） |
| 数据目录 | EXE 同目录 | `~/Library/Application Support/TVBox4Win` |

> **为什么不用 mpv 嵌入？** macOS 的 mpv cocoa 视频输出不支持 `wid` 嵌入（只有 X11 / win32 支持），
> Windows 那套「把 libmpv 塞进 tkinter 子窗口」在 Mac 上不成立。因此画面放在独立的无边框置顶窗口里，
> 位置实时对齐播放页的视频区域（自动扣掉顶栏 / 底栏），页面自绘的控制栏既不被遮挡、也仍可点击。

### 📚 版本历史（每个版本独立打包，互不覆盖）

每个 Release 都是独立附件，想留在旧版直接下对应版本即可：

| 版本 | 主要变化 | 下载 |
|---|---|---|
| **v0.9.6**（最新） | **新增 macOS 原生支持**：AVFoundation 播放后端、`.app` 打包、苹方字体、无 JDK 时自动跳过 jar 源；Windows 部分与 v0.9.5 一致 | [v0.9.6](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.6)（仅 macOS 构建） |
| v0.9.5 | 点播/搜索页海报网格自适应窗口宽度（右侧留白消除）、海报放大到原版 244:320 比例、片名叠加海报底部、菜单按钮均分整行 | [v0.9.5](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.5) |
| v0.9.4 | 直播页整页重构（两层列表 + 进入即播）、修 Esc 退不出的卡死、全局频道编号 + EPG 节目单 | [v0.9.4](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.4) |
| v0.9.3 | 自定义直播源（点播/直播双输入、直播历史、txt/m3u/JSON 解析） | [v0.9.3](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.3) |
| v0.9.2 | 全新自绘应用图标、开始版本号体系 | [v0.9.2](https://github.com/lddxmyg/TVBox4Win/releases/tag/v0.9.2) |

---

## ✨ 功能特性

| 模块 | 说明 | 对齐原版 |
|---|---|---|
| 接口配置 | 兼容 TVBox 各类配置（纯 JSON / 带 BOM / 文本内嵌 JSON），自动解析站点、直播、解析规则、spider 地址 | `ApiConfig.java` |
| 首页推荐 | 豆瓣热播 / 站点推荐 / 观看历史 三模式切换，设置中一键更换 | `HawkConfig.HOME_REC` |
| 分类浏览 | 站点 → 分类 → 影片网格；海报异步加载、优先级调度、豆瓣镜像兜底、失败黑名单 | `HomeActivity` / `GridFragment` |
| 关键词搜索 | 多站点并发搜索、实时进度状态栏、热词分词 chips（点击换词重搜）、结果按相关度排序 | `FastSearchActivity` |
| 详情页 | 影片信息 chips（年份/地区/类型）、多线路多选集（千集长剧分批渲染不卡顿）、播放地址展示、收藏 / 快速搜索 | `DetailActivity` |
| 视频播放 | libmpv 全屏沉浸式播放；悬浮控制栏（4 秒无操作自动隐藏）；断点续播；播完自动连播 | `PlayActivity` |
| 播放器控制栏 | 暂停/上一集/下一集/重播/全屏/音量/倍速/选集 + 可拖动进度条（当前时间/总时长），与原版 `player_vod_control_view.xml` 同布局 | 同左 |
| 直播 | 全屏播放层 + 左侧两层列表（分组列 / 频道列），进入即自动播放；全局台号与数字键选台一致；自定义直播源（txt/m3u/TVBox 配置）；EPG 节目单（XMLTV/JSON，当前▶+下一个节目）；顶栏返回 + 悬浮控制栏，5 秒无操作自动隐藏 | `LivePlayActivity` |
| 收藏/历史 | SQLite 持久化，历史上限自动裁剪（30/50/100 条可选），历史卡片显示进度与上次观看位置 | `VodRecord` |
| 推送 | 手机扫码/HTTP 推送播放链接到桌面播放 | `PushActivity` |
| 设置 | 配置地址（点播 + 直播双输入）、配置历史、直播地址（自定义直播源 + 直播历史）、首页站源、首页推荐、解码方式（硬解/软解）、画面缩放（默认/16:9/4:3/填充/原始）、历史上限、下次进入、清空缓存 | `ModelSettingFragment` / `ApiDialog` |

### 爬虫运行时（type 3 站点支持）

现代 TVBox 配置的站点大多是 type 3 spider 站点，本项目内置三种运行时：

| 爬虫类型 | 运行时 | 依赖 |
|---|---|---|
| `csp_*.js` JS 爬虫 | 内置 [drpy](https://github.com/hjdhnx/dr_py) 运行时（Node 子进程 `bridge.js` + stdio JSON-RPC） | **Node.js** |
| `*.py` Py 爬虫 | 内置 Python 基类（与 tvboxosc-python pyramid 运行时同 API） | 无额外依赖 |
| `*.jar` Jar 爬虫 | dex→jar 转换 + JVM 桥（`jvmrt/`） | **JDK/JRE 17+**，`jvmrt/` + `dex-tools-v2.4/` 资产目录 |

---

## 📦 运行依赖

| 依赖 | 版本要求 | 用途 | 必需？ |
|---|---|---|---|
| [Python](https://www.python.org/) | 3.10+ | 运行主程序 | ✅ 必需 |
| `requests` | 最新 | HTTP 请求 | ✅ 必需 |
| [python-mpv](https://github.com/jaseg/python-mpv) (`mpv`) | 最新 | libmpv 的 Python 绑定 | ✅ 必需 |
| [libmpv](https://github.com/shinchiro/mpv-winbuild-cmake/releases) | `libmpv-2.dll` | 视频播放内核 | ✅ 必需 |
| [Node.js](https://nodejs.org/) | 16+ | 运行 JS 爬虫站点 | 仅 JS 站点需要 |
| [JDK](https://learn.microsoft.com/java/openjdk/download) | 17+（已验证 21） | 运行 Jar 爬虫站点 + dex 转换 | 仅 Jar 站点需要 |
| [PyInstaller](https://pyinstaller.org/) | 最新 | 打包 EXE | 仅打包需要 |

**libmpv 获取方式**：从 [shinchiro/mpv-winbuild-cmake releases](https://github.com/shinchiro/mpv-winbuild-cmake/releases) 下载 `mpv-dev-x86_64-*-git-*.7z`，解压出 `libmpv-2.dll` 放入 `tvboxpy/third_party/mpv/`（`include/` 头文件已随仓库提供，无需下载）。

**macOS 依赖不同**：不需要 `python-mpv` 和 `libmpv`，播放走系统 AVFoundation，只需 `requests` + `Pillow` + `pyobjc-framework-Cocoa` + `pyobjc-framework-AVFoundation`（见下文命令）。

---

## 🚀 从源码运行

```bash
cd tvboxpy
pip install requests python-mpv

# 将 libmpv-2.dll 放入 third_party/mpv/ 后：
python main.py                 # 使用内置默认接口
python main.py <配置URL或本地json路径>   # 指定接口
```

启动后即进入主页海报墙，方向键/鼠标均可操作；`F11` 全局切换全屏。

## 🧱 打包 EXE

```bash
cd tvboxpy
python build_exe.py
```

产物：`tvboxpy/dist/tvboxpy.exe`（单文件）+ 同目录 `jvmrt/`、`dex-tools-v2.4/`（Jar 爬虫运行资产，发布时一并携带）。

**运行资产下载**：Jar 爬虫运行时不入库，可从 [Releases](https://github.com/lddxmyg/TVBox4Win/releases) 下载 `tvboxpy-runtime-assets.zip`，解压到 EXE 同目录即可（包含 `jvmrt/` 与 `dex-tools-v2.4/`）。

## 🍏 从源码运行（macOS）

```bash
cd tvboxpy
python3 -m venv ../.venv && ../.venv/bin/python -m pip install \
  requests Pillow pyobjc-framework-Cocoa pyobjc-framework-AVFoundation

../.venv/bin/python main.py              # 使用内置默认接口
../.venv/bin/python main.py <配置URL>     # 指定接口
```

> Python 必须自带可用的 Tcl/Tk。macOS 系统自带的 3.9（Tk 8.5）能用但偏旧；
> 推荐 python.org 安装包或 `uv python install 3.12`（自带 Tcl/Tk 9.0）。

## 🍏 打包 .app（macOS）

```bash
cd tvboxpy
./build_mac.sh          # 装依赖 → 生成 icns → PyInstaller 打包 → 冒烟自检
./build_mac.sh --run    # 打包完成直接启动
```

产物：`dist/TVBox4Win.app`（arm64，约 47MB）。

**冒烟自检**：打包链路内置一段真实播放校验，会拉起窗口播一段 HLS 测试流并验证 seek：

```bash
dist/TVBox4Win.app/Contents/MacOS/TVBox4Win --smoke
# player_backend: av / position: 6.0 / duration: 634.6 / decode_ok: YES / seek_ok: YES
```

更多移植细节见 [`tvboxpy/README-mac.md`](tvboxpy/README-mac.md)。

## 📁 目录结构

```
tvbox2exe/
├── tvboxpy/                  # ★ 主项目
│   ├── main.py               # 程序入口（对应 App.java 启动流程）
│   ├── tvboxosc/             # 应用源码
│   │   ├── app.py            #   主窗口与页面路由
│   │   ├── ui_*.py           #   主页/搜索/详情/播放/设置/收藏/历史/直播/推送
│   │   ├── player.py         #   播放器门面（按平台分发后端、断点续播、倍速）
│   │   ├── player_av.py      #   macOS 播放后端：AVFoundation
│   │   ├── player_mac.py     #   macOS 可选播放后端：mpv 子进程 + JSON IPC
│   │   ├── data_api.py       #   CMS 接口 + 播放地址解析/页面嗅探
│   │   ├── spider.py         #   spider 分发（js/py/jar）
│   │   ├── spider_runtime/   #   JS 爬虫运行时（drpy.js + Node bridge）
│   │   ├── jar_spider.py     #   Jar 爬虫：dex→jar 转换 + JVM 桥
│   │   ├── py_spider.py      #   Py 爬虫基类
│   │   ├── apiconfig.py      #   接口配置解析
│   │   ├── store.py / hawk.py#   观看历史(SQLite) / 配置存储
│   │   └── theme.py / imgcache.py  # 暗色主题 / 海报缓存
│   ├── third_party/mpv/      # libmpv 开发库（dll 不入库，见上文获取方式）
│   ├── tests/                # 自动化验证脚本（EXE 像素级 UI 回归测试）
│   ├── build_exe.py          # 一键打包脚本（Windows）
│   ├── tvboxpy.spec          # PyInstaller 配置（Windows）
│   ├── build_mac.sh          # 一键打包脚本（macOS）
│   ├── tvboxpy_mac.spec      # PyInstaller 配置（macOS，含 ATS 放行）
│   ├── rthook_tcl.py         # macOS 打包运行时钩子（Tcl/Tk 9 路径）
│   └── README-mac.md         # macOS 移植说明与已知限制
├── reference/                # 开发时对齐 UI/交互所参照的原版安卓源码
│   ├── app/                  #   TVBoxOSC fork 主工程（版权归原项目所有）
│   ├── player/               #   ijkplayer 源码
│   └── ref/                  #   原版界面参考截图
└── build/                    # 打包资产源（jvmrt/ + dex-tools-v2.4/，gitignored）
```

## ⌨️ 播放页快捷键

| 按键 | 功能 | 按键 | 功能 |
|---|---|---|---|
| `空格` | 暂停 / 继续 | `←` / `→` | 快退 / 快进 10 秒 |
| `↑` / `↓` | 音量调节 | `PgUp` / `PgDn` | 上一集 / 下一集 |
| `F` | 全屏 / 窗口切换 | `Esc` / `BackSpace` | 返回 |

控制栏在 4 秒无操作后自动隐藏，移动鼠标或按任意键唤出。

## 🛠 工作原理（简述）

```
main.py 启动
  └─ ApiConfig 加载配置 JSON（站点/直播/解析/spider）
       ├─ type 0/1 站点 ──► data_api：CMS JSON/XML 接口直连
       │                     播放地址：媒体直链直接播；网页链接走页面嗅探/parses 解析
       ├─ type 3 js 站点 ──► Node 子进程跑 drpy 运行时（stdio JSON-RPC）
       ├─ type 3 py 站点 ──► Python 内置基类动态加载
       └─ type 3 jar 站点 ─► dex→jar 转换（md5 缓存）→ JVM 桥 SpiderRunner
            └─ 统一接口：home/category/detail/search/playerContent
播放 ──► ui_play 后台解析地址 → 播放器（悬浮控制栏 + 断点续播 + 自动连播）
         ├─ Windows：libmpv（libmpv-2.dll，wid 嵌入播放页）
         └─ macOS：AVFoundation（独立置顶窗口跟随播放页视频区域）
```

## ❓ 常见问题

- **启动后白屏/无站点**：默认接口依赖网络可达，可在设置 → 配置地址里换一个接口源。
- **点影片没反应**：豆瓣壳源（msearch）点击会自动跳搜索页，与原版行为一致；个别慢源需等待嗅探解析。
- **JS 站点报「未找到 node 运行时」**：安装 Node.js 并确保 `node` 在 PATH 中。
- **Jar 站点报「未找到 java 运行时」**：安装 JDK 17+ 并确保 `java` 在 PATH 中；从 [Releases](https://github.com/lddxmyg/TVBox4Win/releases) 下载运行资产包解压到 EXE 同目录。
- **播放黑屏**：多为该源地址失效，切换线路或换站点；可在设置中尝试软解码。

**macOS 专属**

- **提示「无法打开，因为 Apple 无法检查其是否包含恶意软件」**：未做 Apple 公证。右键 → 打开，或 `xattr -dr com.apple.quarantine /Applications/TVBox4Win.app`。
- **部分影片黑屏 / 只有声音**：该片是 mkv、avi 等 AVFoundation 不支持的容器。换 mp4/m3u8 的线路，或 `brew install mpv` 后重启应用（会自动切到 mpv 后端，支持全格式）。
- **想用 jar 爬虫源**：装 JDK 17+（`brew install openjdk@17`）即可，应用会自动识别。
- **播放时画面盖住界面 / 位置错位**：画面是独立置顶窗口，进出全屏时会自动重新对齐；若出现错位，切一下页面（Esc 返回再进）即可恢复。
- **数据在哪**：`~/Library/Application Support/TVBox4Win`（`hawk.json` 配置、`tvbox.db` 历史、`error.log` 排查日志）。

## 📜 致谢与声明

- [TVBoxOSC](https://github.com/o0HalfLife0o/TVBoxOSC)（及各家 fork）—— 原版安卓应用，本项目 UI/交互的参照对象，`reference/` 目录内为其源码副本，版权归原项目所有
- [drpy](https://github.com/hjdhnx/dr_py)、[libmpv](https://mpv.io/) —— 爬虫运行时与播放内核
- 本项目不存储、不提供任何影视内容；所有数据均来自用户配置的第三方接口
