"""Picture Studio's shared pieces: an RGBA image, a PNG reader and writer, the export sizes,
and the Studio's own picture cache. Pure Python (zlib and struct only): the patcher ships no
Pillow, and Tk cannot write PNGs with alpha reliably.

Both renderers (src/pictures_fish.py, src/pictures_plant.py) draw with Image.draw, cutting
cells from the player's own game art (see docs/picture-studio-interface.md).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import os
from pathlib import Path
import re
import struct
import uuid
import zlib

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MARGIN = 4
SIZES = (("1x", 1), ("2x", 2), ("4x", 4))
MAX_SIDE = 8192                 # the largest picture the Studio writes (a custom size is capped)


class PictureError(Exception):
    """A picture that cannot be drawn or read, in words for the player."""


# ------------------------------------------------------------------ the image


class Image:
    """Straight (not premultiplied) 8-bit RGBA, rows top to bottom."""

    __slots__ = ("width", "height", "data")

    def __init__(self, width: int, height: int, data: bytearray | None = None) -> None:
        if width < 0 or height < 0:
            raise ValueError("an image cannot have a negative size")
        self.width, self.height = int(width), int(height)
        self.data = bytearray(self.width * self.height * 4) if data is None else bytearray(data)
        if len(self.data) != self.width * self.height * 4:
            raise ValueError("the pixel data does not fit the size")

    @classmethod
    def new(cls, width: int, height: int) -> "Image":
        return cls(width, height)

    @classmethod
    def from_png(cls, data: bytes) -> "Image":
        return decode_png(data)

    def to_png(self) -> bytes:
        return encode_png(self)

    def copy(self) -> "Image":
        return Image(self.width, self.height, self.data)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Image) and (self.width, self.height) == (other.width, other.height) \
            and self.data == other.data

    def __repr__(self) -> str:
        return f"Image({self.width}x{self.height})"

    def pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        at = (y * self.width + x) * 4
        return tuple(self.data[at:at + 4])

    def sub(self, x: int, y: int, w: int, h: int) -> "Image":
        """The w x h piece at (x, y); any part outside the image is transparent."""
        out = Image(w, h)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + w), min(self.height, y + h)
        if x1 <= x0 or y1 <= y0:
            return out
        row = (x1 - x0) * 4
        for yy in range(y0, y1):
            src = (yy * self.width + x0) * 4
            dst = ((yy - y) * w + (x0 - x)) * 4
            out.data[dst:dst + row] = self.data[src:src + row]
        return out

    def cell(self, cols: int, rows: int, index: int) -> "Image":
        """Cell `index` of a cols x rows grid (cells numbered across, then down; see cell_rect)."""
        left, top, right, bottom = cell_rect(self.width, self.height, cols, rows, index)
        return self.sub(left, top, right - left, bottom - top)

    def flipped(self) -> "Image":
        out = Image(self.width, self.height)
        stride = self.width * 4
        for y in range(self.height):
            row = self.data[y * stride:(y + 1) * stride]
            pixels = [row[i:i + 4] for i in range(0, stride, 4)]
            out.data[y * stride:(y + 1) * stride] = b"".join(reversed(pixels))
        return out

    def draw(self, src: "Image", x: int, y: int, alpha: int = 255, tint=None) -> None:
        """src over this image at (x, y), clipped. `alpha` multiplies src's alpha (SDL's
        per-surface alpha); `tint` (r, g, b) multiplies its colour (a colour mod)."""
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + src.width), min(self.height, y + src.height)
        if x1 <= x0 or y1 <= y0 or alpha <= 0:
            return
        alpha = min(255, int(alpha))
        # The games' blitter (Fish Tycoon 0x4041C0, 0x404D5E): each pixel's alpha a becomes
        # (a * A + 127) >> 8 under a surface alpha A below 255.
        weights = None if alpha == 255 else bytes((a * alpha + 127) >> 8 for a in range(256))
        sd, dd = src.data, self.data
        tr, tg, tb = tint if tint is not None else (255, 255, 255)
        for yy in range(y0, y1):
            s = ((yy - y) * src.width + (x0 - x)) * 4
            d = (yy * self.width + x0) * 4
            for _ in range(x1 - x0):
                sa = sd[s + 3]
                if sa:
                    if weights is not None:
                        sa = weights[sa]
                    r, g, b = sd[s], sd[s + 1], sd[s + 2]
                    if tint is not None:
                        r, g, b = r * tr // 255, g * tg // 255, b * tb // 255
                    if sa == 255:
                        dd[d], dd[d + 1], dd[d + 2], dd[d + 3] = r, g, b, 255
                    elif sa:
                        da = dd[d + 3]
                        if da == 0:
                            dd[d], dd[d + 1], dd[d + 2], dd[d + 3] = r, g, b, sa
                        else:
                            # straight-alpha "over": out = src + dst * (1 - src_a)
                            keep = da * (255 - sa)            # dst weight, x 255
                            oa255 = sa * 255 + keep           # out alpha, x 255
                            dd[d] = (r * sa * 255 + dd[d] * keep + oa255 // 2) // oa255
                            dd[d + 1] = (g * sa * 255 + dd[d + 1] * keep + oa255 // 2) // oa255
                            dd[d + 2] = (b * sa * 255 + dd[d + 2] * keep + oa255 // 2) // oa255
                            dd[d + 3] = (oa255 + 127) // 255
                s += 4
                d += 4

    def bbox(self) -> tuple[int, int, int, int] | None:
        """(left, top, right, bottom), right and bottom exclusive, of the pixels with any alpha."""
        w, h, data = self.width, self.height, self.data
        alphas = data[3::4]
        top = bottom = None
        left, right = w, 0
        for y in range(h):
            row = alphas[y * w:(y + 1) * w]
            if any(row):
                if top is None:
                    top = y
                bottom = y + 1
                first = next(i for i, a in enumerate(row) if a)
                last = w - next(i for i, a in enumerate(reversed(row)) if a)
                left, right = min(left, first), max(right, last)
        if top is None:
            return None
        return left, top, right, bottom

    def cropped(self, margin: int = MARGIN) -> "Image":
        """Cut to the drawn pixels plus `margin` transparent pixels each side; an image with
        nothing drawn is 1 x 1 transparent (plus the margin)."""
        box = self.bbox()
        if box is None:
            return Image(1 + 2 * margin, 1 + 2 * margin)
        left, top, right, bottom = box
        return self.sub(left - margin, top - margin, right - left + 2 * margin, bottom - top + 2 * margin)

    def scaled(self, factor: int) -> "Image":
        """Nearest neighbour, crisp: every pixel becomes factor x factor."""
        factor = int(factor)
        if factor < 1:
            raise ValueError("the scale must be 1 or more")
        if factor == 1:
            return self.copy()
        out = Image(self.width * factor, self.height * factor)
        stride = self.width * 4
        out_stride = stride * factor
        for y in range(self.height):
            row = self.data[y * stride:(y + 1) * stride]
            wide = b"".join(bytes(row[i:i + 4]) * factor for i in range(0, stride, 4))
            for k in range(factor):
                at = (y * factor + k) * out_stride
                out.data[at:at + out_stride] = wide
        return out

    def resized(self, width: int, height: int) -> "Image":
        """Smooth scaling to width x height: a linear (triangle) filter, widened when shrinking
        so every source pixel counts, on premultiplied colour so transparent edges stay clean."""
        width, height = int(width), int(height)
        if width < 1 or height < 1:
            raise ValueError("a picture must be at least 1 x 1")
        if (width, height) == (self.width, self.height):
            return self.copy()
        # premultiply into floats per channel
        n = self.width * self.height
        src = self.data
        pre = [0.0] * (n * 4)
        for i in range(n):
            a = src[i * 4 + 3]
            if a:
                f = a / 255.0
                pre[i * 4] = src[i * 4] * f
                pre[i * 4 + 1] = src[i * 4 + 1] * f
                pre[i * 4 + 2] = src[i * 4 + 2] * f
                pre[i * 4 + 3] = float(a)
        horizontal = _resample_weights(self.width, width)
        vertical = _resample_weights(self.height, height)
        # pass 1: rows
        mid = [0.0] * (width * self.height * 4)
        for y in range(self.height):
            base = y * self.width * 4
            out = y * width * 4
            for x, (first, weights) in enumerate(horizontal):
                r = g = b = a = 0.0
                at = base + first * 4
                for wgt in weights:
                    r += pre[at] * wgt
                    g += pre[at + 1] * wgt
                    b += pre[at + 2] * wgt
                    a += pre[at + 3] * wgt
                    at += 4
                o = out + x * 4
                mid[o], mid[o + 1], mid[o + 2], mid[o + 3] = r, g, b, a
        # pass 2: columns, then un-premultiply
        result = Image(width, height)
        dd = result.data
        row4 = width * 4
        for y, (first, weights) in enumerate(vertical):
            for x in range(width):
                r = g = b = a = 0.0
                at = first * row4 + x * 4
                for wgt in weights:
                    r += mid[at] * wgt
                    g += mid[at + 1] * wgt
                    b += mid[at + 2] * wgt
                    a += mid[at + 3] * wgt
                    at += row4
                o = (y * width + x) * 4
                alpha = int(a + 0.5)
                if alpha <= 0:
                    continue
                dd[o] = max(0, min(255, int(r / a * 255.0 + 0.5)))
                dd[o + 1] = max(0, min(255, int(g / a * 255.0 + 0.5)))
                dd[o + 2] = max(0, min(255, int(b / a * 255.0 + 0.5)))
                dd[o + 3] = min(255, alpha)
        return result

    def photo(self, tk_mod, master, max_side: int | None = None):
        """A Tk PhotoImage of this image (Tk reads PNG alpha), shrunk by whole steps to fit
        `max_side`, or blown up crisply when small."""
        image = self
        if max_side:
            biggest = max(1, image.width, image.height)
            if biggest > max_side:
                factor = -(-biggest // max_side)
                image = image.resized(max(1, image.width // factor), max(1, image.height // factor))
        return tk_mod.PhotoImage(master=master, data=base64.b64encode(image.to_png()))


def _resample_weights(src: int, dst: int) -> list[tuple[int, list[float]]]:
    """For each output position, (first source index, weights) of a triangle filter."""
    scale = dst / src
    support = max(1.0, 1.0 / scale)
    out = []
    for i in range(dst):
        centre = (i + 0.5) / scale
        lo = max(0, int(centre - support))
        hi = min(src, int(centre + support) + 1)
        weights = []
        for j in range(lo, hi):
            wgt = 1.0 - abs((j + 0.5 - centre) / support)
            weights.append(max(0.0, wgt))
        total = sum(weights)
        if total <= 0:
            nearest = min(src - 1, max(0, int(centre)))
            out.append((nearest, [1.0]))
            continue
        # trim zero weights at the ends
        while weights and weights[0] == 0.0:
            weights.pop(0)
            lo += 1
        while weights and weights[-1] == 0.0:
            weights.pop()
        out.append((lo, [w / total for w in weights]))
    return out


# ------------------------------------------------------------------ PNG


def _chunks(data: bytes):
    if not data.startswith(PNG_MAGIC):
        raise PictureError("not a PNG file")
    at = 8
    while at + 8 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, at)
        body = data[at + 8:at + 8 + length]
        if len(body) != length:
            raise PictureError("the PNG file is cut short")
        yield kind, body
        at += 12 + length
        if kind == b"IEND":
            return


def _unfilter(raw: bytes, width: int, height: int, bpp: int, row_bytes: int) -> bytearray:
    """Undo the PNG row filters (None, Sub, Up, Average, Paeth)."""
    out = bytearray(height * row_bytes)
    prev = bytearray(row_bytes)
    at = 0
    for y in range(height):
        kind = raw[at]
        line = bytearray(raw[at + 1:at + 1 + row_bytes])
        at += 1 + row_bytes
        if len(line) != row_bytes:
            raise PictureError("the PNG image data is cut short")
        if kind == 0:
            pass
        elif kind == 1:
            for i in range(bpp, row_bytes):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif kind == 2:
            line = bytearray((a + b) & 0xFF for a, b in zip(line, prev))
        elif kind == 3:
            for i in range(row_bytes):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(row_bytes):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                if pa <= pb and pa <= pc:
                    pred = a
                elif pb <= pc:
                    pred = b
                else:
                    pred = c
                line[i] = (line[i] + pred) & 0xFF
        else:
            raise PictureError(f"the PNG uses an unknown row filter ({kind})")
        out[y * row_bytes:(y + 1) * row_bytes] = line
        prev = line
    return out


def decode_png(data: bytes) -> Image:
    """Any non-interlaced PNG: grey, grey+alpha, RGB, RGBA (8 or 16 bits) or palette (1-8
    bits), with tRNS transparency. Returns straight RGBA."""
    header = None
    palette = b""
    trns = None
    idat = []
    for kind, body in _chunks(bytes(data)):
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
    if header is None:
        raise PictureError("the PNG has no header")
    width, height, depth, colour, _comp, _filter, interlace = header
    if interlace:
        raise PictureError("interlaced PNGs are not read")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    if channels is None or depth not in (1, 2, 4, 8, 16):
        raise PictureError("the PNG's colour format is not one the games use")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise PictureError(f"the PNG image data could not be unpacked ({exc})") from None
    bits = depth * channels
    row_bytes = (width * bits + 7) // 8
    bpp = max(1, bits // 8)
    rows = _unfilter(raw, width, height, bpp, row_bytes)
    image = Image(width, height)
    out = image.data
    if depth == 16:                      # keep the high byte of each sample
        rows = rows[0::2]
        row_bytes //= 2
        depth = 8
    if colour == 6 and depth == 8:
        out[:] = rows
    elif colour == 2 and depth == 8:
        key = struct.unpack(">HHH", trns) if trns and len(trns) >= 6 else None
        out[0::4] = rows[0::3]
        out[1::4] = rows[1::3]
        out[2::4] = rows[2::3]
        out[3::4] = b"\xff" * (width * height)
        if key is not None:
            key = bytes(k & 0xFF for k in key)
            for i in range(width * height):
                if out[i * 4:i * 4 + 3] == key:
                    out[i * 4 + 3] = 0
    elif colour == 4 and depth == 8:
        out[0::4] = rows[0::2]
        out[1::4] = rows[0::2]
        out[2::4] = rows[0::2]
        out[3::4] = rows[1::2]
    elif colour in (0, 3):
        if colour == 3:
            entries = len(palette) // 3
            alpha = list(trns or b"") + [255] * 256
            table = [bytes(palette[i * 3:i * 3 + 3]) + bytes([alpha[i]]) for i in range(entries)]
            table += [b"\0\0\0\xff"] * (256 - entries)
        else:
            levels = (1 << depth) - 1
            key = struct.unpack(">H", trns[:2])[0] if trns and len(trns) >= 2 else None
            table = []
            for v in range(256):
                grey = v * 255 // levels if v <= levels else 0
                table.append(bytes((grey, grey, grey, 0 if key == v else 255)))
        per_byte = 8 // depth
        mask = (1 << depth) - 1
        pixels = bytearray()
        for y in range(height):
            line = rows[y * row_bytes:(y + 1) * row_bytes]
            if depth == 8:
                values = line[:width]
            else:
                values = [(b >> (8 - depth * (k + 1))) & mask for b in line for k in range(per_byte)][:width]
            pixels += b"".join(table[v] for v in values)
        out[:] = pixels
    else:
        raise PictureError("the PNG's colour format is not one the games use")
    return image


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def encode_png(image: Image) -> bytes:
    """An 8-bit RGBA PNG (colour type 6), every row filtered None or Sub, whichever packs
    smaller (Up for rows that repeat)."""
    stride = image.width * 4
    raw = bytearray()
    prev = bytes(stride)
    for y in range(image.height):
        row = bytes(image.data[y * stride:(y + 1) * stride])
        if row == prev and y:
            raw += b"\x02" + bytes(stride)
        else:
            raw += b"\x00" + row
        prev = row
    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    return PNG_MAGIC + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) \
        + _chunk(b"IEND", b"")


# ------------------------------------------------------------------ export


def export(image: Image, *, scale: int = 1, size: tuple[int, int] | None = None, margin: int = MARGIN) -> Image:
    """Crop to the drawn pixels plus `margin` (0: none), then scale: `scale` crisply
    (nearest neighbour) or `size=(w, h)` smoothly; a 0 in size keeps the aspect ratio."""
    out = image.cropped(max(0, int(margin)))
    if size is not None:
        w, h = (int(v or 0) for v in size)
        if w <= 0 and h <= 0:
            raise PictureError("Give a width, a height or both.")
        if w <= 0:
            w = max(1, round(out.width * h / out.height))
        if h <= 0:
            h = max(1, round(out.height * w / out.width))
        if w > MAX_SIDE or h > MAX_SIDE:
            raise PictureError(f"A picture can be at most {MAX_SIDE} pixels wide or high.")
        return out.resized(w, h)
    scale = int(scale)
    if scale < 1 or out.width * scale > MAX_SIDE or out.height * scale > MAX_SIDE:
        raise PictureError(f"A picture can be at most {MAX_SIDE} pixels wide or high.")
    return out.scaled(scale)


def save_png(image: Image, path, **options) -> Path:
    """Export (see `export`) and write the PNG through a temporary file beside it, so a
    failed write never leaves half a file."""
    path = Path(path)
    data = export(image, **options).to_png()
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    return path


_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_file_name(text: str, limit: int = 80) -> str:
    """A label as a Windows file name (no extension): forbidden characters become "-", no
    trailing dot or space, never a reserved device name, never empty."""
    name = _BAD.sub("-", str(text)).strip().rstrip(". ")[:limit].rstrip(". ")
    if not name:
        name = "picture"
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name


def unique_path(folder: Path, stem: str, suffix: str = ".png") -> Path:
    """folder/stem.png, or "stem (2).png" and so on when that name is taken."""
    path = Path(folder) / f"{stem}{suffix}"
    n = 2
    while path.exists():
        path = Path(folder) / f"{stem} ({n}){suffix}"
        n += 1
    return path


# ------------------------------------------------------------------ what renderers return


@dataclass(frozen=True)
class SavedItem:
    id: str
    label: str
    location: str
    kind: str
    detail: str = ""


@dataclass(frozen=True)
class Option:
    key: object
    label: str
    patcher: bool = False


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    options: tuple
    default: object = None


@dataclass(frozen=True)
class Subject:
    key: str
    title: str
    fields: tuple
    note: str = ""


@dataclass(frozen=True)
class Draw:
    """One sprite draw, as a renderer plans it and the tests record it from the game: cell
    `cell` of a cols x rows sheet `file`, its top-left at (x, y), mirrored when `flip`, with
    surface alpha `alpha` (see Image.draw) and colour mod `tint` (None: none). `scale` is a
    percentage drawn the way Fish Tycoon's scaled draw does (see scaled_cell)."""
    file: str
    cols: int
    rows: int
    cell: int
    x: int
    y: int
    flip: bool = False
    alpha: int = 255
    tint: tuple | None = None
    scale: int = 100


def cell_rect(sheet_w: int, sheet_h: int, cols: int, rows: int, cell: int) -> tuple[int, int, int, int]:
    """The cell's (left, top, right, bottom), as Fish Tycoon's 0x4095F0 cuts it: cells of
    width // cols by height // rows, the column and row clamped to the grid."""
    cols, rows = max(1, cols), max(1, rows)
    cw, ch = sheet_w // cols, sheet_h // rows
    col, row = min(cell % cols, cols - 1), min(cell // cols, rows - 1)
    return cw * col, ch * row, cw * col + cw, ch * row + ch


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _ctrunc_half(value: int) -> int:
    """C's value / 2 (toward zero)."""
    return -((-value) // 2) if value < 0 else value // 2


def scaled_cell(sheet: "Image", rect: tuple, scale: int) -> tuple["Image", int, int]:
    """Fish Tycoon's scaled draw (0x408190): the scale is percent / 100 as a float; 0x407750
    centres the picture on its unscaled place using the rounded size (w x s + 0.5), and the
    blitter 0x4041C0 draws trunc(w x s) by trunc(h x s) pixels, each the source pixel at
    trunc(position), the position starting at the cell's left (top) and growing by w / width
    (h / height) one pixel at a time (in doubles, as the game's x87 code adds them). Returns
    the picture and how far its top-left moves."""
    left, top, right, bottom = rect
    w, h = right - left, bottom - top
    if scale == 100 or w <= 0 or h <= 0:
        return sheet.sub(left, top, w, h), 0, 0
    s = _f32(scale / 100.0)
    rounded_w, rounded_h = int(w * s + 0.5), int(h * s + 0.5)
    dx, dy = -_ctrunc_half(rounded_w - w), -_ctrunc_half(rounded_h - h)
    dw, dh = int(w * s), int(h * s)
    if dw <= 0 or dh <= 0:
        return Image(0, 0), dx, dy
    xs, pos, step = [], float(left), w / dw
    for _ in range(dw):
        xs.append(int(pos))
        pos += step
    ys, pos, step = [], float(top), h / dh
    for _ in range(dh):
        ys.append(int(pos))
        pos += step
    out = Image(dw, dh)
    src, dst, sw = sheet.data, out.data, sheet.width
    for j, sy in enumerate(ys):
        for i, sx in enumerate(xs):
            s_at = (sy * sw + sx) * 4
            d_at = (j * dw + i) * 4
            dst[d_at:d_at + 4] = src[s_at:s_at + 4]
    return out, dx, dy


class Sheets:
    """Decoded sheets, read once from a source with .read(name) -> bytes | None."""

    def __init__(self, source) -> None:
        self.source = source
        self._images: dict[str, Image] = {}

    def image(self, name: str) -> Image:
        key = name.casefold()
        if key not in self._images:
            data = self.source.read(name) if self.source is not None else None
            if data is None:
                raise PictureError(f"The game picture {name} was not found.")
            self._images[key] = decode_png(data)
        return self._images[key]

    def has(self, name: str) -> bool:
        try:
            self.image(name)
        except PictureError:
            return False
        return True


def composite(sheets: Sheets, plan, width: int, height: int, origin: tuple[int, int] = (0, 0)) -> Image:
    """Draw a plan (Draw calls, in order) on a transparent width x height canvas, each call
    moved by -origin."""
    canvas = Image(width, height)
    ox, oy = origin
    for call in plan:
        piece, dx, dy = _piece(sheets, call)
        canvas.draw(piece, call.x + dx - ox, call.y + dy - oy, call.alpha, call.tint)
    return canvas


def _piece(sheets: Sheets, call: Draw) -> tuple[Image, int, int]:
    key = ("piece", call.file.casefold(), call.cols, call.rows, call.cell, call.flip, call.scale)
    cached = sheets._images.get(key)
    if cached is None:
        sheet = sheets.image(call.file)
        rect = cell_rect(sheet.width, sheet.height, call.cols, call.rows, call.cell)
        piece, dx, dy = scaled_cell(sheet, rect, call.scale)
        if call.flip:
            piece = piece.flipped()
        cached = (piece, dx, dy)
        sheets._images[key] = cached
    return cached


def plan_bounds(sheets: Sheets, plan) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) the plan's cells cover."""
    left = top = 10 ** 9
    right = bottom = -10 ** 9
    for call in plan:
        piece, dx, dy = _piece(sheets, call)
        x, y = call.x + dx, call.y + dy
        left, top = min(left, x), min(top, y)
        right, bottom = max(right, x + piece.width), max(bottom, y + piece.height)
    if left > right:
        return 0, 0, 1, 1
    return left, top, right, bottom


def render_plan(sheets: Sheets, plan) -> Image:
    """A plan drawn on a canvas just big enough for it."""
    left, top, right, bottom = plan_bounds(sheets, plan)
    return composite(sheets, plan, right - left, bottom - top, (left, top))


# ------------------------------------------------------------------ the Studio's picture cache

CACHE_FOLDER = "Picture Studio Pictures"
CACHE_FORMAT = "Fish and Plant Tycoon Fix Patcher: Picture Studio Pictures"
CACHE_ROOT = Path(__file__).resolve().parents[1] / CACHE_FOLDER     # a test points it elsewhere


def picture_source(game: str, copies, required, patcher_files):
    """The Studio's own picture cache for a game (see breeding_pictures.picture_source),
    with the renderer's file list `required` and patcher art `patcher_files`."""
    import breeding_pictures as bp
    spec = bp.CacheSpec(root=CACHE_ROOT, format=CACHE_FORMAT, required=tuple(required),
                        patcher=dict(patcher_files))
    return bp.picture_source(game, copies, spec=spec)
