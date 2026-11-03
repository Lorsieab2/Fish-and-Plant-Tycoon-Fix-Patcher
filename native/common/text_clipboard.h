/* text_clipboard.h -- "Unicode Text.dll", both games: "Copy and Paste in Text Boxes".

   While one of the game's text boxes has typing focus (a player-list row, the new player's
   box, Fish Tycoon's registration boxes, Plant Tycoon's price box ...):

     Ctrl+V, Shift+Insert   paste the Windows clipboard's text (CF_UNICODETEXT) at the caret
                            (the boxes' caret is always at the end of their text)
     Ctrl+C, Ctrl+Insert    copy the box's whole text (a player's whole name, never its
                            short form)
     Ctrl+X                 copy, then empty the box (only once the copy succeeded)

   A held key's repeats are swallowed (bit 30 of the key-down's lParam: the key was already
   down), so a held Ctrl+V pastes once.

   The keys are taken in the game window's procedure (unicode_typing.h subclasses it in both
   games once a box is drawn) and never reach the game, so they type nothing; without a focused
   box they go on to the game as before. The focused box is the one the game last drew with its
   focus (+0x25) and its window's focus (+0x1C -> +8) set (clip_seen: from the box's caret blink,
   which the game's draw of a focused box always reaches, empty or not, and from its text draw).

   A paste behaves as if its letters were typed one by one: each is posted as the game's own
   "character" event (5, 0, letter), so the box's own code takes it (box_char with Unicode, the
   game's own path without). Before that the text is cleaned and cut to the box's room:
     - it is put in NFC first (FoldStringW, MAP_PRECOMPOSED: a letter and its combining accent
       become the one precomposed letter where Unicode has one), as VV and VF1 do;
     - CR, LF (CR LF as one) and Tab become spaces; other control characters (C0, DEL, C1)
       and lone surrogates are dropped;
     - with Unicode (utf8_drawing) every letter goes, kept by the write rule (a Windows-1252
       letter one byte, any other UTF-8); without it only what the stock fonts draw and the
       stock box ever got from the keyboard: printable ASCII (0x20-0x7E) in both games (Fish's
       event loop posts only 0x20-0x7E, Plant's only one-byte SDL text), the rest dropped;
     - a number box (+0x2D, Plant's price box) takes digits only (and '-' first), as typed;
     - cut at whole characters (grapheme clusters, unicode_grapheme.h), counted over the box's
       text and the paste together: a letter with its combining marks, variation selectors,
       skin tones and zero-width-joined letters goes in whole or not at all, to the box's byte
       limit (+0x28; a name box NAME_BOX_BYTES, as the save stores them), and a mark that would
       join the box's last character and no longer fits is not pasted.
   At most CLIP_UNITS (8,192) UTF-16 units are read from the clipboard, bounded by GlobalSize and
   the first NUL, however much it holds. OpenClipboard is given the game's window, is never
   waited on and is always closed; a busy or empty clipboard does nothing. */
#ifndef FTFP_TEXT_CLIPBOARD_H
#define FTFP_TEXT_CLIPBOARD_H

static int clip_enabled;                     /* Paste=1 in Unicode Text.ini */
static struct {
    char *box;
    DWORD tick;
} clip_focus;

#define CLIP_FRESH_MS 400
#define CLIP_UNITS 8192                      /* the most UTF-16 units read (docs/UNICODE_SPEC.md section 5) */

/* The box's draw: remember a box drawn with typing focus. */
__declspec(noinline) static void clip_seen(char *box) {
    const char *window;
    if (box == NULL || !box[0x25]) return;
    window = *(const char *const *)(box + 0x1C);
    if (window == NULL || !window[8]) return;
    clip_focus.box = box;
    clip_focus.tick = GetTickCount();
}

/* The focused box's caret blink reads the time (the game's call there, from the box's draw with
   esi = the box, empty or not): note the box, then the game's own call. */
__declspec(naked) static void stub_caret_tick(void) {
    __asm {
        push ecx
        push esi
        call clip_seen
        add esp, 4
        pop ecx
        mov eax, GAME_CARET_TICK_TARGET
        jmp eax
    }
}

/* The box with typing focus now, or NULL. */
static char *clip_box(void) {
    char *box = clip_focus.box;
    const char *window;
    if (box == NULL || GetTickCount() - clip_focus.tick > CLIP_FRESH_MS) return NULL;
    window = *(const char *const *)(box + 0x1C);
    if (!box[0x25] || window == NULL || !window[8] || *(char **)(box + 0x30) == NULL) return NULL;
    return box;
}

#define CLIP_NONE 0
#define CLIP_PASTE 1
#define CLIP_COPY 2
#define CLIP_CUT 3

/* What a key-down does: `ctrl`, `shift`, `alt` are the modifiers held (AltGr is Ctrl+Alt: none). */
__declspec(noinline) static int clip_action(unsigned int vk, int ctrl, int shift, int alt) {
    if (alt) return CLIP_NONE;
    if (ctrl && !shift && vk == 'V') return CLIP_PASTE;
    if (ctrl && !shift && vk == 'C') return CLIP_COPY;
    if (ctrl && !shift && vk == 'X') return CLIP_CUT;
    if (vk == VK_INSERT && shift && !ctrl) return CLIP_PASTE;
    if (vk == VK_INSERT && ctrl && !shift) return CLIP_COPY;
    return CLIP_NONE;
}

/* The clipboard's text, at most `cap` UTF-16 units (NUL-ended): the number read, -1 when the
   clipboard is busy or has no text. */
static int clip_read(WCHAR *out, int cap) {
    HANDLE data;
    const WCHAR *units;
    SIZE_T size;
    int n = 0;
    if (!OpenClipboard(win.window)) return -1;
    data = GetClipboardData(CF_UNICODETEXT);
    if (data != NULL && (units = (const WCHAR *)GlobalLock(data)) != NULL) {
        size = GlobalSize(data) / sizeof(WCHAR);
        while (n < cap - 1 && (SIZE_T)n < size && units[n]) {
            out[n] = units[n];
            ++n;
        }
        GlobalUnlock(data);
    } else {
        n = -1;
    }
    CloseClipboard();
    if (n >= 0) out[n] = 0;
    return n;
}

/* Put `units` (n UTF-16 units) on the clipboard: 1 when done. */
static int clip_write(const WCHAR *units, int n) {
    HGLOBAL data;
    WCHAR *at;
    int ok = 0;
    data = GlobalAlloc(GMEM_MOVEABLE, (SIZE_T)(n + 1) * sizeof(WCHAR));
    if (data == NULL) return 0;
    at = (WCHAR *)GlobalLock(data);
    if (at == NULL) {
        GlobalFree(data);
        return 0;
    }
    memcpy(at, units, (size_t)n * sizeof(WCHAR));
    at[n] = 0;
    GlobalUnlock(data);
    if (OpenClipboard(win.window)) {
        if (EmptyClipboard() && SetClipboardData(CF_UNICODETEXT, data) != NULL) ok = 1;
        CloseClipboard();
    }
    if (!ok) GlobalFree(data);
    return ok;
}

/* The clipboard's text in NFC (FoldStringW, MAP_PRECOMPOSED), in place; unchanged if Windows
   cannot. */
static int clip_nfc(WCHAR *units, int n) {
    static WCHAR folded[CLIP_UNITS];
    int got = FoldStringW(MAP_PRECOMPOSED, units, n, folded, CLIP_UNITS - 1);
    if (got <= 0 || got > n) return n;               /* composing never makes the text longer */
    memcpy(units, folded, (size_t)got * sizeof(WCHAR));
    units[got] = 0;
    return got;
}

/* Paste into `box`: the number of letters posted. */
static int clip_paste(char *box) {
    static WCHAR units[CLIP_UNITS];
    static unsigned int cps[BOX_LETTERS + CLIP_UNITS + 1];
    static char bytes[4 * (BOX_LETTERS + CLIP_UNITS) + 8];
    static int stops[BOX_LETTERS + CLIP_UNITS + 1];
    const char *text = *(const char **)(box + 0x30);
    int limit = *(int *)(box + 0x28), len, have, n, count, i, posted = 0, best, mixed, k, ends;
    int number = box[0x2D] != 0;
    gb_state gs;
    if (text == NULL) return 0;
    len = s_len(text);
    if (limit - len <= 0) return 0;
    /* the box's own text as letters (without Unicode: one byte a letter), the paste after it */
    have = utf8_drawing ? game_decode(text, cps, BOX_LETTERS + 1) : len;
    if (have > BOX_LETTERS) return 0;
    if (!utf8_drawing) {
        for (i = 0; i < len; ++i) cps[i] = (unsigned char)text[i];
    }
    count = have;
    n = clip_read(units, CLIP_UNITS);           /* a bounded read */
    if (n <= 0) return 0;
    n = clip_nfc(units, n);
    for (i = 0; i < n; ++i) {
        unsigned int cp = units[i];
        if (cp >= 0xD800 && cp <= 0xDBFF && i + 1 < n && units[i + 1] >= 0xDC00 && units[i + 1] <= 0xDFFF) {
            cp = 0x10000u + ((cp - 0xD800u) << 10) + (units[i + 1] - 0xDC00u);
            ++i;
        } else if (cp >= 0xD800 && cp <= 0xDFFF) {
            continue;                            /* a lone surrogate */
        }
        if (cp == '\r' && i + 1 < n && units[i + 1] == '\n') ++i;
        if (cp == '\r' || cp == '\n' || cp == '\t') cp = ' ';
        if (!letter_typable(cp)) continue;
        if (!utf8_drawing && cp > 0x7E) continue;    /* the stock fonts and box: printable ASCII */
        if (number && !((cp >= '0' && cp <= '9') || (cp == '-' && count == 0))) continue;
        cps[count++] = cp;
    }
    /* the most letters of the paste that end on a grapheme boundary (counted over the box's text
       and the paste: a mark joining the box's last character belongs to it) and fit the box's
       byte limit as the box keeps them; the mixed bytes (never more than the write rule's) stop
       the walk once they are past the limit */
    ends = 0;
    mixed = 0;
    gb_start(&gs);
    for (i = 0; i <= count; ++i) {
        int brk = i == count || gb_push(&gs, cps[i]);
        if (i > have && brk) {
            if (mixed > limit) break;
            stops[ends++] = i;
        }
        if (i == count) break;
        if (utf8_drawing) {
            k = game_byte(cps[i]);
            mixed += k >= 0 ? 1 : utf8_put(cps[i], bytes, 4);
        } else {
            ++mixed;
        }
    }
    /* the longest that the write rule keeps within the limit (almost always the last one) */
    best = have;
    while (ends > 0) {
        i = stops[--ends];
        if (!utf8_drawing || game_encode(cps, i, bytes, limit + 1) >= 0) {
            best = i;
            break;
        }
    }
    for (i = have; i < best; ++i) post_letter(cps[i]);
    posted = best - have;
    return posted;
}

/* Copy (and with `cut`, empty) `box`: 1 when the clipboard has its text. */
static int clip_copy(char *box, int cut) {
    static WCHAR units[CLIP_UNITS];
    static char full[NAME_BOX_BYTES + 1];
    char *text = *(char **)(box + 0x30);
    const char *whole;
    const unsigned char *p;
    int n = 0;
    if (text == NULL) return 0;
    whole = full_for_short(text);                /* a short form: the full name instead */
    if (whole == NULL) whole = text;
    s_copy(full, whole, sizeof full);
    p = (const unsigned char *)full;
    while (*p && n < CLIP_UNITS - 2) {
        unsigned int cp = utf_next(&p);          /* the read rule (the stock box: Windows-1252 bytes) */
        if (cp >= 0x10000) {
            units[n++] = (WCHAR)(0xD800 + ((cp - 0x10000) >> 10));
            units[n++] = (WCHAR)(0xDC00 + ((cp - 0x10000) & 0x3FF));
        } else {
            units[n++] = (WCHAR)cp;
        }
    }
    if (!clip_write(units, n)) return 0;
    if (cut && text[0]) {
        text[0] = '\0';
        box_changed(box);
    }
    return 1;
}

/* A key-down in the game's window: 1 when it was a clipboard key for a focused box (done here).
   `lparam`'s bit 30 is set when the key was already down: a held key's repeat, swallowed. */
static int clip_key(unsigned int vk, LPARAM lparam) {
    int action;
    char *box;
    if (!clip_enabled) return 0;
    action = clip_action(vk, GetKeyState(VK_CONTROL) < 0, GetKeyState(VK_SHIFT) < 0, GetKeyState(VK_MENU) < 0);
    if (action == CLIP_NONE || (box = clip_box()) == NULL) return 0;
    if (lparam & 0x40000000) return 1;           /* a repeat: the first press did it */
    if (action == CLIP_PASTE) clip_paste(box);
    else clip_copy(box, action == CLIP_CUT);
    return 1;
}

#endif
