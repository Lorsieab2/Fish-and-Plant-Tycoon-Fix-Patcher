"""Picture Studio reads the games' BMP, GIF and JPEG pictures (src/picture_formats.py).

* JPEG: every one of Plant Tycoon's JPEGs decodes, pixel for pixel, to what the game's own
  libjpeg-9.dll gives (run in Unicorn, tests/libjpeg_emulator.py) with SDL2_image's settings:
  RGB out, nothing else changed (SDL2_image.dll 0x1000360D..0x10003687 sets out_color_space and
  quantize_colors only). This includes the three 2 x 2 subsampled ones, whose chroma libjpeg 9
  grows with its 16 x 16 IDCT.
* BMP and GIF: every one of the games' (Fish Tycoon's 16 BMPs in ft.dat, Plant Tycoon's three
  GIFs) against Pillow, when it is installed (a test-only check; the patcher ships none).
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import picture_formats as F  # noqa: E402
import libjpeg_emulator as L  # noqa: E402

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
FISH_DAT = VANILLA / "Fish Tycoon" / "Assets" / "ft.dat"
PLANT_IMAGES = VANILLA / "Plant Tycoon" / "Images"

try:
    from PIL import Image as PIL_Image
except ImportError:                       # no Pillow: the BMP and GIF checks skip
    PIL_Image = None


def rgb(image) -> bytes:
    out = bytearray(image.width * image.height * 3)
    out[0::3], out[1::3], out[2::3] = image.data[0::4], image.data[1::4], image.data[2::4]
    return bytes(out)


class Basics(unittest.TestCase):
    def test_tiny_pictures(self) -> None:
        import struct
        # a 2 x 2, 24-bit bottom-up BMP: blue, green / red, white
        rows = [bytes((0, 0, 255, 255, 255, 255)) + b"\0\0", bytes((255, 0, 0, 0, 255, 0)) + b"\0\0"]
        pixels = b"".join(rows)
        header = b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54) + \
            struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 24, 0, len(pixels), 0, 0, 0, 0)
        image = F.decode("x.bmp", header + pixels)
        self.assertEqual([image.pixel(x, y) for y in (0, 1) for x in (0, 1)],
                         [(0, 0, 255, 255), (0, 255, 0, 255), (255, 0, 0, 255), (255, 255, 255, 255)])
        with self.assertRaises(Exception):
            F.decode("x.jpg", b"\xff\xd8\xff\xd9")


@unittest.skipUnless(L.available() and PLANT_IMAGES.is_dir(), "the vanilla Plant Tycoon and Unicorn")
class JpegIsTheGames(unittest.TestCase):
    def test_every_jpeg_is_libjpeg_9s(self) -> None:
        names = sorted(p.name for p in PLANT_IMAGES.iterdir() if p.suffix.casefold() == ".jpg")
        self.assertEqual(len(names), 21)
        subsampled = 0
        with tempfile.TemporaryDirectory() as folder:
            games = L.decode_in_child([PLANT_IMAGES / n for n in names], folder)
        for name in names:
            data = (PLANT_IMAGES / name).read_bytes()
            width, height, expected = games[name]
            image = F.decode(name, data)
            self.assertEqual((image.width, image.height), (width, height), name)
            self.assertTrue(rgb(image) == expected, f"{name}: every pixel as libjpeg-9 decodes it")
            self.assertEqual(set(image.data[3::4]), {255}, name)
            subsampled += b"\x01\x22" in data[:2000]
        self.assertGreaterEqual(subsampled, 3, "the 2 x 2 subsampled pictures are among them")


@unittest.skipUnless(PIL_Image is not None and FISH_DAT.is_file() and PLANT_IMAGES.is_dir(),
                     "Pillow and the vanilla games")
class BmpAndGifAsPillowReadsThem(unittest.TestCase):
    def test_every_bmp(self) -> None:
        import io
        files = []
        with zipfile.ZipFile(FISH_DAT) as z:
            files += [(n, z.read(n)) for n in z.namelist()
                      if n.casefold().endswith(".bmp") and not n.startswith("__MACOSX")]
        files += [(p.name, p.read_bytes()) for p in PLANT_IMAGES.iterdir() if p.suffix.casefold() == ".bmp"]
        self.assertEqual(len(files), 16, "Fish Tycoon's 16 (Plant Tycoon's SPLASH3_BG.bmp is not in its folder)")
        for name, data in files:
            image = F.decode(name, data)
            expected = PIL_Image.open(io.BytesIO(data)).convert("RGBA").tobytes()
            self.assertTrue(bytes(image.data) == expected, name)

    def test_every_gif_frame(self) -> None:
        names = sorted(p.name for p in PLANT_IMAGES.iterdir() if p.suffix.casefold() == ".gif")
        self.assertEqual(names, ["30dayguarantee.gif", "PTwinbuy.gif", "logo1.gif"])
        for name in names:
            data = (PLANT_IMAGES / name).read_bytes()
            frames = F.decode_gif(data)
            with PIL_Image.open(PLANT_IMAGES / name) as gif:
                self.assertEqual(len(frames), getattr(gif, "n_frames", 1), name)
                for k, frame in enumerate(frames):
                    gif.seek(k)
                    want = gif.convert("RGBA").tobytes()
                    got = bytes(frame.data)
                    for i in range(0, len(want), 4):
                        if want[i + 3]:
                            self.assertEqual(got[i:i + 4], want[i:i + 4], (name, k, i // 4))
                        else:
                            self.assertEqual(got[i + 3], 0, (name, k, i // 4))
