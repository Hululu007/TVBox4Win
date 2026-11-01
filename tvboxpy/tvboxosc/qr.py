"""纯 Python 二维码生成（字节模式，纠错等级 L，版本 1~10）

推送页要把局域网地址显示成手机能扫的二维码。为了不新增第三方依赖
（打包体积、离线可用性），这里按 ISO/IEC 18004 实现最小可用子集：
字节模式、Reed-Solomon 纠错、8 种掩码自动择优。覆盖 1~10 版本意味着
最多 271 字节，足够容纳 http://192.168.x.x:9978/ 这类地址。

只负责生成模块矩阵（bool[y][x]），绘制交给 tkinter Canvas。
"""
import math

# 版本 → (每块纠错码字数, 各块数据码字数)；纠错等级 L
_VERSION_L = {
    1: (7, [19]),
    2: (10, [34]),
    3: (15, [55]),
    4: (20, [80]),
    5: (26, [108]),
    6: (18, [68, 68]),
    7: (20, [78, 78]),
    8: (24, [97, 97]),
    9: (30, [116, 116]),
    10: (18, [68, 68, 69, 69]),
}

# 对齐图案中心坐标（版本 1 没有对齐图案）
_ALIGN = {
    1: [],
    2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
    7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}

_ECL_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}


# ---------------------------------------------------------------- GF(256)
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _gen_poly(degree):
    """生成多项式（最高次项在前）：∏(x - α^i), i=0..degree-1"""
    poly = [1]
    for i in range(degree):
        root = _EXP[i]
        nxt = [0] * (len(poly) + 1)
        for j, coef in enumerate(poly):
            nxt[j] ^= coef
            nxt[j + 1] ^= _mul(coef, root)
        poly = nxt
    return poly


def _ecc(data, degree):
    """Reed-Solomon 余数 = 纠错码字"""
    gen = _gen_poly(degree)
    rem = [0] * degree
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        for i in range(degree):
            rem[i] ^= _mul(gen[i + 1], factor)
    return rem


# ---------------------------------------------------------------- 数据编码
def _count_bits(version):
    return 8 if version <= 9 else 16


def _data_capacity(version):
    return sum(_VERSION_L[version][1])


def _byte_capacity(version):
    """该版本可容纳的字节数（含模式指示符与字符计数）"""
    bits = _data_capacity(version) * 8 - 4 - _count_bits(version)
    return bits // 8


def _pick_version(payload, min_version=1):
    for v in range(max(1, min_version), 11):
        if len(payload) <= _byte_capacity(v):
            return v
    raise ValueError("二维码内容过长（最多 271 字节）")


def _encode_data(payload, version):
    capacity = _data_capacity(version)
    bits = []

    def put(value, length):
        for i in range(length - 1, -1, -1):
            bits.append((value >> i) & 1)

    put(0b0100, 4)                       # 字节模式
    put(len(payload), _count_bits(version))
    for byte in payload:
        put(byte, 8)
    # 终止符最多 4 bit，补到字节边界，再交替填 0xEC / 0x11
    put(0, min(4, capacity * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    data = [int("".join(map(str, bits[i:i + 8])), 2)
            for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < capacity:
        data.append(pad)
        pad = 0x11 if pad == 0xEC else 0xEC
    return data


def _codewords(payload, version):
    """数据码字 → 按块纠错 → 交织（返回最终码字序列）"""
    data = _encode_data(payload, version)
    ecc_degree, block_sizes = _VERSION_L[version]
    blocks, pos = [], 0
    for size in block_sizes:
        block = data[pos:pos + size]
        pos += size
        blocks.append([block, _ecc(block, ecc_degree)])
    out = []
    max_len = max(len(b[0]) for b in blocks)
    for i in range(max_len):
        for block in blocks:
            if i < len(block[0]):
                out.append(block[0][i])
    for i in range(ecc_degree):
        for block in blocks:
            out.append(block[1][i])
    return out


# ---------------------------------------------------------------- 矩阵
def _draw_finder(m, fn, x0, y0):
    size = len(m)
    for dy in range(-1, 8):
        for dx in range(-1, 8):
            x, y = x0 + dx, y0 + dy
            if not (0 <= x < size and 0 <= y < size):
                continue
            dark = (0 <= dx <= 6 and 0 <= dy <= 6 and
                    (dx in (0, 6) or dy in (0, 6) or
                     (2 <= dx <= 4 and 2 <= dy <= 4)))
            m[y][x] = bool(dark)
            fn[y][x] = True


def _draw_alignment(m, fn, cx, cy):
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            dark = max(abs(dx), abs(dy)) != 1
            m[cy + dy][cx + dx] = dark
            fn[cy + dy][cx + dx] = True


def _base_matrix(version):
    size = 17 + 4 * version
    m = [[False] * size for _ in range(size)]
    fn = [[False] * size for _ in range(size)]
    _draw_finder(m, fn, 0, 0)
    _draw_finder(m, fn, size - 7, 0)
    _draw_finder(m, fn, 0, size - 7)
    # 定时图案
    for i in range(8, size - 8):
        m[6][i] = m[i][6] = (i % 2 == 0)
        fn[6][i] = fn[i][6] = True
    # 对齐图案（避开三个定位图案）
    positions = _ALIGN.get(version, [])
    for cy in positions:
        for cx in positions:
            if (cx <= 8 and cy <= 8) or (cx <= 8 and cy >= size - 9) or \
                    (cx >= size - 9 and cy <= 8):
                continue
            _draw_alignment(m, fn, cx, cy)
    # 固定深色模块 + 格式信息占位（先标为功能模块，避免数据写入）
    m[size - 8][8] = True
    for i in range(9):
        fn[8][i] = fn[i][8] = True
    for i in range(8):
        fn[8][size - 1 - i] = True
        fn[size - 1 - i][8] = True
    fn[size - 8][8] = True
    # 版本信息（版本 7 起）
    if version >= 7:
        rem = version
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = (version << 12) | rem
        for i in range(18):
            bit = (bits >> i) & 1
            a, b = size - 11 + i % 3, i // 3
            m[b][a] = m[a][b] = bool(bit)
            fn[b][a] = fn[a][b] = True
    return m, fn


def _format_bits(mask, ecl="L"):
    data = (_ECL_BITS[ecl] << 3) | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return ((data << 10) | rem) ^ 0x5412


def _draw_format(m, mask, ecl="L"):
    size = len(m)
    bits = _format_bits(mask, ecl)

    def bit(i):
        return bool((bits >> i) & 1)

    for i in range(6):
        m[i][8] = bit(i)
    m[7][8], m[8][8], m[8][7] = bit(6), bit(7), bit(8)
    for i in range(9, 15):
        m[8][14 - i] = bit(i)
    for i in range(8):
        m[8][size - 1 - i] = bit(i)
    for i in range(8, 15):
        m[size - 15 + i][8] = bit(i)
    m[size - 8][8] = True


def _mask_bit(mask, x, y):
    if mask == 0:
        return (x + y) % 2 == 0
    if mask == 1:
        return y % 2 == 0
    if mask == 2:
        return x % 3 == 0
    if mask == 3:
        return (x + y) % 3 == 0
    if mask == 4:
        return (y // 2 + x // 3) % 2 == 0
    if mask == 5:
        return (x * y) % 2 + (x * y) % 3 == 0
    if mask == 6:
        return ((x * y) % 2 + (x * y) % 3) % 2 == 0
    return ((x + y) % 2 + (x * y) % 3) % 2 == 0


def _place_data(m, fn, codewords):
    size = len(m)
    bits = []
    for byte in codewords:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    idx = 0
    right = size - 1
    while right >= 1:
        if right == 6:          # 跳过竖向定时图案所在列
            right = 5
        upward = ((right + 1) & 2) == 0
        for vert in range(size):
            y = size - 1 - vert if upward else vert
            for j in range(2):
                x = right - j
                if fn[y][x] or idx >= len(bits):
                    continue
                m[y][x] = bool(bits[idx])
                idx += 1
        right -= 2


def _apply_mask(m, fn, mask):
    """数据掩码按规范作用于整个编码区（含不足一字节的剩余位）"""
    size = len(m)
    for y in range(size):
        for x in range(size):
            if not fn[y][x] and _mask_bit(mask, x, y):
                m[y][x] = not m[y][x]


# ---------------------------------------------------------------- 掩码评分
def _penalty(m):
    size = len(m)
    score = 0
    # 规则 1：行/列 5 个以上同色
    for rows in (m, [[m[y][x] for y in range(size)] for x in range(size)]):
        for row in rows:
            run = 1
            for i in range(1, size):
                if row[i] == row[i - 1]:
                    run += 1
                else:
                    if run >= 5:
                        score += 3 + run - 5
                    run = 1
            if run >= 5:
                score += 3 + run - 5
    # 规则 2：2x2 同色块
    for y in range(size - 1):
        for x in range(size - 1):
            c = m[y][x]
            if c == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    # 规则 3：类似定位图案的 1:1:3:1:1
    pats = ("10111010000", "00001011101")
    lines = []
    for y in range(size):
        lines.append("".join("1" if v else "0" for v in m[y]))
    for x in range(size):
        lines.append("".join("1" if m[y][x] else "0" for y in range(size)))
    for line in lines:
        for pat in pats:
            start = 0
            while True:
                pos = line.find(pat, start)
                if pos < 0:
                    break
                score += 40
                start = pos + 1
    # 规则 4：深色比例
    dark = sum(1 for row in m for v in row if v)
    total = size * size
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    score += max(0, k) * 10
    return score


def encode(text, ecl="L"):
    """文本 → (matrix, version, mask)。matrix[y][x] 为 True 表示深色。

    只支持字节模式，内容按 UTF-8 编码；超长抛 ValueError。
    """
    payload = str(text).encode("utf-8")
    version = _pick_version(payload)
    codewords = _codewords(payload, version)
    base, fn = _base_matrix(version)
    best = None
    for mask in range(8):
        m = [row[:] for row in base]
        _place_data(m, fn, codewords)
        _apply_mask(m, fn, mask)
        _draw_format(m, mask, ecl)
        score = _penalty(m)
        if best is None or score < best[0]:
            best = (score, m, mask)
    return best[1], version, best[2]


def size_for(text):
    """内容对应的模块边长（含静区前的矩阵尺寸）"""
    return 17 + 4 * _pick_version(str(text).encode("utf-8"))
