/* Store Upgrades and Items -- the store's Upgrades view in PC Plant Tycoon.

   WHAT.  An "Upgrades" link on the teal bricks at the left of the store opens
   a second view of the store that shows only the new items, each where it
   would sit in the stock store:
     * Legendary Seeds (lower right, the seed shelves): three a day, $5000
       each, any foliage with one of the 14 new flowers (genes 24-37, from
       "Unused Flowers.dll", which loads this DLL).  The stock packets keep
       their stock rolls; only these can grow the new flowers.  Their art is
       each foliage's Extinct seed recoloured prismatic.
     * Radioactive Plant Formula (upper right, the chemicals): chemical 36,
       3 doses, $10000.  On a plant: full health, every dead branch alive
       again, the largest size, as many flowers as the plant can hold,
       grown to full bloom, and a pollinated plant's full 5 seeds.
     * seeds bred from the new flowers (self-pollinated or crossed) get the
       Legendary seed art too.
     * the Fourth, Fifth and Sixth Seed Box (upper left, the seed-box column
       of the tool upgrades), when "Extra Seed Boxes.dll" is beside this DLL;
       that DLL holds the boxes, this one sells them through the stock dialog;
     * with their settings ("<name>.ini" beside this DLL): the Time Warp
       clock and Add Money ($950 for +$1,000); with Free upgrades every item
       on this view costs $0 (the stock store keeps its prices).
   The link is hidden on the Upgrades view; the bottom bar's "Supplies" plate
   leads back.  docs/plant-tycoon-upgrades-design.md has every address.

   HOW.  FtfpUpgradesStartup() (called by the New Flowers DLL before WinMain)
   writes every site in upgrade_sites.h -- all of them or none -- after
   checking each holds exactly its vanilla bytes.  The seed and chemical
   sheet records are pointed at this mod's taller copies of the stock sheets
   (the stock files are never changed), so every stock draw site shows the
   new seeds and bottle with no code hook.

   STATE.  The three Legendary packets on sale are kept per slot in
   "<save folder>\Plant Tycoon Fix Patcher Data\Plant Upgrades <slot>.dat";
   bought seeds and formula doses live in the stock seed and chemical trays,
   so the save keeps its stock layout. */
#include <windows.h>
#include <string.h>
#include <stdio.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "upgrade_sites.h"
#include "../common/time_warp_popup.h"

#define FOLIAGES 23
#define FIRST_NEW_FLOWER 24
#define NEW_FLOWERS 14
#define LEGENDARY_COUNT 3
#define LEGENDARY_PRICE 5000
#define LEGENDARY_TRASH 10
#define LEGENDARY_FRAME_BASE 95             /* frame 95 + foliage on the taller seed sheet */
#define FIRST_LEGENDARY_INDEX 52            /* purchase-dialog indices 52..54 */
#define FORMULA_ID 36                       /* chemical id = purchase-dialog index */
#define FORMULA_PRICE 10000
#define FORMULA_DOSES 3
#define FORMULA_NAME_ID 0x1F0               /* a string id above the game's last (0x1B2) */
#define POT_SEEDS_HELD_BACK 0x7C            /* see on_pollinated */
#define LINK_SPRITE 0x8B                    /* the one sprite id the game leaves free */
#define EXTRA_BOXES 3
#define BOX_PRICE 1000
#define BOX_TITLE_ID 0x1F1                  /* 0x1F1..0x1F3 the box names, 0x1F4 their description */
#define BOX_DESC_ID 0x1F4

/* Free upgrades ("Free Upgrades.ini" beside this DLL): every item on the
   Upgrades view costs $0.  The stock store keeps its prices. */
static volatile unsigned char free_upgrades = 0;
static int price(int normal) { return free_upgrades ? 0 : normal; }

#define SHEET_SEEDS 0x2E
#define SHEET_SHADOW 0xB0
#define SHEET_TOOLS 0xB2
#define SHEET_CHEMICALS 0xB3
#define SHEET_TICK 0x25
#define SOUND_BUTTON 0xC

/* ---------------------------------------------------------------- the game */

typedef int (__cdecl *random_fn)(int bound);
typedef void *(__cdecl *new_fn)(unsigned int size);
typedef void (__fastcall *sprite_fn)(void *mgr, int edx, int sheet, int frame, int x, int y, float scale, int alpha, int flag);
typedef void (__fastcall *shadow_fn)(void *mgr, int edx, int sheet, int x, int y, float scale, int alpha);
typedef void (__fastcall *dialog_ctor_fn)(void *dlg, int edx, int index);
typedef void (__fastcall *dialog_run_fn)(void *dlg, int edx, void *parent, int zero);
typedef void (__fastcall *dialog_dtor_fn)(void *dlg, int edx);
typedef void (__fastcall *tooltip_ctor_fn)(void *tip, int edx, int id, const RECT *rect, void *parent,
                                           const char *text, int colour, int font, int extra);
typedef void (__fastcall *tooltip_text_fn)(void *tip, int edx, const char *text, int colour, int font, int extra);
typedef void (__fastcall *add_control_fn)(void *scene, int edx, void *control);
typedef void (__fastcall *sound_fn)(void *sound, int edx, int id);
typedef void (__fastcall *cash_fn)(void *state, int edx, int delta);
typedef int (__fastcall *tray_slot_fn)(void *dlg, int edx);
typedef void (__fastcall *add_flowers_fn)(void *plant, int edx, int a, int b);

static const random_fn game_random = (random_fn)0x004033B0u;
static const new_fn game_new = (new_fn)0x0044E894u;
static const sprite_fn draw_sprite = (sprite_fn)0x004208F0u;
static const shadow_fn draw_shadow = (shadow_fn)0x004207F0u;
static const dialog_ctor_fn dialog_ctor = (dialog_ctor_fn)0x00432E90u;
static const dialog_run_fn dialog_run = (dialog_run_fn)0x00401C90u;
static const dialog_dtor_fn dialog_dtor = (dialog_dtor_fn)0x004307A0u;
static const tooltip_ctor_fn tooltip_ctor = (tooltip_ctor_fn)0x00409870u;
static const tooltip_text_fn tooltip_text = (tooltip_text_fn)0x00409AA0u;
static const add_control_fn add_control = (add_control_fn)0x0040B400u;
static const sound_fn play_sound = (sound_fn)0x0044A580u;
static const cash_fn add_cash = (cash_fn)0x0041ED70u;
static const tray_slot_fn free_tray_slot = (tray_slot_fn)0x00430900u;
#define TOOLTIP_FONT (*(int *)0x0048EB3Cu)
#define TOOLTIP_COLOUR (*(int *)0x00493CA0u)

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))
#define SCENE_STATE(scene) AT(scene, 0x1BC, char *)
#define SCENE_SPRITES(scene) AT(scene, 0x1C0, void *)
#define SCENE_SOUND(scene) AT(scene, 0x1C4, void *)
#define SCENE_TOOLTIP(scene, slot) AT(scene, 0x10 + (slot) * 4, char *)

/* --------------------------------------------------------- legendary seeds */

/* A seed record, the stock layout (shop shelves, seed tray, seed box). */
typedef struct seed_record {
    int parent[4];
    int foliage, flower;
    int present;            /* low byte */
    int frame;
    int trash;
} seed_record;

static seed_record legendary[LEGENDARY_COUNT];

static void roll_legendary(const char *state) {
    int i, k;
    for (i = 0; i < LEGENDARY_COUNT; ++i) {
        seed_record *s = &legendary[i];
        const seed_record *stock = (const seed_record *)(state + 0x5A4);    /* the first stock packet */
        for (k = 0; k < 4; ++k) s->parent[k] = stock->parent[k];
        s->foliage = game_random(FOLIAGES) + 1;
        s->flower = game_random(NEW_FLOWERS) + FIRST_NEW_FLOWER;
        s->present = 1;
        s->frame = LEGENDARY_FRAME_BASE + s->foliage;
        s->trash = LEGENDARY_TRASH;
    }
}

static void __cdecl on_roll(const char *state) { roll_legendary(state); }

static int __cdecl legendary_frame(int index) {
    int i = index - FIRST_LEGENDARY_INDEX;
    return (i >= 0 && i < LEGENDARY_COUNT) ? legendary[i].frame : 0;
}

/* The purchase: the packet goes to the first free seed-tray slot. */
static void __cdecl buy_legendary(char *dlg) {
    int i = AT(dlg, 0xB8, int) - FIRST_LEGENDARY_INDEX;
    char *state = AT(dlg, 0x74, char *);
    int slot;
    if (i < 0 || i >= LEGENDARY_COUNT || !(legendary[i].present & 0xFF)) return;
    slot = free_tray_slot(dlg, 0);
    if (slot < 0) return;
    memcpy(state + 0x52B88 + slot * 0x24, &legendary[i], sizeof legendary[i]);
    legendary[i].present = 0;
    add_cash(state, 0, -AT(dlg, 0x84, int));
}

/* ----------------------------------------------------------------- formula */

/* Set while the formula flowers a plant: every flower spot counts as free,
   even on a joint a branch grows from (stub_joint_free). */
static volatile unsigned char formula_flowering = 0;

/* A plant family's shape table: 0xF4-byte part definitions ending with id -1.
   +0x14/+0x18/+0x1C/+0x20 the part's box in its sheet, +0xA8 its flower spot
   count, +0xAC + i*12 the spots (x, y, flags).  Every definition has room for
   6; the empty ones past the count get spots on the part's own visible pixels
   (FORMULA_SPOTS, from the art).  The game reads a flower's spot by index
   without checking the count, so these draw everywhere, and only the formula
   raises the counts to reach them. */
#define DEF_STRIDE 0xF4
#define DEF_MAX 80
#define SPOTS 6

static void add_spots(void) {
    int k;
    for (k = 0; k < FORMULA_SPOT_COUNT; ++k) {
        int *spot = (int *)(UINT_PTR)FORMULA_SPOTS[k].at;
        if (spot[0] || spot[1] || spot[2]) continue;
        spot[0] = FORMULA_SPOTS[k].x;
        spot[1] = FORMULA_SPOTS[k].y;
    }
}

/* How many of a definition's spots, from the first, are in place. */
static int filled_spots(const char *def) {
    int i = 0;
    while (i < SPOTS && (AT(def, 0xAC + i * 12, int) || AT(def, 0xB0 + i * 12, int) || AT(def, 0xB4 + i * 12, int)))
        ++i;
    return i;
}

/* At start-up, before any save is drawn: every family's tables writable (the
   formula raises their counts for a moment) and their spots in place, so the
   formula's flowers draw where they grew after a restart too. */
static int shapes_ready = 0;

static void prepare_shapes(void) {
    int t;
    for (t = 0; t < SHAPE_TABLE_COUNT; ++t) {
        char *table = (char *)(UINT_PTR)SHAPE_TABLES[t];
        DWORD old;
        int n = 0;
        while (n < DEF_MAX && AT(table, n * DEF_STRIDE, int) != -1) ++n;
        if (!VirtualProtect(table, (SIZE_T)n * DEF_STRIDE, PAGE_READWRITE, &old)) return;
    }
    add_spots();
    shapes_ready = 1;
}

static int known_table(const char *table) {
    int t;
    for (t = 0; t < SHAPE_TABLE_COUNT; ++t)
        if ((UINT_PTR)table == SHAPE_TABLES[t]) return 1;
    return 0;
}

/* add_flowers with every part's spot count raised to its spots in place
   (restored afterwards). */
static void flower_everything(char *plant) {
    add_flowers_fn add_flowers = (add_flowers_fn)AT(AT(plant, 0, char *), 0x44, void *);
    char *table = AT(plant, 4, char *);
    int saved[DEF_MAX], n = 0;
    if (shapes_ready && known_table(table))             /* else the plant's own spots only */
    for (n = 0; n < DEF_MAX && AT(table, n * DEF_STRIDE, int) != -1; ++n) {
        char *def = table + n * DEF_STRIDE;
        int filled = filled_spots(def);
        saved[n] = AT(def, 0xA8, int);
        if (filled > saved[n]) AT(def, 0xA8, int) = filled;
    }
    formula_flowering = 1;
    add_flowers(plant, 0, 360, 0);
    formula_flowering = 0;
    while (n-- > 0) AT(table + n * DEF_STRIDE, 0xA8, int) = saved[n];
}

/* Full health, every branch alive (dead ones, and the ones the plant's shape
   hides), largest size, a flower on every spot of every branch, grown to full
   bloom.  The dose is already used (stock order). */
static void __cdecl apply_formula(char *greenhouse, int col, int row, char *plant) {
    char *state = AT(greenhouse, 0x68, char *);
    char *pot = state + 0x2188 + (row * 5 + col) * 0x5600;
    int k;
    if (AT(pot, 0x24, int) <= 0) return;                 /* a dead plant stays dead, as with the stock cures */
    AT(pot, 0x24, int) = 100;
    for (k = 0; k < 60; ++k) {
        int *type = &AT(pot, 0xA8 + k * 0x16C + 4, int);
        if (*type == 0) break;
        if (*type == 2 || *type == 4) *type = 1;          /* hidden or dead: alive (cut ones stay cut) */
    }
    AT(pot, 0x80, int) = 110;
    AT(pot, 0x9C, int) = 1;                              /* skip the age-7 roll that kills branches */
    if (plant != NULL && AT(plant, 4, void *) != NULL) {
        flower_everything(plant);
        AT(pot, 0x8C, int) = 100;
    }
    if (AT(pot, 0x10, float) < 28.0f && AT(pot, 0x14, float) < 28.0f) AT(pot, 0x14, float) = 28.0f;
    if (AT(pot, 0x6C, unsigned char)) {                  /* pollinated: all 5 seeds */
        int used = AT(pot, 0x94, int) - AT(pot, POT_SEEDS_HELD_BACK, int);
        AT(pot, 0x94, int) = used < 0 ? 0 : used;
        AT(pot, POT_SEEDS_HELD_BACK, int) = 0;
    }
}

/* After a pot's pollination (0x4240A0's tail, hooked by "Unused Flowers.dll"):
   * a seed with one of the new flowers gets its Legendary (prismatic) art;
   * the seeds the game held back (it gives 5, 4 or 3, or 1 if the plant is
     infested, by counting 0-2 or 4 seeds as used) are kept in +0x7C, the
     record's "seed bonus" that no stock code writes, so the formula can give
     them back.  The stock count subtracted +0x7C, so it is added back first. */
static void __cdecl on_pollinated(char *pot) {
    int held_back = AT(pot, 0x94, int);
    if (held_back != 4) held_back += AT(pot, POT_SEEDS_HELD_BACK, int);
    AT(pot, 0x94, int) = held_back;
    AT(pot, POT_SEEDS_HELD_BACK, int) = held_back;
    if (AT(pot, 0x68, int) >= FIRST_NEW_FLOWER && AT(pot, 0x64, int) >= 1 && AT(pot, 0x64, int) <= FOLIAGES) {
        AT(pot, 0x70, int) = LEGENDARY_FRAME_BASE + AT(pot, 0x64, int);
        AT(pot, 0x74, int) = LEGENDARY_TRASH;
    }
}

/* ------------------------------------------------------------- seed boxes */

/* "Extra Seed Boxes.dll": the boxes themselves, and its save events. */
typedef struct ftfp_box_events {
    int version;
    void (__cdecl *save)(char *state, int slot);
    void (__cdecl *load)(const char *state, int slot);
    void (__cdecl *remove)(int slot);
    void (__cdecl *new_game)(void);
    int (__cdecl *owned)(int box);
    void (__cdecl *set_owned)(int box, int value);
} ftfp_box_events;
typedef const ftfp_box_events *(__stdcall *boxes_startup_fn)(void);

static const ftfp_box_events *boxes = NULL;

/* The stock store sells the seed box's drawers as tool upgrades 4, 9 and 14
   (dialog indices 14, 19, 24).  While a Fourth/Fifth/Sixth box's dialog is
   open, those three records describe the new boxes instead, so the stock
   dialog does all of it: the price, "You already have this item!", "You need
   the previous upgrade first!", can't afford, and the purchase. */
#define TOOL_RECORD(state, k) ((state) + 0x6E8 + (k) * 0x20)

/* ----------------------------------------------------------------- strings */

static const char LEGENDARY_TITLE[] = "Legendary Seeds\n";
static const char LEGENDARY_DESC[] =
    "These ultra-rare seeds were only recently\nrediscovered on Isola and require the\nbest of care to survive.";
static const char FORMULA_TITLE[] = "Radioactive Plant Formula\n";
static const char FORMULA_DESC[] =
    "Causes maximum flower and plant growth\nand restores full health to plants.\nNo more dead leaves!\nContains 3 doses.\n";
static const char FORMULA_NAME[] = "Radioactive Plant Formula";
static const char BOX_TITLE_4[] = "Fourth Seed Box";
static const char BOX_TITLE_5[] = "Fifth Seed Box";
static const char BOX_TITLE_6[] = "Sixth Seed Box";
static const char BOX_DESC[] = "Even more space for your seeds!";
static const char *const BOX_TITLES[EXTRA_BOXES] = { BOX_TITLE_4, BOX_TITLE_5, BOX_TITLE_6 };

static volatile unsigned char building_legendary = 0;     /* a Legendary dialog is being built */
static volatile unsigned char building_formula = 0;       /* a formula dialog is being built */

/* ------------------------------------------------------------- store view */

static int upgrades_view = 0;
static int link_hover = 0;
static int hover_x = -1, hover_y = -1;
#define TIP_FORMULA LEGENDARY_COUNT
#define TIP_BOXES (LEGENDARY_COUNT + 1)
#define TIPS (TIP_BOXES + EXTRA_BOXES)
static char *tips[TIPS];
static char tip_text[TIPS][64];

#define LINK_X 128                 /* the link's frame is 64 x 17, centred at (160, 281) on the bricks */
#define LINK_Y 273
#define LINK_W 64
#define LINK_H 17
static const RECT PLATE = { 462, 540, 574, 600 };     /* the bottom bar's "Supplies" plate */

static int inside(const RECT *r, int x, int y) { return x >= r->left && x <= r->right && y >= r->top && y <= r->bottom; }

static RECT seed_rect(int i) { RECT r = { 598 + 60 * i, 290, 648 + 60 * i, 355 }; return r; }
static const RECT FORMULA_RECT = { 610, 63, 655, 115 };
static const RECT LINK_RECT = { LINK_X - 2, LINK_Y - 2, LINK_X + LINK_W + 2, LINK_Y + LINK_H + 2 };
static RECT box_rect(int box) { RECT r = { 471, 52 + 70 * box, 528, 113 + 70 * box }; return r; }

/* ------------------------------------------------------------ time warp */

/* The Time Warp setting ships "Time Warp.ini" beside this DLL.  The item sits
   on the Upgrades view's empty Nursery shelf; its picture is frame 20 (row 10)
   of the chemicals sheet this DLL already extends.  Clicking it asks for the
   hours in a Windows popup, confirms, charges $500 and moves every live pot's
   time stamp back that far, then runs the game's own plant update (0x41D810,
   the call the Options screen makes), exactly as if the player had been away:
   the catch-up has no cap.  The seed shop's restock time (state+0x5A0) and
   the Sundial's start (state+0x30) move back too.  Once the update has run,
   an OK box says the hours, age units and price. */
#define WARP_PRICE 500
#define WARP_FRAME 20
#define WARP_X 300
#define WARP_Y 296
#define S_CASH 0x217C
#define S_SPEED 0x534
#define S_RESTOCK 0x5A0
#define S_STARTED 0x30
#define POTS 15
#define POT(state, k) ((state) + 0x2188 + (k) * 0x5600)
typedef unsigned int (__cdecl *mono_clock_fn)(void);
typedef void (__fastcall *plants_update_fn)(void *state, int edx);
static const mono_clock_fn mono_clock = (mono_clock_fn)0x00403430u;
static const plants_update_fn update_plants = (plants_update_fn)0x0041D810u;
static const RECT WARP_RECT = { WARP_X, WARP_Y, WARP_X + 64, WARP_Y + 64 };
static int warp_on = 0;
static char *warp_tip = NULL;
static char warp_tip_text[64];

static void time_warp(char *scene) {
    char *state = SCENE_STATE(scene);
    wchar_t text[256];
    unsigned int now, dt;
    int hours, k, cost = price(WARP_PRICE);
    if (state == NULL) return;
    if (AT(state, S_SPEED, int) > 100) {
        tw_tell(L"Time is stopped. Turn time back on in Options, then warp.");
        return;
    }
    if (AT(state, S_CASH, unsigned int) < (unsigned int)cost) {        /* the game's cash is unsigned (0x430D13) */
        tw_tell(L"You can't afford to buy this yet! A Time Warp costs $500.");
        return;
    }
    swprintf_s(text, 256, L"Costs $%d. Your plants grow, ripen seeds and need water, and the seed shop "
               L"restocks if due, as if you had been away.", cost);
    hours = tw_ask_hours(text);
    if (hours <= 0) return;
    swprintf_s(text, 256, L"Warp %d hour%s for $%d?\n\nYour plants will age %d hour%s, as if you had been "
               L"away that long. This cannot be undone.", hours, hours == 1 ? L"" : L"s", cost, hours,
               hours == 1 ? L"" : L"s");
    if (!tw_confirm(text)) return;
    if (AT(state, S_CASH, unsigned int) < (unsigned int)cost) return;
    add_cash(state, 0, -cost);
    play_sound(SCENE_SOUND(scene), 0, SOUND_BUTTON);
    now = mono_clock();
    dt = (unsigned int)hours * 3600u;
    for (k = 0; k < POTS; ++k) {
        char *pot = POT(state, k);
        unsigned int stamp = AT(pot, 0x04, unsigned int);
        if (AT(pot, 0x4C, int) == 0 || stamp == 0 || AT(pot, 0x24, int) <= 0) continue;
        if (stamp > now) stamp = now;                  /* a fresh seed's stamp is a second ahead */
        AT(pot, 0x04, unsigned int) = stamp - dt;
    }
    {   /* "Extra Greenhouses.dll" (its own setting): the same for its pots. */
        typedef void (__cdecl *extra_warp_fn)(unsigned int dt, unsigned int now);
        HMODULE extra = GetModuleHandleW(L"Extra Greenhouses.dll");
        extra_warp_fn extra_warp = extra ? (extra_warp_fn)GetProcAddress(extra, "FtfpExtraGreenhousesWarp") : NULL;
        if (extra_warp != NULL) extra_warp(dt, now);
    }
    AT(state, S_RESTOCK, unsigned int) -= dt;          /* the greenhouse's next 3-s check restocks if due */
    if (AT(state, S_STARTED, unsigned int) > dt) AT(state, S_STARTED, unsigned int) -= dt;
    update_plants(state, 0);
    /* One age unit per 60 x speed seconds, and the catch-up has no cap: every unit of dt was played. */
    tw_done(hours, AT(state, S_SPEED, int) > 0 ? dt / (60u * (unsigned int)AT(state, S_SPEED, int)) : 0,
            L"age unit", cost);
}

/* ------------------------------------------------------------ add money */

/* The Add Money setting ships "Add Money.ini" beside this DLL.  A pile of
   gold coins (frame 22, row 11 of the chemicals sheet) sits beside the Time
   Warp clock: $950, or $0 with Free upgrades, then +$1,000, any number of
   times.  Both go through the game's own cash function (0x41ED70), which
   keeps the cash between $0 and $4,000,000,000 (the double at 0x467F78). */
#define MONEY_PRICE 950
#define MONEY_GAIN 1000
#define MONEY_FRAME 22
#define MONEY_X 370
#define MONEY_Y 296
static const RECT MONEY_RECT = { MONEY_X, MONEY_Y, MONEY_X + 64, MONEY_Y + 64 };
static int money_on = 0;
static char *money_tip = NULL;
static char money_tip_text[64];

static void add_money(char *scene) {
    char *state = SCENE_STATE(scene);
    wchar_t text[128];
    int cost = price(MONEY_PRICE);
    if (state == NULL) return;
    if (AT(state, S_CASH, unsigned int) < (unsigned int)cost) {
        tw_tell_as(L"Add $1,000", L"You can't afford to buy this yet! +$1,000 costs $950.");
        return;
    }
    swprintf_s(text, 128, L"Buy +$1,000 for $%d?", cost);
    if (!tw_confirm_as(L"Add $1,000", text)) return;
    if (AT(state, S_CASH, unsigned int) < (unsigned int)cost) return;
    add_cash(state, 0, -cost);
    add_cash(state, 0, MONEY_GAIN);
    play_sound(SCENE_SOUND(scene), 0, SOUND_BUTTON);
}

/* ------------------------------------------- extra greenhouses and nurseries */

/* "Extra Greenhouses.dll" (the 5 extra greenhouses and 5 extra nurseries
   settings) sells Greenhouses 2-6 and Nurseries 2-6 here: two items, each
   bought in order like the Fourth-Sixth Seed Box, $10,000 each ($0 with Free
   upgrades), through the same Yes / No as Add Money, with the stock tick once
   all five are owned.  The greenhouse stands on the tool shelf beside the seed
   boxes, drawn with the game's own greenhouse picture (greenhouse1.png, sprite
   0xC2); the nursery on the Nursery shelf beside Add Money, drawn with the
   game's own golden pot (goldpot.png, sprite 0x2C, the nursery's display).
   An item shows only while its setting is on (its Owned export says -1 when
   it is off). */
#define EXTRA_PRICE 10000
#define EXTRA_COUNT 5
#define EXTRA_ITEMS 2
typedef int (__cdecl *extra_fn)(void);

typedef struct extra_item {
    const char *title;
    const wchar_t *caption, *all_owned, *too_poor, *confirm;
    const char *owned_export, *buy_export;
    int sprite, x, y;
    float scale;
    RECT rect;
} extra_item;

static const extra_item EXTRA_ITEM[EXTRA_ITEMS] = {
    { "Extra Greenhouse", L"Extra Greenhouse", L"You already have all five extra greenhouses!",
      L"You can't afford to buy this yet! An extra greenhouse costs $10,000.",
      L"Buy Greenhouse %d for $%d?\n\nIt has 15 empty pots. The arrows on the greenhouse screen lead to it.",
      "FtfpExtraGreenhousesOwned", "FtfpExtraGreenhousesBuy", 0xC2, 404, 50, 0.29f, { 404, 52, 461, 113 } },
    { "Extra Nursery", L"Extra Nursery", L"You already have all five extra nurseries!",
      L"You can't afford to buy this yet! An extra nursery costs $10,000.",
      L"Buy Nursery %d for $%d?\n\nIt holds 15 more plants for sale. The arrows on the nursery screen lead to it.",
      "FtfpExtraNurseriesOwned", "FtfpExtraNurseriesBuy", 0x2C, 440, 296, 0.84f, { 440, 296, 504, 360 } },
};
static extra_fn extra_owned[EXTRA_ITEMS], extra_buy[EXTRA_ITEMS];
static char *extra_tip[EXTRA_ITEMS];
static char extra_tip_text[EXTRA_ITEMS][64];

static int extra_on(int i) { return extra_owned[i] != NULL && extra_owned[i]() >= 0; }

static void extra_tip_set(int i) {
    int owned = extra_owned[i]();
    if (owned >= EXTRA_COUNT) sprintf_s(extra_tip_text[i], 64, "%s\nSold out", EXTRA_ITEM[i].title);
    else sprintf_s(extra_tip_text[i], 64, "%s %i of %i\nPrice: $ %i", EXTRA_ITEM[i].title, owned + 1, EXTRA_COUNT,
                   price(EXTRA_PRICE));
}

static void buy_extra(char *scene, int i) {
    char *state = SCENE_STATE(scene);
    wchar_t text[256];
    int owned, cost = price(EXTRA_PRICE);
    if (state == NULL || !extra_on(i)) return;
    owned = extra_owned[i]();
    if (owned >= EXTRA_COUNT) {
        tw_tell_as(EXTRA_ITEM[i].caption, EXTRA_ITEM[i].all_owned);
        return;
    }
    if (AT(state, S_CASH, unsigned int) < (unsigned int)cost) {
        tw_tell_as(EXTRA_ITEM[i].caption, EXTRA_ITEM[i].too_poor);
        return;
    }
    swprintf_s(text, 256, EXTRA_ITEM[i].confirm, owned + 2, cost);
    if (!tw_confirm_as(EXTRA_ITEM[i].caption, text)) return;
    if (AT(state, S_CASH, unsigned int) < (unsigned int)cost || extra_owned[i]() != owned) return;
    add_cash(state, 0, -cost);
    extra_buy[i]();
    play_sound(SCENE_SOUND(scene), 0, SOUND_BUTTON);
    extra_tip_set(i);
    if (extra_tip[i] != NULL) tooltip_text(extra_tip[i], 0, extra_tip_text[i], TOOLTIP_COLOUR, 0, 0);
}

static void load_extras(void) {
    HMODULE module = GetModuleHandleW(L"Extra Greenhouses.dll");
    int i;
    if (module == NULL) return;
    for (i = 0; i < EXTRA_ITEMS; ++i) {
        extra_fn owned = (extra_fn)GetProcAddress(module, EXTRA_ITEM[i].owned_export);
        extra_fn buy = (extra_fn)GetProcAddress(module, EXTRA_ITEM[i].buy_export);
        if (owned != NULL && buy != NULL) {
            extra_owned[i] = owned;
            extra_buy[i] = buy;
        }
    }
}

static void box_tip_text(int box) {
    if (boxes != NULL && boxes->owned(box)) sprintf_s(tip_text[TIP_BOXES + box], 64, "%s", BOX_TITLES[box]);
    else sprintf_s(tip_text[TIP_BOXES + box], 64, "%s\nPrice: $ %i", BOX_TITLES[box], price(BOX_PRICE));
}

static void set_tooltips(char *scene) {
    int slot, i;
    for (slot = 6; slot <= 53; ++slot) {                  /* the stock items' tooltips */
        char *tip = SCENE_TOOLTIP(scene, slot);
        if (tip != NULL) AT(tip, 8, unsigned char) = (unsigned char)!upgrades_view;
    }
    for (i = 0; i < TIPS; ++i) {
        int shown = i < LEGENDARY_COUNT ? (legendary[i].present & 0xFF) : i == TIP_FORMULA ? 1 : boxes != NULL;
        if (tips[i] == NULL) continue;
        if (i >= TIP_BOXES) {
            box_tip_text(i - TIP_BOXES);
            tooltip_text(tips[i], 0, tip_text[i], TOOLTIP_COLOUR, 0, 0);
        }
        AT(tips[i], 8, unsigned char) = (unsigned char)(upgrades_view && shown);
    }
    if (warp_tip != NULL) AT(warp_tip, 8, unsigned char) = (unsigned char)upgrades_view;
    if (money_tip != NULL) AT(money_tip, 8, unsigned char) = (unsigned char)upgrades_view;
    for (i = 0; i < EXTRA_ITEMS; ++i) {
        if (extra_tip[i] == NULL) continue;
        extra_tip_set(i);
        tooltip_text(extra_tip[i], 0, extra_tip_text[i], TOOLTIP_COLOUR, 0, 0);
        AT(extra_tip[i], 8, unsigned char) = (unsigned char)upgrades_view;
    }
}

static char *make_tooltip(char *scene, int id, const RECT *r, const char *text) {
    char *tip = (char *)game_new(0x10);
    if (tip == NULL) return NULL;
    tooltip_ctor(tip, 0, id, r, scene, text, TOOLTIP_FONT, 0, 0);
    add_control(scene, 0, tip);
    return tip;
}

static void make_tooltips(char *scene) {
    int i;
    if (tips[0] != NULL) return;
    for (i = 0; i < TIPS; ++i) {
        RECT r = i < LEGENDARY_COUNT ? seed_rect(i) : i == TIP_FORMULA ? FORMULA_RECT : box_rect(i - TIP_BOXES);
        char *tip = (char *)game_new(0x10);
        if (tip == NULL) return;
        if (i < LEGENDARY_COUNT) sprintf_s(tip_text[i], sizeof tip_text[i], "%sPrice: $ %i", LEGENDARY_TITLE, price(LEGENDARY_PRICE));
        else if (i == TIP_FORMULA) sprintf_s(tip_text[i], sizeof tip_text[i], "%sPrice: $ %i", FORMULA_TITLE, price(FORMULA_PRICE));
        else box_tip_text(i - TIP_BOXES);
        tooltip_ctor(tip, 0, 54 + i, &r, scene, tip_text[i], TOOLTIP_FONT, 0, 0);
        add_control(scene, 0, tip);
        tips[i] = tip;
    }
    if (warp_on && warp_tip == NULL) {
        sprintf_s(warp_tip_text, sizeof warp_tip_text, "Time Warp\nPrice: $ %i", price(WARP_PRICE));
        if ((warp_tip = make_tooltip(scene, 54 + TIPS, &WARP_RECT, warp_tip_text)) == NULL) return;
    }
    if (money_on && money_tip == NULL) {
        sprintf_s(money_tip_text, sizeof money_tip_text, "Add $1,000\nPrice: $ %i", price(MONEY_PRICE));
        money_tip = make_tooltip(scene, 55 + TIPS, &MONEY_RECT, money_tip_text);
    }
    for (i = 0; i < EXTRA_ITEMS; ++i) {
        if (!extra_on(i) || extra_tip[i] != NULL) continue;
        extra_tip_set(i);
        extra_tip[i] = make_tooltip(scene, 56 + TIPS + i, &EXTRA_ITEM[i].rect, extra_tip_text[i]);
    }
}

static void switch_view(char *scene, int on) {
    upgrades_view = on;
    link_hover = 0;
    set_tooltips(scene);
}

/* activate(1) on entering the store, activate(0) on leaving: always the stock view first. */
static void __cdecl on_activate(char *scene, int on) {
    make_tooltips(scene);
    switch_view(scene, 0);
    (void)on;
}

/* Called at the top of the store's item drawing; 1 = the Upgrades view was drawn instead. */
static int __cdecl on_draw(char *scene) {
    void *mgr = SCENE_SPRITES(scene);
    int i;
    if (!upgrades_view) {
        draw_sprite(mgr, 0, LINK_SPRITE, link_hover ? 1 : 0, LINK_X, LINK_Y, 1.0f, 100, 1);
        return 0;
    }
    for (i = 0; i < LEGENDARY_COUNT; ++i) {
        int x = 602 + 57 * i;
        if (!(legendary[i].present & 0xFF)) continue;
        draw_shadow(mgr, 0, SHEET_SHADOW, x + 5, 320, 1.0f, 100);
        draw_sprite(mgr, 0, SHEET_SEEDS, legendary[i].frame, x, 315, 1.0f, 100, 1);
    }
    draw_shadow(mgr, 0, SHEET_SHADOW, 598 + 0x19, 55 + 0x1E, 1.0f, 100);
    draw_sprite(mgr, 0, SHEET_CHEMICALS, 2 * FORMULA_ID - 54, 598, 55, 1.0f, 100, 1);
    for (i = 0; boxes != NULL && i < EXTRA_BOXES; ++i) {      /* where the stock store draws its seed boxes */
        int x = 233 + 57 * 4, y = 50 + 61 * i;
        draw_shadow(mgr, 0, SHEET_SHADOW, x + 0x19, y + 0x1E, 1.0f, 100);
        draw_sprite(mgr, 0, SHEET_TOOLS, i * 5 + 4, x, y, 1.0f, 100, 1);
        if (boxes->owned(i)) draw_shadow(mgr, 0, SHEET_TICK, x + 19, y + 22, 1.0f, 100);
    }
    if (warp_on) {
        draw_shadow(mgr, 0, SHEET_SHADOW, WARP_X + 0x19, WARP_Y + 0x1E, 1.0f, 100);
        draw_sprite(mgr, 0, SHEET_CHEMICALS, WARP_FRAME, WARP_X, WARP_Y, 1.0f, 100, 1);
    }
    if (money_on) {
        draw_shadow(mgr, 0, SHEET_SHADOW, MONEY_X + 0x19, MONEY_Y + 0x1E, 1.0f, 100);
        draw_sprite(mgr, 0, SHEET_CHEMICALS, MONEY_FRAME, MONEY_X, MONEY_Y, 1.0f, 100, 1);
    }
    for (i = 0; i < EXTRA_ITEMS; ++i) {
        const extra_item *it = &EXTRA_ITEM[i];
        if (!extra_on(i)) continue;
        draw_shadow(mgr, 0, SHEET_SHADOW, it->x + 0x19, it->y + 0x1E, 1.0f, 100);
        draw_sprite(mgr, 0, it->sprite, 0, it->x + 6, it->y, it->scale, 100, 1);
        if (extra_owned[i]() >= EXTRA_COUNT) draw_shadow(mgr, 0, SHEET_TICK, it->x + 19, it->y + 22, 1.0f, 100);
    }
    return 1;
}

static void open_dialog(char *scene, int index) {
    __declspec(align(16)) unsigned char dlg[0x400];
    memset(dlg, 0, sizeof dlg);
    dialog_ctor(dlg, 0, index);
    dialog_run(dlg, 0, scene, 0);
    dialog_dtor(dlg, 0);
    set_tooltips(scene);                                  /* a bought packet's tooltip goes */
}

static void open_box_dialog(char *scene, int box) {
    char *state = SCENE_STATE(scene);
    unsigned char stock[EXTRA_BOXES][0x20];
    int i;
    for (i = 0; i < EXTRA_BOXES; ++i) {
        char *record = TOOL_RECORD(state, 4 + 5 * i);
        memcpy(stock[i], record, 0x20);
        AT(record, 0x00, int) = price(BOX_PRICE);
        AT(record, 0x04, unsigned char) = (unsigned char)boxes->owned(i);
        AT(record, 0x0C, int) = BOX_DESC_ID;
        AT(record, 0x10, int) = BOX_TITLE_ID + i;
    }
    open_dialog(scene, 14 + 5 * box);
    for (i = 0; i < EXTRA_BOXES; ++i) {
        char *record = TOOL_RECORD(state, 4 + 5 * i);
        boxes->set_owned(i, AT(record, 0x04, unsigned char));
        memcpy(record, stock[i], 0x20);
    }
    set_tooltips(scene);
}

/* Button-down in the store; 1 = handled here (the stock item loops are skipped). */
static int __cdecl on_click(char *scene, int x, int y) {
    int i;
    if (!upgrades_view) {
        if (!inside(&LINK_RECT, x, y)) return 0;
        play_sound(SCENE_SOUND(scene), 0, SOUND_BUTTON);
        switch_view(scene, 1);
        return 1;
    }
    if (inside(&PLATE, x, y)) {
        play_sound(SCENE_SOUND(scene), 0, SOUND_BUTTON);
        switch_view(scene, 0);
        return 1;
    }
    for (i = 0; i < LEGENDARY_COUNT; ++i) {
        RECT r = seed_rect(i);
        if (inside(&r, x, y) && (legendary[i].present & 0xFF)) {
            open_dialog(scene, FIRST_LEGENDARY_INDEX + i);
            return 1;
        }
    }
    if (inside(&FORMULA_RECT, x, y)) open_dialog(scene, FORMULA_ID);
    for (i = 0; boxes != NULL && i < EXTRA_BOXES; ++i) {
        RECT r = box_rect(i);
        if (inside(&r, x, y)) open_box_dialog(scene, i);
    }
    if (warp_on && inside(&WARP_RECT, x, y)) time_warp(scene);
    if (money_on && inside(&MONEY_RECT, x, y)) add_money(scene);
    for (i = 0; i < EXTRA_ITEMS; ++i) {
        if (extra_on(i) && inside(&EXTRA_ITEM[i].rect, x, y)) buy_extra(scene, i);
    }
    return 1;
}

static void __cdecl on_hover(int x, int y) {
    hover_x = x;
    hover_y = y;
    link_hover = !upgrades_view && inside(&LINK_RECT, x, y);
}

/* ----------------------------------------------------------------- sidecar */

#define SIDECAR_MAGIC 0x50555050u      /* "PPUP" */
#define SIDECAR_VERSION 1u
typedef BOOL (WINAPI *special_folder_fn)(HWND, LPWSTR, int, BOOL);

/* "<Documents>\LDW\<exe name>\Plant Tycoon Fix Patcher Data\Plant Upgrades <slot>.dat". */
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
    wcscat_s(out, cap, L"\\Plant Upgrades ");
    {
        wchar_t digits[12];
        int i = 0, v = slot;
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 11);
        while (i) { size_t len = wcslen(out); out[len] = digits[--i]; out[len + 1] = L'\0'; }
    }
    wcscat_s(out, cap, L".dat");
    return 1;
}

static void __cdecl on_save(char *state, int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    DWORD header[3], written;
    if (boxes != NULL) boxes->save(state, slot);
    if (slot <= 0 || !sidecar_path(slot, path, 1024, 1)) return;
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    header[0] = SIDECAR_MAGIC;
    header[1] = SIDECAR_VERSION;
    header[2] = (DWORD)sizeof legendary;
    if (WriteFile(file, header, sizeof header, &written, NULL) && written == sizeof header
        && WriteFile(file, legendary, sizeof legendary, &written, NULL) && written == sizeof legendary) {
        CloseHandle(file);
        MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING);
    } else {
        CloseHandle(file);
        DeleteFileW(temp);
    }
}

static int valid_packets(const seed_record *s) {
    int i;
    for (i = 0; i < LEGENDARY_COUNT; ++i) {
        if (s[i].foliage < 1 || s[i].foliage > FOLIAGES || s[i].flower < FIRST_NEW_FLOWER
            || s[i].flower >= FIRST_NEW_FLOWER + NEW_FLOWERS || s[i].frame != LEGENDARY_FRAME_BASE + s[i].foliage) {
            return 0;
        }
    }
    return 1;
}

/* A save loaded: its packets, or (a save from before the mod, or a file that
   cannot be read, which is set aside) a fresh roll. */
static void __cdecl on_load(const char *state, int slot) {
    wchar_t path[1024];
    HANDLE file;
    DWORD header[3], got;
    int ok = 0;
    seed_record body[LEGENDARY_COUNT];
    if (slot <= 0) return;
    if (sidecar_path(slot, path, 1024, 0)) {
        file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (file != INVALID_HANDLE_VALUE) {
            ok = ReadFile(file, header, sizeof header, &got, NULL) && got == sizeof header
                 && header[0] == SIDECAR_MAGIC && header[1] == SIDECAR_VERSION && header[2] == sizeof body
                 && ReadFile(file, body, sizeof body, &got, NULL) && got == sizeof body && valid_packets(body);
            CloseHandle(file);
            if (!ok) {
                wchar_t aside[1100];
                wcscpy_s(aside, 1100, path);
                wcscat_s(aside, 1100, L".unreadable");
                MoveFileExW(path, aside, MOVEFILE_REPLACE_EXISTING);
            }
        }
    }
    if (ok) memcpy(legendary, body, sizeof legendary);
    else roll_legendary(state);
    if (boxes != NULL) boxes->load(state, slot);
}

static void __cdecl on_delete(int slot) {
    wchar_t path[1024];
    if (slot > 0 && sidecar_path(slot, path, 1024, 0)) DeleteFileW(path);
    if (boxes != NULL) boxes->remove(slot);
}

static void __cdecl on_new_game(void) {
    if (boxes != NULL) boxes->new_game();
}

/* ------------------------------------------------------------------- stubs */

static const DWORD k_roll_back_unused = 0;
static const DWORD k_dialog_back = SITE_DIALOG_ENTRY_BACK;
static const DWORD k_picture_back = SITE_DIALOG_PICTURE_BACK;
static const DWORD k_price_buyable_back = SITE_PRICE_BUYABLE_BACK;
static const DWORD k_price_poor_back = SITE_PRICE_POOR_BACK;
static const DWORD k_price_tray_full_back = SITE_PRICE_TRAY_FULL_BACK;
static const DWORD k_done_back = SITE_DIALOG_DONE_BACK;
static const DWORD k_buy_back = SITE_BUY_SEED_BACK;
static const DWORD k_buy_close = 0x00432E5Au;          /* sound, close the dialog */
static const DWORD k_chem_price_back = SITE_CHEM_PRICE_BACK;
static const DWORD k_chem_doses_back = SITE_CHEM_DOSES_BACK;
static const DWORD k_apply_back = SITE_CHEM_APPLY_BACK;
static const DWORD k_apply_tail = 0x0042720Bu;         /* sound, keep or drop the bottle */
static const DWORD k_name_gh_back = SITE_TRAY_NAME_GREENHOUSE_BACK;
static const DWORD k_name_store_back = SITE_TRAY_NAME_STORE_BACK;
static const DWORD k_string_back = SITE_STRING_LOOKUP_BACK;
static const DWORD k_activate_back = SITE_STORE_ACTIVATE_BACK;
static const DWORD k_draw_back = SITE_STORE_DRAW_BACK;
static const DWORD k_draw_skip = 0x00447FF8u;          /* after the stock item grids */
static const DWORD k_click_back = SITE_STORE_CLICK_BACK;
static const DWORD k_click_done = 0x00448583u;         /* the mouse handler's exit */
static const DWORD k_hover_back = SITE_STORE_HOVER_BACK;
static const DWORD k_joint_free_back = SITE_JOINT_FREE_BACK;
static const DWORD k_sprite_draw = 0x004208F0u;
static const float k_one = 1.0f;

/* 0x41DDDA: the tail of the daily seed roll (also run for a new game). */
__declspec(naked) static void stub_roll(void) {
    __asm {
        pop edi
        pop esi
        pop ebp
        pop ebx
        pop ecx
        pushad
        push ecx
        call on_roll
        add esp, 4
        popad
        ret
    }
}

/* 0x430950 purchase-dialog helper(index): 52..54 ride the Extinct seed path
   (6..8), 36 the Vaporbomb path (35), each with its flag set. */
__declspec(naked) static void stub_dialog(void) {
    __asm {
        mov eax, [esp + 4]
        cmp eax, FORMULA_ID
        jne seeds
        mov byte ptr [building_formula], 1
        mov dword ptr [esp + 4], 35
        jmp stock
    seeds:
        sub eax, FIRST_LEGENDARY_INDEX
        cmp eax, LEGENDARY_COUNT - 1
        ja stock
        mov byte ptr [building_legendary], 1
        add eax, 6
        mov [esp + 4], eax
    stock:
        push -1
        push 0x463A67
        jmp k_dialog_back
    }
}

/* 0x430827 dialog picture: ecx = sprite manager, ebx/edi = picture position + 0x19. */
__declspec(naked) static void stub_picture(void) {
    __asm {
        mov eax, [esi + 0xB8]
        sub eax, FIRST_LEGENDARY_INDEX
        cmp eax, LEGENDARY_COUNT - 1
        ja stock
        push ecx
        push dword ptr [esi + 0xB8]
        call legendary_frame
        add esp, 4
        pop ecx
        push 1
        push 100
        push dword ptr [k_one]
        lea edx, [edi - 0x19]
        push edx
        lea edx, [ebx - 0x19]
        push edx
        push eax
        push SHEET_SEEDS
        call dword ptr [k_sprite_draw]
        pop edi
        pop esi
        pop ebx
        ret
    stock:
        mov eax, [esi + 0xB8]
        jmp k_picture_back
    }
}

/* The Extinct path's three price writes: $5000 for a Legendary packet, $0
   with Free upgrades (the stock compare that follows, unsigned cash against
   this price at 0x430D13, then always finds it affordable). */
#define PRICE_STUB(NAME, BACK)                              \
    __declspec(naked) static void NAME(void) {              \
        __asm { mov dword ptr [esi + 0x84], 2000 }          \
        __asm { cmp byte ptr [building_legendary], 0 }      \
        __asm { je done }                                   \
        __asm { mov dword ptr [esi + 0x84], LEGENDARY_PRICE } \
        __asm { cmp byte ptr [free_upgrades], 0 }           \
        __asm { je done }                                   \
        __asm { mov dword ptr [esi + 0x84], 0 }             \
        __asm { done: jmp BACK }                            \
    }
PRICE_STUB(stub_price_buyable, k_price_buyable_back)
PRICE_STUB(stub_price_poor, k_price_poor_back)
PRICE_STUB(stub_price_tray_full, k_price_tray_full_back)

/* 0x433240 right after the helper: the flags only last while it runs. */
__declspec(naked) static void stub_done(void) {
    __asm {
        mov byte ptr [building_legendary], 0
        mov byte ptr [building_formula], 0
        cmp byte ptr [esi + 0xA8], 0
        jmp k_done_back
    }
}

/* 0x432D45 Buy, seed mode: ebp = dialog. */
__declspec(naked) static void stub_buy(void) {
    __asm {
        mov eax, [ebp + 0xB8]
        sub eax, FIRST_LEGENDARY_INDEX
        cmp eax, LEGENDARY_COUNT - 1
        ja stock
        pushad
        push ebp
        call buy_legendary
        add esp, 4
        popad
        jmp k_buy_close
    stock:
        mov eax, [ebp + 0x94]
        jmp k_buy_back
    }
}

/* 0x432716 chemical dialog: the formula's price, and room for chemical 36 in the tray. */
__declspec(naked) static void stub_chem_price(void) {
    __asm {
        cmp byte ptr [building_formula], 0
        je stock
        mov edx, FORMULA_PRICE
        cmp byte ptr [free_upgrades], 0
        je priced
        xor edx, edx
    priced:
        mov ecx, [esi + 0x78]
        push FORMULA_ID
        jmp k_chem_price_back
    stock:
        mov edx, [eax + ecx + 0x8C8]
        mov ecx, [esi + 0x78]
        push edi
        jmp k_chem_price_back
    }
}

/* 0x432E43 chemical Buy: the formula comes with 3 doses. */
__declspec(naked) static void stub_chem_doses(void) {
    __asm {
        cmp dword ptr [ebp + 0xB8], FORMULA_ID
        jne stock
        mov edx, FORMULA_DOSES
        jmp k_chem_doses_back
    stock:
        mov edx, [eax + ecx + 0x8DC]
        jmp k_chem_doses_back
    }
}

/* 0x4266A6 a chemical used on a pot: esi = greenhouse, ebx = col, ebp = row, [esp+0x14] = plant. */
__declspec(naked) static void stub_apply(void) {
    __asm {
        mov eax, [esp + 0x20]
        cmp eax, FORMULA_ID
        jne stock
        mov eax, [esp + 0x14]
        pushad
        push eax
        push ebp
        push ebx
        push esi
        call apply_formula
        add esp, 16
        popad
        jmp k_apply_tail
    stock:
        add eax, -0x1B
        jmp k_apply_back
    }
}

/* Chemical tray tooltips: the formula's name. */
__declspec(naked) static void stub_name_greenhouse(void) {
    __asm {
        cmp eax, FORMULA_ID
        jne stock
        mov eax, FORMULA_NAME_ID
        jmp k_name_gh_back
    stock:
        add eax, 0x189
        jmp k_name_gh_back
    }
}

__declspec(naked) static void stub_name_store(void) {
    __asm {
        cmp edx, FORMULA_ID
        jne stock
        mov edx, FORMULA_NAME_ID
        jmp k_name_store_back
    stock:
        add edx, 0x189
        jmp k_name_store_back
    }
}

/* 0x44CA70 string(id) (thiscall, ret 4): this mod's texts. */
__declspec(naked) static void stub_string(void) {
    __asm {
        mov eax, [esp + 4]
        cmp eax, FORMULA_NAME_ID
        jne box_4
        mov eax, offset FORMULA_NAME
        ret 4
    box_4:
        cmp eax, BOX_TITLE_ID
        jne box_5
        mov eax, offset BOX_TITLE_4
        ret 4
    box_5:
        cmp eax, BOX_TITLE_ID + 1
        jne box_6
        mov eax, offset BOX_TITLE_5
        ret 4
    box_6:
        cmp eax, BOX_TITLE_ID + 2
        jne box_desc
        mov eax, offset BOX_TITLE_6
        ret 4
    box_desc:
        cmp eax, BOX_DESC_ID
        jne legendary_texts
        mov eax, offset BOX_DESC
        ret 4
    legendary_texts:
        cmp byte ptr [building_legendary], 0
        je formula_texts
        cmp eax, 0x11D
        jne legendary_desc
        mov eax, offset LEGENDARY_TITLE
        ret 4
    legendary_desc:
        cmp eax, 0x11E
        jne formula_texts
        mov eax, offset LEGENDARY_DESC
        ret 4
    formula_texts:
        cmp byte ptr [building_formula], 0
        je stock
        cmp eax, 0x165
        jne formula_desc
        mov eax, offset FORMULA_TITLE
        ret 4
    formula_desc:
        cmp eax, 0x166
        jne stock
        mov eax, offset FORMULA_DESC
        ret 4
    stock:
        mov eax, [esp + 4]
        test eax, eax
        jmp k_string_back
    }
}

/* 0x446D40 store activate(bool) (thiscall): ecx = store. */
__declspec(naked) static void stub_activate(void) {
    __asm {
        pushad
        push dword ptr [esp + 0x24]
        push ecx
        call on_activate
        add esp, 8
        popad
        push -1
        push 0x463E5E
        jmp k_activate_back
    }
}

/* 0x42D330 (stdcall-style, ret 0xC): is this flower spot free?  Yes to all
   while the formula flowers a plant. */
__declspec(naked) static void stub_joint_free(void) {
    __asm {
        cmp byte ptr [formula_flowering], 0
        je stock
        mov al, 1
        ret 0xC
    stock:
        mov eax, [esp + 0xC]
        mov edx, [esp + 8]
        jmp k_joint_free_back
    }
}

/* 0x447DA2 store draw, before the item grids: esi = store. */
__declspec(naked) static void stub_draw(void) {
    __asm {
        pushad
        push esi
        call on_draw
        add esp, 4
        mov [esp + 28], eax
        popad
        test eax, eax
        jnz skip
        xor ebx, ebx
        mov ebp, 0x13B
        jmp k_draw_back
    skip:
        jmp k_draw_skip
    }
}

/* 0x448173 store button-down, before the item loops: esi = store, edi/ebx = mouse x/y, eax = 0. */
__declspec(naked) static void stub_click(void) {
    __asm {
        pushad
        push ebx
        push edi
        push esi
        call on_click
        add esp, 12
        mov [esp + 28], eax
        popad
        test eax, eax
        jnz done
        mov [esp + 0x14], eax
        mov ebp, 0x122
        jmp k_click_back
    done:
        jmp k_click_done
    }
}

/* 0x448433 store mouse move (nothing held is tested next): edi/ebx = mouse x/y. */
__declspec(naked) static void stub_hover(void) {
    __asm {
        pushad
        push ebx
        push edi
        call on_hover
        add esp, 8
        popad
        mov eax, [esi + 0x1BC]
        jmp k_hover_back
    }
}

/* ----------------------------------------------------------------- install */

static const char SEED_SHEET_FILE[] = "seed_grid_legendary.png";
static const char CHEM_SHEET_FILE[] = "Chemicals_Grid_upgrades.png";
static const char LINK_FILE[] = "upgrades_link.png";

#define CODE_ADDR(f) ((const void *)(UINT_PTR)(f))
#define CODE_SITES 19
#define DATA_SITES 6
#define TOTAL_SITES (CODE_SITES + DATA_SITES)
static ftfp_site_write writes[TOTAL_SITES];
static int installed = 0;

#define JMP(W, NAME, TO) ftfp_site_branch((W), SITE_##NAME##_VA, SITE_##NAME##_LEN, SITE_##NAME##_EXPECT, 0xE9, CODE_ADDR(TO))

static void site_data(ftfp_site_write *w, unsigned int va, int length, const unsigned char *expect,
                      const void *bytes, int count) {
    w->va = va;
    w->length = length;
    w->expect = expect;
    memcpy(w->bytes, expect, (size_t)length);
    memcpy(w->bytes, bytes, (size_t)count);
}

static int prepare(void) {
    ftfp_site_write *w = writes;
    DWORD seed_file = (DWORD)(UINT_PTR)SEED_SHEET_FILE, chem_file = (DWORD)(UINT_PTR)CHEM_SHEET_FILE;
    DWORD seed_rows = 8, chem_rows = 12;           /* row 10: the Time Warp clock, row 11: Add Money's coins */
    DWORD link[6];
    unsigned char bound = SITE_CHEM_PICTURE_BOUND_NEW;
    link[0] = LINK_SPRITE;
    link[1] = (DWORD)(UINT_PTR)LINK_FILE;
    link[2] = 0;
    link[3] = 0;
    link[4] = 2;                 /* columns: normal, hover */
    link[5] = 1;
    JMP(w++, ROLL_TAIL, stub_roll);
    JMP(w++, DIALOG_ENTRY, stub_dialog);
    JMP(w++, DIALOG_PICTURE, stub_picture);
    JMP(w++, PRICE_BUYABLE, stub_price_buyable);
    JMP(w++, PRICE_POOR, stub_price_poor);
    JMP(w++, PRICE_TRAY_FULL, stub_price_tray_full);
    JMP(w++, DIALOG_DONE, stub_done);
    JMP(w++, BUY_SEED, stub_buy);
    JMP(w++, CHEM_PRICE, stub_chem_price);
    JMP(w++, CHEM_DOSES, stub_chem_doses);
    JMP(w++, CHEM_APPLY, stub_apply);
    JMP(w++, TRAY_NAME_GREENHOUSE, stub_name_greenhouse);
    JMP(w++, TRAY_NAME_STORE, stub_name_store);
    JMP(w++, STRING_LOOKUP, stub_string);
    JMP(w++, STORE_ACTIVATE, stub_activate);
    JMP(w++, STORE_DRAW, stub_draw);
    JMP(w++, STORE_CLICK, stub_click);
    JMP(w++, STORE_HOVER, stub_hover);
    JMP(w++, JOINT_FREE, stub_joint_free);
    site_data(w++, SITE_CHEM_PICTURE_BOUND_VA, SITE_CHEM_PICTURE_BOUND_LEN, SITE_CHEM_PICTURE_BOUND_EXPECT, NULL, 0);
    writes[CODE_SITES].bytes[SITE_CHEM_PICTURE_BOUND_IMM_AT] = bound;
    site_data(w++, SITE_SEED_SHEET_FILE_VA, SITE_SEED_SHEET_FILE_LEN, SITE_SEED_SHEET_FILE_EXPECT, &seed_file, 4);
    site_data(w++, SITE_SEED_SHEET_ROWS_VA, SITE_SEED_SHEET_ROWS_LEN, SITE_SEED_SHEET_ROWS_EXPECT, &seed_rows, 4);
    site_data(w++, SITE_CHEM_SHEET_FILE_VA, SITE_CHEM_SHEET_FILE_LEN, SITE_CHEM_SHEET_FILE_EXPECT, &chem_file, 4);
    site_data(w++, SITE_CHEM_SHEET_ROWS_VA, SITE_CHEM_SHEET_ROWS_LEN, SITE_CHEM_SHEET_ROWS_EXPECT, &chem_rows, 4);
    site_data(w++, SITE_LINK_RECORD_VA, SITE_LINK_RECORD_LEN, SITE_LINK_RECORD_EXPECT, link, sizeof link);
    (void)k_roll_back_unused;
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

/* "<game>\Plant Tycoon Fix Patcher DLLs\Store Upgrades and Items.log". */
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
    wcscat_s(path, 1024, L"Plant Tycoon Fix Patcher DLLs\\Store Upgrades and Items.log");
    if (installed) {
        len = append_text(line, len, "Plant Upgrades: installed (all sites)\r\n");
    } else if (ftfp_failed_site != 0) {
        len = append_text(line, len, "Plant Upgrades: NOT installed; the code at ");
        len = append_hex(line, len, ftfp_failed_site);
        len = append_text(line, len, " is not the stock code this build expects\r\n");
    } else {
        len = append_text(line, len, "Plant Upgrades: NOT installed\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* The New Flowers DLL passes its save, load, delete and new-game events on to these. */
typedef struct ftfp_upgrades_events {
    int version;
    void (__cdecl *save)(char *state, int slot);
    void (__cdecl *load)(const char *state, int slot);
    void (__cdecl *remove)(int slot);
    void (__cdecl *new_game)(void);
    void (__cdecl *pollinated)(char *pot);   /* version 2: called by "Unused Flowers.dll" after its breeding rule */
} ftfp_upgrades_events;

static const ftfp_upgrades_events events = { 2, on_save, on_load, on_delete, on_new_game, on_pollinated };

EXTERN_C IMAGE_DOS_HEADER __ImageBase;

/* "Extra Seed Boxes.dll", when it is beside this DLL. */
static void load_boxes(void) {
    wchar_t path[1024];
    wchar_t *slash;
    HMODULE module;
    boxes_startup_fn startup;
    const ftfp_box_events *found;
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, path, 1024);
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(path) + 40 >= 1024) return;
    wcscat_s(path, 1024, L"Extra Seed Boxes.dll");
    if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return;
    module = LoadLibraryW(path);
    if (module == NULL) return;
    startup = (boxes_startup_fn)GetProcAddress(module, "FtfpSeedBoxesStartup");
    if (startup == NULL) return;
    found = startup();
    if (found != NULL && found->version == 1) boxes = found;
}

/* Called once by "Unused Flowers.dll" after it installed, before WinMain. */
const ftfp_upgrades_events *__stdcall FtfpUpgradesStartup(void) {
    if (!installed) {
        __try {
            if (prepare() && ftfp_install_sites(writes, TOTAL_SITES)) installed = 1;
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            installed = 0;
        }
        if (installed) {
            warp_on = tw_enabled((HMODULE)&__ImageBase);
            money_on = ftfp_setting_on((HMODULE)&__ImageBase, L"Add Money.ini");
            free_upgrades = (unsigned char)ftfp_setting_on((HMODULE)&__ImageBase, L"Free Upgrades.ini");
            __try {
                prepare_shapes();
            } __except (EXCEPTION_EXECUTE_HANDLER) {
                shapes_ready = 0;
            }
        }
        write_install_log();
        if (installed) {
            __try {
                load_boxes();
            } __except (EXCEPTION_EXECUTE_HANDLER) {
                boxes = NULL;
            }
            __try {
                load_extras();
            } __except (EXCEPTION_EXECUTE_HANDLER) {
                memset(extra_owned, 0, sizeof extra_owned);
                memset(extra_buy, 0, sizeof extra_buy);
            }
        }
    }
    return installed ? &events : NULL;
}

int __stdcall FtfpPlantUpgradesInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}
