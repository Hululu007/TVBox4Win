# TVBox4Win — TVBox 复刻（Python 版）

> **背景**：原版 TVBox 是安卓应用，装到手机上要通讯录、地理位置、设备信息等一堆权限，很多人已经不愿意装了；
> 想在电脑上找一份功能完整的桌面复刻，一直找不到。过去卡在「工作量太大」——这次借助 AI Agent 结对开发才真正做出来。
> 欢迎 **star / fork / PR**，一起把它磨完整。完整说明见[仓库根目录 README](../README.md)。

用 **Python 3 + tkinter + libmpv** 在 Windows 桌面上复刻 [TVBox](https://github.com/o0HalfLife0o/TVBoxOSC)（安卓 TV 端影视聚合播放器）的核心功能：

- **接口配置加载**：兼容 TVBox 各类配置（纯 JSON / 带 BOM / 文本内嵌 JSON），站点、直播、解析、spider 全解析
- **首页推荐**：豆瓣热播 / 站点推荐 / 观看历史 三模式切换（对应原版 HawkConfig.HOME_REC）
- **分类浏览**：站点 → 分类 → 影片网格（海报异步加载、豆瓣镜像兜底、优先级调度）
- **搜索**：复刻原版 FastSearchActivity——多站点并发、实时状态、分词 chips 换词重搜
- **详情页**：影片信息 chips、多线路多选集（千集长剧分批渲染）、播放地址展示、收藏/快速搜索
- **播放**：libmpv 全屏沉浸式播放，复刻原版控制栏（暂停/上下集/重播/倍速/进度条拖拽/音量/选集，4 秒无操作自动隐藏），断点续播、自动连播
- **设置**：解码方式（硬解/软解）、画面缩放、历史上限、首页站源、清空缓存等
- **爬虫运行时**：type 0/1 CMS 接口、type 3 的 JS 爬虫（内置 drpy 运行时，经 Node 子进程桥接）/ Py 爬虫 / Jar 爬虫（dex→jar 转换 + JVM 桥）

## 目录结构

```
tvboxpy/
├── main.py              # 入口
├── tvboxosc/            # 应用源码（UI / 数据 / 播放 / 爬虫）
│   ├── app.py           # 主窗口与页面路由
│   ├── ui_*.py          # 主页/搜索/详情/播放/设置/收藏/直播等页面
│   ├── player.py        # libmpv 封装（预热、复用、断点续播）
│   ├── data_api.py      # CMS 接口 + 播放地址解析/嗅探
│   ├── spider.py        # spider 分发（js/py/jar）
│   ├── spider_runtime/  # 内置 quickjs JS 爬虫运行时（drpy 同款）
│   ├── jar_spider.py    # jar spider：dex→jar 转换 + JVM 桥
│   ├── apiconfig.py     # 接口配置解析
│   ├── store.py / hawk.py  # 观看历史(SQLite) / 配置存储
│   └── theme.py / imgcache.py  # 主题与海报缓存
├── third_party/mpv/     # libmpv 开发库（dll 不入库，见下）
├── tests/               # 自动化验证脚本（EXE 像素级 UI 测试）
├── build_exe.py         # PyInstaller 打包脚本
└── tvboxpy.spec
```

## 运行

> ### ⚠️ 强烈建议先安装 Java 环境（JDK 17+）
>
> 现代影视源大多是 **Jar 爬虫站点**，不装 Java 这些源会全部打不开（报「未找到 java 运行时」）。请安装 [Microsoft OpenJDK 17](https://learn.microsoft.com/java/openjdk/download)（或任意 JDK/JRE 17+），确保 `java` 在 PATH 中即可。JS 爬虫站点还需要 [Node.js](https://nodejs.org/) 16+。两者都装上，绝大多数接口配置里的源都能正常打开。

依赖：Python 3.10+，`pip install requests python-mpv`，以及 [libmpv](https://github.com/shinchiro/mpv-winbuild-cmake/releases) 的 `libmpv-2.dll`（放入 `third_party/mpv/`，`include/` 头文件已随仓库提供）。

```
python main.py                # 使用内置默认接口
python main.py <配置URL或本地json路径>
```

## 打包 EXE

```
python build_exe.py           # 产物在 dist/tvboxpy.exe
```

jar spider 站点运行还需将 `jvmrt/`（JVM 桥运行时）与 `dex-tools-v2.4/` 放到 exe 同目录。

## 说明

- `reference/`（仓库根目录）内为学习对齐 UI/交互所参照的原版安卓源码（TVBoxOSC fork），版权归原项目所有，不参与本项目构建。
- 本项目仅供学习交流，请勿用于商业用途；影视数据均来自第三方接口，与本项目无关。
