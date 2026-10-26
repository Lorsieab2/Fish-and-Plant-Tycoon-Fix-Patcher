/* FTFP DS Store -- the Nintendo DS store items in PC Fish Tycoon.

   WHAT.  An "Upgrades" button in the Supplies store opens a second page:
     * Puffer Fish, Sting Ray and Moray Eel: tank companions like the
       Golden Seahorse (they swim, can be dragged between tanks, never age,
       breed or get sold, and show the seahorse's health and food meters);
     * the Moray Eel comes with its rock, a decoration moved like the shell
       or pagoda.  Drop the eel on its rock and it goes home (the DS in-rock
       animation, head peeking out); moving the rock then moves the eel.
       A click on its head lets it out again;
     * Exotic Fish Eggs: eggs for slot #4 that hatch only DS-exclusive
       bodies and fins (genes 23-29, even odds), as many as the other eggs.
   Effects, per tank, rescaled from the DS (docs/fish-tycoon-ds-store-items-design.md),
   for healthy fish (no disease, food above 5), each age step:
     * Golden Seahorse (its PC effects stay) and Sting Ray: 82% chance of +1 health;
     * Puffer Fish: +1 food, and a 60% chance of +1 more;
     * Moray Eel: a fish that would die survives at health 10, 1 time in 10.

   HOW.  "FTFP DS Store.dll" sits beside "FTFP DS Fish.dll", which loads it
   after its own install and lends it sprite table entries 220-235.  Every
   write into the game is in store_sites.h -- all of them or none.

   STATE.  Nothing new is saved.  A companion is a seahorse-type fish record
   (body 22) whose fin marks the animal: 22 Golden Seahorse, 30 Puffer Fish,
   31 Sting Ray, 32 Moray Eel -- so every rule the game has for the seahorse
   applies to them.  The rock is one of the tank's ornament records; while
   the eel is home, the rock record's spare bytes keep its health and food.
   Owning an animal means it is in a tank. */
#include <windows.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "store_sites.h"
#include "store_data.h"

#define STATE_GLOBAL 0x0045ABDCu
#define FISH_BASE 0x390
#define TANK_STRIDE 0x51EC
#define SLOT_STRIDE 0x288
#define SLOTS 21
#define ORN_BASE 0x5208
#define ORN_STRIDE 0x2C
#define ORN_SLOTS 6

#define F_LIVE 0x00
#define F_LAST_AGE 0x08
#define F_AGE 0x0C
#define F_PREGNANT 0x10
#define F_HEALTH 0x3C
#define F_DISEASE 0x40
#define F_FOOD 0x44
#define F_BODY 0x4C
#define F_FIN 0x50
#define F_SPRITES 0x54

#define O_X 0x04
#define O_Y 0x08
#define O_FALLING 0x10
#define O_H 0x1C
#define O_W 0x20
#define O_SPRITE 0x24
#define O_HOME_HEALTH 1             /* spare bytes after the active byte */
#define O_HOME_FOOD 2
#define O_HOME_FLAG 3
#define HOME_FLAG 0xE1

#define S_CURRENT_TANK 0x384
#define S_MONEY 0x38C
#define S_SPENT 0x24
#define S_SECOND_TANK 0x230
#define S_EGG_PLANT 0x17C
#define S_EASY 0x14
#define S_EGG_ITEM 0x30C
#define S_EGG_PRESENT 0x310
#define S_EGG_COUNT 0x314
#define S_EGG_ICON 0x318
#define S_EGG_CURSOR 0x31C
#define S_EGG_X 0x320

#define BODY_SEAHORSE 22
#define FIN_SEAHORSE 22
#define FIN_PUFFER 30
#define FIN_RAY 31
#define FIN_EEL 32
#define DS_FIRST_GENE 23
#define DS_GENES 7
#define EXOTIC_ITEM 28              /* 26 = starter eggs, 27 = the store's "none" */
#define ITEM_NONE 0x1B

/* Sprite table entries lent by DS Fish. */
#define STORE_SPRITE_BASE 220
#define SPR_ITEM_PUFFER (STORE_SPRITE_BASE + 0)
#define SPR_ITEM_EGGS (STORE_SPRITE_BASE + 3)
#define SPR_TOOL_EGGS (STORE_SPRITE_BASE + 4)
#define SPR_SHEET (STORE_SPRITE_BASE + 5)       /* + 0..2 by animal */
#define SPR_ROCK (STORE_SPRITE_BASE + 8)
#define SPR_ROCK_HOME (STORE_SPRITE_BASE + 9)
#define SPR_HOME_BACK (STORE_SPRITE_BASE + 10)
#define SPR_HOME_FRONT (STORE_SPRITE_BASE + 11)
#define STORE_SPRITES 12

typedef struct sprite_entry {
    int id;
    const char *name;
    int cols, rows;
    int reserved[5];
} sprite_entry;

typedef struct ftfp_store_host {
    int version;
    void *sprites;
    int first;
    int count;
} ftfp_store_host;

static const struct { const char *name; int cols, rows; } SPRITE_FILES[STORE_SPRITES] = {
    { "ITEM_DS_PUFFER.png", 0, 0 },
    { "ITEM_DS_STINGRAY.png", 0, 0 },
    { "ITEM_DS_EEL.png", 0, 0 },
    { "ITEM_FISHEGGS_EXOTIC.png", 0, 0 },
    { "TOOL_FISHEGGS_EXOTIC.png", 0, 0 },
    { "DS_PUFFER_Grid.png", 6, 3 },
    { "DS_STINGRAY_Grid.png", 6, 3 },
    { "DS_EEL_Grid.png", 6, 3 },
    { "DS_EEL_ROCK.png", 0, 0 },                /* the eel out */
    { "DS_EEL_ROCK.png", 0, 0 },                /* the eel home */
    { "DS_EEL_HOME_BACK_Grid.png", HOME_COLS, HOME_FRAMES / HOME_COLS },
    { "DS_EEL_HOME_FRONT_Grid.png", HOME_COLS, HOME_FRAMES / HOME_COLS },
};

/* ------------------------------------------------------------ the game */

/* thiscall functions are called as fastcall with a dummy edx: both pass
   `this` in ecx and let the callee pop the stack arguments. */
typedef int (__cdecl *random_fn)(int bound);
typedef int (__cdecl *clock_fn)(void);
typedef void *(__cdecl *getter_fn)(void);
typedef void *(__cdecl *new_fn)(unsigned int size);
typedef int (__fastcall *this0_fn)(void *self, void *edx);
typedef int (__fastcall *this1_fn)(void *self, void *edx, int a);
typedef int (__fastcall *this2_fn)(void *self, void *edx, int a, int b);
typedef int (__fastcall *this3_fn)(void *self, void *edx, int a, int b, int c);
typedef int (__fastcall *this4_fn)(void *self, void *edx, int a, int b, int c, int d);
typedef int (__fastcall *this5_fn)(void *self, void *edx, int a, int b, int c, int d, int e);
typedef int (__fastcall *this6_fn)(void *self, void *edx, int a, int b, int c, int d, int e, int f);
typedef int (__fastcall *baby_fn)(void *self, void *edx, int, int, int, int, int, int, int, int, int, int,
                                  int, int, int, int);

#define GAME(T, VA) ((T)(UINT_PTR)(VA))
#define RANDOM GAME(random_fn, 0x00403240u)
#define CLOCK_NOW GAME(clock_fn, 0x004020D0u)
#define OPERATOR_NEW GAME(new_fn, 0x0042A793u)
#define SOUND_MANAGER GAME(getter_fn, 0x00425120u)
#define SOUND_GET GAME(this1_fn, 0x004251A0u)          /* (id) -> sound */
#define SOUND_PLAY GAME(this1_fn, 0x0040AE20u)         /* (0) */
#define STRING_TABLE GAME(getter_fn, 0x00427060u)
#define GET_STRING GAME(this1_fn, 0x00427050u)
#define SPRITE_GET GAME(this1_fn, 0x0041BE70u)
#define SPRITE_GRID GAME(this1_fn, 0x0041BCA0u)
#define DRAW GAME(this3_fn, 0x00408A40u)               /* (img, x, y) */
#define DRAW_ALPHA GAME(this6_fn, 0x00408AE0u)         /* (img, x, y, alpha, 1, 0) */
#define DRAW_CELL GAME(this4_fn, 0x00408AA0u)          /* (img, x, y, frame) */
#define DRAW_TEXT GAME(this5_fn, 0x00408B80u)          /* (text, x, y, font, attr) */
#define HINT GAME(this1_fn, 0x00417FA0u)               /* string n + 0x83 near the mouse */
#define DIALOG_INIT GAME(this2_fn, 0x004221A0u)        /* (string id, 1) */
#define DIALOG_RUN GAME(this2_fn, 0x00401D00u)         /* (parent, 0) -> 0 = Yes */
#define DIALOG_FREE GAME(this0_fn, 0x00422440u)
#define BUTTON_INIT GAME(this6_fn, 0x00401B10u)        /* (id, image, x, y, handler, 0) */
#define BUTTON_SOUND GAME(this2_fn, 0x004015E0u)       /* (sound, 0) */
#define ADD_CONTROL GAME(this1_fn, 0x0040A9E0u)
#define FISH_INIT GAME(this0_fn, 0x0041A540u)
#define FISH_SPRITES_HELPER GAME(getter_fn, 0x004160A0u)
#define FISH_SPRITES GAME(this3_fn, 0x00415390u)       /* (sprites, 22, 22) */
#define STATE_NOW GAME(this0_fn, 0x004032C0u)
#define ADD_FISH GAME(this2_fn, 0x00419C50u)           /* (tank, record) -> slot or -1 */
#define REMOVE_FISH GAME(this2_fn, 0x00418E20u)        /* (tank, slot) */
#define VIEW_MOVE GAME(this4_fn, 0x00415380u)          /* (entry, tank, 1, slot) */
#define VIEW_SYNC GAME(this1_fn, 0x00415E70u)          /* (the current tank's fish) */
#define SPLASH GAME(this3_fn, 0x00413B00u)             /* (4, x, y) */
#define NEW_BABY GAME(baby_fn, 0x0041FA30u)

#define FONT_TITLE (*(void **)(UINT_PTR)0x0045849Cu)
#define FONT_BODY (*(void **)(UINT_PTR)0x0045B318u)
#define LANGUAGE_PTR (*(int **)(UINT_PTR)0x0045B314u)
#define STOCK_ITEMS 0x00457EF0u

static char *game_state(void) { return *(char *volatile *)(UINT_PTR)STATE_GLOBAL; }
static int *I(void *base, int offset) { return (int *)((char *)base + offset); }
static void *P(void *base, int offset) { return *(void **)((char *)base + offset); }

static char *fish(char *state, int tank, int slot) {
    return state + FISH_BASE + tank * TANK_STRIDE + slot * SLOT_STRIDE;
}

static unsigned char *ornament(char *state, int tank, int k) {
    return (unsigned char *)state + ORN_BASE + tank * TANK_STRIDE + k * ORN_STRIDE;
}

static void play_sound(int id) {
    void *sound = (void *)(UINT_PTR)SOUND_GET(SOUND_MANAGER(), NULL, id);
    if (sound) SOUND_PLAY(sound, NULL, 0);
}

static int german(void) {
    int *lang = LANGUAGE_PTR;
    return lang != NULL && *lang == 1;
}

/* --------------------------------------------------------- companions */

static int is_companion(char *f, int fin) {
    return *I(f, F_LIVE) != 0 && *I(f, F_BODY) == BODY_SEAHORSE && *I(f, F_FIN) == fin;
}

static int count_in_tank(char *state, int tank, int fin) {
    int s, n = 0;
    for (s = 0; s < SLOTS; ++s) {
        if (is_companion(fish(state, tank, s), fin)) ++n;
    }
    return n;
}

static int is_rock(unsigned char *o) {
    return o[0] != 0 && (*I(o, O_SPRITE) == SPR_ROCK || *I(o, O_SPRITE) == SPR_ROCK_HOME);
}

static int is_home_rock(unsigned char *o) {
    return o[0] != 0 && *I(o, O_SPRITE) == SPR_ROCK_HOME;
}

static int eel_in_tank(char *state, int tank) {
    int k;
    if (count_in_tank(state, tank, FIN_EEL)) return 1;
    for (k = 0; k < ORN_SLOTS; ++k) {
        if (is_home_rock(ornament(state, tank, k))) return 1;
    }
    return 0;
}

static int owned(char *state, int fin) {
    int t;
    for (t = 0; t <= 3; ++t) {
        if (count_in_tank(state, t, fin)) return 1;
    }
    return fin == FIN_EEL && (eel_in_tank(state, 0) || eel_in_tank(state, 1) || eel_in_tank(state, 2));
}

static int clamp100(int v) { return v < 0 ? 0 : v > 100 ? 100 : v; }

/* After the game's own health tick for one fish, one age step. */
static void __cdecl companion_effects(char *f, int tank) {
    char *state = game_state();
    int n, health, food;
    if (state == NULL || tank < 0 || tank > 2 || *I(f, F_BODY) == BODY_SEAHORSE) return;
    if (*I(f, F_DISEASE) != 0 || *I(f, F_FOOD) <= 5 || *I(f, F_HEALTH) <= 0) return;
    health = *I(f, F_HEALTH);
    n = count_in_tank(state, tank, FIN_SEAHORSE) + count_in_tank(state, tank, FIN_RAY);
    while (n-- > 0) {
        if (RANDOM(100) < 82) ++health;
    }
    *I(f, F_HEALTH) = clamp100(health);
    food = *I(f, F_FOOD);
    n = count_in_tank(state, tank, FIN_PUFFER);
    while (n-- > 0) {
        ++food;
        if (RANDOM(100) < 60) ++food;
    }
    *I(f, F_FOOD) = clamp100(food);
}

/* At the death test: 1 = this fish lives on. */
static int __cdecl eel_save(char *f, int tank) {
    char *state = game_state();
    if (state == NULL || tank < 0 || tank > 2 || !eel_in_tank(state, tank)) return 0;
    if (RANDOM(10) != 0) return 0;
    *I(f, F_HEALTH) = 10;
    return 1;
}

/* A seahorse-type record, as the game builds the Golden Seahorse's. */
static void make_companion(char *state, char *rec, int fin, int health, int food) {
    void *helper;
    memset(rec, 0, SLOT_STRIDE);
    FISH_INIT(rec, NULL);
    *I(rec, F_BODY) = BODY_SEAHORSE;
    *I(rec, F_FIN) = fin;
    *I(rec, F_SPRITES) = 10001;
    *I(rec, F_SPRITES + 4) = 12101;
    *I(rec, F_SPRITES + 8) = 12101;
    helper = FISH_SPRITES_HELPER();
    FISH_SPRITES(helper, NULL, (int)(UINT_PTR)(rec + F_SPRITES), BODY_SEAHORSE, BODY_SEAHORSE);
    *I(rec, F_HEALTH) = health;
    *I(rec, F_DISEASE) = 0;
    *I(rec, F_FOOD) = food;
    *I(rec, F_AGE) = 21;
    *I(rec, F_LAST_AGE) = 21;
    *I(rec, F_PREGNANT) = 0;
    *I(rec, F_LIVE) = STATE_NOW(state, NULL);
}

/* The stage-3 draw: each animal's own sheet, centred on the seahorse's box. */
static int __cdecl companion_sheet(int fin, int *x, int *y) {
    int k = fin - FIN_PUFFER, w, h, nx;
    if (k < 0 || k > 2) return 0x65;
    w = COMPANION_CELL[k][0];
    h = COMPANION_CELL[k][1];
    nx = *x + 57 - w / 2;
    if (nx < 0) nx = 0;
    if (nx > 800 - w) nx = 800 - w;
    *x = nx;
    *y = *y + 30 - h / 2;
    return SPR_SHEET + k;
}

/* ----------------------------------------------------------- the eel */

static int inside(int x, int y, int left, int top, int right, int bottom) {
    return x >= left && x <= right && y >= top && y <= bottom;
}

/* A fish dropped in the tank: the eel on its rock goes home.  1 = handled. */
static int __cdecl eel_drop(char *impl, int tank, int slot, int entry, int x, int y) {
    char *state = (char *)P(impl, 0x34);
    char *f;
    int k;
    if (state == NULL || tank < 0 || tank > 2 || tank != *I(state, S_CURRENT_TANK) || slot < 0 || slot >= SLOTS) return 0;
    f = fish(state, tank, slot);
    if (!is_companion(f, FIN_EEL)) return 0;
    for (k = 0; k < ORN_SLOTS; ++k) {
        unsigned char *o = ornament(state, tank, k);
        if (o[0] == 0 || *I(o, O_SPRITE) != SPR_ROCK) continue;
        if (!inside(x, y, *I(o, O_X), *I(o, O_Y), *I(o, O_X) + *I(o, O_W), *I(o, O_Y) + *I(o, O_H))) continue;
        o[O_HOME_HEALTH] = (unsigned char)clamp100(*I(f, F_HEALTH));
        o[O_HOME_FOOD] = (unsigned char)clamp100(*I(f, F_FOOD));
        o[O_HOME_FLAG] = HOME_FLAG;
        *I(o, O_SPRITE) = SPR_ROCK_HOME;
        REMOVE_FISH(state, NULL, tank, slot);
        VIEW_MOVE(P(impl, 0x3C), NULL, entry, -1, 1, -1);
        return 1;
    }
    return 0;
}

/* A click in the tank: on the head of an eel at home, the eel comes out.  1 = handled. */
static int __cdecl eel_click(char *impl, int x, int y) {
    char *state = (char *)P(impl, 0x34);
    char rec[SLOT_STRIDE];
    int tank, k;
    if (state == NULL) return 0;
    tank = *I(state, S_CURRENT_TANK);
    if (tank < 0 || tank > 2) return 0;
    for (k = 0; k < ORN_SLOTS; ++k) {
        unsigned char *o = ornament(state, tank, k);
        int ox, oy;
        if (!is_home_rock(o)) continue;
        ox = *I(o, O_X);
        oy = *I(o, O_Y);
        if (!inside(x, y, ox + HEAD_BOX[0], oy + HEAD_BOX[1], ox + HEAD_BOX[2], oy + HEAD_BOX[3])) continue;
        make_companion(state, rec, FIN_EEL,
                       o[O_HOME_FLAG] == HOME_FLAG && o[O_HOME_HEALTH] > 0 ? o[O_HOME_HEALTH] : 80,
                       o[O_HOME_FLAG] == HOME_FLAG ? o[O_HOME_FOOD] : 50);
        if (ADD_FISH(state, NULL, tank, (int)(UINT_PTR)rec) == -1) {
            HINT(P(impl, 0x44), NULL, 6);          /* "The tank is full!" */
            return 1;
        }
        o[O_HOME_HEALTH] = o[O_HOME_FOOD] = o[O_HOME_FLAG] = 0;
        *I(o, O_SPRITE) = SPR_ROCK;
        VIEW_SYNC(P(impl, 0x3C), NULL, (int)(UINT_PTR)fish(state, tank, 0));   /* as after a hatch */
        play_sound(0xC);
        return 1;
    }
    return 0;
}

/* The eel at home: the part of it behind the rock, then (after every
   ornament) the part in front, the DS in-rock animation. */
static void draw_home(char *impl, int sprite) {
    char *state = (char *)P(impl, 0x34);
    int tank, k, frame = (int)((GetTickCount() / 110u) % HOME_FRAMES);
    if (state == NULL) return;
    tank = *I(state, S_CURRENT_TANK);
    if (tank < 0 || tank > 2) return;
    for (k = 0; k < ORN_SLOTS; ++k) {
        unsigned char *o = ornament(state, tank, k);
        void *img;
        if (!is_home_rock(o)) continue;
        img = (void *)(UINT_PTR)SPRITE_GRID(P(impl, 0x38), NULL, sprite);
        if (img) DRAW_CELL(P(impl, 0x54), NULL, (int)(UINT_PTR)img, *I(o, O_X), *I(o, O_Y), frame);
    }
}

static void __cdecl draw_home_backs(char *impl) { draw_home(impl, SPR_HOME_BACK); }
static void __cdecl draw_home_fronts(char *impl) { draw_home(impl, SPR_HOME_FRONT); }

/* ------------------------------------------------------ Exotic Fish Eggs */

/* The egg switch for item 28: the stock egg sequence with DS-only genes. */
static void __cdecl exotic_hatch(char *impl, int x, int y) {
    char *state = (char *)P(impl, 0x34);
    int count;
    void *sound = (void *)(UINT_PTR)SOUND_GET(P(impl, 0x4C), NULL, 0xC);
    if (sound) SOUND_PLAY(sound, NULL, 0);
    SPLASH(P(impl, 0x3C), NULL, 4, x, y);
    *I(impl, 0x30) = CLOCK_NOW() + 10;
    state = (char *)P(impl, 0x34);
    *I(state, S_EGG_COUNT) = 0;
    *I(state, S_EGG_PRESENT) = 0;
    *I(state, S_EGG_ICON) = 0;
    *I(state, S_EGG_CURSOR) = 0;
    *I(state, S_EGG_ITEM) = 0;
    count = RANDOM(2) + *I(state, S_EGG_PLANT) + 3;
    if (*I(state, S_EASY) == 0) ++count;
    while (count-- > 0) {
        int fin = DS_FIRST_GENE + RANDOM(DS_GENES);
        int body = DS_FIRST_GENE + RANDOM(DS_GENES);
        NEW_BABY(impl, NULL, body, fin, body, fin, body, fin, body, fin, body, fin, body, fin, 1,
                 *I(state, S_CURRENT_TANK));
    }
}

/* ------------------------------------------------------- the store page */

typedef struct store_item {
    int fin;                       /* companion marker, or 0 for the eggs */
    int price;
    int x, y, w, h;                /* the net cell (stock records 0-3) */
    int sprite, icon_w, icon_h;
    const char *name[2];
    const char *text[2];
} store_item;

#define ITEMS 4
static const store_item ITEM[ITEMS] = {
    { FIN_PUFFER, 1250, 44, 83, 85, 70, SPR_ITEM_PUFFER, 80, 60,
      { "Puffer Fish", "Kugelfisch" },
      { "The puffer fish magically enhances your\nenvironment and the life of your fish.\nComes fully installed.",
        "Dieser Kugelfisch verbessert auf\nmagische Weise die Umgebung und das\nLeben deiner Fische.\nWird komplett installiert ausgeliefert." } },
    { FIN_RAY, 1250, 141, 87, 73, 71, SPR_ITEM_PUFFER + 1, 80, 60,
      { "Sting Ray", "Stachelrochen" },
      { "The sting ray magically enhances your\nenvironment and the life of your fish.\nComes fully installed.",
        "Dieser Stachelrochen verbessert auf\nmagische Weise die Umgebung und das\nLeben deiner Fische.\nWird komplett installiert ausgeliefert." } },
    { FIN_EEL, 1250, 234, 93, 71, 71, SPR_ITEM_PUFFER + 2, 80, 60,
      { "Moray Eel", "Mur\xE4ne" },
      { "The moray eel magically enhances your\nenvironment and the life of your fish.\nComes fully installed, with its rock.",
        "Diese Mur\xE4ne verbessert auf\nmagische Weise die Umgebung und das\nLeben deiner Fische. Wird komplett\ninstalliert ausgeliefert, mit ihrem Felsen." } },
    { 0, 2300, 320, 98, 77, 69, SPR_ITEM_EGGS, 60, 36,
      { "Exotic Fish Eggs", "Exotische Fischeier" },
      { "These special eggs were extremely hard\nto obtain. Research FISH ENVIRONMENT\nbefore you try to hatch these.",
        "Diese besonderen Eier waren extrem\nschwer zu bekommen. Erforsche\nLEBENSBEDINGUNGEN, bevor du\nversuchst, sie auszubr\xFCten." } },
};

static int page_upgrades = 0;
static int selected = -1, hovered = -1;
static int button_added = 0;
static int empty_items[13] = { -1 };     /* one item record: x = -1, the end */

static char *store_impl(void *scene) { return (char *)P(scene, 8); }

static void enter_page(void *scene) {
    char *impl = store_impl(scene);
    *I(impl, 0x28) = (int)(UINT_PTR)empty_items;
    *I(impl, 0) = *I(impl, 4) = *I(impl, 8) = ITEM_NONE;
    selected = hovered = -1;
    page_upgrades = 1;
}

static void leave_page(void *scene) {
    char *impl = store_impl(scene);
    *I(impl, 0x28) = (int)STOCK_ITEMS;
    *I(impl, 0) = *I(impl, 4) = *I(impl, 8) = ITEM_NONE;
    selected = hovered = -1;
    page_upgrades = 0;
}

static void add_button(void *scene) {
    void *button = OPERATOR_NEW(0x14);
    void *sound;
    if (button == NULL) return;
    button = (void *)(UINT_PTR)BUTTON_INIT(button, NULL, 3, (int)(UINT_PTR)"SuppliesUpgradesButton.png",
                                           UPGRADES_X, UPGRADES_Y, (int)(UINT_PTR)scene, 0);
    if (button == NULL) return;
    sound = (void *)(UINT_PTR)SOUND_GET(SOUND_MANAGER(), NULL, 1);
    BUTTON_SOUND(button, NULL, (int)(UINT_PTR)sound, 0);
    ADD_CONTROL(scene, NULL, (int)(UINT_PTR)button);
    button_added = 1;
}

static int hit_item(int x, int y) {
    int i;
    for (i = 0; i < ITEMS; ++i) {
        if (inside(x, y, ITEM[i].x, ITEM[i].y, ITEM[i].x + ITEM[i].w, ITEM[i].y + ITEM[i].h)) return i;
    }
    return -1;
}

static const char *game_string(int id) {
    return (const char *)(UINT_PTR)GET_STRING(STRING_TABLE(), NULL, id);
}

static void draw_text(char *impl, const char *text, int x, int y, void *font, int attr) {
    DRAW_TEXT(P(impl, 0x18), NULL, (int)(UINT_PTR)text, x, y, (int)(UINT_PTR)font, attr);
}

static void draw_page(void *scene) {
    char *impl = store_impl(scene);
    char *state = (char *)P(impl, 0x10);
    int i, lang = german(), pulse;
    DWORD t = GetTickCount() % 1600u;
    pulse = 0x30 + (int)((t < 800u ? t : 1600u - t) * 0x50u / 800u);
    for (i = 0; i < ITEMS; ++i) {
        const store_item *it = &ITEM[i];
        void *img = (void *)(UINT_PTR)SPRITE_GET(P(impl, 0x14), NULL, it->sprite);
        int x = it->x + (it->w - it->icon_w) / 2, y = it->y + (it->h - it->icon_h) / 2;
        if (img == NULL) continue;
        if (i == selected) {
            DRAW_ALPHA(P(impl, 0x18), NULL, (int)(UINT_PTR)img, x, y, pulse, 1, 0);
        } else if (i == hovered) {
            DRAW_ALPHA(P(impl, 0x18), NULL, (int)(UINT_PTR)img, x, y, 0x78, 1, 0);
        } else {
            DRAW(P(impl, 0x18), NULL, (int)(UINT_PTR)img, x, y);
        }
    }
    if (selected >= 0 && state != NULL) {
        const store_item *it = &ITEM[selected];
        draw_text(impl, it->name[lang], 0x39, 0x159, FONT_TITLE, *I(impl, 0x24));
        draw_text(impl, it->text[lang], 0x39, 0x181, FONT_BODY, 0);
        if (it->fin != 0 && owned(state, it->fin)) {
            draw_text(impl, game_string(0xE9), 0x39, 0x1FD, FONT_BODY, 0);   /* "This is in your inventory." */
        } else {
            char line[64];
            const char *label = game_string(0xAD);                            /* "Price:" */
            int n = 0, v = it->price, d = 0;
            char digits[12];
            while (*label && n < 40) line[n++] = *label++;
            line[n++] = ' ';
            line[n++] = ' ';
            line[n++] = '$';
            do { digits[d++] = (char)('0' + v % 10); v /= 10; } while (v && d < 11);
            while (d) line[n++] = digits[--d];
            line[n] = '\0';
            draw_text(impl, line, 0x39, 0x1FD, FONT_BODY, 0);
        }
    }
}

static int confirm(char *impl, int string_id) {
    char dialog[0x400];
    int answer;
    DIALOG_INIT(dialog, NULL, string_id, 1);
    answer = DIALOG_RUN(dialog, NULL, (int)(UINT_PTR)P(impl, 0x20), 0);
    DIALOG_FREE(dialog, NULL);
    return answer == 0;
}

static int free_fish_slot(char *state, int tank) {
    int s;
    for (s = 0; s < SLOTS; ++s) {
        if (*I(fish(state, tank, s), F_LIVE) == 0) return 1;
    }
    return 0;
}

static int free_ornament_slot(char *state, int tank) {
    int k;
    for (k = 0; k < ORN_SLOTS; ++k) {
        if (ornament(state, tank, k)[0] == 0) return 1;
    }
    return 0;
}

/* Tanks in the order a new animal tries them: the one you came from, then
   the stock order (Tank 1, Tank 2 if bought, the selling tank). */
static int tank_order(char *state, int *order) {
    int n = 0, t, current = *I(state, S_CURRENT_TANK);
    if (current >= 0 && current <= 2) order[n++] = current;
    for (t = 0; t <= 2; ++t) {
        if (t == current || (t == 1 && *I(state, S_SECOND_TANK) == 0)) continue;
        order[n++] = t;
    }
    return n;
}

static void charge(char *state, int price) {
    *I(state, S_MONEY) -= price;
    *I(state, S_SPENT) += price;
    play_sound(0xE);
}

static void buy(void *scene) {
    char *impl = store_impl(scene);
    char *state = (char *)P(impl, 0x10);
    const store_item *it;
    void *hint = P(impl, 0xC);
    if (selected < 0 || state == NULL) return;
    it = &ITEM[selected];
    if (it->fin != 0 && owned(state, it->fin)) {
        HINT(hint, NULL, 0x1C);                      /* "You already own this!" */
        return;
    }
    if (it->price > *I(state, S_MONEY)) {
        HINT(hint, NULL, 2);                         /* "You can't afford to buy this yet!" */
        return;
    }
    if (it->fin == 0) {
        if (!confirm(impl, *I(state, S_EGG_PRESENT) ? 0xED : 0xEC)) return;
        charge(state, it->price);
        *I(state, S_EGG_ITEM) = EXOTIC_ITEM;
        *I(state, S_EGG_PRESENT) = 1;
        *I(state, S_EGG_COUNT) = 3;
        *I(state, S_EGG_ICON) = SPR_ITEM_EGGS;
        *I(state, S_EGG_CURSOR) = SPR_TOOL_EGGS;
        *I(state, S_EGG_X) = 3 * 0x30 + 0x1E;
        return;
    } else {
        int order[3], n = tank_order(state, order), i, fish_tank = -1, rock_tank = -1;
        char rec[SLOT_STRIDE];
        for (i = 0; i < n && fish_tank < 0; ++i) {
            if (free_fish_slot(state, order[i])) fish_tank = order[i];
        }
        if (it->fin == FIN_EEL && fish_tank >= 0) {
            if (free_ornament_slot(state, fish_tank)) rock_tank = fish_tank;
            for (i = 0; i < n && rock_tank < 0; ++i) {
                if (free_ornament_slot(state, order[i])) rock_tank = order[i];
            }
        }
        if (fish_tank < 0 || (it->fin == FIN_EEL && rock_tank < 0)) {
            HINT(hint, NULL, 6);                     /* "The tank is full!" */
            return;
        }
        if (!confirm(impl, 0xEC)) return;
        make_companion(state, rec, it->fin, 80 + RANDOM(15), 50);
        if (ADD_FISH(state, NULL, fish_tank, (int)(UINT_PTR)rec) == -1) {
            HINT(hint, NULL, 6);
            return;
        }
        if (it->fin == FIN_EEL) {
            unsigned char rock[ORN_STRIDE];
            memset(rock, 0, sizeof rock);
            rock[0] = 1;
            *I(rock, O_X) = 200;
            *I(rock, O_Y) = 250;
            *I(rock, O_FALLING) = 1;
            *I(rock, O_H) = ROCK_H;
            *I(rock, O_W) = ROCK_W;
            *I(rock, O_SPRITE) = SPR_ROCK;
            GAME(this2_fn, 0x00419C00u)(state, NULL, rock_tank, (int)(UINT_PTR)rock);
        }
        charge(state, it->price);
    }
}

/* The Supplies scene's vtable slots. */
static int __fastcall on_mouse(void *scene, void *edx, int type, int x, int y) {
    if (!page_upgrades) return GAME(this3_fn, SITE_VT_MOUSE_HOLDS)(scene, edx, type, x, y);
    if (type == 1) {
        hovered = hit_item(x, y);
    } else if (type == 3) {
        int hit = hit_item(x, y);
        if (hit >= 0) selected = hit;
    }
    return 0;
}

static int __fastcall on_command(void *scene, void *edx, int command, int id) {
    if (command == 8 && id == 3) {
        if (page_upgrades) leave_page(scene); else enter_page(scene);
        return 1;
    }
    if (page_upgrades && command == 8 && id == 1) {
        buy(scene);
        return 0;
    }
    if (page_upgrades && command == 8 && id == 2) {
        leave_page(scene);
    }
    return GAME(this2_fn, SITE_VT_COMMAND_HOLDS)(scene, edx, command, id);
}

static void __fastcall on_overlay(void *scene, void *edx) {
    (void)edx;
    if (page_upgrades) draw_page(scene);
}

static void __fastcall on_activate(void *scene, void *edx, int active) {
    GAME(this1_fn, SITE_VT_ACTIVATE_HOLDS)(scene, edx, active);
    leave_page(scene);
    if (!button_added) add_button(scene);
}

/* ------------------------------------------------------------------ stubs */

static const DWORD k_health_tick = 0x0041DF50u;
static const DWORD k_dead_join = 0x0042062Eu, k_alive_join = 0x00420649u;
static const DWORD k_customer_join = 0x0042427Du, k_customer_skip = 0x0042448Au;
static const DWORD k_thought_join = 0x0041356Cu, k_thought_skip = 0x00413622u;
static const DWORD k_egg_join = 0x0042135Fu, k_egg_done = 0x00421437u;
static const DWORD k_egg_confirm_yes = 0x004281B7u, k_egg_confirm_no = 0x004281D6u;
static const DWORD k_draw_ornaments = 0x0041D600u;
static const DWORD k_drop_join = 0x0041F06Du, k_drop_done = 0x0041F0F9u;
static const DWORD k_pick_join = 0x0041E579u;
static const DWORD k_draw_join = 0x00414C93u;

/* Replaces `call 0x41DF50` (the per-step health tick): the tick, then the
   companions' effects.  ebp is the tank there. */
__declspec(naked) static void stub_tick(void) {
    __asm {
        push dword ptr [esp + 4]
        call k_health_tick
        pushad
        push ebp
        push dword ptr [esp + 0x28]
        call companion_effects
        add esp, 8
        popad
        ret 4
    }
}

__declspec(naked) static void stub_death(void) {
    __asm {
        mov edx, [esi + 0x34]
        cmp dword ptr [edi + edx + 0x3CC], ebx
        jg alive
        pushad
        lea eax, [edi + edx + 0x390]
        push ebp
        push eax
        call eel_save
        add esp, 8
        test eax, eax
        popad
        jnz alive
        jmp k_dead_join
    alive:
        jmp k_alive_join
    }
}

__declspec(naked) static void stub_customers(void) {
    __asm {
        cmp dword ptr [esi + ebx + 0xA774], 0x14
        jl skip
        cmp dword ptr [esi + ebx + 0xA7B4], BODY_SEAHORSE
        je skip
        jmp k_customer_join
    skip:
        jmp k_customer_skip
    }
}

__declspec(naked) static void stub_thoughts(void) {
    __asm {
        cmp dword ptr [edx + 0xA774], 0x14
        jl skip
        cmp dword ptr [edx + 0xA7B4], BODY_SEAHORSE
        je skip
        jmp k_thought_join
    skip:
        jmp k_thought_skip
    }
}

/* The egg switch; x is edi and y ebx there. */
__declspec(naked) static void stub_egg_use(void) {
    __asm {
        mov edx, [esi + 0x34]
        mov eax, [edx + 0x30C]
        cmp eax, EXOTIC_ITEM
        je exotic
        jmp k_egg_join
    exotic:
        push ebx
        push edi
        push esi
        call exotic_hatch
        add esp, 12
        jmp k_egg_done
    }
}

/* Buying stock eggs over Exotic Eggs asks "Replace eggs in slot #4?" too. */
__declspec(naked) static void stub_egg_confirm(void) {
    __asm {
        cmp ecx, 0xAC
        je eggs
        cmp ecx, SPR_ITEM_EGGS
        je eggs
        jmp k_egg_confirm_no
    eggs:
        jmp k_egg_confirm_yes
    }
}

/* Replaces the tail `jmp 0x41D600` (the ornaments); ecx is the tank scene. */
__declspec(naked) static void stub_ornaments(void) {
    __asm {
        push ecx
        push ecx
        call draw_home_backs
        add esp, 4
        mov ecx, [esp]
        call k_draw_ornaments
        call draw_home_fronts
        add esp, 4
        ret
    }
}

/* A fish dropped: [esp+0x10] tank, ebp slot, ebx view entry, [esp+0x1C] x, [esp+0x20] y. */
__declspec(naked) static void stub_fish_drop(void) {
    __asm {
        pushad
        push dword ptr [esp + 0x40]
        push dword ptr [esp + 0x40]
        push ebx
        push ebp
        push dword ptr [esp + 0x40]
        push esi
        call eel_drop
        add esp, 24
        test eax, eax
        popad
        jnz handled
        mov ecx, [esi + 0x34]
        mov eax, [ecx + 0x384]
        jmp k_drop_join
    handled:
        jmp k_drop_done
    }
}

/* The ornament pick (x, y); a click on the eel's head lets it out instead. */
__declspec(naked) static void stub_ornament_pick(void) {
    __asm {
        pushad
        push dword ptr [esp + 0x28]
        push dword ptr [esp + 0x28]
        push ecx
        call eel_click
        add esp, 12
        test eax, eax
        popad
        jnz handled
        mov eax, [ecx + 0x34]
        mov edx, [eax + 0x384]
        jmp k_pick_join
    handled:
        xor eax, eax
        ret 8
    }
}

/* The stage-3 draw: eax frame, ebx x, [esp+0x24] y, esi the fish record. */
__declspec(naked) static void stub_draw_companion(void) {
    __asm {
        mov edx, [esp + 0x24]
        push eax
        push edx
        push ebx
        lea ecx, [esp + 4]
        push ecx
        lea ecx, [esp + 4]
        push ecx
        push dword ptr [esi + 0x50]
        call companion_sheet
        add esp, 12
        push eax
        jmp k_draw_join
    }
}

/* ----------------------------------------------------------------- install */

#define CODE_ADDR(f) ((const void *)(UINT_PTR)(f))
#define TOTAL_SITES 14
static ftfp_site_write writes[TOTAL_SITES];
static int installed = 0;
static int host_ok = 0;

#define JMP(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE9, CODE_ADDR(TO))
#define CALL(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE8, CODE_ADDR(TO))
#define SLOT(W, NAME, TO) ftfp_site_imm32((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0, (unsigned int)(UINT_PTR)(TO))

static int prepare(void) {
    ftfp_site_write *w = writes;
    JMP(w++, DRAW_COMPANION, stub_draw_companion);
    CALL(w++, TICK, stub_tick);
    JMP(w++, DEATH, stub_death);
    JMP(w++, CUSTOMERS, stub_customers);
    JMP(w++, THOUGHTS, stub_thoughts);
    JMP(w++, EGG_USE, stub_egg_use);
    JMP(w++, EGG_CONFIRM, stub_egg_confirm);
    JMP(w++, ORNAMENTS, stub_ornaments);
    JMP(w++, FISH_DROP, stub_fish_drop);
    JMP(w++, ORNAMENT_PICK, stub_ornament_pick);
    SLOT(w++, VT_MOUSE, on_mouse);
    SLOT(w++, VT_COMMAND, on_command);
    SLOT(w++, VT_OVERLAY, on_overlay);
    SLOT(w++, VT_ACTIVATE, on_activate);
    return (int)(w - writes) == TOTAL_SITES;
}

static int name_sprites(const ftfp_store_host *host) {
    sprite_entry *table;
    int i;
    if (host == NULL || host->version != 1 || host->sprites == NULL
        || host->first != STORE_SPRITE_BASE || host->count < STORE_SPRITES) {
        return 0;
    }
    table = (sprite_entry *)host->sprites;
    for (i = 0; i < STORE_SPRITES; ++i) {
        sprite_entry *s = &table[STORE_SPRITE_BASE + i];
        memset(s, 0, sizeof *s);
        s->id = STORE_SPRITE_BASE + i;
        s->name = SPRITE_FILES[i].name;
        s->cols = SPRITE_FILES[i].cols;
        s->rows = SPRITE_FILES[i].rows;
    }
    return 1;
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

/* "<game>\Fish Tycoon Fix Patcher Files\FTFP DS Store.log", as DS Fish's log. */
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
    wcscat_s(path, 1024, L"Fish Tycoon Fix Patcher Files\\FTFP DS Store.log");
    if (installed) {
        len = append_text(line, len, "DS Store: installed (all sites)\r\n");
    } else if (!host_ok) {
        len = append_text(line, len, "DS Store: NOT installed; FTFP DS Fish.dll is not the version this build expects\r\n");
    } else if (ftfp_failed_site != 0) {
        len = append_text(line, len, "DS Store: NOT installed; the code at ");
        len = append_hex(line, len, ftfp_failed_site);
        len = append_text(line, len, " is not the stock code this build expects\r\n");
    } else {
        len = append_text(line, len, "DS Store: NOT installed\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* Called once by FTFP DS Fish.dll, after its own install, before WinMain. */
int __stdcall FtfpStoreStartup(const ftfp_store_host *host) {
    if (installed) return 1;
    __try {
        host_ok = name_sprites(host);
        if (host_ok && prepare() && ftfp_install_sites(writes, TOTAL_SITES)) {
            installed = 1;
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    return installed;
}

int __stdcall FtfpDsStoreInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
