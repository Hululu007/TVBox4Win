# -*- coding: utf-8 -*-
"""绘制 TVBox4Win 应用图标（4x 超采样抗锯齿）
设计：深蓝夜色圆角底 + 复古电视机（橙色渐变屏幕 + 白色播放键）
      + V 形天线 + 右下角 Windows 四格徽标
产物: tvboxosc/assets/tvbox4win.ico（16~256 全尺寸）+ tvbox4win.png（512 预览）
"""
from PIL import Image, ImageDraw
import os

S = 4096          # 画布（超采样）
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tvboxosc", "assets")

# ---- 配色 ----
BG_TOP = (26, 34, 51)      # 深蓝夜色上
BG_BOT = (13, 18, 30)      # 下
BODY = (38, 48, 70)        # 机身
BODY_EDGE = (58, 70, 98)   # 机身亮边
SCREEN_A = (255, 122, 89)  # 主题橙
SCREEN_B = (255, 88, 50)   # 深橙
WHITE = (245, 247, 252)
PANE = (120, 190, 255)     # Windows 四格蓝


def lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def rounded_gradient_bg(draw, box, r, top, bot):
    """圆角矩形垂直渐变：逐行裁剪绘制"""
    x0, y0, x1, y1 = box
    for y in range(int(y0), int(y1) + 1):
        t = (y - y0) / (y1 - y0)
        draw.rectangle([x0, y, x1, y + 1], fill=lerp(top, bot, t))
    # 再叠加圆角形状 mask 效果 —— 用覆盖四角的方式太糙，
    # 这里直接换成：先画满渐变，再用 mask 贴到透明底
    return None


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ---- 背景：圆角矩形 + 垂直渐变（mask 法）----
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.rectangle([0, y, S, y + 1], fill=lerp(BG_TOP, BG_BOT, y / S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [80, 80, S - 80, S - 80], radius=int(S * 0.21), fill=255)
    img.paste(grad, (0, 0), mask)

    # ---- 天线 ----
    cx = S / 2
    ant_y = 560
    lw = int(S * 0.020)
    for dx, dy in [(-330, -430), (330, -430)]:
        d.line([cx, ant_y, cx + dx, ant_y + dy], fill=BODY_EDGE, width=lw * 3)
        d.ellipse([cx + dx - 130, ant_y + dy - 130, cx + dx + 130, ant_y + dy + 130],
                  fill=WHITE)

    # ---- 机身 ----
    bx0, by0, bx1, by1 = 620, 560, S - 620, 2900
    d.rounded_rectangle([bx0 - 60, by0 - 60, bx1 + 60, by1 + 60],
                        radius=340, fill=BODY_EDGE)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=300, fill=BODY)

    # ---- 屏幕：橙色渐变圆角矩形 ----
    sx0, sy0, sx1, sy1 = 820, 760, S - 820, 2440
    scr = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scr)
    for y in range(sy0, sy1):
        t = (y - sy0) / (sy1 - sy0)
        sd.rectangle([sx0, y, sx1, y + 1], fill=lerp(SCREEN_A, SCREEN_B, t))
    smask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(smask).rounded_rectangle([sx0, sy0, sx1, sy1], radius=220, fill=255)
    img.paste(scr, (0, 0), smask)
    # 屏幕高光：顶部一条极淡的弧形光带（不与播放键抢视觉）
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle(
        [sx0 + 120, sy0 + 90, sx1 - 120, sy0 + 200], radius=55, fill=(255, 255, 255, 36))
    hmask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(hmask).rounded_rectangle(
        [sx0 + 120, sy0 + 90, sx1 - 120, sy0 + 200], radius=55, fill=255)
    img.paste(hl, (0, 0), hmask)

    # ---- 播放键（白色圆 + 橙色三角，或直接白色三角）----
    pcx, pcy, pr = cx, (sy0 + sy1) / 2, 520
    d.ellipse([pcx - pr, pcy - pr, pcx + pr, pcy + pr], fill=(255, 255, 255, 235))
    tri = [(pcx - 130, pcy - 280), (pcx - 130, pcy + 280), (pcx + 320, pcy)]
    d.polygon(tri, fill=SCREEN_B)

    # ---- 底部支脚 ----
    d.rounded_rectangle([bx0 + 320, by1 + 40, bx0 + 700, by1 + 200], radius=60, fill=BODY)
    d.rounded_rectangle([bx1 - 700, by1 + 40, bx1 - 320, by1 + 200], radius=60, fill=BODY)

    # ---- 右下角 Windows 四格徽标 ----
    ps, gap, px0, py0 = 240, 40, 2540, 2620
    for i, (ox, oy) in enumerate([(0, 0), (ps + gap, 0), (0, ps + gap), (ps + gap, ps + gap)]):
        d.rounded_rectangle([px0 + ox, py0 + oy, px0 + ox + ps, py0 + oy + ps],
                            radius=40, fill=PANE)

    # ---- 缩小到各尺寸 ----
    os.makedirs(OUT, exist_ok=True)
    big = img.resize((1024, 1024), Image.LANCZOS)
    big.save(os.path.join(OUT, "tvbox4win.png"))
    big.resize((512, 512), Image.LANCZOS).save(
        os.path.join(os.path.dirname(OUT), "..", "tvbox4win_preview.png"))
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    big.save(os.path.join(OUT, "tvbox4win.ico"),
             format="ICO", sizes=[(s, s) for s in ico_sizes])
    print("OK:", os.path.join(OUT, "tvbox4win.ico"))


if __name__ == "__main__":
    main()
