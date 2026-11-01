/* unicode_hooks.h -- "Unicode Text.dll", both games: the jumps into the DLL for names and
   text (unicode_names.h, unicode_text.h) and the game's own code they go on to.

   Each game's file defines its addresses (GAME_*) and its sites' stock bytes (SITE_*, in its
   unicode_sites.h) before including this. The two engines are the same code at different
   addresses, so each stub is the same for both. */
#ifndef FTFP_UNICODE_HOOKS_H
#define FTFP_UNICODE_HOOKS_H

/* ---- the game's own draw and measure, from their 8th byte */

__declspec(naked) static void orig_draw(void) {
    __asm {
        sub esp, GAME_DRAW_FRAME
        mov eax, [esp + GAME_DRAW_FRAME + 0x14]
        mov edx, GAME_DRAW_RESUME
        jmp edx
    }
}

__declspec(naked) static void orig_width(void) {
    __asm {
        sub esp, 0x10
        push ebp
        mov ebp, [ecx + 4]
        mov edx, GAME_WIDTH_RESUME
        jmp edx
    }
}

static void game_draw(void *graphics, const char *text, int x, int y, unsigned int colour, void *font) {
    ((draw_fn)(UINT_PTR)CODE_ADDR(orig_draw))(graphics, NULL, text, x, y, colour, font);
}

static int game_width(void *font, const char *text, float scale) {
    return ((width_fn)(UINT_PTR)CODE_ADDR(orig_width))(font, NULL, text, scale);
}

/* ---- the stubs: the game's thiscall in, the DLL's cdecl C */

/* setText(text): the text the box keeps (set_text), then the game's own setText. */
__declspec(naked) static void stub_set_text(void) {
    __asm {
        push ecx
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        push ecx
        call set_text
        add esp, 0xC
        pop ecx
        mov [esp + 4], eax
        push esi
        mov esi, ecx
        mov eax, [esi + 0x30]
        mov edx, GAME_SET_TEXT_RESUME
        jmp edx
    }
}

/* getText(dst, size), all of it in get_text. */
__declspec(naked) static void stub_get_text(void) {
    __asm {
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        push ecx
        call get_text
        add esp, 0x10
        ret 8
    }
}

/* setLimit(fixed, limit): a name box's limit (name_limit), then the game's own setLimit. */
__declspec(naked) static void stub_set_limit(void) {
    __asm {
        push ecx
        push dword ptr [esp + 0xC]
        push dword ptr [esp + 8]
        call name_limit
        add esp, 8
        pop ecx
        mov [esp + 8], eax
        mov ecx, [ecx + 0x10]
        mov eax, GAME_SET_LIMIT_TARGET
        jmp eax
    }
}

/* The box's measure of its text, called instead of the game's measure; esi is the box. */
__declspec(naked) static void stub_box_width(void) {
    __asm {
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        push esi
        push ecx
        call box_width
        add esp, 0x14
        ret 8
    }
}

/* The box's draw of its text, called instead of the game's left draw; esi is the box. */
__declspec(naked) static void stub_box_draw(void) {
    __asm {
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x14]
        push esi
        push ecx
        call box_draw
        add esp, 0x20
        ret 0x14
    }
}

/* The game's text draw. */
__declspec(naked) static void stub_draw(void) {
    __asm {
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x14]
        push ecx
        call draw_hook
        add esp, 0x1C
        ret 0x14
    }
}

/* The game's text measure. */
__declspec(naked) static void stub_width(void) {
    __asm {
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        push ecx
        call width_hook
        add esp, 0x10
        ret 8
    }
}

#define NAME_SITES 9

static void stub_box_char(void);

/* The nine writes for names, text and typing, after `w`. */
static ftfp_site_write *name_site_writes(ftfp_site_write *w) {
    ftfp_site_branch(w++, SITE_SET_TEXT_VA, SITE_SET_TEXT_LEN, SITE_SET_TEXT_EXPECT, 0xE9, CODE_ADDR(stub_set_text));
    ftfp_site_branch(w++, SITE_GET_TEXT_VA, SITE_GET_TEXT_LEN, SITE_GET_TEXT_EXPECT, 0xE9, CODE_ADDR(stub_get_text));
    ftfp_site_branch(w++, SITE_SET_LIMIT_VA, SITE_SET_LIMIT_LEN, SITE_SET_LIMIT_EXPECT, 0xE9, CODE_ADDR(stub_set_limit));
    ftfp_site_branch(w++, SITE_BOX_WIDTH_VA, SITE_BOX_WIDTH_LEN, SITE_BOX_WIDTH_EXPECT, 0xE8, CODE_ADDR(stub_box_width));
    w->va = SITE_BOX_CUT_VA;
    w->length = SITE_BOX_CUT_LEN;
    w->expect = SITE_BOX_CUT_EXPECT;
    w->bytes[0] = 0xEB;
    w->bytes[1] = SITE_BOX_CUT_EXPECT[1];
    ++w;
    ftfp_site_branch(w++, SITE_BOX_DRAW_VA, SITE_BOX_DRAW_LEN, SITE_BOX_DRAW_EXPECT, 0xE8, CODE_ADDR(stub_box_draw));
    ftfp_site_branch(w++, SITE_DRAW_VA, SITE_DRAW_LEN, SITE_DRAW_EXPECT, 0xE9, CODE_ADDR(stub_draw));
    ftfp_site_branch(w++, SITE_WIDTH_VA, SITE_WIDTH_LEN, SITE_WIDTH_EXPECT, 0xE9, CODE_ADDR(stub_width));
    ftfp_site_branch(w++, SITE_BOX_CHAR_VA, SITE_BOX_CHAR_LEN, SITE_BOX_CHAR_EXPECT, 0xE9, CODE_ADDR(stub_box_char));
    return w;
}

#endif
