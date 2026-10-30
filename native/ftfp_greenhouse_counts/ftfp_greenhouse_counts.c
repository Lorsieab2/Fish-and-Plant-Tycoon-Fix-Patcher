/* Greenhouse Counts -- how many plants Plant Tycoon's greenhouse holds, on
   the greenhouse screen.

   WHAT.  Lines in the game's font (PTfontsmall, the only one it loads,
   0x412D9F) along the top of the greenhouse wall:
     Plants: 9 of 15 (5 mature, 2 with buds, 2 seedlings)  Dead: 1
     Infested: 2  Unhealthy: 1               (only when a plant is)
   counting the 15 pots (3 tables of 5) of the greenhouse on screen that
   hold a living plant (with "5 extra greenhouses", Greenhouses 2-6 too: that
   DLL moves the greenhouse on screen into the game's 15 pots), and a
   "Counts: On" / "Counts: Off" button at the right of the wall that hides or
   shows them; hidden, only the button is drawn.  Its state is kept in
   "Greenhouse Counts.ini" beside this DLL (common/count_toggle.h), never in
   a save.  Recomputed from the game state every frame; nothing in the game
   is written.

   WHICH PLANTS.  A pot record is state + 0x2188 + k * 0x5600 (k = row * 5 +
   col, 0x423750).  It holds a plant when +0x4C is set (the plant object
   exists only then, 0x42F6E4), and the plant is dead at health 0 or less
   (+0x24; 0x4284DB: "Dead", string 0x57): dead plants still fill their pot
   until they are trashed, and are counted as "Dead", not among the plants.
   The stages are the selected plant's own countdown (0x423750), by its age
   (+0x10, a float):
     age < 21.0 (0x4237E3, the float at 0x4691D8)  "Buds in N Min."  a seedling;
     age < 24.0 (0x423866, the float at 0x4677E8)  "Mature in N Min." with buds;
     otherwise                                      mature ("Mature", 0x18B, 0x5E).
   The words are the game's own: "We have started you with a few seedlings",
   "Buds", "Mature".  The game has one pest, "small black insects", and its
   status panel (0x4284CE) names a living plant "Infested" when +0x28 is set
   (string 0x58), else "Unhealthy" below health 30 (0x428551, string 0x59):
   the second line counts them the same way.  The game has no German text.

   THE BUTTON.  The greenhouse's mouse slot (0x469224, 0x4273D0; type, x,
   y, ret 0xC) is wrapped: a press on the button while nothing is held
   (state+0x56C, the held seed or tool the stock press tests at 0x42742E)
   toggles the counts, and that press and its release stay here.  The button
   lies on the stone wall at the top right, above the pots and the tables.

   WITH EXTRA GREENHOUSES.  Once a greenhouse is bought, "5 extra
   greenhouses" draws gold arrows in the top corners (x 222-271 and 748-797,
   y 10-59) and the greenhouse's name centred at (510, 26): the lines then
   start at y 62, under the arrows, and the button moves to (646, 4), left of
   the right arrow and above the name.

   HOW.  The startup loader loads this DLL and calls FtfpStartup() before
   WinMain ("Extra Greenhouses.dll" starts it instead when its settings are
   on, before wrapping the same two slots itself).  It first loads the DLL the loader would load without this
   setting ("Unused Flowers.dll", else "Sort Seeds.dll", when their settings
   put them beside this one), then wraps two slots of the greenhouse scene's
   vtable, its background draw (0x469238, 0x4257A0: main_bg.png) and its
   mouse (above), after checking each holds the stock function, or writes
   neither.  The draw wrapper draws the background and then the lines, so
   the pots, plants, tools and buttons (drawn after it) are always drawn
   over them, never under. */
#include <windows.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "../common/count_text.h"
#include "../common/count_toggle.h"

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))

#define SCENE_STATE 0x68
#define S_HELD 0x56C
#define POTS 15
#define POT_BASE 0x2188
#define POT_STRIDE 0x5600
#define P_AGE 0x10
#define P_HEALTH 0x24
#define P_INFESTED 0x28
#define P_PLANTED 0x4C

#define AGE_BUDS 21.0f              /* 0x4691D8 */
#define AGE_MATURE 24.0f            /* 0x4677E8 */
#define HEALTH_UNHEALTHY 30         /* 0x428551 `cmp eax, 0x1e` */

#define LABEL_X 236
#define LABEL_Y 4                   /* the stone wall above the doors' lintel */
#define LINE_H 22                   /* PTfontsmall's glyphs are 21 px tall */
#define BUTTON_X 694
#define BUTTON_Y (LABEL_Y + LINE_H)
#define LABEL_Y_ARROWS 62           /* under Extra Greenhouses' arrows (y 10-59), on the floor's edge */
#define BUTTON_X_ARROWS 646         /* "Counts: Off" is 98 px: it ends left of the right arrow (x 748) */
#define BUTTON_Y_ARROWS 4           /* above the greenhouse's name (y 26) */
#define WHITE 0xFFFFFFFFu
#define YELLOW 0xFFFFD040u
#define SHADOW 0xFF000000u

typedef void (__fastcall *scene_fn)(void *scene, int edx);
typedef int (__fastcall *mouse_fn)(void *scene, int edx, int type, int x, int y);
typedef void *(__cdecl *getter_fn)(void);
typedef void (__fastcall *text_fn)(void *graphics, int edx, const char *text, int x, int y, unsigned int colour,
                                   int font);

static const getter_fn graphics_get = (getter_fn)0x00407A90u;
static const text_fn draw_text = (text_fn)0x004092A0u;          /* (text, x, y, colour, font 0 = PTfontsmall) */
static const scene_fn stock_draw = (scene_fn)0x004257A0u;
static const mouse_fn stock_mouse = (mouse_fn)0x004273D0u;

static count_toggle toggle = { 1, 0, 0, { BUTTON_X - 4, BUTTON_Y - 2, 798, BUTTON_Y + LINE_H - 2 }, { 0 } };

/* ------------------------------------------------------------------ counts */

typedef struct greenhouse_count {
    int plants, mature, buds, seedlings, dead, infested, unhealthy;
} greenhouse_count;

static void count_greenhouse(char *state, greenhouse_count *out) {
    int k;
    ZeroMemory(out, sizeof *out);
    for (k = 0; k < POTS; ++k) {
        char *pot = state + POT_BASE + k * POT_STRIDE;
        float age = AT(pot, P_AGE, float);
        int health = AT(pot, P_HEALTH, int);
        if (AT(pot, P_PLANTED, int) == 0) continue;
        if (health <= 0) {
            ++out->dead;
            continue;
        }
        ++out->plants;
        if (age < AGE_BUDS) ++out->seedlings;
        else if (age < AGE_MATURE) ++out->buds;
        else ++out->mature;
        if (AT(pot, P_INFESTED, int) != 0) ++out->infested;
        else if (health < HEALTH_UNHEALTHY) ++out->unhealthy;
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

/* "Infested: 2  Unhealthy: 1"; 0 when every plant is well. */
static int health_line(count_line *line, const greenhouse_count *c) {
    ct_start(line);
    if (c->infested > 0) {
        ct_text(line, "Infested: ");
        ct_number(line, c->infested);
    }
    if (c->unhealthy > 0) {
        if (c->infested > 0) ct_text(line, "  ");
        ct_text(line, "Unhealthy: ");
        ct_number(line, c->unhealthy);
    }
    return line->at > 0;
}

/* --------------------------------------------------------------- the draw */

#define DRAW_SLOT_VA 0x00469238u
static const unsigned char DRAW_SLOT_STOCK[4] = { 0xA0, 0x57, 0x42, 0x00 };     /* 0x4257A0 */
#define MOUSE_SLOT_VA 0x00469224u
static const unsigned char MOUSE_SLOT_STOCK[4] = { 0xD0, 0x73, 0x42, 0x00 };    /* 0x4273D0 */

static void draw_at(void *graphics, const char *text, int x, int y, unsigned int colour) {
    draw_text(graphics, 0, text, x + 1, y + 1, SHADOW, 0);
    draw_text(graphics, 0, text, x, y, colour, 0);
}

/* "5 extra greenhouses": once one is bought its arrows show (FtfpExtraGreenhousesOwned > 0). */
typedef int (__cdecl *owned_fn)(void);
static int arrows_shown(void) {
    HMODULE greenhouses = GetModuleHandleW(L"Extra Greenhouses.dll");
    owned_fn fn = greenhouses != NULL ? (owned_fn)GetProcAddress(greenhouses, "FtfpExtraGreenhousesOwned") : NULL;
    return fn != NULL && fn() > 0;
}

/* The lines' top and the button's place for the screen as it is now; the click area follows the button. */
static int place_button(int *bx, int *by) {
    int arrows = arrows_shown();
    *bx = arrows ? BUTTON_X_ARROWS : BUTTON_X;
    *by = arrows ? BUTTON_Y_ARROWS : BUTTON_Y;
    toggle.box.left = *bx - 4;
    toggle.box.top = *by - 2;
    toggle.box.right = arrows ? BUTTON_X_ARROWS + 98 : 798;
    toggle.box.bottom = *by + LINE_H - 2;
    return arrows ? LABEL_Y_ARROWS : LABEL_Y;
}

static void draw_counts(char *scene) {
    char *state = AT(scene, SCENE_STATE, char *);
    void *graphics = graphics_get();
    greenhouse_count count;
    count_line line;
    int bx, by, y;
    if (state == NULL || graphics == NULL) return;
    y = place_button(&bx, &by);
    draw_at(graphics, toggle.shown ? "Counts: On" : "Counts: Off", bx, by, toggle.hovered ? WHITE : YELLOW);
    if (!toggle.shown) return;
    count_greenhouse(state, &count);
    plant_line(&line, &count);
    draw_at(graphics, line.text, LABEL_X, y, WHITE);
    if (health_line(&line, &count)) draw_at(graphics, line.text, LABEL_X, y + LINE_H, WHITE);
}

static void __fastcall on_draw(char *scene, int edx) {
    stock_draw(scene, edx);
    __try {
        draw_counts(scene);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
}

static int __fastcall on_mouse(char *scene, int edx, int type, int x, int y) {
    int mine = 0;
    __try {
        char *state = AT(scene, SCENE_STATE, char *);
        int bx, by;
        place_button(&bx, &by);
        if (state != NULL) mine = toggle_mouse(&toggle, type, x, y, AT(state, S_HELD, int) == 0);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        mine = 0;
    }
    return mine ? 0 : stock_mouse(scene, edx, type, x, y);
}

/* ----------------------------------------------------------------- install */

static ftfp_site_write writes[2];
static int installed = 0;

typedef int (__stdcall *startup_fn)(void);

static void slot_write(ftfp_site_write *w, unsigned int va, const unsigned char *stock, const void *to) {
    DWORD value = (DWORD)(UINT_PTR)to;
    w->va = va;
    w->length = 4;
    w->expect = stock;
    memcpy(w->bytes, &value, 4);
}

/* The DLL the startup loader loads when this setting is off, beside this one
   (only an enabled setting's files are there): Unused Flowers (which loads
   the store upgrades, the seed boxes and Sort Seeds itself), else Sort Seeds. */
static void load_next(void) {
    static const wchar_t *const names[2] = { L"Unused Flowers.dll", L"Sort Seeds.dll" };
    wchar_t folder[1024], path[1024];
    int i;
    if (!dll_folder(folder, 1024)) return;
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
        toggle_load(&toggle, L"Greenhouse Counts.ini");
        slot_write(&writes[0], DRAW_SLOT_VA, DRAW_SLOT_STOCK, (const void *)(UINT_PTR)on_draw);
        slot_write(&writes[1], MOUSE_SLOT_VA, MOUSE_SLOT_STOCK, (const void *)(UINT_PTR)on_mouse);
        installed = ftfp_install_sites(writes, 2);
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
