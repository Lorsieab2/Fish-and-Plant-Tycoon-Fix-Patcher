/* Unused Flowers -- the 14 unused flower heads in PC Plant Tycoon.

   WHAT.  Plant Tycoon ships 14 flower heads (3 views each) in its flower
   sheets that no flower gene uses.  They become flower genes 24-37, so with
   the 23 foliages there are 322 new species.  Every one is the rarest class
   (the game makes any gene above 17 class D on its own).  They come from:
     * Mutation Liquid, whose flower step (+1 or -1, unchanged odds) now runs
       over 1-37: a Tilia (23) can step up into 24, and 37 bounces to 36;
     * breeding, by the game's own rule (the parents' average, rounded up);
     * Legendary Seeds, sold on the store's Upgrades page by the separate
       "Store Upgrades and Items.dll", which this DLL loads when it is beside it.
   docs/plant-tycoon-new-flowers-design.md has the design and every address.

   HOW.  The patched executable's startup stub loads this DLL by its full
   path and calls FtfpStartup() before WinMain.  FtfpStartup writes every
   site in flower_sites.h and flower_stubs.h -- all of them or none -- after
   checking each holds exactly its vanilla bytes.

   STATE.  The game keeps its species tables as int[26][26] value and asking
   price, byte[24][24] discovered and a name table, so flowers 24-37 do not
   fit.  Their species live here: value V (fixed), asking price P and the
   discovered flag, reached through the game's own index arithmetic (the 15
   index sites swap the index for a flower 24-37 so the game's own read or
   write lands in these tables).  P and discovered are saved per slot in
   "<save folder>\Plant Tycoon Fix Patcher Data\New Flowers <slot>.dat"; the
   save itself keeps its stock layout and size. */
#include <windows.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "flower_sites.h"

#define FIRST_NEW 24
#define LAST_NEW 37
#define NEW_COUNT 14
#define FOLIAGES 23
#define FOLIAGE_ROWS 24                      /* indexed by foliage gene 1..23 */
#define STATE_KNOWLEDGE 0x2181               /* the Flower of Knowledge's flag byte */

typedef int (__cdecl *game_random_fn)(int bound);
#ifndef FTFP_TEST_RANDOM
static const game_random_fn game_random = (game_random_fn)0x004033B0u;
#else
static int __cdecl game_random(int bound) { return FTFP_TEST_RANDOM(bound); }   /* tests only */
#endif

static int is_new(int flower) { return flower >= FIRST_NEW && flower <= LAST_NEW; }
static int valid_foliage(int foliage) { return foliage >= 1 && foliage <= FOLIAGES; }

/* ------------------------------------------------------------- the flowers */

/* The flower art records the game reads (0x48E6B8's layout): gene, worth per
   visible flower, sheet, mask, first cell, and the anchor offsets (x, y, in
   cell pixels at full bloom) that set which point of the art sits on the
   branch: 0, 0 is the cell's centre.  The game's own flowers are centred the
   same way (the Painted flower's art sits 10 px high in its cell, and its
   offset of 12 re-centres it); the new heads are all within 2 px of centre. */
typedef struct flower_art {
    int gene, worth, sheet, mask, cell, factor_a, factor_b;
} flower_art;

#ifndef MIRABILIS_ANCHOR_X
#define MIRABILIS_ANCHOR_X 0
#define MIRABILIS_ANCHOR_Y -12
#endif

static const flower_art ART[NEW_COUNT] = {
    { 24, 5, 81, 107, 6, 0, 0 },     /* Indigo: the blue rose */
    { 25, 5, 81, 107, 33, 0, 0 },    /* Peony: the pink rose */
    { 26, 5, 81, 107, 24, 0, 0 },    /* Lilac: the lilac star */
    { 27, 5, 81, 107, 27, 0, 0 },    /* Veronica: the blue-white star */
    { 28, 5, 81, 107, 54, 0, 0 },    /* Violetta: the purple violet */
    { 29, 5, 81, 107, 51, 0, 0 },    /* Stella: the yellow star */
    { 30, 5, 81, 107, 39, 0, 0 },    /* Forget-me-not: the small teal flower */
    { 31, 5, 81, 107, 42, 0, 0 },    /* Anagallis: the small red flower */
    { 32, 5, 81, 107, 48, 0, 0 },    /* Buttercup: the small yellow flower */
    { 33, 5, 82, 108, 12, 0, 0 },    /* Cerulean: the cyan orchid */
    { 34, 5, 82, 108, 27, 0, 0 },    /* Phalaena: the white-purple orchid */
    { 35, 5, 82, 108, 33, MIRABILIS_ANCHOR_X, MIRABILIS_ANCHOR_Y }, /* Mirabilis: the trumpet, recoloured into the sheet's empty cells 33-35;
                                        anchored halfway between the bell and the tube's end, not the cell's centre */
    { 36, 5, 83, 109, 6, 0, 0 },     /* Blueberry */
    { 37, 5, 83, 109, 15, 0, 0 },    /* Prunus: the purple plum */
};

/* The owner's names (2026-10-26). */
static const char *const ADJECTIVE[NEW_COUNT] = {
    "Indigo", "Peony", "Lilac", "Veronica", "Violetta", "Stella", "Forget-me-not",
    "Anagallis", "Buttercup", "Cerulean", "Phalaena", "Mirabilis", "Blueberry", "Prunus",
};

/* The value each flower adds to its species' value (the game's own flower adds
   for 18-23 are 40, 64, 30, 32, 36 and 26). */
static const int FLOWER_ADD[NEW_COUNT] = { 60, 60, 45, 45, 45, 45, 35, 35, 35, 70, 70, 55, 50, 50 };

/* The game's foliage bases and nouns, by foliage gene (0x41D870, 0x41E550). */
static const int FOLIAGE_BASE[FOLIAGE_ROWS] = {
    0, 4, 28, 16, 36, 5, 36, 20, 28, 5, 30, 18, 34, 6, 32, 22, 42, 6, 68, 48, 70, 60, 64, 66,
};
static const char *const NOUN[FOLIAGE_ROWS] = {
    "", "Reptans", "Scandens", "Grass", "Orchid", "Astera", "Gladiatus", "Fern", "Ananas", "Maranta",
    "Fanleaf", "Lemonbush", "Bamboo", "Maple", "Rare Oak", "Pipe Cactus", "Pear Cactus", "Ball Cactus",
    "Glaber", "Tigerfern", "Pitcher", "Weeper", "Multiflora", "Ridgeball",
};

/* The new species' tables, [foliage][flower - 24]. */
static int value[FOLIAGE_ROWS][NEW_COUNT];
static int price[FOLIAGE_ROWS][NEW_COUNT];
static unsigned char discovered[FOLIAGE_ROWS][NEW_COUNT];
static char names[FOLIAGE_ROWS][NEW_COUNT][0x60];

static void build_tables(void) {
    int f, k;
    for (f = 1; f <= FOLIAGES; ++f) {
        for (k = 0; k < NEW_COUNT; ++k) {
            char *name = names[f][k];
            size_t n = 0;
            const char *s;
            value[f][k] = FOLIAGE_BASE[f] + FLOWER_ADD[k];
            for (s = ADJECTIVE[k]; *s && n < 0x5E; ) name[n++] = *s++;
            name[n++] = ' ';
            for (s = NOUN[f]; *s && n < 0x5F; ) name[n++] = *s++;
            name[n] = '\0';
        }
    }
}

/* The game's own pricing (0x41DBD0) for the new species: V -+ Random(V/2),
   minus on Random(100) <= 50; with the Flower of Knowledge, V + 3*(V/4). */
static void price_species(const char *state) {
    int f, k;
    int knowledge = state != NULL && state[STATE_KNOWLEDGE] != 0;
    for (f = 1; f <= FOLIAGES; ++f) {
        for (k = 0; k < NEW_COUNT; ++k) {
            int v = value[f][k];
            int d = game_random(v / 2);
            int p = game_random(100) <= 50 ? v - d : v + d;
            price[f][k] = knowledge ? v + 3 * (v / 4) : p;
        }
    }
}

static void reset_species(void) {
    memset(discovered, 0, sizeof discovered);
    memset(price, 0, sizeof price);
}

/* ------------------------------------------------------------ the hooks */

/* Index sites: the game computed R = (foliage + K) * 26 + flower and will read
   or write [state + R*4]; for a new flower return the index of the DLL's cell. */
static int __stdcall index_fix(int flower, int index, int state, int family_price) {
    int foliage;
    UINT_PTR cell;
    if (!is_new(flower)) return index;
    foliage = (index - flower) / 26 - (family_price ? 0x37 : 0x1D);
    if (!valid_foliage(foliage)) return index;
    cell = family_price ? (UINT_PTR)&price[foliage][flower - FIRST_NEW]
                        : (UINT_PTR)&value[foliage][flower - FIRST_NEW];
    return (int)((cell - (UINT_PTR)(unsigned int)state) / 4u);
}

#include "flower_stubs.h"

static const flower_art *__cdecl art_for(int flower) {
    return is_new(flower) ? &ART[flower - FIRST_NEW] : NULL;
}

static void __cdecl mark_discovered(int foliage, int flower) {
    if (valid_foliage(foliage) && is_new(flower)) discovered[foliage][flower - FIRST_NEW] = 1;
}

static int __cdecl discovered_count(void) {
    int f, k, n = 0;
    for (f = 1; f <= FOLIAGES; ++f)
        for (k = 0; k < NEW_COUNT; ++k) n += discovered[f][k];
    return n;
}

static int __cdecl species_value(int foliage, int flower) {
    return valid_foliage(foliage) && is_new(flower) ? value[foliage][flower - FIRST_NEW] : 0;
}

static int __cdecl species_price(int foliage, int flower) {
    return valid_foliage(foliage) && is_new(flower) ? price[foliage][flower - FIRST_NEW] : 0;
}

static const char *__cdecl species_name(int foliage, int flower) {
    return valid_foliage(foliage) && is_new(flower) ? names[foliage][flower - FIRST_NEW] : "";
}

/* ----------------------------------------------------------------- sidecar */

#define SIDECAR_MAGIC 0x574C4650u      /* "PFLW" */
#define SIDECAR_VERSION 1u
typedef BOOL (WINAPI *special_folder_fn)(HWND, LPWSTR, int, BOOL);

/* "<Documents>\LDW\<exe name>\Plant Tycoon Fix Patcher Data\New Flowers <slot>.dat". */
static int sidecar_path(int slot, wchar_t *out, DWORD cap, int make_folder) {
    wchar_t exe[MAX_PATH];
    wchar_t *name, *dot;
    special_folder_fn special;
    HMODULE shell = LoadLibraryW(L"shell32.dll");
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
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
    wcscat_s(out, cap, L"\\Plant Tycoon Fix Patcher Data");
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\New Flowers ");
    {
        wchar_t digits[12];
        int i = 0, v = slot;
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 11);
        while (i) { size_t len = wcslen(out); out[len] = digits[--i]; out[len + 1] = L'\0'; }
    }
    wcscat_s(out, cap, L".dat");
    return 1;
}

typedef struct sidecar_body {
    int price[FOLIAGE_ROWS][NEW_COUNT];
    unsigned char discovered[FOLIAGE_ROWS][NEW_COUNT];
} sidecar_body;

static void __cdecl on_save(int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    DWORD header[3], written;
    static sidecar_body body;
    if (slot <= 0 || !sidecar_path(slot, path, 1024, 1)) return;
    memcpy(body.price, price, sizeof price);
    memcpy(body.discovered, discovered, sizeof discovered);
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    header[0] = SIDECAR_MAGIC;
    header[1] = SIDECAR_VERSION;
    header[2] = (DWORD)sizeof body;
    if (WriteFile(file, header, sizeof header, &written, NULL) && written == sizeof header
        && WriteFile(file, &body, sizeof body, &written, NULL) && written == sizeof body) {
        CloseHandle(file);
        MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING);
    } else {
        CloseHandle(file);
        DeleteFileW(temp);
    }
}

/* A save loaded: its new species, or (a save from before the mod, or a file
   that cannot be read, which is set aside) fresh prices and nothing found. */
static void __cdecl on_load(const char *state, int slot) {
    wchar_t path[1024];
    HANDLE file;
    DWORD header[3], got;
    int ok = 0;
    static sidecar_body body;
    if (slot <= 0) return;
    if (sidecar_path(slot, path, 1024, 0)) {
        file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (file != INVALID_HANDLE_VALUE) {
            ok = ReadFile(file, header, sizeof header, &got, NULL) && got == sizeof header
                 && header[0] == SIDECAR_MAGIC && header[1] == SIDECAR_VERSION && header[2] == sizeof body
                 && ReadFile(file, &body, sizeof body, &got, NULL) && got == sizeof body;
            CloseHandle(file);
            if (!ok) {
                wchar_t aside[1100];
                wcscpy_s(aside, 1100, path);
                wcscat_s(aside, 1100, L".unreadable");
                MoveFileExW(path, aside, MOVEFILE_REPLACE_EXISTING);
            }
        }
    }
    if (ok) {
        memcpy(price, body.price, sizeof price);
        memcpy(discovered, body.discovered, sizeof discovered);
    } else {
        reset_species();
        price_species(state);
    }
}

static void __cdecl on_delete(int slot) {
    wchar_t path[1024];
    if (slot > 0 && sidecar_path(slot, path, 1024, 0)) DeleteFileW(path);
}

/* ---------------------------------------------------------------- upgrades */

/* "Store Upgrades and Items.dll" (the store's Upgrades page) needs these flowers,
   so this DLL loads it and passes on the save, load, delete and new-game
   events for its own sidecar. */
typedef struct ftfp_upgrades_events {
    int version;
    void (__cdecl *save)(char *state, int slot);
    void (__cdecl *load)(const char *state, int slot);
    void (__cdecl *remove)(int slot);
    void (__cdecl *new_game)(void);
    void (__cdecl *pollinated)(char *pot);    /* version 2 */
} ftfp_upgrades_events;
typedef const ftfp_upgrades_events *(__stdcall *upgrades_startup_fn)(void);

static const ftfp_upgrades_events *upgrades = NULL;
EXTERN_C IMAGE_DOS_HEADER __ImageBase;

static void load_upgrades(void) {
    wchar_t path[1024];
    wchar_t *slash;
    HMODULE module;
    upgrades_startup_fn startup;
    const ftfp_upgrades_events *events;
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, path, 1024);
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(path) + 40 >= 1024) return;
    wcscat_s(path, 1024, L"Store Upgrades and Items.dll");
    if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return;
    module = LoadLibraryW(path);
    if (module == NULL) return;
    startup = (upgrades_startup_fn)GetProcAddress(module, "FtfpUpgradesStartup");
    if (startup == NULL) return;
    events = startup();
    if (events != NULL && (events->version == 1 || events->version == 2)) upgrades = events;
}

static void __cdecl on_save_all(char *state, int slot) {
    on_save(slot);
    if (upgrades) upgrades->save(state, slot);
}

static void __cdecl on_load_all(const char *state, int slot) {
    on_load(state, slot);
    if (upgrades) upgrades->load(state, slot);
}

static void __cdecl on_delete_all(int slot) {
    on_delete(slot);
    if (upgrades) upgrades->remove(slot);
}

static void __cdecl on_new_game_all(void) {
    reset_species();
    if (upgrades) upgrades->new_game();
}

/* ------------------------------------------------------------------- stubs */

static const DWORD k_art_back = SITE_ART_LOOKUP_BACK;
static const DWORD k_comments_back = SITE_VP_COMMENTS_BACK;
static const DWORD k_name_back = SITE_NAME_BACK;
static const DWORD k_mutation_back = SITE_DISCOVER_MUTATION_BACK;
static const DWORD k_age_back = SITE_DISCOVER_AGE_BACK;
static const DWORD k_count_back = SITE_DISCOVERED_COUNT_BACK;
static const DWORD k_price_back = SITE_PRICE_SETUP_BACK;
static const DWORD k_new_game_back = SITE_NEW_GAME_BACK;
static const DWORD k_save_back = SITE_SAVE_BACK;
static const DWORD k_load_back = SITE_LOAD_BACK;
static const DWORD k_remove_file = 0x00403650u;

/* 0x42D2D0(gene) (thiscall, ret 4): the flower art record, or NULL. */
__declspec(naked) static void stub_art(void) {
    __asm {
        mov eax, [esp + 4]
        cmp eax, FIRST_NEW
        jl stock
        cmp eax, LAST_NEW
        jg stock
        push ecx
        push eax
        call art_for
        add esp, 4
        pop ecx
        ret 4
    stock:
        push esi
        mov esi, [esp + 8]
        jmp k_art_back
    }
}

/* Visitor comments: edx = V, ebp = P of (foliage edx, flower ecx), state eax. */
__declspec(naked) static void stub_comments(void) {
    __asm {
        cmp ecx, FIRST_NEW
        jl stock
        cmp ecx, LAST_NEW
        jg stock
        pushad
        push dword ptr [esp + 24]      /* flower (ecx in the pushad frame) */
        push dword ptr [esp + 24]      /* foliage (edx) */
        call species_price
        add esp, 8
        mov [esp + 8], eax             /* ebp = P */
        push dword ptr [esp + 24]
        push dword ptr [esp + 24]
        call species_value
        add esp, 8
        mov [esp + 20], eax            /* edx = V */
        popad
        mov ecx, [esp + 0x14]
        jmp k_comments_back
    stock:
        lea ebp, [edx + 0x37]
        add edx, 0x1D
        imul ebp, ebp, 0x1A
        imul edx, edx, 0x1A
        add edx, ecx
        mov edx, [eax + edx * 4]
        add ebp, ecx
        mov ecx, [esp + 0x14]
        mov ebp, [eax + ebp * 4]
        jmp k_comments_back
    }
}

/* Info panel name: ecx = state, ebp = the pot's offset, eax = the stock name index. */
__declspec(naked) static void stub_name(void) {
    __asm {
        mov edx, [ecx + ebp + 0x21D8]
        cmp edx, FIRST_NEW
        jl stock
        cmp edx, LAST_NEW
        jg stock
        push eax
        push edx
        push dword ptr [ecx + ebp + 0x21D4]
        call species_name
        add esp, 8
        mov ecx, eax
        pop eax
        jmp k_name_back
    stock:
        lea ecx, [eax + ecx + 0x540CC]
        jmp k_name_back
    }
}

/* Mutation Liquid's result: ecx = foliage, edx = flower, eax = state. */
__declspec(naked) static void stub_discover_mutation(void) {
    __asm {
        cmp edx, FIRST_NEW
        jl stock
        pushad
        push edx
        push ecx
        call mark_discovered
        add esp, 8
        popad
        jmp k_mutation_back
    stock:
        lea ecx, [ecx + ecx * 2]
        lea ecx, [edx + ecx * 8]
        mov byte ptr [ecx + eax + 0x64], 1
        jmp k_mutation_back
    }
}

/* Age 24: ecx = foliage, eax = flower, [esi+0xC] = state. */
__declspec(naked) static void stub_discover_age(void) {
    __asm {
        cmp eax, FIRST_NEW
        jl stock
        pushad
        push eax
        push ecx
        call mark_discovered
        add esp, 8
        popad
        mov edx, [esi + 0xC]
        jmp k_age_back
    stock:
        lea edx, [ecx + ecx * 2]
        lea ecx, [eax + edx * 8]
        mov edx, [esi + 0xC]
        mov byte ptr [ecx + edx + 0x64], 1
        jmp k_age_back
    }
}

/* Stats screen: "Species Discovered" in [esi+0x60] counts the new species too. */
__declspec(naked) static void stub_count(void) {
    __asm {
        pushad
        call discovered_count
        add [esi + 0x60], eax
        popad
        mov edx, [esi + 0x60]
        push edx
        lea eax, [esp + 0x38]
        jmp k_count_back
    }
}

/* 0x41DBD0 (thiscall, no arguments): the game's prices, then the new species'. */
__declspec(naked) static void stock_price_setup(void) {
    __asm {
        sub esp, 8
        push ebx
        push ebp
        jmp k_price_back
    }
}

__declspec(naked) static void stub_price_setup(void) {
    __asm {
        push ecx
        call stock_price_setup
        pop ecx
        pushad
        push ecx
        call price_species
        add esp, 4
        popad
        ret
    }
}

/* 0x41EF30 new game: forget the new species first (the game then prices them). */
__declspec(naked) static void stub_new_game(void) {
    __asm {
        pushad
        call on_new_game_all
        popad
        push ebx
        push esi
        push edi
        xor ebx, ebx
        jmp k_new_game_back
    }
}

/* ------------------------------------------------------------ pollination */

/* The game's seed class (0x42CA80's rule) and trash value (0x4240A0), for a
   child whose flower the breeding rule changed. */
static int seed_class(int foliage, int flower) {
    int odd_special = foliage == 3 || foliage == 7 || foliage == 11 || foliage == 15 ||
                      flower == 3 || flower == 7 || flower == 11 || flower == 15;
    if (foliage > 17 || flower > 17) return 3;
    if (foliage % 2 == 0 || flower % 2 == 0) return 2;
    return odd_special ? 1 : 0;
}

static int seed_trash(int flower) {
    if (flower > 17) return 10;
    if (flower % 2 == 0) return 5;
    return flower == 3 || flower == 7 || flower == 11 || flower == 15 ? 3 : 1;
}

/* Breeding with a new flower uses the DS fish rule (decided, user: the same
   approach as the DS fish): the parents' average, an odd sum rounded up or
   down at random, one roll per pollination.  Stock x stock keeps the game's
   rounding up, and a pair always breeds true.  The pot holds the target
   (+0x54 foliage, +0x58 flower), the donor (+0x5C, +0x60) and the child
   (+0x64, +0x68, its seed frame +0x70 and trash value +0x74). */
static void __cdecl on_pollinated(char *pot) {
    int target = *(int *)(pot + 0x58), donor = *(int *)(pot + 0x60);
    if ((target >= FIRST_NEW || donor >= FIRST_NEW) && (target + donor) % 2 != 0 && game_random(2) == 0) {
        int foliage = *(int *)(pot + 0x64), flower = (target + donor) / 2;
        *(int *)(pot + 0x68) = flower;
        *(int *)(pot + 0x70) = foliage * 4 - 4 + seed_class(foliage, flower);
        *(int *)(pot + 0x74) = seed_trash(flower);
    }
    if (upgrades != NULL && upgrades->version >= 2) upgrades->pollinated(pot);
}

/* 0x4241B4 the tail of the pollination (esi = the pot's record). */
__declspec(naked) static void stub_pollinated(void) {
    __asm {
        pushad
        push esi
        call on_pollinated
        add esp, 4
        popad
        pop edi
        pop esi
        pop ebp
        pop ebx
        ret 8
    }
}

/* 0x41D120 save(slot) (thiscall, ret 4): the sidecar, then the game's save. */
__declspec(naked) static void stub_save(void) {
    __asm {
        pushad
        push dword ptr [esp + 0x24]    /* slot */
        push dword ptr [esp + 0x1C]    /* state (ecx in the pushad frame) */
        call on_save_all
        add esp, 8
        popad
        mov edx, [esp + 4]
        test edx, edx
        jmp k_save_back
    }
}

/* 0x41EE00 load(slot) (thiscall, ret 4, al = loaded): the game's load, then the sidecar. */
__declspec(naked) static void stock_load(void) {
    __asm {
        mov eax, 0x54074
        jmp k_load_back
    }
}

__declspec(naked) static void stub_load(void) {
    __asm {
        push ecx
        push dword ptr [esp + 8]
        call stock_load
        pop ecx
        test al, al
        jz done
        pushad
        push dword ptr [esp + 0x24]    /* slot */
        push ecx                       /* state */
        call on_load_all
        add esp, 8
        popad
    done:
        ret 4
    }
}

/* 0x41D1F0 delete(slot): `jmp 0x403650` (remove the save file); the sidecar too. */
__declspec(naked) static void stub_delete(void) {
    __asm {
        pushad
        push dword ptr [esp + 0x24]
        call on_delete_all
        add esp, 4
        popad
        jmp k_remove_file
    }
}

/* ----------------------------------------------------------------- install */

#define CODE_ADDR(f) ((const void *)(UINT_PTR)(f))
#define CODE_SITES 12
#define IMM_SITES 4
#define TOTAL_SITES (CODE_SITES + IMM_SITES + INDEX_SITE_COUNT)
static ftfp_site_write writes[TOTAL_SITES];
static int installed = 0;

#define JMP(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE9, CODE_ADDR(TO))

static void site_immediate(ftfp_site_write *w, unsigned int va, int length, const unsigned char *expect,
                           int at, int size, unsigned int new_value) {
    w->va = va;
    w->length = length;
    w->expect = expect;
    memcpy(w->bytes, expect, (size_t)length);
    if (size == 1) w->bytes[at] = (unsigned char)new_value;
    else memcpy(w->bytes + at, &new_value, 4);
}

#define IMM(W, NAME) site_immediate((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, \
                                    SITE_##NAME##_IMM_AT, SITE_##NAME##_IMM_SIZE, SITE_##NAME##_NEW)

static int prepare(void) {
    ftfp_site_write *w = writes;
    int i;
    JMP(w++, ART_LOOKUP, stub_art);
    JMP(w++, VP_COMMENTS, stub_comments);
    JMP(w++, NAME, stub_name);
    JMP(w++, DISCOVER_MUTATION, stub_discover_mutation);
    JMP(w++, DISCOVER_AGE, stub_discover_age);
    JMP(w++, DISCOVERED_COUNT, stub_count);
    JMP(w++, PRICE_SETUP, stub_price_setup);
    JMP(w++, NEW_GAME, stub_new_game);
    JMP(w++, SAVE, stub_save);
    JMP(w++, LOAD, stub_load);
    JMP(w++, DELETE, stub_delete);
    JMP(w++, POLLINATED, stub_pollinated);
    IMM(w++, DRAW_BOUND);
    IMM(w++, FLOWERING_BOUND);
    IMM(w++, MUTATION_TOP);
    IMM(w++, MUTATION_BOUNCE);
    for (i = 0; i < INDEX_SITE_COUNT; ++i) {
        ftfp_site_branch(w++, INDEX_SITES[i].va, INDEX_SITES[i].length, INDEX_SITES[i].expect, 0xE9,
                         INDEX_SITES[i].stub);
    }
    return (int)(w - writes) == TOTAL_SITES;
}

static int append_text(char *out, int at, const char *text) {
    while (*text && at < 158) out[at++] = *text++;
    return at;
}

static int append_hex(char *out, int at, unsigned int v) {
    int shift;
    at = append_text(out, at, "0x");
    for (shift = 28; shift >= 0 && at < 158; shift -= 4) out[at++] = "0123456789ABCDEF"[(v >> shift) & 0xF];
    return at;
}

/* "<game>\Plant Tycoon Fix Patcher DLLs\Unused Flowers.log". */
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
    wcscat_s(path, 1024, L"Plant Tycoon Fix Patcher DLLs\\Unused Flowers.log");
    if (installed) {
        len = append_text(line, len, "New Flowers: installed (all sites)\r\n");
    } else if (ftfp_failed_site != 0) {
        len = append_text(line, len, "New Flowers: NOT installed; the code at ");
        len = append_hex(line, len, ftfp_failed_site);
        len = append_text(line, len, " is not the stock code this build expects\r\n");
    } else {
        len = append_text(line, len, "New Flowers: NOT installed\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* Called once by the executable's startup stub, before WinMain. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        build_tables();
        if (prepare() && ftfp_install_sites(writes, TOTAL_SITES)) installed = 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    if (installed) {
        __try {
            load_upgrades();
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            upgrades = NULL;
        }
    }
    return installed;
}

int __stdcall FtfpNewFlowersInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}
