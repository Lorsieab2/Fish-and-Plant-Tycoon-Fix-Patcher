"""Maximizable window (Fish Tycoon): the setting, its pins, and the DLL's own
code run in Unicorn against the vanilla executable.

The emulated tests rebuild "Maximizable Window.dll" from its source (it must
come out byte-for-byte the committed one), map it beside the vanilla
Fish Tycoon.exe, and stand in for SDL.dll and Windows with Python hooks: the
install must be all or none, the window gets its maximize box and sizing
border in windowed mode only, the picture is drawn scaled with its aspect
ratio kept, and mouse messages reach SDL in the picture's coordinates.
"""

from __future__ import annotations

from argparse import Namespace
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402
from test_ds_fish_patcher import synthetic_exe  # noqa: E402

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

SETTING = "maximizable_window"
WINDOW_DLL = ROOT / "assets" / "fish_tycoon_window" / "Maximizable Window.dll"
DS_FISH_DLL = ROOT / "assets" / "fish_tycoon_ds" / "DS Exclusive Fish.dll"
FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
SDL_DLL = (E.VANILLA / "Fish Tycoon" / "SDL.dll") if E else None
SDL_BASE, USER32 = 0x68100000, 0x77000000
SDL_SCREEN_TO_CLIENT_SLOT = 0x68151698     # SDL.dll's import slot for USER32!ScreenToClient

SET_VIDEO_MODE_SLOT, FLIP_SLOT = 0x440190, 0x4401C8
SDL_FULLSCREEN = 0x80000000
WS_MAXIMIZEBOX, WS_THICKFRAME = 0x00010000, 0x00040000
SDL_WINDOWED_STYLE = 0x00CA0000          # WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX
GWL_STYLE, GWLP_WNDPROC = -16 & 0xFFFFFFFF, -4 & 0xFFFFFFFF
WM_GETMINMAXINFO, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_RBUTTONUP = 0x24, 0x200, 0x201, 0x205
HALFTONE, COLORONCOLOR, SW_RESTORE = 4, 3, 9
HWND, OLD_PROC, DC = 0x1234, 0x0BAD0000, 0xDC


def fit(client_w: int, client_h: int, w: int = 800, h: int = 600) -> tuple[int, int, int, int]:
    """The picture's place in the client area: as large as fits, aspect ratio kept, centred."""
    if client_w * h <= client_h * w:
        fw, fh = client_w, client_w * h // w
    else:
        fw, fh = client_h * w // h, client_h
    return (client_w - fw) // 2, (client_h - fh) // 2, fw, fh


def to_picture(v: int, origin: int, size: int, picture: int) -> int:
    if v < origin:
        return 0
    return min(picture - 1, (v - origin) * picture // size)


class FitMathsTests(unittest.TestCase):
    """The scale and letterbox maths the DLL implements (checked against it below)."""

    SIZES = [(800, 600), (1920, 1017), (1280, 689), (1600, 1200), (1000, 600), (800, 900),
             (400, 300), (1023, 767), (2560, 1377), (1366, 705)]

    def test_aspect_ratio_is_kept_and_the_picture_is_centred(self) -> None:
        for cw, ch in self.SIZES:
            x, y, w, h = fit(cw, ch)
            self.assertTrue(w == cw or h == ch, (cw, ch))          # fills one direction
            self.assertLessEqual(w, cw)
            self.assertLessEqual(h, ch)
            self.assertLess(abs(w * 600 - h * 800), 800, (cw, ch))  # within a pixel of 4:3
            self.assertLessEqual(abs((cw - w - x) - x), 1)          # bars equal to a pixel
            self.assertLessEqual(abs((ch - h - y) - y), 1)

    def test_own_size_is_the_identity(self) -> None:
        self.assertEqual(fit(800, 600), (0, 0, 800, 600))
        for v in (0, 1, 399, 799):
            self.assertEqual(to_picture(v, 0, 800, 800), v)

    def test_picture_edges_map_to_the_game_edges_and_bars_clamp(self) -> None:
        for cw, ch in self.SIZES:
            x, y, w, h = fit(cw, ch)
            self.assertEqual(to_picture(x, x, w, 800), 0)
            # the last client pixel holds the last game pixel (one of the last
            # few when the picture is shrunk)
            self.assertGreaterEqual(to_picture(x + w - 1, x, w, 800), 800 - -(-800 // w))
            self.assertGreaterEqual(to_picture(y + h - 1, y, h, 600), 600 - -(-600 // h))
            self.assertLessEqual(to_picture(x + w - 1, x, w, 800), 799)
            self.assertEqual(to_picture(-7, x, w, 800), 0)          # left bar / captured mouse outside
            self.assertEqual(to_picture(cw + 50, x, w, 800), 799)   # right bar

    def test_every_game_pixel_is_reachable_when_enlarged(self) -> None:
        x, _y, w, _h = fit(1920, 1017)
        self.assertEqual({to_picture(v, x, w, 800) for v in range(x, x + w)}, set(range(800)))


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = combined.load_manifest("fish")
        self.setting = combined.patch_settings("fish")[SETTING]

    def test_setting_is_on_by_default_in_the_plain_copy(self) -> None:
        self.assertTrue(self.setting["default"])
        self.assertEqual(self.setting["name"], "Maximizable window")
        self.assertFalse(self.setting.get("separate_output", False))
        self.assertFalse(self.setting.get("requires_settings"))
        defaults = fish_patcher.enabled_settings(self.manifest, Namespace(enable=None, disable=None, disable_all=False))
        self.assertIn(SETTING, defaults)
        folder, exe = fish_patcher.output_names(self.manifest, defaults, Path("Fish Tycoon - Modded"),
                                                "Fish Tycoon - Modded.exe")
        self.assertEqual((folder.name, exe), ("Fish Tycoon - Modded", "Fish Tycoon - Modded.exe"))
        self.assertNotIn(SETTING, combined.patch_settings("plant"))

    def test_companion_dll_is_pinned_and_present(self) -> None:
        companion = self.setting["companion"]
        self.assertTrue(companion["startup_loader"])
        [entry] = companion["files"]
        self.assertEqual(entry["destination"], "Fish Tycoon Fix Patcher DLLs/Maximizable Window.dll")
        data = (ROOT / companion["source"] / entry["path"]).read_bytes()
        self.assertEqual(data, WINDOW_DLL.read_bytes())
        self.assertEqual(len(data), entry["size"])
        self.assertEqual(hashlib.sha256(data).hexdigest().upper(), entry["sha256"])
        self.assertIn(b"FtfpStartup", data)

    def test_ds_fish_dll_loads_the_window_dll(self) -> None:
        self.assertIn("Maximizable Window.dll".encode("utf-16-le"), DS_FISH_DLL.read_bytes())

    def test_every_combination_is_pinned(self) -> None:
        pins = self.manifest["patched_sha256_by_settings"]
        without = [key for key in pins if SETTING not in key.split(",")]
        with_it = [key for key in pins if SETTING in key.split(",")]
        self.assertEqual(len(with_it), len(without) + 1)          # every one, and the setting alone
        for key in with_it:
            enabled = set(key.split(","))
            self.assertRegex(pins[key], r"^[0-9A-F]{64}$")
            if "ds_fish" in enabled:   # DS Exclusive Fish.dll loads it: the exe is the same
                self.assertEqual(pins[key], pins[fish_patcher.settings_key(enabled - {SETTING})], key)

    def test_loader_loads_the_window_dll_unless_ds_fish_does(self) -> None:
        self.assertIs(ds_fish_loader.fish_profile({SETTING}), ds_fish_loader.FISH_WINDOW)
        self.assertIs(ds_fish_loader.fish_profile({SETTING, "ds_fish"}), ds_fish_loader.FISH)
        out, _ = ds_fish_loader.append_startup_loader(synthetic_exe(), ds_fish_loader.FISH_WINDOW)
        self.assertIn("Fish Tycoon Fix Patcher DLLs\\Maximizable Window.dll".encode("utf-16-le"), out)
        details = combined.setting_companion_details("fish", SETTING)
        self.assertTrue(any("Maximizable Window.dll" in d.note for d in details))

    @unittest.skipUnless(FISH_EXE is not None and FISH_EXE.is_file(), "needs the vanilla Fish Tycoon.exe")
    def test_pins_match_the_vanilla_executable(self) -> None:
        vanilla = FISH_EXE.read_bytes()
        pins = self.manifest["patched_sha256_by_settings"]
        defaults = fish_patcher.enabled_settings(self.manifest, Namespace(enable=None, disable=None, disable_all=False))
        for enabled in ({SETTING}, defaults, defaults | {"bigger_tanks"}, defaults | {"ds_fish"}):
            patched, _ = fish_patcher.apply_patch_bytes(
                vanilla, fish_patcher.active_patch_records(self.manifest, enabled))
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.fish_profile(enabled))
            self.assertEqual(hashlib.sha256(patched).hexdigest().upper(), pins[fish_patcher.settings_key(enabled)])


def _needs():
    ready = (E is not None and E.toolchain_ready() and FISH_EXE is not None and FISH_EXE.is_file()
             and SDL_DLL.is_file())
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable and SDL.dll")


@_needs()
class EmulatedDllTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_fish_window", WINDOW_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # ------------------------------------------------------------ fixture
    def setUp(self) -> None:
        emu = self.emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        emu.uc.mem_map(0, 0x1000)             # fs:[0] for __try's SEH frame (FS base is 0 here)
        self.sdl = {name: emu.thunk() for name in (
            "SDL_SetVideoMode", "SDL_Flip", "SDL_LockSurface", "SDL_UnlockSurface", "SDL_GetWMInfo")}
        self.missing: set[str] = set()
        self.calls: list[tuple] = []
        self.style = SDL_WINDOWED_STYLE
        self.client = [800, 600]
        self.outer = [800 + 6, 600 + 29]       # a fixed-border window around an 800x600 client
        self.zoomed = 0
        self.ticks = 0
        self.tick_step = 0
        self.surface_flags = 0
        self.surface = self._surface()
        emu.write32(SET_VIDEO_MODE_SLOT, self.sdl["SDL_SetVideoMode"])
        emu.write32(FLIP_SLOT, self.sdl["SDL_Flip"])
        # The real SDL.dll, mapped at its own base: the DLL finds its ScreenToClient import slot there.
        self.sdl_imports = emu._map(SDL_DLL.read_bytes(), resolve=True)
        self.user32_screen_to_client = self.sdl_imports["ScreenToClient"]

        emu.hook_import("GetModuleHandleA", self._module, 4)
        emu.hook_import("lstrcmpA", lambda e: self._compare(e, False), 8)
        emu.hook_import("lstrcmpiA", lambda e: self._compare(e, True), 8)
        emu.hook_import("GetProcAddress", self._get_proc, 8)
        emu.hook_import("VirtualProtect", self._virtual_protect, 16)
        emu.hook_import("GetWindowLongA", lambda e: self.style if e.arg(1) == GWL_STYLE else 0, 8)
        emu.hook_import("SetWindowLongA", self._set_window_long, 12)
        emu.hook_import("SetWindowPos", self._set_window_pos, 28)
        emu.hook_import("GetClientRect", lambda e: self._rect(e.arg(1), *self.client), 8)
        emu.hook_import("GetWindowRect", lambda e: self._rect(e.arg(1), *self.outer), 8)
        emu.hook_import("IsZoomed", lambda e: self.zoomed, 4)
        emu.hook_import("ShowWindow", self._log("ShowWindow", 2, 1), 8)
        emu.hook_import("CallWindowProcA", self._log("CallWindowProcA", 5, 0x77), 20)
        emu.hook_import("GetDC", self._log("GetDC", 1, DC), 4)
        emu.hook_import("ReleaseDC", self._log("ReleaseDC", 2, 1), 8)
        emu.hook_import("BeginPaint", self._log("BeginPaint", 2, DC), 8)
        emu.hook_import("EndPaint", self._log("EndPaint", 2, 1), 8)
        emu.hook_import("GetStockObject", lambda e: 0xB1AC, 4)
        emu.hook_import("FillRect", self._fill_rect, 12)
        emu.hook_import("SetRect", self._set_rect, 20)
        emu.hook_import("SetStretchBltMode", self._log("SetStretchBltMode", 2, 1), 8)
        emu.hook_import("SetBrushOrgEx", lambda e: 1, 16)
        emu.hook_import("StretchDIBits", self._log("StretchDIBits", 13, 600), 52)
        emu.hook_import("QueryPerformanceCounter", self._qpc, 4)
        emu.hook_import("QueryPerformanceFrequency", self._qpf, 4)
        emu.hook(self.sdl["SDL_SetVideoMode"], self._sdl_set_video_mode)
        emu.hook(self.sdl["SDL_Flip"], self._log("SDL_Flip", 1, 0))
        emu.hook(self.sdl["SDL_LockSurface"], lambda e: 0)
        emu.hook(self.sdl["SDL_UnlockSurface"], lambda e: 0)
        emu.hook(self.sdl["SDL_GetWMInfo"], self._wm_info)

    def _surface(self) -> int:
        emu = self.emu
        fmt = emu.alloc(40)
        emu.uc.mem_write(fmt, struct.pack("<IBB8x2xIIII", 0, 16, 2, 0xF800, 0x07E0, 0x001F, 0))
        pixels = emu.alloc(1600 * 600)
        surface = emu.alloc(64)
        emu.uc.mem_write(surface, struct.pack("<IIiiH2xI", 0, fmt, 800, 600, 1600, pixels))
        self.pixels = pixels
        return surface

    def _log(self, name: str, args: int, result: int):
        def handler(e) -> int:
            self.calls.append((name, *[e.arg(i) for i in range(args)]))
            return result
        return handler

    def _module(self, e) -> int:
        return {b"sdl.dll": SDL_BASE, b"user32.dll": USER32}.get(e.cstring(e.arg(0)).lower(), 0)

    @staticmethod
    def _compare(e, fold: bool) -> int:
        a, b = e.cstring(e.arg(0)), e.cstring(e.arg(1))
        if fold:
            a, b = a.lower(), b.lower()
        return (a > b) - (a < b)

    def _get_proc(self, e) -> int:
        name = e.cstring(e.arg(1)).decode()
        if name in self.missing:
            return 0
        if e.arg(0) == USER32:
            return self.user32_screen_to_client if name == "ScreenToClient" else 0
        return self.sdl.get(name, 0) if e.arg(0) == SDL_BASE else 0

    def _virtual_protect(self, e) -> int:
        self.calls.append(("VirtualProtect", e.arg(0), e.arg(1), e.arg(2)))
        e.write32(e.arg(3), 0x02)
        return 1

    def _rect(self, at: int, w: int, h: int) -> int:
        self.emu.uc.mem_write(at, struct.pack("<4i", 0, 0, w, h))
        return 1

    def _frame(self) -> tuple[int, int]:
        return (16, 39) if self.style & WS_THICKFRAME else (6, 29)

    def _set_window_long(self, e) -> int:
        index, value = e.arg(1), e.arg(2)
        self.calls.append(("SetWindowLongA", index, value))
        if index == GWL_STYLE:
            old, self.style = self.style, value
            return old
        self.proc = value
        return OLD_PROC

    def _set_window_pos(self, e) -> int:
        cx, cy, flags = e.arg(4), e.arg(5), e.arg(6)
        self.calls.append(("SetWindowPos", cx, cy, flags))
        if not flags & 0x1:                     # SWP_NOSIZE not set
            self.outer = [cx, cy]
        fw, fh = self._frame()
        self.client = [self.outer[0] - fw, self.outer[1] - fh]
        return 1

    def _set_rect(self, e) -> int:
        self.emu.uc.mem_write(e.arg(0), struct.pack("<4i", *[e.arg(i) for i in range(1, 5)]))
        return 1

    def _fill_rect(self, e) -> int:
        self.calls.append(("FillRect", *struct.unpack("<4i", e.uc.mem_read(e.arg(1), 16))))
        return 1

    def _qpc(self, e) -> int:
        self.ticks += self.tick_step
        e.uc.mem_write(e.arg(0), struct.pack("<q", self.ticks))
        return 1

    def _qpf(self, e) -> int:
        e.uc.mem_write(e.arg(0), struct.pack("<q", 1000))       # one tick a millisecond
        return 1

    def _sdl_set_video_mode(self, e) -> int:
        self.calls.append(("SDL_SetVideoMode", e.arg(0), e.arg(1), e.arg(2), e.arg(3)))
        e.write32(self.surface, self.surface_flags)
        return self.surface

    def _wm_info(self, e) -> int:
        info = e.arg(0)
        self.calls.append(("SDL_GetWMInfo", bytes(e.uc.mem_read(info, 3))))
        e.write32(info + 4, HWND)
        return 1

    def named(self, name: str) -> list[tuple]:
        return [call for call in self.calls if call[0] == name]

    def startup(self) -> int:
        return self.emu.call(self.symbols["_FtfpStartup@0"])

    def set_video_mode(self, flags: int = 0) -> int:
        self.surface_flags = flags
        return self.emu.call(self.emu.read32(SET_VIDEO_MODE_SLOT), 800, 600, 16, flags)

    def flip(self) -> int:
        return self.emu.call(self.emu.read32(FLIP_SLOT), self.surface)

    def window_proc(self) -> int:
        return self.proc

    def message(self, msg: int, lparam: int) -> tuple:
        proc = self.window_proc()
        self.calls.clear()
        self.emu.call(proc, HWND, msg, 1, lparam)
        return self.named("CallWindowProcA")[-1]

    def windowed(self) -> None:
        self.assertEqual(self.startup(), 1)
        self.assertEqual(self.set_video_mode(), self.surface)

    # ------------------------------------------------------------ install
    def test_install_points_both_slots_here(self) -> None:
        self.assertEqual(self.startup(), 1)
        video_mode, flip = self.emu.read32(SET_VIDEO_MODE_SLOT), self.emu.read32(FLIP_SLOT)
        base = E.pe_image(self.dll.read_bytes())[0]
        cursor = self.emu.read32(SDL_SCREEN_TO_CLIENT_SLOT)
        for slot in (video_mode, flip, cursor):
            self.assertTrue(base <= slot < base + 0x100000, hex(slot))
        protected = [call[1:3] for call in self.named("VirtualProtect")]
        self.assertIn((SET_VIDEO_MODE_SLOT, FLIP_SLOT + 4 - SET_VIDEO_MODE_SLOT), protected)
        self.assertIn((SDL_SCREEN_TO_CLIENT_SLOT, 4), protected)

    def test_the_slot_found_is_sdls_own_screen_to_client(self) -> None:
        # SDL.dll's pointer reads all go through this one slot (DIB_PumpEvents, focus, DirectX).
        for site in (0x6812F820, 0x6812D9D6, 0x68132400):
            self.assertEqual(bytes(self.emu.uc.mem_read(site, 6)), b"\xFF\x15" + struct.pack("<I", SDL_SCREEN_TO_CLIENT_SLOT))
        self.assertEqual(self.emu.read32(SDL_SCREEN_TO_CLIENT_SLOT), self.user32_screen_to_client)

    def _refused(self) -> None:
        before = (self.emu.read32(SET_VIDEO_MODE_SLOT), self.emu.read32(FLIP_SLOT),
                  self.emu.read32(SDL_SCREEN_TO_CLIENT_SLOT))
        self.assertEqual(self.startup(), 0)
        self.assertEqual((self.emu.read32(SET_VIDEO_MODE_SLOT), self.emu.read32(FLIP_SLOT),
                          self.emu.read32(SDL_SCREEN_TO_CLIENT_SLOT)), before)
        self.assertEqual(self.named("VirtualProtect"), [])

    def test_sdls_screen_to_client_already_changed_installs_nothing(self) -> None:
        self.emu.write32(SDL_SCREEN_TO_CLIENT_SLOT, 0x12345678)
        self._refused()

    def test_no_user32_screen_to_client_installs_nothing(self) -> None:
        self.missing.add("ScreenToClient")
        self._refused()

    def test_a_slot_already_changed_installs_nothing(self) -> None:
        self.emu.write32(FLIP_SLOT, 0x12345678)
        self._refused()

    def test_a_changed_thunk_installs_nothing(self) -> None:
        self.emu.uc.mem_write(0x42A62A, b"\xE9\0\0\0\0\x90")
        self._refused()

    def test_a_missing_sdl_function_installs_nothing(self) -> None:
        self.missing.add("SDL_GetWMInfo")
        self._refused()

    # ------------------------------------------------------------ window style
    def test_windowed_mode_gets_the_maximize_box_and_keeps_its_size(self) -> None:
        self.windowed()
        self.assertEqual(self.named("SDL_GetWMInfo")[0][1], bytes([1, 2, 15]))
        self.assertEqual(self.style, SDL_WINDOWED_STYLE | WS_MAXIMIZEBOX | WS_THICKFRAME)
        self.assertEqual(self.client, [800, 600])           # resized for the thicker border
        self.assertEqual(self.window_proc() >> 28, E.pe_image(self.dll.read_bytes())[0] >> 28)

    def test_fullscreen_is_left_alone(self) -> None:
        self.assertEqual(self.startup(), 1)
        self.set_video_mode(SDL_FULLSCREEN)
        self.assertEqual(self.style, SDL_WINDOWED_STYLE)
        self.assertEqual(self.named("SetWindowPos"), [])
        self.client = [1920, 1080]
        self.calls.clear()
        self.flip()
        self.assertEqual(self.named("SDL_Flip"), [("SDL_Flip", self.surface)])
        self.assertEqual(self.named("StretchDIBits"), [])
        self.assertEqual(self.message(WM_LBUTTONDOWN, (300 << 16) | 500)[5], (300 << 16) | 500)

    def test_a_maximized_window_is_restored_before_the_mode_changes(self) -> None:
        self.windowed()
        self.zoomed = 1
        self.calls.clear()
        self.set_video_mode(SDL_FULLSCREEN)
        self.assertEqual(self.calls[0], ("ShowWindow", HWND, SW_RESTORE))
        self.assertEqual(self.calls[1][0], "SDL_SetVideoMode")

    def test_min_max_info_is_not_pinned_to_the_window_size(self) -> None:
        self.windowed()
        info = self.emu.alloc(40)
        self.emu.uc.mem_write(info, bytes(40))
        self.calls.clear()
        self.emu.call(self.window_proc(), HWND, WM_GETMINMAXINFO, 0, info)
        self.assertEqual(self.named("CallWindowProcA"), [])   # SDL would pin it to the current size
        fw, fh = self._frame()
        self.assertEqual(struct.unpack("<2i", self.emu.uc.mem_read(info + 24, 8)), (400 + fw, 300 + fh))
        self.assertEqual(struct.unpack("<2i", self.emu.uc.mem_read(info + 8, 8)), (0, 0))  # Windows' own maximum

    # ------------------------------------------------------------ drawing
    def test_own_size_flips_through_sdl_untouched(self) -> None:
        self.windowed()
        self.calls.clear()
        self.flip()
        self.assertEqual(self.named("SDL_Flip"), [("SDL_Flip", self.surface)])
        self.assertEqual(self.named("StretchDIBits"), [])

    def test_other_sizes_draw_the_picture_scaled_with_bars(self) -> None:
        self.windowed()
        for cw, ch in FitMathsTests.SIZES[1:]:
            self.client = [cw, ch]
            self.calls.clear()
            self.assertEqual(self.flip(), 0)
            self.assertEqual(self.named("SDL_Flip"), [])
            [call] = self.named("StretchDIBits")
            x, y, w, h = fit(cw, ch)
            self.assertEqual(call[1:9], (DC, x, y, w, h, 0, 0, 800))
            self.assertEqual(call[9:11], (600, self.pixels))
            self.assertEqual(self.named("SetStretchBltMode"), [("SetStretchBltMode", DC, HALFTONE)])
            # the bars and the picture cover the client area exactly once
            area = sum((r - l) * (b - t) for _n, l, t, r, b in self.named("FillRect"))
            self.assertEqual(area + w * h, cw * ch, (cw, ch))
            self.assertEqual(self.named("ReleaseDC"), [("ReleaseDC", HWND, DC)])

    def test_bitmap_header_describes_the_sdl_surface(self) -> None:
        self.windowed()
        self.client = [1600, 1200]
        self.calls.clear()
        self.flip()
        header = self.named("StretchDIBits")[0][11]
        size, width, height, planes, bits, compression = struct.unpack("<IiiHHI", self.emu.uc.mem_read(header, 20))
        masks = struct.unpack("<3I", self.emu.uc.mem_read(header + 40, 12))
        self.assertEqual((size, width, height, planes, bits, compression), (40, 800, -600, 1, 16, 3))
        self.assertEqual(masks, (0xF800, 0x07E0, 0x001F))

    def test_slow_smoothing_falls_back_to_nearest_pixel_at_that_size(self) -> None:
        self.windowed()
        self.client = [2560, 1377]
        self.tick_step = 20                      # every draw takes 20 ms
        modes = []
        for _ in range(4):
            self.calls.clear()
            self.flip()
            modes.append(self.named("SetStretchBltMode")[0][2])
        self.assertEqual(modes, [HALFTONE, HALFTONE, HALFTONE, COLORONCOLOR])
        self.client = [1920, 1017]               # another size smooths again
        self.tick_step = 5
        self.calls.clear()
        self.flip()
        self.assertEqual(self.named("SetStretchBltMode")[0][2], HALFTONE)

    def test_paint_draws_scaled_only_when_enlarged(self) -> None:
        self.windowed()
        WM_PAINT = 0x0F
        self.calls.clear()
        self.emu.call(self.window_proc(), HWND, WM_PAINT, 0, 0)
        self.assertEqual(len(self.named("CallWindowProcA")), 1)      # SDL paints its own size
        self.client = [1920, 1017]
        self.calls.clear()
        self.assertEqual(self.emu.call(self.window_proc(), HWND, WM_PAINT, 0, 0), 0)
        self.assertEqual(self.named("CallWindowProcA"), [])
        self.assertEqual(len(self.named("StretchDIBits")), 1)
        self.assertEqual(len(self.named("EndPaint")), 1)

    # ------------------------------------------------------------ mouse
    def test_mouse_reaches_sdl_in_picture_coordinates(self) -> None:
        self.windowed()
        for cw, ch in FitMathsTests.SIZES:
            self.client = [cw, ch]
            x, y, w, h = fit(cw, ch)
            for cx, cy in ((0, 0), (x, y), (x + w - 1, y + h - 1), (cw // 2, ch // 2), (cw - 1, ch - 1),
                           (x + w // 3, y + h // 5)):
                for msg in (WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_RBUTTONUP):
                    call = self.message(msg, (cy << 16) | cx)
                    self.assertEqual(call[1:4], (OLD_PROC, HWND, msg))
                    if (cw, ch) == (800, 600):
                        expected = (cy << 16) | cx              # stock: untouched
                    else:
                        expected = (to_picture(cy, y, h, 600) << 16) | to_picture(cx, x, w, 800)
                    self.assertEqual(call[5], expected, (cw, ch, cx, cy))

    def test_captured_mouse_outside_the_window_clamps(self) -> None:
        self.windowed()
        self.client = [1920, 1017]
        lparam = ((-20 & 0xFFFF) << 16) | (5000 & 0xFFFF)       # left of / above the window, signed
        self.assertEqual(self.message(WM_LBUTTONDOWN, lparam)[5], (0 << 16) | 799)

    # ------------------------------------------------------------ SDL's own mouse code
    # The real SDL.dll's windib code runs from here on: its window procedure (WinMessage,
    # 0x6812C6A0) for the messages, its event pump (DIB_PumpEvents, 0x6812F6C0), which reads
    # the pointer itself with GetCursorPos + ScreenToClient after every batch of messages,
    # SDL_PrivateMouseMotion / SDL_PrivateMouseButton, and SDL_GetMouseState (0x68107EA0),
    # where the game draws its own cursor (0x408650) and what its hovers read. Only Windows
    # and SDL's event queue (0x68106C10, SDL_PushEvent) are Python.
    ORIGIN = (300, 200)                        # the client area's top-left on the screen

    def sdl_ready(self) -> None:
        emu = self.emu
        self.events: list[tuple[int, int, int]] = []
        self.pointer = self.ORIGIN
        video = emu.alloc(0x200)
        emu.uc.mem_write(video, bytes(0x200))
        emu.write32(video, 0x68144588)         # current_video->name: "windib" (bootstrap[0], 0x68144228)
        emu.write32(video + 0x134, self.surface)
        emu.write32(0x68149390, video)         # current_video
        emu.write32(0x681493B0, HWND)          # SDL_Window
        emu.write32(0x681493D0, 0)             # mouse_relative: no grab
        emu.write8(0x68147500, 7)              # SDL_GetAppState: mouse and input focus, active
        emu.uc.mem_write(0x68149000, struct.pack("<HH", 800, 600))   # SDL_MouseMaxX / Y
        for kind in (4, 5, 6):                 # SDL_ProcessEvents[MOUSEMOTION / BUTTONDOWN / BUTTONUP]
            emu.write8(0x6814ED60 + kind, 1)
        emu.write32(0x68147520, 0)             # no event filter
        emu.hook(0x68121DF0, lambda e: 0)      # SDL_MoveCursor: the game draws its own
        emu.hook(0x68106C10, self._push_event)
        user = self.sdl_imports

        def screen_to_client(e) -> int:
            x, y = struct.unpack("<2i", e.uc.mem_read(e.arg(1), 8))
            e.uc.mem_write(e.arg(1), struct.pack("<2i", x - self.ORIGIN[0], y - self.ORIGIN[1]))
            return 1

        def cursor(e) -> int:
            e.uc.mem_write(e.arg(0), struct.pack("<2i", *self.pointer))
            return 1
        emu.hook(user["PeekMessageA"], lambda e: 0, 20)
        emu.hook(user["GetCursorPos"], cursor, 4)
        emu.hook(user["ScreenToClient"], screen_to_client, 8)
        emu.hook(user["SetCapture"], lambda e: 0, 4)
        emu.hook(user["ReleaseCapture"], lambda e: 1, 0)
        emu.hook(user["SetFocus"], lambda e: HWND, 4)

    def _push_event(self, e) -> int:
        kind, _which, _state, _pad, x, y = struct.unpack("<4BHH", e.uc.mem_read(e.arg(0), 8))
        self.events.append((kind, x, y))
        return 1

    def mouse_state(self) -> tuple[int, int]:
        out = self.emu.alloc(8)
        self.emu.call(0x68107EA0, out, out + 4)
        return struct.unpack("<2i", self.emu.uc.mem_read(out, 8))

    def sdl_message(self, msg: int, cx: int, cy: int) -> None:
        """The message through this DLL's window procedure, then SDL's own WinMessage as it was
        handed on (CallWindowProcA), then SDL's pump, which reads the pointer itself."""
        self.pointer = (self.ORIGIN[0] + cx, self.ORIGIN[1] + cy)
        handed = self.message(msg, ((cy & 0xFFFF) << 16) | (cx & 0xFFFF))
        self.emu.call(0x6812C6A0, HWND, msg, handed[4], handed[5])
        self.emu.call(0x6812F6C0)

    def test_sdls_pointer_and_clicks_agree_at_every_size(self) -> None:
        """Where the game draws its cursor (SDL_GetMouseState) is where the click lands
        (the button events), maximized or not: the picture point under the real pointer."""
        self.windowed()
        self.sdl_ready()
        for cw, ch in FitMathsTests.SIZES:
            self.client = [cw, ch]
            x, y, w, h = fit(cw, ch)
            for cx, cy in ((x + w // 2, y + 10), (x + w - 3, y + h // 2), (x + w // 3, y + h // 5), (0, 0),
                           (cw - 1, ch - 1)):
                expected = (to_picture(cx, x, w, 800), to_picture(cy, y, h, 600))
                self.events.clear()
                for msg in (WM_MOUSEMOVE, WM_LBUTTONDOWN, 0x202):
                    self.sdl_message(msg, cx, cy)
                    self.assertEqual(self.mouse_state(), expected, (cw, ch, cx, cy, hex(msg)))
                self.assertIn((5, *expected), self.events)       # SDL_MOUSEBUTTONDOWN
                self.assertIn((6, *expected), self.events)       # SDL_MOUSEBUTTONUP
                self.assertEqual({(px, py) for _k, px, py in self.events}, {expected}, (cw, ch, cx, cy))

    def test_own_size_pointer_is_stock(self) -> None:
        self.windowed()
        self.sdl_ready()
        for cx, cy in ((0, 0), (513, 20), (799, 599)):
            self.sdl_message(WM_LBUTTONDOWN, cx, cy)
            self.assertEqual(self.mouse_state(), (cx, cy))


if __name__ == "__main__":
    unittest.main()
