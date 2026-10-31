/* DS Store Items -- the Nintendo DS store items in PC Fish Tycoon.

   WHAT.  An "Upgrades" button in the Supplies store opens a second page:
     * Puffer Fish, Sting Ray and Moray Eel: tank companions like the
       Golden Seahorse (they swim, can be dragged between tanks, never age,
       breed or get sold, and show the seahorse's health and food meters,
       full when bought and filled whenever a save loads);
     * the Moray Eel comes with its rock, a decoration moved like the shell
       or pagoda.  Drop the eel on its rock and it goes home (the DS in-rock
       animation, head peeking out); moving the rock then moves the eel.
       A click on its head lets it out again;
     * Exotic Fish Eggs: eggs for slot #4 that hatch only DS-exclusive
       bodies and fins (genes 23-29, even odds), as many as the other eggs;
     * Radioactive Growth Hormone ($10,000, 3 doses): a chemical for slot #3,
       used like the stock Growth Hormone, on every live fish in the tank you
       look at, any age (the stock one stops at 40, 0x421125): each pregnant one first gives birth through the stock birth rules,
       then each fish that was there before the births becomes an adult
       (age 20) if younger, gets full health (100), is cured of its sickness
       and is marked: sold, it pays its species' highest selling price
       (on_fish_sale);
     * Revival Potion ($10,000, 3 doses): a chemical for slot #3; each dose
       revives every dead fish in the tank you look at, at full health;
     * ClonaFish ($2,500, 3 doses): a chemical for slot #3; each dose adds an
       exact copy of every live fish in the tank you look at (it doubles the
       tank), through the game's own AddFish, until the tank is full;
     * the Auto-Feeder and the Auto-Healer ($10,000 each, bought once): every
       live fish in every tank kept fed, and cured at full health
       (auto_upgrades.h);
     * with their settings ("<name>.ini" beside this DLL): the Time Warp
       clock, and Add Money ($950 for +$1,000, any number of times).  With
       Free upgrades every item on this page costs $0.
   Effects, per tank, rescaled from the DS (docs/fish-tycoon-ds-store-items-design.md),
   for healthy fish (no disease, food above 5), each age step:
     * Golden Seahorse (its PC effects stay) and Sting Ray: 82% chance of +1 health;
     * Puffer Fish: +1 food, and a 60% chance of +1 more;
     * Moray Eel: a fish that would die survives at health 10, 1 time in 10.

   HOW.  "DS Store Items.dll" sits beside "DS Exclusive Fish.dll", which loads it
   after its own install and lends it sprite table entries 220-243.  Every
   write into the game is in store_sites.h -- all of them or none.

   STATE.  An animal is a seahorse-type fish record (body 22) whose fin marks
   the animal: 22 Golden Seahorse, 30 Puffer Fish, 31 Sting Ray, 32 Moray Eel
   -- so every rule the game has for the seahorse applies to them.  The
   animals (the Golden Seahorse too) have 5 records per tank of their own,
   here in the DLL, never one of the game's fish records (all 30 of those
   are the fish's with "Bigger tanks"); they are saved in "Tank Animals
   <slot>.dat" beside the save, and a save from an earlier build, which kept
   them in fish records 26-30, has them moved there once (see
   settle_animals).  The rock is one of the tank's ornament records; while
   the eel is home, the rock record's spare bytes keep its health and food.
   Owning an animal means it is in a tank: one of each, bought again after
   it is trashed.  With "Buy Multiple Golden Seahorses" patched in, the store
   sells them however many are already in the tanks, as it does the seahorse
   (each eel comes with its own rock). */
#include <windows.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "store_sites.h"
#include "../common/time_warp_popup.h"
#include "store_data.h"
#include "../common/max_sale_price.h"

#define STATE_GLOBAL 0x0045ABDCu
#define FISH_BASE 0x390
#define TANK_STRIDE 0x51EC
#define SLOT_STRIDE 0x288
#define RECORDS 31                  /* fish records per tank; the game uses 21 (30 with "Bigger tanks") */
#define OLD_ANIMAL_FIRST 26         /* earlier builds kept the animals in records 26-30 */
#define ANIMAL_TANKS 3              /* Tank One, Tank Two, the selling tank */
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
#define F_RADIOACTIVE 0x48          /* the Radioactive Growth Hormone's mark (see on_fish_sale) */
#define RADIOACTIVE_MARK 0x58414D52 /* "RMAX" */

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
#define SPR_ITEM_WARP (STORE_SPRITE_BASE + 13)
#define SPR_ITEM_MONEY (STORE_SPRITE_BASE + 14)
#define SPR_ITEM_RGH (STORE_SPRITE_BASE + 15)
#define SPR_TOOL_RGH (STORE_SPRITE_BASE + 16)        /* on the shelf, as the stock 0x7A */
#define SPR_DROPPER_RGH (STORE_SPRITE_BASE + 17)     /* the cursor while used, as the stock 0x7B */
#define SPR_ITEM_REVIVAL (STORE_SPRITE_BASE + 18)
#define SPR_TOOL_REVIVAL (STORE_SPRITE_BASE + 19)
#define SPR_DROPPER_REVIVAL (STORE_SPRITE_BASE + 20)
#define SPR_ITEM_CLONA (STORE_SPRITE_BASE + 21)
#define SPR_TOOL_CLONA (STORE_SPRITE_BASE + 22)
#define SPR_DROPPER_CLONA (STORE_SPRITE_BASE + 23)
#define SPR_ITEM_FEEDER (STORE_SPRITE_BASE + 24)
#define SPR_ITEM_HEALER (STORE_SPRITE_BASE + 25)
#define STORE_SPRITES 26

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
    { "ITEM_TIME_WARP.png", 0, 0 },             /* the Time Warp clock (the owner's icon) */
    { "ITEM_ADD_MONEY.png", 0, 0 },             /* Add Money: the owner's pile of gold coins */
    { "ITEM_RADIOACTIVE_GROWTHHORMONE.png", 0, 0 },   /* the stock Growth Hormone's art, green */
    { "TOOL_RADIOACTIVE_GROWTHHORMONE.png", 0, 0 },
    { "TOOL_dropper_RADIOACTIVE.png", 0, 0 },
    { "ITEM_REVIVAL_POTION.png", 0, 0 },        /* the owner's amber flask */
    { "TOOL_REVIVAL_POTION.png", 0, 0 },
    { "TOOL_dropper_REVIVAL.png", 0, 0 },
    { "ITEM_CLONAFISH.png", 0, 0 },             /* the owner's magenta bottle */
    { "TOOL_CLONAFISH.png", 0, 0 },
    { "TOOL_dropper_CLONAFISH.png", 0, 0 },
    { "ITEM_AUTO_FEEDER.png", 0, 0 },          /* the owner's green feeder */
    { "ITEM_AUTO_HEALER.png", 0, 0 },          /* the same machine in hot pink */
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

/* ---------------------------------------------------- the animals' records

   Each of Tank One, Tank Two and the selling tank has 5 animal records of
   its own, here in the DLL (saved in "Tank Animals <slot>.dat" beside the
   save), never in the game's 31 fish records, which are all the fish's.
   The game reaches a fish record as state + 0x390 + tank * 0x51EC + slot *
   0x288 (32-bit arithmetic) everywhere it follows a swimming fish's slot,
   with no other use of the slot (docs/fish-tycoon-tank-expansion.md 6).  So
   each animal gets the one slot number for which that sum lands on its
   record here: its swimming entry draws, moves, feeds, picks up, drops and
   trashes it with the game's own code, exactly as when it sat in slots
   26-30.  The number is below 2^29 and never -1 or a real slot 0-30. */
static unsigned char animal_area[ANIMAL_TANKS][ANIMAL_SLOTS * SLOT_STRIDE + 8];
static unsigned int animal_pad[ANIMAL_TANKS];

static char *tank_records(char *state, int tank) { return state + FISH_BASE + tank * TANK_STRIDE; }

/* The record must sit a multiple of 8 bytes from the tank's records (0x288 = 8 x 81). */
static char *animal(char *state, int tank, int k) {
    unsigned int pad = (unsigned int)((UINT_PTR)tank_records(state, tank) - (UINT_PTR)animal_area[tank]) & 7u;
    if (pad != animal_pad[tank]) {
        memmove(animal_area[tank] + pad, animal_area[tank] + animal_pad[tank], ANIMAL_SLOTS * SLOT_STRIDE);
        animal_pad[tank] = pad;
    }
    return (char *)animal_area[tank] + pad + k * SLOT_STRIDE;
}

/* slot * 0x288 == record - tank records (mod 2^32): slot * 81 == distance / 8 (mod 2^29). */
static int animal_slot(char *state, int tank, int k) {
    unsigned int d = (unsigned int)((UINT_PTR)animal(state, tank, k) - (UINT_PTR)tank_records(state, tank));
    unsigned int inverse = 1;
    int i;
    for (i = 0; i < 5; ++i) inverse *= 2u - 81u * inverse;          /* 81 * inverse == 1 (mod 2^32) */
    return (int)(((d >> 3) * inverse) & 0x1FFFFFFFu);
}

/* The animal (0-4) a swimming slot number stands for, or -1. */
static int animal_index(char *state, int tank, int slot) {
    int k;
    if (tank < 0 || tank >= ANIMAL_TANKS || (slot >= 0 && slot < RECORDS)) return -1;
    for (k = 0; k < ANIMAL_SLOTS; ++k) {
        if (animal_slot(state, tank, k) == slot) return k;
    }
    return -1;
}

/* The record a (tank, slot) of a swimming entry addresses: a fish's, an animal's, or NULL. */
static char *record_at(char *state, int tank, int slot) {
    int k;
    if (tank < 0 || tank > 3) return NULL;
    if (slot >= 0 && slot < RECORDS) return fish(state, tank, slot);
    k = animal_index(state, tank, slot);
    return k >= 0 ? animal(state, tank, k) : NULL;
}

static int is_kind(char *f, int fin) {
    return f != NULL && is_animal(f) && *I(f, F_FIN) == fin;
}

static int count_in_tank(char *state, int tank, int fin) {
    int k, n = 0;
    if (tank < 0 || tank >= ANIMAL_TANKS) return 0;
    for (k = 0; k < ANIMAL_SLOTS; ++k) {
        if (is_kind(animal(state, tank, k), fin)) ++n;
    }
    return n;
}

static int free_animal_slot(char *state, int tank) {
    int k;
    for (k = 0; k < ANIMAL_SLOTS; ++k) {
        if (!is_animal(animal(state, tank, k))) return k;
    }
    return -1;
}

/* Copies an animal's record into a free animal record of the tank: its index, or -1. */
static int place_animal(char *state, int tank, char *rec) {
    int k = tank >= 0 && tank < ANIMAL_TANKS ? free_animal_slot(state, tank) : -1;
    if (k < 0) return -1;
    *I(rec, F_MARK) = ANIMAL_MARK;
    *I(rec, F_KIND) = *I(rec, F_FIN);
    memcpy(animal(state, tank, k), rec, SLOT_STRIDE);
    return k;
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

/* "Extra Tanks.dll" (the "3 extra tanks" setting) holds the blocks of the tanks
   that are not in a stock place right now (Tanks 4-6, or Tank 1 while one of
   them is on screen), each with its 5 animal records after the block:
   FtfpExtraTanksHeld(e) for e = 0-2, NULL when it is not loaded.  Every tank's
   animals are therefore either in a stock place here or in one of those. */
#define HELD_TANKS 3
typedef unsigned char *(__stdcall *held_fn)(int e);
static unsigned char *held_block(int e) {
    HMODULE tanks = GetModuleHandleW(L"Extra Tanks.dll");
    held_fn fn = tanks != NULL ? (held_fn)GetProcAddress(tanks, "FtfpExtraTanksHeld") : NULL;
    return fn != NULL ? fn(e) : NULL;
}

static int held_owns(int fin) {
    int e, k;
    for (e = 0; e < HELD_TANKS; ++e) {
        unsigned char *b = held_block(e);
        if (b == NULL) return 0;
        for (k = 0; k < ANIMAL_SLOTS; ++k) {
            if (is_kind((char *)b + TANK_STRIDE + k * SLOT_STRIDE, fin)) return 1;
        }
        if (fin == FIN_EEL) {
            for (k = 0; k < ORN_SLOTS; ++k) {
                if (is_home_rock(b + (ORN_BASE - FISH_BASE) + k * ORN_STRIDE)) return 1;
            }
        }
    }
    return 0;
}

static int owned(char *state, int fin) {
    int t;
    for (t = 0; t <= 3; ++t) {
        if (count_in_tank(state, t, fin)) return 1;
    }
    if (held_owns(fin)) return 1;
    return fin == FIN_EEL && (eel_in_tank(state, 0) || eel_in_tank(state, 1) || eel_in_tank(state, 2));
}

/* "Buy Multiple Golden Seahorses" (fish manifest patch
   redirect_golden_seahorse_store_blocker) puts this jump at 0x4282B2. */
static const unsigned char REPURCHASE_JUMP[10] = { 0xE9, 0x49, 0x75, 0x01, 0x00, 0x90, 0x90, 0x90, 0x90, 0x90 };

#define FIN_WARP (-1)                       /* the Time Warp item: not an animal */
#define FIN_MONEY (-2)                      /* the Add Money item: not an animal */
#define FIN_TANK (-6)                       /* the Extra Tank item (the "3 extra tanks" setting); -3..-5 are the potions */
#define FIN_FEEDER (-7)                     /* the Auto-Feeder (auto_upgrades.h) */
#define FIN_HEALER (-8)                     /* the Auto-Healer */
#define FIN_SLOTS (-9)                      /* Extra Supply Slots (the "Extra supply slots" setting) */
static int auto_sold_out(int fin);
static const char *auto_owned_line(int item);

/* "Extra Tanks.dll" (the "3 extra tanks" setting: Tank 4, 5 and 6) sells its tanks here, in
   order: how many are bought (0-3, -1 when it is not loaded or no game is
   open), and one more bought (the new count, or -1). */
typedef int (__stdcall *tanks_fn)(void);
static int tanks_call(const char *name) {
    HMODULE tanks = GetModuleHandleW(L"Extra Tanks.dll");
    tanks_fn fn = tanks != NULL ? (tanks_fn)GetProcAddress(tanks, name) : NULL;
    return fn != NULL ? fn() : -1;
}
#define EXTRA_TANKS 3

/* "Extra Supply Slots.dll" (the "Extra supply slots" setting: seven more supply slots)
   sells them here, all seven at once: bought (1), not yet (0), or -1 when it is not loaded
   or no game is open; and the purchase (1, or -1). */
static int slots_call(const char *name) {
    HMODULE slots = GetModuleHandleW(L"Extra Supply Slots.dll");
    tanks_fn fn = slots != NULL ? (tanks_fn)GetProcAddress(slots, name) : NULL;
    return fn != NULL ? fn() : -1;
}

/* Its picture for the Upgrades screen (an image of its own, not one of the lent sprites). */
typedef void *(__stdcall *slots_image_fn)(void);
static void *slots_image(void) {
    HMODULE slots = GetModuleHandleW(L"Extra Supply Slots.dll");
    slots_image_fn fn = slots != NULL ? (slots_image_fn)GetProcAddress(slots, "FtfpSupplySlotsImage") : NULL;
    return fn != NULL ? fn() : NULL;
}

/* A supply bought here goes where the stock store would put it -- and with the extra
   slots bought, the extra slot it should go to is lent to a stock slot 2-4 for the
   purchase (FtfpSupplySlotsLend: a stack of the same item, else a free slot, over all
   eleven slots, as ftfp_supply_slots.c lend describes) and put back after. */
typedef int (__stdcall *slots_lend_fn)(int item);
typedef void (__stdcall *slots_return_fn)(void);
static void slots_lend(int item) {
    HMODULE slots = GetModuleHandleW(L"Extra Supply Slots.dll");
    slots_lend_fn fn = slots != NULL ? (slots_lend_fn)GetProcAddress(slots, "FtfpSupplySlotsLend") : NULL;
    if (fn != NULL) fn(item);
}
static void slots_return(void) {
    HMODULE slots = GetModuleHandleW(L"Extra Supply Slots.dll");
    slots_return_fn fn = slots != NULL ? (slots_return_fn)GetProcAddress(slots, "FtfpSupplySlotsReturn") : NULL;
    if (fn != NULL) fn();
}

static int sold_out(char *state, int fin) {
    static int repurchase = -1;
    if (fin == FIN_TANK) return tanks_call("FtfpExtraTanksOwned") >= EXTRA_TANKS;
    if (fin == FIN_SLOTS) return slots_call("FtfpSupplySlotsOwned") >= 1;
    if (fin == FIN_FEEDER || fin == FIN_HEALER) return auto_sold_out(fin);
    if (fin < 0) return 0;                  /* Time Warp, Add Money, the potions: never sold out */
    if (repurchase < 0) repurchase = ftfp_site_holds(0x004282B2u, REPURCHASE_JUMP, sizeof REPURCHASE_JUMP);
    return fin != 0 && !repurchase && owned(state, fin);
}

static int clamp100(int v) { return v < 0 ? 0 : v > 100 ? 100 : v; }

/* A full health or food meter: the game caps both at 100 (0x41E0FE, 0x4121CB,
   0x4205E9, 0x42060F) and draws a full bar at 100 (0x41BF10). */
#define FULL_METER 100

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
    memcpy(animal(state, to, dest), record_at(state, tank, slot), SLOT_STRIDE);
    REMOVE_FISH(state, NULL, tank, slot);
    VIEW_MOVE(view, NULL, entry, -1, 1, -1);
}

/* A fish dropped in the tank: an animal on a tank button moves there, and
   the eel on its rock goes home.  1 = handled. */
static int __cdecl eel_drop(char *impl, int tank, int slot, int entry, int x, int y) {
    char *state = (char *)P(impl, 0x34);
    char *f;
    int k, to;
    if (state == NULL || tank < 0 || tank > 2 || animal_index(state, tank, slot) < 0) return 0;
    f = record_at(state, tank, slot);
    if (is_animal(f) && (to = button_tank(impl, x, y)) >= 0) {
        move_animal(impl, state, tank, slot, entry, to);
        return 1;
    }
    if (tank != *I(state, S_CURRENT_TANK) || !is_kind(f, FIN_EEL)) return 0;
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
                       o[O_HOME_FLAG] == HOME_FLAG && o[O_HOME_HEALTH] > 0 ? o[O_HOME_HEALTH] : FULL_METER,
                       o[O_HOME_FLAG] == HOME_FLAG ? o[O_HOME_FOOD] : FULL_METER);
        slot = place_animal(state, tank, rec);
        if (slot < 0) {
            HINT(P(impl, 0x44), NULL, 6);          /* "The tank is full!" */
            return 1;
        }
        slot = animal_slot(state, tank, slot);     /* the number its swimming entry carries */
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

/* The tanks "Extra Tanks.dll" holds (Tanks 4-6, or Tank 1 while one of them is on
   screen): an empty rock among their ornaments, or a swimming eel among their
   animals, so an eel and its rock go together wherever the two are. */
static unsigned char *held_ornament(unsigned char *b, int k) { return b + (ORN_BASE - FISH_BASE) + k * ORN_STRIDE; }
static char *held_animal(unsigned char *b, int k) { return (char *)b + TANK_STRIDE + k * SLOT_STRIDE; }

static int remove_held_rock(void) {
    int e, k;
    for (e = 0; e < HELD_TANKS; ++e) {
        unsigned char *b = held_block(e);
        if (b == NULL) return 0;
        for (k = 0; k < ORN_SLOTS; ++k) {
            unsigned char *o = held_ornament(b, k);
            if (o[0] != 0 && *I(o, O_SPRITE) == SPR_ROCK) {
                memset(o, 0, ORN_STRIDE);
                return 1;
            }
        }
    }
    return 0;
}

/* REMOVE_FISH clears these fields of a record at state + 0x390 + tank * 0x51EC +
   slot * 0x288; a held record is cleared the same way, as the record of slot 0
   of tank 0 of a state 0x390 bytes before it. */
static int remove_held_eel(void) {
    int e, k;
    for (e = 0; e < HELD_TANKS; ++e) {
        unsigned char *b = held_block(e);
        if (b == NULL) return 0;
        for (k = 0; k < ANIMAL_SLOTS; ++k) {
            char *f = held_animal(b, k);
            if (!is_kind(f, FIN_EEL)) continue;
            REMOVE_FISH(f - FISH_BASE, NULL, 0, 0);
            return 1;
        }
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
    return remove_held_rock();                                 /* then Tanks 4-6 */
}

/* 0x41E809, the trash after its "throw away?" answer: an eel takes a rock with it. */
static void __cdecl fish_trashed(char *impl, int tank, int slot) {
    char *state = (char *)P(impl, 0x34);
    if (state != NULL && tank >= 0 && tank <= 3 && slot >= 0 && slot < RECORDS
        && *I(fish(state, tank, slot), F_RADIOACTIVE) == RADIOACTIVE_MARK)
        *I(fish(state, tank, slot), F_RADIOACTIVE) = 0;    /* a treated fish thrown away: no mark left */
    if (state == NULL || tank < 0 || tank > 2) return;
    if (is_kind(record_at(state, tank, slot), FIN_EEL)) remove_out_rock(state, tank);
}

static int confirm_in(void *parent, int string_id);

/* An ornament dropped (the stock game only moves them): the eel's rock on the
   trash can is thrown away, with its eel (inside it, or the one swimming in
   the same tank, else another, in Tanks 4-6 last).  1 = handled. */
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
                for (s = 0; s < ANIMAL_SLOTS && !done; ++s) {
                    if (!is_kind(animal(state, t, s), FIN_EEL)) continue;
                    s = animal_slot(state, t, s);       /* as its swimming entry knows it */
                    if (t == tank) {
                        int entry = view_entry(impl, t, s);
                        if (entry >= 0) VIEW_MOVE(P(impl, 0x3C), NULL, entry, -1, 0, s);
                    }
                    REMOVE_FISH(state, NULL, t, s);
                    done = 1;
                }
            }
        }
        if (!done) remove_held_eel();                       /* then Tanks 4-6 */
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

/* ---------------------------------------------- Radioactive Growth Hormone */

/* A chemical: item 29 in slot #3 (state + 0x2F0, as the stock chemicals 2-4),
   shelf picture SPR_TOOL_RGH, cursor SPR_DROPPER_RGH, 3 doses a purchase.
   The stock chemical use (0x420E3A: the splash, the sound, then the switch
   on the item at 0x420E72) runs as for any chemical; for item 29 the switch
   calls rgh_dose and goes on into the stock Growth Hormone's own sparkle
   loop (0x42119A) and the stock tail (0x421302), which spends one dose and
   empties the slot at 0. */
#define RGH_ITEM 29
#define RGH_DOSES 3

/* The owner, 2026-10-31 ("Always pays the max"): a fish given a dose sells for the highest price
   the game would ever allow for its species.  The mark is the fish record's +0x48, a dword the
   game never uses: the stock code touches it in exactly two places, the birth (0x41FA30, a new
   fish's record starts at 0 there, at 0x41FAA7) and the field copy 0x41E850 (+0x48 copied as
   is), and no instruction addresses +0x48 of a fish record in the game state (state + 0x390 +
   tank * 0x51EC + slot * 0x288 + 0x48: no operand, any tank or slot); every other [reg + 0x48]
   operand is on another object (tests/test_radioactive_max_price.py pins the list).  So the
   mark goes wherever the record goes, with nothing else to change: AddFish copies the whole
   0x288 bytes (0x419C99: moves between tanks, the isolation tank, ClonaFish's clones), Extra
   Tanks swaps whole blocks (Tanks 4-6, and each one lent the Sale Tank's place to sell), and
   the save is the state (Extra Tanks' sidecar the blocks).  RADIOACTIVE_MARK, never a plain
   non-zero, so no stray value could ever count.  Cleared when the fish is sold (on_fish_sale),
   dies (stub_death), is thrown away (fish_trashed) or revived (revival_dose).  F_RADIOACTIVE and
   RADIOACTIVE_MARK are defined with the other record fields, at the top. */
#define ADULT_AGE 20                /* adults are 20 and up: 0x4200AC, 0x420498 (sickness), 0x42426F (sales) */
#define S_CURED 0x34                /* "Fish Cured", which the stock medicine cure adds to (0x420D2B) */
/* The end of the stock Growth Hormone's fish loop, `cmp ebx, 0x3528` at 0x42118E: 21 records, or 26 with
   "Bigger tanks", which rewrites this immediate. Read here, so the dose reaches the same records. */
#define GH_LOOP_END (*(const int *)(UINT_PTR)0x00421190u)
/* The fish update's own bounds (0x41FE70): slots `cmp ecx, 0x15` at 0x4206B1 (26 with "Bigger
   tanks", which rewrites the byte at 0x4206B3) and tanks `cmp eax, 3` at 0x4206C5 (byte
   0x4206C7).  Read, never assumed, so the potions reach every slot and tank the game updates. */
#define UPDATE_SLOTS (*(const signed char *)(UINT_PTR)0x004206B3u)
#define UPDATE_LAST_TANK (*(const signed char *)(UINT_PTR)0x004206C7u)
/* The one tank where the update never lets a fish give birth (`cmp [esp+0x10], 3` at 0x42013D). */
#define NO_BIRTH_TANK (*(const signed char *)(UINT_PTR)0x00420141u)

static int last_tank(void) { return UPDATE_LAST_TANK; }

/* The fish records the update reaches in a tank (21, or 30 with "Bigger tanks"): never fewer
   than 1, never past record 29 (record 30 is never a fish's; the animals have records of their
   own, kept in "Tank Animals <slot>.dat"). */
static int fish_slots(void) {
    int n = UPDATE_SLOTS;
    return n < 1 ? 1 : n > RECORDS - 1 ? RECORDS - 1 : n;
}

/* ---- Pregnancy and birth (vanilla 0x420113-0x4203DD, run once per fish per update):
   +0x10 is the due age (0 = not pregnant; set at mating), +0x14/+0x18 the father's body and
   fin, +0x1C-+0x38 the grandparents.  When the due age is below the age and the tank is not
   tank 3 (0x42013D), the update gives birth:
     * with a Magic Fish of kind 5 in the tank (0x41DE90(5, tank)): on Random(100) <= 15 the
       father's genes mutate (+0x14 or +0x18 by one, 0x42015E-0x420210), clamped to 0-20;
     * NewBaby 0x41FA30 (one AddFish 0x419C50: a full tank simply gets no baby), then one more
       with a Magic Fish of kind 0 (fertility, 0x4202D9), one more with the Plant of Fertility
       (state + 0x1A4, 0x420356); each baby's age is age - due age;
     * the due age is cleared (0x4203D2).
   stock_birth is that code, call for call, in the same order, so the same random rolls give
   the same litter. */
#define F_DUE F_PREGNANT
#define F_MATE_BODY 0x14
#define F_MATE_FIN 0x18
#define S_PLANT_OF_FERTILITY 0x1A4
#define MAGIC_IN_TANK GAME(this2_fn, 0x0041DE90u)       /* (kind, tank) -> al */

static int magic_in_tank(char *impl, int kind, int tank) {
    return MAGIC_IN_TANK(impl, NULL, kind, tank) & 0xFF;
}

static void stock_baby(char *impl, char *f, int age, int tank) {
    NEW_BABY(impl, NULL, *I(f, F_BODY), *I(f, F_FIN), *I(f, F_MATE_BODY), *I(f, F_MATE_FIN),
             *I(f, 0x1C), *I(f, 0x24), *I(f, 0x20), *I(f, 0x28), *I(f, 0x2C), *I(f, 0x30), *I(f, 0x34),
             *I(f, 0x38), age, tank);
}

static void stock_birth(char *impl, char *f, int tank, int baby_age) {
    char *state = (char *)P(impl, 0x34);
    if (magic_in_tank(impl, 5, tank) && RANDOM(100) <= 15) {
        int *mate_body = I(f, F_MATE_BODY), *mate_fin = I(f, F_MATE_FIN);
        if (RANDOM(100) <= 49) {
            if (*mate_body == 20) --*mate_body;
            else if (RANDOM(100) <= 49 || *mate_body == 0) ++*mate_body;
            else --*mate_body;
        } else {
            /* The stock code tests the father's body here but changes his fin (0x4201CC). */
            if (*mate_body == 20) --*mate_fin;
            else if (RANDOM(100) <= 49 || *mate_body == 0) ++*mate_fin;
            else --*mate_fin;
        }
        if (*mate_body > 20) *mate_body = 20; else if (*mate_body < 0) *mate_body = 0;
        if (*mate_fin > 20) *mate_fin = 20; else if (*mate_fin < 0) *mate_fin = 0;
    }
    stock_baby(impl, f, baby_age, tank);
    if (magic_in_tank(impl, 0, tank)) stock_baby(impl, f, baby_age, tank);
    if (*I(state, S_PLANT_OF_FERTILITY) != 0) stock_baby(impl, f, baby_age, tank);
    *I(f, F_DUE) = 0;
}

/* One dose on the tank being looked at (0x384), on every fish of it, any age (the owner,
   2026-10-30; the stock Growth Hormone, 0x421100-0x421194, stops at age 40): live (+0x00),
   health not 0 (+0x3C), over the stock loop's records.  First every pregnant one of them (+0x10 not 0) gives birth at once, through stock_birth
   (the owner, 2026-10-30), with the babies aged 1, as a birth on the due step is (age - due
   age); tank 3 never gives birth, as stock.  Then each fish reached before the births (the
   newborns stay babies, see reached_before_births):
     * younger than 20: age 20, written as the stock dose writes an age (0x42114F), and
       last-processed age 19 on every difficulty (the stock dose does this only off Hard,
       0x421157; the owner, 2026-10-30: the fish stay healthy on Hard too), so the next
       update runs one step's checks, not one for every skipped step;
     * health 100, the game's maximum (0x41E0FE, 0x42127E);
     * sickness (+0x40: 1 fungus, 2 ick, set at 0x41E120) cleared as the medicine clears it
       (0x420D1D / 0x420D57: +0x40 = 0, and one more Fish Cured).
   Then the stock dose's next fish update, 7 seconds on (0x42117D). The store animals are
   never reached: they are past the stock loop's end (slots 26-30), and a marked animal record
   is skipped wherever the loop end is moved. */
static int gh_reaches(char *f) {
    return *I(f, F_LIVE) != 0 && *I(f, F_HEALTH) != 0 && !is_animal(f);
}

/* The owner, 2026-10-31 ("babies stay babies"): the newborns of a dose are left exactly as the
   stock birth makes them (aged 1).  The game shows a fish's species name only from age 20
   (0x41D9ED: under 20 the name is string 6), so raising them to 20 showed baby fish's names.
   The fish the dose reaches are therefore noted before the births, by record: a newborn goes
   only into a record that was empty then (AddFish takes a record whose +0x00 is 0), so it is
   never among them, whatever record it reuses; the age-up, healing and cure below are for
   those fish only.  A later dose reaches the babies like any other young fish. */
static unsigned char reached_before_births[RECORDS];

static void __cdecl rgh_dose(char *impl) {
    char *state = (char *)P(impl, 0x34);
    int tank, end = GH_LOOP_END, off, born = 0;
    if (state == NULL) return;
    tank = *I(state, S_CURRENT_TANK);
    if (tank < 0 || tank > last_tank()) return;
    if (end > RECORDS * SLOT_STRIDE) end = RECORDS * SLOT_STRIDE;
    for (off = 0; off < end; off += SLOT_STRIDE)
        reached_before_births[off / SLOT_STRIDE] = (unsigned char)gh_reaches(state + FISH_BASE + tank * TANK_STRIDE + off);
    for (off = 0; off < end && tank != NO_BIRTH_TANK; off += SLOT_STRIDE) {
        char *f = state + FISH_BASE + tank * TANK_STRIDE + off;
        if (!gh_reaches(f) || *I(f, F_DUE) == 0) continue;
        stock_birth(impl, f, tank, 1);
        born = 1;
    }
    if (born && P(impl, 0x3C) != NULL)                       /* the newborns swim, as after a hatch */
        VIEW_SYNC(P(impl, 0x3C), NULL, (int)(UINT_PTR)fish(state, tank, 0));
    for (off = 0; off < end; off += SLOT_STRIDE) {
        char *f = state + FISH_BASE + tank * TANK_STRIDE + off;
        if (!reached_before_births[off / SLOT_STRIDE] || !gh_reaches(f)) continue;
        if (*I(f, F_AGE) < ADULT_AGE) {
            *I(f, F_AGE) = ADULT_AGE;
            *I(f, F_LAST_AGE) = ADULT_AGE - 1;
        }
        *I(f, F_HEALTH) = FULL_METER;
        if (*I(f, F_DISEASE) != 0) {
            *I(f, F_DISEASE) = 0;
            ++*I(state, S_CURED);
        }
        *I(f, F_RADIOACTIVE) = RADIOACTIVE_MARK;          /* sells for the highest price (on_fish_sale) */
        *I(impl, 0x30) = CLOCK_NOW() + 7;
    }
}

/* ------------------------------------------- treated fish: the highest price */

/* A species' entry in the game's table (state + 0x14B40 + (body * 31 + fin) * 40: +0x20 the
   asking price, +0x24 the base price), or, for a DS body, DS Exclusive Fish's own row
   (FtfpDsFishEntry), where the sale's price reads (0x424034, 0x42405E, 0x423701) are sent. */
#define SPECIES_TABLE 0x14B40
#define SPECIES_ROW 31
#define SPECIES_ENTRY 40
#define E_PRICE 0x20
typedef unsigned char *(__stdcall *ds_entry_fn)(char *state, int body, int fin);

static unsigned char *species_entry(char *state, int body, int fin) {
    if (body >= 0 && body <= MS_FISH_PC_LAST && fin >= 0 && fin < SPECIES_ROW)
        return (unsigned char *)state + SPECIES_TABLE + (body * SPECIES_ROW + fin) * SPECIES_ENTRY;
    if (ms_fish_is_ds(body)) {
        HMODULE ds = GetModuleHandleW(L"DS Exclusive Fish.dll");
        ds_entry_fn entry = ds != NULL ? (ds_entry_fn)GetProcAddress(ds, "FtfpDsFishEntry") : NULL;
        return entry != NULL ? entry(state, body, fin) : NULL;
    }
    return NULL;
}

/* The price a sold fish pays: its asking price, or for a treated fish its species' highest selling
   price (the Breeding Guide's "Highest selling" with Max effects: 2B - 1, B after Advertising
   level 3; max_sale_price.h), never less than the asking price. */
static int __cdecl sale_price(const char *f, int asking) {
    int best;
    if (f == NULL || *(const int *)(f + F_RADIOACTIVE) != RADIOACTIVE_MARK) return asking;
    best = ms_fish_max_price(*(const int *)(f + F_BODY), *(const int *)(f + F_FIN));
    return best > asking ? best : asking;
}

/* 0x4244D4, the sale roll's `call 0x424010` (thiscall scene; slot; ret 4), its only call: the sale
   of Sale Tank slot `slot` (Tanks 4-6 sell there too, each lent the Sale Tank's place by Extra
   Tanks for its roll).  The roll that chose the fish is over, so its chance and timing are the
   asking price's, as stock.  For a treated fish the species' asking price is the highest selling
   price for the length of this one sale, so everything the sale pays and records uses it: the
   money (state + 0x38C), the money earned (state + 0x20) and the sold fish's price in the selling
   scene (0x4236D0, scene + 0x28); then the asking price is put back and the mark cleared. */
#define SCENE_STATE 0x70
#define SALE_TANK 2
static const DWORD k_sale = 0x00424010u;

static void __fastcall on_fish_sale(char *scene, void *edx, int slot) {
    char *state = (char *)P(scene, SCENE_STATE), *f = NULL;
    unsigned char *entry = NULL;
    int asking = 0, paid;
    if (state != NULL && slot >= 0 && slot < RECORDS) {
        f = fish(state, SALE_TANK, slot);
        if (*I(f, F_RADIOACTIVE) == RADIOACTIVE_MARK)
            entry = species_entry(state, *I(f, F_BODY), *I(f, F_FIN));
    }
    if (entry != NULL) {
        asking = *I(entry, E_PRICE);
        paid = sale_price(f, asking);
        if (paid == asking) entry = NULL;
        else *I(entry, E_PRICE) = paid;
    }
    __try {
        GAME(this1_fn, k_sale)(scene, edx, slot);
    } __finally {
        if (entry != NULL) *I(entry, E_PRICE) = asking;
        if (f != NULL && *I(f, F_RADIOACTIVE) == RADIOACTIVE_MARK) *I(f, F_RADIOACTIVE) = 0;
    }
}

/* ------------------------------------------------------- Revival Potion */

/* Item 30, used like the hormone (slot #3, the stock splash, sparkle and tail).
   How the vanilla game stores a dead fish: nothing but health (+0x3C) at 0.
     * The death test (0x420622) only sets the age to the step it died on (0x420634),
       so the step loop stops there; the record stays live (+0x00 is not cleared),
       and it stays in the tank until it is thrown away: no timer removes it.
     * Every update skips it (0x41FEC3: health <= 0), so its clock (+0x00, the time
       of its last update, set at 0x41FFCA), its banked seconds (+0x04), age, food
       and sickness stay as they were when it died.
     * The tank view draws it dead (0x4146BF / 0x4146F6 / 0x414778: the dead teen
       or adult picture), lets it sink (0x411D5F) and never swims it (0x414337),
       all from that same health test.
   A dose, on the tank being looked at, for every record the update reaches
   (UPDATE_SLOTS, UPDATE_LAST_TANK) that is live with health 0 and not a store
   animal: health 100, and the clock set to now (STATE_NOW 0x4032C0, as the update
   sets it), so the next update counts from now and does not play the time it lay
   dead as time away.  Age, food, sickness, pregnancy and banked seconds stay. */
#define REVIVAL_ITEM 30
#define CLONA_ITEM 31

static void __cdecl revival_dose(char *impl) {
    char *state = (char *)P(impl, 0x34);
    int tank, s, slots = fish_slots(), now;
    if (state == NULL) return;
    tank = *I(state, S_CURRENT_TANK);
    if (tank < 0 || tank > last_tank()) return;
    now = STATE_NOW(state, NULL);
    for (s = 0; s < slots; ++s) {
        char *f = fish(state, tank, s);
        if (*I(f, F_LIVE) == 0 || *I(f, F_HEALTH) > 0 || is_animal(f)) continue;
        *I(f, F_HEALTH) = FULL_METER;
        if (*I(f, F_RADIOACTIVE) == RADIOACTIVE_MARK) *I(f, F_RADIOACTIVE) = 0;   /* death ended the treatment */
        if (now != 0) *I(f, F_LIVE) = now;
    }
}

/* ------------------------------------------------------------ ClonaFish */

/* Item 31, used like the hormone.  Every live fish (+0x00 set, health above 0)
   is cloned once a dose, any species, however many of it there are (the owner,
   2026-10-31: "it should double all fish"; the first build cloned only fish no
   other shared a species with).  Store animals and seahorse-type records are
   never cloned.  The fish in the tank before the dose are copied first, so a
   clone this dose makes is not cloned again until the next dose; then each
   one, in slot order, is copied whole (all 0x288 bytes) and handed to the
   game's own AddFish (0x419C50), which puts it in the first free record under
   the tank's limit (0x419C72) or answers -1 when the tank is full: then the
   dose stops, and the rest get no clone.  A record holds no slot number or id
   of its own (AddFish is a plain copy), so the clone is the original exactly.
   New fish swim at once (the hatch's view call); if the tank was full before
   the first clone, the game's "The tank is full!" hint shows. */
#define S_HINTS 0x44                 /* the tank scene's hint object (string 6: "The tank is full!") */
static char clone_buffer[RECORDS][SLOT_STRIDE];

static int counts_for_cloning(char *f) {
    return *I(f, F_LIVE) != 0 && *I(f, F_HEALTH) > 0 && !is_animal(f) && *I(f, F_BODY) != BODY_SEAHORSE;
}

static void __cdecl clona_dose(char *impl) {
    char *state = (char *)P(impl, 0x34);
    int tank, s, slots = fish_slots(), unique = 0, added = 0, k;
    if (state == NULL) return;
    tank = *I(state, S_CURRENT_TANK);
    if (tank < 0 || tank > last_tank()) return;
    for (s = 0; s < slots; ++s) {                       /* the fish before the dose: copied first */
        char *f = fish(state, tank, s);
        if (counts_for_cloning(f)) memcpy(clone_buffer[unique++], f, SLOT_STRIDE);
    }
    for (k = 0; k < unique; ++k) {
        if (ADD_FISH(state, NULL, tank, (int)(UINT_PTR)clone_buffer[k]) < 0) break;
        ++added;
    }
    if (added > 0 && P(impl, 0x3C) != NULL) {
        VIEW_SYNC(P(impl, 0x3C), NULL, (int)(UINT_PTR)fish(state, tank, 0));
    } else if (unique > 0 && added == 0 && P(impl, S_HINTS) != NULL) {
        HINT(P(impl, S_HINTS), NULL, 6);
    }
}

/* The chemical switch's new items: 1 = handled (then the stock sparkle and tail). */
static int __cdecl new_chemical(char *impl, int item) {
    switch (item) {
    case RGH_ITEM: rgh_dose(impl); return 1;
    case REVIVAL_ITEM: revival_dose(impl); return 1;
    case CLONA_ITEM: clona_dose(impl); return 1;
    default: return 0;
    }
}

/* ---------------------------------------------------- the store supplies in the trash */

/* The stock game never throws a supply away: a supply let go outside the tank
   (0x420B70 tests the tank at impl+0xA8..+0xB4 first) gets a hint and goes
   back to its slot (0x42165C).  This store's own supplies -- Exotic Fish Eggs,
   the Radioactive Growth Hormone, the Revival Potion and ClonaFish -- let go
   on the trash can (impl+0x88..+0x94, the hit area the fish trash tests at
   0x41F31E) are thrown away instead: the slot is emptied as the stock tail
   empties a used-up one (0x420D9B: item, present, count, icon and cursor
   0), with every dose or hatch it still held, nothing is held any more
   (impl+0x1C = 0x63), and the fish trash's sound (4) plays.  The stock game
   asks only before a live fish goes ("Delete this fish?"), so nothing is
   asked.  Food (slot #1) and the stock supplies are never touched: they go
   back to their slot as stock.  1 = thrown away. */
#define HELD_SUPPLY 0x1C
#define NO_SUPPLY 0x63

static int is_store_supply(int item) {
    return item == EXOTIC_ITEM || item == RGH_ITEM || item == REVIVAL_ITEM || item == CLONA_ITEM;
}

static int __cdecl supply_trash(char *impl, int x, int y) {
    char *state = (char *)P(impl, 0x34), *r;
    int k = *I(impl, HELD_SUPPLY);
    if (state == NULL || k < 1 || k > 3) return 0;
    r = SLOT_RECORD(state, k);
    if (*I(r, SR_ICON) == 0 || !is_store_supply(*I(r, SR_ITEM))) return 0;
    if (inside(x, y, *I(impl, 0xA8), *I(impl, 0xAC), *I(impl, 0xB0), *I(impl, 0xB4))) return 0;
    if (!inside(x, y, *I(impl, 0x88), *I(impl, 0x8C), *I(impl, 0x90), *I(impl, 0x94))) return 0;
    *I(r, SR_ITEM) = 0;
    *I(r, SR_PRESENT) = 0;
    *I(r, SR_COUNT) = 0;
    *I(r, SR_ICON) = 0;
    *I(r, SR_CURSOR) = 0;
    *I(impl, HELD_SUPPLY) = NO_SUPPLY;
    play_sound(4);
    return 1;
}

/* ------------------------------------------------------ supply slot tooltips */

/* The owner, 2026-10-31: every supply slot shows its item's name and what is left of it while
   the mouse is over it, in the game's own popup style.  The stock game has no tooltips; its one
   on-screen popup is the hint panel (0x417E90): the rope-edged box of the hint object (its
   vtable[1], 0x423280: the fill colour at +0x14 inside a rectangle, CUSTOMPOPUP_FTROPESTYLE_BAR_*
   along its edges) with centred text in the hint font (0x408C30, the font at 0x45B26C).  The tank
   screen's overlay draws the hint last (0x41D127, after what the hand holds); when no hint is up
   and nothing is held, the slot under the mouse gets a box of the same kind just under the top bar.
   The slot boxes are 0x41E450's (0x45B2A8).  With "Extra supply slots" the slot a position shows
   comes from that DLL (FtfpSupplySlotsShown: its page of extra slots, or the stock one).
     * the name: the stock items' own store names (string 0xAE + 2 x item, English or German as the
       game is set), the starter eggs as Common Fish Eggs, this store's supplies their names here,
       the fish food "Fish Food" / "Fischfutter" (the game keeps no amount of it: the name alone);
     * what is left: doses (medicines and chemicals), uses (the Unknown Chemical) or batches (eggs),
       as the game will really spend them: the stock Unknown Chemical is one use whatever its count
       (0x4210B7 sets it to 1 before the use) unless a setting removed that, and eggs are one batch
       unless Universal supply slots stacks them (vanilla clears the egg slot at the hatch). */
#define TIP_LINE 20
#define TIP_PAD_X 10
#define TIP_PAD_Y 6
#define TIP_TOP 60                          /* just under the 57-pixel top bar */
#define FOOD_ITEM 0x17
#define STARTER_EGGS 26
#define S_HINT_FONT (*(void **)(UINT_PTR)0x0045B26Cu)
#define MOUSE_POS GAME(mouse_pos_fn, 0x00402060u)
#define CENTRE_TEXT GAME(this6_fn, 0x00408C30u)       /* (text, left, right, y, font, attr) */
#define TEXT_WIDTH GAME(text_width_fn, 0x004023D0u)    /* font (text, scale) */
typedef int (__cdecl *mouse_pos_fn)(int *pt);
typedef int (__fastcall *text_width_fn)(void *font, void *edx, const char *text, float scale);
typedef const unsigned char *(__stdcall *slots_shown_fn)(int position);
static const int TIP_SLOT[4][4] = { { 14, 9, 49, 48 }, { 63, 9, 98, 48 }, { 113, 9, 148, 48 }, { 164, 9, 199, 48 } };
static const unsigned char UNKNOWN_ONE_USE[10] = { 0xC7, 0x80, 0xF8, 0x02, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00 };

/* What position p (0-3) shows: the stock slot, or what Extra Supply Slots shows there (NULL: no
   slot there, page 3's fourth place). */
static const unsigned char *shown_slot(char *state, int p) {
    HMODULE slots = GetModuleHandleW(L"Extra Supply Slots.dll");
    slots_shown_fn fn = slots != NULL ? (slots_shown_fn)GetProcAddress(slots, "FtfpSupplySlotsShown") : NULL;
    if (fn != NULL) {
        const unsigned char *r = fn(p);
        if (r != (const unsigned char *)1) return r;               /* 1: no game of its own, the stock slot */
    }
    return (const unsigned char *)SLOT_RECORD(state, p);
}

static const char *game_string(int id);

static const char *const STORE_NAMES[4][2] = {
    { "Exotic Fish Eggs", "Exotische Fischeier" },
    { "Radioactive Growth Hormone", "Radioaktive Wachstumshormone" },
    { "Revival Potion", "Wiederbelebungstrank" },
    { "ClonaFish", "ClonaFish" },
};

static const char *slot_name(int item, int de) {
    if (item == FOOD_ITEM) return de ? "Fischfutter" : "Fish Food";
    if (item >= EXOTIC_ITEM && item <= CLONA_ITEM) return STORE_NAMES[item - EXOTIC_ITEM][de];
    if (item == STARTER_EGGS) item = 5;                               /* the common eggs' name */
    if (item >= 0 && item <= 7) return game_string(0xAE + 2 * item);
    return NULL;
}

/* The stock egg hatches' "empty the slot" (the first of the five field clears, 0x4213A7 common,
   0x421476 unusual, 0x421549 rare): while it is there a batch is the whole stack. Universal supply
   slots' stack_*_egg_uses patches put a call there that takes one batch and empties the slot only
   at 0; anything else that is not the stock store counts the same way. */
static const unsigned char EGG_CLEAR_COMMON[6] = { 0x89, 0xA9, 0x14, 0x03, 0x00, 0x00 };
static const unsigned char EGG_CLEAR_OTHER[6] = { 0x89, 0xAA, 0x14, 0x03, 0x00, 0x00 };

/* How many times the record can still be used, as the game this DLL runs in will spend it: read
   from the executable's own code, never from the settings' names.
     * medicines (0-1), Fish Vitamins and Growth Hormone (2-3) and this store's chemicals (29-31):
       one dose a use, the stock tails (0x420D87, 0x421305): the count;
     * the Unknown Chemical (4): the stock use sets the count to 1 first (0x4210B7), so one use,
       unless that instruction is gone (Unknown Chemical: 3 uses, Universal supply slots): the count;
     * stock eggs (5-7): one batch while the egg's stock clear is in place, else the count;
     * the starter eggs (26): one batch, always (their clear, 0x42161A, is never patched);
     * Exotic Fish Eggs (28): this DLL's own hatch (exotic_hatch) takes one of the stack only with
       Universal supply slots' use trampoline in place (universal_slots), else empties it. */
static int uses_left(int item, int count) {
    switch (item) {
    case 4:
        return ftfp_site_holds(0x004210B7u, UNKNOWN_ONE_USE, sizeof UNKNOWN_ONE_USE) ? 1 : count;
    case 5:
        return ftfp_site_holds(0x004213A7u, EGG_CLEAR_COMMON, sizeof EGG_CLEAR_COMMON) ? 1 : count;
    case 6:
        return ftfp_site_holds(0x00421476u, EGG_CLEAR_OTHER, sizeof EGG_CLEAR_OTHER) ? 1 : count;
    case 7:
        return ftfp_site_holds(0x00421549u, EGG_CLEAR_OTHER, sizeof EGG_CLEAR_OTHER) ? 1 : count;
    case STARTER_EGGS:
        return 1;
    case EXOTIC_ITEM:
        return universal_slots() ? count : 1;
    default:
        return count;
    }
}

/* "3 doses left", "1 use left", "2 batches left" (German "Noch 3 Dosen", ...). */
static void left_line(char *out, int item, int n, int de) {
    int egg = item == 5 || item == 6 || item == 7 || item == STARTER_EGGS || item == EXOTIC_ITEM;
    const char *en = egg ? (n == 1 ? " batch left" : " batches left")
                   : item == 4 ? (n == 1 ? " use left" : " uses left") : (n == 1 ? " dose left" : " doses left");
    const char *ge = egg ? " Gelege" : item == 4 ? (n == 1 ? " Anwendung" : " Anwendungen") : (n == 1 ? " Dosis" : " Dosen");
    char digits[12];
    int d = 0, at = 0;
    unsigned int v = n < 0 ? 0u : (unsigned int)n;
    const char *s;
    if (de) for (s = "Noch "; *s; ++s) out[at++] = *s;
    do { digits[d++] = (char)('0' + v % 10); v /= 10; } while (v && d < 11);
    while (d) out[at++] = digits[--d];
    for (s = de ? ge : en; *s && at < 60; ++s) out[at++] = *s;
    out[at] = '\0';
}

static int text_width(const char *text) {
    void *font = S_HINT_FONT;
    return font != NULL && text != NULL ? TEXT_WIDTH(font, NULL, text, 1.0f) : 0;
}

/* The tooltip of the slot under the mouse, if any; 1 = drawn. */
static int __cdecl slot_tooltip(char *impl, int hint_shown) {
    char *state = (char *)P(impl, 0x34);
    const unsigned char *r;
    const char *name;
    char left[64];
    int pt[2], p, de = german(), w, lines, rect[4], item;
    void *hint, **vtable;
    if ((hint_shown & 0xFF) != 0 || state == NULL || *(unsigned char *)impl != 0) return 0;
    if (*I(impl, 0x1C) != NO_SUPPLY || *I(impl, 0x28) != NO_SUPPLY || *I(state, 0x1E4E8) != -1) return 0;
    if (((unsigned char *)state)[0x1E4F9] != 0) return 0;              /* the intro: no top bar */
    MOUSE_POS(pt);
    for (p = 0; p < 4; ++p) {
        if (inside(pt[0], pt[1], TIP_SLOT[p][0], TIP_SLOT[p][1], TIP_SLOT[p][2], TIP_SLOT[p][3])) break;
    }
    if (p == 4 || (r = shown_slot(state, p)) == NULL || *I((void *)r, SR_ICON) == 0) return 0;
    item = *I((void *)r, SR_ITEM);
    if ((name = slot_name(item, de)) == NULL) return 0;
    lines = 1;
    w = text_width(name);
    if (item != FOOD_ITEM) {
        left_line(left, item, uses_left(item, *I((void *)r, SR_COUNT)), de);
        if (text_width(left) > w) w = text_width(left);
        lines = 2;
    }
    w += 2 * TIP_PAD_X;
    rect[0] = (TIP_SLOT[p][0] + TIP_SLOT[p][2]) / 2 - w / 2;
    if (rect[0] < 4) rect[0] = 4;
    if (rect[0] + w > 796) rect[0] = 796 - w;
    rect[1] = TIP_TOP;
    rect[2] = rect[0] + w;
    rect[3] = TIP_TOP + 2 * TIP_PAD_Y + lines * TIP_LINE;
    hint = P(P(impl, S_HINTS), 0);
    if (hint != NULL) {
        vtable = *(void ***)hint;
        ((this1_fn)vtable[1])(hint, NULL, (int)(UINT_PTR)rect);       /* the hint's own box (0x423280) */
    }
    CENTRE_TEXT(P(impl, 0x54), NULL, (int)(UINT_PTR)name, rect[0], rect[2], TIP_TOP + TIP_PAD_Y,
                (int)(UINT_PTR)S_HINT_FONT, 0);
    if (lines == 2) {
        CENTRE_TEXT(P(impl, 0x54), NULL, (int)(UINT_PTR)left, rect[0], rect[2], TIP_TOP + TIP_PAD_Y + TIP_LINE,
                    (int)(UINT_PTR)S_HINT_FONT, 0);
    }
    return 1;
}

/* 0x41D127 `call 0x417FD0` (the hints' draw; ecx = the hints, esi = the tank screen), al = a hint
   was drawn: the hint first, then a slot's tooltip when there was none. */
static const DWORD k_hint_draw = 0x00417FD0u;

__declspec(naked) static void stub_slot_tooltip(void) {
    __asm {
        call dword ptr [k_hint_draw]
        push eax
        push eax
        push esi
        call slot_tooltip
        add esp, 8
        pop eax
        ret
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
    if (tank < 0 || tank > 2 || (rec = record_at(state, tank, slot)) == NULL) return found;
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

/* Time Warp and Add Money show only with their settings; with Free upgrades
   every item here costs $0 (the stock store keeps its prices). */
#define ITEMS 13
#define ITEM_WARP 4
#define ITEM_MONEY 5
#define FIN_RGH (-3)                        /* the Radioactive Growth Hormone: not an animal */
#define FIN_REVIVAL (-4)                    /* the Revival Potion */
#define FIN_CLONA (-5)                      /* ClonaFish */
#define ITEM_TANK 9
#define ITEM_SLOTS 12
#define SLOTS_ICON_W 76                     /* ITEM_EXTRA_SUPPLY_SLOTS.png (build_supply_slots_assets.py) */
#define SLOTS_ICON_H 51
#define SPR_STOCK_TANK2 157                 /* ITEM_TANK2.png: the stock store's Second Tank */
#define AUTO_ICON_W 73                      /* ITEM_AUTO_FEEDER.png, ITEM_AUTO_HEALER.png (build_auto_upgrades_assets.py) */
#define AUTO_ICON_H 65
#define MONEY_GAIN 1000
#define MONEY_MAX 0x7FFFFFFF       /* money is a signed 32-bit int (state+0x38C); the stock sale adds to it unclamped (0x424074) */
static int warp_on = 0, money_on = 0, free_on = 0;
static int item_shown(int i) {
    if (i == ITEM_TANK) return tanks_call("FtfpExtraTanksOwned") >= 0;
    if (i == ITEM_SLOTS) return slots_call("FtfpSupplySlotsOwned") >= 0;
    return i == ITEM_WARP ? warp_on : i == ITEM_MONEY ? money_on : 1;
}
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
    { FIN_WARP, 500, 411, 100, 79, 66, SPR_ITEM_WARP, 65, 64,
      { "Time Warp", "Zeitsprung" },
      { "Skip ahead in time! Choose how many\nhours (1-72) pass, as if you had been\naway that long. Your fish age, eat and\nresearch goes on.",
        "Spring in der Zeit voraus! W\xE4hle, wie\nviele Stunden (1-72) vergehen, als w\xE4rst\ndu so lange weg gewesen. Deine Fische\naltern, fressen, und die Forschung l\xE4uft." } },
    { FIN_MONEY, 950, 503, 100, 79, 66, SPR_ITEM_MONEY, 74, 60,
      { "Add $1,000", "Plus 1.000 $" },               /* the title font has no "+" (paddington_tt_30) */
      { "A pile of gold coins! Each one you buy\nadds $1,000 to your money.\nBuy as many as you like.",
        "Ein Haufen Goldm\xFCnzen! Jeder Kauf\nbringt dir 1.000 $.\nKauf so viele du willst." } },
    { FIN_RGH, 10000, 595, 90, 79, 72, SPR_ITEM_RGH, 48, 65,
      { "Radioactive Growth Hormone", "Radioaktive Wachstumshormone" },
      { "Every fish in your tank gets full health\nand no sickness, young ones grow up at\nonce, and pregnant ones give birth to\nbabies. Treated fish sell for the highest\npossible price! Contains 3 doses.",
        "Jeder Fisch in deinem Becken wird ganz\ngesund und heil, junge werden sofort\nerwachsen, tr\xE4" "chtige geb\xE4" "ren Babys.\nBehandelte Fische werden zum H\xF6" "chstpreis\nverkauft! Reicht f\xFCr 3 Behandlungen." } },
    /* The owner's names and descriptions (docs/revival-potion-spec.md), wrapped to the panel. */
    { FIN_REVIVAL, 10000, 687, 90, 79, 72, SPR_ITEM_REVIVAL, 48, 65,
      { "Revival Potion", "Wiederbelebungstrank" },
      { "This magical potion instantly revives\ndead fish and restores them to full\nhealth. Contains 3 doses.",
        "Dieser magische Trank belebt tote\nFische sofort wieder und macht sie\nganz gesund. Reicht f\xFCr 3 Behandlungen." } },
    { FIN_CLONA, 2500, 44, 165, 85, 72, SPR_ITEM_CLONA, 48, 65,
      { "ClonaFish", "ClonaFish" },
      { "A wonder drug that instantly clones all\nfish in the tank. Make sure there's\nenough space in the tank!\nContains 3 doses.",
        "Ein Wundermittel, das alle Fische im\nBecken sofort klont. Achte auf genug\nPlatz im Becken!\nReicht f\xFCr 3 Behandlungen." } },
    { FIN_TANK, 10000, 598, 246, 160, 70, SPR_STOCK_TANK2, 150, 60,       /* two net cells, bottom right */
      { "Extra Tank", "Weiteres Aquarium" },
      { "Another tank for breeding! Each one\nyou buy opens the next of Tank 4,\nTank 5 and Tank 6.",
        "Noch ein Aquarium zum Z\xFC" "chten! Jeder\nKauf \xF6" "ffnet das n\xE4" "chste: Becken 4,\n5 und 6." } },
    /* The owner's descriptions, wrapped to the panel (auto_upgrades.h). */
    { FIN_FEEDER, 10000, 141, 165, 73, 72, SPR_ITEM_FEEDER, AUTO_ICON_W, AUTO_ICON_H,
      { "Auto-Feeder", "Futterautomat" },
      { "Automatically feeds all your fish in\nevery tank. No more starvation, ever!",
        "F\xFCttert automatisch alle deine Fische\nin jedem Becken. Nie wieder Hunger!" } },
    { FIN_HEALER, 10000, 234, 165, 71, 72, SPR_ITEM_HEALER, AUTO_ICON_W, AUTO_ICON_H,
      { "Auto-Healer", "Heilautomat" },
      { "Magically cures all diseases from fish\nand restores them to full health.\nWorks in every tank.",
        "Heilt auf magische Weise alle Krankheiten\ndeiner Fische und macht sie ganz gesund.\nWirkt in jedem Becken." } },
    { FIN_SLOTS, 10000, 320, 168, 77, 69, 0, SLOTS_ICON_W, SLOTS_ICON_H,       /* its picture: slots_image() */
      { "Extra Supply Slots", "Zus\xE4tzliche Vorratsf\xE4" "cher" },
      { "Seven more supply slots for medicine,\nchemicals and eggs, on two more pages.\nThe arrows beside the slots turn the\npage. One purchase opens all seven.",
        "Sieben weitere Vorratsf\xE4" "cher f\xFCr Medizin,\nChemikalien und Eier, auf zwei weiteren\nSeiten. Die Pfeile neben den F\xE4" "chern\nbl\xE4ttern um. Ein Kauf \xF6" "ffnet alle sieben." } },
};

static int price_of(const store_item *it) { return free_on ? 0 : it->price; }

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
        if (item_shown(i) && inside(x, y, ITEM[i].x, ITEM[i].y, ITEM[i].x + ITEM[i].w, ITEM[i].y + ITEM[i].h)) return i;
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
        void *img = it->fin == FIN_SLOTS ? slots_image()
                                         : (void *)(UINT_PTR)SPRITE_GET(P(impl, 0x14), NULL, it->sprite);
        int x = it->x + (it->w - it->icon_w) / 2, y = it->y + (it->h - it->icon_h) / 2;
        if (img == NULL || !item_shown(i)) continue;
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
            const char *owned_line = auto_owned_line(selected);           /* an Auto item: how to unpurchase */
            draw_text(impl, owned_line != NULL ? owned_line : game_string(0xE9), 0x39, 0x1FD, FONT_BODY, 0);   /* "This is in your inventory." */
        } else {
            char line[64];
            const char *label = game_string(0xAD);                            /* "Price:" */
            int n = 0, v = price_of(it), d = 0;
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

/* Exotic Eggs or the Radioactive Growth Hormone with universal slots, as the
   setting buys stock eggs and chemicals: confirm, then a stack of the same
   item in slots 2-4 gains `uses` (eggs one hatch, a chemical 3 doses), else
   the first empty slot takes it, else the setting's three "replace?" prompts. */
static void buy_into_slots(char *impl, char *state, int price, int item, int icon, int cursor, int uses);

static void buy_universal(char *impl, char *state, int price, int item, int icon, int cursor, int uses) {
    if (!confirm(impl, 0xEC)) return;
    slots_lend(item);
    buy_into_slots(impl, state, price, item, icon, cursor, uses);
    slots_return();
}

/* buy_universal's search and purchase, once the purchase is confirmed. */
static void buy_into_slots(char *impl, char *state, int price, int item, int icon, int cursor, int uses) {
    int k, slot = -1, count = uses;
    static const int replace_prompt[4] = { 0, 0xEF, 0xEE, 0xED };
    char *r;
    for (k = 1; k <= 3 && slot < 0; ++k) {
        r = SLOT_RECORD(state, k);
        if (*I(r, SR_ICON) != 0 && *I(r, SR_ITEM) == item) {
            slot = k;
            count = *I(r, SR_COUNT) + uses;
        }
    }
    for (k = 1; k <= 3 && slot < 0; ++k)
        if (*I(SLOT_RECORD(state, k), SR_ICON) == 0) slot = k;
    for (k = 1; k <= 3 && slot < 0; ++k)
        if (confirm(impl, replace_prompt[k])) slot = k;
    if (slot < 0) return;
    charge(state, price);
    r = SLOT_RECORD(state, slot);
    *I(r, SR_ITEM) = item;
    *I(r, SR_PRESENT) = 1;
    *I(r, SR_COUNT) = count;
    *I(r, SR_ICON) = icon;
    *I(r, SR_CURSOR) = cursor;
    *I(r, SR_X) = slot * 0x30 + 0x1E;
}

/* A new chemical (the hormone, the Revival Potion, ClonaFish) without
   universal slots, as the stock store buys a chemical (0x428172, the writer
   0x427540): "Replace chemical in slot #3?" (0xEE) if slot #3 holds one, else
   the purchase question (0xEC); then slot #3 holds it with 3 doses, whatever
   was there before is gone, as stock. */
static void buy_chemical_stock(char *impl, char *state, int price, int item, int icon, int cursor);

static void buy_chemical(char *impl, char *state, int price, int item, int icon, int cursor) {
    if (exotic_any_slot) {
        buy_universal(impl, state, price, item, icon, cursor, RGH_DOSES);
        return;
    }
    slots_lend(item);                                /* slot #3, or an extra slot lent to it */
    buy_chemical_stock(impl, state, price, item, icon, cursor);
    slots_return();
}

/* buy_chemical without universal slots: slot #3. */
static void buy_chemical_stock(char *impl, char *state, int price, int item, int icon, int cursor) {
    char *r = SLOT_RECORD(state, 2);
    if (!confirm(impl, *I(r, SR_ICON) != 0 ? 0xEE : 0xEC)) return;
    charge(state, price);
    *I(r, SR_ITEM) = item;
    *I(r, SR_PRESENT) = 1;
    *I(r, SR_COUNT) = RGH_DOSES;
    *I(r, SR_ICON) = icon;
    *I(r, SR_CURSOR) = cursor;
    *I(r, SR_X) = 2 * 0x30 + 0x1E;
}

/* ------------------------------------------------------------ time warp */

/* The Time Warp setting ships "Time Warp.ini" beside this DLL.  Buying the
   item asks for the hours (1-72) in a Windows popup, confirms, charges $500 ($0 with Free upgrades),
   and then plays those hours exactly as time away: each live fish's banked
   time (+0x04) and each running research's banked time get the seconds, at
   most 4 hours at a time so the stock catch-up caps (32400 / 25200 / 18000 s
   at 2x / Normal / 1/2 speed, 0x41FF1D) never cut them, and the stock fish
   update 0x41FE70 runs after each chunk.  Its `this` is the tank screen,
   remembered by the hook on its activation call (0x421AAA).  Once the last
   chunk has been played, an OK box says the hours, age steps and price. */
#define WARP_CHUNK 14400u
#define S_SPEED_FISH 0x1E168
#define FISH_RECORD(state, tank, slot) ((state) + 0x390 + (tank) * 0x51EC + (slot) * SLOT_STRIDE)
#define TANK_SLOTS (*(const unsigned char *)(UINT_PTR)0x004206B3u)      /* 21, or 30 with Bigger tanks */
typedef void (__fastcall *fish_update_fn)(void *tank, int edx);
static const fish_update_fn fish_update = (fish_update_fn)0x0041FE70u;
static void *volatile tank_scene = NULL;

static void warp_fish(char *f, unsigned int seconds) {
    if (*I(f, 0x00) == 0 || *I(f, 0x3C) <= 0 || *I(f, 0x4C) == BODY_SEAHORSE) return;
    *(unsigned int *)(f + 0x04) += seconds;
}

/* "3 extra tanks": the tanks Extra Tanks.dll holds (Tanks 4-6, or Tank 1 while
   one of them is on screen) are warped too, and its own pass of the fish update
   over them (FtfpExtraTanksUpdate, what it runs after every stock update) runs
   after each of the stock ones here. */
typedef void (__stdcall *tanks_update_fn)(void *scene);
static void update_held_tanks(void *scene) {
    HMODULE tanks = GetModuleHandleW(L"Extra Tanks.dll");
    tanks_update_fn fn = tanks != NULL ? (tanks_update_fn)GetProcAddress(tanks, "FtfpExtraTanksUpdate") : NULL;
    if (fn != NULL) fn(scene);
}

static void warp_chunk(char *state, unsigned int seconds) {
    int tank, slot, r, e, slots = TANK_SLOTS;
    if (slots > RECORDS - 1) slots = RECORDS - 1;
    for (tank = 0; tank < 4; ++tank) {
        for (slot = 0; slot < slots; ++slot) warp_fish(FISH_RECORD(state, tank, slot), seconds);
    }
    for (e = 0; e < HELD_TANKS; ++e) {
        unsigned char *b = held_block(e);
        if (b == NULL) break;
        for (slot = 0; slot < slots; ++slot) warp_fish((char *)b + slot * SLOT_STRIDE, seconds);
    }
    for (r = 0x17; r <= 0x19; ++r) {                    /* Fish Food, Environment, Advertising */
        if (*I(state, r * 20 + 0x7C) != 0) *(unsigned int *)(state + r * 20 + 0x84) += seconds;
    }
}

static void time_warp(char *impl, char *state) {
    wchar_t text[256];
    unsigned int left;
    int hours, price = price_of(&ITEM[ITEM_WARP]);
    if (*I(state, S_SPEED_FISH) > 100) {
        tw_tell(L"Time is stopped. Turn time back on in Options, then warp.");
        return;
    }
    if (*I(state, S_MONEY) < price) {
        HINT(P(impl, 0xC), NULL, 2);                 /* "You can't afford to buy this yet!" */
        return;
    }
    if (tank_scene == NULL) {
        tw_tell(L"Open a tank first, then come back to the store to warp.");
        return;
    }
    swprintf_s(text, 256, L"Costs $%d. Your fish age, eat and breed, and research goes on, as if you had "
               L"been away.", price);
    hours = tw_ask_hours(text);
    if (hours <= 0) return;
    swprintf_s(text, 256, L"Warp %d hour%s for $%d?\n\nYour fish will age %d hour%s, as if you had been "
               L"away that long. This cannot be undone.", hours, hours == 1 ? L"" : L"s", price, hours,
               hours == 1 ? L"" : L"s");
    if (!tw_confirm(text)) return;
    if (*I(state, S_MONEY) < price) return;
    charge(state, price);
    fish_update(tank_scene, 0);                         /* the real time so far, by the stock rules */
    update_held_tanks(tank_scene);
    for (left = (unsigned int)hours * 3600u; left > 0;) {
        unsigned int c = left > WARP_CHUNK ? WARP_CHUNK : left;
        left -= c;
        warp_chunk(state, c);
        fish_update(tank_scene, 0);
        update_held_tanks(tank_scene);
    }
    /* What the update made of those seconds: one age step per 60 x speed seconds (0x41FFE9); a
       chunk plus a fish's banked part of a step stays under every cap, so none of it was cut. */
    tw_done(hours, (unsigned int)hours * 3600u / (60u * (unsigned int)*I(state, S_SPEED_FISH)), L"age step", price);
}

/* Add Money: the price is paid as for any item, then $1,000 goes into the
   money the way a stock sale adds it (0x424074), never past MONEY_MAX. */
static int money_after_gain(int money) {
    return money > MONEY_MAX - MONEY_GAIN ? MONEY_MAX : money + MONEY_GAIN;
}

static void add_money(char *impl, char *state, int price) {
    if (!confirm(impl, 0xEC)) return;
    charge(state, price);
    *I(state, S_MONEY) = money_after_gain(*I(state, S_MONEY));
}

#include "auto_upgrades.h"            /* the Auto-Feeder and Auto-Healer */

/* Exotic Fish Eggs without universal slots, as the stock store buys eggs: slot #4. */
static __declspec(noinline) void buy_exotic_stock(char *impl, char *state, int price) {
    if (!confirm(impl, *I(state, S_EGG_PRESENT) ? 0xED : 0xEC)) return;
    charge(state, price);
    *I(state, S_EGG_ITEM) = EXOTIC_ITEM;
    *I(state, S_EGG_PRESENT) = 1;
    *I(state, S_EGG_COUNT) = 3;
    *I(state, S_EGG_ICON) = SPR_TOOL_EGGS;      /* the shelf shows the small picture, as stock eggs do */
    *I(state, S_EGG_CURSOR) = SPR_TOOL_EGGS;
    *I(state, S_EGG_X) = 3 * 0x30 + 0x1E;
}

static void buy(void *scene) {
    char *impl = store_impl(scene);
    char *state = (char *)P(impl, 0x10);
    const store_item *it;
    void *hint = P(impl, 0xC);
    int price;
    if (selected < 0 || state == NULL) return;
    it = &ITEM[selected];
    price = price_of(it);
    if (it->fin == FIN_WARP) {
        time_warp(impl, state);
        return;
    }
    if (sold_out(state, it->fin)) {
        HINT(hint, NULL, 0x1C);                      /* "You already own this!" */
        return;
    }
    if (price > *I(state, S_MONEY)) {
        HINT(hint, NULL, 2);                         /* "You can't afford to buy this yet!" */
        return;
    }
    if (it->fin == FIN_MONEY) {
        add_money(impl, state, price);
        return;
    }
    if (it->fin == FIN_RGH) {
        buy_chemical(impl, state, price, RGH_ITEM, SPR_TOOL_RGH, SPR_DROPPER_RGH);
        return;
    }
    if (it->fin == FIN_REVIVAL) {
        buy_chemical(impl, state, price, REVIVAL_ITEM, SPR_TOOL_REVIVAL, SPR_DROPPER_REVIVAL);
        return;
    }
    if (it->fin == FIN_CLONA) {
        buy_chemical(impl, state, price, CLONA_ITEM, SPR_TOOL_CLONA, SPR_DROPPER_CLONA);
        return;
    }
    if (it->fin == FIN_FEEDER || it->fin == FIN_HEALER) {
        auto_buy(impl, state, it->fin, price);
        return;
    }
    if (it->fin == FIN_SLOTS) {                      /* all seven extra supply slots at once */
        if (!confirm(impl, 0xEC)) return;
        if (slots_call("FtfpSupplySlotsBuy") < 0) return;
        charge(state, price);
        return;
    }
    if (it->fin == FIN_TANK) {                       /* the next of Tank Three, Four and Five */
        if (!confirm(impl, 0xEC)) return;
        if (tanks_call("FtfpExtraTanksBuy") < 0) return;
        charge(state, price);
        return;
    }
    if (it->fin == 0 && exotic_any_slot) {
        buy_universal(impl, state, price, EXOTIC_ITEM, SPR_TOOL_EGGS, SPR_TOOL_EGGS, 1);
        return;
    }
    if (it->fin == 0) {
        slots_lend(EXOTIC_ITEM);                     /* slot #4, or an extra slot lent to it */
        buy_exotic_stock(impl, state, price);
        slots_return();
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
        make_companion(state, rec, it->fin, FULL_METER, FULL_METER);
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
        charge(state, price);
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

/* The game's fish slots are fish_slots() above: 21, or 30 with "Bigger tanks" (the update
   loop's bound, 0x4206B1); record 30 is never a fish's. */

/* Records an earlier build's animals stay in until "Tank Animals <slot>.dat"
   is confirmed written (then they are cleared, before the game saves). */
static unsigned char pending[4][RECORDS];
static int pending_any = 0;

/* New game (after the stock clear of the fish slots): no animals, and the
   records past the fish that earlier builds kept animals in are cleared. */
static void __cdecl clear_animals(char *state) {
    int t, s, first = fish_slots() > OLD_ANIMAL_FIRST ? fish_slots() : OLD_ANIMAL_FIRST;
    auto_new_game();
    memset(animal_area, 0, sizeof animal_area);
    memset(pending, 0, sizeof pending);
    pending_any = 0;
    for (t = 0; t <= 3; ++t) {
        for (s = first; s < RECORDS; ++s) {
            *I(fish(state, t, s), F_LIVE) = 0;
            *I(fish(state, t, s), F_MARK) = 0;
        }
    }
}

/* ------------------------------------------- "Tank Animals <slot>.dat"

   Beside the save, as DS Exclusive Fish's "DS Fish <slot>.dat":
   "<Documents>\LDW\<exe name>\Fish Tycoon Fix Patcher Data\Tank Animals <slot>.dat".
   Written whenever the game saves that slot (before the game writes its own
   file), atomically: a .tmp file, flushed, then moved over the old one,
   which becomes "Tank Animals <slot>.previous.dat"; then read back and
   compared.  It names the save it belongs to (its money, money spent,
   sessions and minutes played as saved), so a save restored from a backup
   never picks up a later or another save's animals: such a file is set
   aside, never deleted.  A file from an earlier point of the same save's
   play (it was played and saved with DS Store Items off since: sessions
   and minutes only grow) brings its animals back. */
#define TA_MAGIC 0x41545446u          /* "FTTA" */
#define TA_VERSION 1u
#define TA_RECORDS (ANIMAL_TANKS * ANIMAL_SLOTS)
#define TA_HEADER 10
#define TA_BYTES (TA_HEADER * 4 + TA_RECORDS * SLOT_STRIDE)
static unsigned char ta_file[TA_BYTES], ta_check[TA_BYTES];

typedef BOOL (WINAPI *special_folder_fn)(HWND, LPWSTR, int, BOOL);

static void append_number(wchar_t *out, size_t cap, int value) {
    wchar_t digits[12];
    int i = 0;
    unsigned int v = (unsigned int)value;
    do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 11);
    while (i) {
        size_t len = wcslen(out);
        if (len + 1 >= cap) return;
        out[len] = digits[--i];
        out[len + 1] = L'\0';
    }
}

/* kind: L"" the file, L".previous", L".tmp", or a set-aside name. */
static int ta_path(int slot, const wchar_t *kind, wchar_t *out, DWORD cap, int make_folder) {
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
    if (wcslen(out) + wcslen(name) + wcslen(kind) + 96 >= cap) return 0;
    wcscat_s(out, cap, L"\\LDW\\");
    wcscat_s(out, cap, name);
    wcscat_s(out, cap, L"\\Fish Tycoon Fix Patcher Data");
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\Tank Animals ");
    append_number(out, cap, slot);
    wcscat_s(out, cap, kind);
    wcscat_s(out, cap, L".dat");
    return 1;
}

static int is_game_slot(int slot) {
    return slot != 0 && slot != 0xB;          /* 0 = settings, 11 = the game's own extra record */
}

/* The save these animals belong to: its money, money spent, sessions and minutes played. */
static void fingerprint(char *state, DWORD *out) {
    out[0] = (DWORD)*I(state, S_MONEY);
    out[1] = (DWORD)*I(state, S_SPENT);
    out[2] = (DWORD)*I(state, 0x3C);
    out[3] = (DWORD)*I(state, 0x44);
}

static DWORD fnv(const unsigned char *data, int size) {
    DWORD h = 2166136261u;
    int i;
    for (i = 0; i < size; ++i) h = (h ^ data[i]) * 16777619u;
    return h;
}

static void ta_build(char *state) {
    DWORD *h = (DWORD *)ta_file;
    int t, k;
    for (t = 0; t < ANIMAL_TANKS; ++t) {
        for (k = 0; k < ANIMAL_SLOTS; ++k) {
            memcpy(ta_file + TA_HEADER * 4 + (t * ANIMAL_SLOTS + k) * SLOT_STRIDE, animal(state, t, k), SLOT_STRIDE);
        }
    }
    h[0] = TA_MAGIC;
    h[1] = TA_VERSION;
    h[2] = TA_RECORDS;
    h[3] = SLOT_STRIDE;
    fingerprint(state, h + 4);
    h[8] = 0;
    h[9] = fnv(ta_file + TA_HEADER * 4, TA_RECORDS * SLOT_STRIDE);
}

/* 1 = the file holds exactly `size` bytes, read into `out`. */
static int read_all(const wchar_t *path, unsigned char *out, DWORD size) {
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    DWORD got = 0, extra = 0;
    unsigned char probe;
    int ok;
    if (file == INVALID_HANDLE_VALUE) return 0;
    ok = ReadFile(file, out, size, &got, NULL) && got == size && ReadFile(file, &probe, 1, &extra, NULL) && extra == 0;
    CloseHandle(file);
    return ok;
}

/* Writes the animals for this slot; 1 = written and read back the same. */
static int ta_write(char *state, int slot) {
    wchar_t path[1024], previous[1024], temp[1024];
    HANDLE file;
    DWORD written = 0;
    int ok;
    if (!ta_path(slot, L"", path, 1024, 1) || !ta_path(slot, L".previous", previous, 1024, 0)
        || !ta_path(slot, L".tmp", temp, 1024, 0)) {
        return 0;
    }
    ta_build(state);
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    ok = WriteFile(file, ta_file, TA_BYTES, &written, NULL) && written == TA_BYTES && FlushFileBuffers(file);
    CloseHandle(file);
    if (!ok) {
        DeleteFileW(temp);                                     /* our own half-written temp file */
        return 0;
    }
    if (GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES
        && !MoveFileExW(path, previous, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        return 0;
    }
    if (!MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) return 0;
    return read_all(path, ta_check, TA_BYTES) && memcmp(ta_check, ta_file, TA_BYTES) == 0;
}

/* Keep a file that cannot be used, never delete it: "<name>.<why>-<n>.dat". */
static void set_aside(int slot, const wchar_t *path, const wchar_t *why) {
    int n;
    for (n = 1; n < 100; ++n) {
        wchar_t kind[64], aside[1024];
        wcscpy_s(kind, 64, L".");
        wcscat_s(kind, 64, why);
        wcscat_s(kind, 64, L"-");
        append_number(kind, 64, n);
        if (!ta_path(slot, kind, aside, 1024, 0)) return;
        if (GetFileAttributesW(aside) != INVALID_FILE_ATTRIBUTES) continue;
        MoveFileExW(path, aside, MOVEFILE_WRITE_THROUGH);
        return;
    }
}

/* 1 = this file is this save's animals (now in ta_check); 2 = written at an
   earlier point of this save's play (played and saved since without DS
   Store Items: sessions and minutes played only grow); 0 = no file;
   -1 = unreadable or damaged; -2 = another save's, or a later point of this
   one (an older save restored from a backup). */
static int ta_read(char *state, const wchar_t *path) {
    DWORD *h = (DWORD *)ta_check, want[4];
    if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return 0;
    if (!read_all(path, ta_check, TA_BYTES) || h[0] != TA_MAGIC || h[1] != TA_VERSION || h[2] != TA_RECORDS
        || h[3] != SLOT_STRIDE || h[9] != fnv(ta_check + TA_HEADER * 4, TA_RECORDS * SLOT_STRIDE)) {
        return -1;
    }
    fingerprint(state, want);
    if (memcmp(h + 4, want, sizeof want) == 0) return 1;
    return h[6] <= want[2] && h[7] <= want[3] && (h[6] < want[2] || h[7] < want[3]) ? 2 : -2;
}

static void ta_take(char *state) {
    int t, k;
    for (t = 0; t < ANIMAL_TANKS; ++t) {
        for (k = 0; k < ANIMAL_SLOTS; ++k) {
            char *rec = animal(state, t, k);
            memcpy(rec, ta_check + TA_HEADER * 4 + (t * ANIMAL_SLOTS + k) * SLOT_STRIDE, SLOT_STRIDE);
            if (!is_animal(rec)) memset(rec, 0, SLOT_STRIDE);
        }
    }
}

static void log_line(const char *text);
static void log_slot(const char *before, int slot, int count, const char *after);

/* Loads this save's animals from its file (or the previous generation's). */
static void ta_load(char *state, int slot) {
    wchar_t path[1024], previous[1024];
    int a, b;
    if (!ta_path(slot, L"", path, 1024, 0) || !ta_path(slot, L".previous", previous, 1024, 0)) return;
    a = ta_read(state, path);
    if (a == 1) { ta_take(state); return; }
    b = ta_read(state, previous);
    if (b == 1) { ta_take(state); log_slot("Slot ", slot, -1, ": the animals came from Tank Animals .previous.dat"); return; }
    if (a == 2 && ta_read(state, path) == 2) {
        ta_take(state);
        log_slot("Slot ", slot, -1, ": played and saved without DS Store Items since; its animals are back");
        return;
    }
    if (a == -1) set_aside(slot, path, L"unreadable");
    if (a == -2) set_aside(slot, path, L"other-save");
    if (b == -1) set_aside(slot, previous, L"unreadable");
    if (b == -2) set_aside(slot, previous, L"other-save");
    if (a < 0 || b < 0) log_slot("Slot ", slot, -1, ": a Tank Animals file did not belong to this save; it was set aside");
}

/* Clears the records the animals were moved out of (the file is written). */
static void clear_pending(char *state) {
    int t, s;
    for (t = 0; t <= 3; ++t) {
        for (s = 0; s < RECORDS; ++s) {
            if (!pending[t][s]) continue;
            REMOVE_FISH(state, NULL, t, s);
            *I(fish(state, t, s), F_MARK) = 0;
            *I(fish(state, t, s), F_KIND) = 0;
            pending[t][s] = 0;
        }
    }
    pending_any = 0;
}

/* After a save loads.  An earlier build kept the animals among the game's
   fish records (slots 26-30, or very early builds among the fish): they
   move into this save's animal records and file, and only once the file is
   written and read back are the game's records cleared.  If it cannot be
   written they stay in the save as they were, and the next save tries
   again.  Loading the same save again moves the same animals again and
   writes the same file.  A save with no animals in its records takes its
   animals from its file.  Leftovers past the fish in the old animal
   records are cleared, as before. */
static void settle_animals(char *state, int slot) {
    int t, s, moved = 0, first = fish_slots() > OLD_ANIMAL_FIRST ? fish_slots() : OLD_ANIMAL_FIRST;
    memset(animal_area, 0, sizeof animal_area);
    memset(pending, 0, sizeof pending);
    pending_any = 0;
    for (t = 0; t <= 3; ++t) {
        for (s = first; s < RECORDS; ++s) {
            char *f = fish(state, t, s);
            if (*I(f, F_LIVE) != 0 && !is_animal(f) && !is_companion(f, *I(f, F_FIN))) {
                *I(f, F_LIVE) = 0;
                *I(f, F_MARK) = 0;
            }
        }
    }
    for (t = 0; t <= 3; ++t) {
        for (s = 0; s < RECORDS; ++s) {
            char *f = fish(state, t, s);
            int fin = *I(f, F_FIN), k, to;
            if (*I(f, F_LIVE) == 0 || *I(f, F_BODY) != BODY_SEAHORSE) continue;
            if (fin != FIN_SEAHORSE && (fin < FIN_PUFFER || fin > FIN_EEL)) continue;
            for (k = 0, to = -1; k < 4 && to < 0; ++k) {
                int target = k == 0 ? (t <= 2 ? t : 0) : k - 1;
                char rec[SLOT_STRIDE];
                memcpy(rec, f, SLOT_STRIDE);
                if (place_animal(state, target, rec) >= 0) to = target;
            }
            if (to >= 0) {
                pending[t][s] = 1;
                pending_any = 1;
                ++moved;
            }
        }
    }
    if (moved == 0) {
        ta_load(state, slot);
        return;
    }
    if (ta_write(state, slot)) {
        clear_pending(state);
        log_slot("Slot ", slot, moved, " animal(s) moved from the save's fish records into Tank Animals.dat");
    } else {
        log_slot("Slot ", slot, moved, " animal(s) found in the save's fish records; Tank Animals.dat could not be "
                 "written, so they stay in the save until the next save");
    }
}

/* Before the game saves a slot: its animals' file; then, once that is
   written, the records an earlier build's animals were moved out of. */
static void __cdecl on_store_save(char *state, int slot) {
    if (state == NULL || !is_game_slot(slot)) return;
    auto_save(slot);
    if (ta_write(state, slot)) {
        if (pending_any) clear_pending(state);
    } else {
        log_slot("Slot ", slot, -1, ": Tank Animals.dat could not be written; the previous one is kept");
    }
}

/* The swimming fish are built (0x413D80) and refreshed (0x415460) by a loop
   over the tank's slots; at its `jl` back to the top this picks the next one:
   the next fish slot (skipping a record whose animal is waiting to leave it),
   then each of the tank's animals, then done.  `slot` and `rec` are the
   loop's own variables (the slot, and its record + 0x4C), already stepped
   past the slot just done.  1 = go round again. */
static int __cdecl view_next(char *view, int *slot, char **rec, const unsigned char *bound_at) {
    char *state = *(char **)(view + 0x5DE4);
    int tank = *I(state, S_CURRENT_TANK), done = *slot - 1, bound = *bound_at, s, k;
    if (done >= 0 && done < bound) {
        for (s = done + 1; s < bound; ++s) {
            if (!pending[tank & 3][s]) {
                *rec += (s - (done + 1)) * SLOT_STRIDE;          /* the loop's own pointer, stepped on */
                *slot = s;
                return 1;
            }
        }
        k = 0;
    } else {
        k = animal_index(state, tank, done);
        if (k < 0) return 0;
        ++k;
    }
    if (tank < 0 || tank >= ANIMAL_TANKS) return 0;
    for (; k < ANIMAL_SLOTS; ++k) {
        char *a = animal(state, tank, k);
        if (!is_animal(a)) continue;
        *slot = animal_slot(state, tank, k);
        *rec = a + F_BODY;
        return 1;
    }
    return 0;
}

/* After a save loads: every store animal's health and food are full, the eel's
   at home in its rock too.  Nothing in the game lowers a seahorse-type record's
   meters (its age step skips them, 0x42043F, and so does overfeeding, 0x4121F4;
   only feeding, 0x4121A3, and one supply item, 0x42125C, raise them), so this
   fills them once. */
static void fill_animals(char *state) {
    int t, k;
    for (t = 0; t < ANIMAL_TANKS; ++t) {
        for (k = 0; k < ANIMAL_SLOTS; ++k) {
            char *f = animal(state, t, k);
            if (is_kind(f, FIN_PUFFER) || is_kind(f, FIN_RAY) || is_kind(f, FIN_EEL)) {
                *I(f, F_HEALTH) = FULL_METER;
                *I(f, F_FOOD) = FULL_METER;
            }
        }
    }
    for (t = 0; t <= 2; ++t) {
        for (k = 0; k < ORN_SLOTS; ++k) {
            unsigned char *o = ornament(state, t, k);
            if (is_home_rock(o) && o[O_HOME_FLAG] == HOME_FLAG) {
                o[O_HOME_HEALTH] = FULL_METER;
                o[O_HOME_FOOD] = FULL_METER;
            }
        }
    }
}

typedef int (__fastcall *load_fn)(void *state, void *edx, int slot);

static int __fastcall on_state_load(char *state, void *edx, int slot) {
    int ok = GAME(load_fn, SITE_STATE_LOAD_HOLDS)(state, edx, slot) & 0xFF;
    if (ok && is_game_slot(slot)) {
        auto_load(slot);
        settle_animals(state, slot);
        fill_animals(state);
    }
    return ok;
}

/* The Supplies scene's vtable slots. */
static int __fastcall on_mouse(void *scene, void *edx, int type, int x, int y) {
    if (!page_upgrades) return GAME(this3_fn, SITE_VT_MOUSE_HOLDS)(scene, edx, type, x, y);
    if (type == 1) {
        hovered = hit_item(x, y);
    } else if (type == 3) {
        int hit = hit_item(x, y);
        if (hit >= 0 && hit == selected && auto_unpurchase(hit)) return 0;   /* an owned Auto item, clicked again */
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
        pushad
        mov eax, [esi + 0x34]
        lea eax, [edi + eax + 0x390]
        push eax
        call auto_step_end
        add esp, 4
        popad
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
        /* It dies: a Radioactive Growth Hormone mark ends with it (edx = the state). */
        cmp dword ptr [edi + edx + 0x390 + F_RADIOACTIVE], RADIOACTIVE_MARK
        jne dead
        mov dword ptr [edi + edx + 0x390 + F_RADIOACTIVE], 0
    dead:
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

/* 0x420E6F, the chemical switch (esi = the tank scene): items 29-31 (the
   Radioactive Growth Hormone, the Revival Potion, ClonaFish) run their dose,
   then the stock Growth Hormone's sparkle loop and tail; any other item goes
   on to the stock `je 0x42120A` with its flags. */
static const DWORD k_chem_switch = 0x00420E7Bu, k_gh_sparkle = 0x0042119Au;

__declspec(naked) static void stub_chem_use(void) {
    __asm {
        mov ecx, [esi + 0x34]
        mov eax, [ecx + 0x2F0]
        cmp eax, RGH_ITEM
        jb stock
        cmp eax, CLONA_ITEM
        ja stock
        pushad
        push eax
        push esi
        call new_chemical
        add esp, 8
        popad
        jmp k_gh_sparkle
    stock:
        sub eax, 2
        jmp k_chem_switch
    }
}

/* Buying a stock chemical over the hormone, the Revival Potion or ClonaFish asks
   "Replace chemical in slot #3?" too. */
static const DWORD k_chem_confirm_yes = 0x00428191u, k_chem_confirm_no = 0x004281D6u;

__declspec(naked) static void stub_chem_confirm(void) {
    __asm {
        cmp ecx, 0xAA
        je chemical
        cmp ecx, SPR_TOOL_RGH
        je chemical
        cmp ecx, SPR_TOOL_REVIVAL
        je chemical
        cmp ecx, SPR_TOOL_CLONA
        je chemical
        jmp k_chem_confirm_no
    chemical:
        jmp k_chem_confirm_yes
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

/* 0x421B52 `call 0x420B70` (thiscall impl; x, y; ret 8), the release of a held
   supply: the store's supplies on the trash can are thrown away, else the
   stock use (or its Universal supply slots trampoline) runs as before. */
static const DWORD k_supply_use = 0x00420B70u;

__declspec(naked) static void stub_supply_drop(void) {
    __asm {
        push ecx
        push dword ptr [esp + 0x0C]
        push dword ptr [esp + 0x0C]
        push ecx
        call supply_trash
        add esp, 12
        pop ecx
        test eax, eax
        jz stock
        ret 8
    stock:
        jmp dword ptr [k_supply_use]
    }
}

/* ----------------------------------------------------------------- install */

static const DWORD k_build_top = 0x00413DC4u, k_build_after = 0x004140D6u;
static const DWORD k_refresh_top = 0x00415533u, k_refresh_after = 0x004158A4u;
static const DWORD k_state_save = 0x00419100u;

/* 0x4140D0, the build loop's `jl` (edi = the view): slot [esp+0x10], record [esp+0x38];
   its bound is the byte at 0x4140C7 (21, or 30 with Bigger tanks). */
__declspec(naked) static void stub_build_next(void) {
    __asm {
        pushad
        push 0x004140C7
        lea eax, [esp + 0x24 + 0x38]
        push eax
        lea eax, [esp + 0x28 + 0x10]
        push eax
        push edi
        call view_next
        add esp, 16
        test eax, eax
        popad
        jz done
        mov ebp, [esp + 0x38]
        jmp k_build_top
    done:
        jmp k_build_after
    }
}

/* 0x41589E, the refresh loop's `jl`: slot [esp+0x14], record [esp+0x10]; bound at 0x415895. */
__declspec(naked) static void stub_refresh_next(void) {
    __asm {
        pushad
        push 0x00415895
        lea eax, [esp + 0x24 + 0x10]
        push eax
        lea eax, [esp + 0x28 + 0x14]
        push eax
        push edi
        call view_next
        add esp, 16
        test eax, eax
        popad
        jz done
        mov ebp, [esp + 0x10]
        jmp k_refresh_top
    done:
        jmp k_refresh_after
    }
}

/* The state's Save(slot) (thiscall, 0x419100), from its two calls and its vtable slot:
   the animals' file first, then the save as before. */
__declspec(naked) static void stub_state_save(void) {
    __asm {
        pushad
        push dword ptr [esp + 0x24]
        push ecx
        call on_store_save
        add esp, 8
        popad
        jmp k_state_save
    }
}

#define CODE_ADDR(f) ((const void *)(UINT_PTR)(f))
#define TOTAL_SITES 33
static ftfp_site_write writes[TOTAL_SITES];
static int installed = 0;
static int host_ok = 0;

#define JMP(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE9, CODE_ADDR(TO))
#define CALL(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE8, CODE_ADDR(TO))
#define SLOT(W, NAME, TO) ftfp_site_imm32((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0, (unsigned int)(UINT_PTR)(TO))

static const DWORD k_fish_update = 0x0041FE70u;
static const unsigned char TANK_UPDATE_CALL[5] = { 0xE8, 0xC1, 0xE3, 0xFF, 0xFF };   /* 0x421AAA: call 0x41FE70 */

/* 0x421AAA, the tank screen's activation: remember the tank, then the stock update. */
__declspec(naked) static void stub_tank_update(void) {
    __asm {
        mov dword ptr [tank_scene], ecx
        jmp dword ptr [k_fish_update]
    }
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
    JMP(w++, CHEM_USE, stub_chem_use);
    JMP(w++, CHEM_CONFIRM, stub_chem_confirm);
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
    JMP(w++, VIEW_BUILD_NEXT, stub_build_next);
    JMP(w++, VIEW_REFRESH_NEXT, stub_refresh_next);
    CALL(w++, SAVE_CALL_GAME, stub_state_save);
    CALL(w++, SAVE_CALL_SETTINGS, stub_state_save);
    SLOT(w++, STATE_SAVE, stub_state_save);
    ftfp_site_branch(w++, 0x00421AAAu, 5, TANK_UPDATE_CALL, 0xE8, CODE_ADDR(stub_tank_update));
    CALL(w++, SUPPLY_DROP, stub_supply_drop);
    JMP(w++, AUTO_STEP, stub_auto_step);
    JMP(w++, OVERFEED, stub_overfeed);
    CALL(w++, SALE, on_fish_sale);
    CALL(w++, SLOT_TOOLTIP, stub_slot_tooltip);
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

static int log_path(wchar_t *path) {
    DWORD n = GetModuleFileNameW(NULL, path, 1024);
    wchar_t *slash;
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return 0;
    slash[1] = L'\0';
    if (wcslen(path) + 64 >= 1024) return 0;
    wcscat_s(path, 1024, L"Fish Tycoon Fix Patcher DLLs\\DS Store Items.log");
    return 1;
}

/* One more line in the log (what happened to a save's animals). */
static void log_line(const char *text) {
    wchar_t path[1024];
    HANDLE file;
    DWORD written;
    if (!log_path(path)) return;
    file = CreateFileW(path, FILE_APPEND_DATA, FILE_SHARE_READ, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, text, (DWORD)strlen(text), &written, NULL);
    WriteFile(file, "\r\n", 2, &written, NULL);
    CloseHandle(file);
}

static int append_decimal(char *out, int at, int value) {
    char digits[12];
    int d = 0;
    unsigned int v = (unsigned int)value;
    do { digits[d++] = (char)('0' + v % 10); v /= 10; } while (v && d < 11);
    while (d && at < 230) out[at++] = digits[--d];
    return at;
}

/* "<before><slot>: <count><after>" (no count when it is -1). */
static void log_slot(const char *before, int slot, int count, const char *after) {
    char line[240];
    int at = 0;
    while (*before && at < 200) line[at++] = *before++;
    at = append_decimal(line, at, slot);
    if (count >= 0) {
        line[at++] = ':';
        line[at++] = ' ';
        at = append_decimal(line, at, count);
    }
    while (*after && at < 238) line[at++] = *after++;
    line[at] = '\0';
    log_line(line);
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
                          ? "DS Store: installed (all sites); Exotic Eggs and the store chemicals use universal supply slots\r\n"
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
   at 0x43F593 `jmp 0x43F5DE`.  Exotic Eggs (item 28) join the eggs there and
   the Radioactive Growth Hormone, the Revival Potion and ClonaFish (items
   29-31) the chemicals, so they work from
   any of slots 2-4.  Only written when that payload is in the executable; edx
   holds the item, the chemicals branch is 0x43F5A2 and the eggs' 0x43F5AC. */
static const unsigned char USE_GATE_EXPECT[5] = { 0xE9, 0x46, 0x00, 0x00, 0x00 };
static const DWORD k_use_chemicals = 0x0043F5A2u, k_use_eggs = 0x0043F5ACu, k_use_other = 0x0043F5DEu;
static ftfp_site_write use_gate[1];

__declspec(naked) static void stub_use_gate(void) {
    __asm {
        cmp edx, EXOTIC_ITEM
        je eggs
        cmp edx, RGH_ITEM
        jb other
        cmp edx, CLONA_ITEM
        jbe chemicals
    other:
        jmp k_use_other
    eggs:
        jmp k_use_eggs
    chemicals:
        jmp k_use_chemicals
    }
}

static void install_use_gate(void) {
    if (!universal_slots()) return;
    ftfp_site_branch(use_gate, 0x0043F593u, 5, USE_GATE_EXPECT, 0xE9, CODE_ADDR(stub_use_gate));
    exotic_any_slot = ftfp_install_sites(use_gate, 1);
}

EXTERN_C IMAGE_DOS_HEADER __ImageBase;

/* Free upgrades' file, or Everything is Free's (which implies it). */
static __declspec(noinline) int free_setting(void) {
    return ftfp_setting_on((HMODULE)&__ImageBase, L"Free Upgrades.ini")
           || ftfp_everything_free((HMODULE)&__ImageBase);
}

/* Called once by DS Exclusive Fish.dll, after its own install, before WinMain. */
int __stdcall FtfpStoreStartup(const ftfp_store_host *host) {
    if (installed) return 1;
    __try {
        host_ok = name_sprites(host);
        warp_on = tw_enabled((HMODULE)&__ImageBase);
        money_on = ftfp_setting_on((HMODULE)&__ImageBase, L"Add Money.ini");
        free_on = free_setting();
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

/* For "Extra Tanks.dll" (which moves a tank's animals with its block) and
   "Tank Counts.dll" (which counts them): the 5 animal records of the tank in
   stock place `tank` (0 Tank 1's place, 1 Tank 2, 2 the Sale Tank), one after
   the other, ANIMAL_SLOTS * 0x288 bytes; NULL for any other tank or when the
   DLL is not installed. */
char *__stdcall FtfpStoreAnimals(char *state, int tank) {
    if (!installed || state == NULL || tank < 0 || tank >= ANIMAL_TANKS) return NULL;
    return animal(state, tank, 0);
}

/* The animal record a swimming entry's (tank, slot) stands for, or NULL when
   the slot is a fish slot or no animal's. */
char *__stdcall FtfpStoreAnimalRecord(char *state, int tank, int slot) {
    int k;
    if (!installed || state == NULL || tank < 0 || tank >= ANIMAL_TANKS) return NULL;
    k = animal_index(state, tank, slot);
    return k >= 0 ? animal(state, tank, k) : NULL;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
