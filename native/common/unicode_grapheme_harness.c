/* unicode_grapheme_harness.c -- unicode_grapheme.h (and the typing filter) as the DLL builds it,
   in a console program for tests/test_unicode18.py.

   Each line of stdin: a command letter, a space, code points in hex separated by spaces.
     g ...  prints the grapheme lengths (in code points) of the text, e.g. "2 1"
     e ...  prints 1 when the whole text is drawn as an emoji (gb_emoji), else 0
     t ...  prints, for each code point, 1 when a text box takes it typed (letter_typable)
     b ...  prints the byte offset grapheme_before gives for the text's end (UTF-8) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "unicode_utf8.h"
#include "unicode_grapheme.h"

static unsigned int cps[200000];
static char utf8[800000];
static char line[2000000];

int main(void) {
    while (fgets(line, sizeof line, stdin)) {
        char *at = line + 1, *end;
        int n = 0, i, bytes = 0;
        char cmd = line[0];
        for (;;) {
            unsigned long v = strtoul(at, &end, 16);
            if (end == at) break;
            cps[n++] = (unsigned int)v;
            at = end;
        }
        for (i = 0; i < n; ++i) bytes += utf8_put(cps[i], utf8 + bytes, 4);
        utf8[bytes] = 0;
        if (cmd == 'g') {
            const unsigned char *p = (const unsigned char *)utf8, *q;
            unsigned int keep[GRAPHEME_MAX];
            int first = 1;
            for (;;) {
                int count = 0;
                q = p;
                if (!next_grapheme(&p, keep, GRAPHEME_MAX)) break;
                while (q < p) { utf8_next(&q); ++count; }
                printf(first ? "%d" : " %d", count);
                first = 0;
            }
            printf("\n");
        } else if (cmd == 'e') {
            printf("%d\n", gb_emoji(cps, n));
        } else if (cmd == 't') {
            for (i = 0; i < n; ++i) putchar(letter_typable(cps[i]) ? '1' : '0');
            printf("\n");
        } else if (cmd == 'b') {
            printf("%d\n", (int)(grapheme_before(utf8, utf8 + bytes) - utf8));
        }
        fflush(stdout);
    }
    return 0;
}
