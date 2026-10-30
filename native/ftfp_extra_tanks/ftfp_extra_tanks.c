/* Extra Tanks -- three more full tanks in PC Fish Tycoon ("3 extra tanks").

   WHAT.  Tank Three, Tank Four and Tank Five: full tanks exactly like Tank
   One and Tank Two.  Fish live, age, eat, get sick, breed and give birth in
   them; chemicals, medicines, food, eggs, ornaments, magic fish and the DS
   store animals work there; fish are dragged to and from them.  They are
   reached from the tank screen's top bar: a small arrow left of the Tank One
   button pages from the stock buttons (Tank One, Tank Two, Sale Tank) to
   Tank Three, Tank Four and Tank Five and back.  Selling is untouched: only
   the Sale Tank sells, with the stock game's limits.

   HOW.  The game keeps its four tanks (Tank One, Tank Two, the Sale Tank and
   the isolation tank) as four blocks of 0x51EC bytes inside its state
   (state + 0x390 + tank * 0x51EC: 31 fish records, the ornaments and the
   rest of a tank), followed at once by the species table, so the state has
   no room for more.  This DLL keeps three more blocks of the same layout and
   lets the game's own code run on them, unchanged:
     * on screen: the extra tank's block is swapped into Tank One's place
       (and Tank One's block into the extra's), so everything the game does
       to "the tank you are looking at" -- drawing it, feeding, medicines,
       chemicals, eggs, ornaments, the trash, the isolation tank -- happens to
       the extra tank, by the game's own code;
     * every fish update: after the game's own update of its four tanks, the
       three blocks the DLL holds are swapped into the places of Tank One,
       Tank Two and the Sale Tank (an empty block in the isolation tank's)
       and the game's own update runs once more, then everything is swapped
       back.  So every extra tank ages, eats, gets sick, breeds and dies by
       the game's own update (0x41FE70), its magic fish and DS animals
       counting in their own tank, exactly as a stock tank would;
     * a fish dropped on an extra tank's button goes in with the game's own
       AddFish (0x419C50) -- the 21 or 26 fish limit is the game's -- and
       leaves its tank with the game's own REMOVE_FISH (0x418E20).
   The Sale Tank is never swapped while anything but the fish update runs,
   so selling, customers and "fish for sale" only ever see the Sale Tank.

   STATE.  The save keeps its stock layout: before every save of a game
   slot the stock blocks are put back in their own places, and the three
   extra blocks are written to
   "<Documents>\LDW\<exe name>\Fish Tycoon Fix Patcher Data\Extra Tanks <slot>.dat"
   (beside DS Fish's data, written to a .tmp file and moved over the old
   one, so it is never half-written).  Loading a slot reads it back; a file
   that cannot be read is set aside, never deleted, and the extra tanks
   start empty.  A new game empties them.

   Every write into the game is in tank_sites.h -- all of them or none.  The
   two the DS Store DLL writes too (the tank screen's update call, the
   state's Load slot) are chained: this DLL calls what was there before. */
#include <windows.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "tank_sites.h"

#define STATE_GLOBAL 0x0045ABDCu
#define FISH_BASE 0x390
#define TANK_STRIDE 0x51EC
#define SLOT_STRIDE 0x288
#define RECORDS 31
#define EXTRA 3                       /* Tank Three, Tank Four, Tank Five */
#define ANIMAL_MARK 0x41435446        /* "FTCA", its animal signature at +0x14 */
#define BODY_SEAHORSE 22
#define SEAHORSE_ITEM 0x0B            /* the store's Golden Seahorse (0x427B30's jump table, case 0) */

#define S_CURRENT_TANK 0x384
#define S_SECOND_TANK 0x230
#define S_HELD 0x1E4E8                /* the held fish's view entry, -1 = none */
#define S_INTRO 0x1E4F9               /* the tank screen draws no buttons while set (0x4216E9) */
#define S_TUTORIAL_DRAG 0x1E178
#define S_TUTORIAL_DROPS 0x1E4E4

#define F_LIVE 0x00
#define F_BODY 0x4C
#define F_MARK 0x14

/* The tank screen (impl): +0x34 state, +0x38 sprites, +0x3C view, +0x44 hints,
   +0x4C sounds, +0x54 graphics, +0x08 the buttons' y offset, +0x58/0x68/0x78
   the three tank buttons (left, top, right, bottom), +0xC8.. their pressed
   flags, byte +0 = a fish or ornament is being dragged. */
#define I_STATE 0x34
#define I_SPRITES 0x38
#define I_VIEW 0x3C
#define I_HINTS 0x44
#define I_SOUNDS 0x4C
#define I_GFX 0x54
#define I_YOFF 0x08
#define I_BUTTON 0x58
#define I_PRESSED 0xC8

/* The two arrows, one above the other, in the top bar between the Magic Breeds
   silhouettes (x <= 495) and the Tank One button (x >= 513): left (previous) on
   top, right (next) below; scripts/build_extra_tanks_assets.py ARROW_BOXES. */
#define ARROW_X 495
#define ARROW_Y_LEFT 8
#define ARROW_Y_RIGHT 31
#define ARROW_W 18
#define ARROW_H 15
#define LOGICAL 6                     /* Tank One, Tank Two, the Sale Tank, Tank Three, Four, Five */
#define NONE 0x63                     /* the tank screen's "nothing held" (+0x1C item, +0x28 ornament) */
#define I_ITEM 0x1C
#define I_ORNAMENT 0x28
#define ORN_BASE 0x5208
#define ORN_STRIDE 0x2C
#define ORN_SLOTS 6

typedef int (__cdecl *new_fn)(unsigned int size);
typedef int (__cdecl *random_fn)(int bound);
typedef int (__cdecl *format_fn)(char *out, const char *format, int value);
typedef int (__cdecl *mouse_pos_fn)(int *pt);
typedef int (__cdecl *pressed_fn)(void);
typedef int (__fastcall *this0_fn)(void *self, void *edx);
typedef int (__fastcall *this1_fn)(void *self, void *edx, int a);
typedef int (__fastcall *this2_fn)(void *self, void *edx, int a, int b);
typedef int (__fastcall *this3_fn)(void *self, void *edx, int a, int b, int c);
typedef int (__fastcall *this4_fn)(void *self, void *edx, int a, int b, int c, int d);
typedef int (__fastcall *this5_fn)(void *self, void *edx, int a, int b, int c, int d, int e);

#define GAME(T, VA) ((T)(UINT_PTR)(VA))
#define FISH_UPDATE GAME(this0_fn, 0x0041FE70u)        /* the fish update, all four tanks */
#define TANK_SWITCH GAME(this0_fn, 0x00421940u)        /* the tank screen's (re)activation */
#define ADD_FISH GAME(this2_fn, 0x00419C50u)           /* (tank, record) -> slot or -1 */
#define REMOVE_FISH GAME(this2_fn, 0x00418E20u)        /* (tank, slot) */
#define VIEW_TANK GAME(this1_fn, 0x00413B30u)          /* (entry) -> tank */
#define VIEW_SLOT GAME(this1_fn, 0x00413B50u)          /* (entry) -> slot */
#define VIEW_MOVE GAME(this4_fn, 0x00415380u)          /* (entry, tank, 1, slot) */
#define HINT GAME(this1_fn, 0x00417FA0u)               /* string n + 0x83 near the mouse */
#define SOUND_GET GAME(this1_fn, 0x004251A0u)          /* (id) -> sound */
#define SOUND_PLAY GAME(this1_fn, 0x0040AE20u)         /* (0) */
#define TUTORIAL GAME(this1_fn, 0x0041A940u)           /* (tip) */
#define MOUSE_POS GAME(mouse_pos_fn, 0x00402060u)      /* (int[2]) */
#define MOUSE_DOWN GAME(pressed_fn, 0x00402080u)
#define DRAW GAME(this3_fn, 0x00408A40u)               /* (img, x, y) */
#define DRAW_CELL GAME(this4_fn, 0x00408AA0u)          /* (img, x, y, frame) */
#define SPRITE_GRID GAME(this1_fn, 0x0041BCA0u)        /* stock sprite id -> grid image */
#define OPERATOR_NEW GAME(new_fn, 0x0042A793u)
#define IMAGE_NEW GAME(this1_fn, 0x00409540u)          /* (file name) */
#define GRID_NEW GAME(this3_fn, 0x004096C0u)           /* (file name, columns, rows) */
#define SPR_TANK1_BUTTON 0x89                          /* Tank1Button.png */
#define SPRITE_GET GAME(this1_fn, 0x0041BE70u)         /* stock sprite id -> image */
#define RANDOM GAME(random_fn, 0x00403240u)            /* the game's Random(n) */
#define CLOCK_SECONDS GAME(pressed_fn, 0x004020D0u)    /* the hints' clock (0x417FAF: shown until now + 2) */
#define DRAW_TEXT GAME(this5_fn, 0x00408B80u)          /* (text, x, y, font, attr) */
#define HINT_FONT (*(void **)(UINT_PTR)0x0045B26Cu)    /* the hints' font (0x417EB3) */
#define LANGUAGE_PTR (*(int **)(UINT_PTR)0x0045B314u)  /* 1 = German */
#define PLACE_ORNAMENT GAME(this2_fn, 0x00419C00u)     /* (tank, record) -> ornament slot or -1 */
#define LIFT_ORNAMENT GAME(this2_fn, 0x0041E980u)      /* impl (tank, slot): the ornament leaves its tank */
#define SPREAD_ORNAMENT GAME(this2_fn, 0x0041E9C0u)    /* impl (tank, slot): a new x in its new tank */
#define SETTLE_ORNAMENT GAME(this4_fn, 0x0041EA10u)    /* impl (x, y, tank, slot): falls or sits */

static int *I(void *base, int offset) { return (int *)((char *)base + offset); }
static void *P(void *base, int offset) { return *(void **)((char *)base + offset); }

/* ------------------------------------------------------------ the blocks */

/* store[e] holds extra tank e, except while extra tank e is on screen
   (shown == e): then the extra is in Tank One's place and store[e] holds
   Tank One. */
/* Each held block is followed by that tank's 5 DS store animals: DS Store
   Items keeps a tank's animals in records of its own, one set per stock place
   (FtfpStoreAnimals), never in the block, so they move with the block
   whenever a block changes places (swap_held, swap_places). */
#define ANIMAL_SLOTS 5
#define ANIMAL_BYTES (ANIMAL_SLOTS * SLOT_STRIDE)
#define HELD_BYTES (TANK_STRIDE + ANIMAL_BYTES)
static unsigned char store[EXTRA][HELD_BYTES];
static unsigned char scratch[TANK_STRIDE];
static unsigned char spare[HELD_BYTES];
static char *owner = NULL;            /* the state the extra tanks belong to */
static int shown = -1;
static int page = 0;                  /* 0: Tank One / Tank Two / Sale Tank; 1: Tank Three / Four / Five */
static int owned = 0;                 /* extra tanks bought (0-3), in order: Tank Three first */
static int selling = 0;               /* bit e: Tank Three + e has "For sale" On */

static unsigned char *block(char *state, int tank) {
    return (unsigned char *)state + FISH_BASE + tank * TANK_STRIDE;
}

static char *record(char *state, int tank, int slot) {
    return state + FISH_BASE + tank * TANK_STRIDE + slot * SLOT_STRIDE;
}

static void swap_bytes(unsigned char *a, unsigned char *b, size_t n) {
    memcpy(scratch, a, n);
    memcpy(a, b, n);
    memcpy(b, scratch, n);
}

/* DS Store Items' 5 animal records of the tank in stock place `place` (0-2),
   or NULL (no DS Store Items, or the isolation tank, which has none). */
typedef char *(__stdcall *store_animals_fn)(char *state, int tank);
typedef char *(__stdcall *store_record_fn)(char *state, int tank, int slot);
static unsigned char *place_animals(char *state, int place) {
    HMODULE store_dll = GetModuleHandleW(L"DS Store Items.dll");
    store_animals_fn fn = store_dll != NULL ? (store_animals_fn)GetProcAddress(store_dll, "FtfpStoreAnimals") : NULL;
    return fn != NULL && place >= 0 && place <= 2 ? (unsigned char *)fn(state, place) : NULL;
}

/* A held block (with its animals after it) and the block in stock place `place` (with DS
   Store Items' animals of that place) change places.  Its own inverse. */
static void swap_held(char *state, int place, unsigned char *held) {
    unsigned char *animals = place_animals(state, place);
    swap_bytes(block(state, place), held, TANK_STRIDE);
    if (animals != NULL) swap_bytes(animals, held + TANK_STRIDE, ANIMAL_BYTES);
}

/* The blocks (and animals) of two stock places change places.  Its own inverse. */
static void swap_places(char *state, int p, int q) {
    unsigned char *a = place_animals(state, p), *b = place_animals(state, q);
    swap_bytes(block(state, p), block(state, q), TANK_STRIDE);
    if (a != NULL && b != NULL) swap_bytes(a, b, ANIMAL_BYTES);
}

static int ready(char *state) { return state != NULL && state == owner; }

static void show(char *state, int e) {
    if (shown >= 0 || e < 0 || e >= EXTRA) return;
    swap_held(state, 0, store[e]);
    shown = e;
}

static void unshow(char *state) {
    if (shown < 0) return;
    swap_held(state, 0, store[shown]);
    shown = -1;
}

static void reset_extras(char *state) {
    owner = state;
    shown = -1;
    page = 0;
    owned = 0;
    selling = 0;
    memset(store, 0, sizeof store);
}

/* One more pass of the game's own fish update, over the three blocks this
   DLL holds, in the places of Tank One, Tank Two and the Sale Tank, with an
   empty isolation tank.  Everything is put back however the update ends. */
static void tick_extras(char *impl) {
    char *state = (char *)P(impl, I_STATE);
    int t;
    if (!ready(state)) return;
    for (t = 0; t < EXTRA; ++t) swap_held(state, t, store[t]);
    memset(spare, 0, sizeof spare);
    swap_held(state, 3, spare);
    __try {
        FISH_UPDATE(impl, NULL);
    } __finally {
        swap_held(state, 3, spare);
        for (t = 0; t < EXTRA; ++t) swap_held(state, t, store[t]);
    }
}

/* ---------------------------------------------------------------- sidecar */

#define SIDECAR_MAGIC 0x54585446u      /* "FTXT" */
#define SIDECAR_VERSION 4u              /* 4: each block followed by its 5 DS store animals */
#define SIDECAR_VERSION_BLOCKS 3u       /* 3: the blocks alone (animals in their records 26-30) */
typedef BOOL (WINAPI *special_folder_fn)(HWND, LPWSTR, int, BOOL);

static unsigned int crc_table[256];

static unsigned int crc32(const unsigned char *p, size_t n) {
    unsigned int c = 0xFFFFFFFFu;
    size_t i;
    if (crc_table[1] == 0) {
        unsigned int k, j;
        for (k = 0; k < 256; ++k) {
            unsigned int v = k;
            for (j = 0; j < 8; ++j) v = (v & 1) ? 0xEDB88320u ^ (v >> 1) : v >> 1;
            crc_table[k] = v;
        }
    }
    for (i = 0; i < n; ++i) c = crc_table[(c ^ p[i]) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

static int is_game_slot(int slot) {
    return slot != 0 && slot != 0xB;          /* 0 = settings, 11 = the game's own extra record */
}

/* "<Documents>\LDW\<exe name>\Fish Tycoon Fix Patcher Data\Extra Tanks <slot>.dat",
   the folder the game saves in, as DS Fish's sidecar. */
static int sidecar_path(int slot, wchar_t *out, DWORD cap, int make_folder) {
    wchar_t exe[MAX_PATH];
    wchar_t *name, *dot;
    special_folder_fn special;
    HMODULE shell = GetModuleHandleW(L"shell32.dll");
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
    if (shell == NULL) shell = LoadLibraryW(L"shell32.dll");
    if (shell == NULL || n == 0 || n >= MAX_PATH) return 0;
    special = (special_folder_fn)GetProcAddress(shell, "SHGetSpecialFolderPathW");
    if (special == NULL || !special(NULL, out, 0x0005 /* CSIDL_PERSONAL */, FALSE)) return 0;
    name = wcsrchr(exe, L'\\');
    name = name ? name + 1 : exe;
    dot = wcsrchr(name, L'.');
    if (dot) *dot = L'\0';
    if (wcslen(out) + wcslen(name) + 80 >= cap) return 0;
    wcscat_s(out, cap, L"\\LDW\\");
    wcscat_s(out, cap, name);
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\Fish Tycoon Fix Patcher Data");
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\Extra Tanks ");
    {
        wchar_t digits[12];
        int i = 0, v = slot;
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 11);
        while (i) { size_t len = wcslen(out); out[len] = digits[--i]; out[len + 1] = L'\0'; }
    }
    wcscat_s(out, cap, L".dat");
    return 1;
}

/* The file's bytes: magic, version, tank count, block size, CRC-32 of the
   blocks, the extra tanks bought (0-3), the For sale toggles (bit e for Tank
   4 + e), then the three blocks (the extra tanks, never Tank 1), each
   followed by its 5 DS store animal records (version 4). */
#define HEADER_WORDS 7
#define SIDECAR_BYTES (HEADER_WORDS * 4 + EXTRA * HELD_BYTES)
#define SIDECAR_BYTES_V3 (HEADER_WORDS * 4 + EXTRA * TANK_STRIDE)
#define ANIMAL_FIRST_V3 26            /* where a version-3 block kept its DS store animals */

static void pack_sidecar(unsigned int *header) {
    header[0] = SIDECAR_MAGIC;
    header[1] = SIDECAR_VERSION;
    header[2] = EXTRA;
    header[3] = TANK_STRIDE;
    header[4] = crc32(&store[0][0], sizeof store);
    header[5] = (unsigned int)owned;
    header[6] = (unsigned int)selling;
}

static int is_animal(char *f);

/* A version-3 block kept its animals in records 26-30, where DS Store Items
   kept them before it had records of its own: they move to the block's
   animal records (the fish records are left empty, as DS Store Items leaves
   a migrated tank). */
static void settle_v3_animals(unsigned char *held) {
    int s, k = 0;
    memset(held + TANK_STRIDE, 0, ANIMAL_BYTES);
    for (s = ANIMAL_FIRST_V3; s < RECORDS; ++s) {
        char *f = (char *)held + s * SLOT_STRIDE;
        if (!is_animal(f)) continue;
        memcpy(held + TANK_STRIDE + k * SLOT_STRIDE, f, SLOT_STRIDE);
        memset(f, 0, SLOT_STRIDE);
        ++k;
    }
}

/* 1 = the bytes are a whole, intact sidecar (then store holds them). */
static int unpack_sidecar(const unsigned char *bytes, DWORD size) {
    const unsigned int *header = (const unsigned int *)bytes;
    int e, v3 = size == SIDECAR_BYTES_V3 && header[1] == SIDECAR_VERSION_BLOCKS;
    DWORD data = v3 ? EXTRA * TANK_STRIDE : EXTRA * HELD_BYTES;
    if ((size != SIDECAR_BYTES || header[1] != SIDECAR_VERSION) && !v3) return 0;
    if (header[0] != SIDECAR_MAGIC || header[2] != EXTRA || header[3] != TANK_STRIDE
        || crc32(bytes + HEADER_WORDS * 4, data) != header[4] || header[5] > EXTRA || header[6] > 7u) {
        return 0;
    }
    if (v3) {
        for (e = 0; e < EXTRA; ++e) {
            memcpy(store[e], bytes + HEADER_WORDS * 4 + e * TANK_STRIDE, TANK_STRIDE);
            settle_v3_animals(store[e]);
        }
    } else {
        memcpy(store, bytes + HEADER_WORDS * 4, sizeof store);
    }
    owned = (int)header[5];
    selling = (int)header[6];
    return 1;
}

static int write_sidecar(int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    unsigned int header[HEADER_WORDS];
    DWORD written;
    int ok;
    if (!sidecar_path(slot, path, 1024, 1)) return 0;
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    pack_sidecar(header);
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    ok = WriteFile(file, header, sizeof header, &written, NULL) && written == sizeof header
         && WriteFile(file, store, sizeof store, &written, NULL) && written == sizeof store
         && FlushFileBuffers(file);
    CloseHandle(file);
    if (!ok || !MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        DeleteFileW(temp);
        return 0;
    }
    return 1;
}

/* Keep a file that cannot be read, never delete it. */
static void set_aside(const wchar_t *path) {
    wchar_t aside[1100];
    int n;
    for (n = 1; n < 100; ++n) {
        wchar_t suffix[32];
        int i = 0, v = n;
        wchar_t digits[4];
        wcscpy_s(aside, 1100, path);
        aside[wcslen(aside) - 4] = L'\0';                   /* drop ".dat" */
        wcscpy_s(suffix, 32, L".unreadable-");
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 3);
        while (i) { size_t len = wcslen(suffix); suffix[len] = digits[--i]; suffix[len + 1] = L'\0'; }
        wcscat_s(suffix, 32, L".dat");
        wcscat_s(aside, 1100, suffix);
        if (MoveFileExW(path, aside, 0)) return;
    }
}

static unsigned char file_bytes[SIDECAR_BYTES + 1];

/* A slot loaded into `state`: its extra tanks from its file, else empty. */
static void read_sidecar(char *state, int slot) {
    wchar_t path[1024];
    HANDLE file;
    DWORD got = 0;
    int ok = 0;
    reset_extras(state);
    if (!sidecar_path(slot, path, 1024, 0)) return;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;                /* no file: a slot never saved with them */
    ok = ReadFile(file, file_bytes, sizeof file_bytes, &got, NULL) && unpack_sidecar(file_bytes, got);
    CloseHandle(file);
    if (!ok) {
        memset(store, 0, sizeof store);
        set_aside(path);
    }
}

/* ------------------------------------------------------------ chained sites */

/* Each site's previous target: the stock one, or another companion's stub. */
static UINT_PTR prev_tick_idle, prev_tick_show, prev_release, prev_mouse, prev_draw, prev_save_quit,
    prev_new_game, prev_starter_eggs, prev_load, prev_save, prev_background, prev_decor, prev_sale_sign, prev_sale_shadow,
    prev_snail, prev_equipment, prev_bubbles, prev_bubbles_start;

#define CALL_PREV0(p, self) ((this0_fn)(p))((self), NULL)
#define CALL_PREV1(p, self, a) ((this1_fn)(p))((self), NULL, (a))
#define CALL_PREV2(p, self, a, b) ((this2_fn)(p))((self), NULL, (a), (b))
#define CALL_PREV3(p, self, a, b, c) ((this3_fn)(p))((self), NULL, (a), (b), (c))

static void play_sound(char *impl, int id) {
    void *sound = (void *)(UINT_PTR)SOUND_GET(P(impl, I_SOUNDS), NULL, id);
    if (sound) SOUND_PLAY(sound, NULL, 0);
}

static int inside(int x, int y, int left, int top, int right, int bottom) {
    return x >= left && x <= right && y >= top && y <= bottom;
}

/* 0 = the left arrow (previous), 1 = the right one (next), -1 = neither. */
static int arrow_at(int x, int y) {
    if (inside(x, y, ARROW_X, ARROW_Y_LEFT, ARROW_X + ARROW_W - 1, ARROW_Y_LEFT + ARROW_H - 1)) return 0;
    if (inside(x, y, ARROW_X, ARROW_Y_RIGHT, ARROW_X + ARROW_W - 1, ARROW_Y_RIGHT + ARROW_H - 1)) return 1;
    return -1;
}
/* The tank button (0-2) under (x, y), the stock rects; -1 = none. */
static int button_at(char *impl, int x, int y) {
    int b;
    for (b = 0; b < 3; ++b) {
        int *r = I(impl, I_BUTTON + b * 0x10);
        if (inside(x, y, r[0], r[1], r[2], r[3])) return b;
    }
    return -1;
}

/* Show extra tank e: it takes Tank One's place, and the screen opens on it
   with the game's own tank switch (as the stock buttons do). */
static void view_extra(char *impl, char *state, int e) {
    page = 1;
    if (shown == e && *I(state, S_CURRENT_TANK) == 0) return;   /* already there */
    unshow(state);
    show(state, e);
    play_sound(impl, 1);
    *I(state, S_CURRENT_TANK) = 0;
    TANK_SWITCH(impl, NULL);
}

static void clear_pressed(char *impl) {
    int k;
    for (k = 0; k < 5; ++k) ((unsigned char *)impl)[I_PRESSED + k] = 0;
}

/* --------------------------------------------------------------- the mouse */

static void refuse_locked(char *impl, int x, int y);

/* The "For sale" toggle and the tank's name, under the top bar on the left
   (the tank's own art and the stock UI are elsewhere). */
#define NAME_X 12
#define NAME_Y 62
#define TOGGLE_X 12
#define TOGGLE_Y 96
#define TOGGLE_W 150
#define TOGGLE_H 34
static unsigned char toggle_down = 0;

/* The toggle shows on an extra tank on screen (bought, or it would not be). */
static int toggle_at(char *state, int x, int y) {
    if (shown < 0 || shown >= owned || *I(state, S_CURRENT_TANK) != 0) return 0;
    return inside(x, y, TOGGLE_X, TOGGLE_Y, TOGGLE_X + TOGGLE_W - 1, TOGGLE_Y + TOGGLE_H - 1);
}

static unsigned char arrow_down = 0, extra_down[EXTRA];

/* -1 = the stock handler takes it; else handled (the stock return value). */
static int extra_mouse(char *impl, char *state, int type, int x, int y) {
    int b;
    if (*(unsigned char *)impl != 0) return -1;                 /* dragging: the stock drop */
    if (type == 2) {
        if (toggle_at(state, x, y)) {
            toggle_down = 1;
            return 0;
        }
        if (arrow_at(x, y) >= 0) {
            arrow_down = (unsigned char)(1 + arrow_at(x, y));
            return 0;
        }
        if (page == 1 && (b = button_at(impl, x, y)) >= 0) {
            extra_down[b] = 1;
            return 0;
        }
        return -1;
    }
    if (type != 3) return -1;
    if (toggle_down) {
        toggle_down = 0;
        if (toggle_at(state, x, y)) {
            selling ^= 1 << shown;
            play_sound(impl, 1);
            return 0;
        }
    }
    if (arrow_down) {
        int was = arrow_down - 1;
        arrow_down = 0;
        if (arrow_at(x, y) == was) {                             /* two pages: either arrow turns it */
            page ^= 1;
            play_sound(impl, 1);
            return 0;
        }
    }
    if (page == 1) {
        b = button_at(impl, x, y);
        if (b >= 0) {
            int was = extra_down[b];
            memset(extra_down, 0, sizeof extra_down);
            clear_pressed(impl);
            if (was && b >= owned) refuse_locked(impl, x, y);
            else if (was) view_extra(impl, state, b);
            return 0;
        }
        memset(extra_down, 0, sizeof extra_down);
        return -1;
    }
    if (shown >= 0 && (b = button_at(impl, x, y)) >= 0 && ((unsigned char *)impl)[I_PRESSED + b]) {
        if (b == 0) {                                            /* back to Tank One */
            clear_pressed(impl);
            unshow(state);
            play_sound(impl, 1);
            *I(state, S_CURRENT_TANK) = 0;
            TANK_SWITCH(impl, NULL);
            return 0;
        }
        if (b == 2 || *I(state, S_SECOND_TANK) != 0) unshow(state);   /* the stock switch follows */
    }
    return -1;
}

static char __fastcall mouse_hook(char *impl, void *edx, int type, int x, int y) {
    char *state = (char *)P(impl, I_STATE);
    int r = -1;
    (void)edx;
    if (ready(state)) {
        __try {
            r = extra_mouse(impl, state, type, x, y);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            r = -1;
        }
    }
    if (r >= 0) return (char)r;
    return (char)CALL_PREV3(prev_mouse, impl, type, x, y);
}

/* ----------------------------------------------------------------- the drop */

#define LOCKED 99                     /* a drop on an extra tank not bought yet */

/* Tanks in page order: 0 Tank One, 1 Tank Two, 2 the Sale Tank, 3-5 Tank Three,
   Four and Five.  The one on screen: */
static int on_screen(char *state) {
    int current = *I(state, S_CURRENT_TANK);
    return current == 0 && shown >= 0 ? 3 + shown : current;
}

/* Where tank L's block is now: in its stock place (*place = 0-2), or held by
   this DLL (*place = -1). */
static unsigned char *where(char *state, int tank, int *place) {
    *place = -1;
    if (tank == 0 && shown >= 0) return store[shown];
    if (tank < 3) {
        *place = tank;
        return block(state, tank);
    }
    if (shown == tank - 3) {
        *place = 0;
        return block(state, 0);
    }
    return store[tank - 3];
}

/* The tank a drop at (x, y) goes to, or -1 for the stock drop: the arrows
   move to the previous or next tank in page order (round), the buttons on
   page 1 to the extra tanks, Tank One's button to Tank One while an extra
   tank is in its place. */
static int drop_target(char *impl, char *state, int x, int y) {
    int a = arrow_at(x, y), b, t;
    if (a >= 0) {                                                /* round the tanks, past any not bought yet */
        t = on_screen(state);
        do t = (t + (a ? 1 : LOGICAL - 1)) % LOGICAL; while (t >= 3 + owned);
        return t;
    }
    b = button_at(impl, x, y);
    if (b < 0) return -1;
    if (page == 1) return b < owned ? 3 + b : LOCKED;
    if (shown >= 0 && b == 0) return 0;
    return -1;
}

static int is_animal(char *f) {
    return *I(f, F_LIVE) != 0 && *I(f, F_BODY) == BODY_SEAHORSE && *I(f, F_MARK) == ANIMAL_MARK;
}

/* A DS store animal into the first free one of a tank's 5 animal records
   (DS Store Items' for a stock place, or the ones after a held block). */
static int place_animal(unsigned char *animals, char *rec) {
    int k;
    if (animals == NULL) return -1;
    for (k = 0; k < ANIMAL_SLOTS; ++k) {
        char *f = (char *)animals + k * SLOT_STRIDE;
        if (!is_animal(f)) {
            memcpy(f, rec, SLOT_STRIDE);
            return k;
        }
    }
    return -1;
}

/* The DS store animal a swimming entry's (tank, slot) stands for (DS Store
   Items gives each one a slot number of its own, past the fish slots), or NULL. */
static char *animal_record(char *state, int tank, int slot) {
    HMODULE store_dll = GetModuleHandleW(L"DS Store Items.dll");
    store_record_fn fn = store_dll != NULL ? (store_record_fn)GetProcAddress(store_dll, "FtfpStoreAnimalRecord") : NULL;
    char *rec = fn != NULL ? fn(state, tank, slot) : NULL;
    return rec != NULL && is_animal(rec) ? rec : NULL;
}

/* The game's own AddFish into a held block: it goes into Tank One's place
   for the call (the record is a copy, so its own tank may move freely). */
static int add_into(char *state, unsigned char *dest, char *rec) {
    int slot;
    swap_held(state, 0, dest);
    slot = ADD_FISH(state, NULL, 0, (int)(UINT_PTR)rec);
    swap_held(state, 0, dest);
    return slot;
}

/* As the stock drop on a tank button (0x41EFF0): the held fish into that
   tank by the game's own AddFish, out of its own by REMOVE_FISH; "You don't
   own a second tank yet!" and "The tank is full!" as stock. */
static void move_fish(char *impl, char *state, int target) {
    void *view = P(impl, I_VIEW);                               /* as the stock code: mov ecx, [esi + 0x3C] */
    int entry = *I(state, S_HELD), tank, slot, placed, place;
    unsigned char *dest;
    char rec[SLOT_STRIDE], *animal = NULL;
    *I(state, S_HELD) = -1;
    tank = VIEW_TANK(view, NULL, entry);
    slot = VIEW_SLOT(view, NULL, entry);
    play_sound(impl, 2);
    if (*I(state, S_TUTORIAL_DRAG) == 1) {
        *I(state, S_TUTORIAL_DROPS) += 1;
        if (*I(state, S_TUTORIAL_DROPS) >= 2) TUTORIAL(state, NULL, 2);
    }
    if (tank >= 0 && tank <= 2 && (slot < 0 || slot >= RECORDS)) animal = animal_record(state, tank, slot);
    else if (tank >= 0 && tank <= 3 && slot >= 0 && slot < RECORDS && is_animal(record(state, tank, slot))) {
        animal = record(state, tank, slot);                      /* an earlier build's, not moved out yet */
    }
    if (target == on_screen(state) || tank < 0 || tank > 3 || ((slot < 0 || slot >= RECORDS) && animal == NULL)) {
        VIEW_MOVE(view, NULL, entry, tank, 1, -1);               /* back to swimming */
        return;
    }
    if (target == 1 && *I(state, S_SECOND_TANK) == 0) {
        HINT(P(impl, I_HINTS), NULL, 8);                         /* "You don't own a second tank yet!" */
        VIEW_MOVE(view, NULL, entry, tank, 1, -1);
        return;
    }
    dest = where(state, target, &place);
    memcpy(rec, animal != NULL ? animal : record(state, tank, slot), SLOT_STRIDE);
    if (animal != NULL) placed = place_animal(place >= 0 ? place_animals(state, place) : dest + TANK_STRIDE, rec);
    else if (place >= 0) placed = ADD_FISH(state, NULL, place, (int)(UINT_PTR)rec);
    else placed = add_into(state, dest, rec);
    if (placed < 0) {
        HINT(P(impl, I_HINTS), NULL, 6);                         /* "The tank is full!" */
        VIEW_MOVE(view, NULL, entry, tank, 1, -1);
        return;
    }
    if (target == 2 && *I(rec, 0x0C) < 20) TUTORIAL(state, NULL, 0x19);   /* a young fish for sale (0x41F27F) */
    REMOVE_FISH(state, NULL, tank, slot);
    if (target == 2 && *I(state, 0x1E1B4) == 1 && *I(state, 0x1E1B0) == 0) TUTORIAL(state, NULL, 0x11);
    VIEW_MOVE(view, NULL, entry, -1, 1, -1);
}

/* As the stock ornament drop on a tank button (0x41F660): the game's own
   placement into that tank (0x419C00, at most six), the ornament lifted out of
   the tank on screen (0x41E980) and given a place in its new tank (0x41E9C0,
   0x41EA10); "The tank is full!" as stock.  A held block takes the place of a
   stock tank other than the one on screen for the calls.  0 = not ours. */
static int move_ornament(char *impl, char *state, int target, int x, int y) {
    int current = *I(state, S_CURRENT_TANK), k = *I(impl, I_ORNAMENT), place, at, slot;
    unsigned char *dest, *source;
    if (k < 0 || k >= ORN_SLOTS || current < 0 || current > 2 || target == on_screen(state)) return 0;
    source = (unsigned char *)state + ORN_BASE + current * TANK_STRIDE + k * ORN_STRIDE;
    if (source[0] == 0) return 0;                                /* not a stock ornament: someone else's */
    if (target == 1 && *I(state, S_SECOND_TANK) == 0) {
        HINT(P(impl, I_HINTS), NULL, 8);
        SETTLE_ORNAMENT(impl, NULL, x, y, current, k);
        *I(impl, I_ORNAMENT) = NONE;
        return 1;
    }
    dest = where(state, target, &place);
    at = place >= 0 ? place : (current == 1 ? 2 : 1);
    if (place < 0) swap_held(state, at, dest);
    __try {
        slot = PLACE_ORNAMENT(state, NULL, at, (int)(UINT_PTR)source);
        if (slot < 0) {
            HINT(P(impl, I_HINTS), NULL, 6);
            SETTLE_ORNAMENT(impl, NULL, x, y, current, k);
        } else {
            LIFT_ORNAMENT(impl, NULL, current, k);
            SPREAD_ORNAMENT(impl, NULL, at, slot);
            SETTLE_ORNAMENT(impl, NULL, x, y, at, slot);
        }
    } __finally {
        if (place < 0) swap_held(state, at, dest);
    }
    *I(impl, I_ORNAMENT) = NONE;
    return 1;
}

/* An extra tank not bought yet: "You don't own this tank yet!" near the mouse
   for 2 seconds, as the game's own hints are shown (0x417FA0 / 0x417E90: the
   hint font at the mouse, x + 0x16), and whatever was dropped goes back as
   from a full tank. */
static unsigned int locked_until = 0;
static int locked_x, locked_y;

static void refuse_locked(char *impl, int x, int y) {
    (void)impl;
    locked_until = (unsigned int)CLOCK_SECONDS() + 2u;
    locked_x = x;
    locked_y = y;
}

static char refuse_locked_drop(char *impl, char *state, int x, int y) {
    refuse_locked(impl, x, y);
    if (*I(state, S_HELD) != -1) {
        void *view = P(impl, I_VIEW);
        int entry = *I(state, S_HELD);
        *I(state, S_HELD) = -1;
        play_sound(impl, 2);
        VIEW_MOVE(view, NULL, entry, VIEW_TANK(view, NULL, entry), 1, -1);
        return 1;
    }
    if (*I(impl, I_ITEM) == NONE && *I(impl, I_ORNAMENT) != NONE) {
        SETTLE_ORNAMENT(impl, NULL, x, y, *I(state, S_CURRENT_TANK), *I(impl, I_ORNAMENT));
        *I(impl, I_ORNAMENT) = NONE;
        return 1;
    }
    return (char)CALL_PREV2(prev_release, impl, x, y);
}

/* Multiple Ornaments' decorative copies (PR #60) move by that DLL's own drop,
   which knows the three stock buttons and asks the tank map which tank each
   shows.  A drop on an arrow, on an extra tank's button, or on Tank One's
   while an extra is on screen is handed to it as a drop on the middle of a
   stock button whose tank the map names as the target, for that call only.
   With no copy held, the stock release with nothing held does nothing. */
static int map_override_to = -1, map_override_tank = -1;

static char copy_drop(char *impl, char *state, int target) {
    int current = *I(state, S_CURRENT_TANK), to, *r;
    char result = 0;
    if (target < 3 && !(target == 0 && shown >= 0)) {
        to = target;                                             /* a stock tank in its own place */
    } else {
        to = current == 2 ? 0 : 2;                               /* any other button; Tank Two's asks if bought */
        map_override_to = to;
        map_override_tank = target;
    }
    r = I(impl, I_BUTTON + to * 0x10);
    __try {
        result = (char)CALL_PREV2(prev_release, impl, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2);
    } __finally {
        map_override_to = map_override_tank = -1;
    }
    return result;
}

static char __fastcall release_hook(char *impl, void *edx, int x, int y) {
    char *state = (char *)P(impl, I_STATE);
    int target;
    (void)edx;
    if (ready(state) && (target = drop_target(impl, state, x, y)) >= 0) {
        if (target == LOCKED) return refuse_locked_drop(impl, state, x, y);
        if (*I(state, S_HELD) != -1) {
            move_fish(impl, state, target);
            return 1;
        }
        if (*I(impl, I_ITEM) == NONE && *I(impl, I_ORNAMENT) != NONE && move_ornament(impl, state, target, x, y)) {
            return 1;
        }
        if (*I(impl, I_ITEM) == NONE && target != on_screen(state)) return copy_drop(impl, state, target);
    }
    return (char)CALL_PREV2(prev_release, impl, x, y);
}
/* ---------------------------------------------------------------- drawing */

static const char *const BUTTON_FILES[EXTRA] = { "ExtraTank1Button.png", "ExtraTank2Button.png", "ExtraTank3Button.png" };
static void *button_art[EXTRA], *arrow_right, *arrow_left, *tank1_normal;
static void *toggle_art[2][2], *name_art[2][6];                 /* [German][Off, On] / [German][tank] */
static const char *const TOGGLE_FILES[2][2] = { { "ForSaleOff.png", "ForSaleOn.png" },
                                                { "ForSaleOff_de.png", "ForSaleOn_de.png" } };
static const char *const NAME_FILES[2][6] = {
    { "TankName1.png", "TankName2.png", "TankName3.png", "TankName4.png", "TankName5.png", "TankName6.png" },
    { "TankName1_de.png", "TankName2_de.png", "TankName3_de.png", "TankName4_de.png", "TankName5_de.png",
      "TankName6_de.png" } };

static void *grid(const char *name, int cols) {
    int obj = OPERATOR_NEW(0x34);
    return obj ? (void *)(UINT_PTR)GRID_NEW((void *)(UINT_PTR)obj, NULL, (int)(UINT_PTR)name, cols, 1) : NULL;
}

static void *image(const char *name) {
    int obj = OPERATOR_NEW(8);
    return obj ? (void *)(UINT_PTR)IMAGE_NEW((void *)(UINT_PTR)obj, NULL, (int)(UINT_PTR)name) : NULL;
}

static void load_art(void) {
    int b;
    if (arrow_right != NULL) return;
    for (b = 0; b < EXTRA; ++b) button_art[b] = grid(BUTTON_FILES[b], 4);      /* normal, hover, current, locked */
    arrow_left = grid("TankArrowLeft.png", 2);
    tank1_normal = image("Tank1ButtonNormal.png");
    for (b = 0; b < 2; ++b) {
        int k;
        toggle_art[b][0] = grid(TOGGLE_FILES[b][0], 2);              /* normal, hover */
        toggle_art[b][1] = grid(TOGGLE_FILES[b][1], 2);
        for (k = 0; k < 6; ++k) name_art[b][k] = image(NAME_FILES[b][k]);
    }
    arrow_right = grid("TankArrowRight.png", 2);
}

static int german(void) {
    int *lang = LANGUAGE_PTR;
    return lang != NULL && *lang == 1;
}

/* The name of the tank on screen, and on an extra tank its For sale toggle. */
static void draw_name_and_toggle(char *impl, char *state, int *pt) {
    void *gfx = P(impl, I_GFX), *art;
    int de = german(), tank = on_screen(state);
    if (tank < 0 || tank >= LOGICAL) return;
    art = name_art[de][tank];
    if (art != NULL) DRAW(gfx, NULL, (int)(UINT_PTR)art, NAME_X, NAME_Y);
    if (!toggle_at(state, TOGGLE_X, TOGGLE_Y)) return;
    art = toggle_art[de][(selling >> shown) & 1];
    if (art != NULL) DRAW_CELL(gfx, NULL, (int)(UINT_PTR)art, TOGGLE_X, TOGGLE_Y, toggle_at(state, pt[0], pt[1]));
}

/* After the stock buttons: the arrow, and on page 1 the extra tanks'
   buttons over the stock ones (normal, hovered, or the tank on screen),
   drawn as the stock buttons are (0x42177E). */
static void draw_extras(char *impl) {
    char *state = (char *)P(impl, I_STATE);
    void *gfx = P(impl, I_GFX);
    int pt[2], b, off, current;
    if (!ready(state) || ((unsigned char *)state)[S_INTRO] != 0) return;
    load_art();
    MOUSE_POS(pt);
    off = *I(impl, I_YOFF);
    current = *I(state, S_CURRENT_TANK);
    if (arrow_left != NULL) {
        DRAW_CELL(gfx, NULL, (int)(UINT_PTR)arrow_left, ARROW_X, ARROW_Y_LEFT + off, arrow_at(pt[0], pt[1]) == 0);
    }
    if (arrow_right != NULL) {
        DRAW_CELL(gfx, NULL, (int)(UINT_PTR)arrow_right, ARROW_X, ARROW_Y_RIGHT + off, arrow_at(pt[0], pt[1]) == 1);
    }
    for (b = 0; b < 3; ++b) {
        int *r = I(impl, I_BUTTON + b * 0x10);
        int hover = inside(pt[0], pt[1], r[0], r[1], r[2], r[3]);
        int frame;
        if (page == 1) {
            if (button_art[b] == NULL) continue;
            frame = b >= owned ? 3 : shown == b && current == 0 ? 2 : hover ? (MOUSE_DOWN() & 0xFF ? 2 : 1) : 0;
            DRAW_CELL(gfx, NULL, (int)(UINT_PTR)button_art[b], r[0], r[1] + off, frame);
        } else if (b == 0 && shown >= 0) {
            /* An extra tank is on screen: Tank One is not the current tank. */
            if (tank1_normal != NULL) DRAW(gfx, NULL, (int)(UINT_PTR)tank1_normal, r[0], r[1] + off);
            if (hover) {
                void *art = (void *)(UINT_PTR)SPRITE_GRID(P(impl, I_SPRITES), NULL, SPR_TANK1_BUTTON);
                if (art) DRAW_CELL(gfx, NULL, (int)(UINT_PTR)art, r[0], r[1] + off, MOUSE_DOWN() & 0xFF ? 2 : 1);
            }
        }
    }
    draw_name_and_toggle(impl, state, pt);
}

static void draw_refusal(char *impl) {
    static const char *const TEXT[2] = { "You don't own this tank yet!", "Dieser Tank geh\xF6rt dir noch nicht!" };
    int *lang = LANGUAGE_PTR;
    if (locked_until == 0 || (unsigned int)CLOCK_SECONDS() > locked_until) {
        locked_until = 0;
        return;
    }
    DRAW_TEXT(P(impl, I_GFX), NULL, (int)(UINT_PTR)TEXT[lang != NULL && *lang == 1], locked_x + 0x16, locked_y,
              (int)(UINT_PTR)HINT_FONT, 0);
}

static void __fastcall draw_hook(char *impl, void *edx) {
    (void)edx;
    CALL_PREV0(prev_draw, impl);
    __try {
        draw_extras(impl);
        draw_refusal(impl);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
}

/* ---------------------------------------------------------------- the art */

/* Tank Three, Four and Five look like Tank One, Tank Two and the Sale Tank:
   the game draws a tank's background (0x41D140) and its own decorations
   (0x41D340) by the tank number, so while an extra tank is on screen (in Tank
   One's place) the number is lent for those two calls.  The Sale Tank's
   background asks once for its tutorial tip (0x41A940(0x1A)); that tip is held
   back for the call.  Tank Five has no "For Sale" sign: the Sale Tank's
   decorations end with it (forsale.png, sprite 4, at (620, 360), 0x41D44F)
   and the shadow under it (sprite 3 at (580, 415), 0x41D435); those two draws
   are skipped while an extra tank is drawn. */
#define S_TIP_SALE_TANK 0x1E1D8                     /* the tip flag of 0x41A940(0x1A): state + 0x1E170 + 0x1A * 4 */
static int drawing_extra = 0;
static int shown_selling(void);
static void draw_sign_on(char *impl);

/* The extra tank on screen takes the place and the number of the tank it is
   drawn as (Tank Three: Tank One's, Four: Tank Two's, Five: the Sale Tank's)
   for one draw, so every draw that picks by tank number -- and any that reads
   the tank on screen, such as the ornaments after the equipment -- draws it
   exactly as that tank.  Given back by the same swap.  0 = not lent. */
static int lend_art(char *state, int *tip) {
    if (!ready(state) || shown < 0 || *I(state, S_CURRENT_TANK) != 0) return 0;
    if (shown != 0) swap_places(state, 0, shown);
    *tip = *I(state, S_TIP_SALE_TANK);
    *I(state, S_CURRENT_TANK) = shown;                       /* Three: 0, Four: 1, Five: 2 */
    *I(state, S_TIP_SALE_TANK) = 0;
    drawing_extra = 1;
    return 1;
}

static void unlend_art(char *state, int tip) {
    drawing_extra = 0;
    *I(state, S_TIP_SALE_TANK) = tip;
    *I(state, S_CURRENT_TANK) = 0;
    if (shown != 0) swap_places(state, 0, shown);
}

static void draw_as_art(UINT_PTR prev, char *impl) {
    char *state = (char *)P(impl, I_STATE);
    int tip = 0;
    if (!lend_art(state, &tip)) {
        CALL_PREV0(prev, impl);
        return;
    }
    __try {
        CALL_PREV0(prev, impl);
    } __finally {
        unlend_art(state, tip);
    }
}

/* The snail (0x41D1B0), the Aeration System and Temperature Regulator with the
   tank's ornaments after them (0x41EE60, then 0x41D600), placed by tank number. */
static void __fastcall snail_hook(char *impl, void *edx) {
    (void)edx;
    draw_as_art(prev_snail, impl);
}

static void __fastcall equipment_hook(char *impl, void *edx) {
    (void)edx;
    draw_as_art(prev_equipment, impl);
}

/* The aerator's bubbles (impl + 0x40's object: started at 0x416B90, moved at
   0x416BB0), which rise where the tank number puts the aerator. */
static void __fastcall bubbles_hook(void *bubbles, void *edx) {
    char *state = *(char **)(UINT_PTR)STATE_GLOBAL;
    int tip = 0;
    (void)edx;
    if (!lend_art(state, &tip)) {
        CALL_PREV0(prev_bubbles, bubbles);
        return;
    }
    __try {
        CALL_PREV0(prev_bubbles, bubbles);
    } __finally {
        unlend_art(state, tip);
    }
}

static void __fastcall bubbles_start_hook(void *bubbles, void *edx, int count) {
    char *state = *(char **)(UINT_PTR)STATE_GLOBAL;
    int tip = 0;
    (void)edx;
    if (!lend_art(state, &tip)) {
        CALL_PREV1(prev_bubbles_start, bubbles, count);
        return;
    }
    __try {
        CALL_PREV1(prev_bubbles_start, bubbles, count);
    } __finally {
        unlend_art(state, tip);
    }
}

static void __fastcall background_hook(char *impl, void *edx) {
    (void)edx;
    draw_as_art(prev_background, impl);
}

static void __fastcall decor_hook(char *impl, void *edx) {
    char *state = (char *)P(impl, I_STATE);
    (void)edx;
    draw_as_art(prev_decor, impl);
    if (ready(state) && *I(state, S_CURRENT_TANK) == 0 && shown_selling() && shown != 2) draw_sign_on(impl);
}

/* The Sale Tank's sign and the shadow under it: drawn as stock, except on an extra tank. */
static int shown_selling(void) { return shown >= 0 && shown < owned && ((selling >> shown) & 1); }

static int __fastcall sale_sign_hook(void *gfx, void *edx, int image, int x, int y) {
    (void)edx;
    if (drawing_extra && !(shown == 2 && shown_selling())) return 0;   /* only Tank Five draws the Sale Tank's own */
    return CALL_PREV3(prev_sale_sign, gfx, image, x, y);
}

static int __fastcall sale_shadow_hook(void *gfx, void *edx, int image, int x, int y) {
    (void)edx;
    if (drawing_extra && !(shown == 2 && shown_selling())) return 0;   /* only Tank Five draws the Sale Tank's own */
    return CALL_PREV3(prev_sale_shadow, gfx, image, x, y);
}

/* "For sale" On on Tank Three or Four (drawn as Tank One or Two, whose
   decorations have no sign): the Sale Tank's sign and its shadow, the same
   sprites at the same places, after the decorations as on the Sale Tank. */
#define SPR_SHADOW 3
#define SPR_FOR_SALE 4
static void draw_sign_on(char *impl) {
    void *gfx = P(impl, I_GFX), *art;
    art = (void *)(UINT_PTR)SPRITE_GET(P(impl, I_SPRITES), NULL, SPR_SHADOW);
    if (art) DRAW(gfx, NULL, (int)(UINT_PTR)art, 580, 415);
    art = (void *)(UINT_PTR)SPRITE_GET(P(impl, I_SPRITES), NULL, SPR_FOR_SALE);
    if (art) DRAW(gfx, NULL, (int)(UINT_PTR)art, 620, 360);
}

/* ---------------------------------------------------------------- selling */

/* The Sale Tank sells as stock; a bought extra tank with "For sale" On sells
   too, as if it were the Sale Tank.  The game's sale code reads the Sale Tank
   at fixed addresses (state + 0xA768 + slot * 0x288), so:
     * the sale roll (0x424240, once a second, the first fish whose roll
       succeeds is sold, then a 5-second pause) runs on the Sale Tank, then
       with each selling extra tank lent the Sale Tank's place, until one
       sells: every fish gets the game's own roll, in tank order, and the sale
       itself (0x424010: price, money, "fish sold", REMOVE_FISH(2, slot), the
       pause) acts on the tank the fish is really in;
     * the customers' thoughts (0x413530: a random Sale Tank slot, 3 tries)
       look at one of the selling tanks, picked by the game's Random;
     * when the sale scene opens (0x423E00) its fish pictures and the count
       they follow (scene + 0x64: live, healthy, not a seahorse-type) cover
       every selling tank, and the crowd (adults / 3 in the formula at
       0x423F2E) counts the adults of every selling tank, but never more than
       one full tank's (the tank size), so the crowd never passes the stock
       maximum;
     * the "Fish for sale" number (0x423800: adults, healthy, not a
       seahorse-type) counts every selling tank.
   With no extra tank selling, every one of these is the stock call, as is. */
#define SCENE_STATE 0x70
#define SCENE_PAUSE 0x58
#define SCENE_COUNT 0x64
#define F_AGE 0x0C
#define F_HEALTH 0x3C
#define TANK_SIZE (*(const unsigned char *)(UINT_PTR)0x00419C74u)   /* AddFish's bound: 21, or the tank size setting's */

static UINT_PTR prev_roll, prev_thoughts, prev_crowd, prev_pictures, prev_for_sale_text;

static int selling_list(int *list) {
    int e, n = 0;
    for (e = 0; e < owned && e < EXTRA; ++e) {
        if ((selling >> e) & 1) list[n++] = e;
    }
    return n;
}

/* Extra tank e lent the Sale Tank's place, or given back (the same swap). */
static void lend(char *state, int e) {
    int place;
    unsigned char *b = where(state, 3 + e, &place);
    if (place >= 0) swap_places(state, place, 2);
    else swap_held(state, 2, b);
}

static int fish_slots(void) {
    int n = TANK_SIZE;
    return n > 0 && n <= RECORDS ? n : 21;
}

/* kind 0: the crowd's adults (live, age 20+, healthy); 1: the pictures
   (live, healthy, not a seahorse-type); 2: "Fish for sale" (adults, healthy,
   not a seahorse-type).  As the game's own loops count them. */
static int count_in(const unsigned char *b, int kind) {
    int s, n = 0;
    for (s = 0; s < fish_slots(); ++s) {
        const int *f = (const int *)(b + s * SLOT_STRIDE);
        if (f[F_LIVE / 4] == 0 || f[F_HEALTH / 4] == 0) continue;
        if (kind != 1 && f[F_AGE / 4] < 20) continue;
        if (kind != 0 && f[F_BODY / 4] == BODY_SEAHORSE) continue;
        ++n;
    }
    return n;
}

static int count_selling(char *state, int kind) {
    int list[EXTRA], n = selling_list(list), i, place, total = count_in(block(state, 2), kind);
    for (i = 0; i < n; ++i) total += count_in(where(state, 3 + list[i], &place), kind);
    return total;
}

static void __fastcall roll_hook(char *scene, void *edx, int browsing) {
    char *state = (char *)P(scene, SCENE_STATE);
    int list[EXTRA], n, i;
    (void)edx;
    n = ready(state) ? selling_list(list) : 0;
    CALL_PREV1(prev_roll, scene, browsing);
    for (i = 0; i < n && *I(scene, SCENE_PAUSE) == 0; ++i) {         /* nothing sold yet this second */
        lend(state, list[i]);
        __try {
            CALL_PREV1(prev_roll, scene, browsing);
        } __finally {
            lend(state, list[i]);
        }
    }
}

static int __fastcall thoughts_hook(char *view, void *edx) {
    char *state = (char *)P(view, 0x5DE4);
    int list[EXTRA], n, pick, result = 0;
    (void)edx;
    n = ready(state) ? selling_list(list) : 0;
    if (n == 0) return CALL_PREV0(prev_thoughts, view);
    pick = RANDOM(n + 1) - 1;                                       /* -1: the Sale Tank */
    if (pick < 0) return CALL_PREV0(prev_thoughts, view);
    lend(state, list[pick]);
    __try {
        result = CALL_PREV0(prev_thoughts, view);
    } __finally {
        lend(state, list[pick]);
    }
    return result;
}

/* The crowd (0x413C10(view, crowd)) with every selling tank's adults, at most a full tank's. */
static int __fastcall crowd_hook(void *view, void *edx, int crowd) {
    char *state = *(char **)(UINT_PTR)STATE_GLOBAL;
    int list[EXTRA], adv, own, all;
    (void)edx;
    if (ready(state) && selling_list(list) > 0) {
        adv = *I(state, 0x26C);                                      /* Advertising level (0x423F43) */
        own = count_in(block(state, 2), 0);
        all = count_selling(state, 0);
        if (all > fish_slots()) all = fish_slots();
        if (own > fish_slots()) own = fish_slots();
        crowd += 2 * adv * (all / 3 - own / 3);
    }
    return CALL_PREV1(prev_crowd, view, crowd);
}

/* The sale scene's fish pictures: drawn from scene + 0x64, set over every selling tank. */
static int __fastcall pictures_hook(char *scene, void *edx, int show) {
    char *state = (char *)P(scene, SCENE_STATE);
    int list[EXTRA];
    (void)edx;
    if (ready(state) && selling_list(list) > 0) *I(scene, SCENE_COUNT) = count_selling(state, 1);
    return CALL_PREV1(prev_pictures, scene, show);
}

/* "Fish for sale: n": the game's sprintf(buffer, "%d", n) at 0x423927. */
static int __cdecl for_sale_text_hook(char *out, const char *format, int value) {
    char *state = *(char **)(UINT_PTR)STATE_GLOBAL;
    int list[EXTRA];
    if (ready(state) && selling_list(list) > 0) value = count_selling(state, 2);
    return ((format_fn)prev_for_sale_text)(out, format, value);
}

/* ------------------------------------------------------------ the update */

static void __fastcall tick_idle_hook(char *impl, void *edx) {
    (void)edx;
    CALL_PREV0(prev_tick_idle, impl);
    tick_extras(impl);
}

static void __fastcall tick_show_hook(char *impl, void *edx) {
    (void)edx;
    CALL_PREV0(prev_tick_show, impl);
    tick_extras(impl);
}

/* --------------------------------------------------------- saves and games */

static int save_common(UINT_PTR prev, char *state, int slot) {
    int was = -1, result = 0, ours = ready(state) && is_game_slot(slot);
    if (ours) {
        was = shown;
        unshow(state);                               /* the save gets the stock tanks in their places */
    }
    __try {
        result = CALL_PREV1(prev, state, slot);
        if (ours && (result & 0xFF) != 0) write_sidecar(slot);
    } __finally {
        if (ours && was >= 0) show(state, was);
    }
    return result;
}

static int __fastcall save_slot_hook(char *state, void *edx, int slot) {
    (void)edx;
    return save_common(prev_save, state, slot);
}

static int __fastcall save_quit_hook(char *state, void *edx, int slot) {
    (void)edx;
    return save_common(prev_save_quit, state, slot);
}

static int __fastcall load_hook(char *state, void *edx, int slot) {
    int result;
    (void)edx;
    result = CALL_PREV1(prev_load, state, slot);
    if ((result & 0xFF) != 0 && is_game_slot(slot) && state != NULL) {
        __try {
            read_sidecar(state, slot);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            reset_extras(state);
        }
    }
    return result;
}

static void __fastcall new_game_hook(char *state, void *edx) {
    (void)edx;
    CALL_PREV0(prev_new_game, state);
    reset_extras(state);
}

/* The starter eggs (0x41FC90) hatch 7 when no tank has a fish, else 3.  The
   game looks at Tank One, Tank Two and the Sale Tank; the extra tanks count
   as tanks too, so a fish in one of them (or in Tank One while an extra is
   on screen) is marked for the game's own test by a stand-in "live" mark in
   an empty record of a tank not on screen, taken away again at once. */
static char *stand_in = NULL;

static int any_live(const unsigned char *b) {
    int s;
    for (s = 0; s < RECORDS; ++s) {
        if (*(const int *)(b + s * SLOT_STRIDE) != 0) return 1;
    }
    return 0;
}

static void __fastcall starter_eggs_hook(char *impl, void *edx) {
    char *state = (char *)P(impl, I_STATE);
    int t, held = 0;
    (void)edx;
    stand_in = NULL;
    if (ready(state) && !any_live(block(state, 0)) && !any_live(block(state, 1)) && !any_live(block(state, 2))) {
        for (t = 0; t < EXTRA; ++t) held |= any_live(store[t]);
        if (held) {
            int other = *I(state, S_CURRENT_TANK) == 1 ? 2 : 1;
            stand_in = record(state, other, 0);
            *I(stand_in, F_LIVE) = 1;
        }
    }
    __try {
        CALL_PREV0(prev_starter_eggs, impl);
    } __finally {
        if (stand_in != NULL) *I(stand_in, F_LIVE) = 0;
        stand_in = NULL;
    }
}

/* The Supplies store's purchase (0x427B30, thiscall store; item).  The stock
   Golden Seahorse goes into Tank One first (0x427E59); while an extra tank
   is on screen it is in Tank One's place, so Tank One is put back for the
   purchase.  With DS Store Items the seahorse goes to the tank you came from
   (its stub at 0x427E43), which is then the extra tank, as for any tank. */
static const unsigned char SEAHORSE_PLACE_STOCK[7] = { 0x8B, 0x4E, 0x10, 0x8D, 0x54, 0x24, 0x3C };
static const DWORD k_purchase_resume = SITE_PURCHASE_VA + SITE_PURCHASE_LEN;

__declspec(naked) static void purchase_stock(void) {
    __asm {
        sub esp, 0x2B4
        jmp dword ptr [k_purchase_resume]
    }
}

static char __fastcall purchase_hook(char *impl, void *edx, int item) {
    char *state = (char *)P(impl, 0x10);
    int was = -1;
    char result = 0;
    (void)edx;
    if (item == SEAHORSE_ITEM && ready(state) && shown >= 0
        && ftfp_site_holds(0x00427E43u, SEAHORSE_PLACE_STOCK, sizeof SEAHORSE_PLACE_STOCK)) {
        was = shown;
        unshow(state);
    }
    __try {
        result = (char)((this1_fn)(UINT_PTR)purchase_stock)(impl, NULL, item);
    } __finally {
        if (was >= 0) show(state, was);
    }
    return result;
}

/* ------------------------------------------------------------- the install */

static ftfp_site_write writes[TANK_SITE_COUNT];
static unsigned char current_bytes[TANK_SITE_COUNT][8];
static int installed = 0;
EXTERN_C IMAGE_DOS_HEADER __ImageBase;

/* Code in another module this process has loaded (another companion's stub). */
static int in_other_module(UINT_PTR address) {
    HMODULE module = NULL;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            (LPCWSTR)address, &module)) {
        return 0;
    }
    return module != NULL && module != GetModuleHandleW(NULL) && module != (HMODULE)&__ImageBase;
}

/* A call/jmp site: its stock bytes, or the same branch into another companion
   (which then keeps working: this DLL calls it).  *prev = what it called. */
static int branch_site(ftfp_site_write *w, unsigned char *keep, unsigned int va, const unsigned char *stock,
                       unsigned int stock_target, unsigned char opcode, const void *to, UINT_PTR *prev) {
    const unsigned char *at = (const unsigned char *)(UINT_PTR)va;
    if (ftfp_site_holds(va, stock, 5)) {
        *prev = stock_target;
    } else {
        int rel;
        UINT_PTR target;
        if (!ftfp_site_holds(va, at, 5) || at[0] != opcode) return 0;     /* readable, same kind of branch */
        memcpy(&rel, at + 1, 4);
        target = (UINT_PTR)va + 5 + (INT_PTR)rel;
        if (!in_other_module(target)) return 0;
        *prev = target;
    }
    memcpy(keep, at, 5);
    ftfp_site_branch(w, va, 5, keep, opcode, to);
    return 1;
}

static int slot_site(ftfp_site_write *w, unsigned char *keep, unsigned int va, unsigned int holds,
                     const void *to, UINT_PTR *prev) {
    UINT_PTR value;
    if (!ftfp_site_holds(va, (const unsigned char *)(UINT_PTR)va, 4)) return 0;
    value = *(const UINT_PTR *)(UINT_PTR)va;
    if (value != holds && !in_other_module(value)) return 0;
    *prev = value;
    memcpy(keep, (const void *)(UINT_PTR)va, 4);
    ftfp_site_imm32(w, va, 4, keep, 0, (unsigned int)(UINT_PTR)to);
    return 1;
}

#define CODE_ADDR(f) ((const void *)(UINT_PTR)(f))
#define BRANCH(N, NAME, OP, TO, PREV) \
    branch_site(&writes[N], current_bytes[N], SITE_##NAME##_VA, SITE_##NAME##_EXPECT, SITE_##NAME##_TARGET, OP, \
                CODE_ADDR(TO), &(PREV))

static int prepare(void) {
    int ok = 1;
    ok &= BRANCH(0, TICK_IDLE, 0xE8, tick_idle_hook, prev_tick_idle);
    ok &= BRANCH(1, TICK_SHOW, 0xE8, tick_show_hook, prev_tick_show);
    ok &= BRANCH(2, RELEASE, 0xE8, release_hook, prev_release);
    ok &= BRANCH(3, MOUSE, 0xE8, mouse_hook, prev_mouse);
    ok &= BRANCH(4, DRAW, 0xE9, draw_hook, prev_draw);
    ok &= BRANCH(5, SAVE_QUIT, 0xE8, save_quit_hook, prev_save_quit);
    ok &= BRANCH(6, NEW_GAME, 0xE8, new_game_hook, prev_new_game);
    ok &= BRANCH(7, STARTER_EGGS, 0xE8, starter_eggs_hook, prev_starter_eggs);
    /* The purchase's first instruction (6 bytes, never shared): stock only.  A jump
       to purchase_hook, which the stack then sees as called with the item. */
    ftfp_site_branch(&writes[8], SITE_PURCHASE_VA, SITE_PURCHASE_LEN, SITE_PURCHASE_EXPECT, 0xE9,
                     CODE_ADDR(purchase_hook));
    ok &= BRANCH(9, BACKGROUND, 0xE8, background_hook, prev_background);
    ok &= BRANCH(10, DECOR, 0xE8, decor_hook, prev_decor);
    ok &= BRANCH(11, SALE_SHADOW, 0xE8, sale_shadow_hook, prev_sale_shadow);
    ok &= BRANCH(12, SALE_SIGN, 0xE8, sale_sign_hook, prev_sale_sign);
    ok &= BRANCH(13, SALE_ROLL, 0xE8, roll_hook, prev_roll);
    ok &= BRANCH(14, THOUGHTS, 0xE8, thoughts_hook, prev_thoughts);
    ok &= BRANCH(15, CROWD, 0xE8, crowd_hook, prev_crowd);
    ok &= BRANCH(16, PICTURES, 0xE8, pictures_hook, prev_pictures);
    ok &= BRANCH(17, FOR_SALE_TEXT, 0xE8, for_sale_text_hook, prev_for_sale_text);
    ok &= BRANCH(18, SNAIL, 0xE8, snail_hook, prev_snail);
    ok &= BRANCH(19, EQUIPMENT, 0xE8, equipment_hook, prev_equipment);
    ok &= BRANCH(20, BUBBLES, 0xE8, bubbles_hook, prev_bubbles);
    ok &= BRANCH(21, BUBBLES_START, 0xE8, bubbles_start_hook, prev_bubbles_start);
    ok &= slot_site(&writes[22], current_bytes[22], SITE_SLOT_LOAD_VA, SITE_SLOT_LOAD_HOLDS, CODE_ADDR(load_hook), &prev_load);
    ok &= slot_site(&writes[23], current_bytes[23], SITE_SLOT_SAVE_VA, SITE_SLOT_SAVE_HOLDS, CODE_ADDR(save_slot_hook), &prev_save);
    return ok;
}

/* "<game>\Fish Tycoon Fix Patcher DLLs\Extra Tanks.log", as the other companions' logs. */
static unsigned int failed_site = 0;

static int append_text(char *out, int at, const char *s) {
    while (*s && at < 158) out[at++] = *s++;
    return at;
}

static int append_hex(char *out, int at, unsigned int value) {
    int shift;
    at = append_text(out, at, "0x");
    for (shift = 28; shift >= 0 && at < 158; shift -= 4) out[at++] = "0123456789ABCDEF"[(value >> shift) & 0xF];
    return at;
}

static void write_install_log(void) {
    wchar_t path[1024];
    char line[160];
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, path, 1024), written;
    wchar_t *slash;
    HANDLE file;
    int len = 0;
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(path) + 32 >= 1024) return;
    wcscat_s(path, 1024, L"Extra Tanks.log");
    if (installed) {
        len = append_text(line, len, "Extra Tanks: installed (all sites)\r\n");
    } else if (failed_site != 0) {
        len = append_text(line, len, "Extra Tanks: NOT installed; the code at ");
        len = append_hex(line, len, failed_site);
        len = append_text(line, len, " is not the code this build expects\r\n");
    } else {
        len = append_text(line, len, "Extra Tanks: NOT installed\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* The startup stub loads only this DLL when "3 extra tanks" is on, so this
   one first loads the companion the stub would have loaded otherwise, from
   the same folder: "Multiple Ornaments.dll" (which loads the next ones
   itself), else "DS Exclusive Fish.dll" (which loads the Maximizable window's
   and DS Store Items' own), else "Maximizable Window.dll".  They install
   first; the two sites DS Store Items shares are then chained. */
typedef int (__stdcall *startup_fn)(void);

static int load_companion(const wchar_t *name) {
    wchar_t path[1024];
    wchar_t *slash;
    HMODULE module;
    startup_fn startup;
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, path, 1024);
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return 0;
    slash[1] = L'\0';
    if (wcslen(path) + wcslen(name) + 1 >= 1024) return 0;
    wcscat_s(path, 1024, name);
    if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return 0;
    module = LoadLibraryW(path);
    if (module == NULL) return 0;
    startup = (startup_fn)GetProcAddress(module, "FtfpStartup");
    if (startup != NULL) startup();
    return 1;
}

/* "Multiple Ornaments.dll" keeps decorative ornament copies per tank (0-7); it
   asks which tank a stock tank shows.  Tank One's place shows Tank Three, Four
   or Five while one is on screen. */
typedef int (__cdecl *tank_map_fn)(int stock_tank);
typedef void (__stdcall *set_tank_map_fn)(tank_map_fn map);

static int __cdecl ornaments_tank_map(int stock_tank) {
    if (drawing_extra && shown >= 0 && stock_tank == shown) return 3 + shown;   /* lent for a draw */
    if (stock_tank == map_override_to && map_override_tank >= 0) return map_override_tank;
    if (stock_tank == 0 && shown >= 0) return 3 + shown;
    return stock_tank;
}

static void tell_ornaments(void) {
    HMODULE module = GetModuleHandleW(L"Multiple Ornaments.dll");
    set_tank_map_fn set;
    if (module == NULL) return;
    set = (set_tank_map_fn)GetProcAddress(module, "FtfpOrnamentsSetTankMap");
    if (set != NULL) set(ornaments_tank_map);
}

static unsigned int first_unwritable(void) {
    int i;
    for (i = 0; i < TANK_SITE_COUNT; ++i) {
        if (writes[i].length <= 0 || !ftfp_site_holds(writes[i].va, writes[i].expect, writes[i].length)) {
            return writes[i].va;
        }
    }
    return 0;
}

/* Called once by the executable's startup stub, before WinMain. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        if (!load_companion(L"Multiple Ornaments.dll") && !load_companion(L"DS Exclusive Fish.dll")) {
            load_companion(L"Maximizable Window.dll");
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    __try {
        memset(writes, 0, sizeof writes);
        if (prepare() && ftfp_install_sites(writes, TANK_SITE_COUNT)) {
            installed = 1;
        } else {
            failed_site = ftfp_failed_site != 0 ? ftfp_failed_site : first_unwritable();
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    if (installed) tell_ornaments();
    write_install_log();
    return installed;
}

/* For the patcher's tests and the patch log. */
int __stdcall FtfpExtraTanksInstalled(void) { return installed; }

/* For DS Store Items' Upgrades screen, where the extra tanks are bought
   ($10,000 each, $0 with Free upgrades), in order: how many the game open now
   has (0-3), or -1 when none is open. */
int __stdcall FtfpExtraTanksOwned(void) {
    char *state = *(char *volatile *)(UINT_PTR)STATE_GLOBAL;
    return installed && ready(state) ? owned : -1;
}

/* One more bought: Tank Three, then Four, then Five.  The new count, or -1. */
int __stdcall FtfpExtraTanksBuy(void) {
    char *state = *(char *volatile *)(UINT_PTR)STATE_GLOBAL;
    if (!installed || !ready(state) || owned >= EXTRA) return -1;
    return ++owned;
}

/* For DS Store Items (one of each animal, unless Buy Multiple Golden Seahorses
   is on): held block e (0-2) with its 5 animal records after it -- a tank not in
   a stock place now (Tank 4-6, or Tank 1 while one of them is on screen) -- or
   NULL when no game is open. */
unsigned char *__stdcall FtfpExtraTanksHeld(int e) {
    char *state = *(char *volatile *)(UINT_PTR)STATE_GLOBAL;
    if (!installed || !ready(state) || e < 0 || e >= EXTRA) return NULL;
    return store[e];
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
