/* Extra Greenhouses -- five more greenhouses of 15 pots in PC Plant Tycoon
   (six greenhouses, 90 pots).

   WHAT.  Gold arrows (the game's own leftarrow.png / rightarrow.png, the ones
   the Seed Storage screen uses for boxes 4-6) page the greenhouse screen
   through Greenhouse 1 (the stock one) to Greenhouse 6 and round again, and
   the screen says "Greenhouse n of 6".  Every greenhouse is the stock one:
   the same screen, pots, buttons, tools and tray, and the game's own code
   runs on its pots, so plants grow, age, need water and care, flower,
   pollinate, give seeds, get pests and die exactly as in the stock pots,
   including the catch-up of time away and the Time Warp.  A plant dragged onto
   an arrow moves to the same pot place in the greenhouse that arrow leads
   to, or to its first empty pot if that place is taken.  The nursery shows the plants for sale from every greenhouse, and the
   stock limit holds: at most 15 plants are for sale at once (the stock
   nursery's 15 spots), counted over all six greenhouses.

   HOW.  The game keeps its 15 pots in its state (state + 0x2188, 0x5600
   bytes each) and one plant object per pot in the plant manager
   ([0x493C80] + 8), each pointing at its pot's record (+8).  This DLL keeps
   the other 75 pots, and their plant objects, in its own memory.  Whatever
   screen is up, the pots it should see are moved into the state (an
   "arrangement"): the greenhouse on screen; in the nursery, Greenhouse 1's
   pots with the other greenhouses' plants for sale moved into its free
   spots; on every other screen, in every save and at every load, Greenhouse
   1 alone (the stock layout).  A move exchanges two records and their plant
   objects (re-pointed to their new records), and is undone exactly in
   reverse, so a plant never changes pot unless the game's own code moved it.
   The game's plant update (0x41D810) is wrapped: it runs once per
   greenhouse, each one moved in for its turn, so every pot gets the stock
   update with the stock clock.

   SAFETY.  The save always holds the stock layout: before the game writes
   it, Greenhouse 1 goes back in.  The five extra greenhouses are kept per
   slot in "<save folder>\Plant Tycoon Fix Patcher Data\Extra Greenhouses
   <slot>.dat", written to a temporary file and renamed over the old one.
   An unreadable file is set aside (".unreadable"), never overwritten.
   Every code site and vtable slot is checked before anything is written,
   and all of them are written or none (install_sites.h).

   The startup loader loads this DLL first when the setting is on; it loads
   "Unused Flowers.dll" (which loads the rest) or "Sort Seeds.dll" when they
   are beside it, and then installs, so it wraps whatever they installed. */
#include <windows.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "greenhouse_sites.h"
#include "../common/setting_file.h"

#define EXTRA 5
#define GREENHOUSES (EXTRA + 1)
#define POTS 15
#define COLUMNS 5
#define POT_BYTES 0x5600

#define STATE_POTS 0x2188
#define STATE_HELD 0x56C
#define STATE_SELECTED 0x63E58
#define NO_SELECTION 0x63
#define HELD_POT 0x3E8
#define HELD_POLLEN 9                    /* 0x42631F: pollen from the selected pot */
#define HELD_POT_SEEDS 0x14              /* 0x426228: seeds from the selected pot */

#define POT_STAMP 0x04
#define POT_AGE 0x10
#define POT_STYLE 0x18
#define POT_HEALTH 0x24
#define POT_PLANTED 0x38
#define POT_FOLIAGE 0x4C
#define POT_FOR_SALE 0x9D
#define POT_SOLD 0x9E
#define OBJECT_RECORD 8

#define MANAGER (*(char **)0x00493C80u)
#define GAME_STATE (*(char **)0x0049333Cu)
#define MATURE_AGE (*(const float *)0x004677E8u)     /* 24.0: the toggle's "old enough to sell" */
#define TEXT_COLOUR (*(int *)0x0048EA2Cu)

#define ARROW_PREV 40
#define ARROW_NEXT 41
#define ARROW_W 50
#define ARROW_H 50
/* The greenhouse's name and arrows, on the top wall between the stock left panel (to about x 240)
   and the camera button (from about x 760).  The name is centred at LABEL_X; at its widest,
   "Greenhouse 6 of 6", it is 154 px of PTfontsmall (x 423-577, y 26-47).  The arrows stand at
   fixed places just outside that, vertically centred on the text (x 367-416 and 583-632, y 11-60),
   clear of the greenhouse counts' "Counts: On" (x 646-744, y 4-24) and Plants line (y 62). */
#define LEFT_X 367
#define RIGHT_X 583
#define ARROW_Y 11
#define LABEL_X 500
#define LABEL_Y 26
#define NU_LEFT_X 220                    /* the nursery's arrows and label, in its sky */
#define NU_RIGHT_X 530
#define NU_ARROW_Y 4
#define NU_LABEL_X 400
#define NU_LABEL_Y 20
#define SOUND_BUTTON 0xC
#define SCENE_SOUND 0x74
#define SCENE_STATE 0x68
#define BUTTON_NURSERY 6
#define BUTTON_ALL_NURSERY 9
#define MOUSE_UP 3

#define NOINLINE __declspec(noinline)   /* keeps the name in the map file the tests read */
#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))

typedef void *(__cdecl *new_fn)(unsigned int size);
typedef void (__fastcall *file_button_fn)(void *button, int edx, int id, const char *file, int x, int y, void *parent, int zero);
typedef void (__fastcall *add_control_fn)(void *scene, int edx, void *control);
typedef void (__fastcall *sound_fn)(void *sound, int edx, int id);
typedef void *(__cdecl *graphics_fn)(void);
typedef void (__fastcall *text_fn)(void *graphics, int edx, const char *text, int x, int y, int colour, int font);
typedef int (__cdecl *random_fn)(int n);
typedef void (__fastcall *clear_pot_fn)(void *manager, int edx, int row, int column);
typedef void (__fastcall *deleting_dtor_fn)(void *object, int edx, int flags);

static const new_fn game_new = (new_fn)0x0044E894u;
static const file_button_fn file_button = (file_button_fn)0x00401AA0u;
static const add_control_fn add_control = (add_control_fn)0x0040B400u;
static const sound_fn play_sound = (sound_fn)0x0044A580u;
static const graphics_fn graphics = (graphics_fn)0x00407A90u;
typedef void *(__cdecl *sound_bank_fn)(void);
static const sound_bank_fn sound_bank = (sound_bank_fn)0x00449F00u;   /* the sound the nursery plays (0x435E7D) */
static const text_fn draw_text_centred = (text_fn)0x004092B0u;
static const random_fn game_random = (random_fn)0x004033B0u;
static const clear_pot_fn clear_pot = (clear_pot_fn)0x0042F410u;    /* the game's "empty this pot" */

typedef int (__fastcall *mouse_fn)(void *scene, int edx, int msg, int x, int y);
typedef int (__fastcall *command_fn)(void *scene, int edx, int msg, int id);
typedef void (__fastcall *plain_fn)(void *scene, int edx);
typedef void (__fastcall *activate_fn)(void *scene, int edx, int on);

/* ------------------------------------------------------------------ pots */

static unsigned char extra_pots[EXTRA][POTS][POT_BYTES];   /* home of Greenhouses 2-6 */
static void *extra_objects[EXTRA][POTS];                     /* their plant objects, while out */
static unsigned char swap_buffer[POT_BYTES];

/* 90 pot places ("positions"): 0-14 the game's own pots in the state, 15-89
   the DLL's (greenhouse g's pot k is at home at g * 15 + k).  An arrangement
   moves pot places around; at_pos / where_home say which home place is at
   which position, and undo lists the moves to take back, last first. */
#define POSITIONS (GREENHOUSES * POTS)
static unsigned char at_pos[POSITIONS], where_home[POSITIONS];
static int layout_ready = 0;
typedef struct swap_t { unsigned char a, b; } swap_t;
static swap_t undo[2 * POTS + 2];
static int undo_count = 0;

#define HOME 0
#define NURSERY 100                     /* NURSERY + n: the pots for sale in nursery n */
static int arranged = HOME;     /* HOME, 1..EXTRA (that greenhouse is in the state), NURSERY + n */
static int shown = 0;           /* the greenhouse on screen, 0..owned */
static int owned = 0;           /* extra greenhouses bought (Store Upgrades and Items.dll), 0..EXTRA, in order */
static int nurseries = 0;       /* extra nurseries bought, 0..EXTRA, in order */
static int nursery_shown = 0;   /* the nursery on screen, 0..nurseries */
static int greenhouses_on = 1;  /* "Extra Greenhouses.ini" beside this DLL (the setting) */
static int nurseries_on = 0;    /* "Extra Nurseries.ini" beside this DLL (the setting) */

/* Greenhouse 1 and the ones bought: the arrows page through these only. */
static int available(void) { return owned + 1; }
static int wrap(int g) { return (g % available() + available()) % available(); }
static int nurseries_available(void) { return nurseries + 1; }
static int nursery_wrap(int n) { return (n % nurseries_available() + nurseries_available()) % nurseries_available(); }
/* The stock nursery's 15 spots, and 15 more per extra nursery bought. */
static int for_sale_limit(void) { return POTS * nurseries_available(); }

static unsigned char scene_on[4];   /* [1] greenhouse, [2] nursery, [3] snapshot open */
static int current = 0;             /* the screen the game last drove */
static int moved_this_frame = 0;
static void *arrows[2], *nursery_arrows[2];
static int installed = 0;

static char *state_pot(char *state, int slot) { return state + STATE_POTS + slot * POT_BYTES; }

static void **manager_slot(int slot) {
    char *manager = MANAGER;
    return manager != NULL ? &AT(manager, 8 + slot * 4, void *) : NULL;
}

static void layout_identity(void) {
    int i;
    for (i = 0; i < POSITIONS; ++i) at_pos[i] = where_home[i] = (unsigned char)i;
    undo_count = 0;
    layout_ready = 1;
}

static char *pos_record(char *state, int pos) {
    return pos < POTS ? state_pot(state, pos) : (char *)extra_pots[pos / POTS - 1][pos % POTS];
}

static void **pos_object(int pos) {
    return pos < POTS ? manager_slot(pos) : &extra_objects[pos / POTS - 1][pos % POTS];
}

static void destroy_object(void *object) {
    if (object != NULL) ((deleting_dtor_fn)(AT(AT(object, 0, char *), 0, void *)))(object, 0, 1);
}

/* An object follows its record; one that does not point at it is rebuilt by the game. */
static void *repoint(void *object, void *from, void *to) {
    if (object == NULL) return NULL;
    if (AT(object, OBJECT_RECORD, void *) != from) {
        destroy_object(object);
        return NULL;
    }
    AT(object, OBJECT_RECORD, void *) = to;
    return object;
}

/* Positions a <-> b: the records and their plant objects (a state pot's object lives in the
   plant manager; with no manager yet, an object moving into the state is deleted). */
NOINLINE static void swap_pos(char *state, int a, int b) {
    char *ra = pos_record(state, a), *rb = pos_record(state, b);
    void **sa = pos_object(a), **sb = pos_object(b);
    void *oa = sa != NULL ? *sa : NULL, *ob = sb != NULL ? *sb : NULL;
    if (a == b) return;
    memcpy(swap_buffer, ra, POT_BYTES);
    memcpy(ra, rb, POT_BYTES);
    memcpy(rb, swap_buffer, POT_BYTES);
    oa = repoint(oa, ra, rb);
    ob = repoint(ob, rb, ra);
    if (sa != NULL) *sa = ob; else destroy_object(ob);
    if (sb != NULL) *sb = oa; else destroy_object(oa);
}

/* State pot `slot` <-> the DLL's pot (bank, pot), as before (contents only: the layout is unchanged). */
NOINLINE static void exchange(char *state, int slot, int bank, int pot) {
    swap_pos(state, slot, (bank + 1) * POTS + pot);
}

static void push_swap(char *state, int a, int b) {
    unsigned char t;
    if (!layout_ready) layout_identity();
    if (a == b) return;
    swap_pos(state, a, b);
    undo[undo_count].a = (unsigned char)a;
    undo[undo_count].b = (unsigned char)b;
    ++undo_count;
    t = at_pos[a];
    at_pos[a] = at_pos[b];
    at_pos[b] = t;
    where_home[at_pos[a]] = (unsigned char)a;
    where_home[at_pos[b]] = (unsigned char)b;
}

static void go_home(char *state) {
    if (!layout_ready) layout_identity();
    while (undo_count > 0) {
        swap_t e = undo[--undo_count];
        unsigned char t;
        swap_pos(state, e.a, e.b);
        t = at_pos[e.a];
        at_pos[e.a] = at_pos[e.b];
        at_pos[e.b] = t;
        where_home[at_pos[e.a]] = e.a;
        where_home[at_pos[e.b]] = e.b;
    }
    arranged = HOME;
}

/* Where greenhouse g's pot k is now, whatever the arrangement. */
static char *locate(char *state, int g, int k) {
    if (!layout_ready) layout_identity();
    return pos_record(state, where_home[g * POTS + k]);
}

static int for_sale(const char *pot) { return pot[POT_FOR_SALE] != 0; }

/* A nursery spot is taken by a plant for sale, and by one just sold until the nursery closes
   (the stock nursery empties sold pots then, 0x4363A3), so a sale never moves the others. */
static int in_nursery(const char *pot) { return for_sale(pot) || (pot[POT_SOLD] && pot[POT_PLANTED]); }

/* Which pot place stands in each spot of nursery `page` (or -1).  The plants for sale fill
   the nurseries in order: Nursery 1 first, a Greenhouse 1 plant at its own pot's spot as in
   the stock game, then the other greenhouses' plants, greenhouse by greenhouse and pot by
   pot, into the free spots of Nursery 1, then Nursery 2, and so on.  Read at home. */
static void nursery_spots(char *state, int page, int *spots) {
    int taken[GREENHOUSES][POTS];
    int home, p = 0, j = 0, k;
    memset(taken, 0xFF, sizeof taken);
    for (k = 0; k < POTS; ++k) {
        if (in_nursery(pos_record(state, k))) taken[0][k] = k;
    }
    for (home = POTS; home < POSITIONS; ++home) {
        if (!in_nursery(pos_record(state, home))) continue;
        while (p < nurseries_available() && taken[p][j] >= 0) {
            if (++j == POTS) { j = 0; ++p; }
        }
        if (p >= nurseries_available()) break;          /* every nursery is full: the limit */
        taken[p][j] = home;
    }
    for (k = 0; k < POTS; ++k) spots[k] = page < GREENHOUSES ? taken[page][k] : -1;
}

NOINLINE static void arrange(char *state, int kind) {
    int k;
    if (state == NULL || arranged == kind) return;
    go_home(state);
    if (kind >= 1 && kind <= EXTRA) {
        for (k = 0; k < POTS; ++k) push_swap(state, k, kind * POTS + k);
    } else if (kind >= NURSERY && kind <= NURSERY + EXTRA) {
        int spots[POTS];
        nursery_spots(state, kind - NURSERY, spots);
        for (k = 0; k < POTS; ++k) {
            if (spots[k] >= 0 && at_pos[k] != spots[k]) push_swap(state, k, where_home[spots[k]]);
        }
        /* A spot with no plant of this nursery shows no plant for sale: an unsold pot goes there. */
        for (k = 0; k < POTS; ++k) {
            int q;
            if (spots[k] >= 0 || !in_nursery(pos_record(state, k))) continue;
            for (q = POTS; q < POSITIONS && in_nursery(pos_record(state, q)); ++q) {
            }
            if (q < POSITIONS) push_swap(state, k, q);
        }
    }
    arranged = kind;
}

/* Which pots a screen wants.  Each screen is tracked on its own, so the order
   in which the game opens one screen and closes the other never matters:
   the screen the game is driving (the last one that ran) decides. */
static int kind_wants(int kind) { return kind == 2 ? NURSERY + nursery_shown : kind != 0 ? shown : HOME; }

static int wanted(void) {
    int kind;
    if (current != 0 && scene_on[current]) return kind_wants(current);
    for (kind = 1; kind <= 3; ++kind) {
        if (scene_on[kind]) return kind_wants(kind);
    }
    return HOME;
}

NOINLINE static void ensure(void) {
    char *state = GAME_STATE;
    if (state != NULL) arrange(state, wanted());
}

/* A call into screen `kind` (1 greenhouse, 2 nursery, 3 snapshot). */
static void enter(int kind) {
    scene_on[kind] = 1;
    current = kind;
    ensure();
}

static void leave(int kind) {
    scene_on[kind] = 0;
    if (current == kind) current = 0;
    ensure();
}

/* Plants for sale in all six greenhouses. */
NOINLINE static int count_for_sale(char *state) {
    int b, k, n = 0;
    for (k = 0; k < POTS; ++k) n += for_sale(state_pot(state, k));
    for (b = 0; b < EXTRA; ++b) {
        for (k = 0; k < POTS; ++k) n += for_sale((const char *)extra_pots[b][k]);
    }
    return n;
}

static int has_plants(int bank) {
    int k;
    for (k = 0; k < POTS; ++k) {
        if (AT(extra_pots[bank][k], POT_FOLIAGE, int) != 0 || extra_pots[bank][k][POT_PLANTED]) return 1;
    }
    return 0;
}

static void forget_objects(void) {
    int b, k;
    for (b = 0; b < EXTRA; ++b) {
        for (k = 0; k < POTS; ++k) {
            destroy_object(extra_objects[b][k]);
            extra_objects[b][k] = NULL;
        }
    }
}

/* Empty pots the way a new game leaves them: zero, with a random pot style. */
static void empty_banks(void) {
    int b, k;
    memset(extra_pots, 0, sizeof extra_pots);
    for (b = 0; b < EXTRA; ++b) {
        for (k = 0; k < POTS; ++k) AT(extra_pots[b][k], POT_STYLE, int) = game_random(6);
    }
}

/* A save was replaced in the state (load, new game): the DLL's layout is gone with it. */
static void reset_layout(void) {
    layout_identity();
    arranged = HOME;
    shown = 0;
    nursery_shown = 0;
    forget_objects();
}

/* ------------------------------------------------------------ the update */

typedef void (__fastcall *update_fn)(char *state, int edx);
static void stock_update(void);

/* 0x41D810: the stock update of the greenhouse in the state, then of each other greenhouse in turn. */
NOINLINE static void __cdecl on_update(char *state) {
    int keep = arranged, b;
    arrange(state, HOME);
    ((update_fn)(UINT_PTR)stock_update)(state, 0);
    for (b = 1; b <= EXTRA; ++b) {
        if (!has_plants(b - 1)) continue;               /* an empty pot has no plant to update */
        arrange(state, b);
        ((update_fn)(UINT_PTR)stock_update)(state, 0);
    }
    arrange(state, HOME);
    arrange(state, keep);
}

/* The Time Warp (Store Upgrades and Items.dll) moves every live pot's clock back by dt
   before it runs the update; this does the same for the extra greenhouses' pots. */
void __cdecl FtfpExtraGreenhousesWarp(unsigned int dt, unsigned int now) {
    char *state = GAME_STATE;
    int b, k, keep = arranged;
    if (state != NULL) arrange(state, HOME);
    for (b = 0; b < EXTRA; ++b) {
        for (k = 0; k < POTS; ++k) {
            unsigned char *pot = extra_pots[b][k];
            unsigned int stamp = AT(pot, POT_STAMP, unsigned int);
            if (AT(pot, POT_FOLIAGE, int) == 0 || stamp == 0 || AT(pot, POT_HEALTH, int) <= 0) continue;
            if (stamp > now) stamp = now;
            AT(pot, POT_STAMP, unsigned int) = stamp - dt;
        }
    }
    if (state != NULL) arrange(state, keep);
}

/* ---------------------------------------------------------------- messages */

/* The game's one-button box (0x42AB50 with "Your seed box is already full!",
   string 0x77, as the greenhouse uses it at 0x428202), showing this text. */
typedef void (__fastcall *box_fn)(void *dialog, int edx, int id, int a, int b, int c, int d);
typedef int (__fastcall *run_modal_fn)(void *dialog, int edx, void *parent, int zero);
typedef void (__fastcall *dialog_done_fn)(void *dialog, int edx);
static const box_fn build_box = (box_fn)0x0042AB50u;
static const run_modal_fn run_modal = (run_modal_fn)0x00401C90u;
static const dialog_done_fn dialog_done = (dialog_done_fn)0x0042AAA0u;
#define STRING_ENTRIES 0x00493CC0u
#define STR_BOX_FULL 0x77

static void tell(void *scene, const char *text) {
    static unsigned char dialog[0x1000];
    char *entry = *(char **)(UINT_PTR)(STRING_ENTRIES + STR_BOX_FULL * 4u);
    const char *saved;
    if (entry == NULL || AT(entry, 0, int) != STR_BOX_FULL) return;
    saved = AT(entry, 0xC, const char *);
    AT(entry, 0xC, const char *) = text;           /* only while the box copies its text */
    memset(dialog, 0, sizeof dialog);
    build_box(dialog, 0, STR_BOX_FULL, 0, 0, 0, 0);
    AT(entry, 0xC, const char *) = saved;
    run_modal(dialog, 0, scene, 0);
    dialog_done(dialog, 0);
}

/* "Your nursery is full! ..." with the limit: 15, and 15 more per extra nursery bought. */
static const char *nursery_full(void) {
    static char text[160];
    const char *head = nurseries == 0 ? "Your nursery is full!\n\nOnly " : "Your nurseries are full!\n\nOnly ";
    const char *tail = " plants can be for sale at once,\ncounting every greenhouse.";
    int n = 0, i, limit = for_sale_limit();
    for (i = 0; head[i]; ++i) text[n++] = head[i];
    if (limit >= 10) text[n++] = (char)('0' + limit / 10);
    text[n++] = (char)('0' + limit % 10);
    for (i = 0; tail[i]; ++i) text[n++] = tail[i];
    text[n] = '\0';
    return text;
}

/* -------------------------------------------------------------- greenhouse */

static mouse_fn next_gh_mouse, next_gh_key, next_nu_mouse, next_nu_key, next_sn_mouse, next_sn_key;
static command_fn next_gh_command, next_nu_command, next_sn_command;
static plain_fn next_gh_overlay, next_gh_draw, next_gh_tick, next_nu_draw, next_nu_overlay, next_nu_tick, next_sn_draw;
static activate_fn next_gh_activate, next_nu_activate, next_sn_activate;

/* Pollen taken in one greenhouse and carried to another: its donor stays the
   plant it came from (greenhouse pollen_g, pot pollen_k). */
static int pollen_g = -1, pollen_k = -1;

/* Seeds taken from a plant (0x426228; the pot's +0x90 seeds left and +0x94
   seeds taken are counted at once, 0x42625D) and carried to another
   greenhouse: wherever the game reads the selected pot's seed record (+0x54),
   or gives the seeds back (0x424480), it gets their own pot's. */
static int seed_g = -1, seed_k = -1;

/* Tools, chemicals and seed-tray seeds (Legendary Seeds too) belong to no
   pot and stay held, as they do while you move over one greenhouse: the
   arrows do not change screen (the stock game drops what you hold only when
   a screen opens: 0x423206 in the greenhouse's 0x4231E0, 0x4363C3 in the
   nursery's 0x4360D0). */
static void reset_hold(char *scene, char *state) {
    int held = AT(state, STATE_HELD, int), selected = AT(state, STATE_SELECTED, int);
    if ((held == HELD_POLLEN || held == HELD_POT_SEEDS) && selected >= 0 && selected < POTS) {
        int *g = held == HELD_POLLEN ? &pollen_g : &seed_g, *k = held == HELD_POLLEN ? &pollen_k : &seed_k;
        if (*g < 0) {
            *g = shown;
            *k = selected;
        }
    } else {
        /* A held plant belongs to its pot: it stays there (moving it is the drop on an arrow). */
        if (held >= HELD_POT) AT(state, STATE_HELD, int) = 0;
        AT(state, STATE_SELECTED, int) = NO_SELECTION;
        pollen_g = pollen_k = seed_g = seed_k = -1;
    }
    AT(scene, 8, unsigned char) = 0;           /* as after a drop (0x427467) */
    AT(scene, 0x104, unsigned char) = 0;       /* as on entering (0x42320D) */
    AT(scene, 0x105, unsigned char) = 0;
}

NOINLINE static void show_greenhouse(char *scene, int g) {
    char *state = AT(scene, SCENE_STATE, char *);
    reset_hold(scene, state);
    shown = wrap(g);
    ensure();
}

/* 0x425F54: the pollen drop's call of 0x4240A0(target, donor) (thiscall, ret 8). */
typedef void (__fastcall *pollinate_fn)(void *scene, int edx, char *target, char *donor);
static void __fastcall pollinate(void *scene, int edx, char *target, char *donor) {
    char *state = GAME_STATE;
    if (state != NULL && pollen_g >= 0 && pollen_g != shown && arranged == shown) {
        donor = locate(state, pollen_g, pollen_k);
    }
    pollen_g = pollen_k = -1;
    ((pollinate_fn)(UINT_PTR)0x004240A0u)(scene, edx, target, donor);
}

/* The carried seeds' own pot, or NULL when they come from a pot of the greenhouse on screen. */
static char *seed_source(void) {
    char *state = GAME_STATE;
    if (state == NULL || seed_g < 0 || seed_g == shown || arranged != shown) return NULL;
    return locate(state, seed_g, seed_k);
}

#define POT_SEED_RECORD 0x54
#define POT_SEED_VALUE 0x74
#define POT_SEEDS_LEFT 0x90
#define POT_SEEDS_TAKEN 0x94

/* 0x425C1B (planted) and 0x42819B (to the seed box): the seed record to copy. */
static char *__cdecl seed_record(char *stock) {
    char *pot = seed_source();
    return pot != NULL ? pot + POT_SEED_RECORD : stock;
}

/* 0x424711 (the trash): what the seeds are worth. */
static int __cdecl seed_value(int stock) {
    char *pot = seed_source();
    return pot != NULL ? AT(pot, POT_SEED_VALUE, int) : stock;
}

/* 0x424508 (put back): the seeds go back to their own pot, as 0x424480 does; 1 when done here. */
static int __cdecl seed_put_back(void) {
    char *pot = seed_source();
    if (pot == NULL) return 0;
    AT(pot, POT_SEEDS_TAKEN, int) -= 1;
    AT(pot, POT_SEEDS_LEFT, int) += 1;
    seed_g = seed_k = -1;
    return 1;
}

/* Sold plants leave their pots when the greenhouse opens (0x4231E0); the
   other greenhouses' sold plants leave theirs too, through the same call. */
static void clear_sold(char *state, int skip) {
    int g, k, keep = arranged;
    if (MANAGER == NULL) return;
    for (g = 0; g < GREENHOUSES; ++g) {
        if (g == skip) continue;
        arrange(state, g);
        for (k = 0; k < POTS; ++k) {
            char *pot = state_pot(state, k);
            if (pot[POT_SOLD] && pot[POT_PLANTED]) clear_pot(MANAGER, 0, k / COLUMNS, k % COLUMNS);
        }
    }
    arrange(state, keep);
}

NOINLINE static void clear_sold_elsewhere(char *state) { clear_sold(state, shown); }

/* The nursery closes: as the stock close empties its sold pots (0x4363A3), every nursery's go. */
NOINLINE static void clear_sold_everywhere(char *state) { clear_sold(state, -1); }

/* A held plant dropped on an arrow: into the same pot place of that
   greenhouse if it is empty, else its first empty pot. */
static int pot_empty(const char *pot) { return AT(pot, POT_FOLIAGE, int) == 0 && !pot[POT_PLANTED]; }

static int target_pot(char *state, int g, int same) {
    int k;
    if (pot_empty(locate(state, g, same))) return same;
    for (k = 0; k < POTS; ++k) {
        if (pot_empty(locate(state, g, k))) return k;
    }
    return -1;
}

NOINLINE static void carry_plant(char *scene, int to) {
    static char text[160];
    char *state = AT(scene, SCENE_STATE, char *);
    int from = AT(state, STATE_HELD, int) - HELD_POT, g = wrap(to), k;
    ensure();
    if (from < 0 || from >= POTS || arranged != shown || g == shown) return;
    k = target_pot(state, g, from);
    if (k < 0) {
        int n = 0, i;
        const char *head = "Greenhouse ", *tail = " is full!\n\nThere is no empty pot to move\nthis plant to.";
        for (i = 0; head[i]; ++i) text[n++] = head[i];
        text[n++] = (char)('1' + g);
        for (i = 0; tail[i]; ++i) text[n++] = tail[i];
        text[n] = '\0';
        reset_hold(scene, state);
        tell(scene, text);
        return;
    }
    /* Exchange the two pots' contents; the undo list keeps each position's greenhouse. */
    swap_pos(state, from, where_home[g * POTS + k]);       /* the contents; each place keeps its greenhouse */
    play_sound(AT(scene, SCENE_SOUND, void *), 0, SOUND_BUTTON);
    show_greenhouse(scene, g);
}

static int in_arrow(int i, int x, int y) {
    int left = i == 0 ? LEFT_X : RIGHT_X;
    return x >= left && x < left + ARROW_W && y >= ARROW_Y && y < ARROW_Y + ARROW_H;
}

static int __fastcall gh_mouse(char *scene, int edx, int msg, int x, int y) {
    char *state = AT(scene, SCENE_STATE, char *);
    enter(1);
    if (msg == MOUSE_UP && owned > 0 && state != NULL && AT(state, STATE_HELD, int) >= HELD_POT
        && AT(state, STATE_HELD, int) < HELD_POT + POTS) {
        int i;
        for (i = 0; i < 2; ++i) {
            if (in_arrow(i, x, y)) {
                carry_plant(scene, shown + (i == 0 ? -1 : 1));
                moved_this_frame = 1;
                return 1;
            }
        }
    }
    return next_gh_mouse(scene, edx, msg, x, y);
}

static int __fastcall gh_key(char *scene, int edx, int msg, int a, int b) {
    enter(1);
    return next_gh_key(scene, edx, msg, a, b);
}

static int sellable(const char *pot) {
    return pot[POT_PLANTED] && AT(pot, POT_FOLIAGE, int) != 0 && AT(pot, POT_AGE, float) >= MATURE_AGE
           && AT(pot, POT_HEALTH, int) > 0;
}

static int __fastcall gh_command(char *scene, int edx, int msg, int id) {
    char *state = AT(scene, SCENE_STATE, char *);
    enter(1);
    if (msg == 8 && (id == ARROW_PREV || id == ARROW_NEXT)) {
        if (!moved_this_frame && owned > 0) {                  /* hidden until one is bought */
            play_sound(AT(scene, SCENE_SOUND, void *), 0, SOUND_BUTTON);
            show_greenhouse(scene, shown + (id == ARROW_PREV ? -1 : 1));
        }
        return 1;
    }
    if (msg == 8 && id == BUTTON_NURSERY && state != NULL) {
        int selected = AT(state, STATE_SELECTED, int);
        if (selected >= 0 && selected < POTS) {
            char *pot = state_pot(state, selected);
            if (!for_sale(pot) && sellable(pot) && count_for_sale(state) >= for_sale_limit()) {
                play_sound(AT(scene, SCENE_SOUND, void *), 0, SOUND_BUTTON);
                tell(scene, nursery_full());
                return 1;
            }
        }
    }
    if (msg == 8 && id == BUTTON_ALL_NURSERY && state != NULL) {
        unsigned char before[POTS];
        int k, r, trimmed = 0;
        for (k = 0; k < POTS; ++k) before[k] = (unsigned char)for_sale(state_pot(state, k));
        r = next_gh_command(scene, edx, msg, id);
        for (k = POTS - 1; k >= 0 && count_for_sale(state) > for_sale_limit(); --k) {
            char *pot = state_pot(state, k);
            if (!before[k] && for_sale(pot)) {
                pot[POT_FOR_SALE] = 0;
                trimmed = 1;
            }
        }
        if (trimmed) tell(scene, nursery_full());
        return r;
    }
    return next_gh_command(scene, edx, msg, id);
}

static void __fastcall gh_overlay(char *scene, int edx) { enter(1); next_gh_overlay(scene, edx); }

/* "Greenhouse n", and " of m" once more than one is owned (m the greenhouses owned, 1 + bought). */
NOINLINE static const char *screen_label(const char *name, int n, int of) {
    static char label[32];
    int at = 0, i;
    for (i = 0; name[i]; ++i) label[at++] = name[i];
    label[at++] = ' ';
    label[at++] = (char)('1' + n);
    if (of > 1) {
        label[at++] = ' ';
        label[at++] = 'o';
        label[at++] = 'f';
        label[at++] = ' ';
        label[at++] = (char)('0' + of);
    }
    label[at] = '\0';
    return label;
}

/* The owner's name label on every greenhouse screen, the stock one too ("Greenhouse 1"). */
static void __fastcall gh_draw(char *scene, int edx) {
    enter(1);
    next_gh_draw(scene, edx);
    if (!greenhouses_on) return;
    draw_text_centred(graphics(), 0, screen_label("Greenhouse", shown, available()), LABEL_X, LABEL_Y,
                      TEXT_COLOUR, 0);
}

static void __fastcall gh_tick(char *scene, int edx) {
    char *state = AT(scene, SCENE_STATE, char *);
    moved_this_frame = 0;
    if (state != NULL && AT(state, STATE_HELD, int) != HELD_POLLEN) pollen_g = pollen_k = -1;
    if (state != NULL && AT(state, STATE_HELD, int) != HELD_POT_SEEDS) seed_g = seed_k = -1;
    enter(1);
    next_gh_tick(scene, edx);
}

/* The arrows show once an extra greenhouse is owned (a control's +8 is its visible byte, as the
   Seed Boxes DLL shows its arrows). */
static void show_arrows(void) {
    int i;
    for (i = 0; i < 2; ++i) {
        if (arrows[i] != NULL) AT(arrows[i], 8, unsigned char) = (unsigned char)(owned > 0);
    }
}

static void __fastcall gh_activate(char *scene, int edx, int on) {
    char *state = AT(scene, SCENE_STATE, char *);
    if (on) {
        enter(1);
        if (state != NULL) clear_sold_elsewhere(state);
        next_gh_activate(scene, edx, on);
        if (arrows[0] == NULL) {
            static const char *const files[2] = { "leftarrow.png", "rightarrow.png" };
            static const int ids[2] = { ARROW_PREV, ARROW_NEXT }, xs[2] = { LEFT_X, RIGHT_X };
            int i;
            for (i = 0; i < 2; ++i) {
                void *button = game_new(0x14);
                if (button == NULL) break;
                file_button(button, 0, ids[i], files[i], xs[i], ARROW_Y, scene, 0);
                add_control(scene, 0, button);
                arrows[i] = button;
            }
        }
        show_arrows();
    } else {
        next_gh_activate(scene, edx, on);
        pollen_g = pollen_k = seed_g = seed_k = -1;
        leave(1);
    }
}

/* ----------------------------------------------------- nursery and snapshot */

/* Every bought nursery sells at once (the owner's choice).  The nursery tick (0x437950) runs the
   stock buy roll 0x436BE0(visitors browsing) every 2 seconds: for the nursery on screen, then, with
   each other nursery's plants moved into the 15 spots for that one call, once for each other
   nursery, with the same visitors.  So every plant for sale gets the stock roll, prices and
   effects.  Visitors are only the screen's: an off-screen sale hands no plant to a visitor (the
   sale's visitor count reads 0), and its "+$" marker (the sale ring at nursery + 0x10..0x57) is
   not shown on the screen's plants.  With no nursery bought this is the stock roll alone. */
typedef void (__fastcall *roll_fn)(void *scene, int edx, int browsing);
typedef int (__fastcall *count_fn)(void *list, int edx);
#define NURSERY_SALE_RING 0x10
#define NURSERY_SALE_RING_BYTES 0x48
static int offscreen_sale = 0;

static int __fastcall sale_visitors(void *list, int edx) {
    return offscreen_sale ? 0 : ((count_fn)(UINT_PTR)0x0043ACD0u)(list, edx);
}

NOINLINE static void __fastcall sales_roll(char *scene, int edx, int browsing) {
    unsigned char ring[NURSERY_SALE_RING_BYTES];
    char *state = GAME_STATE;
    int n, keep = arranged;
    ((roll_fn)(UINT_PTR)0x00436BE0u)(scene, edx, browsing);
    if (state == NULL || !nurseries_on || nurseries == 0 || arranged != NURSERY + nursery_shown) return;
    memcpy(ring, scene + NURSERY_SALE_RING, sizeof ring);
    offscreen_sale = 1;
    for (n = 0; n <= nurseries; ++n) {
        if (n == nursery_shown) continue;
        arrange(state, NURSERY + n);
        ((roll_fn)(UINT_PTR)0x00436BE0u)(scene, edx, browsing);
    }
    offscreen_sale = 0;
    memcpy(scene + NURSERY_SALE_RING, ring, sizeof ring);
    arrange(state, keep);
}


static int __fastcall nu_mouse(char *s, int e, int m, int x, int y) { enter(2); return next_nu_mouse(s, e, m, x, y); }
static int __fastcall nu_key(char *s, int e, int m, int a, int b) { enter(2); return next_nu_key(s, e, m, a, b); }
/* The nursery screen's arrows, once an extra nursery is owned. */
static void show_nursery_arrows(void) {
    int i;
    for (i = 0; i < 2; ++i) {
        if (nursery_arrows[i] != NULL) AT(nursery_arrows[i], 8, unsigned char) = (unsigned char)(nurseries > 0);
    }
}

/* Another nursery: the stock nursery closes (its sold plants leave their pots) and the next one
   opens with its own plants for sale, visitors and prices, exactly as on entering a nursery. */
/* Another nursery: only the plants on the 15 stands change.  The visitors, their places, states and
   timers, the visitor limit and the browsing count the buy rolls use all stay exactly as they are:
   nothing of the nursery scene is touched.  No visitor holds a plant: a visitor's comment picks a
   stand and reads its plant there and then (0x4399D5), a buy roll goes stand by stand (0x436BE0),
   and a sale pays and marks its pot at once (0x435C70), so the new plants are simply what the
   visitors find on the stands.  A plant held to rearrange the nursery is put back first (its index
   is a stand of this nursery), as the stock close does (0x4363C3). */
NOINLINE static void show_nursery(char *s, int e, int n) {
    char *state = GAME_STATE;
    (void)s;
    (void)e;
    if (state != NULL && AT(state, STATE_HELD, int) >= HELD_POT) AT(state, STATE_HELD, int) = 0;
    nursery_shown = nursery_wrap(n);
    enter(2);
}

static int __fastcall nu_command(char *s, int e, int m, int id) {
    enter(2);
    if (m == 8 && (id == ARROW_PREV || id == ARROW_NEXT)) {
        if (nurseries > 0) {
            play_sound(sound_bank(), 0, SOUND_BUTTON);
            show_nursery(s, e, nursery_shown + (id == ARROW_PREV ? -1 : 1));
        }
        return 1;
    }
    return next_nu_command(s, e, m, id);
}

/* "Nursery n" on every nursery screen, the stock one too ("Nursery 1"). */
static void __fastcall nu_draw(char *s, int e) {
    enter(2);
    next_nu_draw(s, e);
    if (!nurseries_on) return;
    draw_text_centred(graphics(), 0, screen_label("Nursery", nursery_shown, nurseries_available()), NU_LABEL_X,
                      NU_LABEL_Y, TEXT_COLOUR, 0);
}
static void __fastcall nu_overlay(char *s, int e) { enter(2); next_nu_overlay(s, e); }
static void __fastcall nu_tick(char *s, int e) { enter(2); next_nu_tick(s, e); }

/* The nursery counts its plants for sale (the visitor limit) as it opens, and
   empties the sold pots as it closes: both on the arranged pots. */
static void __fastcall nu_activate(char *s, int e, int on) {
    if (on) {
        if (nursery_shown > nurseries) nursery_shown = 0;
        enter(2);
        next_nu_activate(s, e, on);
        if (nursery_arrows[0] == NULL) {
            static const char *const files[2] = { "leftarrow.png", "rightarrow.png" };
            static const int ids[2] = { ARROW_PREV, ARROW_NEXT }, xs[2] = { NU_LEFT_X, NU_RIGHT_X };
            int i;
            for (i = 0; i < 2; ++i) {
                void *button = game_new(0x14);
                if (button == NULL) break;
                file_button(button, 0, ids[i], files[i], xs[i], NU_ARROW_Y, s, 0);
                add_control(s, 0, button);
                nursery_arrows[i] = button;
            }
        }
        show_nursery_arrows();
    } else {
        char *state = GAME_STATE;
        next_nu_activate(s, e, on);
        leave(2);
        if (state != NULL && nurseries_on && nurseries > 0) clear_sold_everywhere(state);
    }
}

static int __fastcall sn_mouse(char *s, int e, int m, int x, int y) { enter(3); return next_sn_mouse(s, e, m, x, y); }
static int __fastcall sn_key(char *s, int e, int m, int a, int b) { enter(3); return next_sn_key(s, e, m, a, b); }
static int __fastcall sn_command(char *s, int e, int m, int id) { enter(3); return next_sn_command(s, e, m, id); }
static void __fastcall sn_draw(char *s, int e) { enter(3); next_sn_draw(s, e); }

/* The snapshot (F1 in the greenhouse) shows the greenhouse that was on screen. */
static void __fastcall sn_activate(char *s, int e, int on) {
    if (on) {
        enter(3);
        next_sn_activate(s, e, on);
    } else {
        next_sn_activate(s, e, on);
        leave(3);
    }
}

/* ----------------------------------------------------------------- sidecar */

#define SIDECAR_MAGIC 0x47585450u      /* "PTXG" */
#define SIDECAR_VERSION 1u
typedef BOOL (WINAPI *special_folder_fn)(HWND, LPWSTR, int, BOOL);

/* "<Documents>\LDW\<exe name>\Plant Tycoon Fix Patcher Data\Extra Greenhouses <slot>.dat". */
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
    if (wcslen(out) + wcslen(name) + 100 >= cap) return 0;
    wcscat_s(out, cap, L"\\LDW\\");
    wcscat_s(out, cap, name);
    wcscat_s(out, cap, L"\\Plant Tycoon Fix Patcher Data");
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\Extra Greenhouses ");
    {
        wchar_t digits[12];
        int i = 0, v = slot;
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 11);
        while (i) { size_t len = wcslen(out); out[len] = digits[--i]; out[len + 1] = L'\0'; }
    }
    wcscat_s(out, cap, L".dat");
    return 1;
}

/* Header: magic, version, greenhouses kept, pots each, bytes per pot. */
#define HEADER_WORDS 7

NOINLINE static int write_sidecar(int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    DWORD header[HEADER_WORDS], written;
    int ok;
    if (slot <= 0 || !sidecar_path(slot, path, 1024, 1)) return 0;
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    header[0] = SIDECAR_MAGIC;
    header[1] = SIDECAR_VERSION;
    header[2] = EXTRA;
    header[3] = POTS;
    header[4] = POT_BYTES;
    header[5] = (DWORD)owned;
    header[6] = (DWORD)nurseries;
    ok = WriteFile(file, header, sizeof header, &written, NULL) && written == sizeof header
         && WriteFile(file, extra_pots, sizeof extra_pots, &written, NULL) && written == sizeof extra_pots
         && FlushFileBuffers(file);
    CloseHandle(file);
    if (ok) ok = MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
    if (!ok) DeleteFileW(temp);
    return ok;
}

/* 1 read, 0 no file (empty greenhouses), -1 unreadable (set aside). */
NOINLINE static int read_sidecar(int slot) {
    static unsigned char body[sizeof extra_pots];
    wchar_t path[1024];
    HANDLE file;
    DWORD header[HEADER_WORDS], got;
    LARGE_INTEGER size;
    int ok;
    if (slot <= 0 || !sidecar_path(slot, path, 1024, 0)) return 0;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    ok = GetFileSizeEx(file, &size) && size.QuadPart == (LONGLONG)(sizeof header + sizeof body)
         && ReadFile(file, header, sizeof header, &got, NULL) && got == sizeof header
         && header[0] == SIDECAR_MAGIC && header[1] == SIDECAR_VERSION && header[2] == EXTRA
         && header[3] == POTS && header[4] == POT_BYTES && header[5] <= EXTRA && header[6] <= EXTRA
         && ReadFile(file, body, sizeof body, &got, NULL) && got == sizeof body;
    CloseHandle(file);
    if (!ok) {
        wchar_t aside[1100];
        wcscpy_s(aside, 1100, path);
        wcscat_s(aside, 1100, L".unreadable");
        MoveFileExW(path, aside, MOVEFILE_REPLACE_EXISTING);
        return -1;
    }
    memcpy(extra_pots, body, sizeof body);
    owned = (int)header[5];
    nurseries = (int)header[6];
    return 1;
}

static int last_sidecar = 0;

/* Before the game writes its save: Greenhouse 1 back in the state, the others to the sidecar. */
NOINLINE static void __cdecl before_save(char *state, int slot) {
    if (slot <= 0) return;
    arrange(state, HOME);
    last_sidecar = write_sidecar(slot) ? 1 : -1;
}

static void __cdecl after_save(void) { ensure(); }

NOINLINE static void __cdecl on_loaded(char *state, int slot) {
    int b;
    (void)state;
    reset_layout();
    owned = nurseries = 0;
    if (read_sidecar(slot) != 1) empty_banks();
    for (b = EXTRA; b > owned; --b) {                     /* a greenhouse with plants is never locked away */
        if (has_plants(b - 1)) owned = b;
    }
    if (!greenhouses_on) owned = 0;                       /* the setting off: kept in the file, not shown */
    if (!nurseries_on) nurseries = 0;
    show_arrows();
    show_nursery_arrows();
}

static void __cdecl on_new_game(void) {
    reset_layout();
    owned = nurseries = 0;
    empty_banks();
    show_arrows();
    show_nursery_arrows();
}

/* For Store Upgrades and Items.dll: how many extra greenhouses are bought, and buy the next. */
/* -1 when that setting is off (the store then offers nothing). */
int __cdecl FtfpExtraGreenhousesOwned(void) { return greenhouses_on ? owned : -1; }

int __cdecl FtfpExtraGreenhousesBuy(void) {
    if (greenhouses_on && owned < EXTRA) ++owned;
    show_arrows();
    return owned;
}

int __cdecl FtfpExtraNurseriesOwned(void) { return nurseries_on ? nurseries : -1; }

int __cdecl FtfpExtraNurseriesBuy(void) {
    if (nurseries_on && nurseries < EXTRA) ++nurseries;
    show_nursery_arrows();
    return nurseries;
}

static void __cdecl on_delete(int slot) {
    wchar_t path[1024];
    if (slot > 0 && sidecar_path(slot, path, 1024, 0)) DeleteFileW(path);
}

/* ------------------------------------------------------------------- stubs */

static const DWORD k_update_back = SITE_PLANT_UPDATE_BACK;
static const DWORD k_clock = 0x00403430u;
static const DWORD k_write = 0x00403690u;
static const DWORD k_manager = 0x0042FBC0u;
static const DWORD k_rebuild = 0x0042FC40u;
static const DWORD k_load_back = SITE_LOAD_DONE_BACK;
static const DWORD k_seed_plant_back = SITE_SEED_PLANT_BACK;
static const DWORD k_seed_box_back = SITE_SEED_BOX_BACK;
static const DWORD k_seed_trash_back = SITE_SEED_TRASH_BACK;
static const DWORD k_seed_return_back = SITE_SEED_RETURN_BACK;
static const DWORD k_seed_return_done = 0x004245DDu;    /* 0x4244C0's end: nothing held, nothing animated */

/* 0x425C1B: esi = the seed record to plant (stock: the selected pot's +0x54). */
__declspec(naked) static void stub_seed_plant(void) {
    __asm {
        lea esi, [edx + eax + 0x21DC]
        push eax
        push ecx
        push edx
        push esi
        call seed_record
        add esp, 4
        mov esi, eax
        pop edx
        pop ecx
        pop eax
        jmp dword ptr [k_seed_plant_back]
    }
}

/* 0x42819B: esi = the seed record for the seed box. */
__declspec(naked) static void stub_seed_box(void) {
    __asm {
        lea esi, [edx + ecx + 0x21DC]
        push eax
        push ecx
        push edx
        push esi
        call seed_record
        add esp, 4
        mov esi, eax
        pop edx
        pop ecx
        pop eax
        jmp dword ptr [k_seed_box_back]
    }
}

/* 0x424711: ebx = what the seeds are worth in the trash. */
__declspec(naked) static void stub_seed_trash(void) {
    __asm {
        mov ebx, dword ptr [ecx + edi + 0x21FC]
        push eax
        push ecx
        push edx
        push ebx
        call seed_value
        add esp, 4
        mov ebx, eax
        pop edx
        pop ecx
        pop eax
        jmp dword ptr [k_seed_trash_back]
    }
}

/* 0x424508 in 0x4244C0 (put the held item back), held seeds: carried ones go back to their own pot. */
__declspec(naked) static void stub_seed_return(void) {
    __asm {
        push eax
        push ecx
        push edx
        call seed_put_back
        test eax, eax
        pop edx
        pop ecx
        pop eax
        jnz handled
        mov ebp, dword ptr [ecx + 0x63E58]
        jmp dword ptr [k_seed_return_back]
    handled:
        jmp dword ptr [k_seed_return_done]
    }
}

/* The stock 0x41D810 (thiscall, ecx = state). */
__declspec(naked) static void stock_update(void) {
    __asm {
        push esi
        mov esi, ecx
        call dword ptr [k_clock]
        jmp dword ptr [k_update_back]
    }
}

__declspec(naked) static void stub_update(void) {
    __asm {
        push ecx
        call on_update
        add esp, 4
        ret
    }
}

/* 0x41D156 in save(slot): ecx = state, edx = slot, [esp] = the save's return. */
__declspec(naked) static void stub_save(void) {
    __asm {
        push ecx
        push edx
        push edx
        push ecx
        call before_save
        add esp, 8
        pop edx
        pop ecx
        push edx
        push 0x53FB0
        lea eax, [ecx + 8]
        push eax
        call dword ptr [k_write]
        push eax
        call after_save
        pop eax
        ret 4
    }
}

/* 0x41EEFE in load(slot): ebx = state, the slot at [esp + 0x5407C]. */
__declspec(naked) static void stub_load(void) {
    __asm {
        mov eax, [esp + 0x5407C]
        push eax
        push ebx
        call on_loaded
        add esp, 8
        call dword ptr [k_manager]
        mov ecx, eax
        call dword ptr [k_rebuild]
        jmp dword ptr [k_load_back]
    }
}

/* 0x41D3DC: the new game's call of 0x42F630 (thiscall, ecx = the plant manager). */
typedef void (__fastcall *manager_fn)(void *manager, int edx);
static void __fastcall new_game_clear(void *manager, int edx) {
    on_new_game();
    ((manager_fn)(UINT_PTR)0x0042F630u)(manager, edx);
}

/* 0x415F5E: the slot menu's call of 0x41D1F0(slot) (thiscall, ret 4). */
typedef int (__fastcall *delete_fn)(void *state, int edx, int slot);
static int __fastcall delete_slot(void *state, int edx, int slot) {
    on_delete(slot);
    return ((delete_fn)(UINT_PTR)0x0041D1F0u)(state, edx, slot);
}

/* ----------------------------------------------------------------- install */

#define CODE_ADDR(f) ((const void *)(UINT_PTR)(f))
#define CODE_SITES 12
#define VTABLE_SLOTS 19
#define TOTAL_SITES (CODE_SITES + VTABLE_SLOTS)
static ftfp_site_write writes[TOTAL_SITES];
static unsigned char slot_expect[VTABLE_SLOTS][4];
static HMODULE self_module = NULL;

typedef struct slot_t {
    unsigned int va, stock;
    void **next;
    const void *wrapper;
} slot_t;

static const slot_t SLOTS[VTABLE_SLOTS] = {
    { SLOT_GH_MOUSE_VA, SLOT_GH_MOUSE_STOCK, (void **)&next_gh_mouse, CODE_ADDR(gh_mouse) },
    { SLOT_GH_KEY_VA, SLOT_GH_KEY_STOCK, (void **)&next_gh_key, CODE_ADDR(gh_key) },
    { SLOT_GH_COMMAND_VA, SLOT_GH_COMMAND_STOCK, (void **)&next_gh_command, CODE_ADDR(gh_command) },
    { SLOT_GH_OVERLAY_VA, SLOT_GH_OVERLAY_STOCK, (void **)&next_gh_overlay, CODE_ADDR(gh_overlay) },
    { SLOT_GH_DRAW_VA, SLOT_GH_DRAW_STOCK, (void **)&next_gh_draw, CODE_ADDR(gh_draw) },
    { SLOT_GH_TICK_VA, SLOT_GH_TICK_STOCK, (void **)&next_gh_tick, CODE_ADDR(gh_tick) },
    { SLOT_GH_ACTIVATE_VA, SLOT_GH_ACTIVATE_STOCK, (void **)&next_gh_activate, CODE_ADDR(gh_activate) },
    { SLOT_NU_MOUSE_VA, SLOT_NU_MOUSE_STOCK, (void **)&next_nu_mouse, CODE_ADDR(nu_mouse) },
    { SLOT_NU_KEY_VA, SLOT_NU_KEY_STOCK, (void **)&next_nu_key, CODE_ADDR(nu_key) },
    { SLOT_NU_COMMAND_VA, SLOT_NU_COMMAND_STOCK, (void **)&next_nu_command, CODE_ADDR(nu_command) },
    { SLOT_NU_DRAW_VA, SLOT_NU_DRAW_STOCK, (void **)&next_nu_draw, CODE_ADDR(nu_draw) },
    { SLOT_NU_OVERLAY_VA, SLOT_NU_OVERLAY_STOCK, (void **)&next_nu_overlay, CODE_ADDR(nu_overlay) },
    { SLOT_NU_TICK_VA, SLOT_NU_TICK_STOCK, (void **)&next_nu_tick, CODE_ADDR(nu_tick) },
    { SLOT_NU_ACTIVATE_VA, SLOT_NU_ACTIVATE_STOCK, (void **)&next_nu_activate, CODE_ADDR(nu_activate) },
    { SLOT_SN_MOUSE_VA, SLOT_SN_MOUSE_STOCK, (void **)&next_sn_mouse, CODE_ADDR(sn_mouse) },
    { SLOT_SN_KEY_VA, SLOT_SN_KEY_STOCK, (void **)&next_sn_key, CODE_ADDR(sn_key) },
    { SLOT_SN_COMMAND_VA, SLOT_SN_COMMAND_STOCK, (void **)&next_sn_command, CODE_ADDR(sn_command) },
    { SLOT_SN_DRAW_VA, SLOT_SN_DRAW_STOCK, (void **)&next_sn_draw, CODE_ADDR(sn_draw) },
    { SLOT_SN_ACTIVATE_VA, SLOT_SN_ACTIVATE_STOCK, (void **)&next_sn_activate, CODE_ADDR(sn_activate) },
};

/* The folder this DLL is in (with the trailing backslash). */
static int own_folder(wchar_t *out, DWORD cap) {
    wchar_t *slash;
    DWORD n = GetModuleFileNameW(self_module, out, cap);
    if (n == 0 || n >= cap || (slash = wcsrchr(out, L'\\')) == NULL) return 0;
    slash[1] = L'\0';
    return 1;
}

/* A slot holds its stock function, or the wrapper of another companion DLL
   from this folder (one that loaded before this one), which is then chained. */
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

NOINLINE static int prepare(void) {
    ftfp_site_write *w = writes;
    int i;
    ftfp_site_branch(w++, SITE_PLANT_UPDATE_VA, SITE_PLANT_UPDATE_LEN, SITE_PLANT_UPDATE_EXPECT, 0xE9, CODE_ADDR(stub_update));
    ftfp_site_branch(w++, SITE_SAVE_WRITE_VA, SITE_SAVE_WRITE_LEN, SITE_SAVE_WRITE_EXPECT, 0xE9, CODE_ADDR(stub_save));
    ftfp_site_branch(w++, SITE_LOAD_DONE_VA, SITE_LOAD_DONE_LEN, SITE_LOAD_DONE_EXPECT, 0xE9, CODE_ADDR(stub_load));
    ftfp_site_branch(w++, SITE_NEW_GAME_CLEAR_VA, SITE_NEW_GAME_CLEAR_LEN, SITE_NEW_GAME_CLEAR_EXPECT, 0xE8,
                     CODE_ADDR(new_game_clear));
    ftfp_site_branch(w++, SITE_DELETE_SLOT_VA, SITE_DELETE_SLOT_LEN, SITE_DELETE_SLOT_EXPECT, 0xE8, CODE_ADDR(delete_slot));
    ftfp_site_branch(w++, SITE_POLLINATE_CALL_VA, SITE_POLLINATE_CALL_LEN, SITE_POLLINATE_CALL_EXPECT, 0xE8,
                     CODE_ADDR(pollinate));
    ftfp_site_branch(w++, SITE_SEED_PLANT_VA, SITE_SEED_PLANT_LEN, SITE_SEED_PLANT_EXPECT, 0xE9,
                     CODE_ADDR(stub_seed_plant));
    ftfp_site_branch(w++, SITE_SEED_BOX_VA, SITE_SEED_BOX_LEN, SITE_SEED_BOX_EXPECT, 0xE9, CODE_ADDR(stub_seed_box));
    ftfp_site_branch(w++, SITE_SEED_TRASH_VA, SITE_SEED_TRASH_LEN, SITE_SEED_TRASH_EXPECT, 0xE9,
                     CODE_ADDR(stub_seed_trash));
    ftfp_site_branch(w++, SITE_SEED_RETURN_VA, SITE_SEED_RETURN_LEN, SITE_SEED_RETURN_EXPECT, 0xE9,
                     CODE_ADDR(stub_seed_return));
    ftfp_site_branch(w++, SITE_SALES_ROLL_VA, SITE_SALES_ROLL_LEN, SITE_SALES_ROLL_EXPECT, 0xE8, CODE_ADDR(sales_roll));
    ftfp_site_branch(w++, SITE_SALE_VISITOR_VA, SITE_SALE_VISITOR_LEN, SITE_SALE_VISITOR_EXPECT, 0xE8,
                     CODE_ADDR(sale_visitors));
    for (i = 0; i < VTABLE_SLOTS; ++i) {
        DWORD held, to = (DWORD)(UINT_PTR)SLOTS[i].wrapper;
        if (!known_slot(SLOTS[i].va, SLOTS[i].stock)) {
            ftfp_failed_site = SLOTS[i].va;
            return 0;
        }
        held = *(const DWORD *)(UINT_PTR)SLOTS[i].va;
        memcpy(slot_expect[i], &held, 4);
        *SLOTS[i].next = (void *)(UINT_PTR)held;
        w->va = SLOTS[i].va;
        w->length = 4;
        w->expect = slot_expect[i];
        memcpy(w->bytes, &to, 4);
        ++w;
    }
    return (int)(w - writes) == TOTAL_SITES;
}

/* Every site checked, then all of them written or none. */
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

/* "<game>\Plant Tycoon Fix Patcher DLLs\Extra Greenhouses.log". */
static void write_install_log(void) {
    wchar_t path[1024];
    char line[160];
    DWORD written;
    HANDLE file;
    int len = 0;
    if (!own_folder(path, 1024) || wcslen(path) + 32 >= 1024) return;
    wcscat_s(path, 1024, L"Extra Greenhouses.log");
    if (installed) {
        len = append_text(line, len, "Extra Greenhouses: installed (all sites)\r\n");
    } else if (ftfp_failed_site != 0) {
        len = append_text(line, len, "Extra Greenhouses: NOT installed; the code at ");
        len = append_hex(line, len, ftfp_failed_site);
        len = append_text(line, len, " is not the stock code this build expects\r\n");
    } else {
        len = append_text(line, len, "Extra Greenhouses: NOT installed\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* The other companions beside this DLL start first, so their wrappers are in place. */
typedef int (__stdcall *startup_fn)(void);

/* 1 when the companion is beside this DLL (it is then loaded and started). */
static int start_companion(const wchar_t *name) {
    wchar_t path[1024];
    HMODULE module;
    startup_fn startup;
    if (!own_folder(path, 1024) || wcslen(path) + wcslen(name) + 1 >= 1024) return 0;
    wcscat_s(path, 1024, name);
    if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return 0;
    module = LoadLibraryExW(path, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (module == NULL) return 1;
    startup = (startup_fn)GetProcAddress(module, "FtfpStartup");
    if (startup != NULL) startup();
    return 1;
}

/* Called once by the startup loader before WinMain.  The first of these that
   is beside this DLL starts the others it knows: "Greenhouse Counts.dll"
   (its own setting) starts Unused Flowers or Sort Seeds, and "Unused
   Flowers.dll" starts the store upgrades, the seed boxes and Sort Seeds. */
int __stdcall FtfpStartup(void) {
    static const wchar_t *const first[3] = { L"Greenhouse Counts.dll", L"Unused Flowers.dll", L"Sort Seeds.dll" };
    int i;
    if (installed) return 1;
    greenhouses_on = ftfp_setting_on(self_module, L"Extra Greenhouses.ini");
    nurseries_on = ftfp_setting_on(self_module, L"Extra Nurseries.ini");
    __try {
        for (i = 0; i < 3 && !start_companion(first[i]); ++i) {
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    __try {
        installed = install_all();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    return installed;
}

int __stdcall FtfpExtraGreenhousesInstalled(void) { return installed; }

/* For the tests and other companions: the greenhouse on screen and the plants for sale. */
int __cdecl FtfpExtraGreenhousesShown(void) { return shown; }
int __cdecl FtfpExtraGreenhousesForSale(void) { return GAME_STATE != NULL ? count_for_sale(GAME_STATE) : 0; }
int __cdecl FtfpExtraGreenhousesLastSave(void) { return last_sidecar; }

/* Greenhouse g's pot k (0-based), wherever it is now; NULL outside 0..5 / 0..14. */
char *__cdecl FtfpExtraGreenhousesPot(int g, int k) {
    char *state = GAME_STATE;
    if (state == NULL || g < 0 || g >= GREENHOUSES || k < 0 || k >= POTS) return NULL;
    return locate(state, g, k);
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        self_module = instance;
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
