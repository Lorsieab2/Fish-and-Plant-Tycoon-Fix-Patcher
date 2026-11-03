/* translated_count.h -- a patcher text with numbers ("2 doses left", the Time Warp's questions)
   in the player's translation, its words chosen by the real numbers.

   "Translations.dll" (the Translations setting; the startup loader loads it after every other
   companion, before the game runs) exports

       int __stdcall FtfpTranslateCounted(const void *english, int wide, const int *numbers,
                                          int count, void *out, int cap);

   `english` is a counted text of src/translation_strings.py exactly as its key has it, choices
   and all ("%d {%1: one=dose | other=doses} left"), and numbers[0..count) its conversions'
   values in order.  When the player's translation has that line, it is written into
   out[0..cap) (bytes, or UTF-16 units for `wide`, the terminator included) with its choices
   made and each %d replaced, and the length is returned; otherwise -1, and the caller writes
   its English exactly as before.  It never writes past cap.  Without Translations.dll (the
   setting off) every call is -1. */
#ifndef FTFP_TRANSLATED_COUNT_H
#define FTFP_TRANSLATED_COUNT_H

#include <windows.h>

typedef int (__stdcall *ftfp_counted_fn)(const void *english, int wide, const int *numbers, int count, void *out,
                                         int cap);

static ftfp_counted_fn ftfp_counted_lookup(void) {
    static ftfp_counted_fn fn = NULL;
    static int looked = 0;
    if (!looked) {
        HMODULE tr = GetModuleHandleW(L"Translations.dll");
        fn = tr != NULL ? (ftfp_counted_fn)GetProcAddress(tr, "FtfpTranslateCounted") : NULL;
        looked = 1;     /* the texts are made while the game runs, after every companion loaded */
    }
    return fn;
}

/* The translation of an ANSI counted text into out[0..cap); 0 when there is none. */
static int ftfp_counted(const char *english, const int *numbers, int count, char *out, int cap) {
    ftfp_counted_fn fn = ftfp_counted_lookup();
    return fn != NULL && cap > 0 && fn(english, 0, numbers, count, out, cap) >= 0;
}

/* The same for a Windows popup's (UTF-16) text. */
static int ftfp_counted_w(const wchar_t *english, const int *numbers, int count, wchar_t *out, int cap) {
    ftfp_counted_fn fn = ftfp_counted_lookup();
    return fn != NULL && cap > 0 && fn(english, 1, numbers, count, out, cap) >= 0;
}

#endif /* FTFP_TRANSLATED_COUNT_H */
