# TVBox4Win 安卓版（Kivy / Python）

**与桌面版同一份业务代码的安卓实现**：配置解析、CMS 请求、本地存储、EPG
直接从 `tvboxpy/tvboxosc` 同步复用，界面层用 Kivy 重写（tkinter 没有 Android 实现）。

## 目录结构

```
android/
├── main.py              # 入口（Kivy App）
├── buildozer.spec       # python-for-android 打包配置
├── sync_core.py         # 构建前把桌面版业务模块同步到 vendor/（生成物，不入库）
├── androidui/           # Kivy 界面层
│   ├── app.py           #   全局状态、页面路由、源切换、配置加载
│   ├── theme.py         #   配色（与桌面一致）+ 系统中文字体注册
│   ├── widgets.py       #   扁平按钮 / 分类 chip / 海报卡片 / 滚动网格
│   ├── home.py          #   首页：源 + 分类 + 影片网格 + 分页
│   ├── search.py        #   搜索（当前源）
│   ├── detail.py        #   详情：简介 + 线路 + 选集
│   └── play.py          #   播放：系统 MediaPlayer（m3u8 / mp4）
├── tests/
│   ├── smoke_core.py    # 业务链路自测（不需要设备/界面）
│   ├── shot_android_ui.py    # 桌面跑 Kivy 预览首页并截图
│   └── shot_android_flow.py  # 桌面跑「首页→详情→播放」三页截图
└── vendor/tvboxosc/     # sync_core.py 生成的业务层（gitignored）
```

## 构建 APK

本机没有 Linux 构建环境（p4a 不支持 Windows），APK 统一由 GitHub Actions 构建：

1. 推送 `android/**` 的改动，或到 **Actions → android-apk → Run workflow**
   选目标架构（真机 `arm64-v8a`；逍遥/MEmu 等 x86 模拟器选 `x86_64`）
2. 构建完成后从该次运行的 **Artifacts** 下载 `TVBox4Win-apk`
3. 首次构建约 40–60 分钟（要下载 SDK/NDK），之后有缓存会快很多

## 本地调试（不需要设备）

Kivy 在 Windows 上可以直接跑，界面所见即安卓所得：

```bash
python sync_core.py                      # 同步业务层到 vendor/
python tests/smoke_core.py               # 业务链路自测（配置→分类→列表→详情→播放地址）
python tests/shot_android_ui.py out.png  # 起一个 390x844 的窗口预览首页并截图
python tests/shot_android_flow.py        # 跑「首页→详情→播放」三页截图
```

改桌面版业务逻辑（`tvboxpy/tvboxosc/`）后重新执行 `sync_core.py` 即可带入安卓版。

## 已知限制

- **只支持 CMS 源（type 0/1/2）**：Jar 爬虫需要 JVM、JS 爬虫需要 node，
  安卓 APK 内都没有；界面只列出 `is_type012()` 的站点
- 播放用系统 MediaPlayer，不支持自定义请求头（需要 Referer/UA 的源可能播不了）
- 桌面预览时 Video 控件没有解码器，播放页只有布局（真机/模拟器上正常播放）
