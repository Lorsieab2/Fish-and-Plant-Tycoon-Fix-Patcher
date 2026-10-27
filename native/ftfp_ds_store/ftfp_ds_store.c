/* DS Store Items -- the Nintendo DS store items in PC Fish Tycoon.

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

   HOW.  "DS Store Items.dll" sits beside "DS Exclusive Fish.dll", which loads it
   after its own install and lends it sprite table entries 220-235.  Every
   write into the game is in store_sites.h -- all of them or none.

   STATE.  Nothing new is saved.  An animal is a seahorse-type fish record
   (body 22) whose fin marks the animal: 22 Golden Seahorse, 30 Puffer Fish,
   31 Sting Ray, 32 Moray Eel -- so every rule the game has for the seahorse
   applies to them.  The animals (the Golden Seahorse too) live in the last
   five of each tank's 31 fish records, slots 26-30, which no stock gameplay
   loop reaches (the game uses 21, or 26 with "Bigger tanks"), so they never
   take a fish's place; they are saved with the game.  The rock is one of the tank's ornament records; while
   the eel is home, the rock record's spare bytes keep its health and food.
   Owning an animal means it is in a tank: one of each, bought again after
   it is trashed.  With "Buy Multiple Golden Seahorses" patched in, the store
   sells them however many are already in the tanks, as it does the seahorse
   (each eel comes with its own rock). */
#include <windows.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "store_sites.h"
#include "store_data.h"

#define STATE_GLOBAL 0x0045ABDCu
#define FISH_BASE 0x390
#define TANK_STRIDE 0x51EC
#define SLOT_STRIDE 0x288
#define RECORDS 31                  /* fish records per tank; the game uses 21 (26 with "Bigger tanks") */
#define ANIMAL_FIRST 26             /* the animals' slots: 26-30 */
#define ANIMAL_SLOTS 5
#define F_MARK 0x14                 /* mate-gene fields, read only by breeding: the animal signature */
#define F_KIND 0x18
#define ANIMAL_MARK 0x41435446      /* "FTCA" */
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
#define ROCK_SINK 14                 /* the rock sits this much deeper in the gravel than its art's height */
#define ROCK_FLOOR_H (ROCK_H - ROCK_SINK)
#define SPR_SHADOW 3                 /* TANK_OBJECT_SHADOW.png, 135 x 33 */
#define SHADOW_W 135
#define HOME_FRAME_MS 10000u         /* the in-rock animation, played forward then back (user: very gradual) */
#define O_HOME_HEALTH 1             /* spare bytes after the active byte */
#define O_HOME_FOOD 2
#define O_HOME_FLAG 3
#define HOME_FLAG 0xE1

#define S_CURRENT_TANK 0x384
#define S_MONEY 0x38C
#define S_SPENT 0x24
#define S_SECOND_TANK 0x230
/* The egg plant's dword: the game's own hatch code (0x4213DB, mov ecx, [edi + disp32]) names it,
   0x17C as shipped or 0x168 with Fix Vanilla Bugs, so Exotic Fish Eggs follow the same plant. */
#define S_EGG_PLANT (*(const int *)0x004213DDu)
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
#define SPR_PUFF (STORE_SPRITE_BASE + 12)
#define STORE_SPRITES 13

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
    { "DS_PUFFER_PUFF_Grid.png", 4, 2 },        /* the puffer puffed up: left, then right */
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

static int is_animal(char *f) {
    return *I(f, F_LIVE) != 0 && *I(f, F_BODY) == BODY_SEAHORSE && *I(f, F_MARK) == ANIMAL_MARK;
}

/* An animal of this kind in slots 26-30, or one an earlier build left among the fish. */
static int is_kind(char *f, int slot, int fin) {
    return slot >= ANIMAL_FIRST ? is_animal(f) && *I(f, F_FIN) == fin : is_companion(f, fin);
}

static int count_in_tank(char *state, int tank, int fin) {
    int s, n = 0;
    for (s = 0; s < RECORDS; ++s) {
        if (is_kind(fish(state, tank, s), s, fin)) ++n;
    }
    return n;
}

static int free_animal_slot(char *state, int tank) {
    int s;
    for (s = ANIMAL_FIRST; s < ANIMAL_FIRST + ANIMAL_SLOTS; ++s) {
        if (!is_animal(fish(state, tank, s))) return s;
    }
    return -1;
}

/* Copies an animal's record into a free animal slot of the tank: its slot, or -1. */
static int place_animal(char *state, int tank, char *rec) {
    int slot = tank >= 0 && tank <= 2 ? free_animal_slot(state, tank) : -1;
    if (slot < 0) return -1;
    *I(rec, F_MARK) = ANIMAL_MARK;
    *I(rec, F_KIND) = *I(rec, F_FIN);
    memcpy(fish(state, tank, slot), rec, SLOT_STRIDE);
    return slot;
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

/* "Buy Multiple Golden Seahorses" (fish manifest patch
   redirect_golden_seahorse_store_blocker) puts this jump at 0x4282B2. */
static const unsigned char REPURCHASE_JUMP[10] = { 0xE9, 0x49, 0x75, 0x01, 0x00, 0x90, 0x90, 0x90, 0x90, 0x90 };

static int sold_out(char *state, int fin) {
    static int repurchase = -1;
    if (repurchase < 0) repurchase = ftfp_site_holds(0x004282B2u, REPURCHASE_JUMP, sizeof REPURCHASE_JUMP);
    return fin != 0 && !repurchase && owned(state, fin);
}

static int clamp100(int v) { return v < 0 ? 0 : v > 100 ? 100 : v; }

/* After the game's own health tick for one fish, one age step. */
static void __cdecl companion_effects(char *f, int tank) {
    char *state = game_state();
    int n, health, food;
    if (state != NULL && *I(state, S_EGG_ICON) == SPR_ITEM_EGGS) {
        *I(state, S_EGG_ICON) = SPR_TOOL_EGGS;      /* eggs bought with the first builds showed the store picture */
    }
    if (state != NULL) {                             /* rocks from the first builds sat too high on the gravel */
        int t, k;
        for (t = 0; t <= 2; ++t) {
            for (k = 0; k < ORN_SLOTS; ++k) {
                unsigned char *o = ornament(state, t, k);
                if (is_rock(o) && *I(o, O_H) == ROCK_H) {
                    *I(o, O_H) = ROCK_FLOOR_H;
                    *I(o, O_Y) += ROCK_H - ROCK_FLOOR_H;
                }
            }
        }
    }
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

/* Every 26 seconds or so (each puffer on its own clock) the puffer puffs up
   while it swims: the DS's puff-up frames 1, 2, 3, held, then back.  0 = not now. */
static int puff_stage(char *rec) {
    DWORD t = (GetTickCount() + (DWORD)(UINT_PTR)rec * 2654435761u) % 26000u;
    if (t < 300u) return 1;
    if (t < 600u) return 2;
    if (t < 3600u) return 3;
    if (t < 3900u) return 2;
    if (t < 4200u) return 1;
    return 0;
}

/* The stage-3 draw: each animal's own sheet, centred on the seahorse's box. */
static int __cdecl companion_sheet(char *rec, int *x, int *y, int *frame) {
    int fin = *I(rec, F_FIN), k = fin - FIN_PUFFER, w, h, nx, stage;
    if (k < 0 || k > 2) return 0x65;
    w = COMPANION_CELL[k][0];
    h = COMPANION_CELL[k][1];
    nx = *x + 57 - w / 2;
    if (nx < 0) nx = 0;
    if (nx > 800 - w) nx = 800 - w;
    *x = nx;
    *y = *y + 30 - h / 2;
    if (fin == FIN_PUFFER && *frame >= 0 && *frame < 12 && (stage = puff_stage(rec)) != 0) {
        *frame = (*frame >= 6 ? 4 : 0) + stage;           /* 0-5 face left, 6-11 right */
        return SPR_PUFF;
    }
    return SPR_SHEET + k;
}

/* ----------------------------------------------------------- the eel */

static int inside(int x, int y, int left, int top, int right, int bottom) {
    return x >= left && x <= right && y >= top && y <= bottom;
}

/* The tank button under (x, y) (Tank 1, Tank 2, the selling tank), or -1;
   rects at impl+0x58 / +0x68 / +0x78: left, top, right, bottom. */
static int button_tank(char *impl, int x, int y) {
    int t;
    for (t = 0; t <= 2; ++t) {
        int *r = I(impl, 0x58 + t * 0x10);
        if (inside(x, y, r[0], r[1], r[2], r[3])) return t;
    }
    return -1;
}

/* An animal dropped on a tank button: into that tank's animal slots, never the fish's. */
static void move_animal(char *impl, char *state, int tank, int slot, int entry, int to) {
    void *view = P(impl, 0x3C);
    int dest;
    if (to == tank) {
        VIEW_MOVE(view, NULL, entry, tank, 1, -1);            /* back to swimming */
        return;
    }
    if (to == 1 && *I(state, S_SECOND_TANK) == 0) {
        HINT(P(impl, 0x44), NULL, 8);
        VIEW_MOVE(view, NULL, entry, tank, 1, -1);
        return;
    }
    dest = free_animal_slot(state, to);
    if (dest < 0) {
        HINT(P(impl, 0x44), NULL, 6);                         /* "The tank is full!" */
        VIEW_MOVE(view, NULL, entry, tank, 1, -1);
        return;
    }
    memcpy(fish(state, to, dest), fish(state, tank, slot), SLOT_STRIDE);
    REMOVE_FISH(state, NULL, tank, slot);
    VIEW_MOVE(view, NULL, entry, -1, 1, -1);
}

/* A fish dropped in the tank: an animal on a tank button moves there, and
   the eel on its rock goes home.  1 = handled. */
static int __cdecl eel_drop(char *impl, int tank, int slot, int entry, int x, int y) {
    char *state = (char *)P(impl, 0x34);
    char *f;
    int k, to;
    if (state == NULL || tank < 0 || tank > 2 || slot < 0 || slot >= RECORDS) return 0;
    f = fish(state, tank, slot);
    if (slot >= ANIMAL_FIRST && is_animal(f) && (to = button_tank(impl, x, y)) >= 0) {
        move_animal(impl, state, tank, slot, entry, to);
        return 1;
    }
    if (tank != *I(state, S_CURRENT_TANK) || !is_kind(f, slot, FIN_EEL)) return 0;
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

/* The view entry swimming the fish in (tank, slot), or -1. */
static int view_entry(char *impl, int tank, int slot) {
    char *view = *(char **)P(impl, 0x3C);
    int i, n = *I(view, 0x5DD8);
    for (i = 1; i <= n && i < 150; ++i) {
        unsigned char *e = (unsigned char *)view + 0x1080 + i * 0x84;
        if (e[0] && *I(e, 0x40) == tank && *I(e, 0x44) == slot) return i;
    }
    return -1;
}

/* A press in the tank on the head of an eel at home: the eel comes out, already
   held, so it is dragged out of the rock (stock pick 0x41E3F0 does the same for
   a fish).  0 = not here, 1 = handled, 2 = handled and now held. */
static int __cdecl eel_click(char *impl, int x, int y) {
    char *state = (char *)P(impl, 0x34);
    char rec[SLOT_STRIDE];
    unsigned char *e;
    int tank, k, slot, entry;
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
        slot = place_animal(state, tank, rec);
        if (slot < 0) {
            HINT(P(impl, 0x44), NULL, 6);          /* "The tank is full!" */
            return 1;
        }
        o[O_HOME_HEALTH] = o[O_HOME_FOOD] = o[O_HOME_FLAG] = 0;
        *I(o, O_SPRITE) = SPR_ROCK;
        VIEW_SYNC(P(impl, 0x3C), NULL, (int)(UINT_PTR)fish(state, tank, 0));   /* as after a hatch */
        play_sound(0xC);
        entry = view_entry(impl, tank, slot);
        if (entry < 0) return 1;
        e = (unsigned char *)*(char **)P(impl, 0x3C) + 0x1080 + entry * 0x84;
        e[1] = 1;                                   /* held */
        *I(e, 0x4C) = -1;
        GAME(this3_fn, 0x00413B70u)(P(impl, 0x3C), NULL, x, y, entry);
        *I(state, 0x1E4E8) = entry;
        *I(impl, 0x20) = x;
        *I(impl, 0x24) = y;
        play_sound(3);
        return 2;
    }
    return 0;
}

static int remove_out_rock(char *state, int tank) {
    int t, k, pass;
    for (pass = 0; pass < 2; ++pass) {
        for (t = 0; t <= 2; ++t) {
            if ((pass == 0) != (t == tank)) continue;          /* the eel's own tank first */
            for (k = 0; k < ORN_SLOTS; ++k) {
                unsigned char *o = ornament(state, t, k);
                if (o[0] != 0 && *I(o, O_SPRITE) == SPR_ROCK) {
                    memset(o, 0, ORN_STRIDE);
                    return 1;
                }
            }
        }
    }
    return 0;
}

/* 0x41E809, the trash after its "throw away?" answer: an eel takes a rock with it. */
static void __cdecl fish_trashed(char *impl, int tank, int slot) {
    char *state = (char *)P(impl, 0x34);
    if (state == NULL || tank < 0 || tank > 2 || slot < 0 || slot >= RECORDS) return;
    if (is_kind(fish(state, tank, slot), slot, FIN_EEL)) remove_out_rock(state, tank);
}

static int confirm_in(void *parent, int string_id);

/* An ornament dropped (the stock game only moves them): the eel's rock on the
   trash can is thrown away, with its eel (inside it, or the one swimming in
   the same tank, else another).  1 = handled. */
static int __cdecl rock_trash(char *impl, int x, int y) {
    char *state = (char *)P(impl, 0x34);
    int tank, k = *I(impl, 0x28), t, s, pass, done = 0;
    unsigned char *o;
    if (state == NULL || k < 0 || k >= ORN_SLOTS) return 0;
    tank = *I(state, S_CURRENT_TANK);
    if (tank < 0 || tank > 2) return 0;
    o = ornament(state, tank, k);
    if (!is_rock(o) || !inside(x, y, *I(impl, 0x88), *I(impl, 0x8C), *I(impl, 0x90), *I(impl, 0x94))) return 0;
    if (!confirm_in(P(impl, 0x50), 0xAC)) return 0;            /* no: the stock code puts it back */
    if (!is_home_rock(o)) {
        for (pass = 0; pass < 2 && !done; ++pass) {
            for (t = 0; t <= 2 && !done; ++t) {
                if ((pass == 0) != (t == tank)) continue;
                for (s = 0; s < RECORDS && !done; ++s) {
                    if (!is_kind(fish(state, t, s), s, FIN_EEL)) continue;
                    if (t == tank) {
                        int entry = view_entry(impl, t, s);
                        if (entry >= 0) VIEW_MOVE(P(impl, 0x3C), NULL, entry, -1, 0, s);
                    }
                    REMOVE_FISH(state, NULL, t, s);
                    done = 1;
                }
            }
        }
    }
    memset(o, 0, ORN_STRIDE);
    *I(impl, 0x28) = 0x63;
    play_sound(4);
    return 1;
}

/* The eel at home: the part of it behind the rock, then (after every
   ornament) the part in front, the DS in-rock animation.  It idles in the
   cave mouth, very gradually, and every 30-90 s plays the DS's action burst
   (ducks, peeks, lunges, snaps out in front of the rock and bites) at the
   DS's own pace (user). */
#define ACTION_FRAME_MS 120u
#define BITE_MS 500u                 /* the burst's last frame, the bite, is held */
static DWORD next_snap = 0, snap_start = 0;

static DWORD snap_gap(DWORD now) {
    return 30000u + ((now * 1103515245u + 12345u) >> 8) % 60000u;
}

static int home_frame(void) {
    DWORD now = GetTickCount();
    int step;
    if (next_snap == 0) next_snap = now + snap_gap(now);
    if (snap_start == 0 && (int)(now - next_snap) >= 0) snap_start = now;
    if (snap_start != 0) {
        DWORD t = now - snap_start;
        int k;
        for (k = 0; k < HOME_ACTION; ++k) {
            DWORD ms = k == HOME_ACTION - 1 ? BITE_MS : ACTION_FRAME_MS;
            if (t < ms) return HOME_IDLE + k;
            t -= ms;
        }
        snap_start = 0;
        next_snap = now + snap_gap(now);
    }
    step = (int)((now / HOME_FRAME_MS) % (2 * (HOME_IDLE - 1)));
    return step < HOME_IDLE ? step : 2 * (HOME_IDLE - 1) - step;
}

static void draw_home(char *impl, int sprite) {
    char *state = (char *)P(impl, 0x34);
    int tank, k, frame = home_frame();
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

/* The stock pass draws every ornament's shadow (sprite 3, 135 x 33) at
   (x - 25, y + h - 25), which suits the small stock ornaments; under the
   wide rock it sat off to the left.  The rock's shadow is drawn here,
   centred under it, and the stock pass skips it (a falling ornament has no
   shadow, so the rock is marked falling for the length of the pass). */
static unsigned char hid_shadow[ORN_SLOTS];

static void rock_shadows(char *impl) {
    char *state = (char *)P(impl, 0x34);
    int tank, k;
    memset(hid_shadow, 0, sizeof hid_shadow);
    if (state == NULL) return;
    tank = *I(state, S_CURRENT_TANK);
    if (tank < 0 || tank > 2) return;
    for (k = 0; k < ORN_SLOTS; ++k) {
        unsigned char *o = ornament(state, tank, k);
        void *img;
        if (!is_rock(o) || *I(o, O_FALLING) != 0) continue;
        hid_shadow[k] = 1;
        *I(o, O_FALLING) = 1;
        if (*I(impl, 0x28) == k) continue;                   /* being dragged: no shadow, as stock */
        img = (void *)(UINT_PTR)SPRITE_GET(P(impl, 0x38), NULL, SPR_SHADOW);
        if (img) DRAW(P(impl, 0x54), NULL, (int)(UINT_PTR)img,
                      *I(o, O_X) + *I(o, O_W) / 2 - SHADOW_W / 2, *I(o, O_Y) + *I(o, O_H) - 25);
    }
}

static void restore_shadows(char *impl) {
    char *state = (char *)P(impl, 0x34);
    int k, tank;
    if (state == NULL) return;
    tank = *I(state, S_CURRENT_TANK);
    if (tank < 0 || tank > 2) return;
    for (k = 0; k < ORN_SLOTS; ++k) {
        if (hid_shadow[k]) *I(ornament(state, tank, k), O_FALLING) = 0;
    }
    memset(hid_shadow, 0, sizeof hid_shadow);
}

static void __cdecl draw_home_backs(char *impl) {
    rock_shadows(impl);
    draw_home(impl, SPR_HOME_BACK);
}

static void __cdecl draw_home_fronts(char *impl) {
    restore_shadows(impl);
    draw_home(impl, SPR_HOME_FRONT);
}

/* ------------------------------------------------------ Exotic Fish Eggs */

/* The Fix Patcher's "Universal supply slots" setting: supply slots 2-4 are
   records at state + 0x2B8 + k * 0x1C (k = 1..3, slot #4 = k 3), any item in
   any of them, egg stacks counting one hatch per purchase.  Its payload is
   recognised by its use hook (0x420B70 jumps to 0x43F550). */
#define SLOT_RECORD(state, k) ((state) + 0x2B8 + (k) * 0x1C)
#define SR_ITEM 0x00
#define SR_PRESENT 0x04
#define SR_COUNT 0x08
#define SR_ICON 0x0C
#define SR_CURSOR 0x10
#define SR_X 0x14

static int exotic_any_slot;                 /* set at install: the use gate below is in */

static int universal_slots(void) {
    const unsigned char *p = (const unsigned char *)(UINT_PTR)0x00420B70u;
    return p[0] == 0xE9 && *(const int *)(p + 1) == (int)(0x0043F550u - 0x00420B75u);
}

/* The egg switch for item 28: the stock egg sequence with DS-only genes. */
static void __cdecl exotic_hatch(char *impl, int x, int y) {
    char *state = (char *)P(impl, 0x34);
    int count;
    void *sound = (void *)(UINT_PTR)SOUND_GET(P(impl, 0x4C), NULL, 0xC);
    if (sound) SOUND_PLAY(sound, NULL, 0);
    SPLASH(P(impl, 0x3C), NULL, 4, x, y);
    *I(impl, 0x30) = CLOCK_NOW() + 10;
    state = (char *)P(impl, 0x34);
    /* With universal slots the used record sits in slot #4 for the call and a
       stack loses one hatch (the setting's own egg rule); else it is used up. */
    if (!universal_slots() || --*I(state, S_EGG_COUNT) <= 0) {
        *I(state, S_EGG_COUNT) = 0;
        *I(state, S_EGG_PRESENT) = 0;
        *I(state, S_EGG_ICON) = 0;
        *I(state, S_EGG_CURSOR) = 0;
        *I(state, S_EGG_ITEM) = 0;
    }
    count = RANDOM(2) + *I(state, S_EGG_PLANT) + 3;
    if (*I(state, S_EASY) == 0) ++count;
    while (count-- > 0) {
        int fin = DS_FIRST_GENE + RANDOM(DS_GENES);
        int body = DS_FIRST_GENE + RANDOM(DS_GENES);
        NEW_BABY(impl, NULL, body, fin, body, fin, body, fin, body, fin, body, fin, body, fin, 1,
                 *I(state, S_CURRENT_TANK));
    }
}

/* ------------------------------------------------------- creature names */

/* The names the info panel shows for a held animal (user, 2026-10-26).  The
   game's species table has no name for a seahorse-type record, so stock code
   showed none, the Golden Seahorse's included. */
static const char *animal_name(int fin) {
    switch (fin) {
    case FIN_SEAHORSE: return "Golden Seahorse";
    case FIN_PUFFER: return "Magic Pufferfish";
    case FIN_RAY: return "Blue-Spotted Stingray";
    case FIN_EEL: return "Moray Eel";
    default: return NULL;
    }
}

/* After 0x41D980's species lookup (kind 0 = the held fish): an animal's name
   in place of the table's empty one. */
static const char *__cdecl held_name(char *impl, int kind, const char *found) {
    char *state = (char *)P(impl, 0x34), *view, *rec;
    unsigned char *e;
    int i, tank, slot;
    const char *name;
    if (kind != 0 || state == NULL) return found;
    i = *I(state, 0x1E4E8);
    view = *(char **)P(impl, 0x3C);
    if (view == NULL || i < 1 || i >= 150 || i > *I(view, 0x5DD8)) return found;
    e = (unsigned char *)view + 0x1080 + i * 0x84;
    tank = *I(e, 0x40);
    slot = *I(e, 0x44);
    if (tank < 0 || tank > 2 || slot < 0 || slot >= RECORDS) return found;
    rec = fish(state, tank, slot);
    if (*I(rec, F_BODY) != BODY_SEAHORSE) return found;
    name = animal_name(*I(rec, F_FIN));
    return name != NULL ? name : found;
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
      { "Magic Pufferfish", "Magischer Kugelfisch" },
      { "The puffer fish magically enhances your\nenvironment and the life of your fish.\nComes fully installed.",
        "Dieser Kugelfisch verbessert auf\nmagische Weise die Umgebung und das\nLeben deiner Fische.\nWird komplett installiert ausgeliefert." } },
    { FIN_RAY, 1250, 141, 87, 73, 71, SPR_ITEM_PUFFER + 1, 80, 60,
      { "Blue-Spotted Stingray", "Blaupunktrochen" },
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
        if (sold_out(state, it->fin)) {
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

static int confirm_in(void *parent, int string_id) {
    char dialog[0x400];
    int answer;
    DIALOG_INIT(dialog, NULL, string_id, 1);
    answer = DIALOG_RUN(dialog, NULL, (int)(UINT_PTR)parent, 0);
    DIALOG_FREE(dialog, NULL);
    return answer == 0;
}

static int confirm(char *impl, int string_id) { return confirm_in(P(impl, 0x20), string_id); }

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

/* Exotic Eggs with universal slots, as the setting buys stock eggs: confirm,
   then a stack of Exotic Eggs in slots 2-4 gains one hatch, else the first
   empty slot takes them, else the setting's three "replace?" prompts. */
static void buy_exotic_universal(char *impl, char *state, int price) {
    int k, slot = -1, count = 1;
    static const int replace_prompt[4] = { 0, 0xEF, 0xEE, 0xED };
    char *r;
    if (!confirm(impl, 0xEC)) return;
    for (k = 1; k <= 3 && slot < 0; ++k) {
        r = SLOT_RECORD(state, k);
        if (*I(r, SR_ICON) != 0 && *I(r, SR_ITEM) == EXOTIC_ITEM) {
            slot = k;
            count = *I(r, SR_COUNT) + 1;
        }
    }
    for (k = 1; k <= 3 && slot < 0; ++k)
        if (*I(SLOT_RECORD(state, k), SR_ICON) == 0) slot = k;
    for (k = 1; k <= 3 && slot < 0; ++k)
        if (confirm(impl, replace_prompt[k])) slot = k;
    if (slot < 0) return;
    charge(state, price);
    r = SLOT_RECORD(state, slot);
    *I(r, SR_ITEM) = EXOTIC_ITEM;
    *I(r, SR_PRESENT) = 1;
    *I(r, SR_COUNT) = count;
    *I(r, SR_ICON) = SPR_TOOL_EGGS;
    *I(r, SR_CURSOR) = SPR_TOOL_EGGS;
    *I(r, SR_X) = slot * 0x30 + 0x1E;
}

static void buy(void *scene) {
    char *impl = store_impl(scene);
    char *state = (char *)P(impl, 0x10);
    const store_item *it;
    void *hint = P(impl, 0xC);
    if (selected < 0 || state == NULL) return;
    it = &ITEM[selected];
    if (sold_out(state, it->fin)) {
        HINT(hint, NULL, 0x1C);                      /* "You already own this!" */
        return;
    }
    if (it->price > *I(state, S_MONEY)) {
        HINT(hint, NULL, 2);                         /* "You can't afford to buy this yet!" */
        return;
    }
    if (it->fin == 0 && exotic_any_slot) {
        buy_exotic_universal(impl, state, it->price);
        return;
    }
    if (it->fin == 0) {
        if (!confirm(impl, *I(state, S_EGG_PRESENT) ? 0xED : 0xEC)) return;
        charge(state, it->price);
        *I(state, S_EGG_ITEM) = EXOTIC_ITEM;
        *I(state, S_EGG_PRESENT) = 1;
        *I(state, S_EGG_COUNT) = 3;
        *I(state, S_EGG_ICON) = SPR_TOOL_EGGS;      /* the shelf shows the small picture, as stock eggs do */
        *I(state, S_EGG_CURSOR) = SPR_TOOL_EGGS;
        *I(state, S_EGG_X) = 3 * 0x30 + 0x1E;
        return;
    } else {
        int order[3], n = tank_order(state, order), i, fish_tank = -1, rock_tank = -1;
        char rec[SLOT_STRIDE];
        for (i = 0; i < n && fish_tank < 0; ++i) {
            if (free_animal_slot(state, order[i]) >= 0) fish_tank = order[i];
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
        if (place_animal(state, fish_tank, rec) < 0) {
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
            *I(rock, O_H) = ROCK_FLOOR_H;
            *I(rock, O_W) = ROCK_W;
            *I(rock, O_SPRITE) = SPR_ROCK;
            GAME(this2_fn, 0x00419C00u)(state, NULL, rock_tank, (int)(UINT_PTR)rock);
        }
        charge(state, it->price);
    }
}

/* The stock Golden Seahorse purchase (0x427E43): into the animal slots, the
   tank you came from first.  1 = placed; 0 = no room (the stock refund). */
static int __cdecl place_seahorse(char *state, char *rec, int now) {
    int order[3], n = tank_order(state, order), i;
    *I(rec, F_LIVE) = now;
    *I(rec, F_PREGNANT) = 0;
    for (i = 0; i < n; ++i) {
        if (place_animal(state, order[i], rec) >= 0) return 1;
    }
    return 0;
}

/* New game (after the stock clear of slots 0-20): the animal slots too. */
static void __cdecl clear_animals(char *state) {
    int t, s;
    for (t = 0; t <= 3; ++t) {
        for (s = ANIMAL_FIRST; s < RECORDS; ++s) {
            *I(fish(state, t, s), F_LIVE) = 0;
            *I(fish(state, t, s), F_MARK) = 0;
        }
    }
}

/* After a save loads: leftovers in the animal slots are cleared, and animals
   an earlier build kept among the fish move to their own slots. */
static void settle_animals(char *state) {
    int t, s, to, k;
    for (t = 0; t <= 3; ++t) {
        for (s = ANIMAL_FIRST; s < RECORDS; ++s) {
            char *f = fish(state, t, s);
            if (*I(f, F_LIVE) != 0 && !is_animal(f)) {
                *I(f, F_LIVE) = 0;
                *I(f, F_MARK) = 0;
            }
        }
    }
    for (t = 0; t <= 3; ++t) {
        for (s = 0; s < ANIMAL_FIRST; ++s) {
            char *f = fish(state, t, s);
            int fin = *I(f, F_FIN);
            if (*I(f, F_LIVE) == 0 || *I(f, F_BODY) != BODY_SEAHORSE) continue;
            if (fin != FIN_SEAHORSE && (fin < FIN_PUFFER || fin > FIN_EEL)) continue;
            for (k = 0, to = -1; k < 4 && to < 0; ++k) {
                int target = k == 0 ? (t <= 2 ? t : 0) : k - 1;
                char rec[SLOT_STRIDE];
                memcpy(rec, f, SLOT_STRIDE);
                if (place_animal(state, target, rec) >= 0) to = target;
            }
            if (to >= 0) REMOVE_FISH(state, NULL, t, s);
        }
    }
}

typedef int (__fastcall *load_fn)(void *state, void *edx, int slot);

static int __fastcall on_state_load(char *state, void *edx, int slot) {
    int ok = GAME(load_fn, SITE_STATE_LOAD_HOLDS)(state, edx, slot) & 0xFF;
    if (ok && slot != 0 && slot != 0xB) settle_animals(state);
    return ok;
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
static const DWORD k_species_lookup = 0x00419290u;
static const DWORD k_held_name_back = 0x0041DA0Fu;
static const DWORD k_dead_join = 0x0042062Eu, k_alive_join = 0x00420649u;
static const DWORD k_customer_join = 0x0042427Du, k_customer_skip = 0x0042448Au;
static const DWORD k_thought_join = 0x0041356Cu, k_thought_skip = 0x00413622u;
static const DWORD k_egg_join = 0x0042135Fu, k_egg_done = 0x00421437u;
static const DWORD k_egg_confirm_yes = 0x004281B7u, k_egg_confirm_no = 0x004281D6u;
static const DWORD k_draw_ornaments = 0x0041D600u;
static const DWORD k_drop_join = 0x0041F06Du, k_drop_done = 0x0041F0F9u;
static const DWORD k_pick_join = 0x0041E579u;
static const DWORD k_draw_join = 0x00414C93u;
static const DWORD k_seahorse_ok = 0x00427C66u, k_seahorse_full = 0x00427E9Fu;
static const DWORD k_reset_clear = 0x004198F0u;
static const DWORD k_trash_join = 0x0041E80Eu;
static const DWORD k_ornament_drop_join = 0x0041F669u;

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
        cmp ecx, SPR_TOOL_EGGS
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
        mov [esp + 28], eax
        popad
        test eax, eax
        jnz handled
        mov eax, [ecx + 0x34]
        mov edx, [eax + 0x384]
        jmp k_pick_join
    handled:
        cmp eax, 2
        je held
        xor eax, eax
        ret 8
    held:
        mov al, 1                      /* picked up, as the stock fish pick returns */
        ret 8
    }
}

/* The stage-3 draw: eax frame, ebx x, [esp+0x24] y, esi the fish record. */
__declspec(naked) static void stub_draw_companion(void) {
    __asm {
        mov edx, [esp + 0x24]
        push eax                       /* frame */
        push edx                       /* y */
        push ebx                       /* x */
        lea ecx, [esp + 8]
        push ecx                       /* &frame */
        lea ecx, [esp + 8]
        push ecx                       /* &y */
        lea ecx, [esp + 8]
        push ecx                       /* &x */
        push esi                       /* the record */
        call companion_sheet
        add esp, 16
        push eax
        jmp k_draw_join
    }
}

/* 0x427E43, the stock Golden Seahorse placement: eax = now, the record at esp+0x3C. */
__declspec(naked) static void stub_seahorse_place(void) {
    __asm {
        pushad
        mov ecx, [esp + 28]            /* now (eax) */
        lea edx, [esp + 0x20 + 0x3C]   /* the record */
        push ecx
        push edx
        push dword ptr [esi + 0x10]    /* the state */
        call place_seahorse
        add esp, 12
        test eax, eax
        popad
        jz full
        jmp k_seahorse_ok
    full:
        jmp k_seahorse_full
    }
}

/* Replaces `call 0x4198F0` in the new-game reset: that clear, then the animals'. */
__declspec(naked) static void stub_new_game_clear(void) {
    __asm {
        call k_reset_clear
        pushad
        push esi
        call clear_animals
        add esp, 4
        popad
        ret
    }
}

/* 0x41E809, the trash after the answer: esi = impl, edi = tank, ebx = slot. */
__declspec(naked) static void stub_fish_trash(void) {
    __asm {
        pushad
        push ebx
        push edi
        push esi
        call fish_trashed
        add esp, 12
        popad
        mov ecx, [esi + 0x34]
        push ebx
        push edi
        jmp k_trash_join
    }
}

/* 0x41F660, the ornament drop (thiscall impl; x, y), ret 8. */
/* 0x41DA0A call 0x419290 (thiscall: kind, a, b; ret 0xC), in 0x41D980 (esi = the
   tank scene): the lookup as before, then held_name.  Back at 0x41DA0F. */
__declspec(naked) static void stub_held_name(void) {
    __asm {
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        call dword ptr [k_species_lookup]
        push eax
        push dword ptr [esp + 4]
        push esi
        call held_name
        add esp, 12
        add esp, 12
        jmp k_held_name_back
    }
}

__declspec(naked) static void stub_ornament_drop(void) {
    __asm {
        pushad
        push dword ptr [esp + 0x28]
        push dword ptr [esp + 0x28]
        push ecx
        call rock_trash
        add esp, 12
        mov [esp + 28], eax
        popad
        test eax, eax
        jnz handled
        push ebx
        push ebp
        mov ebp, [esp + 0x10]
        push esi
        mov esi, ecx
        jmp k_ornament_drop_join
    handled:
        ret 8
    }
}

/* ----------------------------------------------------------------- install */

#define CODE_ADDR(f) ((const void *)(UINT_PTR)(f))
#define TOTAL_SITES 22
static ftfp_site_write writes[TOTAL_SITES];
static int installed = 0;
static int host_ok = 0;

#define JMP(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE9, CODE_ADDR(TO))
#define CALL(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE8, CODE_ADDR(TO))
#define SLOT(W, NAME, TO) ftfp_site_imm32((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0, (unsigned int)(UINT_PTR)(TO))

/* The view builders' slot bound (`cmp eax, 21`, or 26 with "Bigger tanks"):
   31, so the animals in slots 26-30 swim too. */
static void view_limit(ftfp_site_write *w, unsigned int va, const unsigned char *stock, const unsigned char *bigger) {
    w->va = va;
    w->length = 3;
    w->expect = ftfp_site_holds(va, bigger, 3) ? bigger : stock;
    memcpy(w->bytes, w->expect, 3);
    w->bytes[2] = RECORDS;
}

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
    JMP(w++, SEAHORSE_PLACE, stub_seahorse_place);
    CALL(w++, NEW_GAME_CLEAR, stub_new_game_clear);
    JMP(w++, FISH_TRASH, stub_fish_trash);
    JMP(w++, ORNAMENT_DROP, stub_ornament_drop);
    JMP(w++, HELD_NAME, stub_held_name);
    SLOT(w++, STATE_LOAD, on_state_load);
    view_limit(w++, SITE_VIEW_BUILD_SLOTS_VA, SITE_VIEW_BUILD_SLOTS_EXPECT, SITE_VIEW_BUILD_SLOTS_EXPECT_26);
    view_limit(w++, SITE_VIEW_REFRESH_SLOTS_VA, SITE_VIEW_REFRESH_SLOTS_EXPECT, SITE_VIEW_REFRESH_SLOTS_EXPECT_26);
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

/* "<game>\Fish Tycoon Fix Patcher DLLs\DS Store Items.log", as DS Fish's log. */
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
    wcscat_s(path, 1024, L"Fish Tycoon Fix Patcher DLLs\\DS Store Items.log");
    if (installed) {
        len = append_text(line, len, exotic_any_slot
                          ? "DS Store: installed (all sites); Exotic Eggs use universal supply slots\r\n"
                          : "DS Store: installed (all sites)\r\n");
    } else if (!host_ok) {
        len = append_text(line, len, "DS Store: NOT installed; DS Exclusive Fish.dll is not the version this build expects\r\n");
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

/* With "Universal supply slots": its use trampoline sends items 0-7 to their
   own slot (eggs 5-7 to slot #4) and lets anything else through untouched,
   at 0x43F593 `jmp 0x43F5DE`.  Exotic Eggs (item 28) join the eggs there, so
   they work from any of slots 2-4.  Only written when that payload is in the
   executable; edx holds the item, the eggs branch is 0x43F5AC. */
static const unsigned char USE_GATE_EXPECT[5] = { 0xE9, 0x46, 0x00, 0x00, 0x00 };
static const DWORD k_use_eggs = 0x0043F5ACu, k_use_other = 0x0043F5DEu;
static ftfp_site_write use_gate[1];

__declspec(naked) static void stub_use_gate(void) {
    __asm {
        cmp edx, EXOTIC_ITEM
        jne other
        jmp k_use_eggs
    other:
        jmp k_use_other
    }
}

static void install_use_gate(void) {
    if (!universal_slots()) return;
    ftfp_site_branch(use_gate, 0x0043F593u, 5, USE_GATE_EXPECT, 0xE9, CODE_ADDR(stub_use_gate));
    exotic_any_slot = ftfp_install_sites(use_gate, 1);
}

/* Called once by DS Exclusive Fish.dll, after its own install, before WinMain. */
int __stdcall FtfpStoreStartup(const ftfp_store_host *host) {
    if (installed) return 1;
    __try {
        host_ok = name_sprites(host);
        if (host_ok && prepare() && ftfp_install_sites(writes, TOTAL_SITES)) {
            installed = 1;
            install_use_gate();
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
