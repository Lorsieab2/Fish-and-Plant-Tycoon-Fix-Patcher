/* The highest selling price the game would ever allow for a species: the
   Breeding Guide's "Highest selling" with "Max effects" (prices(key, "max")),
   for the Radioactive Growth Hormone / Radioactive Plant Formula rule that a
   treated fish or plant always sells for it.

   A line-for-line port of src/breeding_fish.py (base_price, advertised, and
   FishModel.prices' highest selling 2B - 1 at Advertising level 3) and
   src/breeding_plant.py (value, seen_price, sale_k, and price_search's
   highest asking price that sells, with MAX_EFFECTS).  Kept apart from
   price_math.h (the Optimize Prices button's maths), which it does not
   change.  tests/test_radioactive_max_price.py compiles
   native/common/max_sale_price_harness.c and checks every species against
   the Python. */
#ifndef FTFP_MAX_SALE_PRICE_H
#define FTFP_MAX_SALE_PRICE_H

/* ------------------------------------------------------------ Fish Tycoon */

#define MS_FISH_PC_LAST 20
#define MS_FISH_DS_FIRST 23
#define MS_FISH_DS_LAST 29
#define MS_FISH_ADVERTISING_MAX 3        /* Advertising research's last level */

/* B for each stock species, [body][fin], as 0x418B10 sets it (breeding_fish.BASE_PRICES). */
static const unsigned char MS_FISH_BASE[21][21] = {
    { 4, 12, 6, 12, 4, 12, 8, 12, 8, 22, 6, 26, 4, 12, 6, 12, 8, 12, 5, 12, 4 },
    { 12, 20, 30, 20, 12, 20, 16, 20, 16, 30, 14, 34, 12, 20, 14, 20, 16, 20, 13, 20, 12 },
    { 7, 15, 9, 15, 7, 15, 33, 15, 11, 25, 9, 29, 7, 15, 9, 15, 11, 15, 8, 15, 7 },
    { 12, 20, 14, 20, 12, 20, 16, 20, 16, 30, 14, 34, 12, 20, 14, 20, 16, 20, 13, 20, 12 },
    { 4, 12, 6, 12, 4, 12, 8, 12, 8, 22, 6, 26, 4, 12, 6, 12, 8, 12, 5, 12, 4 },
    { 16, 24, 18, 24, 16, 24, 20, 24, 70, 34, 18, 38, 16, 24, 18, 24, 20, 24, 17, 24, 16 },
    { 7, 15, 9, 15, 7, 15, 11, 15, 11, 25, 9, 29, 7, 15, 33, 15, 11, 15, 8, 15, 7 },
    { 27, 35, 29, 35, 27, 35, 31, 190, 31, 45, 29, 49, 27, 35, 29, 35, 31, 35, 28, 35, 27 },
    { 10, 18, 12, 18, 10, 18, 14, 18, 20, 28, 12, 32, 10, 18, 12, 18, 14, 18, 11, 18, 10 },
    { 12, 20, 14, 20, 12, 20, 16, 20, 16, 30, 14, 34, 12, 20, 14, 20, 16, 20, 13, 20, 12 },
    { 17, 25, 19, 25, 17, 25, 21, 25, 21, 70, 33, 39, 17, 25, 19, 25, 21, 25, 18, 25, 17 },
    { 12, 20, 14, 20, 12, 20, 16, 20, 16, 30, 14, 70, 12, 20, 14, 20, 16, 20, 13, 20, 12 },
    { 4, 12, 6, 12, 4, 12, 8, 12, 8, 22, 6, 26, 4, 12, 6, 12, 8, 12, 5, 12, 4 },
    { 20, 28, 22, 28, 20, 28, 95, 28, 24, 38, 22, 42, 20, 28, 22, 28, 24, 28, 21, 28, 20 },
    { 17, 25, 19, 25, 17, 25, 21, 25, 21, 35, 19, 39, 17, 25, 55, 25, 21, 25, 18, 25, 17 },
    { 12, 20, 14, 20, 12, 20, 16, 20, 16, 30, 14, 34, 12, 20, 14, 20, 16, 20, 13, 20, 12 },
    { 11, 19, 13, 19, 11, 19, 15, 19, 15, 29, 13, 33, 11, 19, 13, 19, 15, 19, 12, 19, 11 },
    { 12, 20, 14, 20, 12, 20, 16, 20, 16, 45, 14, 34, 12, 20, 14, 20, 16, 20, 13, 20, 12 },
    { 11, 19, 13, 19, 11, 19, 15, 19, 15, 29, 13, 33, 11, 19, 13, 19, 15, 19, 12, 19, 11 },
    { 22, 30, 24, 30, 22, 30, 26, 30, 26, 40, 24, 44, 22, 30, 24, 30, 26, 30, 23, 30, 22 },
    { 4, 12, 6, 12, 4, 12, 8, 12, 8, 22, 6, 26, 4, 12, 6, 12, 48, 12, 5, 12, 4 },
};
/* The DS game's values by DS index (DS_BODY_VALUE / DS_FIN_VALUE, the DS Fish DLL's ds_data.h). */
static const unsigned char MS_DS_BODY_VALUE[28] = {
    2, 10, 5, 10, 2, 14, 5, 25, 8, 10, 15, 10, 2, 18, 15, 10, 9, 10, 9, 20, 2, 10, 4, 9, 6, 10, 8, 17 };
static const unsigned char MS_DS_FIN_VALUE[28] = {
    2, 10, 4, 10, 2, 10, 6, 10, 6, 20, 4, 24, 2, 10, 4, 10, 6, 10, 3, 10, 2, 10, 5, 11, 3, 15, 7, 15 };

static int ms_fish_gene(int g) { return (g >= 0 && g <= MS_FISH_PC_LAST) || (g >= MS_FISH_DS_FIRST && g <= MS_FISH_DS_LAST); }
static int ms_fish_is_ds(int g) { return g >= MS_FISH_DS_FIRST && g <= MS_FISH_DS_LAST; }
static int ms_fish_ds_index(int g) { return g <= MS_FISH_PC_LAST ? g : g - 2; }

/* breeding_fish.base_price; -1 when (body, fin) is not a species (the seahorse-type 21/22). */
static int ms_fish_base_price(int body, int fin) {
    int b, f;
    if (!ms_fish_gene(body) || !ms_fish_gene(fin)) return -1;
    if (!ms_fish_is_ds(body) && !ms_fish_is_ds(fin)) return MS_FISH_BASE[body][fin];
    b = ms_fish_ds_index(body);
    f = ms_fish_ds_index(fin);
    return MS_DS_BODY_VALUE[b] + MS_DS_FIN_VALUE[f] + (b == f && b > MS_FISH_PC_LAST ? 10 : 0);
}

/* breeding_fish.advertised: level 2 adds B / 10 (0x420AE6), level 3 then B / 7 (0x420A82). */
static int ms_fish_advertised(int base, int level) {
    if (level >= 2) base += base / 10;
    if (level >= 3) base += base / 7;
    return base;
}

/* FishModel.prices(key, "max").highest_selling: 2B - 1 with B after Advertising level 3 (an asking
   price of 2B or more never sells, 0x4243E4); 0 when (body, fin) is not a species. */
static int ms_fish_max_price(int body, int fin) {
    int base = ms_fish_base_price(body, fin);
    if (base < 0) return 0;
    base = ms_fish_advertised(base, MS_FISH_ADVERTISING_MAX);
    return 2 * base - 1;
}

/* ----------------------------------------------------------- Plant Tycoon */

#define MS_PLANT_FOLIAGES 23
#define MS_PLANT_FLOWERS 37                /* 24-37: Unused Flowers */
#define MS_PLANT_MAX_TYPED_PRICE 9999      /* breeding_plant.MAX_TYPED_PRICE */

/* V = MS_FOLIAGE_BASE[foliage] + MS_FLOWER_ADD[flower] (0x41D870), except MS_VALUE_EXCEPTIONS. */
static const unsigned char MS_FOLIAGE_BASE[24] = {
    0, 4, 28, 16, 36, 5, 36, 20, 28, 5, 30, 18, 34, 6, 32, 22, 42, 6, 68, 48, 70, 60, 64, 66 };
static const unsigned char MS_FLOWER_ADD[38] = {
    0, 3, 13, 8, 39, 4, 20, 10, 21, 5, 28, 10, 13, 6, 34, 8, 10, 4, 40, 64, 30, 32, 36, 26,
    60, 60, 45, 45, 45, 45, 35, 35, 35, 70, 70, 55, 50, 50 };
static const struct { unsigned char foliage, flower; unsigned char value; } MS_VALUE_EXCEPTIONS[8] = {
    { 2, 14, 130 }, { 3, 15, 79 }, { 4, 4, 95 }, { 7, 7, 75 }, { 7, 11, 46 }, { 11, 10, 250 }, { 13, 13, 44 },
    { 14, 16, 110 } };

/* breeding_plant.value; 0 when (foliage, flower) is not a species. */
static int ms_plant_value(int foliage, int flower) {
    int i;
    if (foliage < 1 || foliage > MS_PLANT_FOLIAGES || flower < 1 || flower > MS_PLANT_FLOWERS) return 0;
    for (i = 0; i < 8; ++i)
        if (MS_VALUE_EXCEPTIONS[i].foliage == foliage && MS_VALUE_EXCEPTIONS[i].flower == flower)
            return MS_VALUE_EXCEPTIONS[i].value;
    return MS_FOLIAGE_BASE[foliage] + MS_FLOWER_ADD[flower];
}

/* breeding_plant.Condition. */
typedef struct ms_condition {
    int over_pruned, cut_parts_2, dead_foliage, health, flowers, plant_food, infested, golden_berries,
        tutorial_first_sale;
} ms_condition;

/* breeding_plant.MAX_EFFECTS: 2+ cut parts, 2 Plant Food doses, the Golden Berries of Wealth, a healthy
   flowering plant. */
static const ms_condition MS_MAX_EFFECTS = { 0, 1, 0, 100, 1, 2, 0, 1, 0 };

/* breeding_plant.seen_price (0x436D4B-0x436E3C); C's division is _cdiv's. */
static int ms_plant_seen_price(int asking, const ms_condition *c) {
    int p = asking;
    if (c->over_pruned) p *= 5;
    else if (c->cut_parts_2) p -= p / 8;
    if (c->dead_foliage) p += p / 3;
    if (c->health < 15) p += p / 4;
    if (!c->over_pruned && c->flowers == 0) p *= 2;
    if (c->plant_food > 0) p -= p / 5;
    if (c->plant_food >= 2) p -= p / 5;
    if (c->infested) p *= 3;
    if (c->golden_berries) p -= p / 4;
    return p;
}

/* breeding_plant.sale_k: k of the roll Random(1300) <= k x E, or -1 (None) when it never sells. */
static int ms_plant_sale_k(int asking, int v, const ms_condition *c) {
    int p = ms_plant_seen_price(asking, c);
    if (c->tutorial_first_sale && p < 3 * v) return 70;
    if (p < v && !c->infested) return v - p >= v / 2 ? 30 : 10;
    if (p - v >= v) return -1;
    return p - v > v / 2 ? 2 : 5;
}

/* price_search(v, c, browsing)'s third answer, the highest asking price that sells (it does not
   depend on the visitors): asking prices 1-9999, up to the last one whose price seen is below 2V. */
static int ms_plant_highest_selling(int v, const ms_condition *c) {
    int p, highest = 0;
    for (p = 1; p <= MS_PLANT_MAX_TYPED_PRICE; ++p) {
        if (!c->tutorial_first_sale && ms_plant_seen_price(p, c) >= 2 * v) break;
        if (ms_plant_sale_k(p, v, c) < 0) continue;
        highest = p;
    }
    return highest;
}

/* PlantModel.prices(key, "max").highest_selling; 0 when (foliage, flower) is not a species. */
static int ms_plant_max_price(int foliage, int flower) {
    int v = ms_plant_value(foliage, flower);
    return v > 0 ? ms_plant_highest_selling(v, &MS_MAX_EFFECTS) : 0;
}

#endif
