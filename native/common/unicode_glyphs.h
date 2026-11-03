/* unicode_glyphs.h -- "Unicode Text.dll", both games: every letter of UTF-8 text drawn and
   measured, from the first source that has it (the shared Unicode spec's glyph source order,
   UNICODE_SPEC.md row 3).

   1. The game's own font: its letters (Latin-1 is its byte, a Windows-1252 letter such as
      U+20AC its byte 0x80-0x9F). A run of such letters is drawn and measured by the game's
      own code (game_draw, game_width), pixel for pixel as before.
   2. The patcher-made letters the DLL's extended font tables add (unicode_fonts.h, made by
      scripts/build_unicode_assets.py in each font's style), drawn the same way.
   3. Any other letter is drawn at run time from Windows' fonts (GDI and Uniscribe) in the game
      font's STYLE (unicode_styles.h, measured from the game's own font picture by
      src/text_maker.py, the numbers the Text Maker's patcher-made letters use): the em at which
      Segoe UI's capital H is as tall as the font's own, the weight whose stem is nearest the
      font's, the letter standing on the font's baseline, the font's side bearings, and its
      coverage taken to the font's own alpha steps; then made an SDL surface in the text's
      colour and the colour's alpha (the game's colour is 0xAABBGGRR; alpha 0 means the game's
      default colour) and kept for the next draw (up to GLYPH_CACHE of them).
      The font is the first of the shared fallback chain (CHAIN, the spec's list in its order:
      Segoe UI, Segoe UI Historic, Segoe UI Symbol, Segoe UI Emoji, the CJK fonts, Nirmala UI,
      Ebrima ... Cambria Math, the Noto fonts if installed; then the fonts the patcher ships)
      whose character map has EVERY code point of the piece (ScriptGetCMap) and that is
      installed (a face Windows would substitute is skipped).
      A colour font's letter (a font with a COLR, CBDT, sbix or SVG table: Segoe UI Emoji's
      emoji) is drawn by Direct2D and DirectWrite instead, as the patcher's Text Maker draws
      them (src/text_raster.py: a DC render target on the same 32-bit DIB, grayscale
      anti-aliasing, D2D1_DRAW_TEXT_OPTIONS_ENABLE_COLOR_FONT, a white brush), at the same em
      with its baseline on the font's: when that drawing has colour, the surface keeps the
      font's colours (never tinted with the text's colour) with the text's alpha. d2d1.dll and
      dwrite.dll are loaded when first needed; without them (or when a call fails) the letter
      is drawn in one colour by GDI as before.
   4. A letter no font has is the MISSING-GLYPH BOX, drawn in the font's style: as tall as its
      capitals, two thirds as wide, on its baseline, with a stroke of half its stem, in the
      text's colour (missing_box; the same box src/text_maker.py draws).

   PIECES.  Text is taken a UNIT at a time (next_unit): a grapheme cluster (unicode_grapheme.h:
   a letter with its marks, an emoji ZWJ sequence, a flag, a keycap), or a RUN of a script that
   needs shaping (Arabic, Hebrew, Syriac, Thaana, N'Ko, the Indic scripts, Thai, Lao, Tibetan,
   Myanmar, Khmer, Mongolian: complex_cp) with its marks, joiners, digits and the spaces
   between its words, as Virtual Villagers' text_utf8.h ut_unit takes them. A cluster that
   composes to one letter (NFC: e + U+0301 is U+00E9; unicode_compose_table.h) is that letter,
   so the game's own é draws it. A run is shaped and ordered by Uniscribe as a whole
   (ScriptItemize, ScriptLayout for the right-to-left order of its items, ScriptShape,
   ScriptPlace, ScriptTextOut): joined Arabic letters, Indic reordering, Hebrew right to left.
   A run no single font has is drawn a cluster at a time; a cluster no font has whole, a code
   point at a time.

   In the Use Unicode Font mode (system_font) every letter is drawn at run time, with the chosen
   font first in the chain (then Segoe UI and the rest), each game font keeping its line height,
   baseline, weight and alpha steps, at the em fitted so that "The quick brown fox jumps over
   the lazy dog 0123456789" is as wide as the game font draws it, kept within 60%..130% of the
   style's own em (fit_em, as Virtual Families 1's FitChosenFont).

   The GDI, Uniscribe and window functions are looked up when first needed
   (LoadLibraryW / GetProcAddress), so a missing one only means that source is skipped.

   UNICODE 18.0.  After Windows' fonts the chain has the fonts the patcher ships beside the DLL
   ("<Game> Fix Patcher DLLs\Fonts", loaded for this process only with
   AddFontResourceExW(FR_PRIVATE)): GNU Unifont and Unifont Upper (bitmap letters, the games'
   pixel look), Noto Serif Tangut and Noto Sans Cuneiform for what neither Windows nor Unifont
   has, and Unicode's Last Resort font last, whose block placeholder stands for any code point
   no other font has (a letter newer than every font). So every assigned code point of Unicode
   18.0 draws (tests/test_unicode18.py). A font that refuses a script
   (USP_E_SCRIPT_NOT_IN_FONT) is asked again with no shaping (SCRIPT_UNDEFINED). A font file
   chosen in the patcher's "Unicode Font..." window (File= in Unicode Text.ini, copied beside
   the DLL) is loaded the same way. */
#ifndef FTFP_UNICODE_GLYPHS_H
#define FTFP_UNICODE_GLYPHS_H

#include <usp10.h>
#include "unicode_grapheme.h"
#include "unicode_compose_table.h"

static int system_font;                     /* Use Unicode Font: every letter from Windows' fonts */
static wchar_t chosen_font[64] = L"Segoe UI";
static wchar_t chosen_file[128];            /* File=: a font file beside the DLL, loaded privately */

/* ---- the game's fonts and their styles */

typedef struct font_style {
    unsigned int stock_table;               /* the game's own glyph table (Use Unicode Font) */
    const int *dll_table;                   /* the DLL's extended one (Render with In-Game Fonts) */
    int height, cap_top, baseline, em, weight, left, right, stroke;
    unsigned char levels[256];              /* coverage -> the nearest of the font's alpha steps */
} font_style;

#include "unicode_styles.h"                 /* FONT_STYLES: native/ftfp_<game>_unicode, generated */

/* The style letters drawn now are made in (pen_for): the font's, or for a font this DLL does
   not know one made from its line height. */
static struct {
    int id;                                 /* FONT_STYLES index + 1; 0: not a known font */
    int height, cap_top, baseline, em, weight, left, right, stroke;
    const unsigned char *levels;            /* NULL: coverage as drawn */
    int game_fit;                           /* the fit sentence's width in the game font (Use Unicode Font) */
} pen;

static const char FIT_SENTENCE[] = "The quick brown fox jumps over the lazy dog 0123456789";

static char *font_inner(void *font) {
    return font != NULL ? *(char **)((char *)font + 4) : NULL;
}

/* CP1252_HIGH (Windows-1252's 0x80-0x9F) is in unicode_utf8.h, shared with the read rule. */

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

/* The pen set to FONT_STYLES[index] (or, index < 0, a style made from `height`). Separate (and not
   inlined) so the native tests and the preview sheet can set a game font's style. */
__declspec(noinline) static void pen_for_style(int index, int height) {
    if (index >= 0 && index < FONT_STYLE_COUNT) {
        const font_style *s = &FONT_STYLES[index];
        pen.id = index + 1;
        pen.height = s->height;
        pen.cap_top = s->cap_top;
        pen.baseline = s->baseline;
        pen.em = s->em;
        pen.weight = s->weight;
        pen.left = s->left;
        pen.right = s->right;
        pen.stroke = s->stroke;
        pen.levels = s->levels;
        return;
    }
    pen.id = 0;
    pen.height = height;
    pen.cap_top = height / 5;
    pen.baseline = height * 4 / 5;
    pen.em = height;
    pen.weight = FW_SEMIBOLD;
    pen.left = 0;
    pen.right = 1;
    pen.stroke = height >= 24 ? 2 : 1;
    pen.levels = NULL;
}

/* The pen for the game font `inner`: its style when it is one of the game's fonts (its glyph
   table is the game's own or this DLL's extended one). */
static void pen_for(const char *inner) {
    const int *records = inner != NULL ? *(const int *const *)(inner + 0x18) : NULL;
    int i, height = inner != NULL ? *(const int *)(inner + 4) : 16;
    for (i = 0; i < FONT_STYLE_COUNT; ++i) {
        if ((unsigned int)(UINT_PTR)records == FONT_STYLES[i].stock_table || records == FONT_STYLES[i].dll_table) break;
    }
    pen_for_style(i < FONT_STYLE_COUNT ? i : -1, height);
    if (pen.id) pen.height = height;           /* the line the game lays out */
    pen.game_fit = 0;
    if (system_font && inner != NULL && records != NULL) {
        const char *c;
        for (c = FIT_SENTENCE; *c; ++c) pen.game_fit += font_record_width(inner, (unsigned char)*c);
    }
}

/* ---- run-time glyphs */

#define GLYPH_CACHE 1024
#define GLYPH_MAX_H 128
#define GLYPH_MAX_W 1024

typedef struct glyph {
    unsigned int cp, colour;         /* cp: the code point, or a piece's hash (n > 1) */
    unsigned int key2;               /* a piece's second hash */
    int n;                           /* its code points */
    int height, style, used;
    void *surface;
    int w, xoff, adv;
} glyph;

static glyph glyphs[GLYPH_CACHE];
static int glyph_count;

typedef void *(__cdecl *sdl_create_fn)(unsigned int, int, int, int, unsigned int, unsigned int, unsigned int, unsigned int);
typedef void (__cdecl *sdl_free_fn)(void *);
typedef int (__cdecl *sdl_blit_fn)(void *, void *, void *, void *);

/* Coverage of one letter (`*w` columns of `height` rows, 0-255), its left edge from the pen and
   its advance: 1; or, for a colour letter, its premultiplied B, G, R, A pixels (4 bytes each,
   `*w` columns of `height` rows): 2; 0 when no font of the chain has it. Separate (and not
   inlined) so the tests can stand in for Windows' fonts. */
__declspec(noinline) static int raster_glyph(unsigned int cp, int height, unsigned char *coverage,
                                             int *w, int *xoff, int *adv);
/* The same for a whole piece of n > 1 code points (a grapheme, or a run to shape), shaped together:
   0 when no font has all of it. */
__declspec(noinline) static int raster_cluster(const unsigned int *cps, int n, int height, unsigned char *coverage,
                                               int *w, int *xoff, int *adv);

static unsigned int piece_key2(const unsigned int *cps, int n) {
    unsigned int h = 0x9E3779B9u ^ (unsigned int)n;
    int k;
    for (k = 0; k < n; ++k) h = (h ^ cps[k]) * 0x85EBCA6Bu + (h >> 13);
    return h;
}

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

/* The missing-glyph box in the pen's style: `*w` columns of `height` rows of coverage, its advance
   the same (src/text_maker.py _missing_box: two thirds of the capital height wide, from the capital
   top to the baseline, a column of room each side). */
static int missing_box(int height, unsigned char *coverage, int *w, int *xoff, int *adv) {
    int inner = (pen.baseline - pen.cap_top) * 2 / 3, top = pen.cap_top, bottom = pen.baseline - 1, x, y, s;
    if (inner < 4) inner = 4;
    if (bottom >= height) bottom = height - 1;
    if (top > bottom - 2) top = bottom - 2;
    if (top < 0) top = 0;
    s = pen.stroke < 1 ? 1 : pen.stroke;
    *w = inner + 2;
    *xoff = 0;
    *adv = inner + 2;
    memset(coverage, 0, (size_t)(*w * height));
    for (y = top; y <= bottom; ++y) {
        for (x = 1; x <= inner; ++x) {
            if (y < top + s || y > bottom - s || x < 1 + s || x > inner - s) coverage[y * *w + x] = 255;
        }
    }
    return 1;
}

/* The drawn piece for one code point (n 1) or a whole piece (n > 1) in the pen's style, NULL when
   no font has a piece of several code points. A code point no font has is the missing-glyph box. */
static const glyph *get_piece(const unsigned int *cps, int n, unsigned int colour) {
    static unsigned char coverage[GLYPH_MAX_W * GLYPH_MAX_H * 4];
    int height = pen.height;
    unsigned int cp = n == 1 ? cps[0] : gb_fnv(cps, n), key2 = n == 1 ? 0 : piece_key2(cps, n);
    unsigned int at;
    glyph *g;
    int w = 0, xoff = 0, adv = 0, x, y, pitch, kind;
    unsigned int alpha = colour >> 24, rgb;
    unsigned char *pixels;
    if (height < 1) height = 1;
    if (height > GLYPH_MAX_H) height = GLYPH_MAX_H;
    at = (cp * 2654435761u ^ (unsigned int)height * 40503u ^ colour * 2246822519u ^ (unsigned int)pen.id * 97u)
         % GLYPH_CACHE;
    for (;;) {
        g = &glyphs[at];
        if (!g->used) break;
        if (g->cp == cp && g->key2 == key2 && g->n == n && g->height == height && g->colour == colour
            && g->style == pen.id) {
            return g->adv >= 0 ? g : NULL;
        }
        at = (at + 1) % GLYPH_CACHE;
    }
    if (glyph_count >= GLYPH_CACHE * 3 / 4) {
        free_glyphs();
        return get_piece(cps, n, colour);
    }
    g->cp = cp;
    g->key2 = key2;
    g->n = n;
    g->height = height;
    g->colour = colour;
    g->style = pen.id;
    g->used = 1;
    g->surface = NULL;
    ++glyph_count;
    kind = n == 1 ? raster_glyph(cp, height, coverage, &w, &xoff, &adv)
                  : raster_cluster(cps, n, height, coverage, &w, &xoff, &adv);
    /* a code point no font has: the missing-glyph box */
    if (!kind && n == 1) kind = missing_box(height, coverage, &w, &xoff, &adv);
    if (!kind) {
        g->adv = -1;                         /* no font has it whole: kept, so it is looked for once */
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
    if (kind == 2) {
        /* a colour letter: the font's own colours (premultiplied in, straight out), the text's alpha */
        for (y = 0; y < height; ++y) {
            unsigned int *row = (unsigned int *)(pixels + y * pitch);
            for (x = 0; x < w; ++x) {
                const unsigned char *px = coverage + (y * w + x) * 4;
                unsigned int a = px[3], c[3], k;
                if (a == 0) {
                    row[x] = 0;
                    continue;
                }
                for (k = 0; k < 3; ++k) {
                    c[k] = (px[k] * 255u + a / 2) / a;
                    if (c[k] > 255) c[k] = 255;
                }
                row[x] = ((a * alpha / 255) << 24) | (c[2] << 16) | (c[1] << 8) | c[0];
            }
        }
        return g;
    }
    rgb = ((colour & 0xFF) << 16) | (colour & 0xFF00) | ((colour >> 16) & 0xFF);
    for (y = 0; y < height; ++y) {
        unsigned int *row = (unsigned int *)(pixels + y * pitch);
        for (x = 0; x < w; ++x) {
            unsigned int c = coverage[y * w + x], a;
            if (pen.levels != NULL) c = pen.levels[c];          /* the font's own alpha steps */
            a = c * alpha / 255;
            row[x] = (a << 24) | rgb;
        }
    }
    return g;
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

/* ---- composition (NFC) and units */

static unsigned int compose_pair(unsigned int a, unsigned int b) {
    int lo = 0, hi = COMPOSE_COUNT - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        const unsigned int *e = COMPOSE[mid];
        if (a < e[0] || (a == e[0] && b < e[1])) hi = mid - 1;
        else if (a > e[0] || b > e[1]) lo = mid + 1;
        else return e[2];
    }
    return 0;
}

/* The one precomposed letter a cluster of n > 1 code points is in NFC (e + U+0301 = U+00E9), else 0. */
static unsigned int compose_cluster(const unsigned int *cps, int n) {
    unsigned int c = cps[0];
    int k;
    for (k = 1; k < n && c; ++k) c = compose_pair(c, cps[k]);
    return c;
}

/* A script Windows must shape: joined letters, reordered marks, right to left (VV ut_complex). */
static int complex_cp(unsigned int cp) {
    return (cp >= 0x0590 && cp <= 0x08FF) || (cp >= 0x0900 && cp <= 0x0DFF) || (cp >= 0x0E00 && cp <= 0x0FFF)
        || (cp >= 0x1000 && cp <= 0x109F) || (cp >= 0x1780 && cp <= 0x18AF) || (cp >= 0x1900 && cp <= 0x1AAF)
        || (cp >= 0xA8E0 && cp <= 0xA8FF) || (cp >= 0xA9E0 && cp <= 0xA9FF) || (cp >= 0xAA60 && cp <= 0xAA7F)
        || (cp >= 0xFB1D && cp <= 0xFDFF) || (cp >= 0xFE70 && cp <= 0xFEFF)
        || (cp >= 0x10800 && cp <= 0x10FFF) || (cp >= 0x1E800 && cp <= 0x1EFFF);
}

#define UNIT_MAX 256

/* The unit at *p (a grapheme, or a run of a script to shape with its digits and the spaces between
   its words), its code points (at most `cap`) into cps, *p moved past it; *clusters: how many
   graphemes. Returns how many code points were kept, 0 at the end. */
static int next_unit(const unsigned char **p, unsigned int *cps, int cap, int *clusters) {
    const unsigned char *q = *p;
    int n = next_grapheme(&q, cps, cap < GRAPHEME_MAX ? cap : GRAPHEME_MAX);
    *clusters = n > 0;
    if (n == 0 || !complex_cp(cps[0]) || cps[0] == 0xFEFF) {
        *p = q;
        return n;
    }
    for (;;) {
        const unsigned char *r = q, *s;
        unsigned int more[GRAPHEME_MAX];
        int m;
        while (*r == ' ') ++r;
        s = r;
        m = next_grapheme(&s, more, GRAPHEME_MAX);
        if (m == 0) break;
        if (!(complex_cp(more[0]) && more[0] != 0xFEFF)
            && !(r == q && ((more[0] >= 0x0660 && more[0] <= 0x0669) || (more[0] >= 0x06F0 && more[0] <= 0x06F9)))) {
            break;
        }
        if (n + (int)(r - q) + m > cap) break;
        while (q < r) {
            cps[n++] = ' ';
            ++q;
        }
        memcpy(cps + n, more, sizeof(unsigned int) * (size_t)m);
        n += m;
        q = s;
        ++*clusters;
    }
    *p = q;
    return n;
}

/* ---- drawing and measuring UTF-8 text */

#define RUN_BYTES 2048

/* The whole text as the font's bytes when the font has every letter, composed (the game's own code
   then draws and measures it), else 0. */
static int all_font_bytes(const char *inner, const char *text, char *out, int cap) {
    const unsigned char *p = (const unsigned char *)text;
    int n = 0;
    while (*p) {
        unsigned int cps[GRAPHEME_MAX], cp;
        int k = next_grapheme(&p, cps, GRAPHEME_MAX), b;
        cp = k == 1 ? cps[0] : k > 1 ? compose_cluster(cps, k) : 0;
        b = cp ? font_byte(inner, cp) : -1;
        if (b < 0 || n >= cap - 1) return 0;
        out[n++] = (char)b;
    }
    out[n] = '\0';
    return 1;
}

/* A grapheme that ends a line ("\n", or CR LF). */
static int is_newline(const unsigned int *cps, int n) {
    return cps[n - 1] == '\n';
}

/* One pass over a text: drawn (graphics set) or measured. */
typedef struct walk {
    void *graphics, *font;
    const char *inner;
    unsigned int colour, shade;
    int x, y, pen, run_x, count, spacing, height, line, widest;
    float scale;
    char *run;
} walk;

static void walk_flush(walk *w) {
    if (w->graphics != NULL && w->count) {
        w->run[w->count] = '\0';
        game_draw(w->graphics, w->run, w->run_x, w->y, w->colour, w->font);
        w->count = 0;
    }
}

static void walk_byte(walk *w, int b) {
    int width = font_record_width(w->inner, b);
    if (w->graphics == NULL) {
        w->line += (int)((double)(w->spacing + width) * (double)w->scale);
        return;
    }
    if (w->count >= RUN_BYTES - 1) walk_flush(w);
    if (w->count == 0) w->run_x = w->pen;
    w->run[w->count++] = (char)b;
    w->pen += width + w->spacing;
}

static void walk_piece(walk *w, const glyph *g) {
    if (w->graphics == NULL) {
        w->line += (int)((double)(w->spacing + g->adv) * (double)w->scale);
        return;
    }
    walk_flush(w);
    blit_glyph(w->graphics, g, w->pen + g->xoff, w->y);
    w->pen += g->adv + w->spacing;
    w->run_x = w->pen;
}

static unsigned int walk_shade(const walk *w) {
    return w->graphics != NULL ? w->shade : 0xFFFFFFFFu;
}

/* One code point: the font's letter, else a run-time one (or the box). */
static void walk_letter(walk *w, unsigned int cp) {
    int b = font_byte(w->inner, cp);
    const glyph *g;
    if (b >= 0) {
        walk_byte(w, b);
        return;
    }
    g = get_piece(&cp, 1, walk_shade(w));
    if (g != NULL) walk_piece(w, g);
}

/* One grapheme: composed to one letter when NFC has one, else drawn whole when a font has all of
   it, else its visible code points one at a time. */
static void walk_cluster(walk *w, const unsigned int *cps, int n) {
    const glyph *g;
    int k;
    if (n > 1) {
        unsigned int c = compose_cluster(cps, n);
        if (c) {
            walk_letter(w, c);
            return;
        }
        g = get_piece(cps, n, walk_shade(w));
        if (g != NULL) {
            walk_piece(w, g);
            return;
        }
        for (k = 0; k < n; ++k) {
            if (!gb_invisible(cps[k])) walk_letter(w, cps[k]);
        }
        return;
    }
    walk_letter(w, cps[0]);
}

static void walk_text(walk *w, const char *text) {
    static unsigned int cps[UNIT_MAX];
    const unsigned char *p = (const unsigned char *)text;
    while (*p) {
        const unsigned char *start = p;
        int clusters, n = next_unit(&p, cps, UNIT_MAX, &clusters);
        if (n == 0) break;
        if (is_newline(cps, n)) {
            if (w->graphics != NULL) {
                walk_flush(w);
                w->y += w->height;
                w->pen = w->run_x = w->x;
            } else {
                if (w->line > w->widest) w->widest = w->line;
                w->line = 0;
            }
            continue;
        }
        if (clusters > 1) {
            /* a run to shape: whole, else a cluster at a time */
            const glyph *g = get_piece(cps, n, walk_shade(w));
            if (g != NULL) {
                walk_piece(w, g);
                continue;
            }
            while (start < p) {
                unsigned int one[GRAPHEME_MAX];
                int k = next_grapheme(&start, one, GRAPHEME_MAX);
                if (k == 0) break;
                walk_cluster(w, one, k);
            }
            continue;
        }
        walk_cluster(w, cps, n);
    }
}

static int unicode_width(void *font, const char *text, float scale) {
    static char bytes[RUN_BYTES];
    walk w;
    const char *inner = font_inner(font);
    if (text == NULL || inner == NULL) return game_width(font, text, scale);
    if (all_font_bytes(inner, text, bytes, sizeof bytes)) return game_width(font, bytes, scale);
    memset(&w, 0, sizeof w);
    w.inner = inner;
    w.font = font;
    w.scale = scale;
    w.spacing = *(const int *)(inner + 8);
    w.height = *(const int *)(inner + 4);
    pen_for(inner);
    walk_text(&w, text);
    if (w.line > w.widest) w.widest = w.line;
    return w.widest ? w.widest - w.spacing : 0;
}

static void unicode_draw(void *graphics, const char *text, int x, int y, unsigned int colour, void *font) {
    static char run[RUN_BYTES];
    walk w;
    void *used = font != NULL ? font : *(void **)((char *)graphics + GAME_DEFAULT_FONT);
    const char *inner = font_inner(used);
    if (text == NULL || inner == NULL || *(const int *)(inner + 0xC) == 0) {
        game_draw(graphics, text, x, y, colour, font);
        return;
    }
    if (all_font_bytes(inner, text, run, sizeof run)) {
        game_draw(graphics, run, x, y, colour, font);
        return;
    }
    memset(&w, 0, sizeof w);
    w.graphics = graphics;
    w.font = font;
    w.inner = inner;
    w.colour = colour;
    w.shade = colour;
    if ((w.shade >> 24) == 0) w.shade = *(const unsigned int *)(UINT_PTR)GAME_DEFAULT_COLOUR;
    w.x = w.pen = w.run_x = x;
    w.y = y;
    w.spacing = *(const int *)(inner + 8);
    w.height = *(const int *)(inner + 4);
    w.scale = 1.0f;
    w.run = run;
    pen_for(inner);
    walk_text(&w, text);
    walk_flush(&w);
}

/* ---- Windows' fonts */

typedef HDC (WINAPI *create_dc_fn)(HDC);
typedef HBITMAP (WINAPI *create_dib_fn)(HDC, const BITMAPINFO *, UINT, void **, HANDLE, DWORD);
typedef HGDIOBJ (WINAPI *select_fn)(HDC, HGDIOBJ);
typedef HFONT (WINAPI *create_font_fn)(int, int, int, int, int, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD,
                                       DWORD, LPCWSTR);
typedef COLORREF (WINAPI *text_colour_fn)(HDC, COLORREF);
typedef int (WINAPI *bk_mode_fn)(HDC, int);
typedef BOOL (WINAPI *flush_fn)(void);
typedef UINT (WINAPI *align_fn)(HDC, UINT);
typedef HRESULT (WINAPI *itemize_fn)(const WCHAR *, int, int, const SCRIPT_CONTROL *, const SCRIPT_STATE *,
                                     SCRIPT_ITEM *, int *);
typedef HRESULT (WINAPI *shape_fn)(HDC, SCRIPT_CACHE *, const WCHAR *, int, int, SCRIPT_ANALYSIS *, WORD *, WORD *,
                                   SCRIPT_VISATTR *, int *);
typedef HRESULT (WINAPI *place_fn)(HDC, SCRIPT_CACHE *, const WORD *, int, const SCRIPT_VISATTR *, SCRIPT_ANALYSIS *,
                                   int *, GOFFSET *, ABC *);
typedef HRESULT (WINAPI *props_fn)(HDC, SCRIPT_CACHE *, SCRIPT_FONTPROPERTIES *);
typedef HRESULT (WINAPI *layout_fn)(int, const BYTE *, int *, int *);
typedef HRESULT (WINAPI *text_out_fn)(HDC, SCRIPT_CACHE *, int, int, UINT, const RECT *, const SCRIPT_ANALYSIS *,
                                      const WCHAR *, int, const WORD *, int, const int *, const int *, const GOFFSET *);
typedef HRESULT (WINAPI *cmap_fn)(HDC, SCRIPT_CACHE *, const WCHAR *, int, DWORD, WORD *);
typedef DWORD (WINAPI *font_data_fn)(HDC, DWORD, DWORD, void *, DWORD);
typedef BOOL (WINAPI *metrics_fn)(HDC, TEXTMETRICW *);
typedef int (WINAPI *face_name_fn)(HDC, int, LPWSTR);
typedef BOOL (WINAPI *extent_fn)(HDC, LPCWSTR, int, SIZE *);

static struct {
    int tried, ready;
    create_dc_fn create_dc;
    create_dib_fn create_dib;
    select_fn select;
    create_font_fn create_font;
    text_colour_fn text_colour;
    bk_mode_fn bk_mode;
    flush_fn flush;
    align_fn align;
    itemize_fn itemize;
    shape_fn shape;
    place_fn place;
    props_fn props;
    layout_fn layout;
    text_out_fn text_out;
    cmap_fn cmap;
    font_data_fn font_data;
    metrics_fn metrics;
    face_name_fn face_name;
    extent_fn extent;
    HDC dc;
    unsigned char *bits;
} gdi;

#define DIB_W GLYPH_MAX_W
#define DIB_H GLYPH_MAX_H

/* The shared fallback chain (UNICODE_SPEC.md row 3), in its order; then the faces this DLL had
   before (kept), then the patcher's own (BUNDLED_FONT_FILES, in data/unicode/fonts.json's order;
   Noto Sans Cuneiform is one of them, at its place in the spec's list). A face that is not
   installed (nor loaded from the Fonts folder) is skipped. */
static const wchar_t *const CHAIN[] = {
    L"Segoe UI", L"Segoe UI Historic", L"Segoe UI Symbol", L"Segoe UI Emoji",
    L"Yu Gothic", L"Meiryo", L"Microsoft YaHei", L"Microsoft JhengHei", L"Malgun Gothic", L"SimSun-ExtB",
    L"Nirmala UI", L"Ebrima", L"Gadugi", L"Leelawadee UI", L"Myanmar Text", L"Javanese Text", L"Mongolian Baiti",
    L"Microsoft Himalaya", L"Microsoft Yi Baiti", L"Microsoft New Tai Lue", L"Microsoft Tai Le",
    L"Microsoft PhagsPa", L"Sylfaen", L"Cambria Math",
    L"Noto Sans", L"Noto Sans Symbols", L"Noto Sans Symbols 2", L"Noto Sans CJK JP", L"Noto Sans CJK SC",
    L"Noto Sans Math", L"Noto Sans Cuneiform", L"Noto Color Emoji",
    L"SimSun", L"SimSun-ExtG", L"MingLiU-ExtB",
    L"Unifont", L"Unifont Upper", L"Noto Serif Tangut", L"Last Resort",
};
#define CHAIN_FONTS ((int)(sizeof CHAIN / sizeof CHAIN[0]))
#define CHAIN_EMOJI 3                      /* Segoe UI Emoji */
#define CHAIN_LAST_RESORT (CHAIN_FONTS - 1)

/* The files beside the DLL, in "Fonts" (assets/<game>_tycoon_unicode/Fonts) */
static const wchar_t *const BUNDLED_FONT_FILES[] = {
    L"unifont-18.0.01.otf", L"unifont_upper-18.0.01.otf", L"NotoSerifTangut-Regular.ttf",
    L"NotoSansCuneiform-Regular.ttf", L"LastResort-Regular.ttf",
};

typedef int (WINAPI *add_font_fn)(LPCWSTR, DWORD, PVOID);

/* The patcher's fonts, and the font file chosen in its "Unicode Font..." window (File=, a file name
   beside the DLL), for this process only (FR_PRIVATE): nothing is installed in Windows. A missing
   file only means that font is left out. */
static void load_bundled_fonts(HMODULE gdi32) {
    add_font_fn add = (add_font_fn)(UINT_PTR)GetProcAddress(gdi32, "AddFontResourceExW");
    HMODULE self = NULL;
    wchar_t path[MAX_PATH + 64];
    DWORD len;
    int cut, i;
    if (add == NULL || !GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS
                                           | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                           (LPCWSTR)(UINT_PTR)load_bundled_fonts, &self)) {
        return;
    }
    len = GetModuleFileNameW(self, path, MAX_PATH);
    if (len == 0 || len >= MAX_PATH) return;
    for (cut = (int)len; cut > 0 && path[cut - 1] != L'\\' && path[cut - 1] != L'/'; --cut) {}
    for (i = 0; i < (int)(sizeof BUNDLED_FONT_FILES / sizeof BUNDLED_FONT_FILES[0]); ++i) {
        path[cut] = L'\0';
        if (wcslen(path) + 6 + wcslen(BUNDLED_FONT_FILES[i]) >= MAX_PATH + 64) continue;
        wcscat_s(path, MAX_PATH + 64, L"Fonts\\");
        wcscat_s(path, MAX_PATH + 64, BUNDLED_FONT_FILES[i]);
        add(path, FR_PRIVATE, NULL);
    }
    if (chosen_file[0]) {
        path[cut] = L'\0';
        if (wcslen(path) + wcslen(chosen_file) < MAX_PATH + 64) {
            wcscat_s(path, MAX_PATH + 64, chosen_file);
            add(path, FR_PRIVATE, NULL);
        }
    }
}

typedef struct face {
    int chain, em, weight;
    HFONT font;
    SCRIPT_CACHE cache;
    WORD missing;
    int colour;                      /* a colour font: COLR, CBDT, sbix or SVG */
    int absent;                      /* not installed: Windows gave another face */
} face;

#define FACES 256
static face faces[FACES];
static int face_count;
static int drawn_by = -2;                    /* the chain font of the last piece drawn (-1: the chosen face) */

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
    gdi.flush = (flush_fn)(UINT_PTR)GetProcAddress(g, "GdiFlush");
    gdi.align = (align_fn)(UINT_PTR)GetProcAddress(g, "SetTextAlign");
    gdi.itemize = (itemize_fn)(UINT_PTR)GetProcAddress(u, "ScriptItemize");
    gdi.shape = (shape_fn)(UINT_PTR)GetProcAddress(u, "ScriptShape");
    gdi.place = (place_fn)(UINT_PTR)GetProcAddress(u, "ScriptPlace");
    gdi.props = (props_fn)(UINT_PTR)GetProcAddress(u, "ScriptGetFontProperties");
    gdi.layout = (layout_fn)(UINT_PTR)GetProcAddress(u, "ScriptLayout");
    gdi.text_out = (text_out_fn)(UINT_PTR)GetProcAddress(u, "ScriptTextOut");
    gdi.cmap = (cmap_fn)(UINT_PTR)GetProcAddress(u, "ScriptGetCMap");
    gdi.font_data = (font_data_fn)(UINT_PTR)GetProcAddress(g, "GetFontData");
    gdi.metrics = (metrics_fn)(UINT_PTR)GetProcAddress(g, "GetTextMetricsW");
    gdi.face_name = (face_name_fn)(UINT_PTR)GetProcAddress(g, "GetTextFaceW");
    gdi.extent = (extent_fn)(UINT_PTR)GetProcAddress(g, "GetTextExtentPoint32W");
    if (!gdi.create_dc || !gdi.create_dib || !gdi.select || !gdi.create_font || !gdi.text_colour || !gdi.bk_mode
        || !gdi.flush || !gdi.align || !gdi.itemize || !gdi.shape || !gdi.place || !gdi.props || !gdi.layout
        || !gdi.text_out || !gdi.cmap) {
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
    load_bundled_fonts(g);
    gdi.ready = 1;
    return 1;
}

static const wchar_t *chain_name(int i) {
    return i < 0 ? chosen_font : CHAIN[i];
}

static int same_name(const wchar_t *a, const wchar_t *b) {
    for (; *a && *b; ++a, ++b) {
        wchar_t x = *a >= L'A' && *a <= L'Z' ? (wchar_t)(*a + 32) : *a;
        wchar_t y = *b >= L'A' && *b <= L'Z' ? (wchar_t)(*b + 32) : *b;
        if (x != y) return 0;
    }
    return *a == *b;
}

/* Chain font `chain` at em `em` (a pixel height: negative, as CreateFontW takes an em; positive,
   a cell height) and `weight`, selected in gdi.dc; NULL when Windows has it not. */
static face *get_face(int chain, int em, int weight) {
    face *f;
    int i;
    SCRIPT_FONTPROPERTIES props;
    for (i = 0; i < face_count; ++i) {
        if (faces[i].chain == chain && faces[i].em == em && faces[i].weight == weight) {
            if (faces[i].absent) return NULL;
            gdi.select(gdi.dc, faces[i].font);
            return &faces[i];
        }
    }
    if (face_count >= FACES) return NULL;
    f = &faces[face_count];
    memset(f, 0, sizeof *f);
    f->chain = chain;
    f->em = em;
    f->weight = weight;
    f->font = gdi.create_font(em, 0, 0, 0, weight, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS,
                              CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, chain_name(chain));
    if (f->font == NULL) return NULL;
    ++face_count;
    gdi.select(gdi.dc, f->font);
    if (gdi.face_name != NULL) {
        wchar_t got[LF_FACESIZE + 1];
        got[0] = L'\0';
        if (gdi.face_name(gdi.dc, LF_FACESIZE, got) > 0 && !same_name(got, chain_name(chain))) {
            f->absent = 1;                     /* a face Windows substitutes: skipped */
            return NULL;
        }
    }
    memset(&props, 0, sizeof props);
    props.cBytes = sizeof props;
    if (gdi.props(gdi.dc, &f->cache, &props) != S_OK) {
        f->absent = 1;
        return NULL;
    }
    f->missing = props.wgDefault;
    if (gdi.font_data != NULL) {
        static const DWORD COLOUR_TABLES[4] = {0x524C4F43u, 0x54444243u, 0x78696273u, 0x20475653u};
        for (i = 0; i < 4 && !f->colour; ++i) {
            f->colour = gdi.font_data(gdi.dc, COLOUR_TABLES[i], 0, NULL, 0) != GDI_ERROR;
        }
    }
    return f;
}

/* Use Unicode Font: the em of the chosen face at which the fit sentence is as wide as the game font
   draws it, within 60%..130% of the style's em (computed once per style). */
static int fit_em(void) {
    static int fitted[16];
    int em0 = pen.em, game = pen.game_fit, width, em, lo, hi, i;
    SIZE size;
    WCHAR sentence[sizeof FIT_SENTENCE];
    face *f;
    if (!system_font || pen.id <= 0 || pen.id > 16 || game <= 0) return em0;
    if (fitted[pen.id - 1]) return fitted[pen.id - 1];
    fitted[pen.id - 1] = em0;
    if (gdi.extent == NULL) return em0;
    f = get_face(-1, -em0, pen.weight);        /* the chosen face; not installed: the style's own em */
    if (f == NULL) return em0;
    for (i = 0; FIT_SENTENCE[i]; ++i) sentence[i] = (WCHAR)FIT_SENTENCE[i];
    width = gdi.extent(gdi.dc, sentence, i, &size) ? size.cx : 0;
    if (width <= 0) return em0;
    em = (em0 * game * 2 + width) / (2 * width);
    lo = em0 * 6 / 10;
    hi = em0 * 13 / 10;
    if (em < lo) em = lo;
    if (em > hi) em = hi;
    fitted[pen.id - 1] = em;
    return em;
}

/* ---- colour letters: Direct2D and DirectWrite (as src/text_raster.py, the Text Maker's) */

typedef struct dx_guid {
    unsigned long a;
    unsigned short b, c;
    unsigned char d[8];
} dx_guid;

static const dx_guid IID_D2D_FACTORY = {0x06152247u, 0x6f50, 0x465a, {0x92, 0x45, 0x11, 0x8b, 0xfd, 0x3b, 0x60, 0x07}};
static const dx_guid IID_DWRITE_FACTORY = {0xb859ee5au, 0xd838, 0x4b5b, {0xa2, 0xe8, 0x1a, 0xdc, 0x7d, 0x93, 0xdb, 0x48}};

typedef struct dx_colour { float r, g, b, a; } dx_colour;
typedef struct dx_point { float x, y; } dx_point;
typedef struct dx_target_props {
    unsigned int type, format, alpha_mode;
    float dpi_x, dpi_y;
    unsigned int usage, min_level;
} dx_target_props;
typedef struct dx_line {
    unsigned int length, trailing, newline;
    float height, baseline;
    BOOL trimmed;
} dx_line;

/* vtable slots (d2d1.h, dwrite.h) */
#define DX_RELEASE 2
#define DX_F_CREATE_DC_TARGET 16          /* ID2D1Factory::CreateDCRenderTarget */
#define DX_RT_CREATE_BRUSH 8              /* ID2D1RenderTarget::CreateSolidColorBrush */
#define DX_RT_DRAW_LAYOUT 28              /* ::DrawTextLayout */
#define DX_RT_TEXT_AA 34                  /* ::SetTextAntialiasMode */
#define DX_RT_CLEAR 47
#define DX_RT_BEGIN 48
#define DX_RT_END 49
#define DX_DCRT_BIND 57                   /* ID2D1DCRenderTarget::BindDC */
#define DX_DW_CREATE_FORMAT 15            /* IDWriteFactory::CreateTextFormat */
#define DX_DW_CREATE_LAYOUT 18            /* ::CreateTextLayout */
#define DX_TL_LINE_METRICS 59             /* IDWriteTextLayout::GetLineMetrics */
#define DX_FORMAT_B8G8R8A8 87
#define DX_ALPHA_PREMULTIPLIED 1
#define DX_TEXT_AA_GRAYSCALE 2
#define DX_ENABLE_COLOR_FONT 4

#define DX_SLOT(obj, slot) ((*(void ***)(obj))[slot])

typedef HRESULT (WINAPI *d2d_create_fn)(unsigned int, const dx_guid *, const void *, void **);
typedef HRESULT (WINAPI *dw_create_fn)(unsigned int, const dx_guid *, void **);
typedef ULONG (WINAPI *dx_release_fn)(void *);
typedef HRESULT (WINAPI *dx_create_target_fn)(void *, const dx_target_props *, void **);
typedef HRESULT (WINAPI *dx_create_brush_fn)(void *, const dx_colour *, const void *, void **);
typedef void (WINAPI *dx_text_aa_fn)(void *, unsigned int);
typedef HRESULT (WINAPI *dx_bind_fn)(void *, HDC, const RECT *);
typedef void (WINAPI *dx_begin_fn)(void *);
typedef void (WINAPI *dx_clear_fn)(void *, const dx_colour *);
typedef void (WINAPI *dx_draw_layout_fn)(void *, dx_point, void *, void *, unsigned int);
typedef HRESULT (WINAPI *dx_end_fn)(void *, unsigned __int64 *, unsigned __int64 *);
typedef HRESULT (WINAPI *dx_create_format_fn)(void *, const wchar_t *, void *, unsigned int, unsigned int,
                                              unsigned int, float, const wchar_t *, void **);
typedef HRESULT (WINAPI *dx_create_layout_fn)(void *, const wchar_t *, unsigned int, void *, float, float, void **);
typedef HRESULT (WINAPI *dx_line_metrics_fn)(void *, dx_line *, unsigned int, unsigned int *);

static struct {
    int tried, ready;
    void *dwrite, *target, *brush;
} dx;

static void dx_release(void *obj) {
    if (obj != NULL) ((dx_release_fn)DX_SLOT(obj, DX_RELEASE))(obj);
}

/* Direct2D and DirectWrite, loaded once: 0 when this Windows has not got them (the letter is then
   drawn in one colour by GDI). */
static int dx_start(void) {
    HMODULE d2d1, dwrite;
    d2d_create_fn d2d_create;
    dw_create_fn dw_create;
    void *factory = NULL;
    dx_target_props props;
    dx_colour white = {1.0f, 1.0f, 1.0f, 1.0f};
    if (dx.tried) return dx.ready;
    dx.tried = 1;
    d2d1 = LoadLibraryW(L"d2d1.dll");
    dwrite = LoadLibraryW(L"dwrite.dll");
    if (d2d1 == NULL || dwrite == NULL) return 0;
    d2d_create = (d2d_create_fn)(UINT_PTR)GetProcAddress(d2d1, "D2D1CreateFactory");
    dw_create = (dw_create_fn)(UINT_PTR)GetProcAddress(dwrite, "DWriteCreateFactory");
    if (d2d_create == NULL || dw_create == NULL) return 0;
    if (d2d_create(0, &IID_D2D_FACTORY, NULL, &factory) < 0 || factory == NULL) return 0;
    if (dw_create(0, &IID_DWRITE_FACTORY, &dx.dwrite) < 0 || dx.dwrite == NULL) {
        dx_release(factory);
        return 0;
    }
    memset(&props, 0, sizeof props);
    props.format = DX_FORMAT_B8G8R8A8;
    props.alpha_mode = DX_ALPHA_PREMULTIPLIED;
    props.dpi_x = props.dpi_y = 96.0f;
    if (((dx_create_target_fn)DX_SLOT(factory, DX_F_CREATE_DC_TARGET))(factory, &props, &dx.target) < 0
        || dx.target == NULL) {
        dx_release(factory);
        return 0;
    }
    dx_release(factory);                 /* the target keeps it */
    ((dx_text_aa_fn)DX_SLOT(dx.target, DX_RT_TEXT_AA))(dx.target, DX_TEXT_AA_GRAYSCALE);
    if (((dx_create_brush_fn)DX_SLOT(dx.target, DX_RT_CREATE_BRUSH))(dx.target, &white, NULL, &dx.brush) < 0
        || dx.brush == NULL) {
        return 0;
    }
    dx.ready = 1;
    return 1;
}

/* The letter (`units`, `n` UTF-16 units) of chain font `chain` drawn by Direct2D with colour fonts
   on, at em `em` with its baseline on the pen's (em 0: the em size of the GDI font selected in
   gdi.dc, `height` its cell, its baseline on that font's) and its pen at `pad` in the DIB, as the Text Maker draws it. 1 with its premultiplied
   B, G, R, A pixels (`*w` columns from `*xoff` past the pen, `height` rows) when the drawing has
   colour; 0 when it has none (one-colour glyph: GDI draws it) or Direct2D is not there. */
static int raster_colour(const WCHAR *units, int n, int chain, int em, int height, int pad, unsigned char *bgra,
                         int *w, int *xoff) {
    TEXTMETRICW tm;
    void *format = NULL, *layout = NULL;
    dx_line lines[2];
    unsigned int count = 0;
    dx_colour clear = {0.0f, 0.0f, 0.0f, 0.0f};
    dx_point origin;
    RECT rect;
    int x, y, left = -1, right = -1, coloured = 0, ok = 0;
    if (gdi.metrics == NULL || !gdi.metrics(gdi.dc, &tm) || !dx_start()) return 0;
    if (((dx_create_format_fn)DX_SLOT(dx.dwrite, DX_DW_CREATE_FORMAT))(
            dx.dwrite, chain_name(chain), NULL, 400, 0, 5, em > 0 ? (float)em : (float)(tm.tmHeight - tm.tmInternalLeading), L"en-us",
            &format) < 0 || format == NULL) {
        return 0;
    }
    if (((dx_create_layout_fn)DX_SLOT(dx.dwrite, DX_DW_CREATE_LAYOUT))(
            dx.dwrite, units, (unsigned int)n, format, 100000.0f, 100000.0f, &layout) >= 0 && layout != NULL
        && ((dx_line_metrics_fn)DX_SLOT(layout, DX_TL_LINE_METRICS))(layout, lines, 2, &count) >= 0 && count >= 1) {
        rect.left = 0;
        rect.top = 0;
        rect.right = DIB_W;
        rect.bottom = height;
        origin.x = (float)pad;
        origin.y = (float)(em > 0 ? pen.baseline : tm.tmAscent) - lines[0].baseline;
        if (((dx_bind_fn)DX_SLOT(dx.target, DX_DCRT_BIND))(dx.target, gdi.dc, &rect) >= 0) {
            ((dx_begin_fn)DX_SLOT(dx.target, DX_RT_BEGIN))(dx.target);
            ((dx_clear_fn)DX_SLOT(dx.target, DX_RT_CLEAR))(dx.target, &clear);
            ((dx_draw_layout_fn)DX_SLOT(dx.target, DX_RT_DRAW_LAYOUT))(dx.target, origin, layout, dx.brush,
                                                                      DX_ENABLE_COLOR_FONT);
            ok = ((dx_end_fn)DX_SLOT(dx.target, DX_RT_END))(dx.target, NULL, NULL) >= 0;
            gdi.flush();
        }
    }
    dx_release(layout);
    dx_release(format);
    if (!ok) return 0;
    for (x = 0; x < DIB_W; ++x) {
        for (y = 0; y < height; ++y) {
            const unsigned char *px = gdi.bits + (y * DIB_W + x) * 4;
            if (px[3] == 0) continue;
            if (left < 0) left = x;
            right = x;
            /* white ink has B = G = R = A; any other colour is the font's */
            if (px[3] >= 16 && (px[0] + 16 < px[3] || px[1] + 16 < px[3] || px[2] + 16 < px[3])) coloured = 1;
        }
    }
    if (!coloured || left < 0) return 0;
    *w = right - left + 1;
    *xoff = left - pad;
    for (y = 0; y < height; ++y) {
        memcpy(bgra + (y * *w) * 4, gdi.bits + (y * DIB_W + left) * 4, (size_t)*w * 4);
    }
    return 1;
}

#define PIECE_UNITS (UNIT_MAX * 2)

/* Whether the face selected in gdi.dc maps every code point of `units` (n UTF-16 units) in its
   character map, joiners, variation selectors and tags aside (they draw nothing). */
static int face_maps_all(face *f, const WCHAR *units, int n) {
    int k = 0;
    while (k < n) {
        int len = (units[k] >= 0xD800 && units[k] <= 0xDBFF && k + 1 < n) ? 2 : 1;
        unsigned int cp = len == 2 ? 0x10000 + ((units[k] - 0xD800) << 10) + (units[k + 1] - 0xDC00) : units[k];
        WORD ids[2];
        if (!gb_invisible(cp) && cp != ' ') {
            if (gdi.cmap(gdi.dc, &f->cache, units + k, len, 0, ids) != S_OK) return 0;
        }
        k += len;
    }
    return 1;
}

/* `units` (n UTF-16 units: a code point, a grapheme or a run) from the first font of the chain that
   has all of it: 1 (coverage) or 2 (a colour drawing) as raster_glyph, 0 when none.
   `emoji`: Segoe UI Emoji is asked first; `last_resort`: Last Resort may answer.
   Shaped by Uniscribe: itemized (a run may hold several scripts, directions and digits), its items
   laid out in visual order (ScriptLayout), each shaped, placed and drawn (ScriptTextOut, with its
   glyph offsets) on the pen's baseline at the pen's em and weight. */
static int raster_units(const WCHAR *units, int n, int emoji, int last_resort, int height, unsigned char *coverage,
                        int *w, int *xoff, int *adv) {
    static SCRIPT_ITEM items[PIECE_UNITS + 1];
    static WORD ids[PIECE_UNITS * 2], clusters[PIECE_UNITS];
    static SCRIPT_VISATTR attrs[PIECE_UNITS * 2];
    static int advances[PIECE_UNITS * 2];
    static GOFFSET offsets[PIECE_UNITS * 2];
    static BYTE levels[PIECE_UNITS];
    static int order[PIECE_UNITS], item_ids[PIECE_UNITS + 1];
    int step, first = system_font ? -1 : 0, em = pen.id ? -fit_em() : height, weight = pen.id ? pen.weight : FW_SEMIBOLD;
    if (!gdi_start() || n <= 0 || n > PIECE_UNITS) return 0;
    for (step = first - (emoji ? 1 : 0); step < CHAIN_FONTS; ++step) {
        int items_n = 0, i, x, y, left = -1, right = -1, pad = height, total = 0, ok = 1, used = 0;
        int c = step;
        face *f;
        if (emoji) {
            if (step == first - 1) c = CHAIN_EMOJI;
            else if (step == CHAIN_EMOJI) continue;
        }
        if (c == CHAIN_LAST_RESORT && !last_resort) continue;
        f = get_face(c, em, weight);
        if (f == NULL || !face_maps_all(f, units, n)) continue;
        if (gdi.itemize(units, n, PIECE_UNITS, NULL, NULL, items, &items_n) != S_OK || items_n < 1) continue;
        /* shape every item (logical order), each glyph found */
        for (i = 0; i < items_n && ok; ++i) {
            int start = items[i].iCharPos, len = items[i + 1].iCharPos - start, count = 0, k;
            HRESULT hr;
            if (used + len * 2 + 16 > PIECE_UNITS * 2) { ok = 0; break; }
            hr = gdi.shape(gdi.dc, &f->cache, units + start, len, PIECE_UNITS * 2 - used, &items[i].a, ids + used,
                           clusters, attrs + used, &count);
            if (hr == USP_E_SCRIPT_NOT_IN_FONT) {
                /* the font has no shaping for the script: its own letters, unshaped */
                items[i].a.eScript = SCRIPT_UNDEFINED;
                hr = gdi.shape(gdi.dc, &f->cache, units + start, len, PIECE_UNITS * 2 - used, &items[i].a,
                               ids + used, clusters, attrs + used, &count);
            }
            if (hr != S_OK || count < 1) { ok = 0; break; }
            for (k = 0; k < count; ++k) {
                if (ids[used + k] == f->missing && !(len == 1 && units[start] == ' ')) ok = 0;
            }
            if (!ok) break;
            {
                ABC abc;
                if (gdi.place(gdi.dc, &f->cache, ids + used, count, attrs + used, &items[i].a, advances + used,
                              offsets + used, &abc) != S_OK) {
                    ok = 0;
                    break;
                }
                for (k = 0; k < count; ++k) total += advances[used + k];
            }
            item_ids[i] = used;
            used += count;
            levels[i] = (BYTE)items[i].a.s.uBidiLevel;
        }
        if (!ok) continue;
        item_ids[items_n] = used;
        if (gdi.layout(items_n, levels, order, NULL) != S_OK) {
            for (i = 0; i < items_n; ++i) order[i] = i;
        }
        *adv = total < 0 ? 0 : total;
        if (pad * 2 + *adv > DIB_W) pad = (DIB_W - *adv) / 2;
        if (pad < 0) return 0;
        drawn_by = c;
        if (f->colour && raster_colour(units, n, c, pen.id ? -em : 0, height, pad, coverage, w, xoff)) return 2;
        for (y = 0; y < height; ++y) memset(gdi.bits + y * DIB_W * 4, 0, DIB_W * 4);
        gdi.align(gdi.dc, (pen.id ? TA_BASELINE : TA_TOP) | TA_LEFT | TA_NOUPDATECP);
        {
            int x0 = pad;
            for (i = 0; i < items_n; ++i) {
                int it = order[i], from = item_ids[it], count = item_ids[it + 1] - item_ids[it], k, wide = 0;
                for (k = 0; k < count; ++k) wide += advances[from + k];
                gdi.text_out(gdi.dc, &f->cache, x0, pen.id ? pen.baseline : 0, 0, NULL, &items[it].a, NULL, 0,
                             ids + from, count, advances + from, NULL, offsets + from);
                x0 += wide;
            }
        }
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
        if (pen.id && !system_font) {
            /* the game font's own side bearings around the ink, as its patcher-made letters have */
            *xoff = pen.left;
            *adv = *w + pen.left + pen.right;
        }
        return 1;
    }
    return 0;
}

/* `cps` as UTF-16 into `units` (at most PIECE_UNITS), skipping the invisible ones with `visible`:
   the number of units, 0 when they do not fit or none is left. */
static int to_units(const unsigned int *cps, int n, int visible, WCHAR *units) {
    int k, u = 0;
    for (k = 0; k < n; ++k) {
        unsigned int cp = cps[k];
        if (visible && gb_invisible(cp)) continue;
        if (u + 2 > PIECE_UNITS) return 0;
        if (cp >= 0x10000) {
            units[u++] = (WCHAR)(0xD800 + ((cp - 0x10000) >> 10));
            units[u++] = (WCHAR)(0xDC00 + ((cp - 0x10000) & 0x3FF));
        } else {
            units[u++] = (WCHAR)cp;
        }
    }
    return u;
}

__declspec(noinline) static int raster_glyph(unsigned int cp, int height, unsigned char *coverage,
                                             int *w, int *xoff, int *adv) {
    WCHAR units[2];
    /* variation selectors, joiners and tags alone: nothing drawn, no width */
    if (gb_invisible(cp)) {
        *w = *xoff = *adv = 0;
        return 1;
    }
    return raster_units(units, to_units(&cp, 1, 0, units), gb_emoji(&cp, 1), 1, height, coverage, w, xoff, adv);
}

__declspec(noinline) static int raster_cluster(const unsigned int *cps, int n, int height, unsigned char *coverage,
                                               int *w, int *xoff, int *adv) {
    static WCHAR units[PIECE_UNITS], seen[PIECE_UNITS];
    int u = to_units(cps, n, 0, units), v, kind;
    /* the whole piece, by a font that has every glyph of it (not Last Resort: its boxes would
       stand for the marks too) */
    if (u > 0 && (kind = raster_units(units, u, gb_emoji(cps, n), 0, height, coverage, w, xoff, adv)) != 0) {
        return kind;
    }
    /* its visible code points alone (an emoji's U+FE0F, a joiner, a tag the font has not) */
    v = to_units(cps, n, 1, seen);
    if (v > 0 && v != u) return raster_units(seen, v, gb_emoji(cps, n), 0, height, coverage, w, xoff, adv);
    return 0;                           /* drawn a cluster or a code point at a time */
}

#endif
