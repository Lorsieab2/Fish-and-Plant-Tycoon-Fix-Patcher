/* unicode_names.h -- "Unicode Text.dll", both games: one long name limit for every name box,
   the short form in the save's fixed fields and the whole name beside the save
   (docs/UNICODE_SPEC.md section 2; the patcher's own tools do the same in src/save_tools.py).

   THE LIMIT.  The games' name boxes (the five player rows of the player list and the new
   player's box) are text boxes whose limit the game sets to 32 bytes (setLimit(1, 0x20) at
   each NAME_LIMIT_SITES call), and the name is copied out of them with getText(dst, 0x20):
   31 bytes and a NUL. Every name box now takes NAME_BOX_BYTES (unicode_grapheme_table.h, made
   from src/unicode_data.py: the one place the number is written) bytes as the box keeps them,
   with no character cap: the box keeps its text by the shared write rule (unicode_utf8.h
   game_encode: a Windows-1252 letter one byte, any other UTF-8), so that is up to
   NAME_BOX_BYTES plain letters, fewer when letters need more bytes. It is the games' own text
   box cap (their setLimit clamps there), the same limit as the other Fun Patchers.

   THE SAVE.  The game's own fields stay what they were: 32 bytes (Fish Tycoon: the player list
   at state+0x1E3D8, 42 bytes a row, and the save's own name at state+0x1E3A5; Plant Tycoon: the
   list at state+0x53FC2, 33 a row, and state+8). The stock games build no file name and no
   registry key from them (their save files are "%s%d.ldw" of the slot's number; they import no
   registry call), so UTF-8 bytes there are only text. getText at a name site (NAME_TEXT_SITES)
   writes there:
     - a name that fits (31 bytes by the write rule) as it is;
     - else its SHORT FORM (short_for): the longest start of whole characters (grapheme
       clusters) that fits with the mark, trailing spaces dropped, then "...", or "2...",
       "3..." until it stands for no other name of any slot (its records, the other rows); a
       short form already standing for this very name is used again.
   The stock game loads such a save as always and shows the short form.

   THE NAMES FILE.  The whole name goes into "<Game> Fix Patcher Data\Names <slot>.dat" beside
   the save, the shared format: a header line ("FTFP Names 1"), then one record a line,
   short<TAB>room<TAB>whole<TAB>CRC-32 (8 upper-case hex digits over everything before the last
   tab), in UTF-8. Records are never removed; the first record of a short form wins; a record
   that is cut short, merged with another, has no mark (or v1.0.25's own short form of its
   name), is too long for its room, holds a control character or more than NAME_BOX_BYTES
   bytes is skipped. A file of v1.0.25 and before ("short NUL full NUL", "?" for letters
   Latin-1 has not) is still read, its record used while the player list holds its short
   form, and becomes the shared format when a record is added. The file is written as soon as
   a name is committed (getText into a player's row, or of the new player's box, which the game
   then copies into row 1, GAME_NEW_NAME_RETURN): the whole file to "Names <slot>.dat.tmp",
   moved over the old one (REPLACE_EXISTING | WRITE_THROUGH), written in place if the move is
   refused. A record whose write failed, or made while no slot is known, stays PENDING and is
   written again at a draw (every 2 s) and at the exit (names_sync). The patcher's tools write
   the same format (Rename Players, Copy Player Slot) and carry it (Back Up, Restore).

   SHOWING THEM.  Where the game shows a name it has the short form; the DLL shows the whole one
   instead: setText of a name box (box+0x30) with a player-list row, or with text that is a
   short form, gets the whole name, so the box shows it and edits it; the text draw and its
   width (draw_text, text_width) draw and measure the whole name for a short form, fitted to the
   width the game left for a name (unicode_text.h, fit).

   The file is included by each game's DLL after its GAME_* addresses. */
#ifndef FTFP_UNICODE_NAMES_H
#define FTFP_UNICODE_NAMES_H

#define SHORT_BYTES 32               /* the game's field: 31 bytes and a NUL */
#define SHORT_ROOM (SHORT_BYTES - 1)
#define SLOTS 5
#define NAME_RECS 256                /* records kept in memory (all slots); the files keep every one */
#define NAME_POOL (160 * 1024)       /* their whole names */
#define NAMES_FILE_MAX (256 * 1024)  /* the most of one Names file read and rewritten */
#define NAME_LETTERS_MAX NAME_BOX_BYTES   /* a name of NAME_BOX_BYTES bytes has at most as many letters */
#define LINE_MAX (8 * NAME_BOX_BYTES + 64)

static const char NAMES_HEADER[] = "FTFP Names 1\n";
static const char NAME_MARK[] = "...";

typedef struct name_rec {
    int slot;                        /* 1-5; 0: no slot known yet (pending) */
    int whole;                       /* its whole name (game bytes, NUL-ended) in rec_pool */
    unsigned char on_disk;           /* in the slot's file */
    unsigned char legacy;            /* v1.0.25's short form: used only while the row holds it */
    unsigned char session;           /* made in this session */
    char shortf[SHORT_BYTES];        /* the short form's bytes, as the field holds them */
} name_rec;

static name_rec recs[NAME_RECS];
static int rec_count;
static char rec_pool[NAME_POOL];
static int pool_used;
static int slot_pending[SLOTS + 1];
static DWORD pending_tick;

static const char *rec_whole(const name_rec *r) {
    return rec_pool + r->whole;
}

/* ---- the files beside the save */

static wchar_t names_folder[1024];
static int names_folder_ready;

static int names_path(int slot, wchar_t *path) {
    wchar_t digit[2];
    if (!names_folder_ready || wcslen(names_folder) + 24 >= 1024) return 0;
    digit[0] = (wchar_t)(L'0' + slot);
    digit[1] = L'\0';
    wcscpy_s(path, 1024, names_folder);
    wcscat_s(path, 1024, L"\\Names ");
    wcscat_s(path, 1024, digit);
    wcscat_s(path, 1024, L".dat");
    return 1;
}

/* A record for `slot` (the first of its short form wins): the record, or NULL when memory is full. */
static name_rec *add_rec(int slot, const char *shortf, const char *whole, int legacy, int on_disk, int session) {
    name_rec *r;
    int i, n = s_len(whole) + 1;
    for (i = 0; i < rec_count; ++i) {
        if (recs[i].slot == slot && s_eq(recs[i].shortf, shortf)) return &recs[i];
    }
    if (rec_count >= NAME_RECS || pool_used + n > NAME_POOL || s_len(shortf) >= SHORT_BYTES) return NULL;
    r = &recs[rec_count++];
    r->slot = slot;
    r->whole = pool_used;
    memcpy(rec_pool + pool_used, whole, (size_t)n);
    pool_used += n;
    r->on_disk = (unsigned char)on_disk;
    r->legacy = (unsigned char)legacy;
    r->session = (unsigned char)session;
    s_copy(r->shortf, shortf, SHORT_BYTES);
    return r;
}

static unsigned int crc32_of(const char *data, int n) {
    unsigned int c = 0xFFFFFFFFu;
    int i, k;
    for (i = 0; i < n; ++i) {
        c ^= (unsigned char)data[i];
        for (k = 0; k < 8; ++k) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}

/* Strict UTF-8 (the Names files' text) to letters: how many, or -1 when it is not UTF-8 or longer
   than `cap`. */
static int utf8_letters(const char *text, int n, unsigned int *cps, int cap) {
    const unsigned char *p = (const unsigned char *)text, *end = p + n;
    int count = 0, len, cp;
    while (p < end) {
        if (*p == 0 || count >= cap) return -1;
        cp = utf8_at(p, &len);
        if (cp < 0 || p + len > end) return -1;
        cps[count++] = (unsigned int)cp;
        p += len;
    }
    return count;
}

/* No control character (C0, DEL, C1) and at least one letter. */
static int letters_ok(const unsigned int *cps, int n) {
    int i;
    if (n <= 0) return 0;
    for (i = 0; i < n; ++i) {
        if (cps[i] < 0x20 || (cps[i] >= 0x7F && cps[i] < 0xA0)) return 0;
    }
    return 1;
}

/* v1.0.25's short form of a name: its first `room` letters, each the Latin-1 letter or '?'. */
static int is_old_short(const unsigned int *sh, int ns, const unsigned int *wh, int nw, int room) {
    int i, want = nw < room ? nw : room;
    if (ns != want) return 0;
    for (i = 0; i < want; ++i) {
        unsigned int c = wh[i];
        if (!(c >= 0x20 && c <= 0xFF && !(c >= 0x7F && c < 0xA0))) c = '?';
        if (sh[i] != c) return 0;
    }
    return 1;
}

static unsigned int name_cps_a[NAME_LETTERS_MAX + 4], name_cps_b[NAME_LETTERS_MAX + 4];
static char name_bytes_a[4 * NAME_LETTERS_MAX + 8], name_bytes_b[4 * NAME_LETTERS_MAX + 8];

/* A record's short form and whole name (as letters) checked as src/save_tools.py record_valid
   does: 1 when valid, its short form and whole name by the write rule in name_bytes_a / _b and
   *legacy set when its short form is v1.0.25's own (no mark). */
static int check_record(const unsigned int *sh, int ns, int room, const unsigned int *wh, int nw, int *legacy) {
    int i, slen, wlen, marked;
    if (room < 1 || room >= NAME_BOX_BYTES || !letters_ok(sh, ns) || !letters_ok(wh, nw)) return 0;
    if (ns == nw) {
        for (i = 0; i < ns && sh[i] == wh[i]; ++i) {}
        if (i == ns) return 0;                           /* a short form that is the name itself */
    }
    slen = game_encode(sh, ns, name_bytes_a, sizeof name_bytes_a);
    wlen = game_encode(wh, nw, name_bytes_b, sizeof name_bytes_b);
    if (slen < 0 || slen > room || wlen < 0 || wlen > NAME_BOX_BYTES) return 0;
    marked = ns >= 3 && sh[ns - 1] == '.' && sh[ns - 2] == '.' && sh[ns - 3] == '.';
    if (!marked && !is_old_short(sh, ns, wh, nw, room)) return 0;
    *legacy = !marked;
    return 1;
}

/* A valid record into memory for `slot` (one too long for the game's field can match no row). */
static int take_record(int slot, const unsigned int *sh, int ns, int room, const unsigned int *wh, int nw) {
    int legacy;
    if (!check_record(sh, ns, room, wh, nw, &legacy)) return 0;
    if (s_len(name_bytes_a) < SHORT_BYTES) add_rec(slot, name_bytes_a, name_bytes_b, legacy, 1, 0);
    return 1;
}

/* One record line (without its LF) of a Names file: 1 when valid (and taken into memory). */
static int parse_line(int slot, const char *line, int n) {
    int tabs[3], t = 0, i, room = 0, ns, nw;
    char crc[9];
    unsigned int value;
    for (i = 0; i < n; ++i) {
        if (line[i] == '\t') {
            if (t == 3) return 0;
            tabs[t++] = i;
        }
    }
    if (t != 3 || n - tabs[2] - 1 != 8) return 0;
    value = crc32_of(line, tabs[2]);
    for (i = 0; i < 8; ++i) crc[i] = "0123456789ABCDEF"[(value >> (28 - 4 * i)) & 15];
    for (i = 0; i < 8; ++i) {
        if (line[tabs[2] + 1 + i] != crc[i]) return 0;
    }
    if (tabs[1] - tabs[0] - 1 < 1 || tabs[1] - tabs[0] - 1 > 4) return 0;
    for (i = tabs[0] + 1; i < tabs[1]; ++i) {
        if (line[i] < '0' || line[i] > '9') return 0;
        room = room * 10 + (line[i] - '0');
    }
    ns = utf8_letters(line, tabs[0], name_cps_a, NAME_LETTERS_MAX);
    nw = utf8_letters(line + tabs[1] + 1, tabs[2] - tabs[1] - 1, name_cps_b, NAME_LETTERS_MAX);
    if (ns < 0 || nw < 0) return 0;
    return take_record(slot, name_cps_a, ns, room, name_cps_b, nw);
}

/* v1.0.25's file ("short NUL full NUL"): 1 when its one record is valid (checked into
   name_bytes_a / _b, and into memory for `slot` when slot > 0). */
static int parse_old(int slot, const char *data, int n) {
    int split, end, ns, nw, i;
    for (split = 0; split < n && data[split]; ++split) {}
    if (split == 0 || split > SHORT_ROOM || split >= n) return 0;
    for (end = split + 1; end < n && data[end]; ++end) {}
    if (end >= n || end == split + 1) return 0;
    ns = split;
    for (i = 0; i < ns; ++i) name_cps_a[i] = (unsigned char)data[i];        /* Latin-1 */
    nw = utf8_letters(data + split + 1, end - split - 1, name_cps_b, NAME_LETTERS_MAX);
    if (nw < 0) return 0;
    if (slot > 0) return take_record(slot, name_cps_a, ns, SHORT_ROOM, name_cps_b, nw);
    return check_record(name_cps_a, ns, SHORT_ROOM, name_cps_b, nw, &i);
}

static int has_header(const char *data, int n) {
    int h = (int)sizeof NAMES_HEADER - 1;
    return n >= h && memcmp(data, NAMES_HEADER, (size_t)h) == 0;
}

/* Every valid record of a Names file's text into memory for `slot`. */
static void parse_names(int slot, const char *data, int n) {
    int start, i;
    if (!has_header(data, n)) {
        parse_old(slot, data, n);
        return;
    }
    start = (int)sizeof NAMES_HEADER - 1;
    for (i = start; i <= n; ++i) {
        if (i == n || data[i] == '\n') {
            if (i > start) parse_line(slot, data + start, i - start);
            start = i + 1;
        }
    }
}

static char file_buf[NAMES_FILE_MAX + LINE_MAX];

/* The slot's Names file into file_buf: its length, 0 when there is none, -1 when it is too long. */
static int read_names_file(int slot) {
    wchar_t path[1024];
    DWORD got = 0;
    HANDLE file;
    int n = 0;
    if (!names_path(slot, path)) return 0;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    for (;;) {
        if (n >= NAMES_FILE_MAX) {
            n = -1;
            break;
        }
        if (!ReadFile(file, file_buf + n, (DWORD)(NAMES_FILE_MAX - n), &got, NULL) || got == 0) break;
        n += (int)got;
    }
    CloseHandle(file);
    return n;
}

/* `n` bytes to `path`, made anew: 1 when all were written. */
static int write_file(const wchar_t *path, const char *data, int n) {
    DWORD written = 0;
    HANDLE file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    int ok;
    if (file == INVALID_HANDLE_VALUE) return 0;
    ok = WriteFile(file, data, (DWORD)n, &written, NULL) && written == (DWORD)n;
    CloseHandle(file);
    return ok;
}

/* Game bytes as UTF-8 text at out[*at]; 0 when it does not fit before `cap`. */
static int put_text(const char *game, char *out, int *at, int cap) {
    const unsigned char *p = (const unsigned char *)game;
    while (*p) {
        int k = utf8_put(utf8_next(&p), out + *at, cap - *at);
        if (k == 0) return 0;
        *at += k;
    }
    return 1;
}

/* A record's line, short<TAB>room<TAB>whole<TAB>CRC-32 and LF, at out[*at]. */
static int put_record(const char *shortf, const char *whole, char *out, int *at, int cap) {
    int start = *at, i;
    unsigned int value;
    if (!put_text(shortf, out, at, cap) || *at + 4 > cap) return 0;
    out[(*at)++] = '\t';
    out[(*at)++] = (char)('0' + SHORT_ROOM / 10);
    out[(*at)++] = (char)('0' + SHORT_ROOM % 10);
    out[(*at)++] = '\t';
    if (!put_text(whole, out, at, cap) || *at + 10 > cap) return 0;
    value = crc32_of(out + start, *at - start);
    out[(*at)++] = '\t';
    for (i = 0; i < 8; ++i) out[(*at)++] = "0123456789ABCDEF"[(value >> (28 - 4 * i)) & 15];
    out[(*at)++] = '\n';
    return 1;
}

/* Add the slot's records that are not on disk yet to its Names file: the whole file is written to
   "Names <slot>.dat.tmp" and moved over the old one (a crash leaves the old file or the new one,
   never half), or written in place when the move is refused. Records already there stay as they
   are (a v1.0.25 file becomes the shared format, its record first). 1 when done. */
static int write_slot_file(int slot) {
    wchar_t path[1024], temp[1024];
    int n, at, i, any = 0, h = (int)sizeof NAMES_HEADER - 1;
    const int cap = NAMES_FILE_MAX + LINE_MAX;
    if (!names_path(slot, path) || wcslen(path) + 5 >= 1024) return 0;
    n = read_names_file(slot);
    if (n < 0) return 0;                               /* too long to rewrite: kept pending */
    if (has_header(file_buf, n)) {
        at = n;
        if (file_buf[at - 1] != '\n') file_buf[at++] = '\n';
    } else {
        /* none yet, or v1.0.25's: the shared format, the old file's record (as it was) first */
        static char old[SHORT_BYTES + 4 * NAME_LETTERS_MAX + 8];
        int k = n < (int)sizeof old ? n : (int)sizeof old;
        memcpy(old, file_buf, (size_t)k);
        memcpy(file_buf, NAMES_HEADER, (size_t)h);
        at = h;
        if (k > 0 && parse_old(0, old, k) && !put_record(name_bytes_a, name_bytes_b, file_buf, &at, cap)) return 0;
    }
    for (i = 0; i < rec_count; ++i) {
        name_rec *r = &recs[i];
        if (r->slot != slot || r->on_disk) continue;
        if (!put_record(r->shortf, rec_whole(r), file_buf, &at, cap)) return 0;
        any = 1;
    }
    if (!any && at == n) return 1;
    wcscpy_s(temp, 1024, path);
    wcscat_s(temp, 1024, L".tmp");
    if (!(write_file(temp, file_buf, at) && MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))) {
        DeleteFileW(temp);
        if (!write_file(path, file_buf, at)) return 0;
    }
    for (i = 0; i < rec_count; ++i) {
        if (recs[i].slot == slot) recs[i].on_disk = 1;
    }
    return 1;
}

static void names_start(const wchar_t *data_folder) {
    int slot, n;
    names_folder_ready = unicode_data_folder(data_folder, names_folder, 1024);
    for (slot = 1; slot <= SLOTS; ++slot) {
        n = read_names_file(slot);
        if (n > 0) parse_names(slot, file_buf, n);
    }
}

/* ---- the game's player list */

static const char *slot_field(int slot) {
    const char *state = *(const char *const *)(UINT_PTR)GAME_STATE_GLOBAL;
    if (state == NULL) return NULL;
    return state + GAME_SLOT_NAMES + (slot - 1) * GAME_SLOT_STRIDE;
}

static int field_is(const char *field, const char *shortf) {
    return field != NULL && s_eq(field, shortf);
}

/* The record standing for `text` (a field's bytes), as src/save_tools.py NameBook.full: with
   `slot` > 0 (the text is that slot's row) that slot's records first; then a marked record of any
   slot, a v1.0.25 one only while its own slot's row holds it. NULL when none. */
static const name_rec *rec_for(const char *text, int slot) {
    int i;
    if (text == NULL || text[0] == '\0') return NULL;
    if (slot > 0) {
        for (i = 0; i < rec_count; ++i) {
            if (recs[i].slot == slot && s_eq(text, recs[i].shortf)) return &recs[i];
        }
    }
    for (i = 0; i < rec_count; ++i) {
        const name_rec *r = &recs[i];
        if (!s_eq(text, r->shortf)) continue;
        if (!r->legacy || (r->slot >= 1 && field_is(slot_field(r->slot), r->shortf))) return r;
    }
    return NULL;
}

/* The whole name for `text` when it is a short form, else NULL. */
static const char *full_for_short(const char *text) {
    const name_rec *r = rec_for(text, 0);
    return r != NULL ? rec_whole(r) : NULL;
}

/* The first short form within `text` (a name the game put into its own text, such as the main
   menu's "Player: <name>"), at least 4 bytes, of a name made in this session or in its slot's row
   now: its whole name, *at and *len where it is; NULL when there is none. */
static const char *short_within(const char *text, int *at, int *len) {
    int i, n, m;
    if (text == NULL) return NULL;
    for (i = 0; i < rec_count; ++i) {
        const name_rec *r = &recs[i];
        const char *hit;
        if ((m = s_len(r->shortf)) < 4) continue;
        if (!r->session && (r->slot < 1 || !field_is(slot_field(r->slot), r->shortf))) continue;
        for (hit = text; *hit; ++hit) {
            for (n = 0; n < m && hit[n] == r->shortf[n]; ++n) {}
            if (n == m) {
                *at = (int)(hit - text);
                *len = m;
                return rec_whole(r);
            }
        }
    }
    return NULL;
}

/* ---- the short form (the same rule as src/save_tools.py short_form) */

/* The whole name a field's bytes stand for (src/save_tools.py NameBook.full): `slot`'s records
   first, then any slot's marked one, else the field itself. */
static const char *field_whole(int slot, const char *field) {
    const name_rec *r;
    int i;
    for (i = 0; i < rec_count; ++i) {
        if (recs[i].slot == slot && s_eq(recs[i].shortf, field)) return rec_whole(&recs[i]);
    }
    for (i = 0; i < rec_count; ++i) {
        r = &recs[i];
        if (!r->legacy && r->slot >= 1 && s_eq(r->shortf, field)) return rec_whole(r);
    }
    return field;
}

/* What is taken (src/save_tools.py NameBook.taken, in its order): short form -> whole name, of
   every slot's records, slot by slot, the first of a short form only; then of the rows but
   `exclude`'s (a row that is no short form stands for itself). */
static struct { const char *key, *whole; } taken[NAME_RECS + SLOTS];
static int taken_count;

static void taken_add(const char *key, const char *whole) {
    int i;
    for (i = 0; i < taken_count; ++i) {
        if (s_eq(taken[i].key, key)) return;
    }
    taken[taken_count].key = key;
    taken[taken_count].whole = whole;
    ++taken_count;
}

static void taken_make(int exclude) {
    int slot, i;
    taken_count = 0;
    for (slot = 1; slot <= SLOTS; ++slot) {
        for (i = 0; i < rec_count; ++i) {
            if (recs[i].slot == slot) taken_add(recs[i].shortf, rec_whole(&recs[i]));
        }
    }
    for (slot = 1; slot <= SLOTS; ++slot) {
        const char *field = slot_field(slot);
        if (slot != exclude && field != NULL && field[0]) taken_add(field, field_whole(slot, field));
    }
}

static const char *taken_get(const char *key) {
    int i;
    for (i = 0; i < taken_count; ++i) {
        if (s_eq(taken[i].key, key)) return taken[i].whole;
    }
    return NULL;
}

/* The field's bytes for the whole name `whole` (game bytes) into `out` (SHORT_BYTES), the row of
   `exclude` (the one being written) aside. The same rule as src/save_tools.py short_form:
     - a short form already standing for this very name, that fits, is used again;
     - a name that fits and stands for no other name is kept as it is;
     - else the longest start of whole characters that fits with the mark, trailing spaces
       dropped, then "...", "2...", "3..." until one is not taken. */
static void short_for(const char *whole, int exclude, char *out) {
    static unsigned int cps[NAME_LETTERS_MAX + 4];
    static unsigned int head[NAME_LETTERS_MAX + 16];
    static int starts[NAME_LETTERS_MAX + 2], mixed[NAME_LETTERS_MAX + 2];
    char tail[16], tmp[4];
    const char *seen;
    int i, n, clusters = 0, number, k, len = -1, t, end, b;
    gb_state s;
    taken_make(exclude);
    for (i = 0; i < taken_count; ++i) {
        if (s_eq(taken[i].whole, whole) && s_len(taken[i].key) <= SHORT_ROOM) {
            s_copy(out, taken[i].key, SHORT_BYTES);
            return;
        }
    }
    if (s_len(whole) <= SHORT_ROOM) {
        seen = taken_get(whole);
        if (seen == NULL || s_eq(seen, whole)) {
            s_copy(out, whole, SHORT_BYTES);
            return;
        }
    }
    n = game_decode(whole, cps, NAME_LETTERS_MAX);       /* its whole characters' starts */
    gb_start(&s);
    mixed[0] = 0;
    for (i = 0; i < n; ++i) {
        if (gb_push(&s, cps[i])) starts[clusters++] = i;
        b = game_byte(cps[i]);
        mixed[i + 1] = mixed[i] + (b >= 0 ? 1 : utf8_put(cps[i], tmp, 4));
    }
    starts[clusters] = n;
    for (number = 1; number < 1000000; ++number) {
        t = 0;
        if (number > 1) {
            char digits[12];
            int d = 0, v = number;
            while (v > 0) { digits[d++] = (char)('0' + v % 10); v /= 10; }
            while (d > 0) tail[t++] = digits[--d];
        }
        tail[t++] = '.'; tail[t++] = '.'; tail[t++] = '.';
        /* from the longest start whose bytes could fit (the write rule never takes fewer than the
           mixed bytes), down to the first that does */
        for (k = clusters; k > 0 && mixed[starts[k]] > SHORT_ROOM + 64; k = k * 3 / 4) {}
        for (; k < clusters && mixed[starts[k + 1]] <= SHORT_ROOM + 64; ++k) {}
        for (; k >= 0; --k) {
            end = starts[k];
            while (end > 0 && cps[end - 1] == ' ') --end;
            if (mixed[end] + t > SHORT_ROOM) {
                len = -1;
                continue;
            }
            memcpy(head, cps, (size_t)end * sizeof cps[0]);
            for (i = 0; i < t; ++i) head[end + i] = (unsigned char)tail[i];
            len = game_encode(head, end + t, out, SHORT_BYTES);
            if (len >= 0) break;
        }
        if (len >= 0 && taken_get(out) == NULL) return;
    }
    out[0] = '\0';
}

/* ---- committing names */

/* A name made in this session that a row holds, whose slot has no record of it yet (made while no
   slot was known, or put into that row another way): recorded for that slot, pending. */
static void mark_rows(void) {
    int slot, i, j, there;
    for (slot = 1; slot <= SLOTS; ++slot) {
        const char *field = slot_field(slot);
        if (field == NULL || !field[0]) continue;
        for (i = 0; i < rec_count; ++i) {
            name_rec *r = &recs[i];
            if (!r->session || r->slot == slot || !s_eq(r->shortf, field)) continue;
            for (there = 0, j = 0; j < rec_count; ++j) {
                if (recs[j].slot == slot && s_eq(recs[j].shortf, field)) there = 1;
            }
            if (!there && add_rec(slot, r->shortf, rec_whole(r), 0, 0, 1) != NULL) slot_pending[slot] = 1;
            break;
        }
    }
}

/* Each pending slot's file written again (at most every 2 s; `now`: at once). */
static void write_pending(int now) {
    int slot;
    DWORD tick = GetTickCount();
    if (!now && tick - pending_tick < 2000) return;
    pending_tick = tick;
    for (slot = 1; slot <= SLOTS; ++slot) {
        if (slot_pending[slot] && write_slot_file(slot)) slot_pending[slot] = 0;
    }
}

/* At a draw (every 64) and at the exit: the rows checked, the pending records written. */
__declspec(noinline) static void names_sync_now(int now) {
    if (slot_field(1) == NULL) return;
    mark_rows();
    write_pending(now);
}

__declspec(noinline) static void names_sync(void) {
    names_sync_now(0);
}

/* A name committed to `slot` (0: no slot known yet): its record, written at once, so a crash
   before the next draw or the exit keeps it; a write that fails stays pending. */
static void commit_name(int slot, const char *shortf, const char *whole) {
    if (whole[0] == '\0' || shortf[0] == '\0' || s_eq(shortf, whole)) return;
    if (add_rec(slot, shortf, whole, 0, 0, 1) == NULL || slot < 1) return;
    if (!write_slot_file(slot)) slot_pending[slot] = 1;
}

/* ---- the hooks' C side */

static const unsigned int NAME_LIMIT_RETURNS[] = { GAME_NAME_LIMIT_RETURNS };
static const unsigned int NAME_TEXT_RETURNS[] = { GAME_NAME_TEXT_RETURNS };

static int returns_to(unsigned int ret, const unsigned int *list, int count) {
    int i;
    for (i = 0; i < count; ++i) {
        if (list[i] == ret) return 1;
    }
    return 0;
}

/* setLimit(fixed, limit) from a name box's set-up: the shared limit. */
static int __cdecl name_limit(unsigned int ret, int limit) {
    if (limit == 0x20 && returns_to(ret, NAME_LIMIT_RETURNS, sizeof NAME_LIMIT_RETURNS / sizeof NAME_LIMIT_RETURNS[0])) {
        return NAME_BOX_BYTES;
    }
    return limit;
}

/* The box's text as the whole name: by the write rule (a stray byte a Windows-1252 letter), cut
   at whole characters to NAME_BOX_BYTES (a box the game's setText grew past it): the longest
   start of whole characters that fits (src/unicode_data.py cut_game_bytes). */
static void whole_of(const char *text, char *out, int cap) {
    static unsigned int cps[2 * NAME_LETTERS_MAX + 4];
    static int stops[2 * NAME_LETTERS_MAX + 4];
    int n = game_decode(text, cps, 2 * NAME_LETTERS_MAX + 2), i, mixed = 0, ends = 0, b;
    char tmp[4];
    gb_state s;
    if (!utf8_drawing) {
        const unsigned char *p = (const unsigned char *)text;
        for (n = 0; *p && n < 2 * NAME_LETTERS_MAX + 2; ++p) cps[n++] = byte_char(*p);
    }
    if (game_encode(cps, n, out, cap) >= 0) return;
    gb_start(&s);
    for (i = 0; i <= n; ++i) {
        if (i == n || gb_push(&s, cps[i])) {
            if (mixed > cap - 1) break;
            stops[ends++] = i;
        }
        if (i == n) break;
        b = game_byte(cps[i]);
        mixed += b >= 0 ? 1 : utf8_put(cps[i], tmp, 4);
    }
    while (ends > 0) {
        if (game_encode(cps, stops[--ends], out, cap) >= 0) return;
    }
    out[0] = '\0';
}

/* getText(dst, size) of a text box: the game's strncpy, but at a name site the field's bytes
   (short_for), the whole name recorded beside the save. */
static void __cdecl get_text(char *wrapper, unsigned int ret, char *dst, int size) {
    char *box = *(char **)(wrapper + 0x10);
    const char *text = *(const char **)(box + 0x30);
    int i = 0;
    if (size <= 0) return;
    if (text != NULL && returns_to(ret, NAME_TEXT_RETURNS, sizeof NAME_TEXT_RETURNS / sizeof NAME_TEXT_RETURNS[0])) {
        static char whole[NAME_BOX_BYTES + 1];
        char shortf[SHORT_BYTES];
        int slot, target = 0;
        whole_of(text, whole, sizeof whole);
        for (slot = 1; slot <= SLOTS; ++slot) {
            if (dst == slot_field(slot)) target = slot;
        }
        if (ret == GAME_NEW_NAME_RETURN) target = 1;    /* the game copies it into row 1 next */
        short_for(whole, target, shortf);
        if (size < SHORT_BYTES) shortf[size - 1] = '\0';   /* never past the game's buffer */
        for (i = 0; shortf[i] && i < size - 1; ++i) dst[i] = shortf[i];
        for (; i < size; ++i) dst[i] = '\0';
        if (whole[0]) commit_name(target, shortf, whole);
        /* not before the game's copy into row 1, which still holds the old name */
        if (ret != GAME_NEW_NAME_RETURN) names_sync();
        return;
    }
    /* strncpy(dst, text, size); dst[size - 1] = 0 */
    if (text != NULL) {
        for (; i < size && text[i]; ++i) dst[i] = text[i];
    }
    for (; i < size; ++i) dst[i] = '\0';
    dst[size - 1] = '\0';
}

/* A whole name as the box keeps it (game bytes; without UTF-8 drawing, bytes the box's font has,
   '?' for others). */
static void to_box_text(const char *whole, char *out, int cap) {
    const unsigned char *p = (const unsigned char *)whole;
    int n = 0;
    if (utf8_drawing) {
        s_copy(out, whole, cap);
        return;
    }
    while (*p && n < cap - 1) {
        int b = game_byte(utf8_next(&p));
        out[n++] = (char)(b >= 0 ? b : '?');
    }
    out[n] = '\0';
}

/* setText(text) of a text box: a player's short form (or row) becomes the whole name. */
static const char *__cdecl set_text(char *box, unsigned int ret, const char *text) {
    static char shown[NAME_BOX_BYTES + 1];
    const name_rec *r = NULL;
    int slot;
    (void)box;
    (void)ret;
    if (text == NULL) return text;
    for (slot = 1; slot <= SLOTS && r == NULL; ++slot) {
        if (text == slot_field(slot)) r = rec_for(text, slot);
    }
    if (r == NULL) r = rec_for(text, 0);
    if (r == NULL) return text;
    to_box_text(rec_whole(r), shown, sizeof shown);
    return shown;
}

#endif
