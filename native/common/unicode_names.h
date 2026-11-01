/* unicode_names.h -- "Unicode Text.dll", both games: one long name limit for every name box,
   a short Latin-1 form in the save's fixed fields and the full name beside the save.

   THE LIMIT.  The games' name boxes (the five player rows of the player list and the new
   player's box) are text boxes whose limit the game sets to 32 bytes (setLimit(1, 0x20) at
   each NAME_LIMIT_SITES call), and the name is copied out of them with getText(dst, 0x20):
   31 letters and a NUL. The box itself takes up to 0x4B0 = 1200 bytes (its setLimit clamps
   there), so that is the most a name can hold. Names are UTF-8 (unicode_text.h), up to 4
   bytes a letter, so every name box takes NAME_LETTERS = 300 letters (1200 / 4): the same
   limit in both games and in the patcher's own tools (src/save_tools.py, NAME_LIMIT). While
   the DLL draws the game's bytes (no UTF-8 drawing) a letter is one byte, so the box's
   limit is 300 bytes.

   THE SAVE.  The game's own fields stay what they were: 32 bytes (Fish Tycoon: the player
   list at state+0x1E3D8, 42 bytes a row, and the save's own name at state+0x1E3A5; Plant
   Tycoon: the list at state+0x53FC2, 33 a row, and state+8). getText at a name site
   (NAME_TEXT_SITES) writes the SHORT FORM there: each letter as its Latin-1 byte, '?' for one
   Latin-1 has not, cut after 31 letters (one byte a letter, so always at a letter). The stock
   game loads such a save as always. The full name goes into "<Game> Fix Patcher Data\Names
   <slot>.dat" beside the save: the short form, NUL, the full name in UTF-8, NUL. A file whose
   short form is not the one in the player list (the stock game renamed the player, or the
   slot was emptied) is not used. The patcher's tools copy it with the slot (Copy Player Slot)
   and write it (Rename Players).

   SHOWING THEM.  Where the game shows a name it has the short form; the DLL shows the full one
   instead: setText of a name box (box+0x30) with a player-list row, or with text that is a
   row's short form, gets the full name, so the box shows it and edits it; the text draw and
   its width (draw_text, text_width) draw and measure the full name for a short form, fitted to
   the width the game left for a name (unicode_text.h, fit). The box itself fits its text into
   its own width (box_width, box_draw), where the game cut letters off its text until it fit.

   The file is included by each game's DLL after its GAME_* addresses. */
#ifndef FTFP_UNICODE_NAMES_H
#define FTFP_UNICODE_NAMES_H

/* THE one name limit (src/save_tools.py NAME_LIMIT is the same): at most 300, as the box holds
   at most 0x4B0 = 1200 bytes and a letter is up to 4. */
#define NAME_LETTERS 300
#define NAME_BOX_BYTES (4 * NAME_LETTERS)
#define SHORT_BYTES 32               /* the game's field: 31 letters and a NUL */
#define SLOTS 5

typedef struct name_entry {
    char shortf[SHORT_BYTES];        /* the short form, as in the game's field */
    char full[NAME_BOX_BYTES + 1];   /* UTF-8 */
    int used;
} name_entry;

static name_entry slot_names[SLOTS];       /* "Names <slot>.dat" */
static name_entry typed_names[8];          /* names typed in this session, newest first */
static int typed_count;

/* ---- the short form */

/* Each letter of the UTF-8 `text` as its Latin-1 byte ('?' if it has none), at most `cap - 1`,
   NUL-ended. */
static void short_form(const char *text, char *out, int cap) {
    const unsigned char *p = (const unsigned char *)text;
    int n = 0;
    while (*p && n < cap - 1) {
        unsigned int cp = utf8_next(&p);
        out[n++] = (char)((cp >= 0x20 && cp <= 0xFF && (cp < 0x7F || cp >= 0xA0)) ? cp : '?');
    }
    out[n] = '\0';
}

/* `text` in UTF-8 (the box's bytes read as unicode_text.h reads them). */
static void to_utf8(const char *text, char *out, int cap) {
    const unsigned char *p = (const unsigned char *)text;
    int n = 0;
    while (*p) {
        unsigned int cp = utf_next(&p);
        int k = utf8_put(cp, out + n, cap - 1 - n);
        if (k == 0) break;
        n += k;
    }
    out[n] = '\0';
}

/* A full (UTF-8) name as the box keeps it: UTF-8 while the DLL draws UTF-8, else Latin-1 bytes
   ('?' for a letter Latin-1 has not). */
static void to_box_text(const char *full, char *out, int cap) {
    const unsigned char *p = (const unsigned char *)full;
    int n = 0;
    if (utf8_drawing) {
        s_copy(out, full, cap);
        return;
    }
    while (*p && n < cap - 1) {
        unsigned int cp = utf8_next(&p);
        out[n++] = (char)(cp <= 0xFF ? cp : '?');
    }
    out[n] = '\0';
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

static void read_slot_file(int slot) {
    wchar_t path[1024];
    char data[SHORT_BYTES + NAME_BOX_BYTES + 4];
    DWORD got = 0;
    HANDLE file;
    int split;
    name_entry *e = &slot_names[slot - 1];
    e->used = 0;
    if (!names_path(slot, path)) return;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    if (!ReadFile(file, data, (DWORD)sizeof data - 1, &got, NULL)) got = 0;
    CloseHandle(file);
    data[got] = '\0';
    for (split = 0; split < (int)got && data[split]; ++split) {}
    if (split >= SHORT_BYTES || split + 1 >= (int)got) return;
    memcpy(e->shortf, data, (size_t)split + 1);
    s_copy(e->full, data + split + 1, NAME_BOX_BYTES + 1);
    e->used = e->full[0] != '\0';
}

static void write_slot_file(int slot) {
    wchar_t path[1024];
    DWORD written;
    HANDLE file;
    name_entry *e = &slot_names[slot - 1];
    int a = s_len(e->shortf) + 1, b = s_len(e->full) + 1;
    if (!names_path(slot, path)) return;
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, e->shortf, (DWORD)a, &written, NULL);
    WriteFile(file, e->full, (DWORD)b, &written, NULL);
    CloseHandle(file);
}

static void names_start(const wchar_t *data_folder) {
    int slot;
    names_folder_ready = unicode_data_folder(data_folder, names_folder, 1024);
    for (slot = 1; slot <= SLOTS; ++slot) read_slot_file(slot);
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

/* The full name for `text` when it is a player's short form and the full name differs, else NULL. */
static const char *full_for_short(const char *text) {
    int i;
    if (text == NULL || text[0] == '\0') return NULL;
    for (i = 0; i < SLOTS; ++i) {
        name_entry *e = &slot_names[i];
        if (e->used && s_eq(text, e->shortf) && !s_eq(e->shortf, e->full)
            && field_is(slot_field(i + 1), e->shortf)) {
            return e->full;
        }
    }
    for (i = 0; i < typed_count; ++i) {
        if (s_eq(text, typed_names[i].shortf) && !s_eq(typed_names[i].shortf, typed_names[i].full)) {
            return typed_names[i].full;
        }
    }
    return NULL;
}

/* The first player's short form within `text` (a name the game put into its own text, such as
   the main menu's "Player: <name>"), at least 4 letters and not the full name itself: its full
   name, *at and *len where it is; NULL when there is none. */
static const char *short_within(const char *text, int *at, int *len) {
    int i, n = 0;
    const name_entry *lists[2];
    int counts[2], k;
    if (text == NULL) return NULL;
    lists[0] = slot_names;
    counts[0] = SLOTS;
    lists[1] = typed_names;
    counts[1] = typed_count;
    for (k = 0; k < 2; ++k) {
        for (i = 0; i < counts[k]; ++i) {
            const name_entry *e = &lists[k][i];
            const char *hit;
            int m;
            if (!e->used || s_eq(e->shortf, e->full) || (m = s_len(e->shortf)) < 4) continue;
            if (k == 0 && !field_is(slot_field(i + 1), e->shortf)) continue;
            for (hit = text; *hit; ++hit) {
                for (n = 0; n < m && hit[n] == e->shortf[n]; ++n) {}
                if (n == m) {
                    *at = (int)(hit - text);
                    *len = m;
                    return e->full;
                }
            }
        }
    }
    return NULL;
}

/* A slot's row now holds a name typed in this session: its full name goes beside the save. */
static void names_sync(void) {
    int slot, i;
    for (slot = 1; slot <= SLOTS; ++slot) {
        const char *field = slot_field(slot);
        name_entry *e = &slot_names[slot - 1];
        if (field == NULL) return;
        for (i = 0; i < typed_count; ++i) {
            name_entry *t = &typed_names[i];
            if (field_is(field, t->shortf)) {
                if (!e->used || !s_eq(e->shortf, t->shortf) || !s_eq(e->full, t->full)) {
                    *e = *t;
                    e->used = 1;
                    write_slot_file(slot);
                }
                break;
            }
        }
    }
}

static void remember_typed(const char *shortf, const char *full) {
    int i, j;
    for (i = 0; i < typed_count && !s_eq(typed_names[i].shortf, shortf); ++i) {}
    if (i == typed_count) i = typed_count < 8 ? typed_count++ : 7;
    for (j = i; j > 0; --j) typed_names[j] = typed_names[j - 1];
    s_copy(typed_names[0].shortf, shortf, SHORT_BYTES);
    s_copy(typed_names[0].full, full, NAME_BOX_BYTES + 1);
    typed_names[0].used = 1;
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
        return utf8_drawing ? NAME_BOX_BYTES : NAME_LETTERS;
    }
    return limit;
}

/* getText(dst, size) of a text box: the game's strncpy, but at a name site the short form, the
   full name remembered for the player list. */
static void __cdecl get_text(char *wrapper, unsigned int ret, char *dst, int size) {
    char *box = *(char **)(wrapper + 0x10);
    const char *text = *(const char **)(box + 0x30);
    int i = 0;
    if (size <= 0) return;
    if (text != NULL && returns_to(ret, NAME_TEXT_RETURNS, sizeof NAME_TEXT_RETURNS / sizeof NAME_TEXT_RETURNS[0])) {
        static char full[NAME_BOX_BYTES + 1];
        char shortf[SHORT_BYTES];
        to_utf8(text, full, sizeof full);
        short_form(full, shortf, size < SHORT_BYTES ? size : SHORT_BYTES);
        for (i = 0; shortf[i] && i < size - 1; ++i) dst[i] = shortf[i];
        for (; i < size; ++i) dst[i] = '\0';
        if (full[0]) remember_typed(shortf, full);
        names_sync();
        return;
    }
    /* strncpy(dst, text, size); dst[size - 1] = 0 */
    if (text != NULL) {
        for (; i < size && text[i]; ++i) dst[i] = text[i];
    }
    for (; i < size; ++i) dst[i] = '\0';
    dst[size - 1] = '\0';
}

/* setText(text) of a text box: a player's short form (or row) becomes the full name. */
static const char *__cdecl set_text(char *box, unsigned int ret, const char *text) {
    static char shown[NAME_BOX_BYTES + 1];
    const char *full = NULL;
    int slot;
    (void)box;
    (void)ret;
    if (text == NULL) return text;
    for (slot = 1; slot <= SLOTS && full == NULL; ++slot) {
        name_entry *e = &slot_names[slot - 1];
        if (text == slot_field(slot) && e->used && field_is(text, e->shortf)) full = e->full;
    }
    if (full == NULL) full = full_for_short(text);
    if (full == NULL) return text;
    to_box_text(full, shown, sizeof shown);
    return shown;
}

#endif
