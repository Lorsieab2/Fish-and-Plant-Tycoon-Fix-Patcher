/* Time Warp's Windows popups, shared by the Fish and Plant Tycoon store DLLs.

   tw_ask_hours() shows a small modal dialog built in memory (no resources):
   a line of text, a digits-only box (1-72) and OK / Cancel.  It returns the
   hours, or 0 when the player cancels.  tw_confirm() is a Yes / No message
   box, tw_tell() and tw_done() OK message boxes.  All are parented to the game's window, so they stay in front of it,
   and SDL is asked not to minimise a fullscreen game when the popup takes the
   focus (SDL2's SDL_HINT_VIDEO_MINIMIZE_ON_FOCUS_LOSS, when SDL2.dll is the
   game's SDL; best effort, nothing happens if it is not). */
#ifndef FTFP_TIME_WARP_POPUP_H
#define FTFP_TIME_WARP_POPUP_H

#include <windows.h>
#include <wchar.h>
#include "setting_file.h"

#define TW_MIN_HOURS 1
#define TW_MAX_HOURS 72
#define TW_EDIT 100

typedef int (__cdecl *tw_sdl_hint_fn)(const char *name, const char *value);

static HWND tw_game_window(void) {
    HWND h = GetActiveWindow();
    if (h == NULL) h = GetForegroundWindow();
    return h;
}

static void tw_keep_game_open(void) {
    HMODULE sdl = GetModuleHandleW(L"SDL2.dll");
    tw_sdl_hint_fn hint;
    if (sdl == NULL) return;
    hint = (tw_sdl_hint_fn)GetProcAddress(sdl, "SDL_SetHint");
    if (hint != NULL) hint("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0");
}

typedef struct tw_dialog_data {
    const wchar_t *line2;
    int hours;
} tw_dialog_data;

static INT_PTR CALLBACK tw_proc(HWND dlg, UINT msg, WPARAM wp, LPARAM lp) {
    tw_dialog_data *data;
    switch (msg) {
    case WM_INITDIALOG:
        data = (tw_dialog_data *)lp;
        SetWindowLongPtrW(dlg, DWLP_USER, (LONG_PTR)data);
        SetDlgItemTextW(dlg, 101, data->line2);
        SendDlgItemMessageW(dlg, TW_EDIT, EM_SETLIMITTEXT, 2, 0);
        SetDlgItemInt(dlg, TW_EDIT, 1, FALSE);
        SendDlgItemMessageW(dlg, TW_EDIT, EM_SETSEL, 0, -1);
        SetFocus(GetDlgItem(dlg, TW_EDIT));
        SetForegroundWindow(dlg);
        return FALSE;                                  /* we set the focus */
    case WM_COMMAND:
        data = (tw_dialog_data *)GetWindowLongPtrW(dlg, DWLP_USER);
        if (LOWORD(wp) == IDOK) {
            BOOL ok = FALSE;
            UINT n = GetDlgItemInt(dlg, TW_EDIT, &ok, FALSE);
            if (!ok || n < TW_MIN_HOURS || n > TW_MAX_HOURS) {
                MessageBoxW(dlg, L"Please type a whole number of hours from 1 to 72.", L"Time Warp",
                            MB_OK | MB_ICONINFORMATION);
                SetFocus(GetDlgItem(dlg, TW_EDIT));
                return TRUE;
            }
            if (data != NULL) data->hours = (int)n;
            EndDialog(dlg, 1);
            return TRUE;
        }
        if (LOWORD(wp) == IDCANCEL) {
            EndDialog(dlg, 0);
            return TRUE;
        }
        break;
    }
    return FALSE;
}

/* --- a dialog template in memory --------------------------------------- */

typedef struct tw_template { WORD buf[1024]; int at; } tw_template;

static void tw_word(tw_template *t, WORD w) { if (t->at < 1024) t->buf[t->at++] = w; }
static void tw_dword(tw_template *t, DWORD d) { tw_word(t, LOWORD(d)); tw_word(t, HIWORD(d)); }
static void tw_text(tw_template *t, const wchar_t *s) { do { tw_word(t, *s); } while (*s++); }
static void tw_align(tw_template *t) { if (t->at & 1) tw_word(t, 0); }

static void tw_item(tw_template *t, DWORD style, short x, short y, short cx, short cy, WORD id,
                    WORD cls, const wchar_t *text) {
    tw_align(t);
    tw_dword(t, style | WS_CHILD | WS_VISIBLE);
    tw_dword(t, 0);
    tw_word(t, (WORD)x); tw_word(t, (WORD)y); tw_word(t, (WORD)cx); tw_word(t, (WORD)cy);
    tw_word(t, id);
    tw_word(t, 0xFFFF); tw_word(t, cls);              /* 0x80 button, 0x81 edit, 0x82 static */
    tw_text(t, text);
    tw_word(t, 0);                                     /* no creation data */
}

/* The hours (1-72), or 0 if cancelled.  line2 is the game-specific hint line. */
static int tw_ask_hours(const wchar_t *line2) {
    static tw_template t;
    tw_dialog_data data;
    INT_PTR r;
    t.at = 0;
    tw_dword(&t, DS_MODALFRAME | DS_SETFONT | DS_CENTER | WS_POPUP | WS_CAPTION | WS_SYSMENU | DS_SETFOREGROUND);
    tw_dword(&t, WS_EX_TOPMOST);
    tw_word(&t, 5);                                    /* five controls */
    tw_word(&t, 0); tw_word(&t, 0); tw_word(&t, 210); tw_word(&t, 86);
    tw_word(&t, 0);                                    /* no menu */
    tw_word(&t, 0);                                    /* default class */
    tw_text(&t, L"Time Warp");
    tw_word(&t, 9);
    tw_text(&t, L"Segoe UI");
    tw_item(&t, SS_LEFT, 8, 8, 194, 10, 0xFFFF, 0x82, L"How many hours should pass? (1-72)");
    tw_item(&t, SS_LEFT, 8, 21, 194, 20, 101, 0x82, L"");
    tw_item(&t, ES_NUMBER | ES_LEFT | WS_BORDER | WS_TABSTOP, 8, 44, 50, 13, TW_EDIT, 0x81, L"");
    tw_item(&t, BS_DEFPUSHBUTTON | WS_TABSTOP, 98, 64, 50, 15, IDOK, 0x80, L"OK");
    tw_item(&t, BS_PUSHBUTTON | WS_TABSTOP, 152, 64, 50, 15, IDCANCEL, 0x80, L"Cancel");
    data.line2 = line2;
    data.hours = 0;
    tw_keep_game_open();
    r = DialogBoxIndirectParamW(GetModuleHandleW(NULL), (LPCDLGTEMPLATEW)t.buf, tw_game_window(), tw_proc,
                                (LPARAM)&data);
    return r == 1 ? data.hours : 0;
}

/* Yes / No, with the item's name as the caption. */
static int tw_confirm_as(const wchar_t *caption, const wchar_t *text) {
    tw_keep_game_open();
    return MessageBoxW(tw_game_window(), text, caption,
                       MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON1 | MB_TOPMOST | MB_SETFOREGROUND) == IDYES;
}

static void tw_tell_as(const wchar_t *caption, const wchar_t *text) {
    tw_keep_game_open();
    MessageBoxW(tw_game_window(), text, caption, MB_OK | MB_ICONINFORMATION | MB_TOPMOST | MB_SETFOREGROUND);
}

static int tw_confirm(const wchar_t *text) { return tw_confirm_as(L"Time Warp", text); }
static void tw_tell(const wchar_t *text) { tw_tell_as(L"Time Warp", text); }

/* After the warp has been played: the hours, the game time they made and the
   price taken, e.g. "Time Warp done: 12 hours played (72 age steps). $500
   paid."  unit is the game's word in the singular ("age step" / "age unit"). */
static void tw_done(int hours, unsigned int steps, const wchar_t *unit, int paid) {
    wchar_t text[160];
    swprintf_s(text, 160, L"Time Warp done: %d hour%s played (%d %s%s). $%d paid.", hours, hours == 1 ? L"" : L"s",
               (int)steps, unit, steps == 1 ? L"" : L"s", paid);
    tw_tell(text);
}

/* "<folder of this DLL>\Time Warp.ini" exists: the Time Warp setting is on. */
static int tw_enabled(HMODULE self) { return ftfp_setting_on(self, L"Time Warp.ini"); }

#endif
