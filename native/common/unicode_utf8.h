/* unicode_utf8.h -- "Unicode Text.dll", both games: reading and writing the games' text.

   THE READ RULE (docs/UNICODE_SPEC.md section 2, the same decoder as src/unicode_data.py
   decode_game_text): each whole, shortest UTF-8 sequence (Unicode Table 3-7: no overlong form, no
   surrogate, nothing past U+10FFFF) is its character; every other byte is its Windows-1252
   character, the five bytes Windows-1252 leaves undefined (81 8D 8F 90 9D) the Latin-1 control
   with the same number. Per sequence, not per string, so a name the games kept before (one byte
   a letter) and a mixed one read correctly.

   THE WRITE RULE (src/unicode_data.py encode_game_text, from VV): a character Windows-1252 has is
   its one byte, any other its UTF-8 bytes, both mixed in one string; when the mixed bytes would
   read back as different text (an "A-tilde" byte then a "copyright" byte spell the UTF-8 of
   "e-acute"), every non-ASCII character is written as UTF-8 instead. A text box keeps its text
   so (unicode_typing.h), so a name box's byte limit counts the bytes the save will hold. */
#ifndef FTFP_UNICODE_UTF8_H
#define FTFP_UNICODE_UTF8_H

/* Nonzero once the DLL draws UTF-8 (the Translations contract, FtfpUnicodeTextActive). */
static int utf8_drawing;

/* ---- strings (the DLL's own: its code runs in tests without Windows) */

static int s_len(const char *s) {
    int n = 0;
    while (s[n]) ++n;
    return n;
}

static int s_eq(const char *a, const char *b) {
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}

/* `src` into `dst` (at most cap - 1 bytes and a NUL). */
static void s_copy(char *dst, const char *src, int cap) {
    int n = 0;
    if (cap <= 0) return;
    while (n < cap - 1 && src[n]) { dst[n] = src[n]; ++n; }
    dst[n] = '\0';
}

/* ---- Windows-1252 */

/* 0x80-0x9F (0: one of the five undefined bytes, read as the Latin-1 control). The same table as
   src/unicode_data.py CP1252_HIGH; unicode_glyphs.h maps letters to the fonts' bytes with it. */
static const unsigned short CP1252_HIGH[32] = {
    0x20AC, 0, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021, 0x02C6, 0x2030, 0x0160, 0x2039, 0x0152, 0, 0x017D, 0,
    0, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014, 0x02DC, 0x2122, 0x0161, 0x203A, 0x0153, 0, 0x017E, 0x0178,
};

/* The character one byte stands for. */
static unsigned int byte_char(unsigned int b) {
    if (b >= 0x80 && b <= 0x9F && CP1252_HIGH[b - 0x80]) return CP1252_HIGH[b - 0x80];
    return b;
}

/* The one byte `cp` is written as, or -1 when Windows-1252 (or Latin-1, for its five) has it not. */
static int game_byte(unsigned int cp) {
    int i;
    if (cp < 0x80 || (cp >= 0xA0 && cp <= 0xFF)) return (int)cp;
    for (i = 0; i < 32; ++i) {
        if (CP1252_HIGH[i] == cp || (CP1252_HIGH[i] == 0 && cp == 0x80u + (unsigned int)i)) return 0x80 + i;
    }
    return -1;
}

/* ---- UTF-8 */

/* The letter of a whole, shortest UTF-8 sequence at p (its length in *len), or -1. */
static int utf8_at(const unsigned char *p, int *len) {
    unsigned int c = p[0], cp;
    int n, i;
    if (c < 0x80) { *len = 1; return (int)c; }
    if (c >= 0xC2 && c <= 0xDF) { n = 2; cp = c & 0x1F; }
    else if (c >= 0xE0 && c <= 0xEF) { n = 3; cp = c & 0x0F; }
    else if (c >= 0xF0 && c <= 0xF4) { n = 4; cp = c & 0x07; }
    else return -1;
    for (i = 1; i < n; ++i) {
        if ((p[i] & 0xC0) != 0x80) return -1;
        cp = (cp << 6) | (p[i] & 0x3F);
    }
    if ((n == 3 && cp < 0x800) || (n == 4 && (cp < 0x10000 || cp > 0x10FFFF)) || (cp >= 0xD800 && cp <= 0xDFFF)) {
        return -1;
    }
    *len = n;
    return (int)cp;
}

/* The next letter of the games' text by the read rule: a UTF-8 sequence, else a Windows-1252 byte. */
static unsigned int utf8_next(const unsigned char **p) {
    int len, cp = utf8_at(*p, &len);
    if (cp < 0) { len = 1; cp = (int)byte_char(**p); }
    *p += len;
    return (unsigned int)cp;
}

/* The next letter of the game's text as the DLL reads it now (without UTF-8 drawing: one byte, a
   Windows-1252 letter). */
static unsigned int utf_next(const unsigned char **p) {
    if (utf8_drawing) return utf8_next(p);
    return byte_char(*(*p)++);
}

static int utf8_put(unsigned int cp, char *out, int room) {
    if (cp < 0x80) { if (room < 1) return 0; out[0] = (char)cp; return 1; }
    if (cp < 0x800) {
        if (room < 2) return 0;
        out[0] = (char)(0xC0 | (cp >> 6)); out[1] = (char)(0x80 | (cp & 0x3F)); return 2;
    }
    if (cp < 0x10000) {
        if (room < 3) return 0;
        out[0] = (char)(0xE0 | (cp >> 12)); out[1] = (char)(0x80 | ((cp >> 6) & 0x3F));
        out[2] = (char)(0x80 | (cp & 0x3F)); return 3;
    }
    if (room < 4) return 0;
    out[0] = (char)(0xF0 | (cp >> 18)); out[1] = (char)(0x80 | ((cp >> 12) & 0x3F));
    out[2] = (char)(0x80 | ((cp >> 6) & 0x3F)); out[3] = (char)(0x80 | (cp & 0x3F)); return 4;
}

/* ---- the games' bytes */

/* The text's letters by the read rule, at most `cap` (the rest is left out): how many. */
static int game_decode(const char *text, unsigned int *cps, int cap) {
    const unsigned char *p = (const unsigned char *)text;
    int n = 0;
    while (*p && n < cap) cps[n++] = utf8_next(&p);
    return n;
}

/* `n` letters by the write rule into `out` (NUL-ended): the bytes written, or -1 when they need
   more than cap - 1 (`out` then holds nothing to use). */
static int game_encode(const unsigned int *cps, int n, char *out, int cap) {
    int len = 0, i, k, b;
    char tmp[4];
    const unsigned char *p;
    if (cap <= 0) return -1;
    for (i = 0; i < n; ++i) {                          /* mixed: a byte where Windows-1252 has one */
        b = game_byte(cps[i]);
        if (b >= 0) {
            if (len + 1 > cap - 1) return -1;
            out[len++] = (char)b;
        } else {
            k = utf8_put(cps[i], tmp, 4);
            if (len + k > cap - 1) return -1;
            memcpy(out + len, tmp, (size_t)k);
            len += k;
        }
    }
    out[len] = '\0';
    p = (const unsigned char *)out;                    /* reads back as the same text? */
    for (i = 0; i < n && *p; ++i) {
        if (utf8_next(&p) != cps[i]) break;
    }
    if (i == n && *p == 0) return len;
    len = 0;                                           /* no: every non-ASCII letter as UTF-8 */
    for (i = 0; i < n; ++i) {
        k = utf8_put(cps[i], tmp, 4);
        if (len + k > cap - 1) return -1;
        memcpy(out + len, tmp, (size_t)k);
        len += k;
    }
    out[len] = '\0';
    return len;
}

#endif
