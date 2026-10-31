# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## 项目概述

**TVBox4Win**：把安卓 TVBox（TVBoxOSC fork）复刻到 Windows 桌面的 Python 项目，技术栈 **Python 3 + tkinter + libmpv**，PyInstaller 打包单文件 EXE。仅面向 Windows。

- 主项目在 `tvboxpy/`；根目录 `reference/` 是原版安卓工程的源码副本（TVBoxOSC fork + ijkplayer），**只作为 UI/行为对齐的参照，不参与构建**，其中 Java 类名与本项目 Python 模块一一对应（如 `ApiConfig.java` ↔ `apiconfig.py`、`HawkConfig.java` ↔ `hawk.py`、`HomeActivity` ↔ `app.py:App`）。改动行为拿不准时先看 reference 里对应 Java 实现。
- 版本号：`tvboxpy/tvboxosc/__init__.py` 的 `VERSION`，窗口标题自动带出版本。

## 常用命令

```bash
cd tvboxpy
pip install requests python-mpv

# 运行（需 libmpv-2.dll 在 third_party/mpv/，头文件已入库、dll 不入库）
python main.py                          # 内置默认接口
python main.py <配置URL或本地json路径>    # 指定接口

# 打包 EXE（PyInstaller onefile + 拷贝 JVM 资产）
python build_exe.py                     # 产物 dist/TVBox4Win.exe + jvmrt/ + dex-tools-v2.4/
```

### 测试

`tvboxpy/tests/` 下没有 pytest 单测，全部是**独立运行的验证脚本**（启动真实程序 → pyautogui/win32gui 操控窗口 → 截图像素断言），单个脚本直接跑：

```bash
cd tvboxpy
python tests/verify_startup.py     # 启动后页面是否正确
python tests/verify_player_ctl.py  # 播放控制栏交互
python tests/test_py_spider.py     # py 爬虫功能测试（无 UI）
python main.py --check             # 打包自检：验证所有页面模块可导入
```

- UI 类脚本依赖 `pywin32`、`pyautogui`、`Pillow`，会真的拉起窗口并抢占鼠标，需在有桌面会话的环境运行。
- 脚本内硬编码了绝对路径（`D:\code\tvbox2exe\tvboxpy`、Python 3.13 路径），换环境需相应修改。
- 截图产物落在本机 `dist/`，断言方式多为扫描像素色值（如主题色 `ACCENT`）。

## 架构要点（需要跨文件理解的部分）

### 1. 启动与页面路由

`main.py` → `apiconfig.py` 解析 TVBox 配置 JSON（兼容纯 JSON/BOM/文本内嵌，解析出站点/直播/parses/spider 地址）→ `app.py:App(tk.Tk)`。

`App` 承载所有页面 Frame，`App.switch(frame_cls, ...)` 模拟 Android Activity 栈（旧页 destroy、新页 pack）。所有页面都是 `tvboxosc/ui_*.py`：ui_grid（首页网格）、ui_detail、ui_play、ui_search、ui_live、ui_setting、ui_history、ui_collect、ui_push 等。`report_callback_exception` 把 Tk 回调异常落到 EXE 旁 `error.log`——排查「点了没反应」先看这个文件。

### 2. 线程模型（tkinter 单线程约束）

**tkinter 只能在主线程操作 UI**。跨线程统一走 `ui_thread.py`：工作线程调 `ui_thread.run(fn)` 入队，主线程 pump 逐个执行回调。所有网络/解析/spider 调用都在后台线程做，UI 更新必须经 ui_thread 回来，新代码必须遵守此约定。

### 3. Spider 运行时（type 3 站点的三种爬虫）

`spider.py` 是统一分发层，对外暴露与原版一致的接口：`home/category/detail/search/playerContent`。

| 爬虫 | 实现 | 外部依赖 |
|---|---|---|
| `csp_*.js` | `spider.py` 起 Node 子进程跑 `spider_runtime/bridge.js`（drpy 运行时），stdio JSON-RPC，每站点一进程、懒加载、退出回收 | Node.js |
| `*.py` | `py_spider.py` Python 基类动态加载 | 无 |
| `*.jar` | `jar_spider.py`：dex→jar 转换（md5 缓存到 `.spider_cache`）+ JVM 桥 `SpiderRunner` | JDK 17+，`jvmrt/` + `dex-tools-v2.4/` 资产 |

type 0/1 CMS 站点不走 spider，由 `data_api.py` 直连 JSON/XML 接口；播放地址解析（媒体直链直播、网页链接页面嗅探 `var main`/直链、parses 解析）也在 `data_api.py`，嗅探语义必须对齐原版 `DefaultConfig.isVideoFormat`。

### 4. libmpv 播放器（player.py）

进程级**单例核心**：libmpv 核心反复 init/terminate 会崩溃、多实例会抢音频设备，所以整个进程共享一个 mpv core，切页时通过改 `wid` 重新嵌入新容器，terminate 只停播。启动时 `MpvPlayer.warmup()` 后台预热（省 1~2s 起播开销）。改播放逻辑时不可绕过单例假设。

### 5. 持久化

- `hawk.py`：配置存储，对应原版 HawkConfig，落 `hawk.json`（EXE 旁）。键名沿用原版（`HOME_REC`、`ijk_codec` 等）。
- `store.py`：观看历史/收藏，SQLite `tvbox.db`，含断点续播位置（`pos`/`duration`）。
- `paths.py:data_path()`：**所有持久化文件必须放 EXE 所在目录**——打包后资源在临时 `_MEI` 目录，每次启动更换，不能持久化。诊断信息统一写 `error.log`。

### 6. 打包资产（不入库，缺了构建/运行会失败）

- `tvboxpy/third_party/mpv/libmpv-2.dll`：从 shinchiro/mpv-winbuild-cmake releases 获取（`include/` 头文件已入库）。
- 根目录 `build/jvmrt/` + `build/dex-tools-v2.4/`：`build_exe.py` 从这里拷贝到 dist（gitignored），丢失可从 Release 的 `tvboxpy-runtime-assets.zip` 恢复。

## 约定

- 代码注释为简体中文，模块 docstring 通常标注对应的原版 Java 类名。
- `.gitattributes` 将 `reference/**`、`tvboxosc/spider_runtime/*.js`、`tests/**` 标记为 `linguist-vendored`（保持 GitHub 语言统计为 Python），新增第三方/生成代码目录时同样处理。
- 仓库：github.com/lddxmyg/TVBox4Win（push 走 SSH）。
