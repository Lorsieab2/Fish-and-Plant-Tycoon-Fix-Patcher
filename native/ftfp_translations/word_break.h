/* word_break.h -- word boundaries for the scripts written without spaces (Translations.dll).

   Thai, Lao, Burmese (Myanmar), Khmer, Chinese and Japanese put no spaces between words, so a line
   that must wrap should break between words.  translation_fit.h asks wb_mark() for the line it is
   about to break; the answer is tf_wb[byte offset of a character]: 0 no information (a character
   of no such script, or a run that could not be segmented), 1 inside a word (no break before it),
   2 a word starts here (a break may go before it).

   Source of the words, in order:
     1. Windows' own icu.dll (Windows 10 1703 and later), loaded dynamically from System32:
        ubrk_open / ubrk_next / ubrk_close, UBRK_LINE for Thai, Lao, Burmese and Khmer, UBRK_WORD
        for Chinese and Japanese (the line iterator may break between any two ideographs; the word
        iterator uses the dictionary).  Missing icu.dll, a missing export, an error, or no word
        boundary at all in a long run: the next source.
     2. ICU's own dictionaries, unchanged, in "<this DLL's folder>\word-lists" (thaidict.txt,
        laodict.txt, burmesedict.txt, khmerdict.txt, cjdict.txt), read the first time text of that
        script is seen (not at start), each into a hash of its words.  Longest match with a look
        ahead of up to two more words, exactly as src/word_break.py (the editor's reference; tests
        compare them).  A missing or unreadable list leaves the run at 0, which is the old
        behaviour (Thai-like text is never broken; Chinese and Japanese break anywhere).

   A "run" is the characters in a row of one script (Han, Hiragana and Katakana count as one).
   Nothing here writes past its arrays: a run has at most FIT_MAX characters. */
#ifndef FTFP_WORD_BREAK_H
#define FTFP_WORD_BREAK_H

#define WB_THAI 1
#define WB_LAO 2
#define WB_MYANMAR 3
#define WB_KHMER 4
#define WB_CJ 5
#define WB_MAXW 48
#define WB_RUN_MAX (FIT_MAX + 8)

static const unsigned int WB_RANGES[] = {
    /* thai */   WB_THAI, 0x0E01, 0x0E3A, WB_THAI, 0x0E40, 0x0E4E, WB_THAI, 0x0E50, 0x0E59,
    /* lao */    WB_LAO, 0x0E81, 0x0ECD, WB_LAO, 0x0ED0, 0x0ED9, WB_LAO, 0x0EDC, 0x0EDF,
    /* myanmar */ WB_MYANMAR, 0x1000, 0x1049, WB_MYANMAR, 0x1050, 0x109F,
    /* khmer */  WB_KHMER, 0x1780, 0x17D3, WB_KHMER, 0x17DD, 0x17E9,
    /* cj */     WB_CJ, 0x2E80, 0x2FDF, WB_CJ, 0x3005, 0x3005, WB_CJ, 0x3007, 0x3007, WB_CJ, 0x3021, 0x3029,
                 WB_CJ, 0x3038, 0x303B, WB_CJ, 0x3041, 0x309A, WB_CJ, 0x309D, 0x309F, WB_CJ, 0x30A1, 0x30FA,
                 WB_CJ, 0x30FC, 0x30FF, WB_CJ, 0x31F0, 0x31FF, WB_CJ, 0x3400, 0x4DBF, WB_CJ, 0x4E00, 0x9FFF,
                 WB_CJ, 0xF900, 0xFAFF, WB_CJ, 0xFF66, 0xFF9F, WB_CJ, 0x20000, 0x3FFFD,
};

/* A character that joins the one before it: a word never starts on it. */
static const unsigned int WB_JOINERS[] = {
    0x0E31, 0x0E31, 0x0E34, 0x0E3A, 0x0E47, 0x0E4E, 0x0EB1, 0x0EB1, 0x0EB4, 0x0EBC, 0x0EC8, 0x0ECD,
    0x102B, 0x103E, 0x1056, 0x1059, 0x105E, 0x1060, 0x1062, 0x1064, 0x1067, 0x106D, 0x1071, 0x1074,
    0x1082, 0x108D, 0x108F, 0x108F, 0x109A, 0x109D, 0x17B4, 0x17D3, 0x17DD, 0x17DD, 0x3099, 0x309A,
};
static const unsigned int WB_KATAKANA[] = { 0x30A1, 0x30FA, 0x30FC, 0x30FF, 0x31F0, 0x31FF, 0xFF66, 0xFF9F };

/* 0, or WB_THAI .. WB_CJ for a character a list covers. */
static int wb_script(unsigned int cp) {
    int k;
    if (cp < 0x0E01) return 0;
    for (k = 0; k < (int)(sizeof WB_RANGES / sizeof WB_RANGES[0]); k += 3)
        if (cp >= WB_RANGES[k + 1] && cp <= WB_RANGES[k + 2]) return (int)WB_RANGES[k];
    return 0;
}

#define WB_JOINER(cp) tf_in((cp), WB_JOINERS, (int)(sizeof WB_JOINERS / sizeof WB_JOINERS[0]))
#define WB_KATA(cp) tf_in((cp), WB_KATAKANA, (int)(sizeof WB_KATAKANA / sizeof WB_KATAKANA[0]))

/* ----------------------------------------------------------------- the lists */

typedef struct wb_dict {
    int state;                       /* 0 not tried, 1 loaded, -1 unavailable */
    unsigned char *data;
    unsigned int *slots;             /* offset + 1 of a word in data; 0 empty */
    unsigned int mask;
    int longest;                     /* characters in the longest word */
} wb_dict;

static wb_dict wb_dicts[6];
static const wchar_t *const WB_FILES[6] = { NULL, L"thaidict.txt", L"laodict.txt", L"burmesedict.txt",
                                            L"khmerdict.txt", L"cjdict.txt" };

#define WB_FNV 2166136261u
static unsigned int wb_fnv(unsigned int h, unsigned char b) { return (h ^ b) * 16777619u; }
static int wb_end(unsigned char b) { return b == 0 || b == '\t' || b == '\r' || b == '\n' || b == ' '; }

static void wb_add(wb_dict *d, unsigned int at) {
    unsigned int h = WB_FNV, k = at, slot;
    int cps = 0;
    while (!wb_end(d->data[k])) {
        if ((d->data[k] & 0xC0) != 0x80) ++cps;
        h = wb_fnv(h, d->data[k++]);
    }
    if (k == at || cps > WB_MAXW) return;
    if (cps > d->longest) d->longest = cps;
    slot = h & d->mask;
    while (d->slots[slot] != 0) slot = (slot + 1) & d->mask;
    d->slots[slot] = at + 1;
}

/* Reads one list: UTF-8, an optional byte order mark, "#" lines are comments, one word a line (the
   Chinese and Japanese list adds a tab and a frequency). */
static void wb_load(int sc) {
    wb_dict *d = &wb_dicts[sc];
    wchar_t path[1100];
    static const wchar_t sub[] = L"word-lists\\";
    int size = 0, lines = 1, i, size_slots = 1;
    if (d->state != 0) return;
    d->state = -1;
    if (folder[0] == 0 || wlen(folder) > 1000) return;
    wcopy(path, folder);
    wcat(path, sub);
    wcat(path, WB_FILES[sc]);
    d->data = read_file(path, &size);
    if (d->data == NULL) return;
    for (i = 0; i < size; ++i) if (d->data[i] == '\n') ++lines;
    while (size_slots < lines + lines / 2 + 2) size_slots *= 2;
    d->slots = (unsigned int *)tr_alloc((SIZE_T)size_slots * 4);
    if (d->slots == NULL) {
        HeapFree(GetProcessHeap(), 0, d->data);
        d->data = NULL;
        return;
    }
    d->mask = (unsigned int)size_slots - 1;
    i = 0;
    if (size >= 3 && d->data[0] == 0xEF && d->data[1] == 0xBB && d->data[2] == 0xBF) i = 3;
    while (i < size) {
        int e = i;
        while (e < size && d->data[e] != '\n') ++e;
        while (i < e && (d->data[i] == ' ' || d->data[i] == '\t' || d->data[i] == '\r')) ++i;
        if (i < e && d->data[i] != '#') wb_add(d, (unsigned int)i);
        i = e + 1;
    }
    d->state = d->longest > 0 ? 1 : -1;
}

/* Is s[0..n) a word of the list (its hash already computed)? */
static int wb_find(const wb_dict *d, const char *s, int n, unsigned int h) {
    unsigned int slot = h & d->mask;
    while (d->slots[slot] != 0) {
        const unsigned char *w = d->data + (d->slots[slot] - 1);
        if (memcmp(w, s, (size_t)n) == 0 && wb_end(w[n])) return 1;
        slot = (slot + 1) & d->mask;
    }
    return 0;
}

/* ----------------------------------------------------------------- one run */

static unsigned int wb_cp[WB_RUN_MAX];
static int wb_off[WB_RUN_MAX + 1];          /* byte offset of each character of the run, then its end */
static unsigned char wb_start[WB_RUN_MAX + 1];
static unsigned char wb_begin[WB_RUN_MAX + 1];
static signed char wb_long[WB_RUN_MAX + 1];
static const char *wb_text;                 /* the line; wb_off counts from it */

/* The lengths (in characters, longest first) of the list's words at character i of a run of n. */
static int wb_matches(const wb_dict *d, int i, int n, int *lens) {
    unsigned int hashes[WB_MAXW + 1];
    int max = d->longest < n - i ? d->longest : n - i, l, b, found = 0;
    unsigned int h = WB_FNV;
    if (!wb_start[i]) return 0;
    for (l = 1; l <= max; ++l) {
        for (b = wb_off[i + l - 1]; b < wb_off[i + l]; ++b) h = wb_fnv(h, (unsigned char)wb_text[b]);
        hashes[l] = h;
    }
    for (l = max; l >= 1; --l) {
        if ((i + l == n || wb_start[i + l]) &&
            wb_find(d, wb_text + wb_off[i], wb_off[i + l] - wb_off[i], hashes[l])) lens[found++] = l;
    }
    return found;
}

static int wb_longest(const wb_dict *d, int i, int n) {
    if (wb_long[i] < 0) {
        int lens[WB_MAXW + 1];
        wb_long[i] = (signed char)(wb_matches(d, i, n, lens) > 0 ? lens[0] : 0);
    }
    return wb_long[i];
}

/* wb_begin[k] = 1 where a word starts, by the list (the same method as src/word_break.py). */
static void wb_segment(const wb_dict *d, int sc, int n) {
    int i, j;
    for (i = 0; i < n; ++i) {
        wb_start[i] = (unsigned char)(!WB_JOINER(wb_cp[i]) && !(i > 0 && wb_cp[i - 1] == 0x17D2));
        wb_begin[i] = 0;
        wb_long[i] = -1;
    }
    wb_start[n] = 1;
    wb_long[n] = -1;
    i = 0;
    while (i < n) {
        int lens[WB_MAXW + 1], found, choice = 0, k;
        wb_begin[i] = 1;
        if (!wb_start[i]) { ++i; continue; }
        found = wb_matches(d, i, n, lens);
        for (k = 0; k < found; ++k) {
            int end = i + lens[k], second, after;
            if (end == n) { choice = lens[k]; break; }
            second = wb_longest(d, end, n);
            if (!second) continue;
            after = end + second;
            if (after == n || wb_longest(d, after, n)) { choice = lens[k]; break; }
        }
        if (!choice && found > 0) choice = lens[0];
        if (choice) { i += choice; continue; }
        j = i + 1;                                   /* no word here: one unknown piece */
        if (sc == WB_CJ) {
            if (WB_KATA(wb_cp[i])) while (j < n && WB_KATA(wb_cp[j])) ++j;
        } else {
            while (j < n && !(wb_start[j] && wb_longest(d, j, n))) ++j;
        }
        i = j;
    }
}

/* ----------------------------------------------------------------- Windows' icu.dll */

typedef void *(__cdecl *wb_ubrk_open_fn)(int type, const char *locale, const unsigned short *text, int length, int *status);
typedef int (__cdecl *wb_ubrk_next_fn)(void *iterator);
typedef void (__cdecl *wb_ubrk_close_fn)(void *iterator);

static int wb_icu_state = 0;                 /* 0 not tried, 1 ready, -1 not available */
static wb_ubrk_open_fn wb_ubrk_open;
static wb_ubrk_next_fn wb_ubrk_next;
static wb_ubrk_close_fn wb_ubrk_close;
static unsigned short wb_u16[WB_RUN_MAX * 2 + 2];
static int wb_umap[WB_RUN_MAX * 2 + 2];

/* name, or name_NN for an ICU build with a version suffix. */
static FARPROC wb_symbol(HMODULE module, const char *name, int version) {
    char full[40];
    int n = 0;
    while (name[n] && n < 24) { full[n] = name[n]; ++n; }
    if (version > 0) {
        full[n++] = '_';
        if (version >= 100) full[n++] = (char)('0' + version / 100);
        full[n++] = (char)('0' + version / 10 % 10);
        full[n++] = (char)('0' + version % 10);
    }
    full[n] = 0;
    return GetProcAddress(module, full);
}

static void wb_icu_init(void) {
    HMODULE module;
    int version;
    wb_icu_state = -1;
    __try {
        module = LoadLibraryExW(L"icu.dll", NULL, 0x00000800);      /* LOAD_LIBRARY_SEARCH_SYSTEM32 */
        if (module == NULL) return;
        for (version = 0; version < 100; version = version == 0 ? 50 : version + 1) {
            wb_ubrk_open = (wb_ubrk_open_fn)wb_symbol(module, "ubrk_open", version);
            wb_ubrk_next = (wb_ubrk_next_fn)wb_symbol(module, "ubrk_next", version);
            wb_ubrk_close = (wb_ubrk_close_fn)wb_symbol(module, "ubrk_close", version);
            if (wb_ubrk_open != NULL && wb_ubrk_next != NULL && wb_ubrk_close != NULL) { wb_icu_state = 1; return; }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        wb_icu_state = -1;
    }
}

/* wb_begin[0..n) from the ICU break iterator; 0 when it could not be used. */
static int wb_icu_segment(int sc, int n) {
    int i, length = 0, status = 0, boundaries = 0, p, guard;
    void *iterator;
    for (i = 0; i < n; ++i) {
        unsigned int cp = wb_cp[i];
        wb_begin[i] = 0;
        wb_umap[length] = i;
        if (cp >= 0x10000) {
            cp -= 0x10000;
            wb_u16[length++] = (unsigned short)(0xD800 + (cp >> 10));
            wb_umap[length] = i;
            wb_u16[length++] = (unsigned short)(0xDC00 + (cp & 0x3FF));
        } else {
            wb_u16[length++] = (unsigned short)cp;
        }
    }
    wb_umap[length] = n;
    wb_begin[0] = 1;
    __try {
        iterator = wb_ubrk_open(sc == WB_CJ ? 1 : 2, "", wb_u16, length, &status);   /* UBRK_WORD, UBRK_LINE */
        if (iterator != NULL && status > 0) { wb_ubrk_close(iterator); return 0; }
        if (iterator == NULL) return 0;
        for (guard = 0, p = wb_ubrk_next(iterator); p > 0 && p < length && guard <= length; p = wb_ubrk_next(iterator), ++guard) {
            if (wb_umap[p] != wb_umap[p - 1]) { wb_begin[wb_umap[p]] = 1; ++boundaries; }
        }
        wb_ubrk_close(iterator);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
    return !(boundaries == 0 && n >= 10);          /* a long run with no boundary: no dictionary data, use ours */
}

/* ----------------------------------------------------------------- a line */

/* Marks tf_wb for every character of the runs in s[0..n) (UTF-8); tf_wb is zero before. */
static void wb_mark(const char *s, int n) {
    int i = 0;
    wb_text = s;
    while (i < n) {
        int at = i, count = 0, sc, k, ok = 0;
        unsigned int cp = tt_next_cp(s, n, &i);
        sc = wb_script(cp);
        if (sc == 0) continue;
        wb_cp[0] = cp;
        wb_off[0] = at;
        count = 1;
        while (i < n && count < WB_RUN_MAX - 1) {
            int j = i;
            unsigned int next = tt_next_cp(s, n, &j);
            if (wb_script(next) != sc) break;
            wb_cp[count] = next;
            wb_off[count++] = i;
            i = j;
        }
        wb_off[count] = i;
        if (wb_icu_state == 0) wb_icu_init();
        if (wb_icu_state == 1) ok = wb_icu_segment(sc, count);
        if (!ok) {
            wb_load(sc);
            if (wb_dicts[sc].state == 1) { wb_segment(&wb_dicts[sc], sc, count); ok = 1; }
        }
        if (ok) for (k = 0; k < count; ++k) tf_wb[wb_off[k]] = wb_begin[k] ? 2 : 1;
    }
}

#endif
