/* Zoom in when pruning -- the iOS version's pruning zoom, in the greenhouse of Plant Tycoon.

   WHAT.  With the shears in the hand (state+0x56C = 3), a click on a plant opens a zoom (that click prunes
   nothing): a grey, half-transparent box three pots wide and three rows tall over the plant's cell (moved
   in at the edges so it stays on the greenhouse: x 240-800, y 0-506), and in the middle of it that pot and
   its plant drawn again, twice as large, by the game's own code.  The part the shears would cut is lit
   with the game's own flash (the part's mask in white, its alpha 0.4 + 0.2 sin(angle), the angle 10 degrees
   on each frame: 0x42D590), and a click in the box cuts exactly
   that part -- of a working copy of the plant: the real plant, and everything behind the box, stay as they
   are while the zoom is open.  Three buttons sit in the box's top-right corner: Undo and Redo (each prune
   can be taken back and done again, up to 20 steps; a button with nothing to do is grey) and X, which
   closes the zoom and saves: the prunes are written into the real plant exactly as the game's own prunes
   would have written them.  The zoom is modal: a click outside the box does nothing, and nothing else is
   picked up while it is open.  If the game leaves the greenhouse or saves while it is open, the prunes are
   saved first.  Hovering a button names it under the button ("Undo", "Redo", "Close": translatable,
   Translations.dll's mod/prune_zoom.* lines).  Without the shears nothing is different.

   HOW THE GAME DRAWS AND PRUNES.  The overlay (0x428E70) draws the benches' plants at 0x428FC0 through
   0x423580, which calls 0x42FDE0 with "hover" = (shears held): each pot (row r, column c) at x 323 + 93c,
   y 117 + 144r by 0x42F740 (pot.png 0x38 at x-28,y-15; soil.png 0x37 at x-25,y-12; the price tag 0x36 at
   x+20,y+22, all through the sprite draw 0x4208F0), then the plant by vtable slot 7 (0x42E4A0).  Slot 7
   with hover set takes the mouse (0x402030) less (4, 16), the shears' tip, into the plant (+0x34, +0x38),
   sets +0x19 and calls slot 10, the plant's draw at a scale (1.0, or 0.85 when dead), which draws every
   branch (0x42E690) and flower (0x42D9C0) at that scale with the game's scaler, reading the pot through the
   object's +8 (and noting in it where each part was drawn); each part draw (slot 11, 0x42CFE0) reads the
   screen's pixel under the tip before and after drawing itself, and a change makes it the part under the
   tip (+0x24 branch, +0x28 flower), which slot 7 copies to +0x1C / +0x20.  The next draw lights that branch
   and what grows on it with its mask sheet at the pulsing alpha +0x2C.  The greenhouse's mouse (table slot
   0x469224, 0x4273D0: 1 move, 2 press, 3 release) calls the press 0x426040, which finds the pot under the
   click (0x423970: 5 x 3 cells of 92 x 144 from 270, 43), and with the shears calls slot 15 (+0x1C set?)
   and slot 16 (0x42D880: the part's type 1 -> 3 or 4 -> 5, or a flower's state +0x18 -> 3, the bloom
   +0x8C, a falling piece in the object) of that pot's plant, adds 1 to the prune count (state+0x4C),
   shows two one-time tips (state+0x53F33, +0x53F3E), changes the health (+0x24, by the shears' level and
   Random) and selects the pot.

   THE HOOKS.  Four sites, all checked and written, or none:
     * 0x428FC0, the overlay's call of 0x423580: a call of on_draw here, which calls 0x423580 (the benches
       exactly as the game draws them; the screen under the zoomed pot is taken just before) and then,
       with the zoom open: the part under the shears, found by the game's own hit test exactly as on the
       bench (find_part: the working copy drawn at its real size and place, over that screen and its pot
       and soil, with slot 7's test armed at the shears' tip mapped back to the real plant; the screen put
       back after); the box (the game's FillRect 0x407B80, grey at alpha 0.5); the pot and soil and tag
       (0x4208F0 at 200%) and the working copy by the plant's own slot 10 at 2 x its scale with that part
       flashing, all clipped to the box (the graphics' clip rectangle, +0x60..+0x6C).  For the draws the
       object's +8 points at the copy and its +0x18..+0x57 are put back after them, so no plant changes;
     * 0x469224, the greenhouse's mouse slot (chained after Greenhouse Counts', Extra Greenhouses' and
       Extra Chemical Slots' wrappers): with the shears and the zoom closed, a press on a plant opens it.
       With it open every press and release is taken here: a button does what it says; a press in the box
       runs the game's own press (0x426040) at the same point of the real plant (back through the zoom's
       scale and offset, kept inside the plant's cell) with the part the zoom found under the tip, while
       the pot holds the working copy, which then takes what the press wrote; the pot, the prune count and
       the object's fields go back as they were.  Moves are the game's;
     * 0x469244, the greenhouse's activation slot (chained after Extra Greenhouses' and Extra Chemical
       Slots'): leaving the greenhouse saves the prunes and closes the zoom;
     * 0x467D6C, the game state's Save slot (0x41D120): the prunes are saved before the game writes.

   SAVING.  The copy taken when the zoom opened (the base) tells what the prunes changed: each part's type
   and each flower's state that differ from the base, the bloom, and the health change (added to the real
   plant's health, kept to 0-100) are written into the real plant, and the prune count gets the prunes.
   With no time gone by that is exactly the game's own prunes; parts the plant grew meanwhile are kept.

   UNDO.  A step is the working copy and its prune count; Undo and Redo put a step back.

   INSTALL.  "Prune Zoom.dll" is a loader tail (src/ds_fish_loader.py): the startup loader loads it after
   every other companion.  "Prune Zoom.log" beside the DLL says whether it was installed. */
#include <windows.h>
#include "../ftfp_ds_fish/install_sites.h"

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))
#define NOINLINE __declspec(noinline)

#define SCENE_STATE 0x68
#define SCENE_POTS 0x70
#define S_PRUNED 0x4C
#define S_HELD 0x56C
#define HELD_SHEARS 3
#define POT_BASE 0x2188
#define POT_STRIDE 0x5600
#define POT_STYLE 0x18
#define POT_SOIL 0x1C
#define POT_WATER 0x20
#define POT_HEALTH 0x24
#define POT_PLANT 0x38
#define POT_FOLIAGE 0x4C
#define POT_BLOOM 0x8C
#define POT_FOR_SALE 0x9D
#define POT_PARTS 0xA8
#define PART_SIZE 0x16C
#define PART_TYPE 0x04
#define PART_FLOWERS 0xC0
#define PART_FLOWER 0xC4
#define FLOWER_SIZE 0x1C
#define FLOWER_STATE 0x18
#define PARTS 60
#define FLOWERS 13

/* the plant object */
#define P_POT 0x08
#define OBJECT_FIELDS 0x18
#define OBJECT_FIELDS_SIZE 0x40          /* +0x18..+0x57: the object is 0x58 bytes (0x42EE7E) */
#define P_TESTING 0x19
#define P_HOVER_PART 0x1C
#define P_HOVER_FLOWER 0x20
#define P_HIT_PART 0x24
#define P_HIT_FLOWER 0x28
#define P_TIP_X 0x34
#define P_TIP_Y 0x38
#define SLOT_DRAW 0x28
#define TIP_DX 4
#define TIP_DY 16
#define DEAD_SCALE 0.85f

/* the benches (0x42FDE0, 0x423970) */
#define ROWS 3
#define COLS 5
#define POT_X 323
#define POT_Y 117
#define POT_STEP_X 93
#define POT_STEP_Y 144
#define CELL_X 270
#define CELL_Y 43
#define CELL_W 92
#define CELL_H 144

/* the zoom */
#define ZOOM 2.0f
#define ZOOM_PERCENT 200
#define BOX_W 279
#define BOX_H 432
#define AREA_LEFT 240
#define AREA_RIGHT 800
#define AREA_TOP 0
#define AREA_BOTTOM 506
#define BUTTON_SIZE 20
#define BUTTON_INSET 5
#define BUTTON_GAP 4
#define SCREEN_RIGHT 796               /* a label ends here at the latest (its shadow 1 px more) */
#define HISTORY_MAX 21                 /* 20 steps */

#define BUTTON_UNDO 0
#define BUTTON_REDO 1
#define BUTTON_CLOSE 2
#define BUTTONS 3

#define MOUSE_MOVE 1
#define MOUSE_PRESS 2
#define MOUSE_RELEASE 3

#define DRAW_SITE_VA 0x00428FC0u
static const unsigned char DRAW_SITE[5] = { 0xE8, 0xBB, 0xA5, 0xFF, 0xFF };                  /* call 0x423580 */
#define MOUSE_SLOT_VA 0x00469224u
#define MOUSE_STOCK 0x004273D0u
#define ACTIVATE_SLOT_VA 0x00469244u
#define ACTIVATE_STOCK 0x004231E0u
#define SAVE_SLOT_VA 0x00467D6Cu
#define SAVE_STOCK 0x0041D120u

typedef void (__fastcall *benches_fn)(char *scene, int edx);
typedef void *(__cdecl *graphics_fn)(void);
typedef void (__fastcall *fill_fn)(void *graphics, int edx, const int *rect, float r, float g, float b, float a);
typedef int *(__cdecl *mouse_pos_fn)(int *out);
typedef int (__cdecl *button_fn)(void);
typedef char *(__fastcall *plant_of_fn)(void *pots, int edx, int row, int col);
typedef void (__fastcall *sprite_fn)(void *sprites, int edx, int id, int frame, int x, int y, float alpha, int percent, int centre);
typedef int (__fastcall *soil_fn)(char *state, int edx);
typedef int (__fastcall *pot_at_fn)(char *scene, int edx, int x, int y, int *row, int *col);
typedef void (__fastcall *plant_draw_fn)(char *plant, int edx, int x, int y, float scale);
typedef void (__fastcall *text_fn)(void *graphics, int edx, const char *text, int x, int y, unsigned int colour, int font);
typedef int (__fastcall *width_fn)(void *font, void *edx, const char *text, float scale);
typedef int (__fastcall *press_fn)(char *scene, int edx, int x, int y);
typedef int (__fastcall *mouse_fn)(char *scene, int edx, int type, int x, int y);
typedef int (__fastcall *activate_fn)(char *scene, int edx, int on);
typedef int (__fastcall *save_fn)(char *state, int edx, int slot);

static const benches_fn stock_benches = (benches_fn)0x00423580u;
static const graphics_fn game_graphics = (graphics_fn)0x00407A90u;
static const fill_fn fill_rect = (fill_fn)0x00407B80u;
static const mouse_pos_fn game_mouse = (mouse_pos_fn)0x00402030u;
static const button_fn mouse_down = (button_fn)0x00402050u;
static const plant_of_fn plant_of = (plant_of_fn)0x0042F6C0u;
static const sprite_fn draw_sprite = (sprite_fn)0x004208F0u;
static const soil_fn soil_level = (soil_fn)0x0041DDE0u;
static const pot_at_fn pot_at = (pot_at_fn)0x00423970u;
static const text_fn draw_text = (text_fn)0x004092A0u;          /* (text, x, y, colour, font 0 = PTfontsmall) */
static const width_fn text_width = (width_fn)0x00402380u;      /* the game's measure */
static const press_fn game_press = (press_fn)0x00426040u;

static mouse_fn next_mouse = NULL;
static activate_fn next_activate = NULL;
static save_fn next_save = NULL;

static HMODULE self_module;

/* The zoom, kept between frames. */
static int open_pot = -1;             /* the plant zoomed (row * 5 + col), -1 when closed */
static char *open_state = NULL;       /* the game state it belongs to */
static int box[4];                    /* left, top, right, bottom (inclusive) */
static int zoom_part = -1, zoom_flower = -1;  /* the part under the tip in the zoom, last frame */
static char base[POT_STRIDE];         /* the real pot when the zoom opened (or last saved) */
static char object_fields[OBJECT_FIELDS_SIZE];   /* the plant object's +0x18..+0x57 around a zoom draw or press */

/* The working copy and its history: steps[at] is the copy now, steps[0] as the zoom opened. */
typedef struct step {
    char pot[POT_STRIDE];
    int prunes;
} step;
static step steps[HISTORY_MAX];
static int step_count = 0, step_at = 0;
#define WORK (steps[step_at].pot)

int __stdcall FtfpPruneZoomState(int *out) {
    if (out != NULL) {
        out[0] = open_pot; out[1] = step_count; out[2] = box[0]; out[3] = box[1]; out[4] = box[2]; out[5] = box[3];
        out[6] = step_at; out[7] = open_pot >= 0 ? steps[step_at].prunes : 0;
        out[8] = (int)(UINT_PTR)(open_pot >= 0 ? WORK : NULL);
        out[9] = zoom_part; out[10] = zoom_flower;
    }
    return open_pot;
}

static int inside(const int *r, int x, int y) { return x >= r[0] && x <= r[2] && y >= r[1] && y <= r[3]; }

/* The buttons, right to left from the box's top-right corner: X, Redo, Undo. */
static void button_rect(int which, int *r) {
    r[2] = box[2] - BUTTON_INSET - (BUTTONS - 1 - which) * (BUTTON_SIZE + BUTTON_GAP);
    r[0] = r[2] - BUTTON_SIZE + 1;
    r[1] = box[1] + BUTTON_INSET;
    r[3] = r[1] + BUTTON_SIZE - 1;
}

static int button_at(int x, int y) {
    int r[4], which;
    for (which = 0; which < BUTTONS; ++which) {
        button_rect(which, r);
        if (inside(r, x, y)) return which;
    }
    return -1;
}

static int can_undo(void) { return step_at > 0; }
static int can_redo(void) { return step_at + 1 < step_count; }

static int clampi(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }

static int round_f(float v) { return v >= 0.0f ? (int)(v + 0.5f) : -(int)(-v + 0.5f); }

static void place_box(int k) {
    int cx = CELL_X + (k % COLS) * CELL_W + CELL_W / 2, cy = CELL_Y + (k / COLS) * CELL_H + CELL_H / 2;
    box[0] = clampi(cx - BOX_W / 2, AREA_LEFT, AREA_RIGHT - BOX_W);
    box[1] = clampi(cy - BOX_H / 2, AREA_TOP, AREA_BOTTOM - BOX_H);
    box[2] = box[0] + BOX_W - 1;
    box[3] = box[1] + BOX_H - 1;
}

/* The cell's centre and the box's centre: a point p of the zoom is C + (p - B) / ZOOM of the bench. */
static void centres(int k, int *cx, int *cy, int *bx, int *by) {
    *cx = CELL_X + (k % COLS) * CELL_W + CELL_W / 2;
    *cy = CELL_Y + (k / COLS) * CELL_H + CELL_H / 2;
    *bx = box[0] + BOX_W / 2;
    *by = box[1] + BOX_H / 2;
}

static char *real_pot(char *state, int k) { return state + POT_BASE + k * POT_STRIDE; }

static char *plant_in(char *scene, int k) {
    char *pot = real_pot(AT(scene, SCENE_STATE, char *), k);
    if (AT(pot, POT_PLANT, char) == 0 || AT(pot, POT_FOLIAGE, int) == 0) return NULL;
    return plant_of(AT(scene, SCENE_POTS, void *), 0, k / COLS, k % COLS);
}

/* The pot under (x, y) that holds a plant, by the game's own pot test; -1 for none. */
static int plant_under(char *scene, int x, int y) {
    int row = -1, col = -1, k = pot_at(scene, 0, x, y, &row, &col);
    if (k < 0 || row < 0 || row >= ROWS || col < 0 || col >= COLS) return -1;
    k = row * COLS + col;
    return plant_in(scene, k) != NULL ? k : -1;
}

/* A fresh working copy of the real pot: the base, and the history's one step. */
static void start_copy(char *state) {
    memcpy(base, real_pot(state, open_pot), POT_STRIDE);
    memcpy(steps[0].pot, base, POT_STRIDE);
    steps[0].prunes = 0;
    step_count = 1;
    step_at = 0;
}

static void open_on(char *state, int k) {
    open_pot = k;
    open_state = state;
    zoom_part = -1;
    zoom_flower = -1;
    place_box(k);
    start_copy(state);
}

/* ------------------------------------------------------------------ saving */

/* The working copy's prunes into the real plant (what differs from the base), then a fresh copy. */
NOINLINE static void save_prunes(void) {
    char *state = open_state, *real, *work;
    int i, j, flowers;
    if (open_pot < 0 || state == NULL) return;
    real = real_pot(state, open_pot);
    work = WORK;
    if (AT(real, POT_PLANT, char) != 0 && AT(real, POT_FOLIAGE, int) == AT(base, POT_FOLIAGE, int)) {
        for (i = 0; i < PARTS; ++i) {
            int at = POT_PARTS + i * PART_SIZE;
            if (AT(work, at + PART_TYPE, int) != AT(base, at + PART_TYPE, int))
                AT(real, at + PART_TYPE, int) = AT(work, at + PART_TYPE, int);
            flowers = clampi(AT(base, at + PART_FLOWERS, int), 0, FLOWERS);
            for (j = 0; j < flowers; ++j) {
                int f = at + PART_FLOWER + j * FLOWER_SIZE + FLOWER_STATE;
                if (AT(work, f, int) != AT(base, f, int)) AT(real, f, int) = AT(work, f, int);
            }
        }
        if (AT(work, POT_BLOOM, int) != AT(base, POT_BLOOM, int)) AT(real, POT_BLOOM, int) = AT(work, POT_BLOOM, int);
        if (AT(work, POT_HEALTH, int) != AT(base, POT_HEALTH, int))
            AT(real, POT_HEALTH, int) = clampi(AT(real, POT_HEALTH, int) + AT(work, POT_HEALTH, int) - AT(base, POT_HEALTH, int), 0, 100);
        AT(state, S_PRUNED, int) += steps[step_at].prunes;
    }
    start_copy(state);
}

static void close_zoom(void) {
    __try {
        save_prunes();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    open_pot = -1;
    open_state = NULL;
    step_count = 0;
    step_at = 0;
}

/* ------------------------------------------------------------------ the draw */

static void fill(void *graphics, int x0, int y0, int x1, int y1, float r, float g, float b, float a) {
    int rect[4];
    rect[0] = x0; rect[1] = y0; rect[2] = x1; rect[3] = y1;
    fill_rect(graphics, 0, rect, r, g, b, a);
}

/* A button: a dark green square with a light face (grey when it has nothing to do), and its sign. */
static void draw_button(void *graphics, int which, int enabled) {
    int r[4], i;
    float ink_r = enabled ? 0.62f : 0.55f, ink_g = enabled ? 0.10f : 0.55f, ink_b = enabled ? 0.08f : 0.55f;
    button_rect(which, r);
    if (enabled) fill(graphics, r[0], r[1], r[2] + 1, r[3] + 1, 0.16f, 0.32f, 0.12f, 1.0f);
    else fill(graphics, r[0], r[1], r[2] + 1, r[3] + 1, 0.40f, 0.40f, 0.40f, 1.0f);
    if (enabled) fill(graphics, r[0] + 2, r[1] + 2, r[2] - 1, r[3] - 1, 0.93f, 0.95f, 0.86f, 1.0f);
    else fill(graphics, r[0] + 2, r[1] + 2, r[2] - 1, r[3] - 1, 0.78f, 0.78f, 0.78f, 1.0f);
    if (which == BUTTON_CLOSE) {
        for (i = 4; i <= BUTTON_SIZE - 6; ++i) {
            fill(graphics, r[0] + i, r[1] + i, r[0] + i + 2, r[1] + i + 2, ink_r, ink_g, ink_b, 1.0f);
            fill(graphics, r[2] - i - 1, r[1] + i, r[2] - i + 1, r[1] + i + 2, ink_r, ink_g, ink_b, 1.0f);
        }
        return;
    }
    /* a turning arrow: a hook over the top, its head at the bottom (left for Undo, right for Redo) */
    {
        int left = which == BUTTON_UNDO, head = left ? r[0] + 4 : r[2] - 4, tail = left ? r[2] - 5 : r[0] + 5;
        int lo = head < tail ? head : tail, hi = head < tail ? tail : head, y = r[1] + 12;
        fill(graphics, lo, y, hi + 1, y + 2, ink_r, ink_g, ink_b, 1.0f);                 /* the shaft */
        fill(graphics, tail - 1, r[1] + 6, tail + 1, y + 2, ink_r, ink_g, ink_b, 1.0f);  /* up the far side */
        fill(graphics, left ? lo + 6 : lo, r[1] + 5, left ? hi + 1 : hi - 5, r[1] + 7, ink_r, ink_g, ink_b, 1.0f);
        for (i = 0; i < 4; ++i) {                                                         /* the head */
            int x = left ? head + i : head - i;
            fill(graphics, x, y - i, x + 1, y + 2 + i, ink_r, ink_g, ink_b, 1.0f);
        }
    }
}

static const char *const LABELS[BUTTONS] = { "Undo", "Redo", "Close" };

/* The hovered button's name under it, ending at the button's right edge, kept on the screen. */
static void draw_label(void *graphics, int which) {
    char *impl = AT(graphics, 0, char *);
    void *font = impl != NULL ? AT(impl, 0x5C, void *) : NULL;
    const char *text = LABELS[which];
    int r[4], w = font != NULL ? text_width(font, NULL, text, 1.0f) : 0, x;
    button_rect(which, r);
    x = r[2] + 1 - w;
    if (x + w > SCREEN_RIGHT) x = SCREEN_RIGHT - w;
    if (x < 0) x = 0;
    draw_text(graphics, 0, text, x + 1, r[3] + 4, 0xFF000000u, 0);
    draw_text(graphics, 0, text, x, r[3] + 3, 0xFFFFFFFFu, 0);
}

/* The part under the shears, found exactly as the game finds it on the bench: the working copy drawn at
   its real size and place by its own draw (slot 10) with slot 7's hit test armed at the tip's point of the
   real plant (the zoom's tip, back through its scale and offset), over what the bench drew it over (the
   screen as it was before the benches, taken in on_draw, and the pot and soil as 0x42F740 draws them);
   the screen is put back after, pixel for pixel.  -1 when the tip is off the plant. */
typedef int (__cdecl *surface_fn)(void *surface);
typedef unsigned int (__cdecl *map_rgb_fn)(void *format, unsigned char r, unsigned char g, unsigned char b);
static const surface_fn lock_surface = (surface_fn)0x0044E660u;
static const surface_fn unlock_surface = (surface_fn)0x0044E654u;
static const map_rgb_fn map_rgb = (map_rgb_fn)0x0044E678u;
#define HIT_LEFT 170                   /* the region around the real plant's anchor */
#define HIT_RIGHT 170
#define HIT_UP 300
#define HIT_DOWN 130
#define HIT_W (HIT_LEFT + HIT_RIGHT)
static unsigned int under_plant[HIT_W * (HIT_UP + HIT_DOWN)];   /* the screen, put back after */
static unsigned int before_benches[HIT_W * (HIT_UP + HIT_DOWN)];
static int before_rect[4], before_taken = 0;

static int hit_region(char *surface, int k, int *r) {
    int ax = POT_X + (k % COLS) * POT_STEP_X, ay = POT_Y + (k / COLS) * POT_STEP_Y, w, h;
    char *format;
    if (surface == NULL || (format = AT(surface, 4, char *)) == NULL || AT(format, 9, unsigned char) != 4) return 0;
    w = AT(surface, 8, int);
    h = AT(surface, 0xC, int);
    r[0] = ax - HIT_LEFT < 0 ? 0 : ax - HIT_LEFT;
    r[1] = ay - HIT_UP < 0 ? 0 : ay - HIT_UP;
    r[2] = ax + HIT_RIGHT > w ? w : ax + HIT_RIGHT;
    r[3] = ay + HIT_DOWN > h ? h : ay + HIT_DOWN;
    return r[2] > r[0] && r[3] > r[1];
}

/* Region r of the surface into (or, back, from) buf. */
static int copy_region(char *surface, const int *r, unsigned int *buf, int back) {
    char *pixels;
    int y, pitch = AT(surface, 0x10, int);
    if (lock_surface(surface) != 0) return 0;
    pixels = AT(surface, 0x14, char *);
    for (y = r[1]; y < r[3]; ++y) {
        unsigned int *row = (unsigned int *)(pixels + y * pitch) + r[0], *at = &buf[(y - r[1]) * HIT_W];
        if (back) memcpy(row, at, (size_t)(r[2] - r[0]) * 4);
        else memcpy(at, row, (size_t)(r[2] - r[0]) * 4);
    }
    unlock_surface(surface);
    return 1;
}

/* on_draw, before the benches: the screen the zoomed plant's pot and plant are drawn over. */
static void take_before_benches(void) {
    char *inner = AT(game_graphics(), 0, char *);
    char *surface = inner != NULL ? AT(inner, 0x30, char *) : NULL;
    before_taken = surface != NULL && hit_region(surface, open_pot, before_rect)
                && copy_region(surface, before_rect, before_benches, 0);
}

static int floor_half(int v) { return v >= 0 ? v / 2 : -((-v + 1) / 2); }

NOINLINE static void find_part(char *scene, char *plant, char *work, char *inner, int k, int tip_x, int tip_y) {
    char *state = AT(scene, SCENE_STATE, char *), *pot = real_pot(state, k);
    void *sprites = AT(AT(scene, SCENE_POTS, char *), 4, void *);
    char *surface = AT(inner, 0x30, char *);
    int cx, cy, bx, by, ax = POT_X + (k % COLS) * POT_STEP_X, ay = POT_Y + (k / COLS) * POT_STEP_Y;
    int rx, ry, r[4], clip[4], saved = 0;
    zoom_part = -1;
    zoom_flower = -1;
    if (!before_taken || !hit_region(surface, k, r) || memcmp(r, before_rect, sizeof r) != 0) return;
    centres(k, &cx, &cy, &bx, &by);
    rx = cx + floor_half(tip_x - bx);
    ry = cy + floor_half(tip_y - by);
    if (rx < r[0] || rx >= r[2] || ry < r[1] || ry >= r[3]) return;
    memcpy(clip, inner + 0x60, sizeof clip);
    __try {
        if (!copy_region(surface, r, under_plant, 0)) return;
        saved = 1;
        copy_region(surface, r, before_benches, 1);
        AT(inner, 0x60, int) = r[0];
        AT(inner, 0x64, int) = r[1];
        AT(inner, 0x68, int) = r[2];
        AT(inner, 0x6C, int) = r[3];
        /* the pot and soil, as 0x42F740 draws them before the plant */
        draw_sprite(sprites, 0, 0x38, AT(pot, POT_STYLE, int), ax - 28, ay - 15, 1.0f, 100, 1);
        if (AT(pot, POT_SOIL, int) != 0) {
            int frame = soil_level(state, 0) * 4 + (AT(pot, POT_WATER, int) > 500 ? 2 : 0) + (AT(pot, POT_FOLIAGE, int) != 0 ? 1 : 0);
            draw_sprite(sprites, 0, 0x37, frame, ax - 25, ay - 12, 1.0f, 100, 1);
        }
        AT(plant, P_POT, char *) = work;
        AT(plant, P_HOVER_PART, int) = -1;
        AT(plant, P_HOVER_FLOWER, int) = -1;
        AT(plant, P_HIT_PART, int) = -1;
        AT(plant, P_HIT_FLOWER, int) = -1;
        AT(plant, P_TIP_X, int) = rx;
        AT(plant, P_TIP_Y, int) = ry;
        AT(plant, P_TESTING, char) = 1;
        ((plant_draw_fn)AT(AT(plant, 0, char *), SLOT_DRAW, void *))(plant, 0, ax, ay,
                                                                      AT(work, POT_HEALTH, int) != 0 ? 1.0f : DEAD_SCALE);
        zoom_part = AT(plant, P_HIT_PART, int);
        zoom_flower = AT(plant, P_HIT_FLOWER, int);
    } __finally {
        memcpy(inner + 0x60, clip, sizeof clip);
        if (saved) copy_region(surface, r, under_plant, 1);
    }
}

static void draw_zoom(char *scene, int mx, int my) {
    char *state = AT(scene, SCENE_STATE, char *);
    void *pots = AT(scene, SCENE_POTS, void *);
    void *sprites = AT(pots, 4, void *);
    char *pot = real_pot(state, open_pot), *work = WORK;
    char *plant = plant_in(scene, open_pot);
    void *graphics = game_graphics();
    char *inner = AT(graphics, 0, char *);
    int clip[4], cx, cy, bx, by, ax, ay, swapped = 0, hovered = button_at(mx, my);
    float scale;
    if (plant == NULL) return;
    centres(open_pot, &cx, &cy, &bx, &by);
    ax = bx + round_f(ZOOM * (float)(POT_X + (open_pot % COLS) * POT_STEP_X - cx));
    ay = by + round_f(ZOOM * (float)(POT_Y + (open_pot / COLS) * POT_STEP_Y - cy));
    memcpy(object_fields, plant + OBJECT_FIELDS, OBJECT_FIELDS_SIZE);
    memcpy(clip, inner + 0x60, sizeof clip);
    __try {
        /* the part under the tip, as slot 7 finds it (not while the button is held, as slot 7 does not) */
        swapped = 1;
        if (hovered >= 0 || !inside(box, mx, my)) {
            zoom_part = -1;
            zoom_flower = -1;
        } else if (!mouse_down()) {
            find_part(scene, plant, work, inner, open_pot, mx - TIP_DX, my - TIP_DY);
        }
        fill(graphics, box[0], box[1], box[2] + 1, box[3] + 1, 0.5f, 0.5f, 0.5f, 0.5f);
        AT(inner, 0x60, int) = box[0] > clip[0] ? box[0] : clip[0];
        AT(inner, 0x64, int) = box[1] > clip[1] ? box[1] : clip[1];
        AT(inner, 0x68, int) = box[2] + 1 < clip[2] ? box[2] + 1 : clip[2];
        AT(inner, 0x6C, int) = box[3] + 1 < clip[3] ? box[3] + 1 : clip[3];
        /* the pot draw 0x42F740, at the zoom */
        draw_sprite(sprites, 0, 0x38, AT(pot, POT_STYLE, int), ax + round_f(ZOOM * -28.0f), ay + round_f(ZOOM * -15.0f),
                    1.0f, ZOOM_PERCENT, 0);
        if (AT(pot, POT_SOIL, int) != 0) {
            int frame = soil_level(state, 0) * 4 + (AT(pot, POT_WATER, int) > 500 ? 2 : 0) + (AT(pot, POT_FOLIAGE, int) != 0 ? 1 : 0);
            draw_sprite(sprites, 0, 0x37, frame, ax + round_f(ZOOM * -25.0f), ay + round_f(ZOOM * -12.0f), 1.0f, ZOOM_PERCENT, 0);
        }
        /* the working copy at the zoom's scale, the part found flashing as on the bench (the object's own
           flash, +0x2C) */
        memcpy(plant + OBJECT_FIELDS, object_fields, OBJECT_FIELDS_SIZE);
        AT(plant, P_POT, char *) = work;
        AT(plant, P_HOVER_PART, int) = zoom_part;
        AT(plant, P_HOVER_FLOWER, int) = zoom_flower;
        AT(plant, P_TESTING, char) = 0;
        scale = AT(work, POT_HEALTH, int) != 0 ? ZOOM : ZOOM * DEAD_SCALE;
        ((plant_draw_fn)AT(AT(plant, 0, char *), SLOT_DRAW, void *))(plant, 0, ax, ay, scale);
        if (AT(pot, POT_FOR_SALE, char) != 0) {
            draw_sprite(sprites, 0, 0x36, 0, ax + round_f(ZOOM * 20.0f), ay + round_f(ZOOM * 22.0f), 1.0f, ZOOM_PERCENT, 0);
        }
    } __finally {
        if (swapped) {
            AT(plant, P_POT, char *) = pot;
            memcpy(plant + OBJECT_FIELDS, object_fields, OBJECT_FIELDS_SIZE);
        }
        memcpy(inner + 0x60, clip, sizeof clip);
    }
    draw_button(graphics, BUTTON_UNDO, can_undo());
    draw_button(graphics, BUTTON_REDO, can_redo());
    draw_button(graphics, BUTTON_CLOSE, 1);
    if (hovered >= 0) draw_label(graphics, hovered);
}

/* 0x428FC0 in the overlay: the stock call of the benches' plants (thiscall scene), then the zoom. */
static void __fastcall on_draw(char *scene, int edx) {
    before_taken = 0;
    __try {
        if (open_pot >= 0) take_before_benches();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        before_taken = 0;
    }
    stock_benches(scene, edx);
    __try {
        int mouse[2];
        if (open_pot < 0) return;
        if (AT(scene, SCENE_STATE, char *) != open_state || plant_in(scene, open_pot) == NULL) {
            close_zoom();
            return;
        }
        mouse[0] = mouse[1] = -1000;
        game_mouse(mouse);
        draw_zoom(scene, mouse[0], mouse[1]);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        close_zoom();
    }
}

/* ------------------------------------------------------------------ the mouse */

/* A press in the box: the game's own press on the working copy (the pot holds it for the press). */
static char real_saved[POT_STRIDE], before[POT_STRIDE];
NOINLINE static int prune_in_zoom(char *scene, int x, int y) {
    char *state = AT(scene, SCENE_STATE, char *), *pot = real_pot(state, open_pot), *plant = plant_in(scene, open_pot);
    int cx, cy, bx, by, col = open_pot % COLS, row = open_pot / COLS, mapped_x, mapped_y, result = 1, count, swapped = 0;
    if (plant == NULL || AT(state, S_HELD, int) != HELD_SHEARS) return 1;
    centres(open_pot, &cx, &cy, &bx, &by);
    mapped_x = clampi(cx + round_f((float)(x - bx) / ZOOM), CELL_X + col * CELL_W + 1, CELL_X + col * CELL_W + CELL_W - 2);
    mapped_y = clampi(cy + round_f((float)(y - by) / ZOOM), CELL_Y + row * CELL_H + 1, CELL_Y + row * CELL_H + CELL_H - 2);
    memcpy(before, WORK, POT_STRIDE);
    memcpy(real_saved, pot, POT_STRIDE);
    memcpy(object_fields, plant + OBJECT_FIELDS, OBJECT_FIELDS_SIZE);
    count = AT(state, S_PRUNED, int);
    __try {
        memcpy(pot, WORK, POT_STRIDE);
        swapped = 1;
        AT(plant, P_HOVER_PART, int) = zoom_part;           /* what the zoom lit under the tip */
        AT(plant, P_HOVER_FLOWER, int) = zoom_flower;
        result = game_press(scene, 0, mapped_x, mapped_y);
        memcpy(WORK, pot, POT_STRIDE);
    } __finally {
        if (swapped) {
            int pruned = AT(state, S_PRUNED, int) - count, prunes = steps[step_at].prunes;
            memcpy(pot, real_saved, POT_STRIDE);
            memcpy(plant + OBJECT_FIELDS, object_fields, OBJECT_FIELDS_SIZE);
            AT(state, S_PRUNED, int) = count;
            steps[step_at].prunes = prunes + pruned;
            if (memcmp(before, WORK, POT_STRIDE) != 0 || pruned != 0) {
                step *now = &steps[step_at];
                if (step_at + 1 == HISTORY_MAX) {
                    memmove(&steps[0], &steps[1], sizeof(step) * (HISTORY_MAX - 1));
                    --step_at;
                    now = &steps[step_at];
                }
                memcpy(&steps[step_at + 1], now, sizeof(step));      /* the new step: the copy after */
                memcpy(now->pot, before, POT_STRIDE);                 /* this one: as it was before */
                now->prunes = prunes;
                ++step_at;
                step_count = step_at + 1;
            }
        }
    }
    return result & 0xFF;
}

#define PASS (-1)

NOINLINE static int on_mouse(char *scene, int type, int x, int y) {
    char *state = AT(scene, SCENE_STATE, char *);
    int which, k;
    if (state == NULL || type == MOUSE_MOVE) return PASS;
    if (open_pot < 0) {
        if (type != MOUSE_PRESS || AT(state, S_HELD, int) != HELD_SHEARS) return PASS;
        k = plant_under(scene, x, y);
        if (k < 0) return PASS;
        open_on(state, k);
        return 1;
    }
    if (type != MOUSE_PRESS) return 1;                     /* modal: releases and the rest are taken too */
    if (!inside(box, x, y)) return 1;
    which = button_at(x, y);
    if (which == BUTTON_CLOSE) {
        close_zoom();
        return 1;
    }
    if (which == BUTTON_UNDO) {
        if (can_undo()) --step_at;
        return 1;
    }
    if (which == BUTTON_REDO) {
        if (can_redo()) ++step_at;
        return 1;
    }
    return prune_in_zoom(scene, x, y);
}

/* The greenhouse's mouse (table slot 0x469224; thiscall scene, type, x, y; ret 0xC). */
NOINLINE static int __fastcall gh_mouse(char *scene, int edx, int type, int x, int y) {
    int r = PASS;
    (void)edx;
    __try {
        r = on_mouse(scene, type, x, y);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        r = PASS;
    }
    return r != PASS ? r : next_mouse(scene, 0, type, x, y);
}

/* The greenhouse's activation (0x469244): leaving it saves the prunes and closes the zoom. */
NOINLINE static int __fastcall gh_activate(char *scene, int edx, int on) {
    (void)edx;
    if (open_pot >= 0) close_zoom();
    return next_activate(scene, 0, on);
}

/* The game state's Save (0x467D6C -> 0x41D120; thiscall state, slot; ret 4): the prunes first. */
NOINLINE static int __fastcall state_save(char *state, int edx, int slot) {
    (void)edx;
    __try {
        if (open_pot >= 0 && state == open_state) save_prunes();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    return next_save(state, 0, slot);
}

/* ------------------------------------------------------------------ installing */

#define SITES 4
static ftfp_site_write writes[SITES];
static unsigned char slot_expect[3][4];
static int installed = 0;

static int own_folder(wchar_t *out, DWORD cap) {
    wchar_t *slash;
    DWORD n = GetModuleFileNameW(self_module, out, cap);
    if (n == 0 || n >= cap || (slash = wcsrchr(out, L'\\')) == NULL) return 0;
    slash[1] = L'\0';
    return 1;
}

/* A table slot holds its stock function, or the wrapper of another companion DLL from this folder (one
   that installed before this one), which is then chained. */
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
    if (!known_slot(va, stock)) return 0;
    now = *(const DWORD *)(UINT_PTR)va;
    memcpy(slot_expect[i], &now, 4);
    *next = (void *)(UINT_PTR)now;
    w->va = va;
    w->length = 4;
    w->expect = slot_expect[i];
    memcpy(w->bytes, &target, 4);
    return 1;
}

static void write_install_log(void) {
    wchar_t path[1024];
    wchar_t *slash;
    const char *line = installed ? "Prune Zoom: installed\r\n"
                                 : "Prune Zoom: not installed (0x00428FC0, 0x00469224, 0x00469244 or 0x00467D6C is not "
                                   "the stock code or another companion's wrapper)\r\n";
    DWORD written, n = GetModuleFileNameW(self_module, path, 1024);
    HANDLE file;
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL || wcslen(path) + 32 >= 1024) return;
    slash[1] = L'\0';
    wcscat_s(path, 1024, L"Prune Zoom.log");
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)strlen(line), &written, NULL);
    CloseHandle(file);
}

/* Called once by the executable's startup stub, before WinMain, after every other companion. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        ftfp_site_branch(&writes[0], DRAW_SITE_VA, sizeof DRAW_SITE, DRAW_SITE, 0xE8, (const void *)(UINT_PTR)on_draw);
        installed = table_slot(&writes[1], 0, MOUSE_SLOT_VA, MOUSE_STOCK, (void **)&next_mouse, (const void *)(UINT_PTR)gh_mouse)
                 && table_slot(&writes[2], 1, ACTIVATE_SLOT_VA, ACTIVATE_STOCK, (void **)&next_activate,
                               (const void *)(UINT_PTR)gh_activate)
                 && table_slot(&writes[3], 2, SAVE_SLOT_VA, SAVE_STOCK, (void **)&next_save, (const void *)(UINT_PTR)state_save)
                 && ftfp_install_sites(writes, SITES);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    return installed;
}

int __stdcall FtfpPruneZoomInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        self_module = instance;
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
