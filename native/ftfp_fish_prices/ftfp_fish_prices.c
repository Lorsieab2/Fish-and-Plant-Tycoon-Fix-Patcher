/* Optimize Prices -- an "Optimize Prices" button on Fish Tycoon's Species Chart.

   WHAT.  The Species Chart is where the player sets a species' asking price
   (its arrows and keypad).  The button sits on its bottom bar, left of Done.
   It asks "Set every discovered species to its best price per day?" (Yes /
   No, the game's own question box).  On Yes, every discovered species' asking
   price becomes the Breeding Guide's "best per day" price for the shop as it
   is now: the species' base price B (entry + 0x24, which already has the
   Advertising rises), the ornaments owned, the Golden Seahorse, the
   Advertising level, and a full selling tank (21 adults, or 26 with Bigger
   tanks: the exe's own slot bound says which).  The maths is
   native/common/price_math.h, the port of src/breeding_fish.py.  Then the
   game's own message box says "N prices set."

   WHAT IT WRITES.  Only the asking price of discovered species (entry +
   0x20, the cell the chart's arrows and keypad write, which the save
   keeps).  An undiscovered species (price -1, or no entry) is never
   written.  With DS Exclusive Fish installed, its species are included: the
   PC bodies' DS fins are in the stock table's spare columns, and the DS
   bodies' rows come from "DS Exclusive Fish.dll" (FtfpDsFishEntry), the
   cells the game's own index arithmetic reaches.

   HOW.  The startup loader loads this DLL after any other companion and
   calls FtfpStartup() before WinMain.  It wraps two slots of the Species
   Chart's vtable (0x443C90), command and activate, after checking both still
   hold the stock functions, or writes neither: activate adds the button
   once, command runs it for the button's id. */
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
#define TANK_BOUND_VA 0x00419C74u       /* AddFish's `cmp eax, 0x15`: 0x1A with Bigger tanks */

#define BUTTON_ID 7
#define BUTTON_X 524
#define BUTTON_Y 546
#define BUTTON_IMAGE "OptimizePricesButton.png"
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

/* The string table (0x426FD0 looks ids up here): { id, English, German }. */
#define STRINGS 0x00457340u
#define STRING_COUNT 0xF9
#define STR_QUESTION 0xAC               /* "Delete this fish?", a Yes / No question */
#define STR_MESSAGE 0xF1                /* an OK message */

static command_fn next_command = NULL;
static activate_fn next_activate = NULL;
static void *button_scene = NULL;
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
    s->tank = *(const unsigned char *)(UINT_PTR)TANK_BOUND_VA == 0x1A ? 26 : 21;
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

/* Sets every discovered species to its best price; returns how many. */
static int optimize(char *state) {
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
            best = pm_fish_best(AT(e, ENTRY_BASE, int), s.ornaments, s.seahorse, s.advertising, s.tank);
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

static void run_button(void *scene) {
    char *state = scene_state(scene);
    int set;
    if (state == NULL || !ask(scene, STR_QUESTION, 1, QUESTION_EN, QUESTION_DE)) return;
    set = optimize(state);
    tell_count(scene, set);
}

static int __fastcall scene_command(void *scene, void *edx, int msg, int id) {
    if (msg == 8 && id == BUTTON_ID) {
        __try {
            run_button(scene);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
        }
        return 1;
    }
    return next_command(scene, edx, msg, id);
}

static void add_button(void *scene) {
    void *button = OPERATOR_NEW(0x14), *sound;
    if (button == NULL) return;
    button = (void *)(UINT_PTR)BUTTON_INIT(button, NULL, BUTTON_ID, (int)(UINT_PTR)BUTTON_IMAGE, BUTTON_X, BUTTON_Y,
                                           (int)(UINT_PTR)scene, 0);
    if (button == NULL) return;
    sound = (void *)(UINT_PTR)SOUND_GET(SOUND_MANAGER(), NULL, SOUND_CLICK);
    BUTTON_SOUND(button, NULL, (int)(UINT_PTR)sound, 0);
    ADD_CONTROL(scene, NULL, (int)(UINT_PTR)button);
    button_scene = scene;
}

static void __fastcall scene_activate(void *scene, void *edx, int on) {
    next_activate(scene, edx, on);
    if ((on & 0xFF) && button_scene != scene) {
        __try {
            add_button(scene);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
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
                                 : "Optimize Prices: NOT installed (the Species Chart is not the stock one)\r\n";
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

/* Called once before WinMain by the startup loader, after any other companion. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        if (slot_holds(SPECIES_VT_COMMAND, SPECIES_COMMAND_STOCK) && slot_holds(SPECIES_VT_ACTIVATE, SPECIES_ACTIVATE_STOCK)) {
            next_command = (command_fn)(UINT_PTR)SPECIES_COMMAND_STOCK;
            next_activate = (activate_fn)(UINT_PTR)SPECIES_ACTIVATE_STOCK;
            if (write_slot(SPECIES_VT_COMMAND, (const void *)(UINT_PTR)scene_command)) {
                if (write_slot(SPECIES_VT_ACTIVATE, (const void *)(UINT_PTR)scene_activate)) installed = 1;
                else write_slot(SPECIES_VT_COMMAND, (const void *)(UINT_PTR)SPECIES_COMMAND_STOCK);
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
