/* FTFP DS Fish -- the Nintendo DS exclusive fish in PC Fish Tycoon.

   WHAT.  Seven DS-only bodies (Clownfish, Discus, Bicolor, Trigger,
   Surgeonfish, Tang, Idle) and seven DS-only fins (Small Fin, Roundy, Angel,
   Clown, Yellow, Blue, Moorish) as exe genes 23-29 (DS indices 21-27; 21 is
   the Golden Seahorse's sprite slot and 22 its body, so both are skipped).
   They are never laid by eggs or bred from two PC fish:
     * the Unknown Chemical and the Magic Fish of Mutation step a gene one
       place along the list exactly as before, but the common end (20) now
       continues into the DS genes and 29 is the new end -- same rolls, same
       odds;
     * a baby with a DS parent gets the DS game's rule: the average of the
       parents' genes, an odd sum rounded up or down at random, one roll per
       litter (DS arm9 0x02034B54).  PC x PC keeps the PC's floor average.
   Rarity tiers, prices, names, sprites and fin placement follow the DS:
   docs/fish-tycoon-ds-fish-technical-map.md has every address.

   HOW.  The patched executable's startup stub loads this DLL by its full
   path and calls FtfpStartup() before WinMain.  FtfpStartup writes every
   site in ds_sites.h -- all of them or none (install_sites.h) -- after
   checking each holds exactly its vanilla bytes.  If anything differs, or
   any step fails, nothing is written and the game runs as stock.

   STATE.  The species table lives in the game state (state + 0x14B40,
   rows of 31 entries of 40 bytes, 21 rows).  DS fins use the spare columns
   23-29 of those rows, so they are saved with the game.  The 7 DS body rows
   live here, in ds_rows, reached through the game's own index arithmetic:
   every `R = body * 31` (33 sites) becomes a call that returns, for a DS
   body, the row index that lands in ds_rows.  ds_rows is saved per slot in
   "<save folder>\Fish Tycoon Fix Patcher Data\DS Fish <slot>.dat"; the
   save itself keeps its stock layout and size. */
#include <windows.h>
#include <string.h>
#include "install_sites.h"
#include "ds_sites.h"
#include "ds_data.h"

#define GENE_SEAHORSE 22
#define GENE_PC_LAST 20
#define FIN_MIRROR_X 0x32           /* a left-facing fish's fins sit at x + 50 - anchor x (0x414878) */
#define ROW_STRIDE 31
#define ENTRY_SIZE 40
#define SPECIES_BASE 0x14B40
#define ENTRY_PRICE 0x20
#define ENTRY_BASE_PRICE 0x24
#define STATE_GLOBAL 0x0045ABDCu
#define DS_ROWS_BYTES (DS_COUNT * ROW_STRIDE * ENTRY_SIZE)

typedef int (__cdecl *game_random_fn)(int bound);
#ifndef FTFP_TEST_RANDOM
static const game_random_fn game_random = (game_random_fn)0x00403240u;
#else
static int __cdecl game_random(int bound) { return FTFP_TEST_RANDOM(bound); }   /* tests only */
#endif

/* ------------------------------------------------------------------ genes */

static int is_ds(int g) { return g >= DS_FIRST_GENE && g <= DS_LAST_GENE; }
static int ds_index(int g) { return g <= GENE_PC_LAST ? g : g - 2; }
static int exe_gene(int d) { return d <= GENE_PC_LAST ? d : d + 2; }
static int valid_gene(int g) { return (g >= 0 && g <= GENE_PC_LAST) || is_ds(g); }

/* One place along the list: ... 19, 20, 23, 24 ... 29. */
static int gene_up(int g) { return g == GENE_PC_LAST ? DS_FIRST_GENE : g + 1; }
static int gene_down(int g) { return g == DS_FIRST_GENE ? GENE_PC_LAST : g - 1; }

/* The vanilla step (0x420EFB / 0x420180), with 29 as the end instead of 20:
   at the end always down; otherwise Random(100) <= 49, or 0, goes up. */
static void __cdecl step_gene(int *gene) {
    int g = *gene;
    if (g == GENE_SEAHORSE || !valid_gene(g)) {
        return;
    }
    if (g == DS_LAST_GENE) {
        *gene = gene_down(g);
    } else if (game_random(100) <= 49 || g == 0) {
        *gene = gene_up(g);
    } else {
        *gene = gene_down(g);
    }
}

/* The hatch clamp (0x420213): 0..20 before, now 0..29. */
static int clamp_gene(int g) {
    if (g < 0) return 0;
    if (g > DS_LAST_GENE) return DS_LAST_GENE;
    return g;
}

static void __cdecl clamp_mate(int *mate) {
    mate[0] = clamp_gene(mate[0]);
    mate[1] = clamp_gene(mate[1]);
}

/* One rounding roll per litter: the DS reads the frame counter once per
   birth, and the PC creates a litter's babies in one pass. */
static DWORD coin_tick = 0;
static int coin_value = 0;
static int litter_coin(void) {
    DWORD now = GetTickCount();
    if (now != coin_tick) {
        coin_tick = now;
        coin_value = game_random(2);
    }
    return coin_value;
}

static int __cdecl breed_gene(int a, int b) {
    int s;
    if (!is_ds(a) && !is_ds(b)) {
        return (a + b) / 2;                      /* the PC's own rule */
    }
    if (!valid_gene(a) || !valid_gene(b)) {
        return (a + b) / 2;
    }
    s = ds_index(a) + ds_index(b);
    return exe_gene(s / 2 + ((s & 1) ? litter_coin() : 0));
}

/* ------------------------------------------------------------------ tiers */

/* 3 = odd, 2 = 2/6/10/14/18, 1 = 0/4/.../20, 0 = none (the seahorse body),
   as the game's lists; DS genes by the same rule on their DS index. */
static int __cdecl gene_tier(int g) {
    int d;
    if (is_ds(g)) {
        d = ds_index(g);
        return (d & 1) ? 3 : (d % 4 == 2) ? 2 : 1;
    }
    if (g & 1) return 3;
    if (g == 2 || g == 6 || g == 10 || g == 14 || g == 18) return 2;
    if (g == 0 || g == 4 || g == 8 || g == 12 || g == 16 || g == 20) return 1;
    return 0;
}

static int __cdecl fish_tier(int body, int fin) {
    int a = gene_tier(body), b = gene_tier(fin);
    return a > b ? a : b;
}

static int __cdecl rare_pair(int body, int fin) {
    return gene_tier(body) >= 2 || gene_tier(fin) >= 2;
}

/* ---------------------------------------------------------- species table */

static unsigned char ds_rows_raw[DS_ROWS_BYTES + ENTRY_SIZE];
static unsigned char *ds_rows = NULL;
static char *ds_rows_state = NULL;
static int g_ds_row_base = 0;

static char *game_state(void) {
    return *(char *volatile *)(UINT_PTR)STATE_GLOBAL;
}

/* Place ds_rows so that state + 0x14B40 + index * 40 reaches it for a whole
   index (the game's own arithmetic, 32-bit).  The game builds its names and
   prices inside the state's constructor, before it stores the state in its
   global, so callers that have the state pass it; the index stubs, which
   only run later, use the global. */
static void ds_rows_for(char *state) {
    INT_PTR diff;
    int r;
    if (state == NULL || state == ds_rows_state) {
        return;
    }
    diff = (INT_PTR)ds_rows_raw - (INT_PTR)(state + SPECIES_BASE);
    r = (int)(((diff % ENTRY_SIZE) + ENTRY_SIZE) % ENTRY_SIZE);
    ds_rows = ds_rows_raw + (r ? ENTRY_SIZE - r : 0);
    g_ds_row_base = (int)(((INT_PTR)ds_rows - (INT_PTR)(state + SPECIES_BASE)) / ENTRY_SIZE);
    ds_rows_state = state;
}

static void __cdecl ensure_ds_rows(void) {
    ds_rows_for(game_state());
}

static unsigned char *entry(char *state, int body, int fin) {
    if (is_ds(body)) {
        ds_rows_for(state);
        return ds_rows + ((body - DS_FIRST_GENE) * ROW_STRIDE + fin) * ENTRY_SIZE;
    }
    return (unsigned char *)state + SPECIES_BASE + (body * ROW_STRIDE + fin) * ENTRY_SIZE;
}

static int ds_price(int body, int fin) {
    int b = ds_index(body), f = ds_index(fin);
    return DS_BODY_VALUE[b] + DS_FIN_VALUE[f] + ((b == f && b > GENE_PC_LAST) ? 10 : 0);
}

static void set_name(unsigned char *e, int body, int fin) {
    char *name = (char *)e;
    size_t n = 0;
    const char *parts[2];
    int p;
    parts[0] = DS_FIN_NAME[ds_index(fin)];
    parts[1] = DS_BODY_NAME[ds_index(body)];
    for (p = 0; p < 2; ++p) {
        const char *s = parts[p];
        while (*s && n + 1 < ENTRY_PRICE) {
            name[n++] = *s++;
        }
    }
    name[n] = '\0';
}

/* Call `fn` for every species entry that has a DS gene. */
typedef void (*entry_fn)(char *state, int body, int fin);
static void for_each_ds_entry(char *state, entry_fn fn) {
    int b, f;
    for (b = 0; b <= DS_LAST_GENE; ++b) {
        if (b == 21 || b == GENE_SEAHORSE) continue;
        for (f = 0; f <= DS_LAST_GENE; ++f) {
            if (f == 21 || f == GENE_SEAHORSE) continue;
            if (is_ds(b) || is_ds(f)) fn(state, b, f);
        }
    }
}

static void init_entry(char *state, int body, int fin) {
    unsigned char *e = entry(state, body, fin);
    memset(e, 0, ENTRY_SIZE);
    set_name(e, body, fin);
    *(int *)(e + ENTRY_PRICE) = -1;               /* undiscovered */
    *(int *)(e + ENTRY_BASE_PRICE) = ds_price(body, fin);
}

static void name_entry(char *state, int body, int fin) {
    set_name(entry(state, body, fin), body, fin);
}

static int divisor_now = 7;
static void inflate_entry(char *state, int body, int fin) {
    int *price = (int *)(entry(state, body, fin) + ENTRY_BASE_PRICE);
    *price += *price / divisor_now;
}

/* New game: after the game's own price setup (0x418B10). */
static void __fastcall init_ds_species(char *state) {
    if (state != NULL) {
        for_each_ds_entry(state, init_entry);
    }
}

/* After the game builds its 21 x 21 names (0x419600). */
static void __fastcall build_ds_names(char *state) {
    if (state != NULL) {
        for_each_ds_entry(state, name_entry);
    }
}

/* Research price rise (0x420A82 / 0x420AE6): the game's 21 x 21 pass, then
   the DS entries, each `price += price / divisor` as the game rounds it. */
static void __cdecl inflate_prices(char *state, int divisor) {
    int b, f;
    for (b = 0; b <= GENE_PC_LAST; ++b) {
        for (f = 0; f <= GENE_PC_LAST; ++f) {
            int *price = (int *)(state + SPECIES_BASE + (b * ROW_STRIDE + f) * ENTRY_SIZE + ENTRY_BASE_PRICE);
            *price += *price / divisor;
        }
    }
    divisor_now = divisor;
    for_each_ds_entry(state, inflate_entry);
}

/* Species discovered (0x419240): the game's 21 x 21, plus the DS entries. */
static int ds_discovered = 0;
static void count_entry(char *state, int body, int fin) {
    if (*(int *)(entry(state, body, fin) + ENTRY_PRICE) != -1) ++ds_discovered;
}
static int __fastcall count_species(char *state) {
    int b, f, n = 0;
    for (b = 0; b <= GENE_PC_LAST; ++b) {
        for (f = 0; f <= GENE_PC_LAST; ++f) {
            if (*(int *)(state + SPECIES_BASE + (b * ROW_STRIDE + f) * ENTRY_SIZE + ENTRY_PRICE) != -1) ++n;
        }
    }
    ds_discovered = 0;
    for_each_ds_entry(state, count_entry);
    return n + ds_discovered;
}

/* ---------------------------------------------------------------- sidecar */

#define SIDECAR_MAGIC 0x53445446u      /* "FTDS" */
#define SIDECAR_VERSION 1u
typedef BOOL (WINAPI *special_folder_fn)(HWND, LPWSTR, int, BOOL);

/* "<Documents>\LDW\<exe name>\Fish Tycoon Fix Patcher Data\DS Fish <slot>.dat":
   the folder the game saves in (its own Documents\LDW\<exe name>), so a
   modded copy's data stays beside its own saves. */
static int sidecar_path(int slot, wchar_t *out, DWORD cap, int make_folder) {
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
    wcscat_s(out, cap, L"\\DS Fish ");
    {
        wchar_t digits[12];
        int i = 0, v = slot;
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 11);
        while (i) { size_t len = wcslen(out); out[len] = digits[--i]; out[len + 1] = L'\0'; }
    }
    wcscat_s(out, cap, L".dat");
    return 1;
}

static int is_game_slot(int slot) {
    return slot != 0 && slot != 0xB;          /* 0 = settings, 11 = the game's own extra record */
}

static void __cdecl on_save(int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    DWORD header[3], written;
    char *state = game_state();
    if (!is_game_slot(slot) || state == NULL || !sidecar_path(slot, path, 1024, 1)) return;
    ds_rows_for(state);
    if (ds_rows == NULL) return;
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    header[0] = SIDECAR_MAGIC;
    header[1] = SIDECAR_VERSION;
    header[2] = DS_ROWS_BYTES;
    if (WriteFile(file, header, sizeof header, &written, NULL) && written == sizeof header
        && WriteFile(file, ds_rows, DS_ROWS_BYTES, &written, NULL) && written == DS_ROWS_BYTES) {
        CloseHandle(file);
        MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING);
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

/* Is the save's own DS-fin data already set up (a save made with this mod)? */
static int pc_columns_ready(char *state) {
    unsigned char *e = entry(state, 0, DS_FIRST_GENE);
    return e[0] != 0 && *(int *)(e + ENTRY_BASE_PRICE) != 0;
}

static void init_ds_rows_only(char *state) {
    int b, f;
    for (b = DS_FIRST_GENE; b <= DS_LAST_GENE; ++b) {
        for (f = 0; f <= DS_LAST_GENE; ++f) {
            if (f != 21 && f != GENE_SEAHORSE) init_entry(state, b, f);
        }
    }
}

static void refresh_anchors(char *state);

static void __cdecl on_load(int slot) {
    wchar_t path[1024];
    HANDLE file;
    DWORD header[3], got;
    int ok = 0;
    char *state = game_state();
    if (!is_game_slot(slot) || state == NULL) return;
    refresh_anchors(state);
    ds_rows_for(state);
    if (ds_rows == NULL) return;
    if (sidecar_path(slot, path, 1024, 0)) {
        file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (file != INVALID_HANDLE_VALUE) {
            ok = ReadFile(file, header, sizeof header, &got, NULL) && got == sizeof header
                 && header[0] == SIDECAR_MAGIC && header[1] == SIDECAR_VERSION && header[2] == DS_ROWS_BYTES
                 && ReadFile(file, ds_rows, DS_ROWS_BYTES, &got, NULL) && got == DS_ROWS_BYTES;
            CloseHandle(file);
            if (!ok) set_aside(path);
        }
    }
    if (!pc_columns_ready(state)) {
        init_ds_species(state);              /* a save from before the mod: everything fresh */
    } else if (!ok) {
        init_ds_rows_only(state);
    }
}

/* ----------------------------------------------------------------- sprites */

typedef struct sprite_entry {
    int id;
    const char *name;
    int cols, rows;
    int reserved[5];
} sprite_entry;

#define GAME_SPRITES 197
#define DS_SPRITE_BASE GAME_SPRITES                 /* body, bot, top per DS gene */
#define DS_SPRITE_TEEN (GAME_SPRITES + 3 * DS_COUNT)
#define DS_SPRITE_DEAD (DS_SPRITE_TEEN + 1)
#define STORE_SPRITE_BASE (DS_SPRITE_DEAD + 1)        /* 220: lent to "FTFP DS Store.dll" */
#define STORE_SPRITE_COUNT 16
#define ALL_SPRITES (STORE_SPRITE_BASE + STORE_SPRITE_COUNT)
static sprite_entry sprites[ALL_SPRITES];

static const char *const DS_SHEETS[3 * DS_COUNT] = {
    "FISH_23_body_Grid.png", "FISH_23_bot_Grid.png", "FISH_23_top_Grid.png",
    "FISH_24_body_Grid.png", "FISH_24_bot_Grid.png", "FISH_24_top_Grid.png",
    "FISH_25_body_Grid.png", "FISH_25_bot_Grid.png", "FISH_25_top_Grid.png",
    "FISH_26_body_Grid.png", "FISH_26_bot_Grid.png", "FISH_26_top_Grid.png",
    "FISH_27_body_Grid.png", "FISH_27_bot_Grid.png", "FISH_27_top_Grid.png",
    "FISH_28_body_Grid.png", "FISH_28_bot_Grid.png", "FISH_28_top_Grid.png",
    "FISH_29_body_Grid.png", "FISH_29_bot_Grid.png", "FISH_29_top_Grid.png",
};

static void build_sprite_table(void) {
    int i;
    memcpy(sprites, (const void *)(UINT_PTR)0x004552F0u, GAME_SPRITES * sizeof(sprite_entry));
    for (i = 0; i < 3 * DS_COUNT; ++i) {
        sprite_entry *s = &sprites[DS_SPRITE_BASE + i];
        memset(s, 0, sizeof *s);
        s->id = DS_SPRITE_BASE + i;
        s->name = DS_SHEETS[i];
        s->cols = (i % 3 == 0) ? 7 : 13;
        s->rows = (i % 3 == 0) ? 3 : 2;
    }
    memset(&sprites[DS_SPRITE_TEEN], 0, 2 * sizeof(sprite_entry));
    sprites[DS_SPRITE_TEEN].id = DS_SPRITE_TEEN;
    sprites[DS_SPRITE_TEEN].name = "FISH_DS_teen_Grid.png";
    sprites[DS_SPRITE_TEEN].cols = 18;
    sprites[DS_SPRITE_TEEN].rows = DS_COUNT;
    sprites[DS_SPRITE_DEAD].id = DS_SPRITE_DEAD;
    sprites[DS_SPRITE_DEAD].name = "FISH_DS_adult_dead_Grid.png";
    sprites[DS_SPRITE_DEAD].cols = DS_COUNT;
    sprites[DS_SPRITE_DEAD].rows = 1;
    /* The store's entries stand in as the seahorse sheet until the store
       companion names them; nothing asks for them without it. */
    for (i = STORE_SPRITE_BASE; i < ALL_SPRITES; ++i) {
        sprites[i] = sprites[101];
        sprites[i].id = i;
    }
}

/* 0x4122A0: sprite id (gene * 100 + 10000 + frame code) -> table entry and
   frame, exactly as the game maps it; DS genes go to the DS sheets. */
static void __stdcall decode_sprite(int id, int *out) {
    int v = id - 10000;
    int g = v / 100;
    int f = v - g * 100;
    int base = is_ds(g) ? DS_SPRITE_BASE + 3 * (g - DS_FIRST_GENE) : 38 + 3 * g;
    int part = 0, frame;
    if (f >= 81)      { part = 2; frame = f - 69; }
    else if (f >= 71) { part = 2; frame = f - 65; }
    else if (f >= 61) { part = 2; frame = f - 61; }
    else if (f >= 51) { part = 1; frame = f - 39; }
    else if (f >= 41) { part = 1; frame = f - 35; }
    else if (f >= 31) { part = 1; frame = f - 31; }
    else if (f >= 21) { frame = f - 9; }
    else if (f >= 11) { frame = f - 5; }
    else              { frame = f - 1; }
    out[0] = base + part;
    out[1] = frame;
}

/* 0x415DF0 sets a fish's sprite ids, its fin alpha and the per-body fin
   anchors; for a pair with a DS gene, put each fin where the DS draws it. */
static void __stdcall pair_anchors(int *sprite, int body, int fin) {
    const signed char *a;
    if (!(is_ds(body) || is_ds(fin)) || !valid_gene(body) || !valid_gene(fin)) return;
    a = DS_PAIR_ANCHOR[ds_index(body)][ds_index(fin)];
    sprite[5] = a[0];          /* +0x14 top x */
    sprite[6] = a[1];          /* +0x18 top y */
    sprite[7] = a[2];          /* +0x1C bottom x */
    sprite[8] = a[3];          /* +0x20 bottom y */
}

/* A fish keeps the fin anchors it was given when it was born or mutated, in
   its record (+0x68..+0x74).  After a load every fish with a DS gene gets the
   current ones, so fish from earlier builds of this DLL are drawn right too. */
static void refresh_anchors(char *state) {
    int tank, slot;
    for (tank = 0; tank <= 3; ++tank) {
        for (slot = 0; slot < 31; ++slot) {
            char *rec = state + 0x390 + tank * 0x51EC + slot * 0x288;
            if (*(int *)rec == 0) continue;
            pair_anchors((int *)(rec + 0x54), *(int *)(rec + 0x4C), *(int *)(rec + 0x50));
        }
    }
}

/* Head-on frames (12-17) draw a fin at body + 44 + c - anchor, which only
   suits the PC's own anchors.  For a pair with a DS gene keep the fin at
   the same fraction along the body as on frame 0.  Returns the value the
   game then turns into x with `+ body + 0x2C`. */
static int __cdecl head_on_x(int body, int fin, int part, int frame, int anchor, int c) {
    const unsigned char *b0, *bk, *f0, *fk;
    int k, w0, wk, num, x;
    if (!(is_ds(body) || is_ds(fin)) || !valid_gene(body) || !valid_gene(fin) || frame < 0 || frame > 5) {
        return c - anchor;
    }
    k = frame + 1;
    b0 = DS_EXTENT[ds_index(body)][0][0];
    bk = DS_EXTENT[ds_index(body)][0][k];
    f0 = DS_EXTENT[ds_index(fin)][1 + part][0];
    fk = DS_EXTENT[ds_index(fin)][1 + part][k];
    w0 = b0[1] - b0[0];
    wk = bk[1] - bk[0];
    if (w0 <= 0 || f0[1] == 0 || fk[1] == 0) {
        return c - anchor;
    }
    num = (FIN_MIRROR_X - anchor + f0[0] - b0[0]) * wk;   /* frame 0's fin is at x + 50 - anchor */
    if (frame < 3) {          /* 12-14 face right: the fin's front edge is its right edge */
        x = bk[1] - (num + w0 / 2) / w0 - fk[1];
    } else {
        x = bk[0] + (num + w0 / 2) / w0 - fk[0];
    }
    return x - 0x2C;
}

/* ------------------------------------------------------------------- stubs */

static const DWORD k_mutate_join = 0x00420F51u;
static const DWORD k_hatch_join = 0x00420213u;
static const DWORD k_hatch_clamped = 0x00420263u;
static const DWORD k_breed_join = 0x0041FAC8u;
static const DWORD k_tier3 = 0x0041E059u, k_tier2 = 0x0041E035u, k_tier1 = 0x0041E011u, k_tier0 = 0x0041E083u;
static const DWORD k_dis3 = 0x0041E19Du, k_dis2 = 0x0041E1C3u, k_dis1 = 0x0041E1D9u, k_dis0 = 0x0041E1F4u;
static const DWORD k_goal_yes = 0x0041FC71u, k_goal_no = 0x0041FC7Au;
static const DWORD k_get_sprite = 0x0041BCA0u;
static const DWORD k_teen_join = 0x00414759u;
static const DWORD k_draw_join = 0x00414C93u;
static const DWORD k_head_on_top_join = 0x00414937u;
static const DWORD k_head_on_bot_join = 0x004149ADu;
static const DWORD k_inflate_join = 0x00420B42u;
static const DWORD k_save_join = 0x00419106u;
static const DWORD k_memcpy = 0x0042CB10u;

__declspec(naked) static void stub_mutate_body(void) {
    __asm {
        lea eax, [edi + 0x4C]
        push eax
        call step_gene
        add esp, 4
        jmp k_mutate_join
    }
}

__declspec(naked) static void stub_mutate_fin(void) {
    __asm {
        lea eax, [edi + 0x50]
        push eax
        call step_gene
        add esp, 4
        jmp k_mutate_join
    }
}

__declspec(naked) static void stub_hatch_body(void) {
    __asm {
        mov eax, [esi + 0x34]
        lea eax, [edi + eax + 0x3A4]
        push eax
        call step_gene
        add esp, 4
        jmp k_hatch_join
    }
}

/* The game's fin branch tests the BODY value for its 0/20 bounce (a
   vanilla slip the clamp hid); the fin's own value is used here. */
__declspec(naked) static void stub_hatch_fin(void) {
    __asm {
        mov ecx, [esi + 0x34]
        lea eax, [edi + ecx + 0x3A8]
        push eax
        call step_gene
        add esp, 4
        jmp k_hatch_join
    }
}

__declspec(naked) static void stub_hatch_clamp(void) {
    __asm {
        mov eax, [esi + 0x34]
        lea eax, [edi + eax + 0x3A4]
        push eax
        call clamp_mate
        add esp, 4
        jmp k_hatch_clamped
    }
}

/* body = breed(edi, ebx) into ecx, fin = breed(ebp, [esp+0x2A8]) into eax;
   the overwritten `mov [esp+0x1C], ecx` first. */
__declspec(naked) static void stub_breed(void) {
    __asm {
        mov [esp + 0x1C], ecx
        mov edx, [esp + 0x2A8]
        push edx
        push ebx
        push edi
        call breed_gene
        add esp, 8
        pop edx
        push eax
        push edx
        push ebp
        call breed_gene
        add esp, 8
        pop ecx
        jmp k_breed_join
    }
}

__declspec(naked) static void stub_tier_health(void) {
    __asm {
        push esi
        push ecx
        push eax
        call fish_tier
        add esp, 8
        cmp eax, 3
        je t3
        cmp eax, 2
        je t2
        cmp eax, 1
        je t1
        jmp k_tier0
    t3: jmp k_tier3
    t2: jmp k_tier2
    t1: jmp k_tier1
    }
}

__declspec(naked) static void stub_tier_disease(void) {
    __asm {
        push ecx
        push eax
        call gene_tier
        add esp, 4
        pop ecx
        cmp eax, 1
        je d1
        cmp eax, 2
        je d2
        cmp eax, 3
        je d3
        jmp k_dis0
    d1: jmp k_dis1
    d2: jmp k_dis2
    d3: jmp k_dis3
    }
}

__declspec(naked) static void stub_tier_goal(void) {
    __asm {
        mov eax, [esp + 0x5C]
        mov edx, [esp + 0x60]
        push edx
        push eax
        call rare_pair
        add esp, 8
        test eax, eax
        jnz yes
        jmp k_goal_no
    yes: jmp k_goal_yes
    }
}

/* Teen: sprite 0x24, row = body gene; DS bodies use the DS teen sheet. */
__declspec(naked) static void stub_teen(void) {
    __asm {
        cmp eax, DS_FIRST_GENE
        jl pc
        cmp eax, DS_LAST_GENE
        jg pc
        sub eax, DS_FIRST_GENE
        mov edx, DS_SPRITE_TEEN
        jmp go
    pc: mov edx, 0x24
    go: push eax
        mov eax, [esp + 0x34]
        push eax
        push ebx
        push edx
        call k_get_sprite
        jmp k_teen_join
    }
}

/* Dead adult: sprite 0x25, frame = body gene; DS bodies use the DS sheet. */
__declspec(naked) static void stub_dead(void) {
    __asm {
        mov ecx, [esi + 0x4C]
        mov edx, [esp + 0x24]
        cmp ecx, DS_FIRST_GENE
        jl pc
        cmp ecx, DS_LAST_GENE
        jg pc
        sub ecx, DS_FIRST_GENE
        mov eax, DS_SPRITE_DEAD
        jmp go
    pc: mov eax, 0x25
    go: push ecx
        push edx
        push ebx
        push eax
        jmp k_draw_join
    }
}

/* Hooks that return to the game hand back every register as the original
   left it: the game's callers rely on that (0x41AAC3 calls the next routine
   with the ecx 0x418B10 left, without reloading it). */
__declspec(naked) static void stub_anchors(void) {
    __asm {
        pop edi
        pop esi
        pop ebx
        pushad
        mov eax, [esp + 0x24]          /* sprite */
        mov ecx, [esp + 0x28]          /* body */
        mov edx, [esp + 0x2C]          /* fin */
        push edx
        push ecx
        push eax
        call pair_anchors
        popad
        ret 0x0C
    }
}

/* The game's decoder returns with ecx = out, edx = entry, eax = frame. */
__declspec(naked) static void stub_decode(void) {
    __asm {
        mov eax, [esp + 8]
        push eax
        mov eax, [esp + 8]
        push eax
        call decode_sprite
        mov ecx, [esp + 8]
        mov edx, [ecx]
        mov eax, [ecx + 4]
        ret 8
    }
}

__declspec(naked) static void stub_head_on_top(void) {
    __asm {
        mov eax, 0x004404A8
        fdiv qword ptr [eax]
        push ecx
        push edx
        mov eax, [esp + 0x18]          /* c */
        push eax
        push dword ptr [esi + 0x68]    /* top anchor x */
        mov eax, [esp + 0x40]          /* frame within the turn */
        push eax
        push 0                         /* top */
        push dword ptr [esi + 0x50]    /* fin */
        push dword ptr [esi + 0x4C]    /* body */
        call head_on_x
        add esp, 24
        pop edx
        pop ecx
        jmp k_head_on_top_join
    }
}

__declspec(naked) static void stub_head_on_bot(void) {
    __asm {
        mov eax, [esp + 0x1C]          /* c */
        push eax
        push dword ptr [esi + 0x70]    /* bottom anchor x */
        mov eax, [esp + 0x44]          /* frame within the turn */
        push eax
        push 1                         /* bottom */
        push dword ptr [esi + 0x50]
        push dword ptr [esi + 0x4C]
        call head_on_x
        add esp, 24
        jmp k_head_on_bot_join
    }
}

__declspec(naked) static void stub_init_prices(void) {
    __asm {
        pop edi
        pop esi
        pop ebp
        pop ebx
        pushad
        call init_ds_species           /* ecx is still the state */
        popad
        ret
    }
}

__declspec(naked) static void stub_build_names(void) {
    __asm {
        pop edi
        pop esi
        pop ebp
        pop ebx
        pushad
        mov ecx, [esp + 0x24]          /* the state the routine saved */
        call build_ds_names
        popad
        add esp, 8
        ret
    }
}

__declspec(naked) static void stub_inflate_7(void) {
    __asm {
        pushad
        mov eax, [esi + 0x34]
        push 7
        push eax
        call inflate_prices
        add esp, 8
        popad
        jmp k_inflate_join
    }
}

__declspec(naked) static void stub_inflate_10(void) {
    __asm {
        pushad
        mov eax, [esi + 0x34]
        push 10
        push eax
        call inflate_prices
        add esp, 8
        popad
        jmp k_inflate_join
    }
}

__declspec(naked) static void stub_save(void) {
    __asm {
        push ecx
        mov edx, [esp + 8]
        push edx
        call on_save
        add esp, 4
        pop ecx
        mov edx, [esp + 4]
        test edx, edx
        jmp k_save_join
    }
}

/* Replaces `call memcpy` (0x41AF62) on the loader's save-slot path: the
   copy into the state as before, then this slot's DS data.  edi is the
   slot there; eax is returned as memcpy returns it. */
__declspec(naked) static void stub_load(void) {
    __asm {
        push dword ptr [esp + 0x0C]
        push dword ptr [esp + 0x0C]
        push dword ptr [esp + 0x0C]
        call k_memcpy
        add esp, 0x0C
        pushad
        push edi
        call on_load
        add esp, 4
        popad
        ret
    }
}

/* R = row for gene S: S * 31, or the DS row index for a DS body.  One stub
   per register pair the game uses (ds_sites.h lists them); only R and the
   flags change, as with the `mov / shl / sub` they replace. */
#define INDEX_STUB(NAME, R, S)                                   \
    __declspec(naked) static void NAME(void) {                   \
        __asm { mov R, S }                                       \
        __asm { cmp R, DS_FIRST_GENE }                           \
        __asm { jl pc }                                          \
        __asm { cmp R, DS_LAST_GENE }                            \
        __asm { jg pc }                                          \
        __asm { pushad }                                         \
        __asm { call ensure_ds_rows }                            \
        __asm { popad }                                          \
        __asm { sub R, DS_FIRST_GENE }                           \
        __asm { imul R, R, ROW_STRIDE }                          \
        __asm { add R, g_ds_row_base }                           \
        __asm { ret }                                            \
        __asm { pc: imul R, R, ROW_STRIDE }                      \
        __asm { ret }                                            \
    }

INDEX_STUB(index_eax_ecx, eax, ecx)
INDEX_STUB(index_eax_edi, eax, edi)
INDEX_STUB(index_eax_edx, eax, edx)
INDEX_STUB(index_ecx_eax, ecx, eax)
INDEX_STUB(index_ecx_ebx, ecx, ebx)
INDEX_STUB(index_edx_eax, edx, eax)
INDEX_STUB(index_edx_ebx, edx, ebx)
INDEX_STUB(index_edx_ecx, edx, ecx)
INDEX_STUB(index_edx_edi, edx, edi)

#define CODE_ADDR(f) ((const void *)(UINT_PTR)(f))

/* reg numbers as ds_sites.h: eax 0, ecx 1, edx 2, ebx 3, esp 4, ebp 5, esi 6, edi 7 */
static const void *index_stub(int r, int s) {
    if (r == 0 && s == 1) return CODE_ADDR(index_eax_ecx);
    if (r == 0 && s == 7) return CODE_ADDR(index_eax_edi);
    if (r == 0 && s == 2) return CODE_ADDR(index_eax_edx);
    if (r == 1 && s == 0) return CODE_ADDR(index_ecx_eax);
    if (r == 1 && s == 3) return CODE_ADDR(index_ecx_ebx);
    if (r == 2 && s == 0) return CODE_ADDR(index_edx_eax);
    if (r == 2 && s == 3) return CODE_ADDR(index_edx_ebx);
    if (r == 2 && s == 1) return CODE_ADDR(index_edx_ecx);
    if (r == 2 && s == 7) return CODE_ADDR(index_edx_edi);
    return NULL;
}

/* ----------------------------------------------------------------- install */

#define CODE_SITES 22
#define TABLE_SITES (2 + 3 * TABLE_FUNC_COUNT)
#define TOTAL_SITES (CODE_SITES + TABLE_SITES + INDEX_SITE_COUNT)
static ftfp_site_write writes[TOTAL_SITES];
static int installed = 0;

#define JMP(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE9, CODE_ADDR(TO))
#define IMM(W, NAME, VALUE) ftfp_site_imm32((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, SITE_##NAME##_IMM_AT, (unsigned int)(VALUE))

static int prepare(void) {
    ftfp_site_write *w = writes;
    unsigned int table = (unsigned int)(UINT_PTR)sprites;
    int i;
    JMP(w++, MUTATE_BODY, stub_mutate_body);
    JMP(w++, MUTATE_FIN, stub_mutate_fin);
    JMP(w++, HATCH_BODY, stub_hatch_body);
    JMP(w++, HATCH_FIN, stub_hatch_fin);
    JMP(w++, HATCH_CLAMP, stub_hatch_clamp);
    JMP(w++, BREED, stub_breed);
    JMP(w++, TIER_HEALTH, stub_tier_health);
    JMP(w++, TIER_DISEASE, stub_tier_disease);
    JMP(w++, TIER_GOAL, stub_tier_goal);
    JMP(w++, DECODE, stub_decode);
    JMP(w++, TEEN, stub_teen);
    JMP(w++, DEAD, stub_dead);
    JMP(w++, ANCHORS, stub_anchors);
    JMP(w++, HEAD_ON_TOP, stub_head_on_top);
    JMP(w++, HEAD_ON_BOT, stub_head_on_bot);
    JMP(w++, COUNT_SPECIES, count_species);
    JMP(w++, INIT_PRICES, stub_init_prices);
    JMP(w++, BUILD_NAMES, stub_build_names);
    JMP(w++, INFLATE_7, stub_inflate_7);
    JMP(w++, INFLATE_10, stub_inflate_10);
    JMP(w++, SAVE, stub_save);
    ftfp_site_branch(w++, SITE_LOAD_VA, SITE_LOAD_LEN, SITE_LOAD_EXPECT, 0xE8, CODE_ADDR(stub_load));
    IMM(w++, TBL_FREE_START, table + 0x1C);
    IMM(w++, TBL_FREE_END, table + ALL_SPRITES * sizeof(sprite_entry) - 4);
    IMM(w++, TBL_0_BOUND, ALL_SPRITES - 1);
    IMM(w++, TBL_0_CMP, table);
    IMM(w++, TBL_0_LEA, table);
    IMM(w++, TBL_1_BOUND, ALL_SPRITES - 1);
    IMM(w++, TBL_1_CMP, table);
    IMM(w++, TBL_1_LEA, table);
    IMM(w++, TBL_2_BOUND, ALL_SPRITES - 1);
    IMM(w++, TBL_2_CMP, table);
    IMM(w++, TBL_2_LEA, table);
    IMM(w++, TBL_3_BOUND, ALL_SPRITES - 1);
    IMM(w++, TBL_3_CMP, table);
    IMM(w++, TBL_3_LEA, table);
    for (i = 0; i < INDEX_SITE_COUNT; ++i) {
        const void *stub = index_stub(INDEX_SITES[i].reg_r, INDEX_SITES[i].reg_s);
        if (stub == NULL) return 0;
        ftfp_site_branch(w++, INDEX_SITES[i].va, 7, INDEX_SITES[i].expect, 0xE8, stub);
    }
    return (int)(w - writes) == TOTAL_SITES;
}

/* One line in "<game>\Fish Tycoon Fix Patcher Files\FTFP DS Fish.log": whether the
   DS fish are in this run, and if not, the first site that was not stock. */
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

static void write_install_log(void) {
    wchar_t path[1024];
    char line[160];
    DWORD n = GetModuleFileNameW(NULL, path, 1024), written;
    wchar_t *slash;
    HANDLE file;
    int len = 0;
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(path) + 64 >= 1024) return;
    wcscat_s(path, 1024, L"Fish Tycoon Fix Patcher Files\\FTFP DS Fish.log");
    if (installed) {
        len = append_text(line, len, "DS Fish: installed (all sites)\r\n");
    } else if (ftfp_failed_site != 0) {
        len = append_text(line, len, "DS Fish: NOT installed; the code at ");
        len = append_hex(line, len, ftfp_failed_site);
        len = append_text(line, len, " is not the stock code this build expects\r\n");
    } else {
        len = append_text(line, len, "DS Fish: NOT installed\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* ------------------------------------------------------------ DS Store */

/* "FTFP DS Store.dll" (the "DS Store Items" setting), beside this DLL, adds
   the store's Upgrades page.  It is loaded only once the DS fish are in, and
   gets the sprite table entries set aside for it. */
typedef struct ftfp_store_host {
    int version;
    void *sprites;          /* sprite_entry[ALL_SPRITES] */
    int first;              /* STORE_SPRITE_BASE */
    int count;              /* STORE_SPRITE_COUNT */
} ftfp_store_host;
typedef int (__stdcall *store_startup_fn)(const ftfp_store_host *host);

EXTERN_C IMAGE_DOS_HEADER __ImageBase;
static ftfp_store_host store_host;

static void load_store(void) {
    wchar_t path[1024];
    wchar_t *slash;
    HMODULE store;
    store_startup_fn startup;
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, path, 1024);
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(path) + 32 >= 1024) return;
    wcscat_s(path, 1024, L"FTFP DS Store.dll");
    if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return;
    store = LoadLibraryW(path);
    if (store == NULL) return;
    startup = (store_startup_fn)GetProcAddress(store, "FtfpStoreStartup");
    if (startup == NULL) return;
    store_host.version = 1;
    store_host.sprites = sprites;
    store_host.first = STORE_SPRITE_BASE;
    store_host.count = STORE_SPRITE_COUNT;
    startup(&store_host);
}

/* Called once by the executable's startup stub, before WinMain. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        build_sprite_table();
        if (prepare() && ftfp_install_sites(writes, TOTAL_SITES)) {
            installed = 1;
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    if (installed) {
        __try {
            load_store();
        } __except (EXCEPTION_EXECUTE_HANDLER) {
        }
    }
    return installed;
}

/* For the patcher's tests and the patch log. */
int __stdcall FtfpDsFishInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
