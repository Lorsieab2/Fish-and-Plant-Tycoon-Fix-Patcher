/* count_toggle.h -- the tank and greenhouse counts' on/off button: its
   click area, its hover, and its state, remembered in an .ini file beside
   the DLL ("<DLL folder>\Tank Counts.ini" / "Greenhouse Counts.ini",
   [Counts] Shown=1 or 0), never in a save.  Shared by "Tank Counts.dll" and
   "Greenhouse Counts.dll".

   Mouse events, as both games' scene tables pass them: 1 = move, 2 = button
   down, 3 = button up.  A press inside the button while nothing is held
   toggles the counts, and that press and its release never reach the game;
   every other event (moves, presses elsewhere or while dragging something)
   goes to the game untouched. */
#ifndef FTFP_COUNT_TOGGLE_H
#define FTFP_COUNT_TOGGLE_H

#include <windows.h>

#define MOUSE_MOVE 1
#define MOUSE_DOWN 2
#define MOUSE_UP 3

EXTERN_C IMAGE_DOS_HEADER __ImageBase;

typedef struct count_toggle {
    int shown;              /* the counts are drawn */
    int hovered;            /* the mouse is over the button */
    int swallowed;          /* the button took a press: its release is the button's too */
    RECT box;               /* the click area (inclusive) */
    wchar_t ini[1024];      /* "" when the DLL's folder is unknown: nothing is remembered */
} count_toggle;

/* This DLL's folder, with its trailing backslash; 0 when it is unknown or too long. */
static int dll_folder(wchar_t *out, DWORD cap) {
    wchar_t *slash;
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, out, cap);
    if (n == 0 || n >= cap || (slash = wcsrchr(out, L'\\')) == NULL) return 0;
    slash[1] = L'\0';
    return wcslen(out) + 40 < cap;
}

/* The game's own text measure (Fish 0x4023D0, Plant 0x402380): thiscall (font, text, float scale), the
   width in pixels. */
typedef int (__fastcall *toggle_width_fn)(void *font, void *edx, const char *text, float scale);

#define TOGGLE_SCREEN_RIGHT 796     /* the button's label ends here at the latest (its shadow is 1 pixel more) */

/* The button's label, drawn from x: copied into out[0..cap), and the x to draw it at.  A label that fits
   before the screen's right edge (every English one) stays at x; a wider (translated) one moves left so
   it ends at the edge; only a label wider than the whole screen is cut, from its end.  *width gets the
   drawn width.  A measure that fails leaves the label where it was. */
static int toggle_label(char *out, int cap, const char *text, int x, toggle_width_fn measure, void *font,
                        int *width) {
    int n = 0, w = 0, at = x;
    while (text[n] != '\0' && n < cap - 1) { out[n] = text[n]; ++n; }
    out[n] = '\0';
    __try {
        w = measure(font, NULL, out, 1.0f);
        if (x + w > TOGGLE_SCREEN_RIGHT) {
            at = TOGGLE_SCREEN_RIGHT - w;
            if (at < 0) {
                at = 0;
                while (n > 0 && w > TOGGLE_SCREEN_RIGHT) {
                    --n;
                    while (n > 0 && ((unsigned char)out[n] & 0xC0) == 0x80) --n;   /* never half a UTF-8 letter */
                    out[n] = '\0';
                    w = measure(font, NULL, out, 1.0f);
                }
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        at = x;
        w = 0;
    }
    *width = w;
    return at;
}

/* Shown unless the .ini says Shown=0. */
static void toggle_load(count_toggle *t, const wchar_t *ini_name) {
    t->shown = 1;
    t->ini[0] = L'\0';
    if (!dll_folder(t->ini, 1024)) return;
    wcscat_s(t->ini, 1024, ini_name);
    t->shown = GetPrivateProfileIntW(L"Counts", L"Shown", 1, t->ini) != 0;
}

static int toggle_inside(const count_toggle *t, int x, int y) {
    return x >= t->box.left && x <= t->box.right && y >= t->box.top && y <= t->box.bottom;
}

/* 1 when the event was the button's (the game must not see it). */
static int toggle_mouse(count_toggle *t, int type, int x, int y, int idle) {
    if (type == MOUSE_MOVE) {
        t->hovered = toggle_inside(t, x, y);
        return 0;
    }
    if (type == MOUSE_DOWN && idle && toggle_inside(t, x, y)) {
        t->shown = !t->shown;
        t->swallowed = 1;
        if (t->ini[0] != L'\0') WritePrivateProfileStringW(L"Counts", L"Shown", t->shown ? L"1" : L"0", t->ini);
        return 1;
    }
    if (type == MOUSE_UP && t->swallowed) {
        t->swallowed = 0;
        return 1;
    }
    return 0;
}

#endif /* FTFP_COUNT_TOGGLE_H */
