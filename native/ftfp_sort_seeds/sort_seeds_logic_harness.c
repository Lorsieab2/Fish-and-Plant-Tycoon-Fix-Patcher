/* Test harness: the Sort Seeds rules without the game.  Builds seed boxes in
   memory, sorts them with the DLL's own code and prints one line per check
   ("ok ..." or "FAIL ...") for tests/test_sort_seeds.py. */
#include <stdio.h>

static void test_empty_record(void *record) {
    int *g = (int *)record, i;
    for (i = 0; i < 6; ++i) g[i] = -1;
    ((unsigned char *)record)[0x18] = 0;
    g[7] = -1;
    g[8] = 1;
}
#define FTFP_TEST_EMPTY_RECORD(record) test_empty_record(record)
#include "ftfp_sort_seeds.c"

static unsigned char chest_a[BOX_BYTES], chest_b[BOX_BYTES], chest_c[BOX_BYTES];
static unsigned char scratch[CHESTS][BOX_BYTES];
static int failures = 0;

static void check(int ok, const char *what) {
    printf("%s %s\n", ok ? "ok" : "FAIL", what);
    if (!ok) ++failures;
}

static unsigned char *slot(unsigned char *chest, int s) { return chest + s * RECORD_BYTES; }

static void put(unsigned char *chest, int s, int own_fol, int own_flw, int donor_fol, int donor_flw,
                int fol, int flw, int tag) {
    int *g = (int *)slot(chest, s);
    memset(g, 0, RECORD_BYTES);
    g[0] = own_fol; g[1] = own_flw; g[2] = donor_fol; g[3] = donor_flw; g[4] = fol; g[5] = flw;
    slot(chest, s)[0x18] = 1;
    slot(chest, s)[0x19] = (unsigned char)tag;          /* padding byte: tells equal seeds apart */
    g[7] = fol * 4 - 4 + plant_class(fol, flw);
    g[8] = tag;
}

static void clear(unsigned char *chest) {
    int s;
    for (s = 0; s < BOX_RECORDS; ++s) test_empty_record(slot(chest, s));
}

static int present(unsigned char *chest, int s) { return slot(chest, s)[0x18] != 0; }
static int tag(unsigned char *chest, int s) { return ((int *)slot(chest, s))[8]; }

static int count_present(unsigned char *chest) {
    int s, n = 0;
    for (s = 0; s < BOX_RECORDS; ++s) n += present(chest, s);
    return n;
}

int main(void) {
    unsigned char *chests[CHESTS] = { chest_a, chest_b, chest_c };
    int slots[CHESTS], n, s, ok;
    unsigned char locked_before[RECORD_BYTES];

    /* classes: A (1,1), B (3,5), C (2,1), D (1,18), D new flower (5,30) */
    check(plant_class(1, 1) == 0 && plant_class(3, 5) == 1 && plant_class(2, 1) == 2
          && plant_class(1, 18) == 3 && plant_class(5, 30) == 3 && plant_class(17, 17) == 0, "classes");

    /* 1. one chest, two drawers unlocked (80 slots), seeds scattered */
    clear(chest_a); clear(chest_b);
    put(chest_a, 79, 9, 9, 1, 1, 1, 18, 1);      /* D */
    put(chest_a, 3, 0, 0, 0, 0, 3, 5, 2);        /* B, shop seed */
    put(chest_a, 40, 5, 5, 9, 9, 1, 1, 3);       /* A, parents 5/5 */
    put(chest_a, 12, 0, 0, 0, 0, 1, 1, 4);       /* A, unknown parents: before 3 */
    put(chest_a, 0, 2, 2, 2, 2, 2, 1, 5);        /* C */
    put(chest_a, 50, 5, 5, 9, 9, 1, 1, 6);       /* equal to 3: stays after it */
    put(chest_a, 20, 1, 1, 1, 1, 5, 1, 7);       /* A, foliage 5: after foliage 1 */
    put(chest_a, 90, 1, 1, 1, 1, 1, 1, 99);      /* locked drawer: must not move */
    memcpy(locked_before, slot(chest_a, 90), RECORD_BYTES);
    slots[0] = 80;
    n = sort_chests(chests, slots, 1, scratch);
    check(n == 7, "seven seeds sorted");
    ok = tag(chest_a, 0) == 4 && tag(chest_a, 1) == 3 && tag(chest_a, 2) == 6 && tag(chest_a, 3) == 7
         && tag(chest_a, 4) == 2 && tag(chest_a, 5) == 5 && tag(chest_a, 6) == 1;
    check(ok, "order: class, foliage, flower, unknown parents first, stable");
    ok = 1;
    for (s = 7; s < 80; ++s) ok &= !present(chest_a, s);
    check(ok, "packed from the first slot, the rest empty");
    check(memcmp(locked_before, slot(chest_a, 90), RECORD_BYTES) == 0, "locked drawer untouched");
    check(count_present(chest_a) == 8, "no seed lost or added");

    /* 2. two chests: first fills, overflow goes to the second chest */
    clear(chest_a); clear(chest_b);
    for (s = 0; s < 40; ++s) put(chest_b, s, 0, 0, 0, 0, 1 + (s % 23), 1, 100 + s);
    for (s = 0; s < 30; ++s) put(chest_a, s, 0, 0, 0, 0, 23 - (s % 23), 3, 200 + s);
    slots[0] = 40; slots[1] = 40;
    n = sort_chests(chests, slots, 2, scratch);
    check(n == 70, "seventy seeds over two chests");
    check(count_present(chest_a) == 40 && count_present(chest_b) == 30, "first chest filled first");
    ok = 1;
    for (s = 0; s < 30; ++s) ok &= present(chest_b, s);
    for (s = 30; s < BOX_RECORDS; ++s) ok &= !present(chest_b, s);
    check(ok, "second chest packed from its first slot");

    /* 3. second chest locked (0 slots): its seeds are never touched */
    clear(chest_a); clear(chest_b);
    put(chest_a, 5, 0, 0, 0, 0, 2, 2, 1);
    put(chest_b, 0, 0, 0, 0, 0, 1, 1, 2);
    slots[0] = 40; slots[1] = 0;
    n = sort_chests(chests, slots, 2, scratch);
    check(n == 1 && tag(chest_a, 0) == 1 && present(chest_b, 0) && tag(chest_b, 0) == 2, "locked chest untouched");

    /* 4. empty boxes and full boxes */
    clear(chest_a); clear(chest_b);
    slots[0] = 120; slots[1] = 120;
    check(sort_chests(chests, slots, 2, scratch) == 0 && count_present(chest_a) == 0, "empty boxes");
    for (s = 0; s < 120; ++s) { put(chest_a, s, s % 7, 1, 0, 0, 1 + s % 23, 1 + s % 37, s); put(chest_b, s, 0, 0, 0, 0, 1, 1, 500 + s); }
    n = sort_chests(chests, slots, 2, scratch);
    check(n == 240 && count_present(chest_a) == 120 && count_present(chest_b) == 120, "full boxes");

    /* 5. bad input writes nothing */
    slots[0] = 130;
    memcpy(scratch[0], chest_a, BOX_BYTES);
    check(sort_chests(chests, slots, 1, scratch) == -1, "bad slot count refused");
    slots[0] = 120; slots[1] = 120; slots[2] = 120;
    check(sort_chests(chests, slots, 4, scratch) == -1, "four chests refused");

    /* 6. nine boxes: boxes 1-3 fill, then 4-6, then 7-9; seeds start scattered in all three */
    clear(chest_a); clear(chest_b); clear(chest_c);
    for (s = 0; s < 100; ++s) put(chest_c, 119 - s, 0, 0, 0, 0, 1 + s % 23, 1 + s % 37, 1000 + s);
    for (s = 0; s < 90; ++s) put(chest_b, s * 7 % 120, 0, 0, 0, 0, 23 - s % 23, 2, 2000 + s);
    for (s = 0; s < 110; ++s) put(chest_a, s, 3, 3, 0, 0, 1 + s % 5, 18, 3000 + s);
    slots[0] = 120; slots[1] = 120; slots[2] = 120;
    n = sort_chests(chests, slots, 3, scratch);
    check(n == 300, "three hundred seeds over nine boxes");
    check(count_present(chest_a) == 120 && count_present(chest_b) == 120 && count_present(chest_c) == 60,
          "boxes 1-3, then 4-6, then 7-9");
    ok = 1;
    for (s = 0; s < 60; ++s) ok &= present(chest_c, s);
    for (s = 60; s < BOX_RECORDS; ++s) ok &= !present(chest_c, s);
    check(ok, "boxes 7-9 packed from their first slot");
    {
        static int seen[4000];
        int c2, tags_ok = 1;
        unsigned char *all[3] = { chest_a, chest_b, chest_c };
        memset(seen, 0, sizeof seen);
        for (c2 = 0; c2 < 3; ++c2)
            for (s = 0; s < BOX_RECORDS; ++s)
                if (present(all[c2], s)) seen[tag(all[c2], s)]++;
        for (s = 0; s < 100; ++s) tags_ok &= seen[1000 + s] == 1;
        for (s = 0; s < 90; ++s) tags_ok &= seen[2000 + s] == 1;
        for (s = 0; s < 110; ++s) tags_ok &= seen[3000 + s] == 1;
        check(tags_ok, "every seed once, none lost or doubled");
    }

    /* 7. boxes 7-9 with one drawer: the sort never writes their locked drawers */
    clear(chest_a); clear(chest_b); clear(chest_c);
    put(chest_c, 80, 0, 0, 0, 0, 1, 1, 77);                 /* in the Ninth's drawer, not owned */
    memcpy(locked_before, slot(chest_c, 80), RECORD_BYTES);
    for (s = 0; s < 45; ++s) put(chest_b, s, 0, 0, 0, 0, 1 + s % 23, 1, 400 + s);
    slots[0] = 40; slots[1] = 120; slots[2] = 40;
    n = sort_chests(chests, slots, 3, scratch);
    check(n == 45 && count_present(chest_a) == 40 && count_present(chest_b) == 5
          && memcmp(locked_before, slot(chest_c, 80), RECORD_BYTES) == 0 && count_present(chest_c) == 1,
          "locked drawers of boxes 7-9 untouched");

    /* 8. full nine boxes */
    for (s = 0; s < 120; ++s) {
        put(chest_a, s, 0, 0, 0, 0, 1 + s % 23, 1, s);
        put(chest_b, s, 0, 0, 0, 0, 1 + s % 19, 2, 200 + s);
        put(chest_c, s, 0, 0, 0, 0, 1 + s % 17, 3, 400 + s);
    }
    slots[0] = 120; slots[1] = 120; slots[2] = 120;
    n = sort_chests(chests, slots, 3, scratch);
    check(n == 360 && count_present(chest_a) == 120 && count_present(chest_b) == 120 && count_present(chest_c) == 120,
          "nine full boxes");

    printf("%s\n", failures ? "FAILED" : "ALL OK");
    return failures != 0;
}
