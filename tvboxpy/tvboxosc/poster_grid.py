"""自适应海报网格（对应原版 V7GridLayoutManager：spanCount 均分屏宽）

原版 Android 端用 GridLayoutManager 按 spanCount 把整行宽度均分给每格，
海报撑满格子，不存在右侧留白。之前移植版用固定 6 列 + 固定字符宽海报，
宽窗口下右侧出现大段空白。这里改为：

- 按可用宽度算列数（单格目标 160~236px），列数随窗口宽度自适应
- 每列 grid_columnconfigure(weight=1, uniform=...) 均分整行 → 填满不留白
- 海报占位用像素定尺寸 Frame（pack_propagate(False)），图片按目标尺寸出图
"""
import tkinter as tk

from .theme import BG, FG, FG_DIM, POSTER_BG, FocusLabel, tv_font

RATIO = 320 / 244     # 海报高宽比（原版 ImgUtil 244x320，比 2:3 更方正饱满）
MIN_CELL = 200        # 单格最小宽度
MAX_CELL = 320        # 单格最大宽度（原版 1600 屏 5 列 → 每格 320）
MAX_COLS = 12
GAP = 4               # 格子四周留白
UNIFORM = "pgrid"     # 同一父容器内列宽均分的 uniform 组名

# 海报底部叠加条（对应原版 item_grid：片名/备注浮层）
BAR_BG = "#141A2E"    # 片名条底色
NOTE_BG = "#1A2138"   # 备注条底色


def layout(avail_w, min_cell=MIN_CELL, max_cell=MAX_CELL, max_cols=MAX_COLS):
    """按可用宽度返回 (cols, cell_w, poster_w, poster_h)"""
    avail_w = max(int(avail_w), 360)
    cols = max(2, min(max_cols, round(avail_w / 260)))
    while cols > 2 and avail_w / cols < min_cell:
        cols -= 1
    while cols < max_cols and avail_w / (cols + 1) >= min_cell \
            and avail_w / cols > max_cell:
        cols += 1
    cell_w = avail_w / cols
    poster_w = max(80, int(cell_w) - GAP * 2)
    poster_h = int(poster_w * RATIO)
    return cols, cell_w, poster_w, poster_h


def fill_columns(parent, cols):
    """让 0..cols-1 列均分父容器整行宽度"""
    for c in range(cols):
        parent.grid_columnconfigure(c, weight=1, uniform=UNIFORM)


def _trunc(s, px, per=15):
    """按像素宽估算单行可容纳的 CJK 字符数并截断"""
    n = max(4, px // per)
    return s[:n] + ("…" if len(s) > n else "")


def cell(parent, row, col, poster_w, poster_h, name, note="",
         on_open=None, cell_bg=BG, on_right_click=None, overlay=True):
    """创建一格：焦点承载层 + 像素定尺寸海报占位 + 片名 + 备注

    overlay=True  片名/备注叠加在海报底部半透明条（对应原版 item_grid）
    overlay=False 片名/备注放在海报下方（对应 item_search 搜索卡片）
    返回 (cell, focus, poster)：
    - focus  键盘焦点层（on_select 已接 on_open），调用方拿去做方向键导航
    - poster 海报 Label：图片就绪后 configure(image=photo) 即可（尺寸已定）
    """
    c = tk.Frame(parent, bg=cell_bg, padx=GAP, pady=GAP)
    c.grid(row=row, column=col, padx=0, pady=0, sticky="new")
    focus = FocusLabel(c, text="", bg=cell_bg, on_select=on_open)
    holder = tk.Frame(c, width=poster_w, height=poster_h, bg=POSTER_BG,
                      highlightthickness=0)
    holder.pack()
    holder.pack_propagate(False)   # 锁定像素尺寸：占位阶段就是最终布局
    poster = tk.Label(holder, text=(name[:1] or "🎬"), bg=POSTER_BG,
                      fg="#4A5578", font=tv_font(max(18, poster_w // 7)),
                      wraplength=poster_w - 8, justify="center")
    poster.place(x=0, y=0, relwidth=1.0, relheight=1.0)
    if overlay:
        if note:
            tk.Label(holder, text=_trunc(note, poster_w, 12), bg=NOTE_BG,
                     fg=FG_DIM, font=tv_font(9), anchor="w", padx=6
                     ).place(x=0, rely=1.0, y=-52, relwidth=1.0, height=24)
        tk.Label(holder, text=_trunc(name, poster_w), bg=BAR_BG, fg=FG,
                 font=tv_font(11), anchor="w", padx=6
                 ).place(x=0, rely=1.0, y=-28, relwidth=1.0, height=28)
    else:
        tk.Label(c, text=_trunc(name, poster_w), bg=cell_bg, fg=FG,
                 font=tv_font(11)).pack(fill="x")
        if note:
            tk.Label(c, text=_trunc(note, poster_w, 12), bg=cell_bg, fg=FG_DIM,
                     font=tv_font(9)).pack(fill="x")
    focus.place(in_=holder, relwidth=1.0, relheight=1.0)
    focus.lower()   # 沉到海报底下：不遮挡图片，只承接键盘焦点
    if on_open:
        click = lambda e: on_open()
        for w in (poster, holder):
            w.bind("<Button-1>", click)
    if on_right_click:
        for w in (poster, holder):
            w.bind("<Button-3>", on_right_click)
    focus.bind("<FocusIn>", lambda e: holder.configure(
        highlightthickness=3, highlightbackground="#3D7BFF"), add="+")
    focus.bind("<FocusOut>", lambda e: holder.configure(
        highlightthickness=0), add="+")
    return c, focus, poster
