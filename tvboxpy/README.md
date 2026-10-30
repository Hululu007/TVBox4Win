# tvboxpy — TVBox 复刻（Python 版）

Python + tkinter + libmpv 复刻 TVBox 核心功能，比 C 版开发快一个数量级。

## 运行

```
C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python tvboxpy.py
# 或指定接口
python tvboxpy.py https://dxawi.github.io/0/0.json
```

依赖：requests、python-mpv（已装入 venv）；libmpv-2.dll 在 `third_party/mpv/`。

## 已实现

- 接口配置加载（兼容非纯 JSON 文本、缓存到 tvbox.json）
- 站点 → 分类 → 影片 → 剧集 → libmpv 播放（嵌入窗口，Esc 停止返回）
- 关键词搜索
- type 0/1（CMS API，含 JSON/股票 xml 接口实际返回 JSON 的源）

## 未实现（后续）

- type 3（csp/Spider）站点 —— 现代配置的主流。方案：用 quickjs pip 包跑 JS 爬虫
  （spider 接口：init/home/homeVodSet/category/detail/search/playerContent），
  编译版 csp jar 无法直接跑
- 直播 (lives)、解析 (parses)、历史收藏

## 打包 EXE

```
pyinstaller --onefile --windowed --add-binary "third_party/mpv/libmpv-2.dll;." tvboxpy.py
```

## 默认接口

`https://dxawi.github.io/0/0.json`（48 站点，其中 3 个 type1 可用：
暴风/IK/海外看；其余 type3 需 spider 运行时）
