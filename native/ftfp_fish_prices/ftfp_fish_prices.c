/* Optimize Prices -- an "Optimize Prices" button and a "Max Prices" button
   on Fish Tycoon's Species Chart and on its Fish Store screen.

   WHAT.  The Species Chart is where the player sets a species' asking price
   (its arrows and keypad).  The button sits on its bottom bar, left of Done.
   The Species Chart opens only with a fish in the isolation tank, so the
   same button is also on the Fish Store screen (the sale scene, opened with
   Sell Fish on the tank screen), on its bottom bar between "Your cash" and
   Done; a click there does exactly what the chart's does.  It asks "Set every discovered species to its best price per day?" (Yes /
   No, the game's own question box).  On Yes, every discovered species' asking
   price becomes the Breeding Guide's "best per day" price for the shop as it
   is now: the species' base price B (entry + 0x24, which already has the
   Advertising rises), the ornaments owned, the Golden Seahorse, the
   Advertising level, and a full selling tank (21 adults, or 30 with Bigger
   tanks: the exe's own slot bound says which).  The maths is
   native/common/price_math.h, the port of src/breeding_fish.py.  Then the
   game's own message box says "N prices set."

   MAX PRICES.  Left of it on both bars, a "Max Prices" button asks "Set
   every discovered species to its highest selling price?  Fish at this
   price sell much more slowly." and on Yes sets every discovered species to
   the highest asking price a customer still buys at, 2B - 1 (pm_fish_max,
   the guide's "highest selling").  The sale roll (0x424240) compares the
   asking price only with the species' base price B (2B or more never sells,
   0x4243DC-0x4243EA): ornaments, the Golden Seahorse and the Advertising
   crowd change the odds, never this ceiling; the Advertising research
   raises B itself, which is read at the click.  Then the same "N prices
   set."

   WHAT IT WRITES.  Only the asking price of discovered species (entry +
   0x20, the cell the chart's arrows and keypad write, which the save
   keeps).  An undiscovered species (price -1, or no entry) is never
   written.  With DS Exclusive Fish installed, its species are included: the
   PC bodies' DS fins are in the stock table's spare columns, and the DS
   bodies' rows come from "DS Exclusive Fish.dll" (FtfpDsFishEntry), the
   cells the game's own index arithmetic reaches.

   HOW.  The startup loader loads this DLL after any other companion and
   calls FtfpStartup() before WinMain.  It wraps four vtable slots, command
   and activate of the Species Chart (0x443C90) and of the Fish Store
   (0x443B08), after checking all four still hold the stock functions, or
   writes none.  No other companion writes these slots (Extra Tanks changes
   calls inside the sale scene's code -- its roll, crowd, pictures and "Fish
   for sale" text -- which the stock functions called here still run).
   Activate adds the two buttons once per screen, command runs them for
   their ids.  The button is a stock image button: the game draws it and
   routes its click to command. */
#include <windows.h>
#include <string.h>
#include "../common/price_math.h"

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))

/* The species table: 21 PC body rows of 31 fin entries of 40 bytes. */
#define SPECIES_BASE 0x14B40
#define ROW_STRIDE 31
#define ENTRY_SIZE 40
#define ENTRY_PRICE 0x20
#define ENTRY_BASE 0x24
#define PC_LAST 20
#define DS_FIRST 23
#define DS_LAST 29

/* The shop (the selling scene's crowd, 0x423E00): ownership dwords. */
#define OWN_SEAHORSE 0x154
#define OWN_ORNAMENT 0x1B8              /* six ornaments, 0x14 apart */
#define ORNAMENTS 6
#define ORNAMENT_STRIDE 0x14
#define ADVERTISING 0x26C
#define TANK_BOUND_VA 0x00419C74u       /* AddFish's `cmp eax, 0x15`: 0x1E with Bigger tanks */

#define BUTTON_ID 7
#define BUTTON_X 524
#define BUTTON_Y 546
#define BUTTON_IMAGE "OptimizePricesButton.png"
#define MAX_BUTTON_ID 8
#define MAX_BUTTON_X 400                /* 400-519 x 546-598: the bar left of Optimize Prices */
#define MAX_BUTTON_Y 546
#define MAX_BUTTON_IMAGE "MaxPricesButton.png"
#define SOUND_CLICK 1

typedef void *(__cdecl *new_fn)(unsigned int size);
typedef void *(__cdecl *getter_fn)(void);
typedef int (__fastcall *this0_fn)(void *self, void *edx);
typedef int (__fastcall *this1_fn)(void *self, void *edx, int a);
typedef int (__fastcall *this2_fn)(void *self, void *edx, int a, int b);
typedef int (__fastcall *this6_fn)(void *self, void *edx, int a, int b, int c, int d, int e, int f);
typedef int (__fastcall *command_fn)(void *scene, void *edx, int msg, int id);
typedef void (__fastcall *activate_fn)(void *scene, void *edx, int on);
typedef int (__stdcall *installed_fn)(void);
typedef unsigned char *(__stdcall *ds_entry_fn)(char *state, int body, int fin);

#define GAME(T, VA) ((T)(UINT_PTR)(VA))
#define OPERATOR_NEW GAME(new_fn, 0x0042A793u)
#define SOUND_MANAGER GAME(getter_fn, 0x00425120u)
#define SOUND_GET GAME(this1_fn, 0x004251A0u)          /* (id) -> sound */
#define BUTTON_INIT GAME(this6_fn, 0x00401B10u)        /* (id, image, x, y, handler, 0) */
#define BUTTON_SOUND GAME(this2_fn, 0x004015E0u)       /* (sound, 0) */
#define ADD_CONTROL GAME(this1_fn, 0x0040A9E0u)
#define DIALOG_INIT GAME(this2_fn, 0x004221A0u)        /* (string id, 1 = Yes / No, 0 = OK) */
#define DIALOG_RUN GAME(this2_fn, 0x00401D00u)         /* (parent, 0) -> 0 = the first button */
#define DIALOG_FREE GAME(this0_fn, 0x00422440u)

#define SPECIES_VT_COMMAND 0x00443C9Cu
#define SPECIES_COMMAND_STOCK 0x00425B00u
#define SPECIES_VT_ACTIVATE 0x00443CB4u
#define SPECIES_ACTIVATE_STOCK 0x00401C90u

/* The Fish Store, the sale scene (vtable 0x443B08, built at 0x424500): its
   one button is Done (1, at 701, 547); its command is the chart's own
   0x425B00 (Done goes back to the tank), its activate 0x424160 runs the
   scene's opening 0x423E00 (customers, pictures, the "Fish for sale" count);
   its impl (scene + 8) keeps the game state at +0x70 (0x4241B1). */
#define SALE_VT_COMMAND 0x00443B14u
#define SALE_COMMAND_STOCK 0x00425B00u
#define SALE_VT_ACTIVATE 0x00443B2Cu
#define SALE_ACTIVATE_STOCK 0x00424160u
#define SALE_IMPL_STATE 0x70
#define SALE_BUTTON_ID 7
#define SALE_BUTTON_X 544               /* 544-693 x 547-596: the bar between "Your cash" (to 300) and Done */
#define SALE_BUTTON_Y 547
#define SALE_BUTTON_IMAGE "OptimizePricesStoreButton.png"
#define SALE_MAX_BUTTON_ID 8
#define SALE_MAX_BUTTON_X 420           /* 420-539 x 547-596: between "Your cash" and Optimize Prices */
#define SALE_MAX_BUTTON_Y 547
#define SALE_MAX_BUTTON_IMAGE "MaxPricesStoreButton.png"

/* The string table (0x426FD0 looks ids up here): { id, English, German }. */
#define STRINGS 0x00457340u
#define STRING_COUNT 0xF9
#define STR_QUESTION 0xAC               /* "Delete this fish?", a Yes / No question */
#define STR_MESSAGE 0xF1                /* an OK message */

static command_fn next_command = NULL;
static activate_fn next_activate = NULL;
static command_fn next_sale_command = NULL;
static activate_fn next_sale_activate = NULL;
static void *button_scene = NULL;
static void *sale_button_scene = NULL;
static int installed = 0;

/* ------------------------------------------------------------ the prices */

typedef struct shop {
    int ornaments, seahorse, advertising, tank;
} shop;

static void read_shop(const char *state, shop *s) {
    int k;
    s->ornaments = 0;
    for (k = 0; k < ORNAMENTS; ++k) s->ornaments += AT(state, OWN_ORNAMENT + k * ORNAMENT_STRIDE, int);
    s->seahorse = AT(state, OWN_SEAHORSE, int) != 0;
    s->advertising = AT(state, ADVERTISING, int);
    s->tank = *(const unsigned char *)(UINT_PTR)TANK_BOUND_VA;
    if (s->tank < 21 || s->tank > 30) s->tank = 21;
}

/* "DS Exclusive Fish.dll", when it is installed: its entry lookup. */
static ds_entry_fn ds_entries(void) {
    HMODULE ds = GetModuleHandleW(L"DS Exclusive Fish.dll");
    installed_fn ds_installed;
    if (ds == NULL) return NULL;
    ds_installed = (installed_fn)GetProcAddress(ds, "FtfpDsFishInstalled");
    if (ds_installed == NULL || !ds_installed()) return NULL;
    return (ds_entry_fn)GetProcAddress(ds, "FtfpDsFishEntry");
}

static int valid_gene(int g, int ds) { return (g >= 0 && g <= PC_LAST) || (ds && g >= DS_FIRST && g <= DS_LAST); }

/* Sets every discovered species to its best price per day, or with `max`
   to its highest selling price; returns how many. */
static int set_prices(char *state, int max) {
    shop s;
    ds_entry_fn ds_entry = ds_entries();
    int body, fin, set = 0;
    read_shop(state, &s);
    for (body = 0; body <= DS_LAST; ++body) {
        if (!valid_gene(body, ds_entry != NULL)) continue;
        for (fin = 0; fin <= DS_LAST; ++fin) {
            unsigned char *e;
            int best;
            if (!valid_gene(fin, ds_entry != NULL)) continue;
            e = body <= PC_LAST ? (unsigned char *)state + SPECIES_BASE + (body * ROW_STRIDE + fin) * ENTRY_SIZE
                                : ds_entry(state, body, fin);
            if (e == NULL || e[0] == 0 || AT(e, ENTRY_PRICE, int) == -1 || AT(e, ENTRY_BASE, int) <= 0) continue;
            best = max ? pm_fish_max(AT(e, ENTRY_BASE, int))
                       : pm_fish_best(AT(e, ENTRY_BASE, int), s.ornaments, s.seahorse, s.advertising, s.tank);
            if (best <= 0) continue;
            AT(e, ENTRY_PRICE, int) = best;
            ++set;
        }
    }
    return set;
}

/* ---------------------------------------------------------- the dialogs */

static const char QUESTION_EN[] = "Set every discovered species\nto its best price per day?";
static const char QUESTION_DE[] = "Alle entdeckten Arten auf ihren\nbesten Preis pro Tag setzen?";
static const char MAX_QUESTION_EN[] = "Set every discovered species\nto its highest selling price?\n"
                                      "Fish at this price sell\nmuch more slowly.";
static const char MAX_QUESTION_DE[] = "Alle entdeckten Arten auf ihren\nh\xF6" "chsten Verkaufspreis setzen?\n"
                                      "Zu diesem Preis verkaufen sich\nFische viel langsamer.";

static char *string_entry(int id) {
    char *entry = (char *)(UINT_PTR)STRINGS;
    int i;
    for (i = 0; i < STRING_COUNT; ++i, entry += 12) {
        if (AT(entry, 0, int) == id) return entry;
    }
    return NULL;
}

/* The game's message box for string `id`, showing `en` / `de` instead;
   returns 1 when the first button (Yes, or OK) was clicked. */
static int ask(void *scene, int id, int yes_no, const char *en, const char *de) {
    char dialog[0x400];
    char *entry = string_entry(id);
    const char *saved_en, *saved_de;
    int answer = -1;
    if (entry == NULL) return 0;
    saved_en = AT(entry, 4, const char *);
    saved_de = AT(entry, 8, const char *);
    AT(entry, 4, const char *) = en;
    AT(entry, 8, const char *) = de;
    __try {
        DIALOG_INIT(dialog, NULL, id, yes_no);
        answer = DIALOG_RUN(dialog, NULL, (int)(UINT_PTR)scene, 0);
        DIALOG_FREE(dialog, NULL);
    } __finally {
        AT(entry, 4, const char *) = saved_en;
        AT(entry, 8, const char *) = saved_de;
    }
    return answer == 0;
}

static int append_int(char *out, int len, int value) {
    char digits[12];
    int d = 0;
    if (value < 0) value = 0;
    do { digits[d++] = (char)('0' + value % 10); value /= 10; } while (value && d < 11);
    while (d) out[len++] = digits[--d];
    return len;
}

static int append_text(char *out, int len, const char *text) {
    while (*text) out[len++] = *text++;
    return len;
}

static void tell_count(void *scene, int set) {
    char en[48], de[48];
    int n = append_int(en, 0, set);
    n = append_text(en, n, set == 1 ? " price set." : " prices set.");
    en[n] = '\0';
    n = append_int(de, 0, set);
    n = append_text(de, n, set == 1 ? " Preis gesetzt." : " Preise gesetzt.");
    de[n] = '\0';
    ask(scene, STR_MESSAGE, 0, en, de);
}

/* ------------------------------------------------------------- the scene */

static char *scene_state(void *scene) {
    char *impl = AT(scene, 8, char *);
    return impl != NULL ? AT(impl, 4, char *) : NULL;
}

static char *sale_state(void *scene) {
    char *impl = AT(scene, 8, char *);
    return impl != NULL ? AT(impl, SALE_IMPL_STATE, char *) : NULL;
}

/* A button's click, the same on both screens: the question, the prices,
   the count; `scene` is the dialogs' parent, `max` picks Max Prices. */
static void run_button(void *scene, char *state, int max) {
    int set;
    if (state == NULL || !ask(scene, STR_QUESTION, 1, max ? MAX_QUESTION_EN : QUESTION_EN,
                              max ? MAX_QUESTION_DE : QUESTION_DE))
        return;
    set = set_prices(state, max);
    tell_count(scene, set);
}

static void click(void *scene, char *(*state_of)(void *), int max) {
    __try {
        run_button(scene, state_of(scene), max);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
}

static int __fastcall scene_command(void *scene, void *edx, int msg, int id) {
    if (msg == 8 && (id == BUTTON_ID || id == MAX_BUTTON_ID)) {
        click(scene, scene_state, id == MAX_BUTTON_ID);
        return 1;
    }
    return next_command(scene, edx, msg, id);
}

static int __fastcall sale_command(void *scene, void *edx, int msg, int id) {
    if (msg == 8 && (id == SALE_BUTTON_ID || id == SALE_MAX_BUTTON_ID)) {
        click(scene, sale_state, id == SALE_MAX_BUTTON_ID);
        return 1;
    }
    return next_sale_command(scene, edx, msg, id);
}

static int add_button(void *scene, int id, const char *image, int x, int y) {
    void *button = OPERATOR_NEW(0x14), *sound;
    if (button == NULL) return 0;
    button = (void *)(UINT_PTR)BUTTON_INIT(button, NULL, id, (int)(UINT_PTR)image, x, y, (int)(UINT_PTR)scene, 0);
    if (button == NULL) return 0;
    sound = (void *)(UINT_PTR)SOUND_GET(SOUND_MANAGER(), NULL, SOUND_CLICK);
    BUTTON_SOUND(button, NULL, (int)(UINT_PTR)sound, 0);
    ADD_CONTROL(scene, NULL, (int)(UINT_PTR)button);
    return 1;
}

typedef struct placed {
    int id;
    const char *image;
    int x, y;
} placed;

/* Optimize Prices, then Max Prices, on each screen. */
static const placed CHART_BUTTONS[2] = {
    { BUTTON_ID, BUTTON_IMAGE, BUTTON_X, BUTTON_Y },
    { MAX_BUTTON_ID, MAX_BUTTON_IMAGE, MAX_BUTTON_X, MAX_BUTTON_Y },
};
static const placed SALE_BUTTONS[2] = {
    { SALE_BUTTON_ID, SALE_BUTTON_IMAGE, SALE_BUTTON_X, SALE_BUTTON_Y },
    { SALE_MAX_BUTTON_ID, SALE_MAX_BUTTON_IMAGE, SALE_MAX_BUTTON_X, SALE_MAX_BUTTON_Y },
};

/* Adds the two buttons once to `scene` (remembered in *added, once the
   first is in). */
static void add_once(void *scene, int on, void **added, const placed *buttons) {
    int k;
    if (!(on & 0xFF) || *added == scene) return;
    for (k = 0; k < 2; ++k) {
        __try {
            if (add_button(scene, buttons[k].id, buttons[k].image, buttons[k].x, buttons[k].y) && k == 0)
                *added = scene;
        } __except (EXCEPTION_EXECUTE_HANDLER) {
        }
        if (*added != scene) return;
    }
}

static void __fastcall scene_activate(void *scene, void *edx, int on) {
    next_activate(scene, edx, on);
    add_once(scene, on, &button_scene, CHART_BUTTONS);
}

static void __fastcall sale_activate(void *scene, void *edx, int on) {
    next_sale_activate(scene, edx, on);
    add_once(scene, on, &sale_button_scene, SALE_BUTTONS);
}

/* ---------------------------------------------------------------- install */

/* The slot's function, or 0 when the slot is not committed memory. */
static DWORD slot_value(unsigned int va) {
    MEMORY_BASIC_INFORMATION info;
    if (VirtualQuery((const void *)(UINT_PTR)va, &info, sizeof info) != sizeof info || info.State != MEM_COMMIT) return 0;
    return *(const DWORD *)(UINT_PTR)va;
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
    const char *line = installed ? "Optimize Prices: installed (Species Chart and Fish Store)\r\n"
                                 : "Optimize Prices: NOT installed (the Species Chart or the Fish Store is not "
                                   "the stock one)\r\n";
    DWORD n = GetModuleFileNameW(NULL, path, 1024), written;
    wchar_t *slash;
    HANDLE file;
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(path) + 64 >= 1024) return;
    wcscat_s(path, 1024, L"Fish Tycoon Fix Patcher DLLs\\Optimize Prices.log");
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)strlen(line), &written, NULL);
    CloseHandle(file);
}

#define SLOTS 4

/* Checks all four slots, then writes them in order; a refused write puts
   the ones already written back, so it is all of them or none. */
static int install(void) {
    static const unsigned int va[SLOTS] = { SPECIES_VT_COMMAND, SPECIES_VT_ACTIVATE, SALE_VT_COMMAND, SALE_VT_ACTIVATE };
    const void *to[SLOTS];
    DWORD was[SLOTS];
    int k;
    to[0] = (const void *)(UINT_PTR)scene_command;
    to[1] = (const void *)(UINT_PTR)scene_activate;
    to[2] = (const void *)(UINT_PTR)sale_command;
    to[3] = (const void *)(UINT_PTR)sale_activate;
    for (k = 0; k < SLOTS; ++k) was[k] = slot_value(va[k]);
    if (was[0] != SPECIES_COMMAND_STOCK || was[1] != SPECIES_ACTIVATE_STOCK
        || was[2] != SALE_COMMAND_STOCK || was[3] != SALE_ACTIVATE_STOCK)
        return 0;
    next_command = (command_fn)(UINT_PTR)was[0];
    next_activate = (activate_fn)(UINT_PTR)was[1];
    next_sale_command = (command_fn)(UINT_PTR)was[2];
    next_sale_activate = (activate_fn)(UINT_PTR)was[3];
    for (k = 0; k < SLOTS; ++k) {
        if (!write_slot(va[k], to[k])) {
            while (k-- > 0) write_slot(va[k], (const void *)(UINT_PTR)was[k]);
            return 0;
        }
    }
    return 1;
}

/* Called once before WinMain by the startup loader, after any other companion. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        installed = install();
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
