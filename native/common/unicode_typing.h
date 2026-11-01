/* unicode_typing.h -- "Unicode Text.dll", both games: typing any letter.

   The games post a typed letter as a "character" event (type 5, code, letter) to the focused
   text box (Fish 0x40BFC0, Plant 0x40CA90), which stored the letter as one byte when it was
   0x20-0xFF. Each game's key path now posts every letter (unicode_text's stubs: Fish Tycoon
   keysym.unicode, the UCS-2 letter SDL 1.2 gives a key, past U+00FF too; Plant Tycoon each
   letter of SDL 2's UTF-8 text, so an input method's whole text arrives). The box's
   character path (from Fish 0x40BFF9, Plant 0x40CAC9) is box_char:

     - a letter goes in as its UTF-8 bytes, only whole: while the box's byte limit (+0x28)
       has room for all of them and, in a name box (limit NAME_BOX_BYTES), it has fewer than
       NAME_LETTERS letters;
     - Backspace takes off the last whole letter (the game took one byte);
     - Enter and Tab do what they did (the box's own "done", Fish 0x40BA30, Plant 0x40C4D0);
     - control characters, C1 controls and lone surrogates are dropped;
     - a number box (+0x2D) or a box keeping a number (+0x2F) goes on the game's own way.

   Fish Tycoon's window gets letters SDL 1.2 never reports: SDL takes a key's letter with
   ToUnicode on the key-down and never translates messages, so a letter from the emoji panel
   or another program (VK_PACKET) and an input method's text (WM_IME_CHAR) were lost, and
   keysym.unicode holds one UTF-16 unit, never a letter past U+FFFF. The DLL subclasses the
   game's window (once the game draws): a VK_PACKET key-down is translated and kept from SDL
   and its WM_CHAR read as UTF-16; an input method's finished text (WM_IME_COMPOSITION,
   GCS_RESULTSTR) is read with ImmGetCompositionStringW, and a WM_IME_CHAR sent to the
   window is taken too; each letter is posted, a surrogate pair as its one letter.

   Both games' windows are subclassed (Plant Tycoon's only for what follows): a WM_CHAR that is
   half of a surrogate pair (a letter past U+FFFF sent as two WM_CHARs) is joined and posted as
   its one letter, which the game box dropped; and the clipboard keys of "Copy and Paste in
   Text Boxes" (text_clipboard.h) are taken while a text box has typing focus. */
#ifndef FTFP_UNICODE_TYPING_H
#define FTFP_UNICODE_TYPING_H

typedef void *(__cdecl *events_get_fn)(void);
typedef void (__fastcall *post2_fn)(void *queue, void *edx, int type, int param);
typedef void (__fastcall *post3_fn)(void *queue, void *edx, int type, int code, int letter);
typedef void (__fastcall *box_done_fn)(void *box, void *edx);

static void post_letter(unsigned int cp) {
    void *queue = ((events_get_fn)(UINT_PTR)GAME_EVENTS_GET)();
    ((post3_fn)(UINT_PTR)GAME_EVENTS_POST)(queue, NULL, 5, 0, (int)cp);
}

static void box_changed(char *box) {
    void *queue = ((events_get_fn)(UINT_PTR)GAME_EVENTS_GET)();
    ((post2_fn)(UINT_PTR)GAME_EVENTS_POST2)(queue, NULL, 0xC, *(int *)(box + 4));
}

static int letters_in(const char *text) {
    const unsigned char *p = (const unsigned char *)text;
    int n = 0;
    while (*p) {
        utf8_next(&p);
        ++n;
    }
    return n;
}

/* The box's character event: 1 when done here, 0 for the game's own code. */
static int __cdecl box_char(char *box, unsigned int ch) {
    char *text = *(char **)(box + 0x30);
    int len, limit = *(int *)(box + 0x28), n;
    char bytes[4];
    if (!utf8_drawing || box[0x2D] || box[0x2F] || text == NULL) return 0;
    len = s_len(text);
    if (ch == 8) {
        if (len > 0) {
            text[letter_before(text, text + len) - text] = '\0';
            box_changed(box);
        }
        return 1;
    }
    if (ch == 0xD || ch == 9) {
        ((box_done_fn)(UINT_PTR)GAME_BOX_DONE)(box, NULL);
        return 1;
    }
    if (ch < 0x20 || (ch >= 0x7F && ch < 0xA0) || (ch >= 0xD800 && ch <= 0xDFFF) || ch > 0x10FFFF) return 1;
    n = utf8_put(ch, bytes, 4);
    if (len + n > limit) return 1;
    if (limit == NAME_BOX_BYTES && letters_in(text) >= NAME_LETTERS) return 1;
    memcpy(text + len, bytes, (size_t)n);
    text[len + n] = '\0';
    box_changed(box);
    return 1;
}

__declspec(naked) static void stub_box_char(void) {
    __asm {
        push ecx
        push dword ptr [esp + 0x10]
        push ecx
        call box_char
        add esp, 8
        pop ecx
        test eax, eax
        jz stock
        mov al, 1
        ret 0xC
    stock:
        cmp byte ptr [ecx + 0x2F], 0
        push ebx
        push esi
        mov edx, GAME_BOX_CHAR_RESUME
        jmp edx
    }
}

/* ---- the game's window (the input method's parts: Fish Tycoon, GAME_SUBCLASS_WINDOW) */

#include <imm.h>
typedef LONG_PTR (WINAPI *set_long_fn)(HWND, int, LONG_PTR);
typedef LRESULT (WINAPI *call_proc_fn)(WNDPROC, HWND, UINT, WPARAM, LPARAM);
typedef BOOL (WINAPI *translate_fn)(const MSG *);
typedef BOOL (WINAPI *enum_fn)(DWORD, WNDENUMPROC, LPARAM);
typedef BOOL (WINAPI *visible_fn)(HWND);
typedef BOOL (WINAPI *peek_fn)(MSG *, HWND, UINT, UINT, UINT);
typedef HIMC (WINAPI *imm_get_fn)(HWND);
typedef LONG (WINAPI *imm_string_fn)(HIMC, DWORD, LPVOID, DWORD);
typedef BOOL (WINAPI *imm_release_fn)(HWND, HIMC);

static struct {
    int tried, done;
    set_long_fn set_long;
    call_proc_fn call_proc;
    translate_fn translate;
    enum_fn enum_windows;
    visible_fn visible;
    peek_fn peek;
    imm_get_fn imm_get;
    imm_string_fn imm_string;
    imm_release_fn imm_release;
    WNDPROC old;
    HWND window;
    WCHAR high;
    unsigned int draws;
} win;

#include "text_clipboard.h"

static void unit_in(WCHAR unit) {
    if (unit >= 0xD800 && unit <= 0xDBFF) {
        win.high = unit;
        return;
    }
    if (unit >= 0xDC00 && unit <= 0xDFFF) {
        if (win.high) post_letter(0x10000u + (((unsigned int)win.high - 0xD800u) << 10) + (unit - 0xDC00u));
        win.high = 0;
        return;
    }
    win.high = 0;
    if (unit >= 0x20 && unit != 0x7F) post_letter(unit);
}

static LRESULT CALLBACK text_window(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == WM_KEYDOWN && clip_key((unsigned int)wparam)) return 0;
    if (message == WM_CHAR && utf8_drawing && wparam >= 0xD800 && wparam <= 0xDFFF) {
        unit_in((WCHAR)wparam);              /* half of a letter past U+FFFF: joined here */
        return 0;
    }
#if GAME_SUBCLASS_WINDOW
    if (message == WM_KEYDOWN && (wparam == VK_PACKET || wparam == VK_PROCESSKEY)) {
        MSG msg;
        memset(&msg, 0, sizeof msg);
        msg.hwnd = window;
        msg.message = message;
        msg.wParam = wparam;
        msg.lParam = lparam;
        win.translate(&msg);
        if (wparam == VK_PACKET) {
            /* its WM_CHAR, read as UTF-16 here (SDL's GetMessageA would make it ANSI) */
            while (win.peek(&msg, window, WM_CHAR, WM_CHAR, PM_REMOVE)) unit_in((WCHAR)msg.wParam);
            return 0;
        }
    } else if (message == WM_IME_COMPOSITION && (lparam & GCS_RESULTSTR) && win.imm_get) {
        /* an input method's finished text, read as UTF-16 (the ANSI WM_IME_CHAR would lose it) */
        WCHAR text[256];
        HIMC context = win.imm_get(window);
        if (context != NULL) {
            LONG bytes = win.imm_string(context, GCS_RESULTSTR, text, (DWORD)sizeof text);
            int i;
            for (i = 0; bytes > 0 && i < (int)(bytes / 2); ++i) unit_in(text[i]);
            win.imm_release(window, context);
            lparam &= ~(LPARAM)(GCS_RESULTSTR | GCS_RESULTCLAUSE | GCS_RESULTREADSTR | GCS_RESULTREADCLAUSE);
        }
    } else if (message == WM_IME_CHAR) {
        unit_in((WCHAR)wparam);
        return 0;
    }
#endif
    return win.call_proc(win.old, window, message, wparam, lparam);
}

static BOOL CALLBACK find_window(HWND window, LPARAM found) {
    if (win.visible(window)) {
        *(HWND *)found = window;
        return FALSE;
    }
    return TRUE;
}

/* Called from the text draw: the first time the game has a visible window, subclass it. */
static void window_check(void) {
    HMODULE user;
    HWND found = NULL;
    if (win.done || (win.draws++ & 63) != 0) return;
    if (!win.tried) {
        win.tried = 1;
        user = LoadLibraryW(L"user32.dll");
        if (user == NULL) { win.done = 1; return; }
        win.set_long = (set_long_fn)(UINT_PTR)GetProcAddress(user, "SetWindowLongW");
        win.call_proc = (call_proc_fn)(UINT_PTR)GetProcAddress(user, "CallWindowProcW");
        win.translate = (translate_fn)(UINT_PTR)GetProcAddress(user, "TranslateMessage");
        win.enum_windows = (enum_fn)(UINT_PTR)GetProcAddress(user, "EnumThreadWindows");
        win.visible = (visible_fn)(UINT_PTR)GetProcAddress(user, "IsWindowVisible");
        win.peek = (peek_fn)(UINT_PTR)GetProcAddress(user, "PeekMessageW");
        if (!win.set_long || !win.call_proc || !win.translate || !win.enum_windows || !win.visible || !win.peek) {
            win.done = 1;
            return;
        }
        if (GAME_SUBCLASS_WINDOW) {
            HMODULE imm = LoadLibraryW(L"imm32.dll");
            if (imm != NULL) {
                win.imm_get = (imm_get_fn)(UINT_PTR)GetProcAddress(imm, "ImmGetContext");
                win.imm_string = (imm_string_fn)(UINT_PTR)GetProcAddress(imm, "ImmGetCompositionStringW");
                win.imm_release = (imm_release_fn)(UINT_PTR)GetProcAddress(imm, "ImmReleaseContext");
                if (!win.imm_string || !win.imm_release) win.imm_get = NULL;
            }
        }
    }
    win.enum_windows(GetCurrentThreadId(), find_window, (LPARAM)&found);
    if (found == NULL) return;
    win.window = found;
    win.old = (WNDPROC)win.set_long(found, GWL_WNDPROC, (LONG_PTR)text_window);
    win.done = 1;
}

#endif
