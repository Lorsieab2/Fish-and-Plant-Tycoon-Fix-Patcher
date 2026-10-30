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
