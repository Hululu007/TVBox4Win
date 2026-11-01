# macOS 版说明（TVBox4Win for Mac）

原工程是 Windows 专用（tkinter + libmpv.dll + PyInstaller EXE）。本目录已移植到
macOS，可直接跑源码，也可打包成 `.app` 双击运行。

## 快速开始

```bash
# 运行源码
../.venv/bin/python main.py

# 打包成 dist/TVBox4Win.app（构建脚本会自动装依赖、生成 icns、跑冒烟自检）
./build_mac.sh
./build_mac.sh --run        # 打包后直接启动

# 冒烟自检：真实解码一段 HLS 测试流，验证播放链路
../dist/TVBox4Win.app/Contents/MacOS/TVBox4Win --smoke
```

## 移植改了什么

| 文件 | 改动 |
|---|---|
| `tvboxosc/player_av.py` | **新增**，AVFoundation 播放后端（AVPlayer + AVPlayerLayer） |
| `tvboxosc/player_mac.py` | **新增**，mpv 独立进程 + JSON IPC 后端（装了 mpv 时优先用） |
| `tvboxosc/player.py` | 按平台分发后端；`wid` 参数兼容控件/整数；容器尺寸变化时同步播放窗口 |
| `tvboxosc/apiconfig.py` | 配置加载回调改走 `ui_thread`，回主线程建界面 |
| `tvboxosc/app.py` | `attributes("fullscreen")` 兼容 Tk 9 的横线写法 |
| `tvboxosc/theme.py` | 字体按平台选（苹方 / 雅黑） |
| `tvboxosc/paths.py` | 冻结后数据落 `~/Library/Application Support/TVBox4Win` |
| `tvboxosc/spider.py` | node 查找补上 macOS 路径（GUI 启动 PATH 很干净） |
| `tvboxosc/ui_play.py` 等 | 传入视频容器与 `insets`；页面销毁时统一收尾 |
| `tvboxpy_mac.spec` / `build_mac.sh` / `rthook_tcl.py` | **新增**，macOS 打包链路 |

## 播放方案为什么变了

macOS 的 mpv vo(cocoa) **不支持 `wid` 嵌入**（只有 X11/win32 支持），Windows 那套
「把 libmpv 塞进 tkinter 子窗口」在 Mac 上无法成立。现方案：

- 画面放在一个**无边框 / 置顶 / 鼠标穿透**的独立窗口里，位置实时跟随页面里的视频容器
  （自动扣掉顶栏 42px、底栏 96px），所以页面自绘的控制栏既不被遮挡，也照样能点；
- 播放控制走 AVPlayer API（播放/暂停/seek/音量/倍速），对外接口与 python-mpv 一致，
  业务代码零改动；
- 若本机装了 mpv（`brew install mpv`），会自动优先用 mpv 后端，格式支持更全。

## 已知限制

- **格式**：AVFoundation 只认系统解码器能吃的容器 —— m3u8/mp4/mov/m4v 没问题，
  **mkv、avi 播放不了**（想全格式请装 mpv）。
- **Jar 爬虫源**：需要 JDK 17+。本机没装 Java 时这类源会提示「分类加载失败」，
  换用 CMS 类型（type 0/1）的源即可正常使用。
- **JS 爬虫源**：需要 node，已在 `spider.py` 里补了常见路径查找。
- 首次打开若被 Gatekeeper 拦，右键 → 打开；或
  `xattr -dr com.apple.quarantine dist/TVBox4Win.app`。

## 数据位置（源码运行 / 打包运行不同）

- 源码运行：`tvboxpy/`（`hawk.json`、`tvbox.db`、`error.log`）
- 打包运行：`~/Library/Application Support/TVBox4Win/`

排查「点了没反应」先看对应目录的 `error.log`。
