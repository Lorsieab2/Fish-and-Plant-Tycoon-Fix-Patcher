/* Extra Supply Slots -- seven more supply slots in PC Fish Tycoon ("Extra supply slots").

   WHAT.  The tank screen's four supply slots (top left: slot 1 the fish
   food, slots 2-4 medicine, chemicals and eggs) become eleven, shown in
   three pages: page 1 the stock four, page 2 four more, page 3 three more.
   Two small arrows right of slot 4 (the stock UP_ARROW art turned on its
   side, as Extra Tanks' tank arrows) turn the page, and carrying an item
   over an arrow turns it too, so it can be dropped on any slot.  The seven
   are bought together on the Supplies store's Upgrades screen (DS Store
   Items: "Extra Supply Slots", $10,000, $0 with Free upgrades); until then
   the arrows are greyed and a click on one says "You don't own the extra
   supply slots yet!" just under the top bar, where Extra Tanks says its own.

   Every extra slot is a stock slot 2-4: a record of the stock layout (0x1C
   bytes: +0 item, +4 present, +8 count, +0x0C shelf picture, +0x10 cursor,
   +0x14 x), used by the game's own code:
     * picking an item up: the record goes into the stock slot the item
       belongs to (1 medicine, 2 chemicals, 3 eggs -- the native slot of the
       stock use switch 0x420B70 and of Universal supply slots' trampoline),
       the slot's own record waits here, and the game's held-supply state
       (impl+0x1C, the cursor, the mouse capture) is set as its pick does
       (0x41E450, 0x421C9C).  Whatever the game then does with it -- every
       medicine, chemical and egg, stock or DS Store Items' (the Radioactive
       Growth Hormone, the Revival Potion, ClonaFish, Exotic Fish Eggs), the
       trash (DS Store Items' 0x421B52), a drop outside the tank -- is the
       game's own code on that record; once it is let go the record goes
       back to its extra slot (used up, a dose less, or as it was) and the
       stock slot's own record back to its place;
     * buying (the stock store's Buy, 0x428080, and DS Store Items' supplies,
       which ask FtfpSupplySlotsLend): when the stock rules would put the
       item in a full stock slot, the extra slot the item should go to is
       lent to that stock slot for the purchase -- with Universal supply
       slots a stack of the same item first, then the first free slot, over
       all eleven slots; without it, the first free extra slot when the
       item's own stock slot is full -- so the game's own purchase (its
       questions, its price, its dose counts) fills it;
     * a held supply dropped on a supply slot moves there: onto an empty
       slot it moves, onto the same item with Universal supply slots it
       stacks (the counts add), onto another item the two change places.
       Without Universal supply slots, stock slots 2-4 keep their own kind
       (a move that would put an item in another kind's stock slot is
       refused with the stock hint), and the extra slots take any one item.
   The fish food (slot 1) is never touched.

   STATE.  The save keeps its stock layout: the stock records are always in
   their places when the game saves, and the seven extra records and the
   purchase are written to
   "<Documents>\LDW\<exe name>\Fish Tycoon Fix Patcher Data\Extra Supply Slots <slot>.dat"
   (a .tmp file moved over the old one, so it is never half-written).
   Loading a slot reads it back; a file that cannot be read is set aside
   ("Extra Supply Slots <slot>.unreadable-<n>.dat"), never deleted, and the
   slots start empty and not bought.  A new game empties them.

   Every write into the game is in slot_sites.h -- all of them or none.  The
   sites other companions write too are chained: this DLL calls what was
   there before. */
#include <windows.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "slot_sites.h"

#define STATE_GLOBAL 0x0045ABDCu
#define SLOT_BASE 0x2B8
#define REC 0x1C
#define EXTRA 7                       /* page 2: four, page 3: three */
#define PAGES 3
#define POSITIONS 4

#define R_ITEM 0x00
#define R_PRESENT 0x04
#define R_COUNT 0x08
#define R_ICON 0x0C
#define R_CURSOR 0x10
#define R_X 0x14

#define S_HELD_FISH 0x1E4E8
#define S_INTRO 0x1E4F9

/* The tank screen (impl): +0 a fish, supply or ornament is being dragged, +0x08 the
   top bar's y offset, +0x1C the held supply slot (0x63 none), +0x20/+0x24 where it is
   drawn, +0x34 state, +0x38 sprites, +0x44 hints, +0x4C sounds, +0x50 the window,
   +0x54 graphics. */
#define I_YOFF 0x08
#define I_HELD 0x1C
#define I_HX 0x20
#define I_HY 0x24
#define I_STATE 0x34
#define I_SPRITES 0x38
#define I_HINTS 0x44
#define I_SOUNDS 0x4C
#define I_WINDOW 0x50
#define I_GFX 0x54
#define NONE 0x63

#define HINT_NOT_THERE 0x0D           /* the stock hint for a supply let go outside the tank (0x421680) */
#define SPR_HAND_CLOSED 0xC3          /* the cursor while something is held (0x421CD9) */

typedef int (__cdecl *new_fn)(unsigned int size);
typedef void *(__cdecl *instance_fn)(void);
typedef int (__cdecl *pressed_fn)(void);
typedef int (__cdecl *mouse_pos_fn)(int *pt);
typedef int (__fastcall *this0_fn)(void *self, void *edx);
typedef int (__fastcall *this1_fn)(void *self, void *edx, int a);
typedef int (__fastcall *this2_fn)(void *self, void *edx, int a, int b);
typedef int (__fastcall *this3_fn)(void *self, void *edx, int a, int b, int c);
typedef int (__fastcall *this4_fn)(void *self, void *edx, int a, int b, int c, int d);
typedef int (__fastcall *this6_fn)(void *self, void *edx, int a, int b, int c, int d, int e, int f);

#define GAME(T, VA) ((T)(UINT_PTR)(VA))
#define HINT GAME(this1_fn, 0x00417FA0u)               /* string n + 0x83 near the mouse */
#define SOUND_GET GAME(this1_fn, 0x004251A0u)          /* (id) -> sound */
#define SOUND_PLAY GAME(this1_fn, 0x0040AE20u)         /* (0) */
#define MOUSE_POS GAME(mouse_pos_fn, 0x00402060u)      /* (int[2]) */
#define MOUSE_INSTANCE GAME(instance_fn, 0x004021E0u)  /* the mouse */
#define MOUSE_CAPTURE GAME(this1_fn, 0x00402040u)      /* (window) */
#define SPRITE_MANAGER GAME(instance_fn, 0x0041BDD0u)  /* the sprites */
#define SPRITE_GET GAME(this1_fn, 0x0041BE70u)         /* stock sprite id -> image */
#define SET_CURSOR GAME(this3_fn, 0x00407B20u)         /* graphics (image, 1, 1) */
#define DRAW GAME(this3_fn, 0x00408A40u)               /* (img, x, y) */
#define DRAW_CELL GAME(this4_fn, 0x00408AA0u)          /* (img, x, y, frame) */
#define OPERATOR_NEW GAME(new_fn, 0x0042A793u)
#define IMAGE_NEW GAME(this1_fn, 0x00409540u)          /* (file name) */
#define GRID_NEW GAME(this3_fn, 0x004096C0u)           /* (file name, columns, rows) */
#define IMAGE_WIDTH GAME(this0_fn, 0x004095B0u)        /* an image's width (its surface's w, 0x409D00) */
#define CLOCK_SECONDS GAME(pressed_fn, 0x004020D0u)    /* the hints' clock */
#define CENTRE_TEXT GAME(this6_fn, 0x00408C30u)        /* (text, left, right, y, font, attr) */
#define HINT_FONT (*(void **)(UINT_PTR)0x0045B26Cu)
#define LANGUAGE_PTR (*(int **)(UINT_PTR)0x0045B314u)  /* 1 = German */
#define REFUSAL_RIGHT 800
#define REFUSAL_Y 70                                   /* Extra Tanks' refusal: just under the top bar */

static int *I(void *base, int offset) { return (int *)((char *)base + offset); }
static void *P(void *base, int offset) { return *(void **)((char *)base + offset); }

/* The four slot positions (0x41E450's boxes at 0x45B2A8: left, top, right, bottom) and the
   x the game draws a slot's picture at (+0x14: the food 0x19, the store's writer 0x427540
   48 * slot + 30 for slots 2-4); the picture's y is the bar's offset + 15 (0x41BED6). */
static const int BOX[POSITIONS][4] = { { 14, 9, 49, 48 }, { 63, 9, 98, 48 }, { 113, 9, 148, 48 }, { 164, 9, 199, 48 } };
static const int PICTURE_X[POSITIONS] = { 0x19, 78, 126, 174 };

/* The two arrows, one above the other, in the bar between slot 4 (x <= 199) and the first
   Magic Breeds silhouette (x >= 227, 0x41D75C): previous on top, next below. */
#define ARROW_X 204
#define ARROW_Y_LEFT 8
#define ARROW_Y_RIGHT 31
#define ARROW_W 18
#define ARROW_H 15
/* The page shown, "1/3" to "3/3" (SupplyPage1.png to SupplyPage3.png: the game's own font, small and
   in the yellow of the bar's "Magic Breeds Discovered"), centred under the arrows, between the lower
   arrow (y <= 45) and the bar's edge (y 57), clear of slot 4 and the silhouettes' label (x >= 228).
   Only once the slots are bought: before that there is one page and the grey arrows say so. */
#define PAGE_CENTRE_X (ARROW_X + ARROW_W / 2)
#define PAGE_Y 46

/* ------------------------------------------------------------ the records */

static unsigned char extra[EXTRA][REC];
static char *owner = NULL;            /* the state the extra slots belong to */
static int owned = 0;                 /* the Upgrades screen's "Extra Supply Slots" bought */
static int page = 0;                  /* 0 the stock slots, 1 extra slots 1-4, 2 extra slots 5-7 */

/* An extra slot's record in a stock slot's place: picked up (lift) or lent for a purchase
   (lend).  The stock slot's own record waits in the stash. */
static int lift_e = -1, lift_k = 0, lift_x = 0;
static char *lift_impl = NULL;
static unsigned char lift_stash[REC];
static int lend_e = -1, lend_k = 0, lend_x = 0;
static unsigned char lend_stash[REC];

static unsigned char *stock_rec(char *state, int k) { return (unsigned char *)state + SLOT_BASE + k * REC; }
static int icon(const unsigned char *r) { return *(const int *)(r + R_ICON); }
static int item(const unsigned char *r) { return *(const int *)(r + R_ITEM); }
static int ready(char *state) { return state != NULL && state == owner; }

static void swap_rec(unsigned char *a, unsigned char *b) {
    unsigned char t[REC];
    memcpy(t, a, REC);
    memcpy(a, b, REC);
    memcpy(b, t, REC);
}

/* The x the game draws stock slot k's picture at. */
static int slot_x(int k) { return k >= 0 && k < POSITIONS ? PICTURE_X[k] : 0; }

/* "Universal supply slots": its use trampoline is in (0x420B70 jumps to 0x43F550). */
static int universal(void) {
    const unsigned char *p = (const unsigned char *)(UINT_PTR)0x00420B70u;
    return p[0] == 0xE9 && *(const int *)(p + 1) == (int)(0x0043F550u - 0x00420B75u);
}

/* The stock slot an item is used from: the stock switch 0x420B70 (slot #2 medicine 0-1,
   #3 chemicals 2-4, #4 eggs 5-7), the starter eggs (26) and DS Store Items' Exotic Fish Eggs
   (28) with the eggs, its Radioactive Growth Hormone, Revival Potion and ClonaFish (29-31)
   with the chemicals (ftfp_ds_store.c). */
static int native_k(int it) {
    if (it <= 1) return 1;
    if (it <= 4) return 2;
    if (it <= 7 || it == 26 || it == 28) return 3;
    return 2;
}

static void reset_slots(char *state) {
    owner = state;
    owned = 0;
    page = 0;
    lift_e = lend_e = -1;
    lift_impl = NULL;
    memset(extra, 0, sizeof extra);
}

/* The slots as they really are, with a lifted or lent one's live record. */
static void snapshot(unsigned char out[EXTRA][REC]) {
    memcpy(out, extra, sizeof extra);
    if (owner == NULL) return;
    if (lift_e >= 0) memcpy(out[lift_e], stock_rec(owner, lift_k), REC);
    if (lend_e >= 0) memcpy(out[lend_e], stock_rec(owner, lend_k), REC);
}

/* The stock records in their places (and the lifted / lent ones in the stash), or back:
   its own inverse. */
static void stock_view_swap(void) {
    if (owner == NULL) return;
    if (lift_e >= 0) swap_rec(stock_rec(owner, lift_k), lift_stash);
    if (lend_e >= 0) swap_rec(stock_rec(owner, lend_k), lend_stash);
}

static void tidy(unsigned char *r) {
    if (icon(r) == 0) memset(r, 0, REC);
}

/* A lifted record back in its extra slot, the stock slot's own back in its place. */
static void settle_lift(void) {
    if (lift_e < 0 || owner == NULL) return;
    memcpy(extra[lift_e], stock_rec(owner, lift_k), REC);
    *I(extra[lift_e], R_X) = lift_x;                         /* its own x: only a stock slot's is drawn */
    tidy(extra[lift_e]);
    memcpy(stock_rec(owner, lift_k), lift_stash, REC);
    lift_e = -1;
    lift_impl = NULL;
}

/* Settled once nothing holds it any more (the screen reset its held supply, 0x421A52). */
static void settle_if_stale(void) {
    if (lift_e < 0) return;
    if (lift_impl == NULL || *I(lift_impl, I_HELD) != lift_k) settle_lift();
}

static void unlend(void) {
    if (lend_e < 0 || owner == NULL) return;
    memcpy(extra[lend_e], stock_rec(owner, lend_k), REC);
    *I(extra[lend_e], R_X) = lend_x;
    tidy(extra[lend_e]);
    memcpy(stock_rec(owner, lend_k), lend_stash, REC);
    lend_e = -1;
}

/* Which extra slot a purchase of `it` goes to, lent to which stock slot (0 = none: the
   stock rules alone, a stock slot takes it or the stock questions are asked).  With
   Universal supply slots (its payload 0x43F2F6, and DS Store Items' buy_universal): a
   stack of the same item in slots 2-4, else one in the extra slots, else a free slot 2-4,
   else a free extra slot -- lent to slot #2, where the search then finds it.  Without it:
   the item's own stock slot if free, else the first free extra slot, lent to that slot. */
static int lend(char *state, int it) {
    int k, e, pick = -1, at = 1;
    if (!ready(state) || !owned || lend_e >= 0) return 0;
    settle_lift();
    if (universal()) {
        for (k = 1; k <= 3; ++k) {
            if (icon(stock_rec(state, k)) != 0 && item(stock_rec(state, k)) == it) return 0;
        }
        for (e = 0; e < EXTRA && pick < 0; ++e) {
            if (icon(extra[e]) != 0 && item(extra[e]) == it) pick = e;
        }
        if (pick < 0) {
            for (k = 1; k <= 3; ++k) {
                if (icon(stock_rec(state, k)) == 0) return 0;
            }
            for (e = 0; e < EXTRA && pick < 0; ++e) {
                if (icon(extra[e]) == 0) pick = e;
            }
        }
    } else {
        at = native_k(it);
        if (icon(stock_rec(state, at)) == 0) return 0;
        for (e = 0; e < EXTRA && pick < 0; ++e) {
            if (icon(extra[e]) == 0) pick = e;
        }
    }
    if (pick < 0) return 0;
    lend_x = *I(extra[pick], R_X);
    memcpy(lend_stash, stock_rec(state, at), REC);
    memcpy(stock_rec(state, at), extra[pick], REC);
    if (icon(extra[pick]) != 0) *I(stock_rec(state, at), R_X) = slot_x(at);
    lend_e = pick;
    lend_k = at;
    return at;
}

/* ---------------------------------------------------------------- sidecar */

#define SIDECAR_MAGIC 0x53535446u      /* "FTSS" */
#define SIDECAR_VERSION 1u
#define HEADER_WORDS 6
#define SIDECAR_BYTES (HEADER_WORDS * 4 + EXTRA * REC)
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

/* "<Documents>\LDW\<exe name>\Fish Tycoon Fix Patcher Data\Extra Supply Slots <slot>.dat". */
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
    if (wcslen(out) + wcslen(name) + 90 >= cap) return 0;
    wcscat_s(out, cap, L"\\LDW\\");
    wcscat_s(out, cap, name);
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\Fish Tycoon Fix Patcher Data");
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\Extra Supply Slots ");
    {
        wchar_t digits[12];
        int i = 0, v = slot;
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 11);
        while (i) { size_t len = wcslen(out); out[len] = digits[--i]; out[len + 1] = L'\0'; }
    }
    wcscat_s(out, cap, L".dat");
    return 1;
}

/* The file's bytes: magic, version, slot count, record size, CRC-32 of the records, bought
   (0 or 1), then the seven records. */
static unsigned char file_bytes[SIDECAR_BYTES + 1];

static void pack_sidecar(unsigned char *out) {
    unsigned int *header = (unsigned int *)out;
    snapshot((unsigned char (*)[REC])(out + HEADER_WORDS * 4));
    header[0] = SIDECAR_MAGIC;
    header[1] = SIDECAR_VERSION;
    header[2] = EXTRA;
    header[3] = REC;
    header[4] = crc32(out + HEADER_WORDS * 4, EXTRA * REC);
    header[5] = (unsigned int)owned;
}

/* 1 = the bytes are a whole, intact sidecar (then the slots hold them). */
static int unpack_sidecar(const unsigned char *bytes, DWORD size) {
    const unsigned int *header = (const unsigned int *)bytes;
    if (size != SIDECAR_BYTES || header[0] != SIDECAR_MAGIC || header[1] != SIDECAR_VERSION
        || header[2] != EXTRA || header[3] != REC || header[5] > 1u
        || crc32(bytes + HEADER_WORDS * 4, EXTRA * REC) != header[4]) {
        return 0;
    }
    memcpy(extra, bytes + HEADER_WORDS * 4, sizeof extra);
    owned = (int)header[5];
    return 1;
}

static int write_sidecar(int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    DWORD written;
    int ok;
    if (!sidecar_path(slot, path, 1024, 1)) return 0;
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    pack_sidecar(file_bytes);
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    ok = WriteFile(file, file_bytes, SIDECAR_BYTES, &written, NULL) && written == SIDECAR_BYTES
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

/* A slot loaded into `state`: its extra slots from its file, else empty and not bought. */
static void read_sidecar(char *state, int slot) {
    wchar_t path[1024];
    HANDLE file;
    DWORD got = 0;
    int ok;
    reset_slots(state);
    if (!sidecar_path(slot, path, 1024, 0)) return;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;                /* no file: a slot never saved with them */
    ok = ReadFile(file, file_bytes, sizeof file_bytes, &got, NULL) && unpack_sidecar(file_bytes, got);
    CloseHandle(file);
    if (!ok) {
        reset_slots(state);
        set_aside(path);
    }
}

/* ------------------------------------------------------------ chained sites */

static UINT_PTR prev_mouse, prev_release, prev_draw, prev_tank_slots, prev_store_slots, prev_store_buy,
    prev_save_quit, prev_new_game, prev_load, prev_save;

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

/* 0 = the upper arrow (previous page), 1 = the lower one (next), -1 = neither. */
static int arrow_at(int x, int y) {
    if (inside(x, y, ARROW_X, ARROW_Y_LEFT, ARROW_X + ARROW_W - 1, ARROW_Y_LEFT + ARROW_H - 1)) return 0;
    if (inside(x, y, ARROW_X, ARROW_Y_RIGHT, ARROW_X + ARROW_W - 1, ARROW_Y_RIGHT + ARROW_H - 1)) return 1;
    return -1;
}

/* The slot position (0-3) under (x, y), -1 = none. */
static int position_at(int x, int y) {
    int p;
    for (p = 0; p < POSITIONS; ++p) {
        if (inside(x, y, BOX[p][0], BOX[p][1], BOX[p][2], BOX[p][3])) return p;
    }
    return -1;
}

/* The extra slot at position p of page pg (1 or 2), -1 = none (page 3 has three). */
static int extra_at(int pg, int p) {
    int e = (pg - 1) * POSITIONS + p;
    return pg >= 1 && p >= 0 && p < POSITIONS && e < EXTRA ? e : -1;
}

/* "You don't own the extra supply slots yet!" for 2 seconds, as Extra Tanks' refusal. */
static unsigned int locked_until = 0;

static void refuse_locked(void) { locked_until = (unsigned int)CLOCK_SECONDS() + 2u; }

static void turn_page(char *impl, int forward) {
    if (!owned) {
        refuse_locked();
        return;
    }
    page = (page + (forward ? 1 : PAGES - 1)) % PAGES;
    play_sound(impl, 1);
}

/* Carrying something over an arrow turns the page, once each time it comes onto one. */
static unsigned char over_arrow = 0, arrow_down = 0;

static void carry_over_arrow(char *impl, int x, int y) {
    int a = arrow_at(x, y);
    if (a < 0) {
        over_arrow = 0;
        return;
    }
    if (over_arrow) return;
    over_arrow = 1;
    turn_page(impl, a == 1);
}

/* Extra slot e picked up: its record into the stock slot its item is used from, held as the
   game's own pick holds a supply (0x41E545: impl+0x1C the slot, +0x20/+0x24 the mouse + 10;
   0x421C9C: the mouse captured, the drag flag, the closed hand). */
static void lift(char *impl, char *state, int e, int x, int y) {
    int k = native_k(item(extra[e]));
    void *mouse, *sprites;
    settle_lift();
    lift_x = *I(extra[e], R_X);
    memcpy(lift_stash, stock_rec(state, k), REC);
    memcpy(stock_rec(state, k), extra[e], REC);
    *I(stock_rec(state, k), R_X) = slot_x(k);
    lift_e = e;
    lift_k = k;
    lift_impl = impl;
    *I(impl, I_HELD) = k;
    *I(impl, I_HX) = x + 10;
    *I(impl, I_HY) = y + 10;
    mouse = MOUSE_INSTANCE();
    if (mouse != NULL) MOUSE_CAPTURE(mouse, NULL, *I(impl, I_WINDOW));
    *(unsigned char *)impl = 1;
    sprites = SPRITE_MANAGER();
    if (sprites != NULL) {
        int cursor = SPRITE_GET(sprites, NULL, SPR_HAND_CLOSED);
        if (cursor) SET_CURSOR(P(impl, I_GFX), NULL, cursor, 1, 1);
    }
}

/* -1 = the stock handler takes it; else handled (the stock return value). */
static int slots_mouse(char *impl, char *state, int type, int x, int y) {
    int p, e;
    settle_if_stale();
    if (*(unsigned char *)impl != 0) {                         /* dragging: the stock move and drop */
        if (type == 1) carry_over_arrow(impl, x, y);
        else over_arrow = 0;
        return -1;
    }
    over_arrow = 0;
    if (type == 2) {
        if (arrow_at(x, y) >= 0) {
            arrow_down = (unsigned char)(1 + arrow_at(x, y));
            return 0;
        }
        if (page > 0 && (p = position_at(x, y)) >= 0) {       /* an extra page: never the stock slot under it */
            e = extra_at(page, p);
            if (e >= 0 && icon(extra[e]) != 0 && *I(state, S_HELD_FISH) == -1) lift(impl, state, e, x, y);
            return 0;
        }
        return -1;
    }
    if (type == 3 && arrow_down) {
        int was = arrow_down - 1;
        arrow_down = 0;
        if (arrow_at(x, y) == was) {
            turn_page(impl, was == 1);
            return 0;
        }
    }
    return -1;
}

static char __fastcall mouse_hook(char *impl, void *edx, int type, int x, int y) {
    char *state = (char *)P(impl, I_STATE);
    int r = -1;
    (void)edx;
    if (ready(state)) {
        __try {
            r = slots_mouse(impl, state, type, x, y);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            r = -1;
        }
    }
    if (r >= 0) return (char)r;
    return (char)CALL_PREV3(prev_mouse, impl, type, x, y);
}

/* ----------------------------------------------------------------- the drop */

/* A held supply from `src` dropped on `dst` (both in their own places now).  sk / tk: the
   stock slot (1-3) each is, 0 for an extra slot.  1 = done, 0 = refused. */
static int move_supply(unsigned char *src, unsigned char *dst, int sk, int tk) {
    int empty = icon(dst) == 0;
    if (!universal()) {                                        /* stock slots keep their kind */
        if (tk && native_k(item(src)) != tk) return 0;
        if (sk && !empty && native_k(item(dst)) != sk) return 0;
    }
    if (!empty && universal() && item(src) == item(dst)) {     /* a stack, as the setting stacks a purchase */
        *I(dst, R_COUNT) += *I(src, R_COUNT);
        memset(src, 0, REC);
        return 1;
    }
    swap_rec(src, dst);
    if (tk) *I(dst, R_X) = slot_x(tk);
    if (sk && icon(src) != 0) *I(src, R_X) = slot_x(sk);
    tidy(src);
    return 1;
}

/* A held supply (slots 2-4, or an extra one lifted into them) let go on a supply slot of the
   page shown.  -1 = not ours (the stock release: the tank, the trash, the hint). */
static int slot_drop(char *impl, char *state, int x, int y) {
    int k = *I(impl, I_HELD), p, e, tk = 0, sk = 0;
    unsigned char *src, *dst;
    if (k < 1 || k > 3 || *I(state, S_HELD_FISH) != -1) return -1;
    p = position_at(x, y);
    if (p < 0) return -1;
    if (page == 0) {
        if (p == 0) return -1;                                 /* the fish food: the stock answer */
        tk = p;
        dst = stock_rec(state, p);
    } else {
        e = extra_at(page, p);
        if (e < 0) return -1;
        dst = extra[e];
    }
    if (lift_e >= 0) {
        src = extra[lift_e];
    } else {
        sk = k;
        src = stock_rec(state, k);
    }
    settle_lift();
    *I(impl, I_HELD) = NONE;
    if (src == dst) return 1;                                  /* back where it was */
    if (move_supply(src, dst, sk, tk)) play_sound(impl, 2);
    else HINT(P(impl, I_HINTS), NULL, HINT_NOT_THERE);
    return 1;
}

static char __fastcall release_hook(char *impl, void *edx, int x, int y) {
    char *state = (char *)P(impl, I_STATE);
    int r = -1;
    char result = 0;
    (void)edx;
    if (ready(state)) {
        __try {
            r = slot_drop(impl, state, x, y);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            r = -1;
        }
    }
    if (r >= 0) return 1;
    __try {
        result = (char)CALL_PREV2(prev_release, impl, x, y);
    } __finally {
        settle_if_stale();
    }
    return result;
}

/* ---------------------------------------------------------------- drawing */

static void *arrow_art[2], *unused_art, *item_art, *page_art[PAGES];

static void *grid(const char *name, int cols) {
    int obj = OPERATOR_NEW(0x34);
    return obj ? (void *)(UINT_PTR)GRID_NEW((void *)(UINT_PTR)obj, NULL, (int)(UINT_PTR)name, cols, 1) : NULL;
}

static void *image(const char *name) {
    int obj = OPERATOR_NEW(8);
    return obj ? (void *)(UINT_PTR)IMAGE_NEW((void *)(UINT_PTR)obj, NULL, (int)(UINT_PTR)name) : NULL;
}

static void load_art(void) {
    if (arrow_art[1] != NULL) return;
    arrow_art[0] = grid("SupplyArrowLeft.png", 3);          /* normal, hover, not bought */
    unused_art = image("SupplySlotUnused.png");
    page_art[0] = image("SupplyPage1.png");
    page_art[1] = image("SupplyPage2.png");
    page_art[2] = image("SupplyPage3.png");
    arrow_art[1] = grid("SupplyArrowRight.png", 3);
}

/* The pictures of the page shown: the stock slots as stock (with any lifted or lent record's
   stock slot showing its own), or the extra slots at the stock places, as 0x41BEB0 draws them
   (the held one too, as the stock slot of a held supply keeps its picture). */
static char *drawing_impl = NULL;

static void draw_extra_page(char *impl, void *sprites, int y) {
    unsigned char now[EXTRA][REC];
    void *gfx = P(impl, I_GFX);
    int p;
    snapshot(now);
    for (p = 0; p < POSITIONS; ++p) {
        int e = extra_at(page, p);
        if (e < 0) {
            load_art();
            if (unused_art != NULL) DRAW(gfx, NULL, (int)(UINT_PTR)unused_art, BOX[p][0], BOX[p][1] + *I(impl, I_YOFF));
            continue;
        }
        if (icon(now[e]) != 0) {
            void *img = (void *)(UINT_PTR)SPRITE_GET(sprites, NULL, icon(now[e]));
            if (img) DRAW(gfx, NULL, (int)(UINT_PTR)img, PICTURE_X[p], y + 15);
        }
    }
}

static int stock_slots(UINT_PTR prev, void *sprites, int y) {
    int r = 0;
    stock_view_swap();
    __try {
        r = CALL_PREV1(prev, sprites, y);
    } __finally {
        stock_view_swap();
    }
    return r;
}

static int __fastcall tank_slots_hook(void *sprites, void *edx, int y) {
    char *impl = drawing_impl;
    (void)edx;
    if (impl != NULL && ready((char *)P(impl, I_STATE)) && page > 0) {
        __try {
            draw_extra_page(impl, sprites, y);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
        }
        return 0;
    }
    return stock_slots(prev_tank_slots, sprites, y);
}

static int __fastcall store_slots_hook(void *sprites, void *edx, int y) {
    (void)edx;
    return stock_slots(prev_store_slots, sprites, y);
}

static int german(void) {
    int *lang = LANGUAGE_PTR;
    return lang != NULL && *lang == 1;
}

static void draw_arrows(char *impl) {
    void *gfx = P(impl, I_GFX);
    int pt[2], a, off = *I(impl, I_YOFF);
    load_art();
    MOUSE_POS(pt);
    for (a = 0; a < 2; ++a) {
        int frame = !owned ? 2 : arrow_at(pt[0], pt[1]) == a ? 1 : 0;
        if (arrow_art[a] == NULL) continue;
        DRAW_CELL(gfx, NULL, (int)(UINT_PTR)arrow_art[a], ARROW_X, (a ? ARROW_Y_RIGHT : ARROW_Y_LEFT) + off, frame);
    }
    if (owned && page >= 0 && page < PAGES && page_art[page] != NULL) {
        DRAW(gfx, NULL, (int)(UINT_PTR)page_art[page], PAGE_CENTRE_X - IMAGE_WIDTH(page_art[page], NULL) / 2,
             PAGE_Y + off);
    }
}

static void draw_refusal(char *impl) {
    static const char *const TEXT[2] = { "You don't own the extra supply slots yet!",
                                         "Die zus\xE4tzlichen Vorratsf\xE4" "cher geh\xF6ren dir noch nicht!" };
    if (locked_until == 0 || (unsigned int)CLOCK_SECONDS() > locked_until) {
        locked_until = 0;
        return;
    }
    CENTRE_TEXT(P(impl, I_GFX), NULL, (int)(UINT_PTR)TEXT[german()], 0, REFUSAL_RIGHT, REFUSAL_Y,
                (int)(UINT_PTR)HINT_FONT, 0);
}

static void __fastcall draw_hook(char *impl, void *edx) {
    char *state = (char *)P(impl, I_STATE);
    (void)edx;
    __try {
        if (ready(state)) settle_if_stale();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    drawing_impl = impl;
    __try {
        CALL_PREV0(prev_draw, impl);
    } __finally {
        drawing_impl = NULL;
    }
    __try {
        if (ready(state) && ((unsigned char *)state)[S_INTRO] == 0) {
            draw_arrows(impl);
            draw_refusal(impl);
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
}

/* ------------------------------------------------------- the store's Buy */

/* The stock store's Buy (0x428080, thiscall store; item): its supplies (items 0-7) may go to
   an extra slot, lent to a stock slot for the purchase (lend). */
static int __fastcall store_buy_hook(char *store, void *edx, int it) {
    char *state = (char *)P(store, 0x10);
    int lent = 0, r = 0;
    (void)edx;
    __try {
        if (it >= 0 && it <= 7) lent = lend(state, it);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        lent = 0;
    }
    __try {
        r = CALL_PREV1(prev_store_buy, store, it);
    } __finally {
        if (lent) unlend();
    }
    return r;
}

/* --------------------------------------------------------- saves and games */

/* The save gets the stock records in their places; the file gets the extra slots as they
   are (a held one with its live record). */
static int save_common(UINT_PTR prev, char *state, int slot) {
    int result = 0, ours = ready(state) && is_game_slot(slot);
    if (ours) stock_view_swap();
    __try {
        result = CALL_PREV1(prev, state, slot);
    } __finally {
        if (ours) stock_view_swap();
    }
    if (ours && (result & 0xFF) != 0) {
        __try {
            write_sidecar(slot);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
        }
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
            reset_slots(state);
        }
    }
    return result;
}

static void __fastcall new_game_hook(char *state, void *edx) {
    (void)edx;
    CALL_PREV0(prev_new_game, state);
    reset_slots(state);
}

/* ------------------------------------------------------------- the install */

static ftfp_site_write writes[SLOT_SITE_COUNT];
static unsigned char current_bytes[SLOT_SITE_COUNT][8];
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

/* A call/jmp site: its stock bytes, or the same branch into another companion (which then
   keeps working: this DLL calls it).  *prev = what it called. */
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
    ok &= BRANCH(0, MOUSE, 0xE8, mouse_hook, prev_mouse);
    ok &= BRANCH(1, RELEASE, 0xE8, release_hook, prev_release);
    ok &= BRANCH(2, DRAW, 0xE9, draw_hook, prev_draw);
    ok &= BRANCH(3, TANK_SLOTS, 0xE8, tank_slots_hook, prev_tank_slots);
    ok &= BRANCH(4, STORE_SLOTS, 0xE8, store_slots_hook, prev_store_slots);
    ok &= BRANCH(5, STORE_BUY, 0xE8, store_buy_hook, prev_store_buy);
    ok &= BRANCH(6, SAVE_QUIT, 0xE8, save_quit_hook, prev_save_quit);
    ok &= BRANCH(7, NEW_GAME, 0xE8, new_game_hook, prev_new_game);
    ok &= slot_site(&writes[8], current_bytes[8], SITE_SLOT_LOAD_VA, SITE_SLOT_LOAD_HOLDS, CODE_ADDR(load_hook), &prev_load);
    ok &= slot_site(&writes[9], current_bytes[9], SITE_SLOT_SAVE_VA, SITE_SLOT_SAVE_HOLDS, CODE_ADDR(save_slot_hook), &prev_save);
    return ok;
}

/* "<game>\Fish Tycoon Fix Patcher DLLs\Extra Supply Slots.log", as the other companions' logs. */
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
    wcscat_s(path, 1024, L"Extra Supply Slots.log");
    if (installed) {
        len = append_text(line, len, "Extra Supply Slots: installed (all sites)\r\n");
    } else if (failed_site != 0) {
        len = append_text(line, len, "Extra Supply Slots: NOT installed; the code at ");
        len = append_hex(line, len, failed_site);
        len = append_text(line, len, " is not the code this build expects\r\n");
    } else {
        len = append_text(line, len, "Extra Supply Slots: NOT installed\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* Without "3 extra tanks" the startup stub loads this DLL first, so it first loads the
   companion the stub would have loaded otherwise, from the same folder: "Multiple
   Ornaments.dll" (which loads the next ones itself), else "DS Exclusive Fish.dll" (which
   loads the Maximizable window's and DS Store Items' own), else "Maximizable Window.dll".
   After Extra Tanks they are loaded already (every FtfpStartup runs once). */
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

static unsigned int first_unwritable(void) {
    int i;
    for (i = 0; i < SLOT_SITE_COUNT; ++i) {
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
        if (prepare() && ftfp_install_sites(writes, SLOT_SITE_COUNT)) {
            installed = 1;
        } else {
            failed_site = ftfp_failed_site != 0 ? ftfp_failed_site : first_unwritable();
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    return installed;
}

/* For the patcher's tests and the patch log. */
int __stdcall FtfpSupplySlotsInstalled(void) { return installed; }

/* For DS Store Items' Upgrades screen, where the slots are bought ($10,000, $0 with Free
   upgrades): 1 bought, 0 not yet, -1 when no game is open. */
int __stdcall FtfpSupplySlotsOwned(void) {
    char *state = *(char *volatile *)(UINT_PTR)STATE_GLOBAL;
    return installed && ready(state) ? owned : -1;
}

/* Bought: 1, or -1 (no game, or bought already). */
int __stdcall FtfpSupplySlotsBuy(void) {
    char *state = *(char *volatile *)(UINT_PTR)STATE_GLOBAL;
    if (!installed || !ready(state) || owned) return -1;
    owned = 1;
    return 1;
}

/* The Upgrades screen's picture of the item (this setting's "ITEM_EXTRA_SUPPLY_SLOTS.png",
   loaded once), or NULL. */
void *__stdcall FtfpSupplySlotsImage(void) {
    if (!installed) return NULL;
    if (item_art == NULL) {
        __try {
            item_art = image("ITEM_EXTRA_SUPPLY_SLOTS.png");
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            item_art = NULL;
        }
    }
    return item_art;
}

/* For DS Store Items' own supplies (Exotic Fish Eggs, the Radioactive Growth Hormone, the
   Revival Potion, ClonaFish), bought by the same rules as the stock store's: before its
   search of slots 2-4, the extra slot a purchase of `it` goes to is lent to a stock slot
   (returned, 1-3; 0 = none, the stock slots alone), and FtfpSupplySlotsReturn puts it back
   after, whatever was bought. */
int __stdcall FtfpSupplySlotsLend(int it) {
    char *state = *(char *volatile *)(UINT_PTR)STATE_GLOBAL;
    int k = 0;
    if (!installed) return 0;
    __try {
        k = lend(state, it);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        k = 0;
    }
    return k;
}

void __stdcall FtfpSupplySlotsReturn(void) {
    if (!installed) return;
    __try {
        unlend();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
}

/* For DS Store Items' supply slot tooltips: the record slot position p (0-3) of the page shown
   shows, as it is now (a held one's own: the stock slot's while page 1 shows it, the extra slot's
   live record on pages 2-3); NULL where there is no slot (page 3's fourth place); 1 when no game
   of this DLL's is open (then the stock slot). */
const unsigned char *__stdcall FtfpSupplySlotsShown(int p) {
    static unsigned char now[EXTRA][REC];
    char *state = *(char *volatile *)(UINT_PTR)STATE_GLOBAL;
    int e;
    if (!installed || !ready(state)) return (const unsigned char *)1;
    if (p < 0 || p >= POSITIONS) return NULL;
    if (page == 0) {
        if (lift_e >= 0 && lift_k == p) return lift_stash;
        if (lend_e >= 0 && lend_k == p) return lend_stash;
        return stock_rec(state, p);
    }
    e = extra_at(page, p);
    if (e < 0) return NULL;
    snapshot(now);
    return now[e];
}

/* Extra slot e's record as it is now (0x1C bytes, the stock layout), or NULL. */
const unsigned char *__stdcall FtfpSupplySlotsRecord(int e) {
    static unsigned char now[EXTRA][REC];
    char *state = *(char *volatile *)(UINT_PTR)STATE_GLOBAL;
    if (!installed || !ready(state) || e < 0 || e >= EXTRA) return NULL;
    snapshot(now);
    return now[e];
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
