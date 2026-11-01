"""Picture Studio: the games' BMP, GIF and JPEG pictures, read in pure Python (the patcher ships no
Pillow), into picture_image.Image (straight RGBA).

* BMP (Fish Tycoon's backgrounds and meter bars, Plant Tycoon's SPLASH3_BG): uncompressed 1/4/8-bit
  palette, 16/24/32-bit, and RLE8/RLE4, as SDL_LoadBMP reads them; every pixel opaque (the games
  draw them without a colour key).
* GIF (Plant Tycoon's three): every frame as the GIF builds it (disposal methods, transparency),
  the transparent index clear. SDL_image (the game's loader) reads frame 1 only.
* JPEG (Plant Tycoon's backgrounds): baseline Huffman JPEG with restart markers, decoded the way
  the game's libjpeg-9.dll does with its default settings (SDL2_image changes none of the ones
  that matter): the "islow" integer IDCT (jidctint.c), YCbCr to RGB by libjpeg's tables
  (jdcolor.c), and, for a 2x2 or 2x1 subsampled picture, libjpeg 9's own way of growing the
  chroma: a 16x16 (or 16x8) IDCT of each chroma block instead of upsampling (jdmaster.c picks
  "IDCT scaling" when it can). tests/test_picture_formats.py decodes each picture with the game's
  own libjpeg-9.dll (run in Unicorn) and compares every pixel.
"""

from __future__ import annotations

import struct

from picture_image import Image, PictureError

# ------------------------------------------------------------------ dispatch


def kind(name: str, data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"BM":
        return "bmp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    return name.rsplit(".", 1)[-1].casefold()


def decode(name: str, data: bytes, frame: int = 0) -> Image:
    """Any picture file of the games: PNG, BMP, GIF (frame `frame`) or JPEG."""
    import picture_image as pi
    what = kind(name, data)
    if what == "png":
        return pi.decode_png(data)
    if what == "bmp":
        return decode_bmp(data)
    if what == "gif":
        frames = decode_gif(data)
        return frames[min(max(0, frame), len(frames) - 1)]
    if what in ("jpeg", "jpg"):
        return decode_jpeg(data)
    raise PictureError(f"{name} is not a picture the Studio reads.")


def frame_count(name: str, data: bytes) -> int:
    return len(decode_gif(data)) if kind(name, data) == "gif" else 1


READABLE = (".png", ".bmp", ".gif", ".jpg", ".jpeg")

# ------------------------------------------------------------------ BMP


def decode_bmp(data: bytes) -> Image:
    data = bytes(data)
    if data[:2] != b"BM" or len(data) < 54:
        raise PictureError("not a BMP picture")
    offset = struct.unpack_from("<I", data, 10)[0]
    header = struct.unpack_from("<I", data, 14)[0]
    if header == 12:
        width, height, _planes, bpp = struct.unpack_from("<HHHH", data, 18)
        comp, colours, entry = 0, 0, 3
    else:
        width, height, _planes, bpp, comp = struct.unpack_from("<iiHHI", data, 18)
        colours = struct.unpack_from("<I", data, 46)[0] if header >= 40 else 0
        entry = 4
    top_down = height < 0
    height = abs(height)
    palette = []
    if bpp <= 8:
        count = colours or (1 << bpp)
        at = 14 + header
        for i in range(count):
            b, g, r = data[at + i * entry:at + i * entry + 3]
            palette.append(bytes((r, g, b, 255)))
        palette += [b"\0\0\0\xff"] * (256 - len(palette))
    out = Image(width, height)
    rows = []
    if comp in (1, 2):                                   # RLE8 / RLE4: palette indices
        rows = _bmp_rle(data, offset, width, height, 8 if comp == 1 else 4)
    elif comp in (0, 3):
        stride = ((width * bpp + 31) // 32) * 4
        masks = None
        if comp == 3:
            masks = struct.unpack_from("<III", data, 54)
        for y in range(height):
            start = offset + y * stride
            line = data[start:start + stride]
            if bpp <= 8:
                per = 8 // bpp
                mask = (1 << bpp) - 1
                if bpp == 8:
                    rows.append(line[:width])
                else:
                    rows.append(bytes((line[x // per] >> (8 - bpp * (x % per + 1))) & mask for x in range(width)))
            else:
                rows.append(_bmp_true(line, width, bpp, masks))
    else:
        raise PictureError("a compressed BMP the games do not use")
    for y, row in enumerate(rows):
        oy = y if top_down else height - 1 - y
        at = oy * width * 4
        if bpp <= 8 or comp in (1, 2):
            out.data[at:at + width * 4] = b"".join(palette[v] for v in row)
        else:
            out.data[at:at + width * 4] = row
    return out


def _bmp_true(line: bytes, width: int, bpp: int, masks) -> bytes:
    px = bytearray(width * 4)
    if bpp == 24:
        px[0::4] = line[2:width * 3:3]
        px[1::4] = line[1:width * 3:3]
        px[2::4] = line[0:width * 3:3]
        px[3::4] = b"\xff" * width
        return bytes(px)
    if bpp == 32 and masks is None:
        px[0::4] = line[2:width * 4:4]
        px[1::4] = line[1:width * 4:4]
        px[2::4] = line[0:width * 4:4]
        px[3::4] = b"\xff" * width
        return bytes(px)
    rm, gm, bm = masks or ((0x7C00, 0x3E0, 0x1F) if bpp == 16 else (0xFF0000, 0xFF00, 0xFF))
    step = bpp // 8
    for x in range(width):
        v = int.from_bytes(line[x * step:x * step + step], "little")
        for c, m in enumerate((rm, gm, bm)):
            if m:
                shift = (m & -m).bit_length() - 1
                top = m >> shift
                px[x * 4 + c] = ((v & m) >> shift) * 255 // top
        px[x * 4 + 3] = 255
    return bytes(px)


def _bmp_rle(data: bytes, at: int, width: int, height: int, bits: int) -> list:
    rows = [bytearray(width) for _ in range(height)]
    x = y = 0
    while at + 1 < len(data) and y < height:
        n, v = data[at], data[at + 1]
        at += 2
        if n:
            for k in range(n):
                value = v if bits == 8 else (v >> 4 if k % 2 == 0 else v & 15)
                if x < width:
                    rows[y][x] = value
                x += 1
        elif v == 0:
            x, y = 0, y + 1
        elif v == 1:
            break
        elif v == 2:
            x, y = x + data[at], y + data[at + 1]
            at += 2
        else:
            count = v
            raw = data[at:at + (count if bits == 8 else (count + 1) // 2)]
            for k in range(count):
                value = raw[k] if bits == 8 else (raw[k // 2] >> 4 if k % 2 == 0 else raw[k // 2] & 15)
                if x < width and y < height:
                    rows[y][x] = value
                x += 1
            used = len(raw)
            at += used + (used & 1)
    return [bytes(r) for r in rows]


# ------------------------------------------------------------------ GIF


def decode_gif(data: bytes) -> list:
    """Every frame of a GIF, each the whole logical screen as the GIF builds it up."""
    data = bytes(data)
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        raise PictureError("not a GIF picture")
    width, height, flags, _bg, _aspect = struct.unpack_from("<HHBBB", data, 6)
    at = 13
    global_table = None
    if flags & 0x80:
        size = 3 << ((flags & 7) + 1)
        global_table = data[at:at + size]
        at += size
    canvas = Image(width, height)
    frames = []
    transparent, disposal = None, 0
    while at < len(data):
        block = data[at]
        at += 1
        if block == 0x3B:
            break
        if block == 0x21:                                  # extension
            label = data[at]
            at += 1
            if label == 0xF9 and data[at] >= 4:
                packed = data[at + 1]
                disposal = (packed >> 2) & 7
                transparent = data[at + 4] if packed & 1 else None
            while data[at]:
                at += data[at] + 1
            at += 1
            continue
        if block != 0x2C:
            raise PictureError("the GIF is damaged")
        left, top, w, h, packed = struct.unpack_from("<HHHHB", data, at)
        at += 9
        table = global_table
        if packed & 0x80:
            size = 3 << ((packed & 7) + 1)
            table = data[at:at + size]
            at += size
        interlaced = bool(packed & 0x40)
        min_code = data[at]
        at += 1
        chunks = bytearray()
        while data[at]:
            chunks += data[at + 1:at + 1 + data[at]]
            at += data[at] + 1
        at += 1
        indices = _lzw(bytes(chunks), min_code, w * h)
        if interlaced:
            order = [r for start, step in ((0, 8), (4, 8), (2, 4), (1, 2)) for r in range(start, h, step)]
            rows = [indices[i * w:(i + 1) * w] for i in range(h)]
            fixed = [b""] * h
            for i, r in enumerate(order):
                fixed[r] = rows[i]
            indices = b"".join(fixed)
        before = canvas.copy() if disposal == 3 else None
        table = table or bytes(768)
        for yy in range(h):
            cy = top + yy
            if not 0 <= cy < height:
                continue
            for xx in range(w):
                cx = left + xx
                v = indices[yy * w + xx] if yy * w + xx < len(indices) else 0
                if v == transparent or not 0 <= cx < width:
                    continue
                o = (cy * width + cx) * 4
                canvas.data[o:o + 4] = bytes((table[v * 3], table[v * 3 + 1], table[v * 3 + 2], 255))
        frames.append(canvas.copy())
        if disposal == 2:
            for yy in range(top, min(height, top + h)):
                o = (yy * width + left) * 4
                canvas.data[o:o + 4 * max(0, min(w, width - left))] = bytes(4 * max(0, min(w, width - left)))
        elif disposal == 3 and before is not None:
            canvas = before
        transparent, disposal = None, 0
    if not frames:
        raise PictureError("the GIF has no picture")
    return frames


def _lzw(data: bytes, min_code: int, limit: int) -> bytes:
    clear, end = 1 << min_code, (1 << min_code) + 1
    size = min_code + 1
    table = [bytes((i,)) for i in range(clear)] + [b"", b""]
    out = bytearray()
    prev = None
    bits = value = 0
    for byte in data:
        value |= byte << bits
        bits += 8
        while bits >= size:
            code = value & ((1 << size) - 1)
            value >>= size
            bits -= size
            if code == clear:
                table = table[:clear + 2]
                size = min_code + 1
                prev = None
                continue
            if code == end:
                return bytes(out[:limit])
            if prev is None:
                entry = table[code]
            elif code < len(table):
                entry = table[code]
                table.append(prev + entry[:1])
            else:
                entry = prev + prev[:1]
                table.append(entry)
            out += entry
            prev = entry
            if len(table) == (1 << size) and size < 12:
                size += 1
    return bytes(out[:limit])


# ------------------------------------------------------------------ JPEG

_ZIGZAG = (0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6,
           7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38,
           31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63)
CONST_BITS, PASS1_BITS = 13, 2
F_0_298631336, F_0_390180644, F_0_541196100, F_0_765366865 = 2446, 3196, 4433, 6270
F_0_899976223, F_1_175875602, F_1_501321110, F_1_847759065 = 7373, 9633, 12299, 15137
F_1_961570560, F_2_053119869, F_2_562915447, F_3_072711026 = 16069, 16819, 20995, 25172


def _limit(m: int) -> int:
    """libjpeg's IDCT range limit for a value masked to 10 bits: those bits as a signed number,
    plus 128, clamped to 0..255."""
    x = ((m + 512) & 1023) - 512 + 128
    return 0 if x < 0 else 255 if x > 255 else x


_RL = bytes(_limit(m) for m in range(1024))          # indexed by value & 1023


def _islow(v0, v1, v2, v3, v4, v5, v6, v7):
    """The 8-point islow kernel (jidctint.c): the eight sums before the final descale."""
    z1 = (v2 + v6) * F_0_541196100
    tmp2 = z1 - v6 * F_1_847759065
    tmp3 = z1 + v2 * F_0_765366865
    tmp0 = (v0 + v4) << CONST_BITS
    tmp1 = (v0 - v4) << CONST_BITS
    t10, t13, t11, t12 = tmp0 + tmp3, tmp0 - tmp3, tmp1 + tmp2, tmp1 - tmp2
    z1, z2, z3, z4 = v7 + v1, v5 + v3, v7 + v3, v5 + v1
    z5 = (z3 + z4) * F_1_175875602
    z1 *= -F_0_899976223
    z2 *= -F_2_562915447
    z3 = z3 * -F_1_961570560 + z5
    z4 = z4 * -F_0_390180644 + z5
    tmp0 = v7 * F_0_298631336 + z1 + z3
    tmp1 = v5 * F_2_053119869 + z2 + z4
    tmp2 = v3 * F_3_072711026 + z2 + z3
    tmp3 = v1 * F_1_501321110 + z1 + z4
    return (t10 + tmp3, t11 + tmp2, t12 + tmp1, t13 + tmp0, t13 - tmp0, t12 - tmp1, t11 - tmp2, t10 - tmp3)


def _idct_8x8(coef, q) -> list:
    """jpeg_idct_islow: 8 rows of 8 samples."""
    ws = [0] * 64
    r1, s1 = 1 << (CONST_BITS - PASS1_BITS - 1), CONST_BITS - PASS1_BITS
    for c in range(8):
        d = [coef[8 * k + c] * q[8 * k + c] for k in range(8)]
        if not (d[1] or d[2] or d[3] or d[4] or d[5] or d[6] or d[7]):
            dc = d[0] << PASS1_BITS
            for k in range(8):
                ws[8 * k + c] = dc
            continue
        for k, v in enumerate(_islow(*d)):
            ws[8 * k + c] = (v + r1) >> s1
    out = []
    rl = _RL
    r2, s2 = 1 << (CONST_BITS + PASS1_BITS + 2), CONST_BITS + PASS1_BITS + 3
    for row in range(8):
        w = ws[row * 8:row * 8 + 8]
        if not (w[1] or w[2] or w[3] or w[4] or w[5] or w[6] or w[7]):
            out.append([rl[((w[0] + (1 << (PASS1_BITS + 2))) >> (PASS1_BITS + 3)) & 1023]] * 8)
            continue
        out.append([rl[((v + r2) >> s2) & 1023] for v in _islow(*w)])
    return out


def _f13(x: float) -> int:
    return int(x * (1 << CONST_BITS) + 0.5)


K16 = {name: _f13(v) for name, v in (
    ("c4", 1.306562965), ("c14", 0.275899379), ("c2", 1.387039845), ("c2_10", 0.601344887),
    ("c10_14", 0.509795579), ("c3", 1.353318001), ("c5", 1.247225013), ("c7", 1.093201867),
    ("c9", 0.897167586), ("c11", 0.666655658), ("c13", 0.410524528), ("o1", 2.286341144),
    ("o2", 1.835730603), ("c15", 0.138617169), ("o3", 0.071888074), ("o4", 1.125726048),
    ("c1", 1.407403738), ("o5", 0.766367282), ("o6", 1.971951411), ("o7", 1.065388962),
    ("o8", 3.141271809))}


def _k16(v0, v1, v2, v3, v4, v5, v6, v7, fudge):
    """libjpeg 9's 16-point kernel (jpeg_idct_16x16, jidctint.c): the sixteen sums before the
    final descale, `fudge` added to the DC term."""
    k = K16
    tmp0 = (v0 << CONST_BITS) + fudge
    tmp1 = v4 * k["c4"]
    tmp2 = v4 * F_0_541196100
    tmp10, tmp11, tmp12, tmp13 = tmp0 + tmp1, tmp0 - tmp1, tmp0 + tmp2, tmp0 - tmp2
    z3 = v2 - v6
    z4 = z3 * k["c14"]
    z3 = z3 * k["c2"]
    tmp0 = z3 + v6 * F_2_562915447
    tmp1 = z4 + v2 * F_0_899976223
    tmp2 = z3 - v2 * k["c2_10"]
    tmp3 = z4 - v6 * k["c10_14"]
    tmp20, tmp27 = tmp10 + tmp0, tmp10 - tmp0
    tmp21, tmp26 = tmp12 + tmp1, tmp12 - tmp1
    tmp22, tmp25 = tmp13 + tmp2, tmp13 - tmp2
    tmp23, tmp24 = tmp11 + tmp3, tmp11 - tmp3
    z1, z2, z3, z4 = v1, v3, v5, v7
    tmp11 = z1 + z3
    tmp1 = (z1 + z2) * k["c3"]
    tmp2 = tmp11 * k["c5"]
    tmp3 = (z1 + z4) * k["c7"]
    tmp10 = (z1 - z4) * k["c9"]
    tmp11 = tmp11 * k["c11"]
    tmp12 = (z1 - z2) * k["c13"]
    tmp0 = tmp1 + tmp2 + tmp3 - z1 * k["o1"]
    tmp13 = tmp10 + tmp11 + tmp12 - z1 * k["o2"]
    z1 = (z2 + z3) * k["c15"]
    tmp1 += z1 + z2 * k["o3"]
    tmp2 += z1 - z3 * k["o4"]
    z1 = (z3 - z2) * k["c1"]
    tmp11 += z1 - z3 * k["o5"]
    tmp12 += z1 + z2 * k["o6"]
    z2 += z4
    z1 = z2 * -k["c11"]
    tmp1 += z1
    tmp3 += z1 + z4 * k["o7"]
    z2 = z2 * -k["c5"]
    tmp10 += z2 + z4 * k["o8"]
    tmp12 += z2
    z2 = (z3 + z4) * -k["c3"]
    tmp2 += z2
    tmp3 += z2
    z2 = (z4 - z3) * k["c13"]
    tmp10 += z2
    tmp11 += z2
    return (tmp20 + tmp0, tmp21 + tmp1, tmp22 + tmp2, tmp23 + tmp3, tmp24 + tmp10, tmp25 + tmp11, tmp26 + tmp12,
            tmp27 + tmp13, tmp27 - tmp13, tmp26 - tmp12, tmp25 - tmp11, tmp24 - tmp10, tmp23 - tmp3,
            tmp22 - tmp2, tmp21 - tmp1, tmp20 - tmp0)


def _idct_16x16(coef, q) -> list:
    """jpeg_idct_16x16: 16 rows of 16 samples from one 8 x 8 block (libjpeg 9's chroma for a
    2 x 2 subsampled picture)."""
    ws = [0] * 128                                   # 16 rows of 8
    s1 = CONST_BITS - PASS1_BITS
    f1 = 1 << (CONST_BITS - PASS1_BITS - 1)
    for c in range(8):
        d = [coef[8 * k + c] * q[8 * k + c] for k in range(8)]
        for k, v in enumerate(_k16(*d, f1)):
            ws[8 * k + c] = v >> s1
    out = []
    rl = _RL
    s2 = CONST_BITS + PASS1_BITS + 3
    f2 = (1 << (PASS1_BITS + 2)) << CONST_BITS
    for row in range(16):
        w = ws[row * 8:row * 8 + 8]
        out.append([rl[(v >> s2) & 1023] for v in _k16(*w, f2)])
    return out


class _Bits:
    __slots__ = ("data", "at", "value", "count", "marker")

    def __init__(self, data: bytes, at: int) -> None:
        self.data, self.at, self.value, self.count, self.marker = data, at, 0, 0, None

    def fill(self) -> None:
        data = self.data
        self.value &= (1 << self.count) - 1             # only the bits not read yet
        while self.count <= 24:
            byte = 0
            if self.marker is None and self.at < len(data):
                byte = data[self.at]
                if byte == 0xFF:
                    nxt = data[self.at + 1] if self.at + 1 < len(data) else 0
                    if nxt == 0:
                        self.at += 2
                    else:
                        self.marker = nxt
                        byte = 0
                else:
                    self.at += 1
            self.value = (self.value << 8) | byte
            self.count += 8

    def bits(self, n: int) -> int:
        if n == 0:
            return 0
        if self.count < n:
            self.fill()
        self.count -= n
        return (self.value >> self.count) & ((1 << n) - 1)

    def restart(self) -> None:
        self.value = self.count = 0
        if self.marker is not None:
            self.at += 2                      # the RSTn marker
            self.marker = None
        else:                                 # find it
            while self.at + 1 < len(self.data) and not (self.data[self.at] == 0xFF and 0xD0 <= self.data[self.at + 1] <= 0xD7):
                self.at += 1
            self.at += 2


def _huffman_table(counts: bytes, symbols: bytes) -> dict:
    """(length, code) -> symbol, and a 9-bit lookup."""
    table, code, k = {}, 0, 0
    for length in range(1, 17):
        for _ in range(counts[length - 1]):
            table[(length, code)] = symbols[k]
            code += 1
            k += 1
        code <<= 1
    fast = [None] * 512
    for (length, c), sym in table.items():
        if length <= 9:
            base = c << (9 - length)
            for i in range(1 << (9 - length)):
                fast[base + i] = (length, sym)
    maxcode = [-1] * 18
    valptr, mincode = [0] * 17, [0] * 17
    code = k = 0
    for length in range(1, 17):
        n = counts[length - 1]
        if n:
            valptr[length], mincode[length] = k, code
            code += n
            k += n
            maxcode[length] = code - 1
        code <<= 1
    return {"fast": fast, "maxcode": maxcode, "valptr": valptr, "mincode": mincode, "symbols": symbols}


def _decode_symbol(bits: _Bits, table: dict) -> int:
    if bits.count < 16:
        bits.fill()
    peek = (bits.value >> (bits.count - 9)) & 511
    hit = table["fast"][peek]
    if hit is not None:
        bits.count -= hit[0]
        return hit[1]
    code = 0
    for length in range(1, 17):
        code = (code << 1) | bits.bits(1)
        if code <= table["maxcode"][length]:
            return table["symbols"][table["valptr"][length] + code - table["mincode"][length]]
    raise PictureError("the JPEG's data is damaged")


def _extend(v: int, n: int) -> int:
    return v - (1 << n) + 1 if n and v < (1 << (n - 1)) else v


def decode_jpeg(data: bytes) -> Image:
    data = bytes(data)
    if data[:2] != b"\xff\xd8":
        raise PictureError("not a JPEG picture")
    quant, dc_tables, ac_tables = {}, {}, {}
    comps, restart = [], 0
    width = height = 0
    at = 2
    coefs = None
    while at < len(data):
        if data[at] != 0xFF:
            at += 1
            continue
        marker = data[at + 1]
        at += 2
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xD9:
            break
        length = struct.unpack_from(">H", data, at)[0]
        body = data[at + 2:at + length]
        if marker == 0xDB:
            k = 0
            while k < len(body):
                pq, tq = body[k] >> 4, body[k] & 15
                k += 1
                if pq:
                    values = struct.unpack_from(">64H", body, k)
                    k += 128
                else:
                    values = body[k:k + 64]
                    k += 64
                table = [0] * 64
                for i, v in enumerate(values):
                    table[_ZIGZAG[i]] = v
                quant[tq] = table
        elif marker == 0xC4:
            k = 0
            while k < len(body):
                tc, th = body[k] >> 4, body[k] & 15
                counts = body[k + 1:k + 17]
                n = sum(counts)
                symbols = body[k + 17:k + 17 + n]
                (ac_tables if tc else dc_tables)[th] = _huffman_table(counts, symbols)
                k += 17 + n
        elif marker == 0xC0 or marker == 0xC1:
            _p, height, width, nf = struct.unpack_from(">BHHB", body, 0)
            comps = [{"id": body[6 + 3 * i], "h": body[7 + 3 * i] >> 4, "v": body[7 + 3 * i] & 15,
                      "q": body[8 + 3 * i]} for i in range(nf)]
        elif marker in (0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            raise PictureError("a JPEG kind the games do not use (progressive or arithmetic)")
        elif marker == 0xDD:
            restart = struct.unpack_from(">H", body, 0)[0]
        elif marker == 0xDA:
            coefs = _scan(data, at + length, body, comps, width, height, dc_tables, ac_tables, restart)
            break
        at += length
    if coefs is None:
        raise PictureError("the JPEG has no picture")
    return _to_rgb(coefs, quant, width, height)


def _scan(data, at, body, comps, width, height, dc_tables, ac_tables, restart):
    ns = body[0]
    order = []
    for i in range(ns):
        cid, tables = body[1 + 2 * i], body[2 + 2 * i]
        comp = next(c for c in comps if c["id"] == cid)
        comp["dc"], comp["ac"] = dc_tables[tables >> 4], ac_tables[tables & 15]
        order.append(comp)
    hmax, vmax = max(c["h"] for c in comps), max(c["v"] for c in comps)
    mcux, mcuy = -(-width // (8 * hmax)), -(-height // (8 * vmax))
    for c in comps:
        c["bw"], c["bh"] = mcux * c["h"], mcuy * c["v"]
        c["blocks"] = [None] * (c["bw"] * c["bh"])
        c["pred"] = 0
    bits = _Bits(data, at)
    single = len(order) == 1
    if single:                                     # a non-interleaved scan: the component's own blocks
        c = order[0]
        cw = -(-(-(-width * c["h"] // hmax)) // 8)
        ch = -(-(-(-height * c["v"] // vmax)) // 8)
        units = [(c, bx, by) for by in range(ch) for bx in range(cw)]
        groups = [[u] for u in units]
    else:
        groups = ([(c, mx * c["h"] + x, my * c["v"] + y) for c in order for y in range(c["v"]) for x in range(c["h"])]
                  for my in range(mcuy) for mx in range(mcux))
    zz = _ZIGZAG
    for n, group in enumerate(groups):
        if restart and n and n % restart == 0:
            bits.restart()
            for c in comps:
                c["pred"] = 0
        for c, bx, by in group:
            block = [0] * 64
            t = _decode_symbol(bits, c["dc"])
            diff = _extend(bits.bits(t), t) if t else 0
            c["pred"] += diff
            block[0] = c["pred"]
            k = 1
            ac = c["ac"]
            while k < 64:
                rs = _decode_symbol(bits, ac)
                r, s = rs >> 4, rs & 15
                if s == 0:
                    if r == 15:
                        k += 16
                        continue
                    break
                k += r
                if k > 63:
                    break
                block[zz[k]] = _extend(bits.bits(s), s)
                k += 1
            c["blocks"][by * c["bw"] + bx] = block
    return comps


def _to_rgb(comps, quant, width, height) -> Image:
    """Each component's blocks through the IDCT libjpeg 9 picks (8 x 8, or 16 x 16 for a chroma
    component at half the luma's sampling both ways), then YCbCr (or grey) to RGB."""
    hmax, vmax = max(c["h"] for c in comps), max(c["v"] for c in comps)
    planes = []
    for c in comps:
        q = quant[c["q"]]
        ratio = (hmax // c["h"], vmax // c["v"])
        if ratio == (1, 1):
            idct, size = _idct_8x8, 8
        elif ratio == (2, 2):
            idct, size = _idct_16x16, 16
        else:
            raise PictureError("a JPEG subsampling the games do not use")
        pw = c["bw"] * size
        plane = bytearray(pw * c["bh"] * size)
        for by in range(c["bh"]):
            for bx in range(c["bw"]):
                block = c["blocks"][by * c["bw"] + bx]
                if block is None:
                    continue
                for r, values in enumerate(idct(block, q)):
                    at = (by * size + r) * pw + bx * size
                    plane[at:at + size] = bytes(values)
        planes.append((plane, pw))
    out = Image(width, height)
    data = out.data
    if len(comps) == 1:
        plane, pw = planes[0]
        for y in range(height):
            row = plane[y * pw:y * pw + width]
            at = y * width * 4
            for ch in range(3):
                data[at + ch:at + width * 4:4] = row
            data[at + 3:at + width * 4:4] = b"\xff" * width
        return out
    (yp, yw), (cbp, cbw), (crp, crw) = planes[:3]
    cr_r, cb_b, cr_g, cb_g = _YCC
    for y in range(height):
        at = y * width * 4
        ya, cba, cra = y * yw, y * cbw, y * crw
        for x in range(width):
            lum, cb, cr = yp[ya + x], cbp[cba + x], crp[cra + x]
            r = lum + cr_r[cr]
            g = lum + ((cb_g[cb] + cr_g[cr]) >> 16)
            b = lum + cb_b[cb]
            o = at + 4 * x
            data[o] = 0 if r < 0 else 255 if r > 255 else r
            data[o + 1] = 0 if g < 0 else 255 if g > 255 else g
            data[o + 2] = 0 if b < 0 else 255 if b > 255 else b
            data[o + 3] = 255
    return out


def _ycc_tables():
    """jdcolor.c's build_ycc_rgb_table (SCALEBITS 16)."""
    def fix(v):
        return int(v * 65536 + 0.5)
    half = 1 << 15
    cr_r = [(fix(1.40200) * (i - 128) + half) >> 16 for i in range(256)]
    cb_b = [(fix(1.77200) * (i - 128) + half) >> 16 for i in range(256)]
    cr_g = [-fix(0.71414) * (i - 128) for i in range(256)]
    cb_g = [-fix(0.34414) * (i - 128) + half for i in range(256)]
    return cr_r, cb_b, cr_g, cb_g


_YCC = _ycc_tables()
