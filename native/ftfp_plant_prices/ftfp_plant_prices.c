/* Optimize Prices -- an "Optimize Prices" button in Plant Tycoon's Nursery.

   WHAT.  The Nursery is where plants sell.  The button sits on its bottom
   bar, on the brick strip at the right.  It asks "Set every discovered
   species to its best price per day?" (Yes / No, the game's own question
   box).  On Yes, every discovered species' asking price becomes the Breeding
   Guide's "best per day" price for the nursery as it is now: the species'
   value V, the Golden Berries of Wealth (visitors see prices a quarter
   lower), and the visitor limit 8 + 47 S / 78 from the score S of the
   ornaments owned, the magic plants found, the full bug collection and all
   15 sale spots filled; for a healthy, flowering, unpruned plant without
   Plant Food.  The maths is native/common/price_math.h, the port of
   src/breeding_plant.py.  Then the game's own message box says "N prices
   set."

   MAX PRICES.  Left of it on the same brick strip, a "Max Prices" button
   asks "Set every discovered species to its highest selling price?  Plants
   at this price sell much more slowly." and on Yes sets every discovered
   species to the highest asking price a visitor still buys at (pm_plant_max,
   the guide's "highest selling"): the price seen must stay below 2V.  The
   buy roll (0x436BE0) works out the price seen from the asking price
   (0x436D4B-0x436E3C); its only save-wide step is the Golden Berries of
   Wealth (state + 0x2183, a quarter off), read at the click.  Pruning, dead
   foliage, health, flowers, Plant Food and bugs are each plant's own and
   are not counted (a healthy, flowering, unpruned plant without Plant
   Food), and visitors change the odds, never the ceiling.  The Flower of
   Knowledge (0x41DBD0) only resets asking prices.  Then the same "N prices
   set."

   WHAT IT WRITES.  Only the asking price of discovered species: the cell
   the "Set species price" dialog writes (0x4305BA: state + ((foliage + 0x37)
   * 26 + flower) * 4), which the save keeps.  Undiscovered species (state +
   0x64 + foliage * 24 + flower is 0) are never written.  With Unused Flowers
   installed, its 322 species are included through "Unused Flowers.dll"
   (FtfpNewFlowersSpecies): its value, price cell and discovered flag.

   HOW.  The startup loader loads this DLL after any other companion and
   calls FtfpStartup() before WinMain.  It wraps two slots of the Nursery's
   vtable (theSellScene, 0x469730), command and activate, after checking both
   still hold the stock functions, or writes neither: activate adds the two
   buttons once, command runs them for their ids. */
#include <windows.h>
#include <string.h>
#include "../common/price_math.h"

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))

/* The Nursery scene. */
#define SCENE_STATE 0xA3C
#define SCENE_SOUND 0xA54

/* The game state's species tables (stock genes 1-23). */
#define GENE_LAST 23
#define VALUE_CELL(state, foliage, flower) AT(state, (((foliage) + 0x1D) * 26 + (flower)) * 4, int)
#define PRICE_CELL(state, foliage, flower) AT(state, (((foliage) + 0x37) * 26 + (flower)) * 4, int)
#define DISCOVERED(state, foliage, flower) AT(state, 0x64 + (foliage) * 24 + (flower), unsigned char)
#define NEW_FIRST 24
#define NEW_LAST 37

/* The visitor score S (0x43FF00). */
#define ORNAMENT_FLAGS 0x9EC            /* id 0x18 + 5 r + k at + 0xA0 r + 0x20 k */
#define ORNAMENT_ROWS 3
#define ORNAMENT_COLUMNS 5
#define ROSE_OF_JOY 0x2182
#define GOLDEN_BERRIES 0x2183
#define BUGS 0x53F4B
#define BUG_COUNT 48
#define SALE_SPOTS 15
static const int ORNAMENT_POINTS[ORNAMENT_ROWS * ORNAMENT_COLUMNS] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 4, 4, 4, 4, 1, 4 };
static const int OTHER_MAGIC[5] = { 0x2180, 0x2181, 0x2183, 0x2184, 0x2185 };

#define BUTTON_ID 9
#define BUTTON_X 620
#define BUTTON_Y 561
#define BUTTON_IMAGE "optimize_prices_button.png"
#define MAX_BUTTON_ID 10
#define MAX_BUTTON_X 449                /* 449-611 x 561-599: the brick strip left of Optimize Prices */
#define MAX_BUTTON_Y 561
#define MAX_BUTTON_IMAGE "max_prices_button.png"
#define SOUND_BUTTON 0xC

typedef void *(__cdecl *new_fn)(unsigned int size);
typedef void (__fastcall *file_button_fn)(void *button, int edx, int id, const char *file, int x, int y, void *parent, int zero);
typedef void (__fastcall *add_control_fn)(void *scene, int edx, void *control);
typedef void (__fastcall *sound_fn)(void *sound, int edx, int id);
typedef int (__fastcall *command_fn)(void *scene, int edx, int msg, int id);
typedef void (__fastcall *activate_fn)(void *scene, int edx, int on);
typedef int (__stdcall *installed_fn)(void);
typedef int (__stdcall *new_species_fn)(int foliage, int flower, int *value, int **price);

static const new_fn game_new = (new_fn)0x0044E894u;
static const file_button_fn file_button = (file_button_fn)0x00401AA0u;
static const add_control_fn add_control = (add_control_fn)0x0040B400u;
static const sound_fn play_sound = (sound_fn)0x0044A580u;

#define SELL_VT_COMMAND 0x0046973Cu
#define SELL_COMMAND_STOCK 0x004351C0u
#define SELL_VT_ACTIVATE 0x00469754u
#define SELL_ACTIVATE_STOCK 0x004360D0u

static command_fn next_command = NULL;
static activate_fn next_activate = NULL;
static void *button_scene = NULL;
static int installed = 0;

/* ------------------------------------------------------------ the prices */

static int visitor_score(const char *state) {
    int r, k, i, score = 2 * SALE_SPOTS, bugs = 0;
    for (r = 0; r < ORNAMENT_ROWS; ++r) {
        for (k = 0; k < ORNAMENT_COLUMNS; ++k) {
            if (AT(state, ORNAMENT_FLAGS + 0xA0 * r + 0x20 * k, unsigned char)) score += ORNAMENT_POINTS[r * ORNAMENT_COLUMNS + k];
        }
    }
    if (AT(state, ROSE_OF_JOY, unsigned char)) score += 4;
    for (i = 0; i < 5; ++i) {
        if (AT(state, OTHER_MAGIC[i], unsigned char)) score += 2;
    }
    for (i = 0; i < BUG_COUNT; ++i) {
        if (AT(state, BUGS + i, unsigned char)) ++bugs;
    }
    if (bugs == BUG_COUNT) score += 4;
    return score;
}

/* "Unused Flowers.dll", when it is installed: its species lookup. */
static new_species_fn new_species(void) {
    HMODULE flowers = GetModuleHandleW(L"Unused Flowers.dll");
    installed_fn flowers_installed;
    if (flowers == NULL) return NULL;
    flowers_installed = (installed_fn)GetProcAddress(flowers, "FtfpNewFlowersInstalled");
    if (flowers_installed == NULL || !flowers_installed()) return NULL;
    return (new_species_fn)GetProcAddress(flowers, "FtfpNewFlowersSpecies");
}

static int set_price(int *cell, int v, int golden_berries, int score, int max) {
    int best;
    if (cell == NULL || v <= 0) return 0;
    best = max ? pm_plant_max(v, golden_berries) : pm_plant_best(v, golden_berries, score);
    if (best <= 0) return 0;
    *cell = best;
    return 1;
}

/* Sets every discovered species to its best price per day, or with `max`
   to its highest selling price; returns how many. */
static int set_prices(char *state, int max) {
    new_species_fn flowers = new_species();
    int golden_berries = AT(state, GOLDEN_BERRIES, unsigned char) != 0;
    int score = visitor_score(state);
    int foliage, flower, set = 0;
    for (foliage = 1; foliage <= GENE_LAST; ++foliage) {
        for (flower = 1; flower <= GENE_LAST; ++flower) {
            if (DISCOVERED(state, foliage, flower)) {
                set += set_price(&PRICE_CELL(state, foliage, flower), VALUE_CELL(state, foliage, flower),
                                 golden_berries, score, max);
            }
        }
        for (flower = NEW_FIRST; flowers != NULL && flower <= NEW_LAST; ++flower) {
            int v = 0, *cell = NULL;
            if (flowers(foliage, flower, &v, &cell) == 1) set += set_price(cell, v, golden_berries, score, max);
        }
    }
    return set;
}

/* ---------------------------------------------------------- the dialogs */

/* The game's own message box, the one "Are you sure you want to restart the
   current game?" uses (0x42A5FD-0x42A646): 0x42AB50 builds it from a string
   id (its second argument 1 for two buttons, 0 for OK alone), 0x401C90 runs
   it until a button is clicked (0 for the first) and 0x42AAA0 takes it down.
   Its text and button labels come from the string table (0x44CA70: entry =
   [0x493CC0 + id*4], text = the entry's +0xC override if set, else +8), so
   while it is built the restart question shows this text and OK / Cancel
   read Yes / No.  The same box as Sort Seeds' question. */
typedef void (__fastcall *question_fn)(void *dialog, int edx, int id, int a, int b, int c, int d);
typedef int (__fastcall *run_modal_fn)(void *dialog, int edx, void *parent, int zero);
typedef void (__fastcall *dialog_done_fn)(void *dialog, int edx);
static const question_fn build_question = (question_fn)0x0042AB50u;
static const run_modal_fn run_modal = (run_modal_fn)0x00401C90u;
static const dialog_done_fn dialog_done = (dialog_done_fn)0x0042AAA0u;
#define STRING_ENTRIES 0x00493CC0u
#define STRING_LAST 0x1B2
#define STR_YES 0x10
#define STR_NO 0x11
#define STR_OK 0x12
#define STR_CANCEL 0x13
#define STR_RESTART_QUESTION 0x3E

static const char QUESTION[] = "Set every discovered species\nto its best price per day?";
static const char MAX_QUESTION[] = "Set every discovered species\nto its highest selling price?\n"
                                   "Plants at this price sell\nmuch more slowly.";

static char *string_entry(int id) {
    char *entry;
    if (id < 1 || id > STRING_LAST) return NULL;
    entry = *(char **)(UINT_PTR)(STRING_ENTRIES + (unsigned int)id * 4u);
    return entry != NULL && AT(entry, 0, int) == id ? entry : NULL;
}

static const char *string_text(int id) {
    char *entry = string_entry(id);
    if (entry == NULL) return NULL;
    return AT(entry, 0xC, const char *) ? AT(entry, 0xC, const char *) : AT(entry, 8, const char *);
}

/* The box with `text`; with yes_no, Yes / No buttons, else OK.  1 when the
   first button was clicked. */
static int ask(void *scene, const char *text, int yes_no) {
    static unsigned char dialog[0x1000];           /* the stock code keeps it on its stack */
    static const int ids[3] = { STR_RESTART_QUESTION, STR_OK, STR_CANCEL };
    const char *texts[3];
    const char *saved[3];
    char *entries[3];
    int i, count = yes_no ? 3 : 1, answer;
    texts[0] = text;
    texts[1] = string_text(STR_YES);
    texts[2] = string_text(STR_NO);
    for (i = 0; i < count; ++i) {
        entries[i] = string_entry(ids[i]);
        if (entries[i] == NULL || texts[i] == NULL) return 0;
    }
    for (i = 0; i < count; ++i) {
        saved[i] = AT(entries[i], 0xC, const char *);
        AT(entries[i], 0xC, const char *) = texts[i];
    }
    __try {
        memset(dialog, 0, sizeof dialog);
        build_question(dialog, 0, STR_RESTART_QUESTION, yes_no ? 1 : 0, yes_no ? 1 : 0, 0, 0);
    } __finally {
        for (i = 0; i < count; ++i) AT(entries[i], 0xC, const char *) = saved[i];
    }
    answer = run_modal(dialog, 0, scene, 0);
    dialog_done(dialog, 0);
    return answer == 0;
}

static void tell_count(void *scene, int set) {
    char text[48];
    char digits[12];
    int n = 0, d = 0, value = set;
    const char *tail = set == 1 ? " price set." : " prices set.";
    do { digits[d++] = (char)('0' + value % 10); value /= 10; } while (value && d < 11);
    while (d) text[n++] = digits[--d];
    while (*tail) text[n++] = *tail++;
    text[n] = '\0';
    ask(scene, text, 0);
}

/* ------------------------------------------------------------- the scene */

/* A button's click: the question, the prices, the count; `max` picks Max
   Prices. */
static void run_button(void *scene, int max) {
    char *state = AT(scene, SCENE_STATE, char *);
    if (state == NULL || !ask(scene, max ? MAX_QUESTION : QUESTION, 1)) return;
    tell_count(scene, set_prices(state, max));
}

static int __fastcall scene_command(void *scene, int edx, int msg, int id) {
    if (msg == 8 && (id == BUTTON_ID || id == MAX_BUTTON_ID)) {
        play_sound(AT(scene, SCENE_SOUND, void *), 0, SOUND_BUTTON);
        __try {
            run_button(scene, id == MAX_BUTTON_ID);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
        }
        return 1;
    }
    return next_command(scene, edx, msg, id);
}

static int add_button(void *scene, int id, const char *image, int x, int y) {
    void *b = game_new(0x14);
    if (b == NULL) return 0;
    file_button(b, 0, id, image, x, y, scene, 0);
    add_control(scene, 0, b);
    return 1;
}

/* Optimize Prices, then Max Prices, once per Nursery. */
static void __fastcall scene_activate(void *scene, int edx, int on) {
    next_activate(scene, edx, on);
    if ((on & 0xFF) && button_scene != scene) {
        __try {
            if (add_button(scene, BUTTON_ID, BUTTON_IMAGE, BUTTON_X, BUTTON_Y)) button_scene = scene;
        } __except (EXCEPTION_EXECUTE_HANDLER) {
        }
        if (button_scene == scene) {
            __try {
                add_button(scene, MAX_BUTTON_ID, MAX_BUTTON_IMAGE, MAX_BUTTON_X, MAX_BUTTON_Y);
            } __except (EXCEPTION_EXECUTE_HANDLER) {
            }
        }
    }
}

/* ---------------------------------------------------------------- install */

static int slot_holds(unsigned int va, unsigned int stock) {
    MEMORY_BASIC_INFORMATION info;
    if (VirtualQuery((const void *)(UINT_PTR)va, &info, sizeof info) != sizeof info || info.State != MEM_COMMIT) return 0;
    return *(const DWORD *)(UINT_PTR)va == stock;
}

static int write_slot(unsigned int va, const void *to) {
    DWORD old, ignored;
    if (!VirtualProtect((void *)(UINT_PTR)va, 4, PAGE_READWRITE, &old)) return 0;
    *(DWORD *)(UINT_PTR)va = (DWORD)(UINT_PTR)to;
    VirtualProtect((void *)(UINT_PTR)va, 4, old, &ignored);
    return 1;
}

static void write_install_log(void) {
    wchar_t path[1024];
    const char *line = installed ? "Optimize Prices: installed\r\n"
                                 : "Optimize Prices: NOT installed (the Nursery is not the stock one)\r\n";
    DWORD n = GetModuleFileNameW(NULL, path, 1024), written;
    wchar_t *slash;
    HANDLE file;
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(path) + 64 >= 1024) return;
    wcscat_s(path, 1024, L"Plant Tycoon Fix Patcher DLLs\\Optimize Prices.log");
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)strlen(line), &written, NULL);
    CloseHandle(file);
}

/* Called once before WinMain by the startup loader, after any other companion. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        if (slot_holds(SELL_VT_COMMAND, SELL_COMMAND_STOCK) && slot_holds(SELL_VT_ACTIVATE, SELL_ACTIVATE_STOCK)) {
            next_command = (command_fn)(UINT_PTR)SELL_COMMAND_STOCK;
            next_activate = (activate_fn)(UINT_PTR)SELL_ACTIVATE_STOCK;
            if (write_slot(SELL_VT_COMMAND, (const void *)(UINT_PTR)scene_command)) {
                if (write_slot(SELL_VT_ACTIVATE, (const void *)(UINT_PTR)scene_activate)) installed = 1;
                else write_slot(SELL_VT_COMMAND, (const void *)(UINT_PTR)SELL_COMMAND_STOCK);
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    return installed;
}

int __stdcall FtfpOptimizePricesInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}
