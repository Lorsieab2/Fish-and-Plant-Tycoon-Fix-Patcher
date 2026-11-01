/* unicode_glyphs.h -- "Unicode Text.dll", both games: every letter of UTF-8 text drawn and
   measured, from the first source that has it.

   1. The game's own font: its letters (Latin-1 is its byte, a Windows-1252 letter such as
      U+20AC its byte 0x80-0x9F), with the patcher-made letters the DLL's extended font
      tables add (unicode_fonts.h). A run of such letters is drawn and measured by the game's
      own code (game_draw, game_width), pixel for pixel as before.
   2. Any other letter is rasterised at run time with Windows' fonts (GDI and Uniscribe):
      the first font of the chain that has a glyph for it, sized to the game font's line
      height (its cell height is the line's), anti-aliased, then made an SDL surface in the
      text's colour and the colour's alpha (the game's colour is 0xAABBGGRR; alpha 0 means
      the game's default colour) and kept for the next draw (up to GLYPH_CACHE of them).
      The chain: Segoe UI, then fonts for Japanese, Chinese and Korean (Yu Gothic, Meiryo,
      Microsoft YaHei, Malgun Gothic), the Indic and other scripts, Segoe UI Historic
      (cuneiform and other historic scripts), Segoe UI Emoji and Segoe UI Symbol. GDI draws
      every glyph in one colour, emoji too.
   3. A letter no font has is drawn as '?' from the game's font.

   In the Use Unicode Font mode (system_font) every letter is rasterised, with the chosen
   font first in the chain, so all of the game's text is drawn in that font, at the game
   fonts' line heights and in the game's colours.

   The GDI, Uniscribe and window functions are looked up when first needed
   (LoadLibraryW / GetProcAddress), so a missing one only means that source is skipped. */
#ifndef FTFP_UNICODE_GLYPHS_H
#define FTFP_UNICODE_GLYPHS_H

#include <usp10.h>

static int system_font;                     /* Use Unicode Font: every letter from Windows' fonts */
static wchar_t chosen_font[64] = L"Segoe UI";

/* ---- the game's font */

static char *font_inner(void *font) {
    return font != NULL ? *(char **)((char *)font + 4) : NULL;
}

static const unsigned short CP1252_HIGH[32] = {
    0x20AC, 0, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021, 0x02C6, 0x2030, 0x0160, 0x2039, 0x0152, 0, 0x017D, 0,
    0, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014, 0x02DC, 0x2122, 0x0161, 0x203A, 0x0153, 0, 0x017E, 0x0178,
};

/* The byte the game's font draws `cp` with, or -1 when it has no letter for it. */
static int font_byte(const char *inner, unsigned int cp) {
    int b = -1, i;
    const int *index, *records;
    if (inner == NULL || system_font) return -1;
    if (cp < 0x100) b = (int)cp;
    else {
        for (i = 0; i < 32; ++i) {
            if (CP1252_HIGH[i] == cp) { b = 0x80 + i; break; }
        }
    }
    if (b < 0) return -1;
    if (b == ' ' || b == '\n') return b;
    index = (const int *)(inner + 0x1C);
    records = *(const int *const *)(inner + 0x18);
    if (records == NULL) return -1;
    return (index[b] != 0 || records[0] == b) ? b : -1;
}

/* The width (right - left) of the font's record for byte b. */
static int font_record_width(const char *inner, int b) {
    const int *records = *(const int *const *)(inner + 0x18);
    const int *rec = records + 5 * ((const int *)(inner + 0x1C))[b];
    return rec[3] - rec[1];
}

/* ---- run-time glyphs */

#define GLYPH_CACHE 1024
#define GLYPH_MAX_H 128
#define GLYPH_MAX_W 512

typedef struct glyph {
    unsigned int cp, colour;
    int height, used;
    void *surface;
    int w, xoff, adv;
} glyph;

static glyph glyphs[GLYPH_CACHE];
static int glyph_count;

typedef void *(__cdecl *sdl_create_fn)(unsigned int, int, int, int, unsigned int, unsigned int, unsigned int, unsigned int);
typedef void (__cdecl *sdl_free_fn)(void *);
typedef int (__cdecl *sdl_blit_fn)(void *, void *, void *, void *);

/* Coverage of one letter (`*w` columns of `height` rows, 0-255), its left edge from the pen and
   its advance; 0 when no font of the chain has it. Separate (and not inlined) so the tests can
   stand in for Windows' fonts. */
__declspec(noinline) static int raster_glyph(unsigned int cp, int height, unsigned char *coverage,
                                             int *w, int *xoff, int *adv);

static void free_glyphs(void) {
    int i;
    for (i = 0; i < GLYPH_CACHE; ++i) {
        if (glyphs[i].used && glyphs[i].surface != NULL) {
            ((sdl_free_fn)(UINT_PTR)GAME_SDL_FREE)(glyphs[i].surface);
        }
        glyphs[i].used = 0;
    }
    glyph_count = 0;
}

static const glyph *get_glyph(unsigned int cp, int height, unsigned int colour) {
    static unsigned char coverage[GLYPH_MAX_W * GLYPH_MAX_H];
    unsigned int at = (cp * 2654435761u ^ (unsigned int)height * 40503u ^ colour * 2246822519u) % GLYPH_CACHE;
    glyph *g;
    int w = 0, xoff = 0, adv = 0, x, y, pitch;
    unsigned int alpha = colour >> 24, rgb;
    unsigned char *pixels;
    if (height < 1) height = 1;
    if (height > GLYPH_MAX_H) height = GLYPH_MAX_H;
    for (;;) {
        g = &glyphs[at];
        if (!g->used) break;
        if (g->cp == cp && g->height == height && g->colour == colour) return g->adv >= 0 ? g : NULL;
        at = (at + 1) % GLYPH_CACHE;
    }
    if (glyph_count >= GLYPH_CACHE * 3 / 4) {
        free_glyphs();
        return get_glyph(cp, height, colour);
    }
    g->cp = cp;
    g->height = height;
    g->colour = colour;
    g->used = 1;
    g->surface = NULL;
    ++glyph_count;
    if (!raster_glyph(cp, height, coverage, &w, &xoff, &adv)) {
        g->adv = -1;                         /* no font has it: kept, so it is looked for once */
        g->w = 0;
        return NULL;
    }
    g->w = w;
    g->xoff = xoff;
    g->adv = adv;
    if (w <= 0) return g;
    g->surface = ((sdl_create_fn)(UINT_PTR)GAME_SDL_CREATE)(0, w, height, 32, 0x00FF0000u, 0x0000FF00u,
                                                             0x000000FFu, 0xFF000000u);
    if (g->surface == NULL) return g;
    pitch = *(const unsigned short *)((char *)g->surface + 0x10);
    pixels = *(unsigned char **)((char *)g->surface + 0x14);
    rgb = ((colour & 0xFF) << 16) | (colour & 0xFF00) | ((colour >> 16) & 0xFF);
    for (y = 0; y < height; ++y) {
        unsigned int *row = (unsigned int *)(pixels + y * pitch);
        for (x = 0; x < w; ++x) {
            unsigned int a = coverage[y * w + x] * alpha / 255;
            row[x] = (a << 24) | rgb;
        }
    }
    return g;
}

/* The advance of a letter drawn at run time (0 when none has it). */
static int glyph_advance(unsigned int cp, int height) {
    const glyph *g = get_glyph(cp, height, 0xFFFFFFFFu);
    return g != NULL ? g->adv : -1;
}

static void blit_glyph(void *graphics, const glyph *g, int x, int y) {
    const int *clip = (const int *)((char *)graphics + GAME_CLIP);
    void *screen = *(void **)((char *)graphics + 0x30);
    int l = x, t = y, r = x + g->w, b = y + g->height;
    if (g->surface == NULL || screen == NULL) return;
    if (l < clip[0]) l = clip[0];
    if (t < clip[1]) t = clip[1];
    if (r > clip[2]) r = clip[2];
    if (b > clip[3]) b = clip[3];
    if (r <= l || b <= t) return;
#if GAME_SDL2
    {
        int src[4], dst[4];
        src[0] = l - x; src[1] = t - y; src[2] = r - l; src[3] = b - t;
        dst[0] = l; dst[1] = t; dst[2] = r - l; dst[3] = b - t;
        ((sdl_blit_fn)(UINT_PTR)GAME_SDL_BLIT)(g->surface, src, screen, dst);
    }
#else
    {
        short src[4], dst[4];
        src[0] = (short)(l - x); src[1] = (short)(t - y); src[2] = (short)(r - l); src[3] = (short)(b - t);
        dst[0] = (short)l; dst[1] = (short)t; dst[2] = (short)(r - l); dst[3] = (short)(b - t);
        ((sdl_blit_fn)(UINT_PTR)GAME_SDL_BLIT)(g->surface, src, screen, dst);
    }
#endif
}

/* ---- drawing and measuring UTF-8 text */

#define RUN_BYTES 2048

/* The whole text as the font's bytes when the font has every letter (the game's own code then
   draws and measures it), else 0. */
static int all_font_bytes(const char *inner, const char *text, char *out, int cap) {
    const unsigned char *p = (const unsigned char *)text;
    int n = 0;
    while (*p) {
        int b = font_byte(inner, utf8_next(&p));
        if (b < 0 || n >= cap - 1) return 0;
        out[n++] = (char)b;
    }
    out[n] = '\0';
    return 1;
}

static int unicode_width(void *font, const char *text, float scale) {
    static char bytes[RUN_BYTES];
    const char *inner = font_inner(font);
    const unsigned char *p = (const unsigned char *)text;
    int line = 0, widest = 0, spacing, height;
    if (text == NULL || inner == NULL) return game_width(font, text, scale);
    if (all_font_bytes(inner, text, bytes, sizeof bytes)) return game_width(font, bytes, scale);
    spacing = *(const int *)(inner + 8);
    height = *(const int *)(inner + 4);
    while (*p) {
        unsigned int cp = utf8_next(&p);
        int b, adv;
        if (cp == '\n') {
            if (line > widest) widest = line;
            line = 0;
            continue;
        }
        b = font_byte(inner, cp);
        if (b >= 0) adv = font_record_width(inner, b);
        else {
            adv = glyph_advance(cp, height);
            if (adv < 0) {
                b = font_byte(inner, '?');
                adv = b >= 0 ? font_record_width(inner, b) : 0;
            }
        }
        line += (int)((double)(spacing + adv) * (double)scale);
    }
    if (line > widest) widest = line;
    return widest ? widest - spacing : 0;
}

static void unicode_draw(void *graphics, const char *text, int x, int y, unsigned int colour, void *font) {
    static char run[RUN_BYTES];
    void *used = font != NULL ? font : *(void **)((char *)graphics + GAME_DEFAULT_FONT);
    const char *inner = font_inner(used);
    const unsigned char *p = (const unsigned char *)text;
    unsigned int shade = colour;
    int n = 0, run_x = x, pen = x, spacing, height;
    if (text == NULL || inner == NULL || *(const int *)(inner + 0xC) == 0) {
        game_draw(graphics, text, x, y, colour, font);
        return;
    }
    if (all_font_bytes(inner, text, run, sizeof run)) {
        game_draw(graphics, run, x, y, colour, font);
        return;
    }
    if ((shade >> 24) == 0) shade = *(const unsigned int *)(UINT_PTR)GAME_DEFAULT_COLOUR;
    spacing = *(const int *)(inner + 8);
    height = *(const int *)(inner + 4);
    while (*p) {
        unsigned int cp = utf8_next(&p);
        int b;
        if (cp == '\n' || n >= RUN_BYTES - 1) {
            if (n) { run[n] = '\0'; game_draw(graphics, run, run_x, y, colour, font); n = 0; }
            if (cp == '\n') { y += height; pen = run_x = x; continue; }
        }
        b = font_byte(inner, cp);
        if (b < 0) {
            const glyph *g = get_glyph(cp, height, shade);
            if (g != NULL) {
                if (n) { run[n] = '\0'; game_draw(graphics, run, run_x, y, colour, font); n = 0; }
                blit_glyph(graphics, g, pen + g->xoff, y);
                pen += g->adv + spacing;
                run_x = pen;
                continue;
            }
            b = font_byte(inner, '?');
            if (b < 0) continue;
        }
        if (n == 0) run_x = pen;
        run[n++] = (char)b;
        pen += font_record_width(inner, b) + spacing;
    }
    if (n) { run[n] = '\0'; game_draw(graphics, run, run_x, y, colour, font); }
}

/* ---- Windows' fonts */

typedef HDC (WINAPI *create_dc_fn)(HDC);
typedef HBITMAP (WINAPI *create_dib_fn)(HDC, const BITMAPINFO *, UINT, void **, HANDLE, DWORD);
typedef HGDIOBJ (WINAPI *select_fn)(HDC, HGDIOBJ);
typedef HFONT (WINAPI *create_font_fn)(int, int, int, int, int, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD,
                                       DWORD, LPCWSTR);
typedef COLORREF (WINAPI *text_colour_fn)(HDC, COLORREF);
typedef int (WINAPI *bk_mode_fn)(HDC, int);
typedef BOOL (WINAPI *ext_text_fn)(HDC, int, int, UINT, const RECT *, LPCWSTR, UINT, const INT *);
typedef BOOL (WINAPI *flush_fn)(void);
typedef UINT (WINAPI *align_fn)(HDC, UINT);
typedef HRESULT (WINAPI *itemize_fn)(const WCHAR *, int, int, const SCRIPT_CONTROL *, const SCRIPT_STATE *,
                                     SCRIPT_ITEM *, int *);
typedef HRESULT (WINAPI *shape_fn)(HDC, SCRIPT_CACHE *, const WCHAR *, int, int, SCRIPT_ANALYSIS *, WORD *, WORD *,
                                   SCRIPT_VISATTR *, int *);
typedef HRESULT (WINAPI *place_fn)(HDC, SCRIPT_CACHE *, const WORD *, int, const SCRIPT_VISATTR *, SCRIPT_ANALYSIS *,
                                   int *, GOFFSET *, ABC *);
typedef HRESULT (WINAPI *props_fn)(HDC, SCRIPT_CACHE *, SCRIPT_FONTPROPERTIES *);

static struct {
    int tried, ready;
    create_dc_fn create_dc;
    create_dib_fn create_dib;
    select_fn select;
    create_font_fn create_font;
    text_colour_fn text_colour;
    bk_mode_fn bk_mode;
    ext_text_fn ext_text;
    flush_fn flush;
    align_fn align;
    itemize_fn itemize;
    shape_fn shape;
    place_fn place;
    props_fn props;
    HDC dc;
    unsigned char *bits;
} gdi;

#define DIB_W GLYPH_MAX_W
#define DIB_H GLYPH_MAX_H

static const wchar_t *const CHAIN[] = {
    L"Segoe UI", L"Yu Gothic", L"Meiryo", L"Microsoft YaHei", L"Malgun Gothic", L"Nirmala UI", L"Leelawadee UI",
    L"Ebrima", L"Gadugi", L"Myanmar Text", L"Mongolian Baiti", L"Microsoft Himalaya", L"Javanese Text",
    L"Segoe UI Historic", L"Segoe UI Emoji", L"Segoe UI Symbol", L"Sylfaen",
};
#define CHAIN_FONTS ((int)(sizeof CHAIN / sizeof CHAIN[0]))

typedef struct face {
    int chain, height;
    HFONT font;
    SCRIPT_CACHE cache;
    WORD missing;
} face;

static face faces[64];
static int face_count;

static int gdi_start(void) {
    HMODULE g, u;
    BITMAPINFO info;
    void *bits = NULL;
    HBITMAP dib;
    if (gdi.tried) return gdi.ready;
    gdi.tried = 1;
    g = LoadLibraryW(L"gdi32.dll");
    u = LoadLibraryW(L"usp10.dll");
    if (g == NULL || u == NULL) return 0;
    gdi.create_dc = (create_dc_fn)(UINT_PTR)GetProcAddress(g, "CreateCompatibleDC");
    gdi.create_dib = (create_dib_fn)(UINT_PTR)GetProcAddress(g, "CreateDIBSection");
    gdi.select = (select_fn)(UINT_PTR)GetProcAddress(g, "SelectObject");
    gdi.create_font = (create_font_fn)(UINT_PTR)GetProcAddress(g, "CreateFontW");
    gdi.text_colour = (text_colour_fn)(UINT_PTR)GetProcAddress(g, "SetTextColor");
    gdi.bk_mode = (bk_mode_fn)(UINT_PTR)GetProcAddress(g, "SetBkMode");
    gdi.ext_text = (ext_text_fn)(UINT_PTR)GetProcAddress(g, "ExtTextOutW");
    gdi.flush = (flush_fn)(UINT_PTR)GetProcAddress(g, "GdiFlush");
    gdi.align = (align_fn)(UINT_PTR)GetProcAddress(g, "SetTextAlign");
    gdi.itemize = (itemize_fn)(UINT_PTR)GetProcAddress(u, "ScriptItemize");
    gdi.shape = (shape_fn)(UINT_PTR)GetProcAddress(u, "ScriptShape");
    gdi.place = (place_fn)(UINT_PTR)GetProcAddress(u, "ScriptPlace");
    gdi.props = (props_fn)(UINT_PTR)GetProcAddress(u, "ScriptGetFontProperties");
    if (!gdi.create_dc || !gdi.create_dib || !gdi.select || !gdi.create_font || !gdi.text_colour || !gdi.bk_mode
        || !gdi.ext_text || !gdi.flush || !gdi.align || !gdi.itemize || !gdi.shape || !gdi.place || !gdi.props) {
        return 0;
    }
    gdi.dc = gdi.create_dc(NULL);
    if (gdi.dc == NULL) return 0;
    memset(&info, 0, sizeof info);
    info.bmiHeader.biSize = sizeof info.bmiHeader;
    info.bmiHeader.biWidth = DIB_W;
    info.bmiHeader.biHeight = -DIB_H;
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    dib = gdi.create_dib(gdi.dc, &info, DIB_RGB_COLORS, &bits, NULL, 0);
    if (dib == NULL || bits == NULL) return 0;
    gdi.select(gdi.dc, dib);
    gdi.text_colour(gdi.dc, RGB(255, 255, 255));
    gdi.bk_mode(gdi.dc, TRANSPARENT);
    gdi.align(gdi.dc, TA_TOP | TA_LEFT | TA_NOUPDATECP);
    gdi.bits = (unsigned char *)bits;
    gdi.ready = 1;
    return 1;
}

static const wchar_t *chain_name(int i) {
    return i < 0 ? chosen_font : CHAIN[i];
}

static face *get_face(int chain, int height) {
    face *f;
    int i;
    SCRIPT_FONTPROPERTIES props;
    for (i = 0; i < face_count; ++i) {
        if (faces[i].chain == chain && faces[i].height == height) return &faces[i];
    }
    if (face_count >= 64) return NULL;
    f = &faces[face_count];
    memset(f, 0, sizeof *f);
    f->chain = chain;
    f->height = height;
    f->font = gdi.create_font(height, 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS,
                              CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, chain_name(chain));
    if (f->font == NULL) return NULL;
    gdi.select(gdi.dc, f->font);
    memset(&props, 0, sizeof props);
    props.cBytes = sizeof props;
    if (gdi.props(gdi.dc, &f->cache, &props) != S_OK) return NULL;
    f->missing = props.wgDefault;
    ++face_count;
    return f;
}

__declspec(noinline) static int raster_glyph(unsigned int cp, int height, unsigned char *coverage,
                                             int *w, int *xoff, int *adv) {
    WCHAR units[2];
    int n = 1, c, first = system_font ? -1 : 0;
    if (!gdi_start()) return 0;
    if (cp >= 0x10000) {
        units[0] = (WCHAR)(0xD800 + ((cp - 0x10000) >> 10));
        units[1] = (WCHAR)(0xDC00 + ((cp - 0x10000) & 0x3FF));
        n = 2;
    } else {
        units[0] = (WCHAR)cp;
    }
    for (c = first; c < CHAIN_FONTS; ++c) {
        SCRIPT_ITEM items[4];
        WORD ids[8], clusters[2];
        SCRIPT_VISATTR attrs[8];
        int advances[8], items_n = 0, ids_n = 0, i, x, y, left = -1, right = -1, pad = height;
        GOFFSET offsets[8];
        ABC abc;
        face *f = get_face(c, height);
        if (f == NULL) continue;
        gdi.select(gdi.dc, f->font);
        if (gdi.itemize(units, n, 3, NULL, NULL, items, &items_n) != S_OK || items_n < 1) continue;
        if (gdi.shape(gdi.dc, &f->cache, units, n, 8, &items[0].a, ids, clusters, attrs, &ids_n) != S_OK
            || ids_n < 1) {
            continue;
        }
        for (i = 0; i < ids_n && ids[i] != f->missing; ++i) {}
        if (i < ids_n) continue;
        if (gdi.place(gdi.dc, &f->cache, ids, ids_n, attrs, &items[0].a, advances, offsets, &abc) != S_OK) continue;
        *adv = abc.abcA + (int)abc.abcB + abc.abcC;
        if (*adv < 0) *adv = 0;
        if (pad * 2 + *adv > DIB_W) pad = (DIB_W - *adv) / 2;
        if (pad < 0) return 0;
        for (y = 0; y < height; ++y) memset(gdi.bits + y * DIB_W * 4, 0, DIB_W * 4);
        gdi.ext_text(gdi.dc, pad, 0, ETO_GLYPH_INDEX, NULL, (LPCWSTR)ids, (UINT)ids_n, advances);
        gdi.flush();
        for (x = 0; x < DIB_W; ++x) {
            for (y = 0; y < height; ++y) {
                if (gdi.bits[(y * DIB_W + x) * 4 + 1]) {
                    if (left < 0) left = x;
                    right = x;
                    break;
                }
            }
        }
        if (left < 0) {
            *w = 0;
            *xoff = 0;
            return 1;
        }
        *w = right - left + 1;
        *xoff = left - pad;
        for (y = 0; y < height; ++y) {
            for (x = 0; x < *w; ++x) coverage[y * *w + x] = gdi.bits[(y * DIB_W + left + x) * 4 + 1];
        }
        return 1;
    }
    return 0;
}

#endif
