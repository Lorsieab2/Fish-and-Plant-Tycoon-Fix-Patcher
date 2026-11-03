/* unicode_grapheme.h -- "Unicode Text.dll", both games: user-perceived characters (grapheme
   clusters), Unicode 18.0.

   The rules of UAX #29 for extended grapheme clusters (GB3-GB13 with GB9c as changed for 18.0:
   InCB=Linker InCB=Extend* x InCB=Consonant), over the tables scripts/build_unicode18_tables.py
   makes from data/unicode (unicode_grapheme_table.h). The same state machine as the patcher's own
   tools (src/unicode_data.py, GraphemeState), and both pass all of GraphemeBreakTest.txt 18.0
   (tests/test_unicode18.py; this file natively, through native/common/unicode_grapheme_harness.c).

   The DLL draws a grapheme as one piece (an emoji ZWJ sequence, a flag, a keycap, a letter with
   its marks, an Indic conjunct), and Backspace, paste and a name fitted to its width never cut
   one in half. Free of Windows and of the games, so it builds into the harness as it is. */
#ifndef FTFP_UNICODE_GRAPHEME_H
#define FTFP_UNICODE_GRAPHEME_H

#include "unicode_grapheme_table.h"

enum {
    GB_OTHER, GB_CR, GB_LF, GB_CONTROL, GB_EXTEND, GB_ZWJ, GB_RI, GB_PREPEND, GB_SPACING, GB_L, GB_V, GB_T,
    GB_LV, GB_LVT
};
#define INCB_CONSONANT 1
#define INCB_EXTEND 2
#define INCB_LINKER 3

/* GCB | InCB << 4 | Extended_Pictographic << 6 of `cp` */
static unsigned int gb_props(unsigned int cp) {
    int lo = 0, hi = GB_RANGE_COUNT - 1;
    while (lo < hi) {
        int mid = (lo + hi + 1) / 2;
        if ((GB_RANGES[mid] >> 8) <= cp) lo = mid;
        else hi = mid - 1;
    }
    return GB_RANGES[lo] & 0xFF;
}

typedef struct gb_state {
    int prev;            /* the previous code point's GCB, -1 before the first */
    int emoji;           /* 1: ExtPict Extend*; 2: ExtPict Extend* ZWJ */
    int incb;            /* 1: InCB=Linker InCB=Extend* */
    int ri;              /* regional indicators just before */
} gb_state;

static void gb_start(gb_state *s) {
    s->prev = -1;
    s->emoji = s->incb = s->ri = 0;
}

static int gb_control(int g) {
    return g == GB_CR || g == GB_LF || g == GB_CONTROL;
}

/* Take the next code point: 1 when a grapheme boundary comes before it. */
static int gb_push(gb_state *s, unsigned int cp) {
    unsigned int p = gb_props(cp);
    int g = (int)(p & 15), i = (int)((p >> 4) & 3), pict = (int)((p >> 6) & 1), brk = 1, prev = s->prev;
    if (prev < 0) brk = 1;
    else if (prev == GB_CR && g == GB_LF) brk = 0;
    else if (gb_control(prev) || gb_control(g)) brk = 1;
    else if (prev == GB_L && (g == GB_L || g == GB_V || g == GB_LV || g == GB_LVT)) brk = 0;
    else if ((prev == GB_LV || prev == GB_V) && (g == GB_V || g == GB_T)) brk = 0;
    else if ((prev == GB_LVT || prev == GB_T) && g == GB_T) brk = 0;
    else if (g == GB_EXTEND || g == GB_ZWJ || g == GB_SPACING || prev == GB_PREPEND) brk = 0;
    else if (i == INCB_CONSONANT && s->incb) brk = 0;
    else if (prev == GB_ZWJ && s->emoji == 2 && pict) brk = 0;
    else if (prev == GB_RI && g == GB_RI && (s->ri & 1)) brk = 0;
    if (pict) s->emoji = 1;
    else if (s->emoji == 1 && g == GB_EXTEND) s->emoji = 1;
    else if (s->emoji == 1 && g == GB_ZWJ) s->emoji = 2;
    else s->emoji = 0;
    s->incb = (i == INCB_LINKER || (s->incb && i == INCB_EXTEND)) ? 1 : 0;
    s->ri = g == GB_RI ? s->ri + 1 : 0;
    s->prev = g;
    return brk;
}

/* ---- emoji */

static unsigned int gb_fnv(const unsigned int *cps, int n) {
    unsigned int h = 0x811C9DC5u;
    int k, b;
    for (k = 0; k < n; ++k) {
        for (b = 0; b < 4; ++b) h = (h ^ ((cps[k] >> (8 * b)) & 0xFF)) * 0x01000193u;
    }
    return h;
}

/* An RGI emoji sequence of two or more code points (by its hash), or one Emoji_Presentation
   code point: drawn with the colour emoji font first. */
static int gb_emoji(const unsigned int *cps, int n) {
    int lo = 0, hi;
    if (n == 1) {
        hi = EMOJI_PRESENTATION_COUNT - 1;
        while (lo <= hi) {
            int mid = (lo + hi) / 2;
            if (cps[0] < EMOJI_PRESENTATION[mid][0]) hi = mid - 1;
            else if (cps[0] > EMOJI_PRESENTATION[mid][1]) lo = mid + 1;
            else return 1;
        }
        return 0;
    }
    {
        unsigned int h = gb_fnv(cps, n);
        hi = EMOJI_SEQUENCE_COUNT - 1;
        while (lo <= hi) {
            int mid = (lo + hi) / 2;
            if (h < EMOJI_SEQUENCES[mid]) hi = mid - 1;
            else if (h > EMOJI_SEQUENCES[mid]) lo = mid + 1;
            else return 1;
        }
    }
    return 0;
}

/* Nothing drawn and no width of its own: variation selectors, ZWJ, ZWNJ, tags (an emoji's
   U+FE0F, a flag's tag letters). */
static int gb_invisible(unsigned int cp) {
    return (cp >= 0xFE00 && cp <= 0xFE0F) || cp == 0x200C || cp == 0x200D || (cp >= 0xE0020 && cp <= 0xE007F)
           || (cp >= 0xE0100 && cp <= 0xE01EF);
}

/* A letter a text box takes typed or pasted: anything but C0 and C1 controls, DEL, lone surrogates
   and what is past U+10FFFF (every assigned letter of Unicode 18.0, private use and the
   unassigned too, so a newer letter goes in as well). */
static int letter_typable(unsigned int cp) {
    return cp >= 0x20 && !(cp >= 0x7F && cp < 0xA0) && !(cp >= 0xD800 && cp <= 0xDFFF) && cp <= 0x10FFFF;
}

/* ---- UTF-8 text, a grapheme at a time (needs unicode_utf8.h's utf8_next) */

#define GRAPHEME_MAX 32

/* The grapheme at *p: its code points (at most `cap` kept; the rest of a longer one is still
   read) into cps, *p moved past it. Returns how many were kept, 0 at the end. */
static int next_grapheme(const unsigned char **p, unsigned int *cps, int cap) {
    gb_state s;
    int n = 0;
    if (**p == 0) return 0;
    gb_start(&s);
    for (;;) {
        const unsigned char *at = *p;
        unsigned int cp;
        if (*at == 0) break;
        cp = utf8_next(&at);
        if (gb_push(&s, cp) && n > 0) break;
        *p = at;
        if (n < cap) cps[n++] = cp;
    }
    return n;
}

/* The start of the grapheme before `end` in UTF-8 `text`. */
static const char *grapheme_before(const char *text, const char *end) {
    const unsigned char *p = (const unsigned char *)text, *last = p;
    unsigned int cps[GRAPHEME_MAX];
    while (p < (const unsigned char *)end && *p) {
        last = p;
        next_grapheme(&p, cps, GRAPHEME_MAX);
    }
    return (const char *)last;
}

#endif
