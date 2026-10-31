/* Runs native/common/price_math.h for tests/test_optimize_prices.py: one
   query a line on stdin, one answer a line on stdout.
     F base ornaments seahorse advertising tank  ->  the fish price
     P value golden_berries score                ->  the plant price
     f base                                      ->  the fish max price
     p value golden_berries                      ->  the plant max price */
#include <stdio.h>
#include "price_math.h"

int main(void) {
    char kind;
    int a, b, c, d, e;
    while (scanf_s(" %c", &kind, 1) == 1) {
        if (kind == 'F' && scanf_s("%d %d %d %d %d", &a, &b, &c, &d, &e) == 5) {
            printf("%d\n", pm_fish_best(a, b, c, d, e));
        } else if (kind == 'P' && scanf_s("%d %d %d", &a, &b, &c) == 3) {
            printf("%d\n", pm_plant_best(a, b, c));
        } else if (kind == 'f' && scanf_s("%d", &a) == 1) {
            printf("%d\n", pm_fish_max(a));
        } else if (kind == 'p' && scanf_s("%d %d", &a, &b) == 2) {
            printf("%d\n", pm_plant_max(a, b));
        } else {
            return 1;
        }
    }
    return 0;
}
