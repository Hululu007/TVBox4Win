# tvbox2exe — TVBox 复刻（Windows 原生 EXE）

用 C11 + Win32 + libmpv 复刻 TVBox 核心功能，产出单个 `tvbox.exe` + `libmpv-2.dll`。

## 功能

- 加载 TVBox 接口配置（`sites` 数组，支持 `type: 0/1` 的 JSON/XML 源；`type: 3` spider 站点不支持）
- 左侧站点列表 → 分类 → 影片列表 → 剧集 → mpv 播放
- 关键词搜索（右上角输入，点"搜索"）
- "返回"键逐级回退；播放中按返回先停止播放

## 使用

1. 双击 `build\tvbox.exe`（需与 `libmpv-2.dll` 同目录）
2. 首次启动会从内置默认配置 URL 下载接口并缓存为 `tvbox.json`
   - 想用自己的接口：把 TVBox 配置 JSON 保存为 exe 同目录的 `tvbox.json`，删缓存重开即可
   - 默认 URL 在 `src/main.c` 的 `DEFAULT_CONFIG_URL`，可改后重新编译
3. 双击站点 → 双击分类 → 双击影片 → 双击剧集播放

## 构建

```
cmake -B build -G Ninja
cmake --build build
```

依赖：MinGW-w64 (gcc)、Ninja、CMake。libmpv 已内置在 `third_party/mpv`（来自
zhongfly/mpv-winbuild 每日构建，仅头文件 + 导入库 + 运行 DLL）。

## 结构

```
src/main.c    Win32 UI + mpv 集成 (wid 嵌入)
src/http.c    WinHTTP GET
src/tvbox.c   TVBox 配置/分类/详情 JSON 解析 (基于 cJSON)
```

## 已知限制

- 不支持 `type: 3`（csp/Spider jar）站点——那是 Android 上的 Java 插件机制
- 不支持 xml 源解析（type 1 目前走 JSON 路径）
- 无播放历史/收藏，无直播（live）模块

上游开源参考：`D:/code/tvbox2exe/TVBoxOSC`（AGPL-3.0）
