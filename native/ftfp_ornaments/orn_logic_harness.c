/* Test harness: Multiple Ornaments' rules without the game.  tests/test_multiple_ornaments.py
   builds and runs it, and checks the lines it prints ("name value ...").  The
   game's ornament passes are replaced by C copies of the stock code they stand
   for (0x41E570 pick, 0x41E600 drag, 0x41EA10 settle, 0x41DB00 fall); the
   draw pass logs what it is given.  argv[1] is a folder for the sidecar files
   and for the state dumps the emulation tests read. */
#include <stdio.h>
#include <stdlib.h>

#define FTFP_ORN_HARNESS
#include "ftfp_ornaments.c"

static wchar_t folder[MAX_PATH];
static char state[0x1E510];
static char scene[0x100];
static char store[0x40];
static int last_hint = -1, last_sound = -1, answer_yes = 1, draws = 0, confirms = 0;
static char hints_object[4], sprites_object[4], image_object[4];

int harness_sidecar_path(int slot, wchar_t *out, DWORD cap, int make_folder) {
    (void)make_folder;
    return swprintf_s(out, cap, L"%s\\Ornaments %d.dat", folder, slot) > 0;
}

static int trial_item(int item) { return item <= 18; }

static unsigned char *rec_at(int tank, int k) { return tank_records(state, tank) + k * ORN_STRIDE; }

static int __fastcall fake_pick(void *impl, void *edx, int x, int y) {
    int k;
    unsigned char *o;
    (void)edx;
    for (k = 0; k < ORN_SLOTS; ++k) {
        o = rec_at(*I(state, S_CURRENT_TANK), k);
        if (o[0] && x >= *I(o, O_X) && x <= *I(o, O_X) + *I(o, O_W) && y >= *I(o, O_Y)
            && y <= *I(o, O_Y) + *I(o, O_H)) {
            *I(impl, SCENE_HELD) = k;
            *I(o, O_X) = x - *I(o, O_W) / 2;
            *I(o, O_Y) = y - *I(o, O_H) / 2;
            *I(o, 0x0C) = 0;
            *I(o, O_FALL_SPEED) = 0;
            return 1;
        }
    }
    return 0;
}

static int __fastcall fake_drag(void *impl, void *edx, int x, int y) {
    int k = *I(impl, SCENE_HELD), nx, ny;
    unsigned char *o;
    (void)edx;
    if (k == NO_ORNAMENT) return 0;
    o = rec_at(*I(state, S_CURRENT_TANK), k);
    nx = x - *I(o, O_W) / 2;
    ny = y - *I(o, O_H) / 2;
    *I(o, O_X) = nx;
    *I(o, O_Y) = ny;
    if (nx + *I(o, O_W) > 800) *I(o, O_X) = 800 - *I(o, O_W);
    else if (nx < 10) *I(o, O_X) = 15;
    if (ny > 500) *I(o, O_Y) = 0x1EF;
    else if (ny < 0) *I(o, O_Y) = 5;
    return 0;
}

static int __fastcall fake_place_random(void *impl, void *edx, int tank, int k) {
    unsigned char *o = rec_at(tank, k);
    (void)impl; (void)edx;
    *I(o, O_X) = (800 - *I(o, O_W)) / 2;
    return 0;
}

static int __fastcall fake_settle(void *impl, void *edx, int x, int y, int tank, int k) {
    unsigned char *o = rec_at(tank, k);
    (void)impl; (void)edx; (void)x; (void)y;
    if (*I(o, O_Y) + *I(o, O_H) < 0x1B6) *I(o, O_FALL_SPEED) = 100;
    else if (*I(o, O_Y) + *I(o, O_H) > 0x1DB) *I(o, O_Y) = 0x1D6 - *I(o, O_H);
    else *I(o, O_FALL_SPEED) = 0;
    return 0;
}

static int __fastcall fake_fall(void *impl, void *edx) {
    int k;
    (void)impl; (void)edx;
    for (k = 0; k < ORN_SLOTS; ++k) {
        unsigned char *o = rec_at(*I(state, S_CURRENT_TANK), k);
        if (*I(o, O_FALL_SPEED) == 0) continue;
        *I(o, 0x18) += *I(o, O_FALL_SPEED);
        *I(o, O_Y) += *I(o, 0x18) / 100;
        *I(o, 0x18) %= 100;
        *I(o, O_FALL_SPEED) += 10;
        if (*I(o, O_Y) + *I(o, O_H) > 0x1DB) {
            *I(o, O_Y) = 0x1D6 - *I(o, O_H);
            *I(o, O_FALL_SPEED) = 0;
        }
    }
    return 0;
}

static int __fastcall fake_draw(void *impl, void *edx) {
    int k;
    (void)edx;
    for (k = 0; k < ORN_SLOTS; ++k) {
        unsigned char *o = rec_at(*I(state, S_CURRENT_TANK), k);
        if (!o[0]) continue;
        ++draws;
        printf("draw %d %d %d %d\n", *I(o, O_SPRITE), *I(o, O_X), *I(o, O_Y),
               *I(o, O_FALL_SPEED) == 0 && *I(impl, SCENE_HELD) != k);   /* shadow, as 0x41D63D */
    }
    return 0;
}

static int __fastcall fake_hint(void *self, void *edx, int n) { (void)self; (void)edx; last_hint = n; return 0; }
static int __fastcall fake_sprite_get(void *self, void *edx, int id) { (void)self; (void)edx; (void)id; return (int)(UINT_PTR)image_object; }
static int __fastcall fake_image_h(void *self, void *edx) { (void)self; (void)edx; return 37; }
static int __fastcall fake_image_w(void *self, void *edx) { (void)self; (void)edx; return 52; }
static int fake_confirm(void *parent, int id) { (void)parent; (void)id; ++confirms; return answer_yes; }
static void fake_sound(int id) { last_sound = id; }

static void reset_world(void) {
    memset(state, 0, sizeof state);
    memset(scene, 0, sizeof scene);
    memset(store, 0, sizeof store);
    clear_copies();
    *(char **)(scene + SCENE_STATE) = state;
    *(char **)(scene + SCENE_HINTS) = hints_object;
    *I(scene, SCENE_HELD) = NO_ORNAMENT;
    /* trash can, then the three tank buttons, as rectangles */
    *I(scene, SCENE_TRASH + 0) = 700; *I(scene, SCENE_TRASH + 4) = 500;
    *I(scene, SCENE_TRASH + 8) = 760; *I(scene, SCENE_TRASH + 12) = 590;
    { int t; for (t = 0; t < 3; ++t) {
        *I(scene, SCENE_TANK_BUTTONS + t * 16 + 0) = 10 + t * 60; *I(scene, SCENE_TANK_BUTTONS + t * 16 + 4) = 560;
        *I(scene, SCENE_TANK_BUTTONS + t * 16 + 8) = 60 + t * 60; *I(scene, SCENE_TANK_BUTTONS + t * 16 + 12) = 590;
    } }
    *(char **)(store + STORE_STATE) = state;
    *(char **)(store + STORE_HINTS) = hints_object;
    *(char **)(store + STORE_SPRITES) = sprites_object;
    state[S_REGISTERED] = 1;
    *I(state, S_MONEY) = 100000;
    {   /* the six store ornaments' stock prices */
        static const int price[6] = { 20, 50, 350, 950, 1500, 3500 };
        int i;
        for (i = 0; i < 6; ++i) *I(state, ITEM_PRICE(FIRST_ORNAMENT + i)) = price[i];
    }
    last_hint = last_sound = -1;
    answer_yes = 1;
}

/* An original ornament as the stock purchase makes it, in tank t slot k. */
static void original(int t, int k, int item, int x, int y) {
    unsigned char *o = rec_at(t, k);
    make_copy(o, ORNAMENT_SPRITE[item - FIRST_ORNAMENT], 52, 37);
    *I(o, O_X) = x;
    *I(o, O_Y) = y;
    *I(o, O_FALL_SPEED) = 0;
    *I(state, ITEM_OWNED(item)) = 1;
}

static unsigned int checksum(const void *p, size_t n) {
    const unsigned char *b = (const unsigned char *)p;
    unsigned int h = 2166136261u;
    while (n--) h = (h ^ *b++) * 16777619u;
    return h;
}

static void dump(const char *name) {
    char path[MAX_PATH];
    FILE *f;
    sprintf_s(path, sizeof path, "%ls\\%s", folder, name);
    if (fopen_s(&f, path, "wb") == 0) {
        fwrite(state + 8, 1, 0x1E3C8, f);      /* the save's own bytes: state + 8 */
        fclose(f);
    }
}

static void print_copy(const char *what, int t, int k) {
    const unsigned char *r = copies[t][k];
    int i;
    printf("%s", what);
    for (i = 0; i < ORN_STRIDE; ++i) printf("%s%02X", i ? "" : " ", r[i]);
    printf("\n");
}

int main(int argc, char **argv) {
    unsigned int before;
    int i, r;
    if (argc != 2) return 2;
    swprintf_s(folder, MAX_PATH, L"%hs", argv[1]);
    api.draw_ornaments = fake_draw;
    api.fall = fake_fall;
    api.pick = fake_pick;
    api.drag = fake_drag;
    api.place_random = fake_place_random;
    api.settle = fake_settle;
    api.hint = fake_hint;
    api.sprite_get = fake_sprite_get;
    api.image_h = fake_image_h;
    api.image_w = fake_image_w;
    api.confirm = fake_confirm;
    api.sound = fake_sound;

    /* ---- buying (each call is made before its line is printed) */
    reset_world();
    r = store_click(store, 16);
    printf("buy_unowned %d\n", r);                                  /* the stock purchase makes the first */
    r = store_click(store, 15);
    printf("buy_not_ornament %d\n", r);
    original(0, 0, 16, 100, 433);
    before = checksum(state, sizeof state);
    r = store_click(store, 16);
    printf("buy_second %d money %d spent %d owned %d copies %d sound %d\n", r,
           *I(state, S_MONEY), *I(state, S_SPENT), *I(state, ITEM_OWNED(16)), copy_count[0], last_sound);
    print_copy("bought_record", 0, 0);
    *I(state, S_MONEY) = 100000; *I(state, S_SPENT) = 0;
    printf("buy_state_unchanged %d\n", checksum(state, sizeof state) == before);
    original(1, 0, 21, 300, 400);
    *I(state, S_CURRENT_TANK) = 2;
    r = store_click(store, 21);
    printf("buy_other_tank %d tank2 %d\n", r, copy_count[2]);
    *I(state, S_MONEY) = 10;
    r = store_click(store, 21);
    printf("buy_no_money %d hint %d tank2 %d money %d\n", r, last_hint, copy_count[2], *I(state, S_MONEY));
    *I(state, S_MONEY) = 100000;
    answer_yes = 0;
    r = store_click(store, 21);
    printf("buy_declined %d tank2 %d money %d\n", r, copy_count[2], *I(state, S_MONEY));
    answer_yes = 1;
    state[S_REGISTERED] = 0;
    r = store_click(store, 21);
    printf("buy_trial_locked %d\n", r);                             /* the stock click refuses it */
    r = store_click(store, 16);
    printf("buy_trial_open %d\n", r);
    state[S_REGISTERED] = 1;
    for (i = 0; i < 20; ++i) store_click(store, 21);
    last_hint = -1;
    *I(state, S_MONEY) = 100000;
    r = store_click(store, 21);
    printf("buy_full %d hint %d tank2 %d money %d\n", r, last_hint, copy_count[2], *I(state, S_MONEY));

    /* ---- the effect: the save's bytes after buying 1 or 3 copies (tests emulate the stock effect code) */
    reset_world();
    original(0, 0, 18, 120, 420);
    original(0, 1, 16, 220, 430);
    dump("state_originals.bin");
    store_click(store, 18);
    *I(state, S_MONEY) = 100000; *I(state, S_SPENT) = 0;
    dump("state_1_copy.bin");
    store_click(store, 18);
    store_click(store, 16);
    *I(state, S_MONEY) = 100000; *I(state, S_SPENT) = 0;
    dump("state_3_copies.bin");
    printf("effect_copies %d\n", copy_count[0]);

    /* ---- the originals are put back byte for byte around every pass */
    reset_world();
    for (i = 0; i < ORN_BYTES; ++i) tank_records(state, 0)[i] = (unsigned char)(i * 37 + 11);
    for (i = 0; i < 6; ++i) tank_records(state, 0)[i * ORN_STRIDE] = (unsigned char)(i & 1);
    *I(state, ITEM_OWNED(17)) = 1;
    before = checksum(state, sizeof state);
    for (i = 0; i < 7; ++i) {
        unsigned char rec[ORN_STRIDE];
        make_copy(rec, 178, 40, 30);
        *I(rec, O_X) = 100 + i * 50;
        *I(rec, O_Y) = 200;
        add_copy(0, rec);
    }
    *I(scene, SCENE_HELD) = 4;                      /* an original held: kept as it was */
    draws = 0;
    draw_copies(scene);
    printf("draws %d held_after %d\n", draws, *I(scene, SCENE_HELD));
    for (i = 0; i < 200; ++i) fall_copies(scene);
    printf("fallen_y %d %d speed %d\n", *I(copies[0][0], O_Y), *I(copies[0][6], O_Y), *I(copies[0][6], O_FALL_SPEED));
    *I(scene, SCENE_HELD) = NO_ORNAMENT;
    printf("fall_originals_intact %d\n", checksum(state, sizeof state) == before);

    /* ---- pick, drag, drop: the top copy, as the stock pick takes an original */
    r = pick_copy(scene, 5, 5);
    printf("pick_miss %d\n", r);
    *I(copies[0][6], O_X) = *I(copies[0][0], O_X);                       /* copy 6 over copy 0 */
    r = pick_copy(scene, *I(copies[0][0], O_X) + 5, *I(copies[0][0], O_Y) + 5);
    printf("pick %d held %d %d scene_held %d\n", r, held_tank, held_copy, *I(scene, SCENE_HELD));
    r = drag_copy(scene, 400, 300);
    printf("drag %d\n", r);
    printf("dragged %d %d speed %d\n", *I(copies[0][6], O_X), *I(copies[0][6], O_Y), *I(copies[0][6], O_FALL_SPEED));
    draws = 0;
    draw_copies(scene);                              /* the held copy has no shadow */
    r = drop_copy(scene, 400, 300);
    printf("drop_in_place %d held %d speed %d\n", r, held_copy, *I(copies[0][6], O_FALL_SPEED));
    printf("drag_originals_intact %d\n", checksum(state, sizeof state) == before);

    /* ---- moving to another tank's button */
    pick_copy(scene, *I(copies[0][6], O_X) + 5, *I(copies[0][6], O_Y) + 5);
    r = drop_copy(scene, 80, 570);
    printf("move_no_second_tank %d hint %d tank0 %d tank1 %d\n", r, last_hint, copy_count[0], copy_count[1]);
    *I(state, S_SECOND_TANK) = 1;
    before = checksum(state, sizeof state);
    pick_copy(scene, *I(copies[0][6], O_X) + 5, *I(copies[0][6], O_Y) + 5);
    r = drop_copy(scene, 80, 570);
    printf("move_to_tank1 %d sound %d tank0 %d tank1 %d x %d speed %d\n", r, last_sound,
           copy_count[0], copy_count[1], *I(copies[1][0], O_X), *I(copies[1][0], O_FALL_SPEED));
    printf("move_originals_intact %d tank1_records_clear %d\n", checksum(state, sizeof state) == before,
           tank_records(state, 1)[0] == 0);

    /* ---- the trash can */
    pick_copy(scene, *I(copies[0][0], O_X) + 5, *I(copies[0][0], O_Y) + 5);
    answer_yes = 0;
    r = drop_copy(scene, 720, 550);
    printf("trash_declined %d tank0 %d\n", r, copy_count[0]);
    answer_yes = 1;
    pick_copy(scene, *I(copies[0][0], O_X) + 5, *I(copies[0][0], O_Y) + 5);
    r = drop_copy(scene, 720, 550);
    printf("trash %d sound %d tank0 %d owned %d\n", r, last_sound, copy_count[0], *I(state, ITEM_OWNED(17)));
    while (copy_count[0] > 0) {
        if (!pick_copy(scene, *I(copies[0][0], O_X) + 5, *I(copies[0][0], O_Y) + 5)) break;
        drop_copy(scene, 720, 550);
    }
    printf("trash_all tank0 %d owned %d originals_intact %d\n", copy_count[0], *I(state, ITEM_OWNED(17)),
           checksum(state, sizeof state) == before);

    /* ---- a held copy is let go when the tank changes */
    *I(state, S_CURRENT_TANK) = 1;
    r = pick_copy(scene, *I(copies[1][0], O_X) + 5, *I(copies[1][0], O_Y) + 5);
    *I(state, S_CURRENT_TANK) = 0;
    i = drag_copy(scene, 10, 10);
    printf("stale_hold picked %d drag %d held %d\n", r, i, held_copy);

    /* ---- the sidecar */
    reset_world();
    {
        unsigned char rec[ORN_STRIDE];
        sidecar keep;
        wchar_t path[MAX_PATH];
        FILE *f;
        make_copy(rec, 182, 90, 60); add_copy(0, rec);
        make_copy(rec, 177, 30, 20); *I(rec, O_X) = 640; add_copy(2, rec);
        make_copy(rec, 180, 30, 80); add_copy(5, rec);
        to_image(&keep);
        on_save(3);
        clear_copies();
        on_load(3);
        to_image(&file_image);
        printf("sidecar_round_trip %d counts %d %d %d\n", memcmp(&keep, &file_image, sizeof keep) == 0,
               copy_count[0], copy_count[2], copy_count[5]);
        on_load(4);                                                   /* a slot with no file: none */
        printf("sidecar_missing %d\n", copy_count[0] + copy_count[2] + copy_count[5]);
        on_load(0);
        printf("sidecar_settings_slot %d\n", copy_count[0]);
        harness_sidecar_path(3, path, MAX_PATH, 0);
        if (_wfopen_s(&f, path, L"r+b") == 0) {                        /* a bad sprite: refused whole, kept aside */
            fseek(f, (long)((char *)&keep.records[0][0][O_SPRITE] - (char *)&keep), SEEK_SET);
            fputc(5, f);
            fclose(f);
        }
        on_load(3);
        printf("sidecar_bad %d aside %d\n", copy_count[0] + copy_count[2] + copy_count[5],
               GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES);
        on_save(0);
        on_save(11);
        harness_sidecar_path(0, path, MAX_PATH, 0);
        printf("sidecar_no_settings_file %d\n", GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES);
        printf("sidecar_size %u\n", (unsigned int)sizeof(sidecar));
    }

    /* ---- the Extra Tanks setting's tank map */
    reset_world();
    printf("logical_default %d %d %d %d\n", logical_tank(0), logical_tank(2), logical_tank(3), logical_tank(-1));
    printf("max_copies %d\n", MAX_COPIES);
    return 0;
}
