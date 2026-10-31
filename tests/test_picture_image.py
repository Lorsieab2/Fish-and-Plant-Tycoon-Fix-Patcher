"""Picture Studio's shared image module: the PNG reader and writer, compositing, cropping and
the export sizes (1x/2x/4x crisp, a custom size smooth), and the Studio's own picture cache."""

from __future__ import annotations

import struct
import zlib

import pytest

import breeding_pictures
import picture_image as pi
from picture_image import Image


def _png(width, height, colour, depth, rows: list[bytes], extra=b"") -> bytes:
    raw = b"".join(b"\0" + r for r in rows)
    return (pi.PNG_MAGIC + pi._chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, 0))
            + extra + pi._chunk(b"IDAT", zlib.compress(raw)) + pi._chunk(b"IEND", b""))


def _checker(w=5, h=3) -> Image:
    image = Image(w, h)
    for y in range(h):
        for x in range(w):
            at = (y * w + x) * 4
            image.data[at:at + 4] = bytes((x * 40 % 256, y * 80 % 256, 7, (x + y) * 30 % 256))
    return image


def test_png_round_trip_keeps_every_byte():
    image = _checker()
    data = image.to_png()
    assert data.startswith(pi.PNG_MAGIC)
    back = pi.decode_png(data)
    assert back == image
    # The written file is RGBA, 8 bits (colour type 6).
    assert struct.unpack(">IIBB", data[16:26]) == (5, 3, 8, 6)


@pytest.mark.parametrize("kind", [1, 2, 3, 4])
def test_png_filters_are_undone(kind):
    """Rows written with each PNG filter read back as the same pixels."""
    image = _checker(6, 4)
    stride = 24
    rows, prev = [], bytes(stride)
    for y in range(4):
        row = bytes(image.data[y * stride:(y + 1) * stride])
        out = bytearray()
        for i, value in enumerate(row):
            a = row[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            if kind == 1:
                pred = a
            elif kind == 2:
                pred = b
            elif kind == 3:
                pred = (a + b) >> 1
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            out.append((value - pred) & 0xFF)
        rows.append(bytes([kind]) + bytes(out))
        prev = row
    raw = b"".join(rows)
    data = (pi.PNG_MAGIC + pi._chunk(b"IHDR", struct.pack(">IIBBBBB", 6, 4, 8, 6, 0, 0, 0))
            + pi._chunk(b"IDAT", zlib.compress(raw)) + pi._chunk(b"IEND", b""))
    assert pi.decode_png(data) == image


def test_png_rgb_palette_grey_and_trns():
    rgb = pi.decode_png(_png(2, 1, 2, 8, [bytes((1, 2, 3, 4, 5, 6))]))
    assert rgb.pixel(0, 0) == (1, 2, 3, 255) and rgb.pixel(1, 0) == (4, 5, 6, 255)
    palette = pi._chunk(b"PLTE", bytes((10, 20, 30, 40, 50, 60))) + pi._chunk(b"tRNS", bytes((0,)))
    pal = pi.decode_png(_png(3, 1, 3, 8, [bytes((0, 1, 1))], palette))
    assert pal.pixel(0, 0) == (10, 20, 30, 0) and pal.pixel(1, 0) == (40, 50, 60, 255)
    four = pi.decode_png(_png(3, 1, 3, 4, [bytes((0x10, 0x00))], palette))
    assert [four.pixel(x, 0)[3] for x in range(3)] == [255, 0, 0]
    grey = pi.decode_png(_png(2, 1, 4, 8, [bytes((9, 200, 100, 0))]))
    assert grey.pixel(0, 0) == (9, 9, 9, 200) and grey.pixel(1, 0)[3] == 0


def test_not_a_png_is_a_picture_error():
    with pytest.raises(pi.PictureError):
        pi.decode_png(b"GIF89a....")


def test_draw_is_source_over_with_surface_alpha_and_tint():
    canvas = Image(2, 1)
    red = Image(1, 1, bytes((255, 0, 0, 255)))
    canvas.draw(red, 0, 0)
    assert canvas.pixel(0, 0) == (255, 0, 0, 255)
    half_blue = Image(1, 1, bytes((0, 0, 255, 128)))
    canvas.draw(half_blue, 0, 0)
    r, g, b, a = canvas.pixel(0, 0)
    assert a == 255 and abs(r - 127) <= 1 and abs(b - 128) <= 1
    # onto transparent: the source as it is; surface alpha A makes a pixel's alpha (a x A + 127) >> 8
    # (the game's blitter); a tint multiplies colour
    canvas.draw(red, 1, 0, alpha=128, tint=(128, 255, 255))
    assert canvas.pixel(1, 0) == (128, 0, 0, (255 * 128 + 127) >> 8)
    # clipped off the canvas: nothing happens
    canvas.draw(red, 5, 5)
    canvas.draw(red, -1, 0)


def test_flip_sub_and_cell():
    image = _checker(4, 2)
    flipped = image.flipped()
    assert flipped.pixel(0, 0) == image.pixel(3, 0)
    assert image.cell(2, 1, 1) == image.sub(2, 0, 2, 2)
    outside = image.sub(-1, -1, 2, 2)
    assert outside.pixel(0, 0) == (0, 0, 0, 0) and outside.pixel(1, 1) == image.pixel(0, 0)


def test_crop_margin_and_no_margin():
    image = Image(20, 10)
    dot = Image(3, 2, bytes((1, 2, 3, 255)) * 6)
    image.draw(dot, 7, 4)
    assert image.bbox() == (7, 4, 10, 6)
    assert pi.export(image, margin=0).width == 3 and pi.export(image, margin=0).height == 2
    framed = pi.export(image)
    assert (framed.width, framed.height) == (3 + 2 * pi.MARGIN, 2 + 2 * pi.MARGIN)
    assert framed.pixel(0, 0)[3] == 0 and framed.pixel(pi.MARGIN, pi.MARGIN)[3] == 255
    assert pi.export(Image(5, 5), margin=0).width == 1           # nothing drawn


def test_crisp_sizes_are_nearest_neighbour():
    image = _checker(3, 2)
    for _label, factor in pi.SIZES:
        big = image.scaled(factor)
        assert (big.width, big.height) == (3 * factor, 2 * factor)
        for y in range(big.height):
            for x in range(big.width):
                assert big.pixel(x, y) == image.pixel(x // factor, y // factor)


def test_custom_size_is_smooth_and_keeps_transparency_clean():
    image = Image(4, 1)
    image.data[0:8] = bytes((255, 0, 0, 255, 255, 0, 0, 255))      # two red pixels, then nothing
    wide = image.resized(8, 2)
    assert (wide.width, wide.height) == (8, 2)
    # colour never bleeds black from the transparent pixels; alpha fades
    alphas = [wide.pixel(x, 0)[3] for x in range(8)]
    assert alphas[0] == 255 and alphas[-1] == 0 and any(0 < a < 255 for a in alphas)
    for x in range(8):
        r, g, b, a = wide.pixel(x, 0)
        if a:
            assert (r, g, b) == (255, 0, 0)
    small = _checker(10, 10).resized(3, 3)
    assert (small.width, small.height) == (3, 3)
    keep = pi.export(image, size=(0, 10), margin=0)
    assert (keep.width, keep.height) == (20, 10)
    with pytest.raises(pi.PictureError):
        pi.export(image, size=(0, 0))
    with pytest.raises(pi.PictureError):
        pi.export(image, size=(pi.MAX_SIDE + 1, 1))


def test_save_png_writes_whole_file(tmp_path):
    image = Image(3, 3)
    image.draw(Image(1, 1, bytes((9, 9, 9, 255))), 1, 1)
    path = pi.save_png(image, tmp_path / "a.png", scale=2, margin=1)
    back = pi.decode_png(path.read_bytes())
    assert (back.width, back.height) == (6, 6)
    assert [p.name for p in tmp_path.iterdir()] == ["a.png"]


def test_safe_file_names():
    assert pi.safe_file_name('a<b>:"c"/d\\e|f?g*') == "a-b---c--d-e-f-g-"
    assert pi.safe_file_name("CON") == "_CON"
    assert pi.safe_file_name(" .. ") == "picture"
    assert pi.safe_file_name("Silky Shark. ") == "Silky Shark"


def test_unique_path(tmp_path):
    (tmp_path / "a.png").write_bytes(b"")
    assert pi.unique_path(tmp_path, "a").name == "a (2).png"
    assert pi.unique_path(tmp_path, "b").name == "b.png"


def test_render_plan_composites_cells_in_order():
    sheet = Image(4, 2)
    sheet.data[0:4] = bytes((255, 0, 0, 255))              # cell 0 (2x2): red at its top-left
    sheet.data[8:12] = bytes((0, 255, 0, 255))             # cell 1: green at its top-left

    class Source:
        def read(self, name):
            return sheet.to_png() if name == "S.png" else None
    sheets = pi.Sheets(Source())
    plan = [pi.Draw("S.png", 2, 1, 0, 10, 10), pi.Draw("S.png", 2, 1, 1, 10, 10, flip=True)]
    image = pi.render_plan(sheets, plan)
    assert (image.width, image.height) == (2, 2)
    assert image.pixel(0, 0) == (255, 0, 0, 255) and image.pixel(1, 0) == (0, 255, 0, 255)
    with pytest.raises(pi.PictureError):
        pi.Sheets(Source()).image("missing.png")


def test_studio_cache_is_its_own_and_built_from_a_copy(tmp_path):
    copy = tmp_path / "Fish Tycoon"
    (copy / "Images").mkdir(parents=True)
    (copy / "Images" / "A.png").write_bytes(Image(1, 1).to_png())
    source = pi.picture_source("fish", [copy], ["A.png"], {})
    assert not source.problem and source.read("a.png") is not None
    cache = pi.CACHE_ROOT / "Fish"
    assert (cache / "manifest.json").is_file() and (cache / "A.png").is_file()
    assert breeding_pictures.CacheSource("fish").problem            # the guide's cache is untouched
    # From now on the cache is used without a copy.
    assert pi.picture_source("fish", [], ["A.png"], {}).read("A.png") is not None
