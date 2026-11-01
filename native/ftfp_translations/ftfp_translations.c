/* Translations -- the player's chosen translation, in Fish Tycoon and Plant Tycoon.

   WHAT.  At game start this DLL reads the translation the patcher's Translations window chose
   ("<this DLL's folder>\Translation.ini": file=<the translation's full path>, else the copy
   "Translation.txt" beside it) and from then on the game shows it:

     * every line of the game's string table, through the game's own lookup (Fish Tycoon
       0x426FD0, Plant Tycoon 0x44CA70): a line is replaced when the file has its key
       "strings/<id>" with the English the game has now (a line whose English changed since
       the file was made shows the new English);
     * the patcher's own DLLs' texts ("mod/<dll>.<name>", native/ftfp_translations/
       translation_tables.h): every pointer to such a text in that DLL (its relocations) is
       pointed at the translation instead.  A text that DLL copies into a fixed space has a
       limit; a longer translation is refused (English stays), so nothing can overflow.

   No choice, "English (original)", a missing or unreadable file, or a file for the other game:
   nothing is installed and the game is exactly as without this DLL.  A bad line (a broken
   placeholder, a changed English, too long) shows English; the file's other lines still work.
   Every problem goes to "Translations.log" beside the DLL (line numbers, never the text).

   CHOICES.  A translation may choose words by number, "{%1: one=fish | other=fish}".  Fish
   Tycoon's counted lines (strings 69-75, "You have sold %d fish!") are formatted by the game's
   sprintf at 0x4247FF, 0x424820, 0x424841, 0x424883 and 0x4248AF; those five calls come here
   first and the choice is made with the real number.  Everywhere else a choice takes its
   "other" branch ("o" for a person).  Neither game has a line about a person whose sex it
   knows, so person choices always take "o" (docs/translations.md).

   TEXT.  The game draws bytes in its fonts: the translation is written in Windows-1252
   (Latin-1 and the usual quotes and dashes; any other letter as '?').  When "Unicode Text.dll"
   (loaded first) exports FtfpUnicodeTextActive() returning nonzero, the translation is passed
   on as UTF-8 instead.  Windows popups (the Time Warp's) get UTF-16.

   PLANT TYCOON'S LOOKUP.  "Store Upgrades and Items.dll" already jumps from 0x44CA70 to its own
   texts and back; this DLL is loaded after it (the startup loader loads it last) and chains:
   its jump goes to this DLL, which calls the jump that was there (or the stock code). */
#include <windows.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "translation_text.h"
#include "translation_tables.h"

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))

EXTERN_C IMAGE_DOS_HEADER __ImageBase;

/* Small string helpers of our own (no locale, nothing imported). */
static int slen(const char *s) { int n = 0; while (s[n]) ++n; return n; }
static int wlen(const wchar_t *s) { int n = 0; while (s[n]) ++n; return n; }
static void wcopy(wchar_t *to, const wchar_t *from) { while ((*to++ = *from++) != 0) {} }
static void wcat(wchar_t *to, const wchar_t *from) { wcopy(to + wlen(to), from); }
static int starts(tt_span line, const char *word) {
    int k;
    for (k = 0; word[k]; ++k) if (k >= line.n || tt_lower((unsigned char)line.s[k]) != word[k]) return 0;
    return 1;
}

#define GAME_FISH 1
#define GAME_PLANT 2

/* Fish Tycoon: the lookup 0x426FD0 (thiscall, ret 4): push esi; mov esi, [esp + 8] */
#define FISH_LOOKUP 0x00426FD0u
#define FISH_LOOKUP_BACK 0x00426FD5u
#define FISH_TABLE 0x00457340u
#define FISH_STRINGS 0xF9
#define FISH_SPRINTF 0x0042B20Bu
static const unsigned char FISH_LOOKUP_STOCK[5] = { 0x56, 0x8B, 0x74, 0x24, 0x08 };
static const unsigned char FISH_LOOKUP_TAIL[6] = { 0x81, 0xFE, 0xF8, 0x00, 0x00, 0x00 };
#define FISH_COUNT_CALL_1 0x004247FFu
#define FISH_COUNT_CALL_2 0x00424820u
#define FISH_COUNT_CALL_3 0x00424841u
#define FISH_COUNT_CALL_4 0x00424883u
#define FISH_COUNT_CALL_5 0x004248AFu
static const unsigned int FISH_COUNT_CALLS[5] = { FISH_COUNT_CALL_1, FISH_COUNT_CALL_2, FISH_COUNT_CALL_3, FISH_COUNT_CALL_4,
                                                  FISH_COUNT_CALL_5 };

/* Plant Tycoon: the lookup 0x44CA70 (thiscall, ret 4): mov eax, [esp + 4]; test eax, eax */
#define PLANT_LOOKUP 0x0044CA70u
#define PLANT_LOOKUP_BACK 0x0044CA76u
#define PLANT_ENTRIES 0x00493CC0u
#define PLANT_LAST 0x1B2
static const unsigned char PLANT_LOOKUP_STOCK[6] = { 0x8B, 0x44, 0x24, 0x04, 0x85, 0xC0 };
static const unsigned char PLANT_LOOKUP_TAIL[7] = { 0x75, 0x08, 0xB8, 0xF8, 0x54, 0x46, 0x00 };

#define MAX_IDS 0x200
#define MAX_FILE (8 * 1024 * 1024)
#define LOG_LINES 40

typedef struct row {
    int line;
    int kind;                        /* 1 a game line, 2 a DLL text */
    int id;                          /* the game's string id, or the index in TR_MOD_TEXTS */
    const char *english;             /* UTF-8 */
    int english_n;
    char *english_game;              /* the English as the game holds it (Windows-1252), for matching */
    const char *translation;         /* UTF-8, choices still in */
    int translation_n;
    void *out;                       /* the translation as the game gets it (choices: o / other) */
    int has_select;
    struct row *next;                /* the next line with the same id */
} row;

static int game = 0;
static int installed = 0;
static int text_mode = 0;            /* 0 Windows-1252, 1 UTF-8 */
static int plural_rule = TT_EN;
static row *rows = NULL;
static int row_count = 0;
static row *by_id[MAX_IDS];
static row *mod_rows[64];            /* buckets of the ANSI DLL texts, by their English's hash */
static int used = 0, refused = 0, patched_pointers = 0;
static wchar_t folder[1024];
static char language_name[96];
static char file_label[200];
static char log_text[4096];
static int log_at = 0;
static DWORD next_lookup = 0;        /* what the lookup went to before: the stock head, or an earlier hook */
static const DWORD k_fish_back = FISH_LOOKUP_BACK;
static const DWORD k_plant_back = PLANT_LOOKUP_BACK;

/* ----------------------------------------------------------------- memory and the log */

static void *tr_alloc(SIZE_T n) { return HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, n == 0 ? 1 : n); }

static void log_add(const char *text) {
    while (*text && log_at < (int)sizeof log_text - 1) log_text[log_at++] = *text++;
    log_text[log_at] = 0;
}

static void log_int(int v) {
    char digits[12];
    int d = 0;
    unsigned int u = v < 0 ? (unsigned int)(-(v + 1)) + 1u : (unsigned int)v;
    if (v < 0) log_add("-");
    do { digits[d++] = (char)('0' + u % 10u); u /= 10u; } while (u && d < 11);
    while (d) { char c[2]; c[0] = digits[--d]; c[1] = 0; log_add(c); }
}

static void log_hex(unsigned int v) {
    char out[11];
    int k;
    out[0] = '0'; out[1] = 'x';
    for (k = 0; k < 8; ++k) out[2 + k] = "0123456789ABCDEF"[(v >> (28 - 4 * k)) & 0xF];
    out[10] = 0;
    log_add(out);
}

static int log_lines = 0;

static void log_refused(int line, const char *why) {
    ++refused;
    if (++log_lines > LOG_LINES) return;
    log_add("  line ");
    log_int(line);
    log_add(": ");
    log_add(why);
    log_add(" (shows English)\r\n");
}

static char head_text[1024];
static int head_at = 0;

/* The log's first lines (the outcome); log_add's lines (the details) follow them. */
static void head_add(const char *text) {
    while (*text && head_at < (int)sizeof head_text - 1) head_text[head_at++] = *text++;
    head_text[head_at] = 0;
}

static void write_log(void) {
    static const char bom[] = "\xEF\xBB\xBF";
    wchar_t path[1100];
    HANDLE file;
    DWORD written;
    if (folder[0] == 0 || wlen(folder) > 1000) return;
    wcopy(path, folder);
    wcat(path, L"Translations.log");
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, bom, 3, &written, NULL);
    WriteFile(file, head_text, (DWORD)head_at, &written, NULL);
    WriteFile(file, log_text, (DWORD)log_at, &written, NULL);
    CloseHandle(file);
}

/* ----------------------------------------------------------------- files */

/* The whole file, or NULL; *size its length. */
static unsigned char *read_file(const wchar_t *path, int *size) {
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING,
                              FILE_ATTRIBUTE_NORMAL, NULL);
    LARGE_INTEGER length;
    DWORD low, got = 0;
    unsigned char *data;
    if (file == INVALID_HANDLE_VALUE) return NULL;
    if (!GetFileSizeEx(file, &length) || length.HighPart != 0 || length.LowPart > MAX_FILE) {
        CloseHandle(file);
        return NULL;
    }
    low = length.LowPart;
    data = (unsigned char *)tr_alloc(low + 4);
    if (data == NULL || (low > 0 && (!ReadFile(file, data, low, &got, NULL) || got != low))) {
        CloseHandle(file);
        return NULL;
    }
    CloseHandle(file);
    *size = (int)low;
    return data;
}

/* UTF-8 text to a wide path, in out[0..cap). */
static int utf8_to_wide(const char *s, int n, wchar_t *out, int cap) {
    tt_out o;
    o.buf = (char *)out;
    o.cap = cap;
    o.mode = 2;
    o.at = 0;
    o.overflow = 0;
    {
        int i = 0;
        while (i < n) tt_put_cp(&o, tt_next_cp(s, n, &i));
    }
    if (o.overflow || o.at >= cap) return 0;
    out[o.at] = 0;
    return 1;
}

/* "<folder>\Translation.ini": the chosen file (file=...) and its language (language=...).
   Returns the translation's bytes, or NULL for English. */
static unsigned char *chosen_file(int *size) {
    wchar_t path[1100];
    int n = 0, i = 0;
    unsigned char *ini, *data = NULL;
    char *text;
    int text_n;
    wcopy(path, folder);
    wcat(path, L"Translation.ini");
    ini = read_file(path, &n);
    if (ini == NULL) { log_add("Translations: no translation chosen (English)\r\n"); return NULL; }
    text = (char *)tr_alloc((SIZE_T)n * 2 + 16);
    text_n = text != NULL ? tt_decode(ini, n, text, n * 2 + 16) : -1;
    if (text_n < 0) { log_add("Translations: Translation.ini is not UTF-8 (English)\r\n"); return NULL; }
    while (i < text_n) {
        int start = i, end;
        tt_span line, value;
        while (i < text_n && text[i] != '\n' && text[i] != '\r') ++i;
        end = i;
        while (i < text_n && (text[i] == '\n' || text[i] == '\r')) ++i;
        line.s = text + start;
        line.n = end - start;
        line = tt_strip(line);
        if (line.n > 5 && starts(line, "file=")) {
            value.s = line.s + 5;
            value.n = line.n - 5;
            value = tt_strip(value);
            if (value.n > 0 && utf8_to_wide(value.s, value.n, path, 1060)) {
                int k = value.n, j;
                data = read_file(path, size);
                while (k > 0 && value.s[k - 1] != '\\' && value.s[k - 1] != '/') --k;   /* the name only */
                for (j = 0; k < value.n && j < (int)sizeof file_label - 1; ++j, ++k) file_label[j] = value.s[k];
                file_label[j] = 0;
            }
        } else if (line.n > 9 && starts(line, "language=")) {
            int j;
            for (j = 0; j + 9 < line.n && j < (int)sizeof language_name - 1; ++j) language_name[j] = line.s[9 + j];
            language_name[j] = 0;
        }
    }
    if (data == NULL && file_label[0] != 0) {
        wcopy(path, folder);
        wcat(path, L"Translation.txt");
        data = read_file(path, size);
        if (data != NULL) log_add("Translations: the chosen file was not found; using the copy Translation.txt\r\n");
    }
    if (data == NULL && file_label[0] != 0) log_add("Translations: the chosen file could not be read (English)\r\n");
    if (file_label[0] == 0) log_add("Translations: English (original)\r\n");
    return data;
}

/* ----------------------------------------------------------------- the game's own lines */

static int in_list(const unsigned short *list, int n, int id) {
    int k;
    for (k = 0; k < n; ++k) if (list[k] == id) return 1;
    return 0;
}

/* The game's English text for a string id now (NULL if the table has none). */
static const char *game_english(int id, const char **name) {
    if (name != NULL) *name = NULL;
    if (game == GAME_FISH) {
        unsigned int entry = FISH_TABLE + (unsigned int)id * 12u;
        if (id < 0 || id >= FISH_STRINGS || AT(entry, 0, int) != id) return NULL;
        return AT(entry, 4, const char *);
    }
    if (id >= 1 && id <= PLANT_LAST) {
        char *entry = *(char **)(UINT_PTR)(PLANT_ENTRIES + (unsigned int)id * 4u);
        if (entry != NULL && AT(entry, 0, int) == id) {
            if (name != NULL) *name = AT(entry, 4, const char *);
            return AT(entry, 8, const char *);
        }
    }
    return NULL;
}

static int never_translated(int id) {
    return game == GAME_FISH ? in_list(TR_FISH_NEVER, TR_FISH_NEVER_N, id) : in_list(TR_PLANT_NEVER, TR_PLANT_NEVER_N, id);
}

/* The most a game line may hold (UTF-8 bytes): the buffer rule for lines the game copies. */
static int game_limit(int id, int english_bytes) {
    const char *name = NULL;
    int buffer;
    if (game == GAME_FISH) buffer = in_list(TR_FISH_BUFFER, TR_FISH_BUFFER_N, id);
    else {
        buffer = in_list(TR_PLANT_BUFFER, TR_PLANT_BUFFER_N, id);
        game_english(id, &name);
        if (name != NULL && strncmp(name, "eShortDesc", 10) == 0) buffer = 1;
    }
    if (!buffer) return TR_ABSOLUTE_MAX;
    return english_bytes + (english_bytes / 2 > 8 ? english_bytes / 2 : 8);
}

/* ----------------------------------------------------------------- reading the file */

static unsigned int fnv(const char *s, int n) {
    unsigned int h = 2166136261u;
    int i;
    for (i = 0; i < n; ++i) h = (h ^ (unsigned char)s[i]) * 16777619u;
    return h;
}

/* Field text with a spreadsheet's quotes taken off and \n \t \\ decoded, into out. */
static int field_decode(tt_span f, char *out) {
    int i = 0, o = 0;
    if (f.n >= 2 && f.s[0] == '"' && f.s[f.n - 1] == '"') {
        tt_span inner;
        inner.s = f.s + 1;
        inner.n = f.n - 2;
        for (i = 0; i < inner.n; ++i) {
            out[o++] = inner.s[i];
            if (inner.s[i] == '"' && i + 1 < inner.n && inner.s[i + 1] == '"') ++i;
        }
        f.s = out;
        f.n = o;
        o = 0;
        i = 0;
        {
            /* decode the escapes in place (the result is never longer) */
            char *w = out;
            while (i < f.n) {
                if (f.s[i] == '\\' && i + 1 < f.n && (f.s[i + 1] == 'n' || f.s[i + 1] == 't' || f.s[i + 1] == '\\')) {
                    w[o++] = f.s[i + 1] == 'n' ? '\n' : f.s[i + 1] == 't' ? '\t' : '\\';
                    i += 2;
                } else {
                    w[o++] = f.s[i++];
                }
            }
        }
        out[o] = 0;
        return o;
    }
    while (i < f.n) {
        if (f.s[i] == '\\' && i + 1 < f.n && (f.s[i + 1] == 'n' || f.s[i + 1] == 't' || f.s[i + 1] == '\\')) {
            out[o++] = f.s[i + 1] == 'n' ? '\n' : f.s[i + 1] == 't' ? '\t' : '\\';
            i += 2;
        } else {
            out[o++] = f.s[i++];
        }
    }
    out[o] = 0;
    return o;
}

static int hexval(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

static int key_char(unsigned char c, int id_part) {
    return (c >= 'a' && c <= 'z') || tt_is_digit(c) || c == '_' || c == '-' || c == '.'
        || (id_part && ((c >= 'A' && c <= 'Z') || c == '/'));
}

/* <source>/<id>~<8 lowercase hex>: the source, the id and the hash; 0 when malformed. */
static int split_key(tt_span key, tt_span *source, tt_span *id, unsigned int *hash) {
    int slash = -1, tilde, i;
    for (i = 0; i < key.n; ++i) if (key.s[i] == '/') { slash = i; break; }
    if (slash <= 0 || key.n < slash + 11) return 0;
    tilde = key.n - 9;
    if (key.s[tilde] != '~' || tilde <= slash + 1) return 0;
    for (i = 0; i < slash; ++i) if (!key_char((unsigned char)key.s[i], 0)) return 0;
    for (i = slash + 1; i < tilde; ++i) if (!key_char((unsigned char)key.s[i], 1)) return 0;
    *hash = 0;
    for (i = tilde + 1; i < key.n; ++i) {
        int v = hexval(key.s[i]);
        if (v < 0) return 0;
        *hash = (*hash << 4) | (unsigned int)v;
    }
    source->s = key.s;
    source->n = slash;
    id->s = key.s + slash + 1;
    id->n = tilde - slash - 1;
    return 1;
}

/* The translation as the game gets it, in its own heap block. */
static void *render_out(const char *s, int n, const tt_template *t, int mode, int *units) {
    tt_out o;
    void *buf = tr_alloc((SIZE_T)(TR_ABSOLUTE_MAX + 4) * 4);
    if (buf == NULL) return NULL;
    o.buf = (char *)buf;
    o.cap = TR_ABSOLUTE_MAX * 2;
    o.mode = mode;
    *units = tt_render(s, n, t, plural_rule, NULL, 0, 0, &o);
    return *units < 0 ? NULL : buf;
}

/* The translation's size as the limits count it (choices at their longest; UTF-8 bytes, or
   UTF-16 units for a popup's text), or a huge number when it does not even fit the measure. */
static int measure(const char *s, int n, const tt_template *t, int wide) {
    static char scratch[(TR_ABSOLUTE_MAX + 4) * 8];
    tt_out o;
    int units;
    o.buf = scratch;
    o.cap = TR_ABSOLUTE_MAX * 2;
    o.mode = wide ? 2 : 1;
    units = tt_render(s, n, t, plural_rule, NULL, 0, 1, &o);
    return units < 0 ? 0x7FFFFFFF : units;
}

static tt_template tmpl_english, tmpl_translation;

/* Every usable row of the file; 0 when the file as a whole cannot be used. */
static int read_rows(const char *text, int n) {
    int i = 0, line_no = 0, header = 0, lines = 1, k;
    int format_seen = 0;
    char *pool;
    int pool_at = 0;
    tt_span code;
    const char *title = game == GAME_FISH ? "Fish Tycoon" : "Plant Tycoon";
    code.s = "en";
    code.n = 2;
    for (k = 0; k < n; ++k) if (text[k] == '\n' || text[k] == '\r') ++lines;
    rows = (row *)tr_alloc(sizeof(row) * (SIZE_T)lines);
    pool = (char *)tr_alloc((SIZE_T)n * 2 + 64);
    if (rows == NULL || pool == NULL) return 0;
    /* pass 1: the header and the information rows */
    while (i < n) {
        int start = i, end, ncols = 0;
        tt_span cols[4];
        ++line_no;
        while (i < n && text[i] != '\n' && text[i] != '\r') ++i;
        end = i;
        if (i < n && text[i] == '\r' && i + 1 < n && text[i + 1] == '\n') i += 2; else if (i < n) ++i;
        {
            tt_span whole;
            whole.s = text + start;
            whole.n = end - start;
            if (tt_strip(whole).n == 0 || text[start] == '#') continue;
        }
        {
            int c = start;
            while (ncols < 4) {
                int e = c;
                while (e < end && text[e] != '\t') ++e;
                cols[ncols].s = text + c;
                cols[ncols].n = e - c;
                ++ncols;
                if (e >= end) break;
                c = e + 1;
            }
        }
        if (!header) {
            char a[72], b[72], c3[72];
            tt_span x, y, z;
            if (ncols < 3 || cols[0].n > 64 || cols[1].n > 64 || cols[2].n > 64) {
                log_add("Translations: the file has no header row (English)\r\n");
                return 0;
            }
            x.s = a; x.n = field_decode(cols[0], a); y.s = b; y.n = field_decode(cols[1], b); z.s = c3; z.n = field_decode(cols[2], c3);
            if (!tt_span_is(tt_strip(x), "key") || !tt_span_is(tt_strip(y), "english") || !tt_span_is(tt_strip(z), "translation")) {
                log_add("Translations: the file has no header row (English)\r\n");
                return 0;
            }
            header = 1;
            continue;
        }
        if (ncols < 2) continue;
        {
            tt_span key = tt_strip(cols[0]);
            int info = key.n > 0 && (key.s[0] == '@' || (key.n >= 3 && (unsigned char)key.s[0] == 0xEF
                                                         && (unsigned char)key.s[1] == 0xBC && (unsigned char)key.s[2] == 0xA0));
            if (!info) continue;
            {
                tt_span name, eng, val;
                char *e = pool + pool_at, *v;
                name.s = key.s + (key.s[0] == '@' ? 1 : 3);
                name.n = key.n - (key.s[0] == '@' ? 1 : 3);
                if (cols[1].n > 256 || (ncols > 2 && cols[2].n > 256)) continue;
                eng.s = e; eng.n = field_decode(cols[1], e);
                v = e + eng.n + 1;
                val.s = v; val.n = ncols > 2 ? field_decode(cols[2], v) : 0;
                if (ncols <= 2) v[0] = 0;
                if (tt_exact_case(name, "format") && !format_seen) {
                    tt_span f = tt_strip(val.n > 0 ? val : eng);
                    int major = 0, j = 0;
                    format_seen = 1;
                    while (j < f.n && f.s[j] != '.') {
                        if (!tt_is_digit((unsigned char)f.s[j]) || major > 1000) { log_add("Translations: @format is not a version (English)\r\n"); return 0; }
                        major = major * 10 + (f.s[j] - '0');
                        ++j;
                    }
                    if (j == 0) { log_add("Translations: @format is not a version (English)\r\n"); return 0; }
                    if (major > 1) { log_add("Translations: the file is a newer format than this DLL reads (English)\r\n"); return 0; }
                } else if (tt_exact_case(name, "game") && !(header & 2)) {
                    tt_span g = tt_strip(eng), want;
                    want.s = title;
                    want.n = slen(title);
                    header |= 2;
                    if (!tt_span_eq(g, want)) { log_add("Translations: the file is for another game (English)\r\n"); return 0; }
                } else if (tt_exact_case(name, "code") && !(header & 4)) {
                    header |= 4;
                    code = val;
                    pool_at += eng.n + val.n + 2;
                }
            }
        }
    }
    if (!header) { log_add("Translations: the file has no header row (English)\r\n"); return 0; }
    if (!(header & 2)) { log_add("Translations: the file has no @game row (English)\r\n"); return 0; }
    plural_rule = tt_rule_for(code);
    /* pass 2: the rows */
    i = 0;
    line_no = 0;
    header = 0;
    while (i < n) {
        int start = i, end, ncols = 0;
        tt_span cols[4], key, source, id;
        unsigned int hash;
        row *r;
        ++line_no;
        while (i < n && text[i] != '\n' && text[i] != '\r') ++i;
        end = i;
        if (i < n && text[i] == '\r' && i + 1 < n && text[i + 1] == '\n') i += 2; else if (i < n) ++i;
        {
            tt_span whole;
            whole.s = text + start;
            whole.n = end - start;
            if (tt_strip(whole).n == 0 || text[start] == '#') continue;
        }
        if (!header) { header = 1; continue; }
        {
            int c = start;
            while (ncols < 4) {
                int e = c;
                while (e < end && text[e] != '\t') ++e;
                cols[ncols].s = text + c;
                cols[ncols].n = e - c;
                ++ncols;
                if (e >= end) break;
                c = e + 1;
            }
        }
        if (ncols < 2) continue;
        key = tt_strip(cols[0]);
        if (key.n > 0 && (key.s[0] == '@' || (unsigned char)key.s[0] == 0xEF)) continue;
        if (ncols < 3 || cols[2].n == 0) continue;                            /* not translated */
        if (!split_key(key, &source, &id, &hash)) { log_refused(line_no, "the key is not a valid key"); continue; }
        r = &rows[row_count];
        r->line = line_no;
        r->english = pool + pool_at;
        r->english_n = field_decode(cols[1], pool + pool_at);
        pool_at += r->english_n + 1;
        r->translation = pool + pool_at;
        r->translation_n = field_decode(cols[2], pool + pool_at);
        pool_at += r->translation_n + 1;
        if (r->translation_n == 0) continue;
        if (tt_sha256_head((const unsigned char *)r->english, (unsigned int)r->english_n) != hash) {
            log_refused(line_no, "the English column does not match the key");
            continue;
        }
        if (tt_span_is(source, "strings")) {
            int v = 0, j;
            for (j = 0; j < id.n; ++j) {
                if (!tt_is_digit((unsigned char)id.s[j]) || v > 100000) { v = -1; break; }
                v = v * 10 + (id.s[j] - '0');
            }
            if (v < 0 || v >= MAX_IDS || id.n == 0) { log_refused(line_no, "no such game line"); continue; }
            r->kind = 1;
            r->id = v;
        } else if (tt_span_is(source, "mod")) {
            int m, found = -1;
            for (m = 0; m < TR_MOD_TEXT_COUNT; ++m) {
                if (TR_MOD_TEXTS[m].game == game && slen(TR_MOD_TEXTS[m].id) == id.n
                    && strncmp(TR_MOD_TEXTS[m].id, id.s, (size_t)id.n) == 0 && TR_MOD_TEXTS[m].hash == hash) found = m;
            }
            if (found < 0) { log_refused(line_no, "this version has no such patcher text"); continue; }
            r->kind = 2;
            r->id = found;
        } else {
            log_refused(line_no, "unknown source");
            continue;
        }
        if (!tt_translation_ok(r->english, r->english_n, r->translation, r->translation_n, &tmpl_english, &tmpl_translation)) {
            log_refused(line_no, "the placeholders or choices do not match the English");
            continue;
        }
        {
            int wide = r->kind == 2 && TR_MOD_TEXTS[r->id].wide;
            int limit = r->kind == 1 ? game_limit(r->id, r->english_n) : TR_MOD_TEXTS[r->id].limit;
            int size = measure(r->translation, r->translation_n, &tmpl_translation, wide), units;
            if (limit > TR_ABSOLUTE_MAX) limit = TR_ABSOLUTE_MAX;
            if (size > limit) { log_refused(line_no, "too long for its space"); continue; }
            r->has_select = tmpl_translation.nselects > 0;
            r->out = render_out(r->translation, r->translation_n, &tmpl_translation, wide ? 2 : text_mode, &units);
            if (r->out == NULL) { log_refused(line_no, "could not be written"); continue; }
            /* the English as the game holds it */
            {
                int en_units;
                r->english_game = (char *)render_out(r->english, r->english_n, &tmpl_english, wide ? 2 : 0, &en_units);
                if (r->english_game == NULL) { log_refused(line_no, "could not be read"); continue; }
                /* render_out made the English's own choices; the game's English has none in these games */
            }
        }
        if (r->kind == 1) {
            row **tail = &by_id[r->id];
            while (*tail != NULL && strcmp((*tail)->english_game, r->english_game) != 0) tail = &(*tail)->next;
            if (*tail != NULL) continue;                                       /* the same line again: the first counts */
            *tail = r;
        } else {
            int k2, twice = 0;
            for (k2 = 0; k2 < row_count; ++k2) if (rows[k2].kind == 2 && rows[k2].id == r->id) twice = 1;
            if (twice) continue;
            if (!TR_MOD_TEXTS[r->id].wide) {
                unsigned int b = fnv(r->english_game, slen(r->english_game)) & 63u;
                row **tail = &mod_rows[b];
                while (*tail != NULL) tail = &(*tail)->next;
                *tail = r;
            }
        }
        ++row_count;
        ++used;
    }
    return 1;
}

/* ----------------------------------------------------------------- the lookup */

/* The translation for what the lookup returned for `id`, or `result` itself. */
static const char *translate_game(int id, const char *result) {
    const char *english;
    row *r;
    if (result == NULL) return result;
    if (id >= 0 && id < MAX_IDS && by_id[id] != NULL && !never_translated(id)) {
        english = game_english(id, NULL);
        if (english != NULL) {
            for (r = by_id[id]; r != NULL; r = r->next) {
                if (strcmp(r->english_game, english) == 0) return (const char *)r->out;
            }
        }
    }
    /* a patcher DLL's own text that reached the game's table before this DLL started */
    {
        int len = slen(result);
        for (r = mod_rows[fnv(result, len) & 63u]; r != NULL; r = r->next) {
            if (strcmp(r->english_game, result) == 0) return (const char *)r->out;
        }
    }
    return result;
}

typedef const char *(__fastcall *lookup_fn)(void *self, int edx, int id);

static const char *__cdecl tr_lookup(void *self, int id) {
    const char *result = ((lookup_fn)(UINT_PTR)next_lookup)(self, 0, id);
    __try {
        result = translate_game(id, result);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    return result;
}

/* The lookup's new head: thiscall (ecx = the string table, [esp + 4] = id), ret 4. */
__declspec(naked) static void lookup_hook(void) {
    __asm {
        push ecx
        push dword ptr [esp + 8]
        push ecx
        call tr_lookup
        add esp, 8
        pop ecx
        ret 4
    }
}

/* The stock heads, run before going back into the game's lookup. */
__declspec(naked) static void fish_stock_head(void) {
    __asm {
        push esi
        mov esi, dword ptr [esp + 8]
        jmp dword ptr [k_fish_back]
    }
}

__declspec(naked) static void plant_stock_head(void) {
    __asm {
        mov eax, dword ptr [esp + 4]
        test eax, eax
        jmp dword ptr [k_plant_back]
    }
}

/* ----------------------------------------------------------------- Fish Tycoon's counted lines */

typedef int (__cdecl *sprintf_fn)(char *buffer, const char *format, ...);
static char counted[TR_ABSOLUTE_MAX * 2 + 8];

/* sprintf(buffer, format, n) at the five calls: a translation with a choice is made with n. */
static int __cdecl tr_sprintf(char *buffer, const char *format, int value) {
    const char *use = format;
    __try {
        int k;
        for (k = 0; k < MAX_IDS && use == format; ++k) {
            row *r;
            for (r = by_id[k]; r != NULL; r = r->next) {
                if (r->has_select && (const char *)r->out == format) {
                    tt_out o;
                    tt_template t;
                    tt_template e;
                    if (tt_translation_ok(r->english, r->english_n, r->translation, r->translation_n, &e, &t)) {
                        o.buf = counted;
                        o.cap = (int)sizeof counted;
                        o.mode = text_mode;
                        if (tt_render(r->translation, r->translation_n, &t, plural_rule, &value, 1, 0, &o) >= 0) use = counted;
                    }
                    break;
                }
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        use = format;
    }
    return ((sprintf_fn)(UINT_PTR)FISH_SPRINTF)(buffer, use, value);
}

/* ----------------------------------------------------------------- the patcher DLLs' texts */

static int is_code(const IMAGE_NT_HEADERS *nt, DWORD rva) {
    const IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
    int k;
    for (k = 0; k < nt->FileHeader.NumberOfSections; ++k) {
        DWORD size = s[k].Misc.VirtualSize > s[k].SizeOfRawData ? s[k].Misc.VirtualSize : s[k].SizeOfRawData;
        if (rva >= s[k].VirtualAddress && rva < s[k].VirtualAddress + size) return (s[k].Characteristics & IMAGE_SCN_MEM_EXECUTE) != 0;
    }
    return 1;
}

static int text_at(const char *at, const char *limit, const void *english, int wide) {
    if (wide) {
        const wchar_t *e = (const wchar_t *)english, *a = (const wchar_t *)at;
        int k = 0;
        while ((const char *)(a + k) + 2 <= limit && e[k] != 0 && a[k] == e[k]) ++k;
        return e[k] == 0 && (const char *)(a + k) + 2 <= limit && a[k] == 0;
    } else {
        const char *e = (const char *)english;
        int k = 0;
        while (at + k < limit && e[k] != 0 && at[k] == e[k]) ++k;
        return e[k] == 0 && at + k < limit && at[k] == 0;
    }
}

static void write_pointer(DWORD *at, DWORD value) {
    DWORD old, ignored;
    if (VirtualProtect(at, 4, PAGE_EXECUTE_READWRITE, &old)) {
        *at = value;
        VirtualProtect(at, 4, old, &ignored);
        FlushInstructionCache(GetCurrentProcess(), at, 4);
        ++patched_pointers;
    }
}

/* Every pointer the DLL `name` has to a translated text of its own goes to the translation. */
static void patch_dll(const char *name) {
    wchar_t wide_name[128];
    HMODULE module;
    const IMAGE_NT_HEADERS *nt;
    const IMAGE_DATA_DIRECTORY *dir;
    const char *base, *end;
    DWORD at;
    int k;
    if (!utf8_to_wide(name, slen(name), wide_name, 128)) return;
    module = GetModuleHandleW(wide_name);
    if (module == NULL) return;
    base = (const char *)module;
    if (AT(base, 0, WORD) != IMAGE_DOS_SIGNATURE) return;
    nt = (const IMAGE_NT_HEADERS *)(base + AT(base, 0x3C, LONG));
    if (nt->Signature != IMAGE_NT_SIGNATURE) return;
    end = base + nt->OptionalHeader.SizeOfImage;
    dir = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    if (dir->VirtualAddress == 0 || dir->Size == 0 || dir->VirtualAddress + dir->Size > nt->OptionalHeader.SizeOfImage) return;
    at = 0;
    while (at + 8 <= dir->Size) {
        const IMAGE_BASE_RELOCATION *block = (const IMAGE_BASE_RELOCATION *)(base + dir->VirtualAddress + at);
        DWORD count, e;
        if (block->SizeOfBlock < 8 || at + block->SizeOfBlock > dir->Size) break;
        count = (block->SizeOfBlock - 8) / 2;
        for (e = 0; e < count; ++e) {
            WORD entry = ((const WORD *)(block + 1))[e];
            DWORD *slot;
            const char *target;
            if ((entry >> 12) != IMAGE_REL_BASED_HIGHLOW) continue;
            slot = (DWORD *)(base + block->VirtualAddress + (entry & 0xFFF));
            if ((const char *)slot < base || (const char *)slot + 4 > end) continue;
            target = (const char *)(UINT_PTR)*slot;
            if (target < base || target >= end || is_code(nt, (DWORD)(target - base))) continue;
            for (k = 0; k < row_count; ++k) {
                row *r = &rows[k];
                const tr_mod_text *m;
                if (r->kind != 2 || r->out == NULL) continue;
                m = &TR_MOD_TEXTS[r->id];
                if (strcmp(m->dll, name) != 0) continue;
                if (text_at(target, end, r->english_game, m->wide)) {
                    write_pointer(slot, (DWORD)(UINT_PTR)r->out);
                    break;
                }
            }
        }
        at += block->SizeOfBlock;
    }
}

static void patch_dlls(void) {
    int k, j;
    for (k = 0; k < TR_MOD_TEXT_COUNT; ++k) {
        int first = 1;
        if (TR_MOD_TEXTS[k].game != game) continue;
        for (j = 0; j < k; ++j) if (TR_MOD_TEXTS[j].game == game && strcmp(TR_MOD_TEXTS[j].dll, TR_MOD_TEXTS[k].dll) == 0) first = 0;
        if (!first) continue;
        __try {
            patch_dll(TR_MOD_TEXTS[k].dll);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
        }
    }
}

/* "Unicode Text.dll" (Render Unicode with In-Game Fonts), loaded before this one: when it draws
   UTF-8 (FtfpUnicodeTextActive() nonzero), the translation is passed on as UTF-8. */
typedef int (__stdcall *active_fn)(void);

static int unicode_text_active(void) {
    HMODULE unicode = GetModuleHandleW(L"Unicode Text.dll");
    active_fn active = unicode != NULL ? (active_fn)GetProcAddress(unicode, "FtfpUnicodeTextActive") : NULL;
    return active != NULL && active() != 0;
}

/* ----------------------------------------------------------------- installing */

static ftfp_site_write writes[6];
static unsigned char lookup_now[6];
static unsigned char call_expect[5][5];

/* The lookup's first bytes as they are: the stock head, or an earlier hook's jump. */
static int prepare_lookup(unsigned int va, const unsigned char *stock, int stock_len, const unsigned char *tail,
                          int tail_len, DWORD stock_head) {
    MEMORY_BASIC_INFORMATION info;
    if (!ftfp_site_holds(va + (unsigned int)stock_len, tail, tail_len)) return 0;
    memcpy(lookup_now, (const void *)(UINT_PTR)va, 5);
    if (memcmp(lookup_now, stock, 5) == 0) {
        next_lookup = stock_head;
    } else if (lookup_now[0] == 0xE9) {
        DWORD to = va + 5u + *(DWORD *)(lookup_now + 1);
        if (VirtualQuery((const void *)(UINT_PTR)to, &info, sizeof info) != sizeof info || info.State != MEM_COMMIT
            || (info.Protect & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)) == 0) return 0;
        next_lookup = to;
    } else {
        return 0;
    }
    ftfp_site_branch(&writes[0], va, 5, lookup_now, 0xE9, (const void *)(UINT_PTR)lookup_hook);
    return 1;
}

static int install(void) {
    int count = 1, k;
    if (game == GAME_FISH) {
        if (!prepare_lookup(FISH_LOOKUP, FISH_LOOKUP_STOCK, 5, FISH_LOOKUP_TAIL, 6, (DWORD)(UINT_PTR)fish_stock_head)) return 0;
        for (k = 0; k < 5; ++k) {
            DWORD rel = FISH_SPRINTF - (FISH_COUNT_CALLS[k] + 5u);
            call_expect[k][0] = 0xE8;
            memcpy(call_expect[k] + 1, &rel, 4);
            ftfp_site_branch(&writes[count++], FISH_COUNT_CALLS[k], 5, call_expect[k], 0xE8, (const void *)(UINT_PTR)tr_sprintf);
        }
    } else {
        if (!prepare_lookup(PLANT_LOOKUP, PLANT_LOOKUP_STOCK, 6, PLANT_LOOKUP_TAIL, 7, (DWORD)(UINT_PTR)plant_stock_head)) return 0;
    }
    return ftfp_install_sites(writes, count);
}

static int which_game(void) {
    if (ftfp_site_holds(FISH_LOOKUP + 5u, FISH_LOOKUP_TAIL, 6) && ftfp_site_holds(FISH_TABLE, (const unsigned char *)"\0\0\0\0", 4)) return GAME_FISH;
    if (ftfp_site_holds(PLANT_LOOKUP + 6u, PLANT_LOOKUP_TAIL, 7)) return GAME_PLANT;
    return 0;
}

static void own_folder(void) {
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, folder, 1000);
    wchar_t *slash;
    if (n == 0 || n >= 1000) { folder[0] = 0; return; }
    folder[n] = 0;
    slash = folder + n;
    while (slash > folder && slash[-1] != L'\\' && slash[-1] != L'/') --slash;
    *slash = 0;
}

static int started = 0;

int __stdcall FtfpStartup(void) {
    unsigned char *data;
    char *text;
    int size = 0, text_n;
    if (started) return installed;
    started = 1;
    __try {
        own_folder();
        game = which_game();
        if (game == 0) {
            log_add("Translations: NOT installed; this is not the game this build expects\r\n");
        } else if ((data = chosen_file(&size)) != NULL) {
            text_mode = unicode_text_active() ? 1 : 0;
            text = (char *)tr_alloc((SIZE_T)size * 2 + 16);
            text_n = text != NULL ? tt_decode(data, size, text, size * 2 + 16) : -1;
            if (text_n < 0) {
                log_add("Translations: the file is not UTF-8 or UTF-16 with a byte-order mark (English)\r\n");
            } else if (read_rows(text, text_n)) {
                if (used == 0) {
                    log_add("Translations: no translated line could be used (English)\r\n");
                } else if (!install()) {
                    log_add("Translations: NOT installed; the code at ");
                    log_hex(ftfp_failed_site != 0 ? ftfp_failed_site : (game == GAME_FISH ? FISH_LOOKUP : PLANT_LOOKUP));
                    log_add(" is not the code this build expects\r\n");
                } else {
                    installed = 1;
                    patch_dlls();
                }
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        log_add("Translations: stopped by an error; the game stays in English where it was not yet changed\r\n");
    }
    if (installed) {
        char number[16];
        int at = 0, k;
        head_add("Translations: installed (");
        head_add(game == GAME_FISH ? "Fish Tycoon" : "Plant Tycoon");
        head_add(", ");
        head_add(file_label[0] ? file_label : "Translation.txt");
        head_add("): ");
        for (k = used, at = 15, number[15] = 0; at > 0 && (k > 0 || at == 15); k /= 10) number[--at] = (char)('0' + k % 10);
        head_add(number + at);
        head_add(" lines used, ");
        for (k = patched_pointers, at = 15; at > 0 && (k > 0 || at == 15); k /= 10) number[--at] = (char)('0' + k % 10);
        head_add(number + at);
        head_add(" patcher text references, ");
        head_add(text_mode ? "UTF-8 text" : "Windows-1252 text");
        head_add("\r\n");
    }
    if (refused > 0) {
        char number[16];
        int at = 15, k;
        number[15] = 0;
        for (k = refused; at > 0 && (k > 0 || at == 15); k /= 10) number[--at] = (char)('0' + k % 10);
        head_add("Translations: ");
        head_add(number + at);
        head_add(" line(s) show English:\r\n");
    }
    write_log();
    return installed;
}

int __stdcall FtfpTranslationsInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}
