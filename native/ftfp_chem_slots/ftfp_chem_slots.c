/* Extra Chemical Slots -- a second page of chemical slots in PC Plant Tycoon
   ("Extra chemical slots").

   WHAT.  The greenhouse's Tools box (the panel under the seed tray) is a
   4 x 2 grid: row 1 the four tools (0x423AA0: x 18 + 45 k, y 136), row 2
   the chemical tray's four slots (0x4165A0 / 0x416650: drawn at x 2 + 45 i,
   y 173).  The tray is four records of 12 bytes at state + 0x53F84 (present
   byte, chemical id, doses), and a held chemical is state + 0x56C = 5 + its
   slot.  Once "Extra Chemical Slots" is bought on the store's Upgrades view
   (Store Upgrades and Items.dll, $10,000, $0 with Free upgrades), a small
   gold arrow on the Tools box's plaque turns to page 2: eight more chemical
   slots in both rows of the grid (the tools stay on page 1; a tool already
   in the hand stays there).  Clicking the arrow, or carrying a chemical over
   it, turns the page back.  12 chemical slots in all.

   HOW.  Every page-2 slot is a stock slot while it is used: picking one up
   (0x4260A9, the press's tray hit) moves its record into a stock record --
   a free one if there is one, else one whose own record waits in `stash`
   and is drawn in its place -- so the game's own code holds, draws, doses
   (0x416540), stacks, empties and trashes it (Store Upgrades and Items'
   0x425FF2 / 0x4272DC take the formula and the other new chemicals as
   stock ones).  Once it is let go (put back, used up, thrown away, the
   greenhouse left) the record goes back to its page-2 slot and the stock
   record back to its place.  The tray's add and room checks (0x416410,
   0x4164B0: the store's Buy and its "There is no room in your Chemical
   Tray.") look at all twelve slots: a chemical stacks on its own bottle on
   either page, else goes to the first free slot of page 1, then of page 2.
   A held chemical let go or clicked on another slot moves there (empty),
   stacks (the same chemical) or changes places, on either page.

   STATE.  The save keeps its stock layout: the four stock records are in
   their places whenever the game saves (a held page-2 bottle is put back
   for the save and picked up again after it).  Page 2 and the purchase are
   kept per slot in "Plant Tycoon Fix Patcher Data\Extra Chemical Slots
   <slot>.dat" (chem_slots_file.h), written when the game saves; Store
   Upgrades and Items.dll passes on the save, load, delete and new-game
   events.  A new game empties page 2 and forgets the purchase.

   Every write into the game is in chem_slots_sites.h (five calls and two
   function heads, never overlapping another patch) plus two slots of the
   greenhouse screen's table (its mouse and its activation), which chain
   whatever another companion from this folder put there -- all of them or
   none. */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "chem_slots_sites.h"
#include "chem_slots_file.h"

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))
#define NOINLINE __declspec(noinline)   /* keeps the name in the map file the tests read */
#define CODE_ADDR(fn) ((const void *)(UINT_PTR)(fn))

#define STOCK_SLOTS 4
#define SLOTS (STOCK_SLOTS + CHEM_PAGE_SLOTS)
#define STATE_TRAY 0x53F84
#define STATE_HELD 0x56C
#define HELD_TRAY 5                     /* 5..8: chemical-tray slot 0..3 */
#define FIRST_CHEMICAL 27
#define LAST_CHEMICAL 39                /* 36-39: Store Upgrades and Items' four */

/* The greenhouse screen. */
#define SC_STATE 0x68
#define SC_SPRITES 0x6C
#define SC_SOUNDS 0x74
#define SC_STRINGS 0x78
#define SC_FLIGHT 0x80                  /* an item flying back to its place (0x4244C0) */
#define SC_STOCK_TIPS 0x110             /* the four tray tooltips (0x427836), one per stock slot */
#define FLIGHT_ITEM 0x04
#define FLIGHT_X 0x10
#define FLIGHT_Y 0x14

#define SHEET_CHEMICALS 0xB3            /* Store Upgrades and Items points it at Chemicals_Grid_upgrades.png */
#define ARROW_RIGHT_FRAME 38            /* row 19: the gold arrows, pre-scaled */
#define ARROW_LEFT_FRAME 39
#define SOUND_BUTTON 0x0C
#define SOUND_DROP 0x0D                 /* a seed or bottle laid back in the tray (0x425A35) */
#define STRING_FIRST_NAME 0x189         /* + chemical id */
#define TIP_ID 0x170                    /* the tooltip controls' ids (no other greenhouse control's) */
#define TIP_FONT (*(int *)0x0048C6A0u)
#define TIP_COLOUR (*(int *)0x00493C60u)

/* The page: stock slot i is drawn at (2 + 45 i, 173) and hit at x 20..47 + 45 i,
   y 173..253 (0x4165A0).  Page 2 has the same four columns in two rows:
   row 1 where the tools are, row 2 where page 1's slots are. */
#define COL_DRAW_X(c) (2 + 45 * (c))
#define COL_HIT_LEFT(c) (20 + 45 * (c))
#define COL_HIT_RIGHT(c) (47 + 45 * (c))
static const int ROW_DRAW_Y[2] = { 126, 173 };
static const int ROW_HIT_TOP[2] = { 136, 185 };
static const int ROW_HIT_BOTTOM[2] = { 184, 253 };
#define STOCK_HIT_TOP 173
#define STOCK_HIT_BOTTOM 253
#define FLIGHT_OFFSET 35                /* 0x4244C0 aims a bottle at its picture's place + 35 */

/* The arrow: on the plaque between the seed tray (y <= 98) and the tools (y >= 136),
   right of its middle, clear of its gold scrollwork; nothing else on the plaque takes a click. */
#define ARROW_X 136
#define ARROW_Y 104
#define ARROW_W 24
#define ARROW_H 24
#define PAGE_TEXT_X 100                 /* "1/2" / "2/2" left of the arrow, on the plaque */
#define PAGE_TEXT_Y 107
#define TEXT_WHITE 0xFFFFFFFFu
#define TEXT_SHADOW 0xFF000000u

typedef void (__fastcall *sprite_fn)(void *mgr, int edx, int sheet, int frame, int x, int y, float scale, int alpha, int flag);
typedef void (__fastcall *sound_fn)(void *sound, int edx, int id);
typedef const char *(__fastcall *string_fn)(void *strings, int edx, int id);
typedef void *(__cdecl *new_fn)(unsigned int size);
typedef void (__fastcall *tooltip_ctor_fn)(void *tip, int edx, int id, const RECT *rect, void *parent,
                                           const char *text, int font, int a, int b);
typedef void (__fastcall *tooltip_text_fn)(void *tip, int edx, const char *text, int colour, int font, int extra);
typedef void (__fastcall *add_control_fn)(void *scene, int edx, void *control);
typedef void (__fastcall *anim_finish_fn)(void *anim, int edx);
typedef int (__fastcall *hit2_fn)(void *self, int edx, int x, int y);
typedef void (__fastcall *draw1_fn)(void *self, int edx, int a);
typedef int (__fastcall *mouse_fn)(void *scene, int edx, int type, int x, int y);
typedef int (__fastcall *activate_fn)(void *scene, int edx, int on);
typedef void *(__cdecl *getter_fn)(void);
typedef void (__fastcall *text_fn)(void *graphics, int edx, const char *text, int x, int y, unsigned int colour,
                                   int font);

static const sprite_fn draw_sprite = (sprite_fn)0x004208F0u;
static const sound_fn play_sound = (sound_fn)0x0044A580u;
static const string_fn game_string = (string_fn)0x0044CA70u;
static const new_fn game_new = (new_fn)0x0044E894u;
static const tooltip_ctor_fn tooltip_ctor = (tooltip_ctor_fn)0x00409870u;
static const tooltip_text_fn tooltip_text = (tooltip_text_fn)0x00409AA0u;
static const add_control_fn add_control = (add_control_fn)0x0040B400u;
static const anim_finish_fn anim_finish = (anim_finish_fn)0x004211D0u;
static const getter_fn graphics_get = (getter_fn)0x00407A90u;
static const text_fn draw_text = (text_fn)0x004092A0u;          /* (text, x, y, colour, font 0 = PTfontsmall) */
static const hit2_fn stock_tool_hit = (hit2_fn)0x00423AA0u;       /* thiscall(scene)(x, y) */
static const hit2_fn stock_tray_hit = (hit2_fn)0x004165A0u;       /* thiscall(tray)(x, y) */
static const hit2_fn stock_tray_spot = (hit2_fn)0x00416600u;      /* (x, y), any slot, present or not */
static const draw1_fn stock_tools_draw = (draw1_fn)0x0044DD70u;   /* thiscall(tools)(flying item) */
static const draw1_fn stock_tray_draw = (draw1_fn)0x00416650u;    /* thiscall(tray)(slot not drawn) */

static mouse_fn next_mouse = NULL;
static activate_fn next_activate = NULL;

/* ------------------------------------------------------------ the slots */

static chem_record ext[CHEM_PAGE_SLOTS];       /* page 2 */
static int owned = 0;                          /* "Extra Chemical Slots" bought */
static int ready = 0;                          /* a game is loaded or new: the records are its own */
static int page = 0;                           /* 0 page 1, 1 page 2 */
static int installed = 0;
static HMODULE self_module = NULL;

/* A page-2 record in a stock record's place (lift_e -> stock lift_k), the
   stock record waiting in stash.  While suspended (a save) they are back. */
static int lift_e = -1, lift_k = 0, suspended = 0;
static chem_record stash;
static int over_arrow = 0;                     /* a carried chemical is over the arrow (it turns once) */

static char *tips[STOCK_SLOTS + CHEM_PAGE_SLOTS];  /* every slot's tooltip, both pages */
static char tip_text[STOCK_SLOTS + CHEM_PAGE_SLOTS][96];
static unsigned int tip_key[STOCK_SLOTS + CHEM_PAGE_SLOTS];  /* what each one's text says */
static char *tips_scene = NULL;

static chem_record *tray(char *state) { return (chem_record *)(state + STATE_TRAY); }
static int held(char *state) { return AT(state, STATE_HELD, int); }
static int lifted(void) { return lift_e >= 0 && !suspended; }
static int pages(void) { return ready && owned && installed; }

/* Slot g (0-3 page 1, 4-11 page 2) as the player sees it. */
NOINLINE static chem_record *logical(char *state, int g) {
    if (lifted()) {
        if (g == lift_k) return &stash;
        if (g == STOCK_SLOTS + lift_e) return &tray(state)[lift_k];
    }
    return g < STOCK_SLOTS ? &tray(state)[g] : &ext[g - STOCK_SLOTS];
}

static void *flight(char *scene) { return scene != NULL ? AT(scene, SC_FLIGHT, void *) : NULL; }
static int flying(char *scene) {
    void *f = flight(scene);
    return f != NULL && AT(f, 0, unsigned char) ? AT(f, FLIGHT_ITEM, int) : -1;
}

/* Page-2 slot e into stock record k. */
NOINLINE static int lift(char *state, int e) {
    int k;
    for (k = 0; k < STOCK_SLOTS && tray(state)[k].present; ++k) {
    }
    if (k == STOCK_SLOTS) k = e % STOCK_SLOTS;
    stash = tray(state)[k];
    tray(state)[k] = ext[e];
    memset(&ext[e], 0, sizeof ext[e]);
    lift_e = e;
    lift_k = k;
    suspended = 0;
    return k;
}

NOINLINE static void unlift(char *state) {
    if (lift_e < 0) return;
    if (!suspended) {
        ext[lift_e] = tray(state)[lift_k];
        tray(state)[lift_k] = stash;
    }
    chem_record_clean(&ext[lift_e]);
    memset(&stash, 0, sizeof stash);
    lift_e = -1;
    suspended = 0;
}

/* The bottle went back to its page-2 slot: put back, used up, thrown away. */
NOINLINE static void settle(char *scene) {
    char *state;
    if (lift_e < 0 || suspended || scene == NULL) return;
    state = AT(scene, SC_STATE, char *);
    if (state == NULL) return;
    if (held(state) == HELD_TRAY + lift_k || flying(scene) == HELD_TRAY + lift_k) return;
    unlift(state);
}

/* Leaving the greenhouse: the hand is emptied (as the stock screens do) and the bottle goes home now. */
NOINLINE static void settle_now(char *scene) {
    char *state;
    if (lift_e < 0 || scene == NULL) return;
    state = AT(scene, SC_STATE, char *);
    if (state == NULL) return;
    if (!suspended) {
        if (held(state) == HELD_TRAY + lift_k) AT(state, STATE_HELD, int) = 0;
        if (flying(scene) == HELD_TRAY + lift_k) anim_finish(flight(scene), 0);
    }
    unlift(state);
}

/* A save: the stock records in their places, picked up again at the next event. */
static void suspend(char *state) {
    chem_record t;
    if (!lifted() || state == NULL) return;
    t = tray(state)[lift_k];
    tray(state)[lift_k] = stash;
    ext[lift_e] = t;
    suspended = 1;
}

static void resume(char *state) {
    if (lift_e < 0 || !suspended || state == NULL) return;
    stash = tray(state)[lift_k];
    tray(state)[lift_k] = ext[lift_e];
    memset(&ext[lift_e], 0, sizeof ext[lift_e]);
    suspended = 0;
}

static void reset(void) {
    memset(ext, 0, sizeof ext);
    memset(&stash, 0, sizeof stash);
    owned = 0;
    page = 0;
    lift_e = -1;
    suspended = 0;
    over_arrow = 0;
}

/* Each chemical in one slot: a later slot with a chemical already in an earlier one stacks onto it. */
NOINLINE static void merge_duplicates(char *state) {
    int a, b;
    for (b = 0; b < SLOTS; ++b) {
        chem_record *rb = logical(state, b);
        if (!rb->present) continue;
        for (a = 0; a < b; ++a) {
            chem_record *ra = logical(state, a);
            if (ra->present && ra->id == rb->id) {
                ra->doses += rb->doses;
                memset(rb, 0, sizeof *rb);
                break;
            }
        }
    }
}

/* ------------------------------------------------------------ the page's geometry */

/* The slot (0-11) under (x, y) on the page shown, present or not; -1 for none. */
NOINLINE static int slot_at(int x, int y) {
    int c, r;
    for (c = 0; c < STOCK_SLOTS; ++c) {
        if (x < COL_HIT_LEFT(c) || x > COL_HIT_RIGHT(c)) continue;
        if (page == 0) return y >= STOCK_HIT_TOP && y <= STOCK_HIT_BOTTOM ? c : -1;
        for (r = 0; r < 2; ++r) {
            if (y >= ROW_HIT_TOP[r] && y <= ROW_HIT_BOTTOM[r]) return STOCK_SLOTS + r * STOCK_SLOTS + c;
        }
    }
    return -1;
}

static int in_arrow(int x, int y) {
    return x >= ARROW_X && x < ARROW_X + ARROW_W && y >= ARROW_Y && y < ARROW_Y + ARROW_H;
}

static int draw_x(int g) { return COL_DRAW_X(g < STOCK_SLOTS ? g : (g - STOCK_SLOTS) % STOCK_SLOTS); }
static int draw_y(int g) { return g < STOCK_SLOTS ? ROW_DRAW_Y[1] : ROW_DRAW_Y[(g - STOCK_SLOTS) / STOCK_SLOTS]; }

static RECT tip_rect(int e) {
    int c = e % STOCK_SLOTS, r = e / STOCK_SLOTS;
    RECT rect;
    rect.left = COL_HIT_LEFT(c);
    rect.top = ROW_HIT_TOP[r];
    rect.right = COL_HIT_RIGHT(c);
    rect.bottom = ROW_HIT_BOTTOM[r];
    return rect;
}

/* ------------------------------------------------------------ moving a bottle between slots */

/* The held bottle (from slot src) to slot dst: into an empty slot, onto the same chemical
   (the doses add), or the two change places.  The hand is empty after. */
NOINLINE static void move_bottle(char *scene, int src, int dst) {
    char *state = AT(scene, SC_STATE, char *);
    chem_record *s, *d, t;
    unlift(state);
    s = logical(state, src);
    d = logical(state, dst);
    if (!s->present) return;
    if (!d->present) {
        *d = *s;
        memset(s, 0, sizeof *s);
    } else if (d->id == s->id) {
        d->doses += s->doses;
        memset(s, 0, sizeof *s);
    } else {
        t = *d;
        *d = *s;
        *s = t;
    }
    play_sound(AT(scene, SC_SOUNDS, void *), 0, SOUND_DROP);
}

/* The slot the held chemical came from, or -1 when the hand holds no chemical. */
static int held_slot(char *state) {
    int h = held(state);
    if (h < HELD_TRAY || h >= HELD_TRAY + STOCK_SLOTS) return -1;
    if (lifted() && h == HELD_TRAY + lift_k) return STOCK_SLOTS + lift_e;
    return h - HELD_TRAY;
}

/* ------------------------------------------------------------ the tooltips */

/* Every chemical slot of both pages has a tooltip of the game's own kind (0x409870, as the stock
   tray's): the chemical's name and the doses left ("Revival Potion\n2 doses left"), shown only
   over a slot that holds a bottle (not while that bottle is in the hand), only on the page
   shown.  The stock tray's own tooltips (made at 0x427836 when the mouse is over a slot, "%s\n%s:
   %d") are never made: the hover's spot (0x427765) answers none.  The names are the game's
   (string 0x189 + id); Store Upgrades and Items names its four chemicals with string ids of its
   own (its 0x4277B4), which the game's string lookup (0x44CA70, which it extends) returns. */
static int name_id(int id) {
    switch (id) {
    case 36: return 0x1F0;
    case 37: return 0x1F5;
    case 38: return 0x1F6;
    case 39: return 0x1F7;
    default: return STRING_FIRST_NAME + id;
    }
}

static RECT slot_rect(int g) {
    RECT rect;
    if (g < STOCK_SLOTS) {
        rect.left = COL_HIT_LEFT(g);
        rect.top = STOCK_HIT_TOP;
        rect.right = COL_HIT_RIGHT(g);
        rect.bottom = STOCK_HIT_BOTTOM;
        return rect;
    }
    return tip_rect(g - STOCK_SLOTS);
}

static void make_tips(char *scene) {
    int g;
    if (tips_scene == scene) return;
    tips_scene = scene;
    memset(tips, 0, sizeof tips);
    memset(tip_key, 0, sizeof tip_key);
    for (g = 0; g < SLOTS; ++g) {
        RECT r = slot_rect(g);
        char *tip = (char *)game_new(0x10);
        if (tip == NULL) return;
        tip_text[g][0] = ' ';
        tip_text[g][1] = '\0';
        tooltip_ctor(tip, 0, TIP_ID + g, &r, scene, tip_text[g], TIP_FONT, 0, 0);
        add_control(scene, 0, tip);
        AT(tip, 8, unsigned char) = 0;
        tips[g] = tip;
    }
}

/* The slot (0-11) whose bottle is in the hand or flying home, or -1. */
static int slot_away(char *scene) {
    char *state = AT(scene, SC_STATE, char *);
    int h = held(state), f = flying(scene), k;
    for (k = 0; k < STOCK_SLOTS; ++k) {
        if (h != HELD_TRAY + k && f != HELD_TRAY + k) continue;
        return lifted() && k == lift_k ? STOCK_SLOTS + lift_e : k;
    }
    return -1;
}

/* "<name>\n<n> doses left" for slot g; 0 when it holds no bottle. */
NOINLINE static int tip_text_for(char *scene, int g, char *out, int cap) {
    chem_record *r = logical(AT(scene, SC_STATE, char *), g);
    if (!r->present || r->id < FIRST_CHEMICAL || r->id > LAST_CHEMICAL) return 0;
    sprintf_s(out, (size_t)cap, "%s\n%d %s left", game_string(AT(scene, SC_STRINGS, void *), 0, name_id(r->id)),
              r->doses, r->doses == 1 ? "dose" : "doses");
    return 1;
}

/* Every frame: each tooltip shown only on its page over a bottle, its text kept up to date. */
NOINLINE static void refresh_tips(char *scene) {
    char *state = AT(scene, SC_STATE, char *);
    int g, k, away, shown_page = pages() ? page : 0;
    for (k = 0; k < STOCK_SLOTS; ++k) {
        char *stock_tip = AT(scene, SC_STOCK_TIPS + 4 * k, char *);
        if (stock_tip != NULL) AT(stock_tip, 8, unsigned char) = 0;
    }
    make_tips(scene);
    if (tips_scene != scene) return;
    away = slot_away(scene);
    for (g = 0; g < SLOTS; ++g) {
        chem_record *r = logical(state, g);
        int on_page = g < STOCK_SLOTS ? shown_page == 0 : shown_page == 1;
        int shown = on_page && g != away && r->present;
        unsigned int key = shown ? ((unsigned int)r->id << 24) ^ (unsigned int)r->doses ^ 0x80000000u : 0;
        if (tips[g] == NULL) continue;
        if (shown && key != tip_key[g] && tip_text_for(scene, g, tip_text[g], (int)sizeof tip_text[g])) {
            tooltip_text(tips[g], 0, tip_text[g], TIP_COLOUR, 0, 0);
        }
        tip_key[g] = key;
        AT(tips[g], 8, unsigned char) = (unsigned char)shown;
    }
}

/* ------------------------------------------------------------ turning the page */

NOINLINE static void turn_page(char *scene) {
    page = !page;
    play_sound(AT(scene, SC_SOUNDS, void *), 0, SOUND_BUTTON);
    refresh_tips(scene);
}

/* ------------------------------------------------------------ the hooks */

/* 0x42606E, the press's tool hit (thiscall scene): no tools on page 2. */
NOINLINE static int __fastcall tool_hit(void *scene, int edx, int x, int y) {
    (void)edx;
    if (pages() && page == 1) return -1;
    return stock_tool_hit(scene, 0, x, y);
}

/* 0x4260A9, the press's tray hit (thiscall tray): the stock code then picks up the slot it
   returns (hand empty) or puts back what the hand holds (anything else).  A held chemical
   pressed on another slot moves there instead (the hand is set to -1, which the put-back
   0x4244C0 only empties). */
NOINLINE static int __cdecl tray_hit(void *tray_obj, char *scene, int x, int y) {
    char *state = *(char **)tray_obj;
    int g, h, src;
    if (!pages()) return stock_tray_hit(tray_obj, 0, x, y);
    resume(state);
    g = slot_at(x, y);
    if (g < 0) return -1;
    h = held(state);
    if (h == 0) {
        if (!logical(state, g)->present) return -1;
        return g < STOCK_SLOTS ? g : lift(state, g - STOCK_SLOTS);
    }
    src = held_slot(state);
    if (src >= 0 && src != g) {
        move_bottle(scene, src, g);
        AT(state, STATE_HELD, int) = -1;
        return 0;
    }
    if (src == g) return h - HELD_TRAY;               /* its own slot: put back, as stock */
    return logical(state, g)->present ? 0 : -1;        /* a tool or seed: put back over a bottle, as stock */
}

/* 0x427765, the hover's tray spot (the hand empty): the stock tray tooltips are not made (this
   DLL's own show every slot's name and doses). */
NOINLINE static int __cdecl tray_spot(char *scene, int x, int y) {
    if (!installed || !ready) return stock_tray_spot(NULL, 0, x, y);
    refresh_tips(scene);
    return -1;
}

/* 0x428EE2, the tools' draw: not on page 2. */
NOINLINE static void __fastcall tools_draw(void *tools, int edx, int flying_item) {
    (void)edx;
    if (pages() && page == 1) return;
    stock_tools_draw(tools, 0, flying_item);
}

static void draw_bottle(char *scene, const chem_record *r, int x, int y) {
    if (!r->present || r->id < FIRST_CHEMICAL || r->id > LAST_CHEMICAL) return;
    draw_sprite(AT(scene, SC_SPRITES, void *), 0, SHEET_CHEMICALS, 2 * r->id - 54, x, y, 1.0f, 100, 1);
}

/* "1/2" or "2/2" left of the arrow, in the game's small font (PTfontsmall), white on a black
   shadow as the greenhouse counts are written. */
static void draw_page_number(void) {
    void *graphics = graphics_get();
    const char *text = page == 0 ? "1/2" : "2/2";
    if (graphics == NULL) return;
    draw_text(graphics, 0, text, PAGE_TEXT_X + 1, PAGE_TEXT_Y + 1, TEXT_SHADOW, 0);
    draw_text(graphics, 0, text, PAGE_TEXT_X, PAGE_TEXT_Y, TEXT_WHITE, 0);
}

/* 0x428EFC, the tray's draw (thiscall tray, the slot not to draw): page 1 as stock (and a
   stock slot's own bottle while a page-2 bottle uses its record), or page 2; then the arrow
   and the page number. */
NOINLINE static void __cdecl tray_draw(void *tray_obj, char *scene, int skip) {
    char *state = *(char **)tray_obj;
    int e, away;
    if (!pages()) {
        stock_tray_draw(tray_obj, 0, skip);
        if (installed && ready) refresh_tips(scene);
        return;
    }
    resume(state);
    settle(scene);
    away = lifted() && (held(state) == HELD_TRAY + lift_k || flying(scene) == HELD_TRAY + lift_k);
    if (page == 0) {
        stock_tray_draw(tray_obj, 0, skip);
        if (lifted()) draw_bottle(scene, &stash, draw_x(lift_k), draw_y(lift_k));
    } else {
        for (e = 0; e < CHEM_PAGE_SLOTS; ++e) {
            if (away && e == lift_e) continue;
            draw_bottle(scene, logical(state, STOCK_SLOTS + e), draw_x(STOCK_SLOTS + e), draw_y(STOCK_SLOTS + e));
        }
    }
    draw_sprite(AT(scene, SC_SPRITES, void *), 0, SHEET_CHEMICALS, page == 0 ? ARROW_RIGHT_FRAME : ARROW_LEFT_FRAME,
                ARROW_X, ARROW_Y, 1.0f, 100, 1);
    draw_page_number();
    refresh_tips(scene);
}

/* A page-2 bottle put back flies to its own slot (0x4244C0 aims at the stock slot it uses),
   or, while page 1 is shown, is home at once. */
static void aim_flight(char *scene) {
    void *f = flight(scene);
    int e = lift_e;
    if (!lifted() || flying(scene) != HELD_TRAY + lift_k) return;
    if (page == 0) {
        anim_finish(f, 0);
        settle(scene);
        return;
    }
    AT(f, FLIGHT_X, int) = draw_x(STOCK_SLOTS + e) + FLIGHT_OFFSET;
    AT(f, FLIGHT_Y, int) = draw_y(STOCK_SLOTS + e) + FLIGHT_OFFSET;
}

/* The greenhouse's mouse (0x469224: 1 move, 2 press, 3 release). */
NOINLINE static int __fastcall gh_mouse(char *scene, int edx, int type, int x, int y) {
    char *state = AT(scene, SC_STATE, char *);
    int result, src, g;
    (void)edx;
    if (!pages() || state == NULL) return next_mouse(scene, 0, type, x, y);
    resume(state);
    settle(scene);
    if (type == 2 && in_arrow(x, y)) {
        turn_page(scene);
        return 1;
    }
    if (type == 1) {
        int over = in_arrow(x, y);
        if (over && !over_arrow && held_slot(state) >= 0) turn_page(scene);
        over_arrow = over;
    }
    result = next_mouse(scene, 0, type, x, y);
    if (type == 3 && (src = held_slot(state)) >= 0 && (g = slot_at(x, y)) >= 0 && g != src) {
        move_bottle(scene, src, g);
        AT(state, STATE_HELD, int) = 0;
    }
    aim_flight(scene);
    settle(scene);
    return result;
}

/* The greenhouse's activation (0x469244): entering or leaving, a page-2 bottle is home. */
NOINLINE static int __fastcall gh_activate(char *scene, int edx, int on) {
    (void)edx;
    if (AT(scene, SC_STATE, char *) != NULL) {
        resume(AT(scene, SC_STATE, char *));
        settle_now(scene);
    }
    over_arrow = 0;
    return next_activate(scene, 0, on);
}

/* 0x416410 tray add(id, doses) (thiscall tray, ret 8): the store's Buy.  Onto the same
   chemical, else the first free slot; with page 2, over all twelve slots. */
NOINLINE static int __fastcall tray_add(void *tray_obj, int edx, int id, int doses) {
    char *state = *(char **)tray_obj;
    int n = pages() ? SLOTS : STOCK_SLOTS, g;
    (void)edx;
    for (g = 0; g < n; ++g) {
        chem_record *r = logical(state, g);
        if (r->present && r->id == id) {
            r->doses += doses;
            return 1;
        }
    }
    for (g = 0; g < n; ++g) {
        chem_record *r = logical(state, g);
        if (!r->present) {
            r->present = 1;
            r->id = id;
            r->doses = doses;
            return 1;
        }
    }
    return 0;
}

/* 0x4164B0 tray room(id) (thiscall tray, ret 4): the store's "no room" check. */
NOINLINE static int __fastcall tray_room(void *tray_obj, int edx, int id) {
    char *state = *(char **)tray_obj;
    int n = pages() ? SLOTS : STOCK_SLOTS, g;
    (void)edx;
    for (g = 0; g < n; ++g) {
        chem_record *r = logical(state, g);
        if (!r->present || r->id == id) return 1;
    }
    return 0;
}

/* The call sites: tray and scene in, the stock return. */
__declspec(naked) static void stub_tray_hit(void) {      /* ecx = tray, esi = scene, [esp+4] x, [esp+8] y */
    __asm {
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        push esi
        push ecx
        call tray_hit
        add esp, 16
        ret 8
    }
}

__declspec(naked) static void stub_tray_spot(void) {     /* esi = scene, [esp+4] x, [esp+8] y */
    __asm {
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        push esi
        call tray_spot
        add esp, 12
        ret 8
    }
}

__declspec(naked) static void stub_tray_draw(void) {     /* ecx = tray, esi = scene, [esp+4] skip */
    __asm {
        push dword ptr [esp + 4]
        push esi
        push ecx
        call tray_draw
        add esp, 12
        ret 4
    }
}

/* ------------------------------------------------------------ installing */

#define CODE_SITES 7
#define TABLE_SLOTS 2
#define TOTAL_SITES (CODE_SITES + TABLE_SLOTS)
static ftfp_site_write writes[TOTAL_SITES];
static unsigned char slot_expect[TABLE_SLOTS][4];

static int own_folder(wchar_t *out, DWORD cap) {
    wchar_t *slash;
    DWORD n = GetModuleFileNameW(self_module, out, cap);
    if (n == 0 || n >= cap || (slash = wcsrchr(out, L'\\')) == NULL) return 0;
    slash[1] = L'\0';
    return 1;
}

/* A table slot holds its stock function, or the wrapper of another companion DLL from
   this folder (one that installed before this one), which is then chained. */
static int known_slot(unsigned int va, unsigned int stock) {
    MEMORY_BASIC_INFORMATION info;
    wchar_t mine[1024], theirs[1024];
    wchar_t *slash;
    DWORD value, n;
    if (VirtualQuery((const void *)(UINT_PTR)va, &info, sizeof info) != sizeof info || info.State != MEM_COMMIT) return 0;
    value = *(const DWORD *)(UINT_PTR)va;
    if (value == stock) return 1;
    if (VirtualQuery((const void *)(UINT_PTR)value, &info, sizeof info) != sizeof info || info.AllocationBase == NULL
        || (HMODULE)info.AllocationBase == GetModuleHandleW(NULL) || (HMODULE)info.AllocationBase == self_module) {
        return 0;
    }
    n = GetModuleFileNameW((HMODULE)info.AllocationBase, theirs, 1024);
    if (n == 0 || n >= 1024 || (slash = wcsrchr(theirs, L'\\')) == NULL || !own_folder(mine, 1024)) return 0;
    slash[1] = L'\0';
    return lstrcmpiW(mine, theirs) == 0;
}

static int table_slot(ftfp_site_write *w, int i, unsigned int va, unsigned int stock, void **next, const void *to) {
    DWORD now, target = (DWORD)(UINT_PTR)to;
    if (!known_slot(va, stock)) {
        ftfp_failed_site = va;
        return 0;
    }
    now = *(const DWORD *)(UINT_PTR)va;
    memcpy(slot_expect[i], &now, 4);
    *next = (void *)(UINT_PTR)now;
    w->va = va;
    w->length = 4;
    w->expect = slot_expect[i];
    memcpy(w->bytes, &target, 4);
    return 1;
}

NOINLINE static int prepare(void) {
    ftfp_site_write *w = writes;
    ftfp_site_branch(w++, SITE_TOOL_HIT_VA, SITE_TOOL_HIT_LEN, SITE_TOOL_HIT_EXPECT, 0xE8, CODE_ADDR(tool_hit));
    ftfp_site_branch(w++, SITE_TRAY_HIT_VA, SITE_TRAY_HIT_LEN, SITE_TRAY_HIT_EXPECT, 0xE8, CODE_ADDR(stub_tray_hit));
    ftfp_site_branch(w++, SITE_TRAY_SPOT_VA, SITE_TRAY_SPOT_LEN, SITE_TRAY_SPOT_EXPECT, 0xE8, CODE_ADDR(stub_tray_spot));
    ftfp_site_branch(w++, SITE_TOOLS_DRAW_VA, SITE_TOOLS_DRAW_LEN, SITE_TOOLS_DRAW_EXPECT, 0xE8, CODE_ADDR(tools_draw));
    ftfp_site_branch(w++, SITE_TRAY_DRAW_VA, SITE_TRAY_DRAW_LEN, SITE_TRAY_DRAW_EXPECT, 0xE8, CODE_ADDR(stub_tray_draw));
    ftfp_site_branch(w++, SITE_TRAY_ADD_VA, SITE_TRAY_ADD_LEN, SITE_TRAY_ADD_EXPECT, 0xE9, CODE_ADDR(tray_add));
    ftfp_site_branch(w++, SITE_TRAY_ROOM_VA, SITE_TRAY_ROOM_LEN, SITE_TRAY_ROOM_EXPECT, 0xE9, CODE_ADDR(tray_room));
    if (!table_slot(w++, 0, SITE_GH_MOUSE_VA, SITE_GH_MOUSE_STOCK, (void **)&next_mouse, CODE_ADDR(gh_mouse))) return 0;
    if (!table_slot(w++, 1, SITE_GH_ACTIVATE_VA, SITE_GH_ACTIVATE_STOCK, (void **)&next_activate, CODE_ADDR(gh_activate))) {
        return 0;
    }
    return (int)(w - writes) == TOTAL_SITES;
}

NOINLINE static int install_all(void) {
    return prepare() && ftfp_install_sites(writes, TOTAL_SITES);
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

/* "<game>\Plant Tycoon Fix Patcher DLLs\Extra Chemical Slots.log". */
static void write_install_log(void) {
    wchar_t path[1024];
    char line[160];
    DWORD written;
    HANDLE file;
    int len = 0;
    if (!own_folder(path, 1024) || wcslen(path) + 32 >= 1024) return;
    wcscat_s(path, 1024, L"Extra Chemical Slots.log");
    if (installed) {
        len = append_text(line, len, "Extra Chemical Slots: installed (all sites)\r\n");
    } else if (ftfp_failed_site != 0) {
        len = append_text(line, len, "Extra Chemical Slots: NOT installed; the code at ");
        len = append_hex(line, len, ftfp_failed_site);
        len = append_text(line, len, " is not the stock code this build expects\r\n");
    } else {
        len = append_text(line, len, "Extra Chemical Slots: NOT installed\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* Called once by the startup loader before WinMain, after every other companion it loads
   (so the greenhouse table slots hold their wrappers, which this one chains). */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        installed = install_all();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    return installed;
}

/* ------------------------------------------------------------ for Store Upgrades and Items */

int __stdcall FtfpChemSlotsInstalled(void) { return installed; }

/* -1 not installed, else 1 when bought. */
int __cdecl FtfpChemSlotsOwned(void) { return installed ? owned : -1; }

int __cdecl FtfpChemSlotsBuy(void) {
    if (!installed || !ready) return 0;
    owned = 1;
    return 1;
}

/* The game is about to write slot `slot` (0 = its settings file). */
void __cdecl FtfpChemSlotsSave(char *state, int slot) {
    if (!installed || !ready) return;
    suspend(state);
    if (slot > 0) chem_file_write(slot, owned, ext);
}

/* The game loaded slot `slot` into the state. */
void __cdecl FtfpChemSlotsLoad(char *state, int slot) {
    if (!installed || slot <= 0) return;
    reset();
    chem_file_read(slot, &owned, ext);
    ready = 1;
    if (state != NULL) merge_duplicates(state);
}

void __cdecl FtfpChemSlotsDelete(int slot) {
    if (installed && slot > 0) chem_file_delete(slot);
}

void __cdecl FtfpChemSlotsNewGame(void) {
    if (!installed) return;
    reset();
    ready = 1;
}

/* For the tests: the page shown (0 or 1) and page 2's slot e. */
int __cdecl FtfpChemSlotsPage(void) { return page; }
const chem_record *__cdecl FtfpChemSlotsRecord(int e) { return e >= 0 && e < CHEM_PAGE_SLOTS ? &ext[e] : NULL; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        self_module = instance;
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
