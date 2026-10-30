/* count_text.h -- the text of the tank and greenhouse counts, built in a
   fixed buffer (no CRT formatting, nothing allocated).  Shared by
   "Tank Counts.dll" (Fish Tycoon) and "Greenhouse Counts.dll" (Plant
   Tycoon). */
#ifndef FTFP_COUNT_TEXT_H
#define FTFP_COUNT_TEXT_H

#define COUNT_LINE 160

typedef struct count_line {
    char text[COUNT_LINE];
    int at;
    int parts;              /* parts in the open bracket (ct_part, ct_close) */
} count_line;

static void ct_start(count_line *line) {
    line->at = 0;
    line->parts = 0;
    line->text[0] = '\0';
}

static void ct_text(count_line *line, const char *text) {
    while (*text && line->at < COUNT_LINE - 1) line->text[line->at++] = *text++;
    line->text[line->at] = '\0';
}

static void ct_number(count_line *line, int value) {
    char digits[12];
    unsigned int v = value < 0 ? 0u : (unsigned int)value;
    int n = 0;
    do {
        digits[n++] = (char)('0' + v % 10u);
        v /= 10u;
    } while (v != 0u && n < 11);
    while (n > 0 && line->at < COUNT_LINE - 1) line->text[line->at++] = digits[--n];
    line->text[line->at] = '\0';
}

/* "<label><n><between><room>", e.g. "Fish: 12 of 21". */
static void ct_count(count_line *line, const char *label, int n, const char *between, int room) {
    ct_text(line, label);
    ct_number(line, n);
    ct_text(line, between);
    ct_number(line, room);
}

/* One "n word" part of the bracket, "(8 adults, 3 teens, 1 baby)": nothing
   for n == 0; the bracket opens before the first part (ct_close shuts it). */
static void ct_part(count_line *line, int n, const char *one, const char *many) {
    if (n <= 0) return;
    ct_text(line, line->parts == 0 ? " (" : ", ");
    ct_number(line, n);
    ct_text(line, " ");
    ct_text(line, n == 1 ? one : many);
    ++line->parts;
}

static void ct_close(count_line *line) {
    if (line->parts > 0) ct_text(line, ")");
    line->parts = 0;
}

/* "  Dead: 2" after the count, only when there are dead ones. */
static void ct_dead(count_line *line, const char *label, int n) {
    if (n <= 0) return;
    ct_text(line, "  ");
    ct_text(line, label);
    ct_number(line, n);
}

#endif /* FTFP_COUNT_TEXT_H */
