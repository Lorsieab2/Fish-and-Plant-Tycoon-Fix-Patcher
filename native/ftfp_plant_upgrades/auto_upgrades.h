/* Automatic Sprinklers and the Auto-Healer -- two permanent items on the
   Plant Tycoon Upgrades view (included by ftfp_plant_upgrades.c, after the
   extra greenhouses' item).

   WHAT.  Each costs $10,000 ($0 with Free upgrades), bought once with the
   same Yes / No as Add Money and the extra greenhouses, and works on every
   potted plant of every greenhouse (Greenhouse 1 and, with the extra
   greenhouses setting, Greenhouses 2-6, on screen or not):
     * Automatic Sprinklers keep each live plant's water at WATER_TARGET;
     * the Auto-Healer clears each live plant's pests and keeps its health at
       100.  A dead plant (health 0) is never touched: that is the Revival
       Potion's job.

   THE GAME'S RULES (the plant update 0x42DF80; its age-unit loop
   0x42E134-0x42E2D9 runs once per age unit, every unit of a catch-up or a
   Time Warp one by one; edi / [esi + 8] is the pot record):
     * water is the pot's +0x20, 0-1000 (clamped only after the loop,
       0x42CCF0).  Each unit it drops by 6 + difficulty - the water upgrade
       (0x41DE00: Tap 0, Filtered 1, Isola 2), 3 less for the cacti (foliage
       15, 16, 17, 22) (0x42E197-0x42E1DE);
     * too dry: water below 100 after that drop costs 1 health and, before age
       21, 50% a unit of size -1 (0x42E1E4); the class health gain is skipped
       while water is below 100 (0x42CCE0);
     * too wet: water above 900 triples the pest odds (0x42CB9E), read at the
       top of the unit by the infestation roll (vtable +0x0C, 0x42CAA0).  Nothing
       else reads the water: there is no other overwatering harm;
     * so the best level is anything from 100 + the largest drop (8) to 900.
       The sprinklers write WATER_TARGET (800, high in that band and below the
       900 pest line: the owner, 2026-10-30) at the top of every unit, before
       the roll reads it, and after the loop; the next drop leaves 792 or more.
       Nothing in the update raises the water (only the watering can, between
       updates), and the next unit's top writes 800 again before its roll, so
       the roll never sees more than 900 while they run;
     * pests: +0x28 (1 = infested, set by the roll at 0x42CBCF with +0x3C).  An
       infested plant loses 1 + difficulty health a unit, 50% a unit of size -1
       (0x42E144-0x42E16B), and gains no health (0x42CCDA).  Insect Poison clears
       +0x28 and counts one Plants Cured (state + 0x40, 0x42685D); the Fruit of
       Life clears it every unit (0x42E18B);
     * health: +0x24, 0-100 (clamped after the loop).  At 0 the plant dies
       (0x42E244): +0x3C = 1, and every later update returns at once (0x42DFA6).
       The status panel names only Dead, Infested and Unhealthy (below 30,
       0x4284CE-0x428587): there is no other disease.  Dead branches (+0xA8 part
       records, type 4) come from the age-7 roll, once, as part of the plant's
       growth, not from its health: the Auto-Healer leaves them (the Radioactive
       Plant Formula brings them back);
     * old age (0x42E219) still ends a plant's life; the Auto-Healer does not
       stop it (the "no old age plant deaths" setting does).
   The Auto-Healer, at the top of every unit and after the loop: pests
   cleared (one Plants Cured each, as Insect Poison counts) and health 100.
   A plant that dies during the loop (old age) is left dead for the rest of
   that update: the stock loop can let a later unit's gain lift it above 0,
   which this never turns into a revival.

   OWNED.  Per save slot, "<save folder>\Plant Tycoon Fix Patcher Data\Auto
   Upgrades <slot>.dat", written with the save, atomically (a .tmp file
   renamed over the old one); a new game owns neither; an unreadable file is
   set aside (".unreadable") and owns neither. */

#define AUTO_PRICE 10000
#define AUTO_ITEMS 2
#define AUTO_SPRINKLERS 0
#define AUTO_HEALER 1
#define WATER_TARGET 800
#define WATER_WET 900                       /* above this the pest odds triple (0x42CB9E) */
#define POT_WATER 0x20
#define POT_PESTS 0x28
#define FULL_HEALTH 100
#define S_PLANTS_CURED 0x40                 /* the statistic Insect Poison adds to (0x42686A) */
#define AUTO_SPRINKLERS_FRAME 32            /* chemicals sheet row 16 */
#define AUTO_HEALER_FRAME 34                /* row 17 */

typedef struct auto_item {
    const char *title;
    const wchar_t *caption, *description;
    int frame, x, y;
    RECT rect;
} auto_item;

/* Sprinklers on the tool shelf under the Extra Greenhouse (the stock tool column 3, row 2),
   the Auto-Healer on the chemicals shelf beside the Formula Bomb.  The sprinklers' art is visible
   over x + 6 .. x + 64 of its 70 px cell, so at x 397 it spans 403-460, centred on the Extra
   Greenhouse's art (414-450, centre 432): clear of the Seventh Seed Box's art (to 397) and the
   Fifth's (from 468); at 409 it ran to 472, into the Fifth's.  Its click rectangle (403-461,
   114-174) starts below the greenhouse's (to y 113: inside() counts both edges). */
#define AUTO_SPRINKLERS_X 397
static const auto_item AUTO_ITEM[AUTO_ITEMS] = {
    { "Automatic Sprinklers", L"Automatic Sprinklers",
      L"Automatically waters all pots in the greenhouse. Optimizes water levels for minimal pest infestations "
      L"and problems.", AUTO_SPRINKLERS_FRAME, AUTO_SPRINKLERS_X, 111, { 403, 114, 461, 174 } },
    { "Auto-Healer", L"Auto-Healer",
      L"Magically cures all diseases from plants and restores them to full health. Works in every greenhouse.",
      AUTO_HEALER_FRAME, 655, 116, { 667, 124, 712, 176 } },
};

static volatile unsigned char auto_owned[AUTO_ITEMS];
static char *auto_tip[AUTO_ITEMS];
static char auto_tip_text[AUTO_ITEMS][96];
static volatile unsigned char auto_died = 0;     /* the plant being updated died during this update */

/* ------------------------------------------------------------ the effect */

__declspec(noinline) static void auto_tend(char *state, char *pot) {
    if (AT(pot, POT_HEALTH, int) <= 0) {
        auto_died = 1;                               /* dead: never watered, healed or revived */
        return;
    }
    if (auto_died) return;
    if (auto_owned[AUTO_SPRINKLERS]) AT(pot, POT_WATER, int) = WATER_TARGET;
    if (auto_owned[AUTO_HEALER]) {
        if (AT(pot, POT_PESTS, int) != 0) {
            AT(pot, POT_PESTS, int) = 0;
            if (state != NULL) ++AT(state, S_PLANTS_CURED, int);
        }
        AT(pot, POT_HEALTH, int) = FULL_HEALTH;
    }
}

/* The top of each age unit (edi = the pot). */
static void __cdecl auto_unit(char *plant, char *pot) {
    if (auto_owned[AUTO_SPRINKLERS] || auto_owned[AUTO_HEALER]) auto_tend(AT(plant, 0xC, char *), pot);
}

/* After the unit loop (esi = the plant object), whether any unit ran or not. */
static void __cdecl auto_units_done(char *plant) {
    char *pot = plant != NULL ? AT(plant, 8, char *) : NULL;
    if (pot != NULL && (auto_owned[AUTO_SPRINKLERS] || auto_owned[AUTO_HEALER])) auto_tend(AT(plant, 0xC, char *), pot);
    auto_died = 0;
}

/* At once on a purchase: every planted, live pot of Greenhouse 1 and the extra greenhouses bought. */
typedef char *(__cdecl *extra_pot_fn)(int g, int k);

__declspec(noinline) static void auto_tend_all(char *state) {
    HMODULE extra = GetModuleHandleW(L"Extra Greenhouses.dll");
    extra_pot_fn extra_pot = extra ? (extra_pot_fn)GetProcAddress(extra, "FtfpExtraGreenhousesPot") : NULL;
    typedef int (__cdecl *owned_fn)(void);
    owned_fn extra_owned_fn = extra ? (owned_fn)GetProcAddress(extra, "FtfpExtraGreenhousesOwned") : NULL;
    int g, k, greenhouses = 1;
    if (extra_pot != NULL && extra_owned_fn != NULL && extra_owned_fn() > 0) greenhouses += extra_owned_fn();
    for (g = 0; g < greenhouses; ++g) {
        for (k = 0; k < POTS; ++k) {
            char *pot = extra_pot != NULL ? extra_pot(g, k) : (g == 0 ? POT(state, k) : NULL);
            if (pot == NULL || AT(pot, 0x4C, int) == 0 || !AT(pot, 0x38, unsigned char)) continue;
            auto_died = 0;
            auto_tend(state, pot);
        }
    }
    auto_died = 0;
}

/* ------------------------------------------------------------ the store */

static void auto_tip_set(int i) {
    if (auto_owned[i]) sprintf_s(auto_tip_text[i], 96, "%s\nOwned, click to unpurchase", AUTO_ITEM[i].title);
    else sprintf_s(auto_tip_text[i], 96, "%s\nPrice: $ %i", AUTO_ITEM[i].title, price(AUTO_PRICE));
}

__declspec(noinline) static void auto_make_tips(char *scene) {
    int i;
    for (i = 0; i < AUTO_ITEMS; ++i) {
        char *tip;
        if (auto_tip[i] != NULL) continue;
        tip = (char *)game_new(0x10);
        if (tip == NULL) return;
        auto_tip_set(i);
        tooltip_ctor(tip, 0, 90 + i, &AUTO_ITEM[i].rect, scene, auto_tip_text[i], TOOLTIP_FONT, 0, 0);
        add_control(scene, 0, tip);
        auto_tip[i] = tip;
    }
}

__declspec(noinline) static void auto_set_tips(int shown) {
    int i;
    for (i = 0; i < AUTO_ITEMS; ++i) {
        if (auto_tip[i] == NULL) continue;
        auto_tip_set(i);
        tooltip_text(auto_tip[i], 0, auto_tip_text[i], TOOLTIP_COLOUR, 0, 0);
        tip_place(auto_tip[i], &AUTO_ITEM[i].rect, shown);
    }
}

static void auto_draw(void *mgr) {
    int i;
    for (i = 0; i < AUTO_ITEMS; ++i) {
        const auto_item *it = &AUTO_ITEM[i];
        draw_shadow(mgr, 0, SHEET_SHADOW, it->x + 0x19, it->y + 0x1E, 1.0f, 100);
        draw_sprite(mgr, 0, SHEET_CHEMICALS, it->frame, it->x, it->y, 1.0f, 100, 1);
        if (auto_owned[i]) draw_shadow(mgr, 0, SHEET_TICK, it->x + 19, it->y + 22, 1.0f, 100);
    }
}

__declspec(noinline) static void auto_buy(char *scene, int i) {
    char *state = SCENE_STATE(scene);
    wchar_t text[400];
    int cost = price(AUTO_PRICE);
    if (state == NULL) return;
    if (auto_owned[i]) {
        /* Unpurchase (the owner, 2026-10-30): Yes switches it off at once, no refund; buying it
           again costs the full price.  Nothing it did is undone.  The sidecar keeps it with the
           next save, as it keeps a purchase. */
        swprintf_s(text, 400, L"Unpurchase %s? It switches off. There is no refund, and buying it again costs "
                   L"the full price.", AUTO_ITEM[i].caption);
        if (tw_confirm_as(AUTO_ITEM[i].caption, text)) {
            auto_owned[i] = 0;
            play_sound(SCENE_SOUND(scene), 0, SOUND_BUTTON);
            auto_set_tips(1);
        }
        return;
    }
    if (AT(state, S_CASH, unsigned int) < (unsigned int)cost) {
        swprintf_s(text, 400, L"You can't afford to buy this yet! %s costs $10,000.", AUTO_ITEM[i].caption);
        tw_tell_as(AUTO_ITEM[i].caption, text);
        return;
    }
    swprintf_s(text, 400, L"Buy %s for $%d?\n\n%s", AUTO_ITEM[i].caption, cost, AUTO_ITEM[i].description);
    if (!tw_confirm_as(AUTO_ITEM[i].caption, text)) return;
    if (AT(state, S_CASH, unsigned int) < (unsigned int)cost || auto_owned[i]) return;
    add_cash(state, 0, -cost);
    auto_owned[i] = 1;
    play_sound(SCENE_SOUND(scene), 0, SOUND_BUTTON);
    auto_tend_all(state);
    auto_set_tips(1);
}

static void auto_click(char *scene, int x, int y) {
    int i;
    for (i = 0; i < AUTO_ITEMS; ++i) {
        if (inside(&AUTO_ITEM[i].rect, x, y)) auto_buy(scene, i);
    }
}

/* ----------------------------------------------------------------- sidecar */

typedef BOOL (WINAPI *auto_special_fn)(HWND, LPWSTR, int, BOOL);
#define AUTO_MAGIC 0x55415050u              /* "PPAU" */
#define AUTO_VERSION 1u

/* "<Documents>\LDW\<exe name>\Plant Tycoon Fix Patcher Data\Auto Upgrades <slot>.dat". */
static int auto_path(int slot, wchar_t *out, DWORD cap, int make_folder) {
    wchar_t exe[MAX_PATH];
    wchar_t *name, *dot;
    auto_special_fn special;
    HMODULE shell = LoadLibraryW(L"shell32.dll");
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
    wchar_t digits[12];
    int d = 0, v = slot;
    if (shell == NULL || n == 0 || n >= MAX_PATH || slot <= 0) return 0;
    special = (auto_special_fn)GetProcAddress(shell, "SHGetSpecialFolderPathW");
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
    wcscat_s(out, cap, L"\\Auto Upgrades ");
    do { digits[d++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && d < 11);
    while (d) { size_t len = wcslen(out); out[len] = digits[--d]; out[len + 1] = L'\0'; }
    wcscat_s(out, cap, L".dat");
    return 1;
}

__declspec(noinline) static void auto_save(int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    DWORD body[4], written;
    int ok;
    if (!auto_path(slot, path, 1024, 1)) return;
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    body[0] = AUTO_MAGIC;
    body[1] = AUTO_VERSION;
    body[2] = auto_owned[AUTO_SPRINKLERS];
    body[3] = auto_owned[AUTO_HEALER];
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    ok = WriteFile(file, body, sizeof body, &written, NULL) && written == sizeof body && FlushFileBuffers(file);
    CloseHandle(file);
    if (ok) MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    else DeleteFileW(temp);
}

__declspec(noinline) static void auto_load(int slot) {
    wchar_t path[1024];
    HANDLE file;
    DWORD body[4], got = 0, extra = 0;
    unsigned char probe;
    int ok;
    auto_owned[AUTO_SPRINKLERS] = auto_owned[AUTO_HEALER] = 0;
    if (!auto_path(slot, path, 1024, 0)) return;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;                    /* a save from before: owns neither */
    ok = ReadFile(file, body, sizeof body, &got, NULL) && got == sizeof body
         && ReadFile(file, &probe, 1, &extra, NULL) && extra == 0
         && body[0] == AUTO_MAGIC && body[1] == AUTO_VERSION && body[2] <= 1 && body[3] <= 1;
    CloseHandle(file);
    if (ok) {
        auto_owned[AUTO_SPRINKLERS] = (unsigned char)body[2];
        auto_owned[AUTO_HEALER] = (unsigned char)body[3];
    } else {
        wchar_t aside[1100];
        wcscpy_s(aside, 1100, path);
        wcscat_s(aside, 1100, L".unreadable");
        MoveFileExW(path, aside, MOVEFILE_REPLACE_EXISTING);
    }
}

__declspec(noinline) static void auto_delete(int slot) {
    wchar_t path[1024];
    if (auto_path(slot, path, 1024, 0)) DeleteFileW(path);
}

__declspec(noinline) static void auto_new_game(void) {
    auto_owned[AUTO_SPRINKLERS] = auto_owned[AUTO_HEALER] = 0;
    auto_died = 0;
}

/* ------------------------------------------------------------------- stubs */

static const DWORD k_unit_back = SITE_UNIT_TOP_BACK;
static const DWORD k_unit_infested = 0x0042E144u;        /* the stock jne's target */
static const DWORD k_units_done_back = SITE_UNITS_DONE_BACK;

/* 0x42E134, the top of each age unit: edi = the pot, ebp = 0. */
__declspec(naked) static void stub_unit_top(void) {
    __asm {
        pushad
        push edi
        push esi
        call auto_unit
        add esp, 8
        popad
        cmp dword ptr [edi + 0x28], ebp
        jne infested
        jmp k_unit_back
    infested:
        jmp k_unit_infested
    }
}

/* 0x42E2DF, after the unit loop: esi = the plant object. */
__declspec(naked) static void stub_units_done(void) {
    __asm {
        pushad
        push esi
        call auto_units_done
        add esp, 4
        popad
        mov ecx, [esi + 0xC]
        cmp byte ptr [ecx + 0x53F27], 0
        jmp k_units_done_back
    }
}
