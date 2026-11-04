/* Zoom in when pruning -- the iOS version's pruning zoom, in the greenhouse of Plant Tycoon.

   WHAT.  With the shears in the hand (state+0x56C = 3), a click on a plant opens a zoom (that click prunes
   nothing): a whitish, half-transparent box three pots wide and three rows tall over the plant's cell (moved
   in at the edges so it stays on the greenhouse: x 240-800, y 0-506), and in the middle of it that pot and
   its plant drawn again, 1.75 times larger, by the game's own code.  The part the shears would cut is lit
   the game's own way (the part's mask, pulsing, as on the real plant), and a click in the box cuts exactly
   that part.  An X in the box's top-right corner closes it; so does a click outside the box (a click there
   on a plant prunes nothing; any other is the game's, so a tool can be picked up at once), putting the
   shears down, or taking anything else.  Without the shears nothing is different.

   HOW THE GAME DRAWS AND PRUNES.  The overlay (0x428E70) draws the benches' plants at 0x428FC0 through
   0x423580, which calls 0x42FDE0 with "hover" = (shears held): each pot (row r, column c) at x 323 + 93c,
   y 117 + 144r by 0x42F740 (pot.png 0x38 at x-28,y-15; soil.png 0x37 at x-25,y-12; the price tag 0x36 at
   x+20,y+22, all through the sprite draw 0x4208F0), then the plant by vtable slot 7 (0x42E4A0).  Slot 7
   with hover set takes the mouse (0x402030) less (4, 16), the shears' tip, into the plant (+0x34, +0x38),
   sets +0x19 and calls slot 10, the plant's draw at a scale (1.0, or 0.85 when dead), which draws every
   branch (0x42E690) and flower (0x42D9C0) at that scale with the game's scaler; each part draw (slot 11,
   0x42CFE0) reads the screen's pixel under the tip before and after drawing itself, and a change makes it
   the part under the tip (+0x24 branch, +0x28 flower), which slot 7 copies to +0x1C / +0x20.  The next
   draw lights that branch and what grows on it with its mask sheet at the pulsing alpha +0x2C.  The press
   (0x426040) finds the pot under the click (0x423970: 5 x 3 cells of 92 x 144 from 270, 43), and with the
   shears calls slot 15 (+0x1C set?) and slot 16 (0x42D880: cut +0x1C / +0x20) of that pot's plant.

   THE HOOKS.  Two sites, both checked against the stock bytes and written, or neither:
     * 0x428FC0, the overlay's call of 0x423580: a call of on_draw here, which calls 0x423580 and then
       draws the zoom: the box (the game's FillRect 0x407B80, white at alpha 0.5), the pot and soil and tag
       (0x4208F0 at 175%), and the plant by its own slot 10 at 1.75 x its scale with the hit test armed at
       the tip as slot 7 arms it, all clipped to the box (the graphics' clip rectangle, +0x60..+0x6C); the
       plant's +0x1C / +0x20 become the part under the tip in the zoom, and every other plant's hover is
       cleared (slot 14), so the next press cuts only that part of that plant;
     * 0x426040, the press's first 5 bytes (sub esp, 0xC; push ebx; push ebp): a jump to a stub here.
       With the shears and the zoom closed, a press on a plant opens it, handled here.  With it open, a
       press on the X closes it, handled here; any other press inside the box is moved to the same point
       of the real plant (back through the zoom's scale and offset, kept inside the plant's cell), so the
       game's own press finds that pot and cuts the part lit in the zoom; a press outside closes it, and
       is handled here when it is on a plant, the game's otherwise.  Without the shears every press is
       the game's, unchanged.

   INSTALL.  "Prune Zoom.dll" is a loader tail (src/ds_fish_loader.py): the startup loader loads it after
   every other companion.  "Prune Zoom.log" beside the DLL says whether it was installed. */
#include <windows.h>
#include "../ftfp_ds_fish/install_sites.h"

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))

#define SCENE_STATE 0x68
#define SCENE_POTS 0x70
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
#define POT_FOR_SALE 0x9D

/* the plant object */
#define P_TESTING 0x19
#define P_HOVER_PART 0x1C
#define P_HOVER_FLOWER 0x20
#define P_HIT_PART 0x24
#define P_HIT_FLOWER 0x28
#define P_TIP_X 0x34
#define P_TIP_Y 0x38
#define SLOT_DRAW 0x28
#define SLOT_CLEAR_HOVER 0x38
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
#define ZOOM 1.75f
#define ZOOM_PERCENT 175
#define BOX_W 279
#define BOX_H 432
#define AREA_LEFT 240
#define AREA_RIGHT 800
#define AREA_TOP 0
#define AREA_BOTTOM 506
#define CLOSE_SIZE 20
#define CLOSE_INSET 5

#define DRAW_SITE_VA 0x00428FC0u
static const unsigned char DRAW_SITE[5] = { 0xE8, 0xBB, 0xA5, 0xFF, 0xFF };                  /* call 0x423580 */
#define PRESS_SITE_VA 0x00426040u
#define PRESS_SITE_BACK 0x00426045u
static const unsigned char PRESS_SITE[5] = { 0x83, 0xEC, 0x0C, 0x53, 0x55 };                 /* sub esp, 0xC; push ebx; push ebp */

typedef void (__fastcall *benches_fn)(char *scene, int edx);
typedef void *(__cdecl *graphics_fn)(void);
typedef void (__fastcall *fill_fn)(void *graphics, int edx, const int *rect, float r, float g, float b, float a);
typedef int *(__cdecl *mouse_fn)(int *out);
typedef int (__cdecl *button_fn)(void);
typedef char *(__fastcall *plant_of_fn)(void *pots, int edx, int row, int col);
typedef void (__fastcall *sprite_fn)(void *sprites, int edx, int id, int frame, int x, int y, float alpha, int percent, int centre);
typedef int (__fastcall *soil_fn)(char *state, int edx);
typedef int (__fastcall *pot_at_fn)(char *scene, int edx, int x, int y, int *row, int *col);
typedef void (__fastcall *plant_draw_fn)(char *plant, int edx, int x, int y, float scale);
typedef void (__fastcall *plant_clear_fn)(char *plant, int edx);

static const benches_fn stock_benches = (benches_fn)0x00423580u;
static const graphics_fn game_graphics = (graphics_fn)0x00407A90u;
static const fill_fn fill_rect = (fill_fn)0x00407B80u;
static const mouse_fn game_mouse = (mouse_fn)0x00402030u;
static const button_fn mouse_down = (button_fn)0x00402050u;
static const plant_of_fn plant_of = (plant_of_fn)0x0042F6C0u;
static const sprite_fn draw_sprite = (sprite_fn)0x004208F0u;
static const soil_fn soil_level = (soil_fn)0x0041DDE0u;
static const pot_at_fn pot_at = (pot_at_fn)0x00423970u;

static HMODULE self_module;

/* The zoom, kept between frames. */
static int open_pot = -1;             /* the plant zoomed (row * 5 + col), -1 when closed */
static int box[4];                    /* left, top, right, bottom (inclusive) */
static int zoom_part = -1, zoom_flower = -1;  /* the part under the tip in the zoom, last frame */

int __stdcall FtfpPruneZoomState(int *out) {
    if (out != NULL) {
        out[0] = open_pot; out[1] = 0; out[2] = box[0]; out[3] = box[1]; out[4] = box[2]; out[5] = box[3];
    }
    return open_pot;
}

static int inside(const int *r, int x, int y) { return x >= r[0] && x <= r[2] && y >= r[1] && y <= r[3]; }

static void close_rect(int *r) {
    r[2] = box[2] - CLOSE_INSET; r[0] = r[2] - CLOSE_SIZE + 1;
    r[1] = box[1] + CLOSE_INSET; r[3] = r[1] + CLOSE_SIZE - 1;
}

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

static char *plant_in(char *scene, int k) {
    char *state = AT(scene, SCENE_STATE, char *);
    char *pot = state + POT_BASE + k * POT_STRIDE;
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

static void open_on(int k) {
    if (k != open_pot) {
        zoom_part = -1;
        zoom_flower = -1;
    }
    open_pot = k;
    place_box(k);
}

static void fill(void *graphics, int x0, int y0, int x1, int y1, float r, float g, float b, float a) {
    int rect[4];
    rect[0] = x0; rect[1] = y0; rect[2] = x1; rect[3] = y1;
    fill_rect(graphics, 0, rect, r, g, b, a);
}

/* The X: a dark green square with a light face and a dark red cross. */
static void draw_close(void *graphics) {
    int r[4], i;
    close_rect(r);
    fill(graphics, r[0], r[1], r[2] + 1, r[3] + 1, 0.16f, 0.32f, 0.12f, 1.0f);
    fill(graphics, r[0] + 2, r[1] + 2, r[2] - 1, r[3] - 1, 0.93f, 0.95f, 0.86f, 1.0f);
    for (i = 4; i <= CLOSE_SIZE - 6; ++i) {
        fill(graphics, r[0] + i, r[1] + i, r[0] + i + 2, r[1] + i + 2, 0.62f, 0.10f, 0.08f, 1.0f);
        fill(graphics, r[2] - i - 1, r[1] + i, r[2] - i + 1, r[1] + i + 2, 0.62f, 0.10f, 0.08f, 1.0f);
    }
}

static void draw_zoom(char *scene, int mx, int my) {
    char *state = AT(scene, SCENE_STATE, char *);
    void *pots = AT(scene, SCENE_POTS, void *);
    void *sprites = AT(pots, 4, void *);
    char *pot = state + POT_BASE + open_pot * POT_STRIDE;
    char *plant = plant_in(scene, open_pot);
    void *graphics = game_graphics();
    char *inner = AT(graphics, 0, char *);
    int clip[4], cx, cy, bx, by, ax, ay, k, testing;
    float scale;
    if (plant == NULL) return;
    centres(open_pot, &cx, &cy, &bx, &by);
    ax = bx + round_f(ZOOM * (float)(POT_X + (open_pot % COLS) * POT_STEP_X - cx));
    ay = by + round_f(ZOOM * (float)(POT_Y + (open_pot / COLS) * POT_STEP_Y - cy));

    fill(graphics, box[0], box[1], box[2] + 1, box[3] + 1, 1.0f, 1.0f, 1.0f, 0.5f);
    memcpy(clip, inner + 0x60, sizeof clip);
    AT(inner, 0x60, int) = box[0] > clip[0] ? box[0] : clip[0];
    AT(inner, 0x64, int) = box[1] > clip[1] ? box[1] : clip[1];
    AT(inner, 0x68, int) = box[2] + 1 < clip[2] ? box[2] + 1 : clip[2];
    AT(inner, 0x6C, int) = box[3] + 1 < clip[3] ? box[3] + 1 : clip[3];
    __try {
        /* the pot draw 0x42F740, at the zoom */
        draw_sprite(sprites, 0, 0x38, AT(pot, POT_STYLE, int), ax + round_f(ZOOM * -28.0f), ay + round_f(ZOOM * -15.0f),
                    1.0f, ZOOM_PERCENT, 0);
        if (AT(pot, POT_SOIL, int) != 0) {
            int frame = soil_level(state, 0) * 4 + (AT(pot, POT_WATER, int) > 500 ? 2 : 0) + (AT(pot, POT_FOLIAGE, int) != 0 ? 1 : 0);
            draw_sprite(sprites, 0, 0x37, frame, ax + round_f(ZOOM * -25.0f), ay + round_f(ZOOM * -12.0f), 1.0f, ZOOM_PERCENT, 0);
        }
        /* the plant: slot 7's hit test, armed at the tip, then its own draw at the zoom's scale */
        AT(plant, P_HOVER_PART, int) = zoom_part;
        AT(plant, P_HOVER_FLOWER, int) = zoom_flower;
        testing = !mouse_down();
        if (testing) {
            AT(plant, P_HIT_PART, int) = -1;
            AT(plant, P_HIT_FLOWER, int) = -1;
            AT(plant, P_TIP_X, int) = mx - TIP_DX;
            AT(plant, P_TIP_Y, int) = my - TIP_DY;
        }
        AT(plant, P_TESTING, char) = (char)testing;
        scale = AT(pot, POT_HEALTH, int) != 0 ? ZOOM : ZOOM * DEAD_SCALE;
        ((plant_draw_fn)AT(AT(plant, 0, char *), SLOT_DRAW, void *))(plant, 0, ax, ay, scale);
        if (testing) {
            zoom_part = AT(plant, P_HIT_PART, int);
            zoom_flower = AT(plant, P_HIT_FLOWER, int);
        }
        AT(plant, P_TESTING, char) = 0;
        AT(plant, P_HOVER_PART, int) = zoom_part;
        AT(plant, P_HOVER_FLOWER, int) = zoom_flower;
        if (AT(pot, POT_FOR_SALE, char) != 0) {
            draw_sprite(sprites, 0, 0x36, 0, ax + round_f(ZOOM * 20.0f), ay + round_f(ZOOM * 22.0f), 1.0f, ZOOM_PERCENT, 0);
        }
    } __finally {
        memcpy(inner + 0x60, clip, sizeof clip);
    }
    /* only the zoomed plant keeps a part under the shears */
    for (k = 0; k < ROWS * COLS; ++k) {
        char *other = k == open_pot ? NULL : plant_in(scene, k);
        if (other != NULL) ((plant_clear_fn)AT(AT(other, 0, char *), SLOT_CLEAR_HOVER, void *))(other, 0);
    }
    draw_close(graphics);
}

/* 0x428FC0 in the overlay: the stock call of the benches' plants (thiscall scene), then the zoom. */
static void __fastcall on_draw(char *scene, int edx) {
    stock_benches(scene, edx);
    __try {
        char *state = AT(scene, SCENE_STATE, char *);
        int mouse[2];
        if (state == NULL || AT(state, S_HELD, int) != HELD_SHEARS || (open_pot >= 0 && plant_in(scene, open_pot) == NULL)) {
            open_pot = -1;
            return;
        }
        if (open_pot < 0) return;
        mouse[0] = mouse[1] = -1000;
        game_mouse(mouse);
        draw_zoom(scene, mouse[0], mouse[1]);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        open_pot = -1;
    }
}

/* The press (thiscall scene, x, y; xy points at its x and y on the stack).  1: handled here. */
static int __fastcall on_press(char *scene, int *xy) {
    __try {
        char *state = AT(scene, SCENE_STATE, char *);
        int x = xy[0], y = xy[1], close[4], cx, cy, bx, by, col, row;
        if (state == NULL || AT(state, S_HELD, int) != HELD_SHEARS) {
            open_pot = -1;
            return 0;
        }
        if (open_pot < 0) {
            int k = plant_under(scene, x, y);
            if (k < 0) return 0;
            open_on(k);
            return 1;
        }
        if (!inside(box, x, y)) {
            open_pot = -1;
            return plant_under(scene, x, y) >= 0;
        }
        close_rect(close);
        if (inside(close, x, y)) {
            open_pot = -1;
            return 1;
        }
        centres(open_pot, &cx, &cy, &bx, &by);
        col = open_pot % COLS;
        row = open_pot / COLS;
        xy[0] = clampi(cx + round_f((float)(x - bx) / ZOOM), CELL_X + col * CELL_W + 1, CELL_X + col * CELL_W + CELL_W - 2);
        xy[1] = clampi(cy + round_f((float)(y - by) / ZOOM), CELL_Y + row * CELL_H + 1, CELL_Y + row * CELL_H + CELL_H - 2);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    return 0;
}

/* Jumped to from 0x426040 (ecx = scene, [esp+4] x, [esp+8] y): a press handled here returns al = 1 (ret 8);
   otherwise the five bytes the jump replaced, and on to 0x426045. */
static const DWORD press_back = PRESS_SITE_BACK;
__declspec(naked) static void stub_press(void) {
    __asm {
        pushad
        pushfd
        mov ecx, [esp + 28]
        lea edx, [esp + 40]
        call on_press
        test eax, eax
        jnz handled
        popfd
        popad
        sub esp, 0xC
        push ebx
        push ebp
        jmp dword ptr [press_back]
    handled:
        popfd
        popad
        mov al, 1
        ret 8
    }
}

static ftfp_site_write writes[2];
static int installed = 0;

static void write_install_log(void) {
    wchar_t path[1024];
    wchar_t *slash;
    const char *line = installed ? "Prune Zoom: installed\r\n"
                                 : "Prune Zoom: not installed (the code at 0x00428FC0 or 0x00426040 is not the stock code)\r\n";
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

/* Called once by the executable's startup stub, before WinMain. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        ftfp_site_branch(&writes[0], DRAW_SITE_VA, sizeof DRAW_SITE, DRAW_SITE, 0xE8, (const void *)(UINT_PTR)on_draw);
        ftfp_site_branch(&writes[1], PRESS_SITE_VA, sizeof PRESS_SITE, PRESS_SITE, 0xE9, (const void *)(UINT_PTR)stub_press);
        installed = ftfp_install_sites(writes, 2);
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
