/* text_clipboard.h -- "Unicode Text.dll", both games: "Copy and Paste in Text Boxes".

   While one of the game's text boxes has typing focus (a player-list row, the new player's
   box, Fish Tycoon's registration boxes, Plant Tycoon's price box ...):

     Ctrl+V, Shift+Insert   paste the Windows clipboard's text (CF_UNICODETEXT) at the caret
                            (the boxes' caret is always at the end of their text)
     Ctrl+C, Ctrl+Insert    copy the box's whole text (a player's full name, never its
                            31-letter short form)
     Ctrl+X                 copy, then empty the box

   The keys are taken in the game window's procedure (unicode_typing.h subclasses it in both
   games once a box is drawn) and never reach the game, so they type nothing; without a focused
   box they go on to the game as before. The focused box is the one the game last drew with its
   focus (+0x25) and its window's focus (+0x1C -> +8) set (clip_seen, from the box's draw).

   A paste behaves as if its letters were typed one by one: each is posted as the game's own
   "character" event (5, 0, letter), so the box's own code takes it (box_char with Unicode, the
   game's own path without). Before that the text is cleaned and cut to the box's room:
     - CR, LF (CR LF as one) and Tab become spaces; other control characters (C0, DEL, C1)
       and lone surrogates are dropped;
     - with Unicode (utf8_drawing) every letter goes, as UTF-8; without it only what the stock
       box ever got from the keyboard: printable ASCII (0x20-0x7E) in both games (Fish's event
       loop posts only 0x20-0x7E, Plant's only one-byte SDL text), the rest dropped;
     - a number box (+0x2D, Plant's price box) takes digits only (and '-' first), as typed;
     - cut at whole letters: a letter with its combining marks, variation selectors, skin
       tones and zero-width-joined letters goes in whole or not at all, to the box's byte limit
       (+0x28; a name box 1,200 bytes) and, in a name box, its 300 letters.
   At most 2,408 UTF-16 units are read from the clipboard, however much it holds. OpenClipboard is given the game's
   window and always closed; a busy clipboard does nothing. */
#ifndef FTFP_TEXT_CLIPBOARD_H
#define FTFP_TEXT_CLIPBOARD_H

static int clip_enabled;                     /* Paste=1 in Unicode Text.ini */
static struct {
    char *box;
    DWORD tick;
} clip_focus;

#define CLIP_FRESH_MS 400
#define CLIP_UNITS (2 * NAME_BOX_BYTES + 8)

/* The box's draw: remember a box drawn with typing focus. */
__declspec(noinline) static void clip_seen(char *box) {
    const char *window;
    if (box == NULL || !box[0x25]) return;
    window = *(const char *const *)(box + 0x1C);
    if (window == NULL || !window[8]) return;
    clip_focus.box = box;
    clip_focus.tick = GetTickCount();
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

/* A letter that joins the one before it (a combining mark, a variation selector, a skin tone,
   the zero-width joiner, an emoji tag), so the two go in together or not at all. */
static int clip_joins(unsigned int cp) {
    return (cp >= 0x0300 && cp <= 0x036F) || (cp >= 0x0483 && cp <= 0x0489) || (cp >= 0x0591 && cp <= 0x05BD)
           || (cp >= 0x0610 && cp <= 0x061A) || (cp >= 0x064B && cp <= 0x065F) || (cp >= 0x0900 && cp <= 0x0903)
           || (cp >= 0x093A && cp <= 0x094F) || (cp >= 0x0E31 && cp <= 0x0E3A && cp != 0x0E32 && cp != 0x0E33)
           || (cp >= 0x1AB0 && cp <= 0x1AFF) || (cp >= 0x1DC0 && cp <= 0x1DFF) || (cp >= 0x200C && cp <= 0x200D)
           || (cp >= 0x20D0 && cp <= 0x20FF) || (cp >= 0x3099 && cp <= 0x309A) || (cp >= 0xFE00 && cp <= 0xFE0F)
           || (cp >= 0xFE20 && cp <= 0xFE2F) || (cp >= 0x1F3FB && cp <= 0x1F3FF) || (cp >= 0xE0020 && cp <= 0xE007F)
           || (cp >= 0xE0100 && cp <= 0xE01EF);
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

/* Paste into `box`: the number of letters posted. */
static int clip_paste(char *box) {
    static WCHAR units[CLIP_UNITS];
    static unsigned int cps[CLIP_UNITS];
    const char *text = *(const char **)(box + 0x30);
    int limit = *(int *)(box + 0x28), len, room, letters_room, n, count = 0, i, posted = 0;
    int number = box[0x2D] != 0, name = utf8_drawing && limit == NAME_BOX_BYTES;
    if (text == NULL) return 0;
    len = s_len(text);
    room = limit - len;
    letters_room = name ? NAME_LETTERS - letters_in(text) : room;
    if (room <= 0 || letters_room <= 0) return 0;
    /* a bounded read (twice the longest box, as UTF-16 units, so left-out letters leave enough) */
    n = clip_read(units, CLIP_UNITS);
    if (n <= 0) return 0;
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
        if (cp < 0x20 || (cp >= 0x7F && cp < 0xA0)) continue;
        if (!utf8_drawing && cp > 0x7E) continue;    /* the stock box: printable ASCII */
        if (number && !((cp >= '0' && cp <= '9') || (cp == '-' && len + count == 0))) continue;
        cps[count++] = cp;
    }
    /* whole letters (a base and what joins it) while they fit */
    for (i = 0; i < count;) {
        int end = i + 1, bytes = 0, k;
        char tmp[4];
        while (end < count && (clip_joins(cps[end]) || cps[end - 1] == 0x200D)) ++end;
        for (k = i; k < end; ++k) bytes += utf8_drawing ? utf8_put(cps[k], tmp, 4) : 1;
        if (bytes > room || end - i > letters_room) break;
        room -= bytes;
        letters_room -= end - i;
        for (k = i; k < end; ++k) post_letter(cps[k]);
        posted += end - i;
        i = end;
    }
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
        unsigned int cp = utf8_drawing ? utf8_next(&p) : *p++;      /* the stock box: Latin-1 bytes */
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

/* A key-down in the game's window: 1 when it was a clipboard key for a focused box (done here). */
static int clip_key(unsigned int vk) {
    int action;
    char *box;
    if (!clip_enabled) return 0;
    action = clip_action(vk, GetKeyState(VK_CONTROL) < 0, GetKeyState(VK_SHIFT) < 0, GetKeyState(VK_MENU) < 0);
    if (action == CLIP_NONE || (box = clip_box()) == NULL) return 0;
    if (action == CLIP_PASTE) clip_paste(box);
    else clip_copy(box, action == CLIP_CUT);
    return 1;
}

#endif
