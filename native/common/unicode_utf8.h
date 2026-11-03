/* unicode_utf8.h -- "Unicode Text.dll", both games: reading the games' text.

   While utf8_drawing is 0 the game's bytes are letters as they always were (Latin-1, and the
   Windows-1252 letters the fonts have at 0x80-0x9F). Once it is 1 text is UTF-8; a byte that
   does not start a whole, shortest UTF-8 sequence is read as its Latin-1 letter, so every name
   and text the games kept before (one byte a letter) reads the same. */
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

/* The next letter of UTF-8 text, a stray byte read as Latin-1. */
static unsigned int utf8_next(const unsigned char **p) {
    int len, cp = utf8_at(*p, &len);
    if (cp < 0) { len = 1; cp = **p; }
    *p += len;
    return (unsigned int)cp;
}

/* The next letter of the game's text as the DLL reads it now. */
static unsigned int utf_next(const unsigned char **p) {
    if (utf8_drawing) return utf8_next(p);
    return *(*p)++;
}

/* The start of the letter before `end` in `text`. */
static const char *letter_before(const char *text, const char *end) {
    const unsigned char *p = (const unsigned char *)text, *last = p;
    while (p < (const unsigned char *)end) {
        last = p;
        utf_next(&p);
    }
    return (const char *)last;
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

#endif
