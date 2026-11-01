/* unicode_text.h -- "Unicode Text.dll", both games: the game's text draw and its width,
   hooked once each, and the text boxes' fitting.

   The games draw all their text with one function (Fish Tycoon 0x4087E0, Plant Tycoon
   0x408E20: thiscall(graphics, text, x, y, colour, font)) and measure it with one (0x4023D0 /
   0x402380: thiscall(font, text, float scale)); the left, right and centred draws measure and
   then draw. Their first 7 bytes jump into this DLL (draw_text, text_width); the game's own
   code runs from its 8th byte on (orig_draw, orig_width: the 7 bytes, then a jump back), so
   text the DLL does not change is drawn and measured by the game, byte for byte as before.

   NAMES.  A player's short form (unicode_names.h) is drawn and measured as the full name,
   fitted to the width the game left for a name: the wider of the short form and the game's
   own name placeholder, 26 underscores ("__________________________", the text its name boxes
   are made with). A name wider than that ends in an ellipsis.

   TEXT BOXES.  A box (Fish 0x40B6xx, Plant 0x40C0xx) measured its text and, while it was wider
   than the box, cut its last byte off the box's own text (0x40B7E9 / 0x40C1F9), which would cut
   a long name to what fits and cut a UTF-8 letter in half. That cut is skipped (je becomes jmp)
   and the box's measure and draw (box_width, box_draw) show the text fitted to the box instead:
   while the box has the focus the end of the text (where the next letter goes), with an
   ellipsis in front; otherwise its start, with an ellipsis after. The text itself is whole. */
#ifndef FTFP_UNICODE_TEXT_H
#define FTFP_UNICODE_TEXT_H

static void draw_text(void *graphics, const char *text, int x, int y, unsigned int colour, void *font);
static int text_width(void *font, const char *text, float scale);

/* ---- the game's own draw and measure (the trampolines, in each game's file) */

typedef void (__fastcall *draw_fn)(void *graphics, void *edx, const char *text, int x, int y, unsigned int colour, void *font);
typedef int (__fastcall *width_fn)(void *font, void *edx, const char *text, float scale);

static const char *const ELLIPSIS_UTF8 = "\xE2\x80\xA6";
static const char *const ELLIPSIS_BYTE = "\x85";         /* Windows-1252's ellipsis, in every font */
static const char PLACEHOLDER[] = "__________________________";

static const char *ellipsis(void) {
    return utf8_drawing ? ELLIPSIS_UTF8 : ELLIPSIS_BYTE;
}

/* The width of `text` in `font`, without the names' change (the game's own measure until UTF-8
   drawing). */
static int measure(void *font, const char *text, float scale);

/* `text` cut to fit `budget`: at its end (`tail` 0: its start and an ellipsis) or at its start
   (`tail` 1: an ellipsis and its end), whole letters only, as many as fit (a binary search: a
   longer piece is never narrower). Returns `text` itself when it fits. */
static const char *fit(void *font, const char *text, int budget, int tail, char *out, int cap) {
    static int starts[NAME_BOX_BYTES + 2];
    const char *e = ellipsis();
    const unsigned char *p = (const unsigned char *)text;
    int elen = s_len(e), count = 0, lo, hi;
    if (measure(font, text, 1.0f) <= budget) return text;
    while (*p && count <= NAME_BOX_BYTES) {
        starts[count++] = (int)((const char *)p - text);
        utf_next(&p);
    }
    starts[count] = (int)((const char *)p - text);
    /* the most letters k (0..count) that fit */
    lo = 0;
    hi = count;
    while (lo < hi) {
        int k = (lo + hi + 1) / 2, n;
        if (!tail) {
            n = starts[k];
            if (n + elen + 1 > cap) { hi = k - 1; continue; }
            memcpy(out, text, (size_t)n);
            s_copy(out + n, e, cap - n);
        } else {
            n = starts[count] - starts[count - k];
            if (n + elen + 1 > cap) { hi = k - 1; continue; }
            s_copy(out, e, cap);
            memcpy(out + elen, text + starts[count - k], (size_t)n);
            out[elen + n] = '\0';
        }
        if (measure(font, out, 1.0f) <= budget) lo = k;
        else hi = k - 1;
    }
    if (!tail) {
        memcpy(out, text, (size_t)starts[lo]);
        s_copy(out + starts[lo], e, cap - starts[lo]);
    } else {
        s_copy(out, e, cap);
        memcpy(out + elen, text + starts[count - lo], (size_t)(starts[count] - starts[count - lo]));
        out[elen + starts[count] - starts[count - lo]] = '\0';
    }
    return out;
}

/* A player's short form in `text` (all of it, or within it) as the full name, fitted to the width
   the game left for it: the wider of the text as it is and the text with the game's own name
   placeholder (26 underscores) for the name. */
static const char *name_shown(void *font, const char *text, char *out, int cap) {
    static char full[NAME_BOX_BYTES + 1];
    static char whole[NAME_BOX_BYTES * 2 + 64];
    static char placed[NAME_BOX_BYTES + 64];
    const char *found;
    int at = 0, len = 0, budget, place, rest;
    if (font == NULL || text == NULL) return text;
    found = full_for_short(text);
    if (found != NULL) len = s_len(text);
    else found = short_within(text, &at, &len);
    if (found == NULL) return text;
    rest = s_len(text + at + len);
    if (at + rest + (int)sizeof PLACEHOLDER >= (int)sizeof placed) return text;
    to_box_text(found, full, sizeof full);
    memcpy(whole, text, (size_t)at);
    s_copy(whole + at, full, (int)sizeof whole - at);
    s_copy(whole + s_len(whole), text + at + len, (int)sizeof whole - s_len(whole));
    memcpy(placed, text, (size_t)at);
    s_copy(placed + at, PLACEHOLDER, (int)sizeof placed - at);
    s_copy(placed + s_len(placed), text + at + len, (int)sizeof placed - s_len(placed));
    budget = measure(font, text, 1.0f);
    place = measure(font, placed, 1.0f);
    if (place > budget) budget = place;
    return fit(font, whole, budget, 0, out, cap);
}

static unsigned int draws_since_sync;
static void window_check(void);

static void __cdecl draw_hook(void *graphics, unsigned int ret, const char *text, int x, int y,
                              unsigned int colour, void *font) {
    static char shown[NAME_BOX_BYTES + 8];
    void *used = font != NULL ? font : *(void **)((char *)graphics + GAME_DEFAULT_FONT);
    (void)ret;
    if (++draws_since_sync >= 64) {
        draws_since_sync = 0;
        names_sync();
    }
    window_check();
    if (text != NULL) text = name_shown(used, text, shown, sizeof shown);
    draw_text(graphics, text, x, y, colour, font);
}

static int __cdecl width_hook(void *font, unsigned int ret, const char *text, float scale) {
    static char shown[NAME_BOX_BYTES + 8];
    (void)ret;
    if (text != NULL) text = name_shown(font, text, shown, sizeof shown);
    return text_width(font, text, scale);
}

/* ---- text boxes */

static struct {
    const char *box;
    const char *text;
    char shown[NAME_BOX_BYTES + 8];
    int fitted;
} box_fit;

/* The box's measure of its own text (esi = the box): the text fitted to the box. */
static int __cdecl box_width(void *font, const char *box, unsigned int ret, const char *text, float scale) {
    int room, margin, w;
    (void)ret;
    box_fit.box = box;
    box_fit.text = text;
    box_fit.fitted = 0;
    if (text != NULL) {
        const char *named = name_shown(font, text, box_fit.shown, sizeof box_fit.shown);
        if (named != text) {
            if (named != box_fit.shown) s_copy(box_fit.shown, named, sizeof box_fit.shown);
            box_fit.fitted = 1;
            text = box_fit.shown;
        }
    }
    w = text_width(font, text, scale);
    margin = *(const int *)(box + 0x44);
    if (margin < 0) margin = 0;
    room = *(const int *)(box + 0x10) - *(const int *)(box + 8) - margin;
    /* the game cut only a fixed box (+0x24) */
    if (text == NULL || box[0x24] == 0 || room <= 0 || w <= room) return w;
    {
        static char cut[NAME_BOX_BYTES + 8];
        const char *shown = fit(font, text, room, *(const char *)(box + 0x25) != 0, cut, sizeof cut);
        s_copy(box_fit.shown, shown, sizeof box_fit.shown);
    }
    box_fit.fitted = 1;
    return text_width(font, box_fit.shown, scale);
}

/* The box's draw of its own text (the game's left draw, thiscall(graphics wrapper, ...)). */
static void __cdecl box_draw(void *wrapper, const char *box, unsigned int ret, const char *text, int x, int y,
                             unsigned int colour, void *font) {
    (void)ret;
    if (box_fit.fitted && box_fit.box == box && box_fit.text == text) {
        draw_text(*(void **)wrapper, box_fit.shown, x, y, colour, font);
        return;
    }
    draw_hook(*(void **)wrapper, 0, text, x, y, colour, font);
}

#endif
