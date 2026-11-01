"""Windows' own text drawing, for letters the games' bitmap fonts lack: DirectWrite (font
choice, font fallback, shaping: joined emoji, skin tones, combining marks, Arabic, Indic...)
drawn by Direct2D (anti-aliased in its alpha, colour emoji in colour) into a 32-bit DIB.
Pure ctypes: the patcher ships no Pillow.

raster(text, family, size, weight) -> Raster: the drawing's premultiplied pixels, its
baseline and its advance width, in pixels (96 DPI: a DirectWrite DIP is a pixel).
"""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import math
import threading

HRESULT = ctypes.c_long


class GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text: str) -> "GUID":
        h = text.replace("-", "")
        return cls(int(h[0:8], 16), int(h[8:12], 16), int(h[12:16], 16),
                   (ctypes.c_ubyte * 8)(*bytes.fromhex(h[16:])))


class D2D1_PIXEL_FORMAT(ctypes.Structure):
    _fields_ = [("format", ctypes.c_uint32), ("alphaMode", ctypes.c_uint32)]


class D2D1_RENDER_TARGET_PROPERTIES(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("pixelFormat", D2D1_PIXEL_FORMAT), ("dpiX", ctypes.c_float),
                ("dpiY", ctypes.c_float), ("usage", ctypes.c_uint32), ("minLevel", ctypes.c_uint32)]


class D2D1_COLOR_F(ctypes.Structure):
    _fields_ = [("r", ctypes.c_float), ("g", ctypes.c_float), ("b", ctypes.c_float), ("a", ctypes.c_float)]


class D2D1_POINT_2F(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float)]


class DWRITE_LINE_METRICS(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint32), ("trailingWhitespaceLength", ctypes.c_uint32),
                ("newlineLength", ctypes.c_uint32), ("height", ctypes.c_float), ("baseline", ctypes.c_float),
                ("isTrimmed", wintypes.BOOL)]


class DWRITE_TEXT_METRICS(ctypes.Structure):
    _fields_ = [("left", ctypes.c_float), ("top", ctypes.c_float), ("width", ctypes.c_float),
                ("widthIncludingTrailingWhitespace", ctypes.c_float), ("height", ctypes.c_float),
                ("layoutWidth", ctypes.c_float), ("layoutHeight", ctypes.c_float),
                ("maxBidiReorderingDepth", ctypes.c_uint32), ("lineCount", ctypes.c_uint32)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


IID_ID2D1Factory = GUID.parse("06152247-6f50-465a-9245-118bfd3b6007")
IID_IDWriteFactory = GUID.parse("b859ee5a-d838-4b5b-a2e8-1adc7d93db48")

# vtable slots
RELEASE = 2
F_CREATE_DC_RENDER_TARGET = 16
RT_CREATE_SOLID_COLOR_BRUSH = 8
RT_DRAW_TEXT_LAYOUT = 28
RT_SET_TEXT_ANTIALIAS_MODE = 34
RT_CLEAR = 47
RT_BEGIN_DRAW = 48
RT_END_DRAW = 49
DCRT_BIND_DC = 57
DW_CREATE_TEXT_FORMAT = 15
DW_CREATE_TEXT_LAYOUT = 18
TL_GET_LINE_METRICS = 59
TL_GET_METRICS = 60

DXGI_FORMAT_B8G8R8A8_UNORM = 87
D2D1_ALPHA_MODE_PREMULTIPLIED = 1
D2D1_TEXT_ANTIALIAS_MODE_GRAYSCALE = 2
D2D1_DRAW_TEXT_OPTIONS_ENABLE_COLOR_FONT = 4


class RasterError(Exception):
    pass


def _method(obj: ctypes.c_void_p, slot: int, restype, *argtypes):
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return lambda *args: prototype(vtable[slot])(obj, *args)


def _check(hr: int, what: str) -> None:
    if hr < 0:
        raise RasterError(f"{what} failed (0x{hr & 0xFFFFFFFF:08X})")


def _release(obj) -> None:
    if obj:
        _method(obj, RELEASE, ctypes.c_ulong)()


@dataclass
class Raster:
    width: int
    height: int
    bgra: bytes                  # premultiplied B, G, R, A, rows top to bottom
    baseline: float              # y of the baseline
    advance: float               # the text's advance width
    origin_x: float              # x where the text starts


class _Direct2D:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        d2d1 = ctypes.WinDLL("d2d1")
        dwrite = ctypes.WinDLL("dwrite")
        self.gdi32 = ctypes.WinDLL("gdi32")
        self.gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        self.gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                                ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
        self.gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self.gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self.gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self.gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self.factory = ctypes.c_void_p()
        d2d1.D2D1CreateFactory.restype = HRESULT
        d2d1.D2D1CreateFactory.argtypes = [ctypes.c_uint32, ctypes.POINTER(GUID), ctypes.c_void_p,
                                           ctypes.POINTER(ctypes.c_void_p)]
        _check(d2d1.D2D1CreateFactory(0, ctypes.byref(IID_ID2D1Factory), None, ctypes.byref(self.factory)),
               "D2D1CreateFactory")
        self.dwrite = ctypes.c_void_p()
        dwrite.DWriteCreateFactory.restype = HRESULT
        dwrite.DWriteCreateFactory.argtypes = [ctypes.c_uint32, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        _check(dwrite.DWriteCreateFactory(0, ctypes.byref(IID_IDWriteFactory), ctypes.byref(self.dwrite)),
               "DWriteCreateFactory")
        props = D2D1_RENDER_TARGET_PROPERTIES(0, D2D1_PIXEL_FORMAT(DXGI_FORMAT_B8G8R8A8_UNORM,
                                                                    D2D1_ALPHA_MODE_PREMULTIPLIED), 96.0, 96.0, 0, 0)
        self.target = ctypes.c_void_p()
        _check(_method(self.factory, F_CREATE_DC_RENDER_TARGET, HRESULT, ctypes.POINTER(D2D1_RENDER_TARGET_PROPERTIES),
                       ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(props), ctypes.byref(self.target)),
               "CreateDCRenderTarget")
        _method(self.target, RT_SET_TEXT_ANTIALIAS_MODE, None, ctypes.c_uint32)(D2D1_TEXT_ANTIALIAS_MODE_GRAYSCALE)
        self.brush = ctypes.c_void_p()
        white = D2D1_COLOR_F(1.0, 1.0, 1.0, 1.0)
        _check(_method(self.target, RT_CREATE_SOLID_COLOR_BRUSH, HRESULT, ctypes.POINTER(D2D1_COLOR_F),
                       ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(white), None,
                                                                         ctypes.byref(self.brush)),
               "CreateSolidColorBrush")

    def layout(self, text: str, family: str, size: float, weight: int):
        fmt = ctypes.c_void_p()
        _check(_method(self.dwrite, DW_CREATE_TEXT_FORMAT, HRESULT, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32,
                       ctypes.c_uint32, ctypes.c_uint32, ctypes.c_float, ctypes.c_wchar_p,
                       ctypes.POINTER(ctypes.c_void_p))(family, None, weight, 0, 5, size, "en-us", ctypes.byref(fmt)),
               "CreateTextFormat")
        layout = ctypes.c_void_p()
        try:
            buffer = ctypes.create_unicode_buffer(text)
            length = len(text.encode("utf-16-le")) // 2
            _check(_method(self.dwrite, DW_CREATE_TEXT_LAYOUT, HRESULT, ctypes.c_wchar_p, ctypes.c_uint32,
                           ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.POINTER(ctypes.c_void_p))(
                buffer, length, fmt, 100000.0, 100000.0, ctypes.byref(layout)), "CreateTextLayout")
        finally:
            _release(fmt)
        return layout

    def raster(self, text: str, family: str, size: float, weight: int) -> Raster:
        with self.lock:
            layout = self.layout(text, family, size, weight)
            try:
                lines = (DWRITE_LINE_METRICS * 4)()
                count = ctypes.c_uint32()
                _check(_method(layout, TL_GET_LINE_METRICS, HRESULT, ctypes.c_void_p, ctypes.c_uint32,
                               ctypes.POINTER(ctypes.c_uint32))(lines, 4, ctypes.byref(count)), "GetLineMetrics")
                metrics = DWRITE_TEXT_METRICS()
                _check(_method(layout, TL_GET_METRICS, HRESULT, ctypes.POINTER(DWRITE_TEXT_METRICS))(
                    ctypes.byref(metrics)), "GetMetrics")
                pad = int(size) + 4
                width = int(math.ceil(metrics.widthIncludingTrailingWhitespace)) + 2 * pad
                height = int(math.ceil(metrics.height)) + 2 * pad
                return self._draw(layout, width, height, pad, lines[0].baseline + pad,
                                  metrics.widthIncludingTrailingWhitespace)
            finally:
                _release(layout)

    def _draw(self, layout, width: int, height: int, pad: int, baseline: float, advance: float) -> Raster:
        gdi = self.gdi32
        dc = gdi.CreateCompatibleDC(None)
        if not dc:
            raise RasterError("CreateCompatibleDC failed")
        header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        bitmap = gdi.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        if not bitmap:
            gdi.DeleteDC(dc)
            raise RasterError("CreateDIBSection failed")
        old = gdi.SelectObject(dc, bitmap)
        try:
            ctypes.memset(bits, 0, width * height * 4)
            rect = wintypes.RECT(0, 0, width, height)
            _check(_method(self.target, DCRT_BIND_DC, HRESULT, wintypes.HDC, ctypes.POINTER(wintypes.RECT))(
                dc, ctypes.byref(rect)), "BindDC")
            _method(self.target, RT_BEGIN_DRAW, None)()
            clear = D2D1_COLOR_F(0.0, 0.0, 0.0, 0.0)
            _method(self.target, RT_CLEAR, None, ctypes.POINTER(D2D1_COLOR_F))(ctypes.byref(clear))
            _method(self.target, RT_DRAW_TEXT_LAYOUT, None, D2D1_POINT_2F, ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.c_uint32)(D2D1_POINT_2F(float(pad), float(pad)), layout, self.brush,
                                     D2D1_DRAW_TEXT_OPTIONS_ENABLE_COLOR_FONT)
            _check(_method(self.target, RT_END_DRAW, HRESULT, ctypes.c_void_p, ctypes.c_void_p)(None, None), "EndDraw")
            data = ctypes.string_at(bits, width * height * 4)
        finally:
            gdi.SelectObject(dc, old)
            gdi.DeleteObject(bitmap)
            gdi.DeleteDC(dc)
        return Raster(width, height, data, baseline, advance, float(pad))


_engine: _Direct2D | None = None
_engine_error: str | None = None


def available() -> bool:
    return _get() is not None


def _get() -> _Direct2D | None:
    global _engine, _engine_error
    if _engine is None and _engine_error is None:
        try:
            _engine = _Direct2D()
        except (OSError, AttributeError, RasterError) as error:
            _engine_error = str(error)
    return _engine


def error() -> str | None:
    _get()
    return _engine_error


def raster(text: str, family: str = "Segoe UI", size: float = 16.0, weight: int = 400) -> Raster:
    engine = _get()
    if engine is None:
        raise RasterError(_engine_error or "Direct2D is not available")
    return engine.raster(text, family, size, weight)
