/* Runs native/common/max_sale_price.h for tests/test_radioactive_max_price.py: one
   query a line on stdin, one answer a line on stdout.
     F body fin       ->  the fish species' highest selling price (0: not a species)
     P foliage flower ->  the plant species' highest selling price (0: not a species) */
#include <stdio.h>
#include "max_sale_price.h"

int main(void) {
    char kind;
    int a, b;
    while (scanf_s(" %c", &kind, 1) == 1) {
        if (scanf_s("%d %d", &a, &b) != 2) return 1;
        if (kind == 'F') printf("%d\n", ms_fish_max_price(a, b));
        else if (kind == 'P') printf("%d\n", ms_plant_max_price(a, b));
        else return 1;
    }
    return 0;
}
