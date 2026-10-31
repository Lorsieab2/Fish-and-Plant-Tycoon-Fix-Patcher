/* Extra Chemical Slots -- the Upgrades view's item and the save events for
   "Extra Chemical Slots.dll" (its own setting; included by
   ftfp_plant_upgrades.c, after the automatic upgrades).

   THE ITEM.  "Extra Chemical Slots" stands on the chemicals shelf's third
   row, under the Formula Bomb (the shelf's rows are 61 px apart: 55, 116,
   177), drawn at scale 1 from row 18 of this mod's chemicals sheet (two
   chemical bottles and a small gold arrow, pre-scaled by
   scripts/build_plant_upgrades_assets.py).  It is bought once, $10,000 ($0
   with Free upgrades), with the same Yes / No as Add Money, and has the
   stock tick afterwards.  It shows only while the setting is on (the DLL
   loaded and installed).  The DLL loads after this one (the startup loader
   loads it last), so it is found when the store opens, not at start-up.

   THE EVENTS.  The save, load, delete and new-game events this DLL gets
   from "Unused Flowers.dll" go on to the DLL, which keeps page 2 in
   "Plant Tycoon Fix Patcher Data\Extra Chemical Slots <slot>.dat".

   THE SETTING OFF.  Without the DLL, page 2 would be out of reach.  So when
   a slot is loaded and its file holds chemicals, they go into the stock
   tray as the store's Buy puts them (0x416410: onto the same chemical, else
   a free slot) as far as there is room, and the file keeps the rest and the
   purchase.  The file is rewritten only when the game saves (so the save
   and the file always agree: quitting without a save changes neither); if
   nothing is left and nothing was bought, it is deleted then.  Switching
   the setting on again shows what is left on page 2. */

#define CHEM_SLOTS_DLL L"Extra Chemical Slots.dll"
#define CHEM_SLOTS_PRICE 10000
#define CHEM_SLOTS_FRAME 36                 /* chemicals sheet row 18 */
#define CHEM_SLOTS_X 598                    /* the formula's column, the shelf's third row */
#define CHEM_SLOTS_Y (55 + 2 * 61)
static const RECT CHEM_SLOTS_RECT = { CHEM_SLOTS_X + 12, CHEM_SLOTS_Y + 8, CHEM_SLOTS_X + 57, CHEM_SLOTS_Y + 60 };

typedef int (__cdecl *chem_int_fn)(void);
typedef void (__cdecl *chem_state_fn)(char *state, int slot);
typedef void (__cdecl *chem_slot_fn)(int slot);
typedef void (__cdecl *chem_void_fn)(void);
typedef int (__fastcall *tray_add_fn)(void *tray, int edx, int id, int doses);
typedef void **(__cdecl *tray_instance_fn)(void);
static const tray_add_fn tray_add_stock = (tray_add_fn)0x00416410u;       /* the tray's add(id, doses) */
static const tray_instance_fn tray_instance = (tray_instance_fn)0x00416370u;

static char *chem_tip = NULL;
static char chem_tip_text[64];

static FARPROC chem_export(const char *name) {
    HMODULE module = GetModuleHandleW(CHEM_SLOTS_DLL);
    return module != NULL ? GetProcAddress(module, name) : NULL;
}

/* -1 when the setting is off (or the DLL did not install), else 1 bought, 0 not. */
static int chem_owned(void) {
    chem_int_fn owned = (chem_int_fn)chem_export("FtfpChemSlotsOwned");
    return owned != NULL ? owned() : -1;
}

static int chem_on(void) { return chem_owned() >= 0; }

/* ------------------------------------------------------------ the setting off */

static int chem_off_slot = 0;               /* the slot whose file keeps what did not fit */
static int chem_off_dirty = 0;              /* that file is rewritten at the slot's next save */
static int chem_off_owned = 0;
static int chem_off_fresh = 0;              /* a new game: the slot's old file goes at its next save */
static chem_record chem_off_left[CHEM_PAGE_SLOTS];

/* Page 2 into the stock tray, as far as it fits. */
__declspec(noinline) static void chem_off_load(int slot) {
    int i, moved = 0;
    void **tray = tray_instance();
    chem_off_slot = slot;
    chem_off_dirty = 0;
    chem_off_fresh = 0;
    if (chem_file_read(slot, &chem_off_owned, chem_off_left) != 1 || tray == NULL) return;
    for (i = 0; i < CHEM_PAGE_SLOTS; ++i) {
        chem_record *r = &chem_off_left[i];
        if (!r->present) continue;
        if (tray_add_stock(tray, 0, r->id, r->doses) & 0xFF) {
            memset(r, 0, sizeof *r);
            moved = 1;
        }
    }
    chem_off_dirty = moved;
}

__declspec(noinline) static void chem_off_save(int slot) {
    int i, left = 0;
    if (chem_off_fresh) {
        chem_file_delete(slot);
        chem_off_fresh = 0;
        return;
    }
    if (!chem_off_dirty || slot != chem_off_slot) return;
    for (i = 0; i < CHEM_PAGE_SLOTS; ++i) left |= chem_off_left[i].present;
    if (left || chem_off_owned) {
        if (!chem_file_write(slot, chem_off_owned, chem_off_left)) return;
    } else {
        chem_file_delete(slot);
    }
    chem_off_dirty = 0;
}

/* ------------------------------------------------------------ the events */

static void chem_save(char *state, int slot) {
    chem_state_fn save = (chem_state_fn)chem_export("FtfpChemSlotsSave");
    if (chem_on() && save != NULL) save(state, slot);
    else if (slot > 0) chem_off_save(slot);
}

static void chem_load(const char *state, int slot) {
    chem_state_fn load = (chem_state_fn)chem_export("FtfpChemSlotsLoad");
    if (chem_on() && load != NULL) load((char *)state, slot);
    else chem_off_load(slot);
}

static void chem_delete(int slot) {
    chem_slot_fn remove = (chem_slot_fn)chem_export("FtfpChemSlotsDelete");
    if (chem_on() && remove != NULL) remove(slot);
    else chem_file_delete(slot);
    if (slot == chem_off_slot) chem_off_dirty = 0;
}

/* A new game in the slot: its old page 2 belongs to the old game (the DLL empties it and writes the
   empty page at the next save; without the DLL, the old file is deleted at the next save). */
static void chem_new_game(void) {
    chem_void_fn fresh = (chem_void_fn)chem_export("FtfpChemSlotsNewGame");
    if (chem_on() && fresh != NULL) fresh();
    chem_off_dirty = 0;
    chem_off_slot = 0;
    chem_off_fresh = !chem_on();
}

/* ------------------------------------------------------------ the store */

static void chem_tip_set(void) {
    if (chem_owned() > 0) sprintf_s(chem_tip_text, 64, "Extra Chemical Slots\nSold out");
    else sprintf_s(chem_tip_text, 64, "Extra Chemical Slots\nPrice: $ %i", price(CHEM_SLOTS_PRICE));
}

__declspec(noinline) static void chem_make_tip(char *scene) {
    if (chem_tip != NULL || !chem_on()) return;
    chem_tip_set();
    chem_tip = (char *)game_new(0x10);
    if (chem_tip == NULL) return;
    tooltip_ctor(chem_tip, 0, 95, &CHEM_SLOTS_RECT, scene, chem_tip_text, TOOLTIP_FONT, 0, 0);
    add_control(scene, 0, chem_tip);
}

static void chem_set_tip(int shown) {
    if (chem_tip == NULL) return;
    chem_tip_set();
    tooltip_text(chem_tip, 0, chem_tip_text, TOOLTIP_COLOUR, 0, 0);
    AT(chem_tip, 8, unsigned char) = (unsigned char)(shown && chem_on());
}

static void chem_draw(void *mgr) {
    int owned = chem_owned();
    if (owned < 0) return;
    draw_shadow(mgr, 0, SHEET_SHADOW, CHEM_SLOTS_X + 0x19, CHEM_SLOTS_Y + 0x1E, 1.0f, 100);
    draw_sprite(mgr, 0, SHEET_CHEMICALS, CHEM_SLOTS_FRAME, CHEM_SLOTS_X, CHEM_SLOTS_Y, 1.0f, 100, 1);
    if (owned > 0) draw_shadow(mgr, 0, SHEET_TICK, CHEM_SLOTS_X + 19, CHEM_SLOTS_Y + 22, 1.0f, 100);
}

__declspec(noinline) static void chem_buy(char *scene) {
    char *state = SCENE_STATE(scene);
    chem_int_fn buy = (chem_int_fn)chem_export("FtfpChemSlotsBuy");
    wchar_t text[256];
    int cost = price(CHEM_SLOTS_PRICE);
    if (state == NULL || buy == NULL || chem_owned() < 0) return;
    if (chem_owned() > 0) {
        tw_tell_as(L"Extra Chemical Slots", L"You already have the extra chemical slots!");
        return;
    }
    if (AT(state, S_CASH, unsigned int) < (unsigned int)cost) {
        tw_tell_as(L"Extra Chemical Slots", L"You can't afford to buy this yet! The extra chemical slots cost $10,000.");
        return;
    }
    swprintf_s(text, 256, L"Buy the extra chemical slots for $%d?\n\nA gold arrow in the greenhouse's Tools box "
               L"turns to a second page of 8 chemical slots.", cost);
    if (!tw_confirm_as(L"Extra Chemical Slots", text)) return;
    if (AT(state, S_CASH, unsigned int) < (unsigned int)cost || chem_owned() != 0) return;
    add_cash(state, 0, -cost);
    buy();
    play_sound(SCENE_SOUND(scene), 0, SOUND_BUTTON);
    chem_set_tip(1);
}

static void chem_click(char *scene, int x, int y) {
    if (chem_on() && inside(&CHEM_SLOTS_RECT, x, y)) chem_buy(scene);
}
