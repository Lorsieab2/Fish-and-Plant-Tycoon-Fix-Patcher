/* Test harness: the companion's rules without the game.  Prints one line per
   decision for tests/test_ds_fish_logic.py to check.  The game's Random(n)
   is replaced by a scripted value. */
#include <stdio.h>

static int scripted = 0;
#define FTFP_TEST_RANDOM(bound) (scripted % (bound))
#include "ftfp_ds_fish.c"

static const int GENES[] = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
                             23, 24, 25, 26, 27, 28, 29 };
#define GENE_COUNT (sizeof GENES / sizeof GENES[0])

int main(void) {
    unsigned int i, j;
    int c, r, g, f, out[2];
    /* breed a b coin -> baby */
    for (i = 0; i < GENE_COUNT; ++i) {
        for (j = 0; j < GENE_COUNT; ++j) {
            for (c = 0; c < 2; ++c) {
                scripted = c;
                coin_tick = GetTickCount() ^ 0x80000000u;    /* force a fresh litter roll */
                printf("breed %d %d %d %d\n", GENES[i], GENES[j], c, breed_gene(GENES[i], GENES[j]));
            }
        }
    }
    /* step gene roll -> gene */
    for (i = 0; i < GENE_COUNT; ++i) {
        static const int rolls[] = { 0, 49, 50, 99 };
        for (r = 0; r < 4; ++r) {
            int gene = GENES[i];
            scripted = rolls[r];
            step_gene(&gene);
            printf("step %d %d %d\n", GENES[i], rolls[r], gene);
        }
    }
    {
        int gene = GENE_SEAHORSE;
        step_gene(&gene);
        printf("step 22 0 %d\n", gene);
    }
    /* tier gene -> tier */
    for (g = 0; g <= 29; ++g) printf("tier %d %d\n", g, gene_tier(g));
    /* decode id -> entry frame */
    for (g = 0; g <= 29; ++g) {
        for (f = 1; f <= 90; ++f) {
            decode_sprite(10000 + g * 100 + f, out);
            printf("decode %d %d %d\n", 10000 + g * 100 + f, out[0], out[1]);
        }
    }
    /* anchors body fin -> written? x4 */
    for (i = 0; i < GENE_COUNT; ++i) {
        for (j = 0; j < GENE_COUNT; ++j) {
            int sprite[9] = { 0, 0, 0, 0, 0, -1, -1, -1, -1 };
            pair_anchors(sprite, GENES[i], GENES[j]);
            printf("anchor %d %d %d %d %d %d\n", GENES[i], GENES[j], sprite[5], sprite[6], sprite[7], sprite[8]);
        }
    }
    /* head-on: PC pairs must give the game's own value */
    for (i = 0; i < GENE_COUNT; ++i) {
        for (j = 0; j < GENE_COUNT; ++j) {
            for (r = 0; r < 6; ++r) {
                printf("headon %d %d %d %d %d\n", GENES[i], GENES[j], r,
                       head_on_x(GENES[i], GENES[j], 0, r, 17, -13),
                       head_on_x(GENES[i], GENES[j], 1, r, 21, 10));
            }
        }
    }
    /* prices and names */
    for (i = 0; i < GENE_COUNT; ++i) {
        for (j = 0; j < GENE_COUNT; ++j) {
            unsigned char e[ENTRY_SIZE];
            memset(e, 0, sizeof e);
            set_name(e, GENES[i], GENES[j]);
            printf("species %d %d %d %s\n", GENES[i], GENES[j], ds_price(GENES[i], GENES[j]), (char *)e);
        }
    }
    return 0;
}
