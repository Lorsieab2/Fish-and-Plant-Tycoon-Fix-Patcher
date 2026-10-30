/* Greenhouse Counts -- how many plants Plant Tycoon's greenhouse holds, on
   the greenhouse screen.

   WHAT.  One line in the game's font (PTfontsmall, the only one it loads,
   0x412D9F) along the top of the greenhouse wall:
     Plants: 9 of 15 (5 mature, 2 with buds, 2 seedlings)  Dead: 1
   counting the 15 pots (3 tables of 5) that hold a living plant.
   Recomputed from the game state every frame; nothing is written.

   WHICH PLANTS.  A pot record is state + 0x2188 + k * 0x5600 (k = row * 5 +
   col, 0x423750).  It holds a plant when +0x4C is set (the plant object
   exists only then, 0x42F6E4), and the plant is dead at health 0 or less
   (+0x24; 0x4237D5 shows a dead plant no countdown; "Dead", string 0x57):
   dead plants still fill their pot until they are trashed, and are counted
   as "Dead", not among the plants.  The stages are the selected plant's own
   countdown (0x423750), by its age (+0x10, a float):
     age < 21.0 (0x4237E3, the float at 0x4691D8)  "Buds in N Min."  a seedling;
     age < 24.0 (0x423866, the float at 0x4677E8)  "Mature in N Min." with buds;
     otherwise                                      mature ("Mature", 0x18B, 0x5E).
   The words are the game's own: "We have started you with a few seedlings",
   "Buds", "Mature".

   HOW.  The startup loader loads this DLL and calls FtfpStartup() before
   WinMain.  It first loads the DLL the loader would load without this
   setting ("Unused Flowers.dll", else "Sort Seeds.dll", when their settings
   put them beside this one), then wraps one slot of the greenhouse scene's
   vtable, its background draw (0x469238, 0x4257A0: main_bg.png), after
   checking it holds the stock function, or writes nothing.  The wrapper
   draws the background and then the line, so the pots, plants, tools and
   buttons (drawn after it) are always drawn over the line, never under. */
#include <windows.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "../common/count_text.h"

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))

#define SCENE_STATE 0x68
#define POTS 15
#define POT_BASE 0x2188
#define POT_STRIDE 0x5600
#define P_AGE 0x10
#define P_HEALTH 0x24
#define P_PLANTED 0x4C

#define AGE_BUDS 21.0f              /* 0x4691D8 */
#define AGE_MATURE 24.0f            /* 0x4677E8 */

#define LABEL_X 236
#define LABEL_Y 4                   /* the stone wall above the doors' lintel */
#define WHITE 0xFFFFFFFFu
#define SHADOW 0xFF000000u

typedef void (__fastcall *scene_fn)(void *scene, int edx);
typedef void *(__cdecl *getter_fn)(void);
typedef void (__fastcall *text_fn)(void *graphics, int edx, const char *text, int x, int y, unsigned int colour,
                                   int font);

static const getter_fn graphics_get = (getter_fn)0x00407A90u;
static const text_fn draw_text = (text_fn)0x004092A0u;          /* (text, x, y, colour, font 0 = PTfontsmall) */

/* ------------------------------------------------------------------ counts */

typedef struct greenhouse_count {
    int plants, mature, buds, seedlings, dead;
} greenhouse_count;

static void count_greenhouse(char *state, greenhouse_count *out) {
    int k;
    ZeroMemory(out, sizeof *out);
    for (k = 0; k < POTS; ++k) {
        char *pot = state + POT_BASE + k * POT_STRIDE;
        float age = AT(pot, P_AGE, float);
        if (AT(pot, P_PLANTED, int) == 0) continue;
        if (AT(pot, P_HEALTH, int) <= 0) {
            ++out->dead;
            continue;
        }
        ++out->plants;
        if (age < AGE_BUDS) ++out->seedlings;
        else if (age < AGE_MATURE) ++out->buds;
        else ++out->mature;
    }
}

static void plant_line(count_line *line, const greenhouse_count *c) {
    ct_start(line);
    ct_count(line, "Plants: ", c->plants, " of ", POTS);
    ct_part(line, c->mature, "mature", "mature");
    ct_part(line, c->buds, "with buds", "with buds");
    ct_part(line, c->seedlings, "seedling", "seedlings");
    ct_close(line);
    ct_dead(line, "Dead: ", c->dead);
}

/* --------------------------------------------------------------- the draw */

#define DRAW_SLOT_VA 0x00469238u
static const unsigned char DRAW_SLOT_STOCK[4] = { 0xA0, 0x57, 0x42, 0x00 };     /* 0x4257A0 */
static const scene_fn stock_draw = (scene_fn)0x004257A0u;

static void draw_counts(char *scene) {
    char *state = AT(scene, SCENE_STATE, char *);
    void *graphics = graphics_get();
    greenhouse_count count;
    count_line line;
    if (state == NULL || graphics == NULL) return;
    count_greenhouse(state, &count);
    plant_line(&line, &count);
    draw_text(graphics, 0, line.text, LABEL_X + 1, LABEL_Y + 1, SHADOW, 0);
    draw_text(graphics, 0, line.text, LABEL_X, LABEL_Y, WHITE, 0);
}

static void __fastcall on_draw(char *scene, int edx) {
    stock_draw(scene, edx);
    __try {
        draw_counts(scene);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
}

/* ----------------------------------------------------------------- install */

static ftfp_site_write writes[1];
static int installed = 0;

EXTERN_C IMAGE_DOS_HEADER __ImageBase;
typedef int (__stdcall *startup_fn)(void);

/* The DLL the startup loader loads when this setting is off, beside this one
   (only an enabled setting's files are there): Unused Flowers (which loads
   the store upgrades, the seed boxes and Sort Seeds itself), else Sort Seeds. */
static void load_next(void) {
    static const wchar_t *const names[2] = { L"Unused Flowers.dll", L"Sort Seeds.dll" };
    wchar_t folder[1024], path[1024];
    wchar_t *slash;
    int i;
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, folder, 1024);
    if (n == 0 || n >= 1024 || (slash = wcsrchr(folder, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(folder) + 32 >= 1024) return;
    for (i = 0; i < 2; ++i) {
        HMODULE module;
        startup_fn startup;
        wcscpy_s(path, 1024, folder);
        wcscat_s(path, 1024, names[i]);
        if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) continue;
        module = LoadLibraryW(path);
        if (module == NULL) return;
        startup = (startup_fn)GetProcAddress(module, "FtfpStartup");
        if (startup != NULL) startup();
        return;
    }
}

/* Called once by the executable's startup stub, before WinMain. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        load_next();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    __try {
        DWORD to = (DWORD)(UINT_PTR)on_draw;
        writes[0].va = DRAW_SLOT_VA;
        writes[0].length = 4;
        writes[0].expect = DRAW_SLOT_STOCK;
        memcpy(writes[0].bytes, &to, 4);
        installed = ftfp_install_sites(writes, 1);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    return installed;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}
