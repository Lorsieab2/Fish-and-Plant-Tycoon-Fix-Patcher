/* translation_fit.h -- a translated line fitted to its room on the screen (Translations.dll).

   The room of each line where the game draws it is translation_limits.h (from
   data/translation_limits.json: measured by running the games' own code, or the safe rule).  A
   translation is measured with the GAME'S OWN measure (Fish 0x4023D0, Plant 0x402380, thiscall
   (font, text, float scale)): where "Unicode Text.dll" draws wide letters its hook on that measure
   sees them, so the width is exactly what will be drawn.  The games break lines only at "\n".

   A line wider than its room:
     * where the English breaks lines (TL_MULTILINE), it is broken again at the line's own break
       opportunities (the small UAX #14 rule set of src/text_wrap.py): after a space (the space
       becomes the line break), after a hyphen (not before a digit), between CJK characters (kana,
       ideographs, fullwidth forms) with the kinsoku rules (a line never starts with a closing or
       small mark, nor ends with an opening bracket); never inside a grapheme cluster;
     * a piece still wider than the room (one long word, Thai with no spaces), or any too-wide line
       where the English has no line breaks, is cut with an ellipsis ("...") after the last whole
       cluster that fits;
     * Thai, Lao, Burmese and Khmer, which have no spaces, break only between words, and Chinese and
       Japanese prefer to break between words too (word_break.h: Windows' icu.dll, else ICU's
       dictionaries from the "word-lists" folder beside the DLL); a Chinese or Japanese word wider
       than the room is still broken between its characters, with the kinsoku rules;
     * a printf format (TL_FORMAT) is only ever broken at spaces, never cut (a cut could leave half a
       conversion); a line with a number choice is re-made by the game's sprintf hook from the
       translation, so it is never changed;
     * if even that does not fit (nothing fits before the ellipsis, the text would be taller than its
       box, or a break would make it longer than its buffer's limit), the line shows English.
   Nothing here writes past a buffer: the result is built in fit_out (FIT_MAX bytes) and copied
   back only when it is no longer than the line's own byte limit, which the translation already
   kept to (its buffer was allocated for the absolute maximum). */
#ifndef FTFP_TRANSLATION_FIT_H
#define FTFP_TRANSLATION_FIT_H

#define FIT_MAX (TR_ABSOLUTE_MAX * 2 + 8)

typedef int (__fastcall *tf_width_fn)(void *font, void *edx, const char *text, float scale);
typedef int (__fastcall *tf_height_fn)(void *font, void *edx, const char *text);

typedef struct tf_ctx {
    tf_width_fn width;
    tf_height_fn height;
    void *font;
    int utf8;                       /* the text is UTF-8 (else one byte a letter, Windows-1252) */
    int room;                       /* pixels */
    int format;                     /* a printf format: break at spaces only, never cut */
    int cap;                        /* the most bytes the result may have */
    int broke, cut;                 /* what was done */
} tf_ctx;

static char tf_line[FIT_MAX + 8];
/* Word boundaries of the line being broken, by byte offset (word_break.h): 0 no information, 1 inside
   a word, 2 a word starts here. */
static unsigned char tf_wb[FIT_MAX + 8];
static int wb_script(unsigned int cp);
static void wb_mark(const char *s, int n);
static char fit_out[FIT_MAX + 8];

/* The width of s[0..n) as the game measures it. */
static int tf_px(tf_ctx *c, const char *s, int n) {
    if (n > FIT_MAX) n = FIT_MAX;
    if (n < 0) n = 0;
    memcpy(tf_line, s, (size_t)n);
    tf_line[n] = 0;
    return c->width(c->font, NULL, tf_line, 1.0f);
}

/* The width of s[0..n) followed by "..." */
static int tf_px_ellipsis(tf_ctx *c, const char *s, int n) {
    if (n > FIT_MAX - 4) n = FIT_MAX - 4;
    if (n < 0) n = 0;
    memcpy(tf_line, s, (size_t)n);
    memcpy(tf_line + n, "...", 4);
    return c->width(c->font, NULL, tf_line, 1.0f);
}

static unsigned int tf_cp(const tf_ctx *c, const char *s, int n, int *at) {
    if (c->utf8) return tt_next_cp(s, n, at);
    return (unsigned char)s[(*at)++];
}

static int tf_in(unsigned int cp, const unsigned int *ranges, int count) {
    int k;
    for (k = 0; k < count; k += 2) if (cp >= ranges[k] && cp <= ranges[k + 1]) return 1;
    return 0;
}

/* A mark that belongs to the letter before it (a cluster is never cut before one). */
static const unsigned int TF_EXTEND[] = {
    0x0300, 0x036F, 0x0483, 0x0489, 0x0591, 0x05C7, 0x0610, 0x061A, 0x064B, 0x065F, 0x0670, 0x0670,
    0x06D6, 0x06ED, 0x0900, 0x0903, 0x093A, 0x094F, 0x0951, 0x0957, 0x0962, 0x0963, 0x0981, 0x0983,
    0x09BC, 0x09D7, 0x0E31, 0x0E31, 0x0E34, 0x0E3A, 0x0E47, 0x0E4E, 0x0EB1, 0x0EB1, 0x0EB4, 0x0EBC,
    0x0EC8, 0x0ECD, 0x1160, 0x11FF, 0x1AB0, 0x1AFF, 0x1DC0, 0x1DFF, 0x200C, 0x200D, 0x20D0, 0x20FF,
    0x302A, 0x302F, 0x3099, 0x309A, 0xFE00, 0xFE0F, 0xFE20, 0xFE2F, 0x1F1E6, 0x1F1FF, 0x1F3FB, 0x1F3FF,
    0xE0020, 0xE007F, 0xE0100, 0xE01EF,
};

/* Kana, ideographs, fullwidth forms: a line may break between two of them. */
static const unsigned int TF_CJK[] = {
    0x2E80, 0x2FFF, 0x3000, 0x303F, 0x3040, 0x30FF, 0x3100, 0x312F, 0x3190, 0x31FF, 0x3200, 0x4DBF,
    0x4E00, 0x9FFF, 0xA960, 0xA97F, 0xF900, 0xFAFF, 0xFE30, 0xFE4F, 0xFF00, 0xFFEF, 0x1B000, 0x1B16F,
    0x1F200, 0x1F2FF, 0x20000, 0x3FFFD,
};

/* A line never starts with these (closing and small marks) ... */
static const unsigned int TF_NO_START[] = {
    0x3002, 0x3001, 0xFF0C, 0xFF0E, 0xFF09, 0x300D, 0x300F, 0x3011, 0x3015, 0x3009, 0x300B, 0x3017, 0x3019,
    0x301B, 0xFF5D, 0xFF3D, 0xFF01, 0xFF1F, 0xFF1A, 0xFF1B, 0x30FB, 0x30FC, 0x309D, 0x309E, 0x30FD, 0x30FE,
    0x3005, 0x303B, 0x3041, 0x3043, 0x3045, 0x3047, 0x3049, 0x3063, 0x3083, 0x3085, 0x3087, 0x308E, 0x3095,
    0x3096, 0x30A1, 0x30A3, 0x30A5, 0x30A7, 0x30A9, 0x30C3, 0x30E3, 0x30E5, 0x30E7, 0x30EE, 0x30F5, 0x30F6,
    0x203C, 0x2047, 0x2048, 0x2049, 0x2026, 0x2025, 0x301C, 0xFF5E, '!', '?', ',', '.', ';', ':', ')', ']',
    '}', '%', 0x201D, 0x2019, 0x00BB,
};
/* ... nor ends with these (opening brackets). */
static const unsigned int TF_NO_END[] = {
    0xFF08, 0x300C, 0x300E, 0x3010, 0x3014, 0x3008, 0x300A, 0x3016, 0x3018, 0x301A, 0xFF5B, 0xFF3B, '(', '[',
    '{', 0x201C, 0x2018, 0x00AB, 0x00A1, 0x00BF,
};

static int tf_list(unsigned int cp, const unsigned int *list, int count) {
    int k;
    for (k = 0; k < count; ++k) if (list[k] == cp) return 1;
    return 0;
}

#define TF_N(a) ((int)(sizeof(a) / sizeof((a)[0])))
#define TF_EXTENDS(cp) tf_in((cp), TF_EXTEND, TF_N(TF_EXTEND))
#define TF_IS_CJK(cp) tf_in((cp), TF_CJK, TF_N(TF_CJK))
#define TF_SPACE(cp) ((cp) == ' ' || (cp) == 0x3000)

/* Where a line may end, between `prev` (at s[a..b)) and `cp`: 0 no, 1 replace the space prev, 2 insert. */
static int tf_opportunity(const tf_ctx *c, int at, unsigned int before, unsigned int prev, unsigned int cp, int force) {
    if (TF_EXTENDS(cp) || prev == 0x200D || cp == '\n' || prev == '\n') return 0;
    if (c->utf8 && at >= 0 && at < FIT_MAX) {
        if (tf_wb[at] == 1 && !force) return 0;                                          /* inside a dictionary word */
        if (tf_wb[at] == 2 && wb_script(prev) >= 1 && wb_script(prev) <= 4 && wb_script(cp) >= 1 && wb_script(cp) <= 4)
            return 2;                                                           /* between two Thai-like words */
    }
    if (TF_SPACE(prev)) return TF_SPACE(cp) || tf_list(cp, TF_NO_START, TF_N(TF_NO_START)) || before == '%' ? 0 : 1;
    if (TF_SPACE(cp) || c->format) return c->format && TF_IS_CJK(prev) && TF_IS_CJK(cp)
        && !tf_list(cp, TF_NO_START, TF_N(TF_NO_START)) && !tf_list(prev, TF_NO_END, TF_N(TF_NO_END)) ? 2 : 0;
    if (tf_list(cp, TF_NO_START, TF_N(TF_NO_START)) || tf_list(prev, TF_NO_END, TF_N(TF_NO_END))) return 0;
    if ((prev == '-' || prev == 0x2010 || prev == 0x2013) && !(cp >= '0' && cp <= '9')) return 2;
    return TF_IS_CJK(prev) || TF_IS_CJK(cp) ? 2 : 0;
}

/* Appends s[0..n) to fit_out at *o; 0 when it would not fit within cap. */
static int tf_emit(tf_ctx *c, int *o, const char *s, int n) {
    if (*o + n > c->cap || *o + n > FIT_MAX) return 0;
    memcpy(fit_out + *o, s, (size_t)n);
    *o += n;
    return 1;
}

/* s[0..n), one line, too wide: the longest start of whole clusters that fits with "..." after it. */
static int tf_cut(tf_ctx *c, int *o, const char *s, int n) {
    int best = 0, i = 0;
    if (c->format) return 0;
    while (i < n) {
        int j = i;
        unsigned int cp = tf_cp(c, s, n, &j);
        /* the cluster: cp and every mark after it (and the letter after a joiner) */
        while (j < n) {
            int k = j;
            unsigned int next = tf_cp(c, s, n, &k);
            if (!TF_EXTENDS(next) && cp != 0x200D) break;
            cp = next;
            j = k;
        }
        if (tf_px_ellipsis(c, s, j) > c->room) break;
        best = j;
        i = j;
    }
    while (best > 0 && s[best - 1] == ' ') --best;
    if (best == 0) return 0;
    ++c->cut;
    return tf_emit(c, o, s, best) && tf_emit(c, o, "...", 3);
}

/* One line (no "\n") re-broken to the room; a piece wider than the room is cut. */
static int tf_break_line(tf_ctx *c, int *o, const char *s, int n) {
    int start = 0, force;
    while (start < n) {
        int i = start, last = -1, last_kind = 0, last_end = start, prev_at = start;
        unsigned int before = 0, prev = 0;
        if (tf_px(c, s + start, n - start) <= c->room) return tf_emit(c, o, s + start, n - start);
        if (start == 0) {                                   /* the line's word boundaries, once */
            memset(tf_wb, 0, sizeof tf_wb);
            if (c->utf8 && n <= FIT_MAX) wb_mark(s, n);
        }
        /* the last opportunity whose line fits; if none, again allowing a break inside a dictionary word */
        for (force = 0; force < 2 && last < 0; ++force) {
        i = start;
        before = prev = 0;
        prev_at = start;
        while (i < n) {
            int at = i;
            unsigned int cp = tf_cp(c, s, n, &i);
            if (at > start) {
                int kind = tf_opportunity(c, at, before, prev, cp, force);
                if (kind) {
                    int end = kind == 1 ? prev_at : at;
                    if (tf_px(c, s + start, end - start) > c->room) break;
                    last = at;
                    last_kind = kind;
                    last_end = end;
                }
            }
            before = prev;
            prev = cp;
            prev_at = at;
        }
        }
        if (last < 0) {
            /* nothing fits: the piece up to the next opportunity (or the end) is cut */
            int next = n;
            i = start;
            prev = 0;
            before = 0;
            while (i < n) {
                int at = i;
                unsigned int cp = tf_cp(c, s, n, &i);
                if (at > start && tf_opportunity(c, at, before, prev, cp, 0)) { next = at; break; }
                before = prev;
                prev = cp;
            }
            {
                int piece = next;
                while (piece > start && s[piece - 1] == ' ') --piece;
                if (!tf_cut(c, o, s + start, piece - start)) return 0;
            }
            if (next >= n) return 1;
            if (!tf_emit(c, o, "\n", 1)) return 0;
            ++c->broke;
            start = next;
            continue;
        }
        /* a space becomes the break (last_end is where it starts); otherwise the break goes in */
        if (!tf_emit(c, o, s + start, last_end - start) || !tf_emit(c, o, "\n", 1)) return 0;
        (void)last_kind;
        ++c->broke;
        start = last;
    }
    return 1;
}

/* text[0..n) fitted to c->room into fit_out: its length; TF_FITS when it fits as it is (fit_out
   unused); -1: show English. */
#define TF_FITS (-2)
static int tf_fit(tf_ctx *c, const char *text, int n, int multiline, int height) {
    int i = 0, o = 0, wide = 0;
    while (i <= n) {
        int e = i;
        while (e < n && text[e] != '\n') ++e;
        if (tf_px(c, text + i, e - i) > c->room) { wide = 1; break; }
        i = e + 1;
    }
    if (!wide) {
        if (height > 0 && c->height != NULL && c->height(c->font, NULL, text) > height) return -1;
        return TF_FITS;
    }
    i = 0;
    while (i <= n) {
        int e = i;
        while (e < n && text[e] != '\n') ++e;
        if (tf_px(c, text + i, e - i) <= c->room) {
            if (!tf_emit(c, &o, text + i, e - i)) return -1;
        } else if (multiline) {
            if (!tf_break_line(c, &o, text + i, e - i)) return -1;
        } else if (!tf_cut(c, &o, text + i, e - i)) {
            return -1;
        }
        if (e < n && !tf_emit(c, &o, "\n", 1)) return -1;
        i = e + 1;
    }
    fit_out[o] = 0;
    if (height > 0 && c->height != NULL && c->height(c->font, NULL, fit_out) > height) return -1;
    /* a last check: every line of the result within the room */
    i = 0;
    while (i <= o) {
        int e = i;
        while (e < o && fit_out[e] != '\n') ++e;
        if (tf_px(c, fit_out + i, e - i) > c->room) return -1;
        i = e + 1;
    }
    return o;
}

#endif
