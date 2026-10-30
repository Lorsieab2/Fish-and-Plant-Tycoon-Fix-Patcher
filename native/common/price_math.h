/* The Breeding Guide's "best per day" price, for the Optimize Prices DLLs.

   A line-for-line port of src/breeding_fish.py (sale_threshold, sale_chance,
   income_per_day, crowd, best_asking_price, shop_best_price) and
   src/breeding_plant.py (seen_price, sale_k, roll_chance, sale_chance,
   income_per_day, visitor_limit, price_search, shop_best_price), for the
   cases the button uses: every double is computed by the same operations in
   the same order, so the results are the same numbers.
   tests/test_optimize_prices.py compiles native/common/price_math_harness.c
   and checks them against the Python for many inputs. */
#ifndef FTFP_PRICE_MATH_H
#define FTFP_PRICE_MATH_H

#define PM_RAND_PERIOD 32768             /* Random(n) is rand() % n, rand() 0..32767 */
#define PM_DAY_SECONDS 86400

/* ------------------------------------------------------------ Fish Tycoon */

#define PM_FISH_SALE_ROLL 900            /* Random(900) <= T sells (0x424240) */
#define PM_FISH_SALE_PAUSE 5             /* real seconds with no roll after a sale */

/* x to the whole power n, one multiplication at a time (breeding_fish.power). */
static double pm_power(double x, int n) {
    double result = 1.0;
    int i;
    for (i = 0; i < n; ++i) result *= x;
    return result;
}

/* How many rand() values make Random(n) < k (breeding_fish.rand_count). */
static int pm_rand_count(int n, int k) {
    int full, extra;
    if (n <= 1) return k > 0 ? PM_RAND_PERIOD : 0;
    if (k < 0) k = 0;
    if (k > n) k = n;
    full = PM_RAND_PERIOD / n;
    extra = PM_RAND_PERIOD % n;
    return full * k + (k < extra ? k : extra);
}

/* T of one healthy adult, or -1 when it cannot sell (asking 2B or more). */
static int pm_fish_threshold(int price, int base, int browsing) {
    int k = (browsing + 2) / 2;
    if (price < base) return base - price >= base / 2 ? 30 * k : 10 * k;
    if (price >= 2 * base) return -1;
    if (price - base <= base / 2) return 4 * k;
    return k;
}

static double pm_fish_chance(int price, int base, int browsing) {
    int t = pm_fish_threshold(price, base, browsing);
    if (t < 0) return 0.0;
    return (double)pm_rand_count(PM_FISH_SALE_ROLL, t + 1) / PM_RAND_PERIOD;
}

static double pm_fish_income(int price, int base, int browsing, int fish) {
    double p = pm_fish_chance(price, base, browsing), q;
    if (p <= 0 || price <= 0) return 0.0;
    q = 1.0 - pm_power(1.0 - p, fish);
    return (double)(price * PM_DAY_SECONDS) / (PM_FISH_SALE_PAUSE + 1.0 / q);
}

/* 4 + ornaments + 2 for the Golden Seahorse + 2 x Advertising x (adults / 3 + Random(2) + 2). */
static int pm_fish_crowd(int ornaments, int seahorse, int advertising, int adults, int extra) {
    return 4 + ornaments + (seahorse ? 2 : 0) + 2 * advertising * (adults / 3 + extra + 2);
}

/* The asking price with the most money per real day over the two crowds
   (Random(2) = 0 or 1), the lowest on a tie; 0 when none earns anything. */
static int pm_fish_best(int base, int ornaments, int seahorse, int advertising, int tank) {
    int crowds[2], price, best_price = 0, r;
    double best_income = 0.0, income;
    for (r = 0; r < 2; ++r) crowds[r] = pm_fish_crowd(ornaments, seahorse, advertising, tank, r);
    for (price = 1; price < 2 * base; ++price) {
        income = 0.0;
        for (r = 0; r < 2; ++r) income += pm_fish_income(price, base, crowds[r], tank);
        income /= 2;
        if (income > best_income + 1e-9) {
            best_price = price;
            best_income = income;
        }
    }
    return best_price;
}

/* ----------------------------------------------------------- Plant Tycoon */

#define PM_PLANT_SALE_ROLL 1300          /* Random(1300) <= k * E sells (0x436BE0) */
#define PM_PLANT_TICK_SECONDS 2          /* a nursery tick every 2 real seconds */
#define PM_PLANT_GROW_SECONDS (24 * 600) /* age 24 at Normal speed, 10 minutes a unit */
#define PM_PLANT_MAX_PRICE 9999          /* "Set species price" caps typed values */

/* The price visitors see for a healthy, flowering, unpruned plant without
   Plant Food: the Golden Berries of Wealth take a quarter off. */
static int pm_plant_seen(int asking, int golden_berries) {
    int p = asking;
    if (golden_berries) p -= p / 4;
    return p;
}

/* k of the roll, or -1 when it never sells (not the tutorial's first sale). */
static int pm_plant_k(int asking, int v, int golden_berries) {
    int p = pm_plant_seen(asking, golden_berries);
    if (p < v) return v - p >= v / 2 ? 30 : 10;
    if (p - v >= v) return -1;
    return p - v > v / 2 ? 2 : 5;
}

static double pm_plant_roll(int threshold) {
    int full, extra, count;
    if (threshold < 0) return 0.0;
    if (threshold >= PM_PLANT_SALE_ROLL - 1) return 1.0;
    full = PM_RAND_PERIOD / PM_PLANT_SALE_ROLL;
    extra = PM_RAND_PERIOD % PM_PLANT_SALE_ROLL;
    count = (threshold + 1) * full + (threshold + 1 < extra ? threshold + 1 : extra);
    return (double)count / PM_RAND_PERIOD;
}

static double pm_plant_chance(int asking, int v, int browsing, int golden_berries) {
    int k;
    if (browsing <= 0) return 0.0;
    k = pm_plant_k(asking, v, golden_berries);
    return k < 0 ? 0.0 : pm_plant_roll(k * (browsing / 2));
}

static double pm_plant_income(int asking, int v, int browsing, int golden_berries) {
    double chance = pm_plant_chance(asking, v, browsing, golden_berries), cycle;
    if (chance <= 0) return 0.0;
    cycle = PM_PLANT_GROW_SECONDS + PM_PLANT_TICK_SECONDS / chance;
    return (double)(asking * PM_DAY_SECONDS) / cycle;
}

/* 0x43FF00: at most 8 + 47 S / 78 visitors. */
static int pm_plant_visitors(int score) { return 8 + (47 * score) / 78; }

/* The best asking price for value V, or 0 when none sells. */
static int pm_plant_best(int v, int golden_berries, int score) {
    int browsing = pm_plant_visitors(score), p, best = 0;
    double best_income = 0.0, income;
    for (p = 1; p <= PM_PLANT_MAX_PRICE; ++p) {
        if (pm_plant_seen(p, golden_berries) >= 2 * v) break;
        if (pm_plant_k(p, v, golden_berries) < 0) continue;
        income = pm_plant_income(p, v, browsing, golden_berries);
        if (income > best_income) {
            best = p;
            best_income = income;
        }
    }
    return best;
}

#endif
