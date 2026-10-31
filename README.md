# tvbox2exe

把 TVBox（安卓 TV 影视聚合播放器）搬到 Windows 桌面的复刻项目。

- **`tvboxpy/`** —— 主项目：Python + tkinter + libmpv 实现的 TVBox 复刻，详见 [tvboxpy/README.md](tvboxpy/README.md)
- **`reference/`** —— 开发时对齐 UI / 交互所参照的原版安卓源码（TVBoxOSC fork）与参考截图，仅供学习对照，不参与构建

## 快速开始

```
cd tvboxpy
pip install requests python-mpv
python main.py
```

打包发布：`python build_exe.py`，产物 `tvboxpy/dist/tvboxpy.exe`。

## 历史

项目最早用 C + libmpv 直接实现（原型验证），后整体迁移到 Python 方案（`tvboxpy/`）并持续迭代至今；C 版原型已在仓库历史中保留。
