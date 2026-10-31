/* Multiple Ornaments -- buy more than one of each tank ornament in PC Fish Tycoon.

   WHAT.  The six store ornaments (Shell, Pagoda, Diver, Fancy Coral, Sunken
   Antique Column, Sunken Ship) can be bought again once owned, at their stock
   price.  Every extra copy is decoration only: it is drawn, falls to the
   gravel, is picked up, dragged, dropped and moved to another tank's button
   exactly as an ornament is, and it can be thrown in the trash can (the stock
   game never lets an ornament go).  Up to MAX_COPIES copies per tank.

   EFFECT.  The stock game's only ornament effect is the store-item ownership
   dword (state + item * 20 + 0x78, items 16-21): the selling scene adds it to
   its customer count (0x423EFC-0x423F23) and the customers' "?" thought counts
   it (0x413659-0x41369D).  Nothing reads the ornament records for an effect.
   A copy never touches that dword, so a copy changes no number anywhere, and
   the original keeps its effect however many copies come and go.

   HOW.  "Multiple Ornaments.dll" is loaded by the executable's startup stub
   (it then loads "DS Exclusive Fish.dll" or "Maximizable Window.dll" when
   they are there).  Every write into the game is in orn_sites.h -- all of
   them or none.  The copies are not in the save: each tank's copies are kept
   here and in "<save folder>\Fish Tycoon Fix Patcher Data\Ornaments <slot>.dat".

   The copies run on the game's own ornament code.  A tank's ornaments are six
   0x2C-byte records at state + 0x5208 + tank * 0x51EC; for each stock pass
   (draw 0x41D600, fall 0x41DB00, pick 0x41E570, drag 0x41E600, drop finish
   0x41EA10, random place 0x41E9C0) this DLL puts up to six copies in those
   records, runs the stock function, takes the copies back and puts the
   originals back byte for byte (swap_in / swap_out).  So a copy is drawn and
   moves exactly as an original, by construction.  The game is single
   threaded and nothing else runs during a pass. */
#include <windows.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "orn_sites.h"

#define STATE_GLOBAL 0x0045ABDCu
#define TANK_STRIDE 0x51EC
#define ORN_BASE 0x5208
#define ORN_STRIDE 0x2C
#define ORN_SLOTS 6
#define ORN_BYTES (ORN_SLOTS * ORN_STRIDE)

#define O_ACTIVE 0x00               /* byte */
#define O_X 0x04
#define O_Y 0x08
#define O_FALL_SPEED 0x10           /* non-zero while it falls */
#define O_H 0x1C
#define O_W 0x20
#define O_SPRITE 0x24

#define NO_ORNAMENT 0x63            /* the tank scene's held-ornament index when none is held */
#define SCENE_HELD 0x28
#define SCENE_STATE 0x34
#define SCENE_HINTS 0x44
#define SCENE_DIALOG_PARENT 0x50
#define SCENE_TRASH 0x88            /* left, top, right, bottom */
#define SCENE_TANK_BUTTONS 0x58     /* three rectangles of four ints: Tank One, Tank Two, the selling tank */

#define STORE_ITEM 0x00
#define STORE_HINTS 0x0C
#define STORE_STATE 0x10
#define STORE_SPRITES 0x14
#define STORE_DIALOG_PARENT 0x20

#define S_SPENT 0x24
#define S_SECOND_TANK 0x230
#define S_CURRENT_TANK 0x384
#define S_MONEY 0x38C
#define S_REGISTERED 0x1E50C        /* byte: 0 in the unregistered trial */
#define ITEM_PRICE(item) ((item) * 20 + 0x74)
#define ITEM_OWNED(item) ((item) * 20 + 0x78)
#define TRIAL_ITEMS 0x00428248u     /* byte per store item: 1 = sold in the trial too */

#define FIRST_ORNAMENT 16
#define LAST_ORNAMENT 21
/* Store item 16-21 -> its sprite: Shell, Pagoda, Diver, Fancy Coral, Sunken Antique Column, Sunken Ship
   (the purchase switch at 0x427BAE: 0xB1, 0xB2, 0xB3, 0xB5, 0xB4, 0xB6). */
static const int ORNAMENT_SPRITE[6] = { 177, 178, 179, 181, 180, 182 };

#define MAX_COPIES 10               /* decorative copies per tank */
#define LOGICAL_TANKS 8             /* 0-2 the stock tanks; room for the Extra Tanks setting's */

#define HINT_NO_MONEY 2
#define HINT_TANK_FULL 6
#define HINT_NO_SECOND_TANK 8
#define STRING_BUY 0xEC             /* "Buy this item?" */
#define STRING_DELETE 0xAC          /* the trash can's question, as for the DS eel's rock */
#define SOUND_TRASH 4
#define SOUND_MOVED 0xC
#define SOUND_BOUGHT 0xE

/* ------------------------------------------------------------ the game */

typedef int (__fastcall *this0_fn)(void *self, void *edx);
typedef int (__fastcall *this1_fn)(void *self, void *edx, int a);
typedef int (__fastcall *this2_fn)(void *self, void *edx, int a, int b);
typedef int (__fastcall *this4_fn)(void *self, void *edx, int a, int b, int c, int d);
typedef void *(__cdecl *getter_fn)(void);

/* Everything this DLL calls in the game, so the logic harness can stand in for it. */
typedef struct game_api {
    this0_fn draw_ornaments;    /* 0x41D600 (scene) */
    this0_fn fall;              /* 0x41DB00 (scene) */
    this2_fn pick;              /* 0x41E570 (scene; x, y) -> al */
    this2_fn drag;              /* 0x41E600 (scene; x, y) */
    this2_fn place_random;      /* 0x41E9C0 (scene; tank, k): a random x, as after a move */
    this4_fn settle;            /* 0x41EA10 (scene; x, y, tank, k): falls, or rests in the gravel */
    this1_fn hint;              /* 0x417FA0 (hints; n) */
    this1_fn sprite_get;        /* 0x41BE70 (sprites; id) -> image */
    this0_fn image_h;           /* 0x4095C0 (image) */
    this0_fn image_w;           /* 0x4095B0 (image) */
    int (*confirm)(void *parent, int string_id);
    void (*sound)(int id);
} game_api;

#define GAME(T, VA) ((T)(UINT_PTR)(VA))

static int *I(void *base, int offset) { return (int *)((char *)base + offset); }
static void *P(void *base, int offset) { return *(void **)((char *)base + offset); }

#ifndef FTFP_ORN_HARNESS
#define DIALOG_INIT GAME(this2_fn, 0x004221A0u)        /* (string id, 1) */
#define DIALOG_RUN GAME(this2_fn, 0x00401D00u)         /* (parent, 0) -> 0 = Yes */
#define DIALOG_FREE GAME(this0_fn, 0x00422440u)
#define SOUND_MANAGER GAME(getter_fn, 0x00425120u)
#define SOUND_GET GAME(this1_fn, 0x004251A0u)
#define SOUND_PLAY GAME(this1_fn, 0x0040AE20u)

static int game_confirm(void *parent, int string_id) {
    char dialog[0x400];
    int answer;
    DIALOG_INIT(dialog, NULL, string_id, 1);
    answer = DIALOG_RUN(dialog, NULL, (int)(UINT_PTR)parent, 0);
    DIALOG_FREE(dialog, NULL);
    return answer == 0;
}

static void game_sound(int id) {
    void *sound = (void *)(UINT_PTR)SOUND_GET(SOUND_MANAGER(), NULL, id);
    if (sound) SOUND_PLAY(sound, NULL, 0);
}

static game_api api = {
    GAME(this0_fn, 0x0041D600u), GAME(this0_fn, 0x0041DB00u), GAME(this2_fn, 0x0041E570u),
    GAME(this2_fn, 0x0041E600u), GAME(this2_fn, 0x0041E9C0u), GAME(this4_fn, 0x0041EA10u),
    GAME(this1_fn, 0x00417FA0u), GAME(this1_fn, 0x0041BE70u), GAME(this0_fn, 0x004095C0u),
    GAME(this0_fn, 0x004095B0u), game_confirm, game_sound,
};

static int trial_item(int item) { return ((const unsigned char *)(UINT_PTR)TRIAL_ITEMS)[item] != 0; }
#else
static game_api api;
static int trial_item(int item);
int harness_sidecar_path(int slot, wchar_t *out, DWORD cap, int make_folder);
#endif

/* ------------------------------------------------------------ the copies */

static unsigned char copies[LOGICAL_TANKS][MAX_COPIES][ORN_STRIDE];
static int copy_count[LOGICAL_TANKS];
static int held_tank = -1, held_copy = -1;     /* the copy being dragged */

/* The Extra Tanks setting (or anything else that shows another tank in a stock
   tank's place) names the tank on show: stock tank 0-2 -> its logical tank,
   0-7, or -1 for none.  Without it, the stock tanks are tanks 0-2. */
typedef int (__cdecl *tank_map_fn)(int stock_tank);
static tank_map_fn tank_map = NULL;

static int logical_tank(int stock_tank) {
    int t;
    if (stock_tank < 0 || stock_tank > 2) return -1;
    t = tank_map != NULL ? tank_map(stock_tank) : stock_tank;
    return t >= 0 && t < LOGICAL_TANKS ? t : -1;
}

static int is_ornament_sprite(int sprite) {
    int i;
    for (i = 0; i < 6; ++i) {
        if (ORNAMENT_SPRITE[i] == sprite) return 1;
    }
    return 0;
}

/* A copy as the store makes an ornament (0x427BB5): active, at (200, 250),
   falling, the art's size, its sprite. */
static void make_copy(unsigned char *rec, int sprite, int w, int h) {
    memset(rec, 0, ORN_STRIDE);
    rec[O_ACTIVE] = 1;
    *I(rec, O_X) = 200;
    *I(rec, O_Y) = 250;
    *I(rec, O_FALL_SPEED) = 1;
    *I(rec, O_H) = h;
    *I(rec, O_W) = w;
    *I(rec, O_SPRITE) = sprite;
}

static int add_copy(int tank, const unsigned char *rec) {
    if (tank < 0 || tank >= LOGICAL_TANKS || copy_count[tank] >= MAX_COPIES) return -1;
    memcpy(copies[tank][copy_count[tank]], rec, ORN_STRIDE);
    return copy_count[tank]++;
}

static void remove_copy(int tank, int k) {
    if (tank < 0 || tank >= LOGICAL_TANKS || k < 0 || k >= copy_count[tank]) return;
    memmove(copies[tank][k], copies[tank][k + 1], (size_t)(copy_count[tank] - k - 1) * ORN_STRIDE);
    --copy_count[tank];
    memset(copies[tank][copy_count[tank]], 0, ORN_STRIDE);
    if (held_tank == tank) {
        if (held_copy == k) held_tank = held_copy = -1;
        else if (held_copy > k) --held_copy;
    }
}

static void clear_copies(void) {
    memset(copies, 0, sizeof copies);
    memset(copy_count, 0, sizeof copy_count);
    held_tank = held_copy = -1;
}

/* --------------------------------------------- the copies in the stock records */

static unsigned char saved_records[ORN_BYTES];
static int saved_held;

static unsigned char *tank_records(char *state, int stock_tank) {
    return (unsigned char *)state + ORN_BASE + stock_tank * TANK_STRIDE;
}

/* Puts copies first.. (up to six) of a tank in the stock tank's six ornament
   records, the originals aside, and the held index on the held copy if it is
   among them.  Returns how many copies went in. */
static int swap_in(char *impl, char *state, int stock_tank, int tank, int first) {
    unsigned char *r = tank_records(state, stock_tank);
    int n = copy_count[tank] - first;
    if (n > ORN_SLOTS) n = ORN_SLOTS;
    if (n < 0) n = 0;
    memcpy(saved_records, r, ORN_BYTES);
    memset(r, 0, ORN_BYTES);
    memcpy(r, copies[tank][first], (size_t)n * ORN_STRIDE);
    saved_held = *I(impl, SCENE_HELD);
    *I(impl, SCENE_HELD) = held_tank == tank && held_copy >= first && held_copy < first + n
                               ? held_copy - first : NO_ORNAMENT;
    return n;
}

/* Takes the copies back as the stock code left them and restores the originals. */
static void swap_out(char *impl, char *state, int stock_tank, int tank, int first, int n) {
    unsigned char *r = tank_records(state, stock_tank);
    memcpy(copies[tank][first], r, (size_t)n * ORN_STRIDE);
    memcpy(r, saved_records, ORN_BYTES);
    *I(impl, SCENE_HELD) = saved_held;
}

/* The tank on show, its logical tank, or -1; forgets a held copy of another tank. */
static int shown_tank(char *impl, char **state_out, int *stock_out) {
    char *state = (char *)P(impl, SCENE_STATE);
    int stock, tank;
    if (state == NULL) return -1;
    stock = *I(state, S_CURRENT_TANK);
    tank = logical_tank(stock);
    if (tank < 0) return -1;
    if (held_tank >= 0 && held_tank != tank) held_tank = held_copy = -1;
    *state_out = state;
    *stock_out = stock;
    return tank;
}

/* One stock pass over every copy of the tank on show, six at a time. */
static void each_batch(char *impl, this0_fn pass) {
    char *state;
    int stock, tank = shown_tank(impl, &state, &stock), first, n;
    if (tank < 0) return;
    for (first = 0; first < copy_count[tank]; first += ORN_SLOTS) {
        n = swap_in(impl, state, stock, tank, first);
        pass(impl, NULL);
        swap_out(impl, state, stock, tank, first, n);
    }
}

/* After the stock decor pass (which ends with the originals): the copies, on top. */
static void __cdecl draw_copies(char *impl) { each_batch(impl, api.draw_ornaments); }

/* After the stock ornament fall: the copies fall the same way. */
static void __cdecl fall_copies(char *impl) { each_batch(impl, api.fall); }

/* A press in the tank, before the stock ornament pick: the top copy under it is
   picked up as the stock pick picks an ornament.  1 = picked. */
static int __cdecl pick_copy(char *impl, int x, int y) {
    char *state;
    int stock, tank = shown_tank(impl, &state, &stock), first, n, hit, k;
    if (tank < 0 || copy_count[tank] == 0) return 0;
    held_tank = held_copy = -1;
    for (first = (copy_count[tank] - 1) / ORN_SLOTS * ORN_SLOTS; first >= 0; first -= ORN_SLOTS) {
        n = swap_in(impl, state, stock, tank, first);
        hit = api.pick(impl, NULL, x, y) & 0xFF;
        k = *I(impl, SCENE_HELD);
        swap_out(impl, state, stock, tank, first, n);
        if (hit && k >= 0 && k < n) {
            held_tank = tank;
            held_copy = first + k;
            return 1;
        }
    }
    return 0;
}

/* The mouse moving with a copy held: the stock drag moves it.  1 = handled. */
static int __cdecl drag_copy(char *impl, int x, int y) {
    char *state;
    int stock, tank = shown_tank(impl, &state, &stock), first, n;
    if (tank < 0 || held_tank != tank) return 0;
    first = held_copy / ORN_SLOTS * ORN_SLOTS;
    n = swap_in(impl, state, stock, tank, first);
    api.drag(impl, NULL, x, y);
    swap_out(impl, state, stock, tank, first, n);
    return 1;
}

static int inside(int x, int y, const int *rect) {
    return x >= rect[0] && x <= rect[2] && y >= rect[1] && y <= rect[3];
}

/* The stock finish of a drop (0x41EA10) on copy k of a tank shown as stock_tank,
   after the stock random place (0x41E9C0) when it moved there. */
static void settle_copy(char *impl, char *state, int stock_tank, int tank, int k, int x, int y, int moved) {
    int first = k / ORN_SLOTS * ORN_SLOTS;
    int n = swap_in(impl, state, stock_tank, tank, first);
    if (moved) api.place_random(impl, NULL, stock_tank, k - first);
    api.settle(impl, NULL, x, y, stock_tank, k - first);
    swap_out(impl, state, stock_tank, tank, first, n);
}

/* The release with a copy held, as the stock ornament drop (0x41F660): onto
   another tank's button it moves there (the Second Tank must be bought; "The
   tank is full!" when it has no room), else it falls or rests where it is let
   go.  The trash can throws it away, after the game's own question.  1 = handled. */
static int __cdecl drop_copy(char *impl, int x, int y) {
    char *state;
    int stock, tank = shown_tank(impl, &state, &stock), k, to, dest;
    if (tank < 0 || held_tank != tank) {
        held_tank = held_copy = -1;
        return 0;
    }
    k = held_copy;
    held_tank = held_copy = -1;
    if (inside(x, y, I(impl, SCENE_TRASH)) && api.confirm(P(impl, SCENE_DIALOG_PARENT), STRING_DELETE)) {
        remove_copy(tank, k);
        api.sound(SOUND_TRASH);
        return 1;
    }
    for (to = 0; to <= 2; ++to) {
        if (to == stock || !inside(x, y, I(impl, SCENE_TANK_BUTTONS + to * 0x10))) continue;
        if (to == 1 && *I(state, S_SECOND_TANK) == 0) {
            api.hint(P(impl, SCENE_HINTS), NULL, HINT_NO_SECOND_TANK);
            break;
        }
        dest = logical_tank(to);
        if (dest < 0 || copy_count[dest] >= MAX_COPIES) {
            api.hint(P(impl, SCENE_HINTS), NULL, HINT_TANK_FULL);
            break;
        }
        {
            unsigned char rec[ORN_STRIDE];
            int at;
            memcpy(rec, copies[tank][k], ORN_STRIDE);
            remove_copy(tank, k);
            at = add_copy(dest, rec);
            api.sound(SOUND_MOVED);
            settle_copy(impl, state, to, dest, at, x, y, 1);
        }
        return 1;
    }
    settle_copy(impl, state, stock, tank, k, x, y, 0);
    return 1;
}

/* ------------------------------------------------------------ the store */

/* Everything is Free ("Everything Free.ini" beside this DLL, read at start-up):
   a copy costs $0, as the stock purchase does with that setting's patches. */
static int everything_free = 0;

/* Buy on an owned ornament: a decorative copy for the tank you came from, at
   the item's price.  The ownership dword is never touched.  0 = not this
   DLL's (the stock click goes on), 1 = handled. */
static int __cdecl store_click(char *store, int item) {
    char *state = (char *)P(store, STORE_STATE);
    unsigned char rec[ORN_STRIDE];
    void *image;
    int price, tank, sprite;
    if (state == NULL || item < FIRST_ORNAMENT || item > LAST_ORNAMENT) return 0;
    if (*I(state, ITEM_OWNED(item)) == 0) return 0;                 /* the first one: the stock purchase */
    if (*(unsigned char *)(state + S_REGISTERED) == 0 && !trial_item(item)) return 0;
    price = everything_free ? 0 : *I(state, ITEM_PRICE(item));
    if (price > *I(state, S_MONEY)) {
        api.hint(P(store, STORE_HINTS), NULL, HINT_NO_MONEY);
        return 1;
    }
    tank = logical_tank(*I(state, S_CURRENT_TANK));
    if (tank < 0 || copy_count[tank] >= MAX_COPIES) {
        api.hint(P(store, STORE_HINTS), NULL, HINT_TANK_FULL);
        return 1;
    }
    if (!api.confirm(P(store, STORE_DIALOG_PARENT), STRING_BUY)) return 1;
    sprite = ORNAMENT_SPRITE[item - FIRST_ORNAMENT];
    image = (void *)(UINT_PTR)api.sprite_get(P(store, STORE_SPRITES), NULL, sprite);
    make_copy(rec, sprite, image ? api.image_w(image, NULL) : 0, image ? api.image_h(image, NULL) : 0);
    *I(state, S_MONEY) -= price;
    *I(state, S_SPENT) += price;
    add_copy(tank, rec);
    api.sound(SOUND_BOUGHT);
    return 1;
}

/* ------------------------------------------------------------ the sidecar */

#define SIDECAR_MAGIC 0x524F5446u      /* "FTOR" */
#define SIDECAR_VERSION 1u

typedef struct sidecar {
    DWORD magic, version, tanks, max_copies, record_size;
    DWORD count[LOGICAL_TANKS];
    unsigned char records[LOGICAL_TANKS][MAX_COPIES][ORN_STRIDE];
} sidecar;

static sidecar file_image;

static void to_image(sidecar *s) {
    memset(s, 0, sizeof *s);
    s->magic = SIDECAR_MAGIC;
    s->version = SIDECAR_VERSION;
    s->tanks = LOGICAL_TANKS;
    s->max_copies = MAX_COPIES;
    s->record_size = ORN_STRIDE;
    memcpy(s->count, copy_count, sizeof s->count);
    memcpy(s->records, copies, sizeof s->records);
}

/* A file that is not exactly what this build writes is refused whole. */
static int from_image(const sidecar *s) {
    int t, k;
    if (s->magic != SIDECAR_MAGIC || s->version != SIDECAR_VERSION || s->tanks != LOGICAL_TANKS
        || s->max_copies != MAX_COPIES || s->record_size != ORN_STRIDE) return 0;
    for (t = 0; t < LOGICAL_TANKS; ++t) {
        if (s->count[t] > MAX_COPIES) return 0;
        for (k = 0; k < (int)s->count[t]; ++k) {
            const unsigned char *r = s->records[t][k];
            if (r[O_ACTIVE] != 1 || !is_ornament_sprite(*(const int *)(r + O_SPRITE))
                || *(const int *)(r + O_W) < 0 || *(const int *)(r + O_W) > 800
                || *(const int *)(r + O_H) < 0 || *(const int *)(r + O_H) > 600
                || *(const int *)(r + O_X) < -800 || *(const int *)(r + O_X) > 1600
                || *(const int *)(r + O_Y) < -600 || *(const int *)(r + O_Y) > 1200) return 0;
        }
    }
    clear_copies();
    for (t = 0; t < LOGICAL_TANKS; ++t) {
        copy_count[t] = (int)s->count[t];
        memcpy(copies[t], s->records[t], (size_t)copy_count[t] * ORN_STRIDE);
    }
    return 1;
}

typedef BOOL (WINAPI *special_folder_fn)(HWND, LPWSTR, int, BOOL);

/* "<Documents>\LDW\<exe name>\Fish Tycoon Fix Patcher Data\Ornaments <slot>.dat",
   beside DS Fish's "DS Fish <slot>.dat": the folder the game saves in. */
static int sidecar_path(int slot, wchar_t *out, DWORD cap, int make_folder) {
#ifdef FTFP_ORN_HARNESS
    return harness_sidecar_path(slot, out, cap, make_folder);
#else
    wchar_t exe[MAX_PATH];
    wchar_t *name, *dot;
    special_folder_fn special;
    HMODULE shell = GetModuleHandleW(L"shell32.dll");
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
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
    wcscat_s(out, cap, L"\\Fish Tycoon Fix Patcher Data");
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\Ornaments ");
    {
        wchar_t digits[12];
        int i = 0, v = slot;
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 11);
        while (i) { size_t len = wcslen(out); out[len] = digits[--i]; out[len + 1] = L'\0'; }
    }
    wcscat_s(out, cap, L".dat");
    return 1;
#endif
}

static int is_game_slot(int slot) {
    return slot > 0 && slot != 0xB;          /* 0 = settings, 11 = the game's own extra record */
}

/* Written whole to "<name>.tmp", then moved over the file: never half a file. */
static void __cdecl on_save(int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    DWORD written;
    if (!is_game_slot(slot) || !sidecar_path(slot, path, 1024, 1)) return;
    to_image(&file_image);
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    if (WriteFile(file, &file_image, sizeof file_image, &written, NULL) && written == sizeof file_image) {
        FlushFileBuffers(file);
        CloseHandle(file);
        MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    } else {
        CloseHandle(file);
        DeleteFileW(temp);
    }
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

/* A game slot loads: its copies, or none (a save from before this setting). */
static void __cdecl on_load(int slot) {
    wchar_t path[1024];
    HANDLE file;
    DWORD got;
    int ok;
    clear_copies();
    if (!is_game_slot(slot) || !sidecar_path(slot, path, 1024, 0)) return;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    ok = ReadFile(file, &file_image, sizeof file_image, &got, NULL) && got == sizeof file_image;
    if (ok) {
        char extra;
        ok = ReadFile(file, &extra, 1, &got, NULL) && got == 0;     /* nothing after it */
    }
    CloseHandle(file);
    if (!ok || !from_image(&file_image)) {
        clear_copies();
        set_aside(path);
    }
}

#ifndef FTFP_ORN_HARNESS
/* ------------------------------------------------------------ the stubs */

static const DWORD k_draw_decor = 0x0041EE60u;
static const DWORD k_fall = 0x0041DB00u;
static const DWORD k_pick = 0x0041E570u;
static const DWORD k_drag = 0x0041E600u;
static const DWORD k_drop = 0x00421B20u;
static const DWORD k_reset = 0x004194A0u;
static const DWORD k_save_join = 0x00419169u;
static const DWORD k_load_join = 0x0041AF60u;
static const DWORD k_click_join = 0x004282CDu;
static const DWORD k_click_done = 0x004282DFu;
static const DWORD k_panel_join = 0x00427358u;
static const DWORD k_panel_price = 0x00427478u;
static int click_result;

/* 0x422062, `call 0x41EE60` (thiscall scene): the stock decor, then the copies. */
__declspec(naked) static void stub_draw(void) {
    __asm {
        push ecx
        call dword ptr [k_draw_decor]
        call draw_copies
        add esp, 4
        ret
    }
}

/* 0x4220D8, `call 0x41DB00` (thiscall scene): the stock fall, then the copies'. */
__declspec(naked) static void stub_fall(void) {
    __asm {
        push ecx
        call dword ptr [k_fall]
        call fall_copies
        add esp, 4
        ret
    }
}

/* 0x41EFD9, `call 0x41E570` (thiscall scene; x, y), ret 8, al = picked. */
__declspec(naked) static void stub_pick(void) {
    __asm {
        push ecx
        mov eax, [esp + 0x0C]
        push eax
        mov eax, [esp + 0x0C]
        push eax
        push ecx
        call pick_copy
        add esp, 0x0C
        pop ecx
        test eax, eax
        jz stock
        mov al, 1
        ret 8
    stock:
        jmp dword ptr [k_pick]
    }
}

/* 0x421BA0, `call 0x41E600` (thiscall scene; x, y), ret 8. */
__declspec(naked) static void stub_drag(void) {
    __asm {
        push ecx
        mov eax, [esp + 0x0C]
        push eax
        mov eax, [esp + 0x0C]
        push eax
        push ecx
        call drag_copy
        add esp, 0x0C
        pop ecx
        test eax, eax
        jz stock
        ret 8
    stock:
        jmp dword ptr [k_drag]
    }
}

/* 0x421D43, `call 0x421B20` (thiscall scene; x, y), ret 8. */
__declspec(naked) static void stub_drop(void) {
    __asm {
        push ecx
        mov eax, [esp + 0x0C]
        push eax
        mov eax, [esp + 0x0C]
        push eax
        push ecx
        call drop_copy
        add esp, 0x0C
        pop ecx
        test eax, eax
        jz stock
        ret 8
    stock:
        jmp dword ptr [k_drop]
    }
}

/* 0x41AA98, `call 0x4194A0` (thiscall state): a new game clears the ornaments, and the copies. */
__declspec(naked) static void stub_new_game(void) {
    __asm {
        call dword ptr [k_reset]
        pushad
        call clear_copies
        popad
        ret
    }
}

/* 0x419160 in Save(slot), a game slot: edx = slot, ecx = the state. */
__declspec(naked) static void stub_save(void) {
    __asm {
        pushad
        push edx
        call on_save
        add esp, 4
        popad
        push edx
        lea eax, [ecx + 8]
        push 0x1E3C8
        jmp dword ptr [k_save_join]
    }
}

/* 0x41AF59 in Load(slot), a game slot read whole: edi = slot. */
__declspec(naked) static void stub_load(void) {
    __asm {
        pushad
        push edi
        call on_load
        add esp, 4
        popad
        lea ecx, [esp + 0x120]
        jmp dword ptr [k_load_join]
    }
}

/* 0x4282C6 in the store's Buy click: eax = item, ecx = the store, edx = the
   state, esi = 0; the stock test is `owned == 0`. */
__declspec(naked) static void stub_click(void) {
    __asm {
        pushad
        push eax
        push ecx
        call store_click
        add esp, 8
        mov dword ptr [click_result], eax
        popad
        cmp dword ptr [click_result], 0
        jne handled
        lea edi, [eax + eax*4 + 0x1E]
        cmp dword ptr [edx + edi*4], esi
        jmp dword ptr [k_click_join]
    handled:
        jmp dword ptr [k_click_done]
    }
}

/* 0x427351 in the store panel: eax = item.  An ornament takes the not-owned
   path (its price), owned or not. */
__declspec(naked) static void stub_panel(void) {
    __asm {
        cmp eax, FIRST_ORNAMENT
        jl stock
        cmp eax, LAST_ORNAMENT
        jg stock
        jmp dword ptr [k_panel_price]
    stock:
        lea edx, [eax + eax*4 + 0x1E]
        mov eax, dword ptr [esi + 0x10]
        jmp dword ptr [k_panel_join]
    }
}

/* ------------------------------------------------------------ install */

#define CODE_ADDR(f) ((const void *)(UINT_PTR)(f))
#define JMP(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE9, CODE_ADDR(TO))
#define CALL(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE8, CODE_ADDR(TO))

static ftfp_site_write writes[ORN_SITE_COUNT];
static int installed = 0;

static int prepare(void) {
    ftfp_site_write *w = writes;
    CALL(w++, DRAW_DECOR, stub_draw);
    CALL(w++, ORNAMENT_FALL, stub_fall);
    CALL(w++, ORNAMENT_PICK, stub_pick);
    CALL(w++, DRAG_MOVE, stub_drag);
    CALL(w++, DRAG_DROP, stub_drop);
    CALL(w++, NEW_GAME, stub_new_game);
    JMP(w++, SAVE, stub_save);
    JMP(w++, LOAD, stub_load);
    JMP(w++, STORE_CLICK, stub_click);
    JMP(w++, STORE_PANEL, stub_panel);
    return (int)(w - writes) == ORN_SITE_COUNT;
}

static int append_text(char *out, int at, const char *text) {
    while (*text && at < 158) out[at++] = *text++;
    return at;
}

static int append_hex(char *out, int at, unsigned int value) {
    int shift;
    at = append_text(out, at, "0x");
    for (shift = 28; shift >= 0 && at < 158; shift -= 4) {
        out[at++] = "0123456789ABCDEF"[(value >> shift) & 0xF];
    }
    return at;
}

/* A path beside this DLL: <its folder>\<name>. */
static int beside_this_dll(const wchar_t *name, wchar_t *path) {
    extern IMAGE_DOS_HEADER __ImageBase;
    wchar_t *slash;
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, path, 1024);
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return 0;
    slash[1] = L'\0';
    if (wcslen(path) + wcslen(name) + 1 >= 1024) return 0;
    wcscat_s(path, 1024, name);
    return 1;
}

/* "<game>\Fish Tycoon Fix Patcher DLLs\Multiple Ornaments.log", as DS Fish's log. */
static void write_install_log(void) {
    wchar_t path[1024];
    char line[160];
    DWORD written;
    HANDLE file;
    int len = 0;
    if (!beside_this_dll(L"Multiple Ornaments.log", path)) return;
    if (installed) {
        len = append_text(line, len, "Multiple Ornaments: installed (all sites)\r\n");
    } else if (ftfp_failed_site != 0) {
        len = append_text(line, len, "Multiple Ornaments: NOT installed; the code at ");
        len = append_hex(line, len, ftfp_failed_site);
        len = append_text(line, len, " is not the stock code this build expects\r\n");
    } else {
        len = append_text(line, len, "Multiple Ornaments: NOT installed\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* The startup stub loads only this DLL; the next companion in the chain is
   "DS Exclusive Fish.dll" (which loads the window's and the store's), else
   "Maximizable Window.dll", whichever the patcher put beside it. */
typedef int (__stdcall *startup_fn)(void);

static void load_next(void) {
    static const wchar_t *const NEXT[2] = { L"DS Exclusive Fish.dll", L"Maximizable Window.dll" };
    wchar_t path[1024];
    int i;
    for (i = 0; i < 2; ++i) {
        HMODULE next;
        startup_fn startup;
        if (!beside_this_dll(NEXT[i], path) || GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) continue;
        next = LoadLibraryW(path);
        if (next == NULL) return;
        startup = (startup_fn)GetProcAddress(next, "FtfpStartup");
        if (startup != NULL) startup();
        return;
    }
}

/* Everything is Free's file beside this DLL. */
static __declspec(noinline) int everything_free_setting(void) {
    wchar_t path[1024];
    return beside_this_dll(L"Everything Free.ini", path) && GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}

/* Called once by the executable's startup stub, before WinMain. */
int __stdcall FtfpStartup(void) {
    static int started = 0;
    if (started) return installed;
    started = 1;
    __try {
        everything_free = everything_free_setting();
        installed = prepare() && ftfp_install_sites(writes, ORN_SITE_COUNT);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    __try {
        load_next();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    return installed;
}

/* For the patcher's tests and the patch log. */
int __stdcall FtfpOrnamentsInstalled(void) { return installed; }

/* For the Extra Tanks setting: name the logical tank (0-7) a stock tank (0-2)
   shows, or NULL for the stock tanks.  The copies of each logical tank are kept
   apart and saved with the slot. */
void __stdcall FtfpOrnamentsSetTankMap(tank_map_fn map) { tank_map = map; }

/* How many decorative copies a logical tank holds (0-MAX_COPIES). */
int __stdcall FtfpOrnamentsCount(int tank) {
    return tank >= 0 && tank < LOGICAL_TANKS ? copy_count[tank] : 0;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}
#endif
