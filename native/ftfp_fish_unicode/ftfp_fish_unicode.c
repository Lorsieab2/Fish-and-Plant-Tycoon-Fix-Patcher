/* Unicode Text (Fish Tycoon) -- "Render Unicode with In-Game Fonts", any letter of any script.

   This file: the key path and the fonts as stage 1 made them (Latin-1, below), now posting any
   letter. Names, the text draw, run-time glyphs and the text box: ../common/unicode_names.h,
   unicode_text.h, unicode_glyphs.h, unicode_typing.h.

   TYPING.  Fish Tycoon is an SDL 1.2 game with SDL's Unicode translation on. Its event
   loop (0x403DE0) takes a key's character from keysym.unicode only when it is below 0x80
   (test eax, 0xff80 at 0x403EB7), then posts a "character" event (type 5: code, char) only
   for 0x20-0x7E (lea ebx, [edx-0x20]; cmp ebx, 0x5e; ja 0x403f4f at 0x403ED4), and not
   while Ctrl or Alt is held. The text box (vtable 0x4406C0, its key handler 0x40BFC0)
   stores a character 0x20-0xFF as one byte (cmp edx, 0x1f / cmp edx, 0xff at 0x40C05F),
   so it takes Latin-1 as it is; it only never got any.

   This sends every key whose keysym.unicode is U+00A0-U+00FF straight to the text box as
   that Latin-1 byte, whatever the modifiers (AltGr is Ctrl+Alt): the 8 bytes at 0x403ED4
   become a jump to stub_input, which posts (5, code, char) exactly as the game's own path
   does (0x4021E0 the events, 0x402010 post) with the character zero-extended (the game's
   own path sign-extends, which the text box would refuse), then goes on with the next
   event (0x403EF7). Any other key runs the game's own three instructions and goes where
   they go (0x403EDC or 0x403F4F), so nothing else changes.

   DRAWING.  The font manager (0x4180B0) makes the game's three fonts with the font
   set-up 0x402350(name, table, 0): paddington_tt_18 (0x42A45F table 0x458580, 0x42A464
   name), paddington_tt_30 (0x42A4CF, 0x42A4D4) and FONT_TRIPLEX_SANSLIGHTLIN_BOLD_16PT
   (0x410A9F, 0x410AA4). Their pictures lack most of Latin-1 (and paddington draws an empty
   box for % * + < = > [ \ ] ^ { | } ~). The patcher ships each picture again as
   Images\<name>_unicode.png: the game's own picture with rows of patcher-made letters
   added below (scripts/build_unicode_assets.py), and unicode_fonts.h holds each font's
   table: the game's own records, then the added ones. The two push immediates of each
   font point at this DLL's name and table, so the game's own loader and draw do the rest.
   Only when all three pictures are in the game's Images folder.

   All four sites hold their stock bytes, or nothing is written
   (../ftfp_ds_fish/install_sites.h). Nothing is saved: a name is the game's own bytes.
   The result is in "Fish Tycoon Fix Patcher DLLs\Unicode Text.log"; once installed, the save
   folder gets "Fish Tycoon Fix Patcher Data\Unicode Text.ini" so the patcher's tools know
   this copy takes such names (../common/unicode_marker.h). */

#include <windows.h>
#include <string.h>
#include <wchar.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "../common/unicode_marker.h"
#include "unicode_fonts.h"
#include "unicode_sites.h"

/* ---- names and text: ../common/unicode_names.h, ../common/unicode_text.h */
#define GAME_STATE_GLOBAL 0x0045ABDCu      /* the game state (0x41B070 makes it) */
#define GAME_SLOT_NAMES 0x1E3D8            /* the player list: 5 rows of 42 bytes */
#define GAME_SLOT_STRIDE 0x2A
/* setLimit(1, 0x20) of the player list's five rows and the new player's box (each call + 5) */
#define GAME_NAME_LIMIT_RETURNS 0x00417129u, 0x004171AEu, 0x00417233u, 0x004172B8u, 0x0041733Du, \
    0x004175D7u, 0x00417C63u
/* getText(name, 0x20) into a player's name: the rows, the new player's name (each call + 5) */
#define GAME_NAME_TEXT_RETURNS 0x004176F2u, 0x00417838u, 0x00417883u, 0x004178CEu, 0x0041791Cu, \
    0x00417969u, 0x00417D77u
#define GAME_NEW_NAME_RETURN 0x00417D77u  /* getText of the new player's box (the game copies it to row 1) */
#define GAME_DEFAULT_FONT 0x34             /* the graphics' default font */
#define GAME_SET_TEXT_RESUME 0x0040B976u
#define GAME_SET_LIMIT_TARGET 0x0040B8B0u
#define GAME_DRAW_FRAME 0x34
#define GAME_DRAW_RESUME 0x004087E7u
#define GAME_DEFAULT_COLOUR 0x0045427Cu  /* the colour of text drawn with colour 0 */
#define GAME_CLIP 0x38                     /* the graphics' clip rectangle: left, top, right, bottom */
#define GAME_SDL2 0
#define GAME_SDL_CREATE 0x0042A5DCu        /* SDL_CreateRGBSurface, SDL_FreeSurface, SDL_UpperBlit */
#define GAME_SDL_FREE 0x0042A5E2u
#define GAME_SDL_BLIT 0x0042A600u
#define GAME_EVENTS_GET 0x004021E0u
#define GAME_EVENTS_POST 0x00402010u       /* post(type, code, letter) */
#define GAME_EVENTS_POST2 0x00402030u      /* post(type, param) */
#define GAME_BOX_DONE 0x0040BA30u
#define GAME_BOX_CHAR_RESUME 0x0040BFFFu
#define GAME_SUBCLASS_WINDOW 1
#define GAME_BOX_DRAW_TARGET 0x00408B80u  /* the box's left draw (thiscall wrapper) */
#define GAME_WIDTH_RESUME 0x004023D7u

#define CODE_ADDR(fn) ((const void *)(UINT_PTR)(fn))

#include "../common/unicode_utf8.h"
#include "../common/unicode_names.h"
#include "../common/unicode_text.h"
#include "../common/unicode_hooks.h"
#include "../common/unicode_draw.h"
#include "../common/unicode_typing.h"
#include "../common/unicode_config.h"


#define INPUT_PRINTABLE 0x00403EDC      /* the game's own path for 0x20-0x7E */
#define INPUT_OTHER 0x00403F4F          /* the game's own path for every other key */
#define INPUT_NEXT 0x00403EF7           /* the next event */
#define EVENTS_GET 0x004021E0
#define EVENTS_POST 0x00402010

typedef struct font_site {
    unsigned int va;                     /* push table; push name: 10 bytes */
    unsigned char expect[SITE_FONT_LEN];
    const int *table;
    const char *name;
} font_site;

static const font_site FONT_SITES[3] = {
    {SITE_FONT_PADDINGTON_18_VA, SITE_FONT_PADDINGTON_18_EXPECT, table_paddington_18, name_paddington_18},
    {SITE_FONT_PADDINGTON_30_VA, SITE_FONT_PADDINGTON_30_EXPECT, table_paddington_30, name_paddington_30},
    {SITE_FONT_TRIPLEX_16_VA, SITE_FONT_TRIPLEX_16_EXPECT, table_triplex_16, name_triplex_16},
};

static HMODULE self_module;
static int installed;
static int pictures_missing;

/* keysym.sym is the dword at [esp+0x18], keysym.unicode the word at [esp+0x20]; edx is the key's code. */
__declspec(naked) static void stub_input(void) {
    __asm {
        cmp dword ptr [esp + 0x18], 0x100   /* a special key (arrows, F keys...): the game's way */
        jae stock
        movzx eax, word ptr [esp + 0x20]
        cmp eax, 0xA0
        jb stock
        cmp eax, 0xD800                  /* a surrogate: SDL 1.2 gives only half a letter */
        jb post
        cmp eax, 0xDFFF
        jbe stock
        cmp eax, 0xFFFE
        jae stock
    post:
        push eax                         /* the letter, U+00A0 and up */
        push eax                         /* its code */
        push 5                           /* a character */
        mov eax, EVENTS_GET
        call eax
        mov ecx, eax
        mov eax, EVENTS_POST
        call eax
        mov eax, INPUT_NEXT
        jmp eax
    stock:
        lea ebx, [edx - 0x20]
        cmp ebx, 0x5E
        ja other
        mov eax, INPUT_PRINTABLE
        jmp eax
    other:
        mov eax, INPUT_OTHER
        jmp eax
    }
}

static int game_folder(wchar_t *out, DWORD cap) {
    wchar_t *slash;
    DWORD n = GetModuleFileNameW(NULL, out, cap);
    if (n == 0 || n >= cap || (slash = wcsrchr(out, L'\\')) == NULL) return 0;
    slash[1] = L'\0';
    return 1;
}

/* "<game>\Images\<name>.png" is there. */
static int picture_present(const char *name) {
    wchar_t path[1024];
    size_t at;
    if (!game_folder(path, 1024)) return 0;
    if (wcslen(path) + 8 + strlen(name) + 5 >= 1024) return 0;
    wcscat_s(path, 1024, L"Images\\");
    at = wcslen(path);
    while (*name) path[at++] = (wchar_t)(unsigned char)*name++;
    path[at] = L'\0';
    wcscat_s(path, 1024, L".png");
    return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}

#define TOTAL_SITES (4 + NAME_SITES)
static ftfp_site_write writes[TOTAL_SITES];

static int install_all(void) {
    ftfp_site_write *w = writes;
    int i;
    if (!unicode_on) {
        /* Copy and Paste in Text Boxes alone: the box draw, to know the box with typing focus */
        ftfp_site_branch(writes, SITE_BOX_DRAW_VA, SITE_BOX_DRAW_LEN, SITE_BOX_DRAW_EXPECT, 0xE8,
                         CODE_ADDR(stub_box_draw));
        return ftfp_install_sites(writes, 1);
    }
    for (i = 0; i < 3 && !system_font; ++i) {
        if (!picture_present(FONT_SITES[i].name)) {
            pictures_missing = 1;
            return 0;
        }
    }
    ftfp_site_branch(w++, SITE_INPUT_VA, SITE_INPUT_LEN, SITE_INPUT_EXPECT, 0xE9, CODE_ADDR(stub_input));
    for (i = 0; i < 3 && !system_font; ++i) {      /* Use Unicode Font: the game's fonts stay as they are */
        unsigned int table = (unsigned int)(UINT_PTR)FONT_SITES[i].table;
        unsigned int name = (unsigned int)(UINT_PTR)FONT_SITES[i].name;
        w->va = FONT_SITES[i].va;
        w->length = 10;
        w->expect = FONT_SITES[i].expect;
        memcpy(w->bytes, FONT_SITES[i].expect, 10);
        memcpy(w->bytes + 1, &table, 4);
        memcpy(w->bytes + 6, &name, 4);
        ++w;
    }
    w = name_site_writes(w);
    return ftfp_install_sites(writes, (int)(w - writes));
}

static int own_folder(wchar_t *out, DWORD cap) {
    wchar_t *slash;
    DWORD n = GetModuleFileNameW(self_module, out, cap);
    if (n == 0 || n >= cap || (slash = wcsrchr(out, L'\\')) == NULL) return 0;
    slash[1] = L'\0';
    return 1;
}

static void write_install_log(void) {
    wchar_t path[1024];
    char line[160];
    const char *text;
    DWORD written;
    HANDLE file;
    int len = 0;
    if (!own_folder(path, 1024) || wcslen(path) + 20 >= 1024) return;
    wcscat_s(path, 1024, L"Unicode Text.log");
    if (installed && !unicode_on) {
        text = "Unicode Text: installed for Copy and Paste in Text Boxes only (the game's own letters)\r\n";
    } else if (installed) {
        text = system_font ? "Unicode Text: installed as Use Unicode Font (typing and drawing any letter in "
                             "the chosen font, long names)\r\n"
                           : "Unicode Text: installed (typing and drawing any letter, the three fonts, long names)\r\n";
    } else if (pictures_missing) {
        text = "Unicode Text: not installed (a font picture is missing from Images)\r\n";
    } else {
        text = "Unicode Text: not installed (the game's code is not the stock code)\r\n";
    }
    while (text[len] && len < 159) {
        line[len] = text[len];
        ++len;
    }
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* Called once at start by the executable's startup loader, before WinMain. */
int __stdcall FtfpStartup(void) {
    static int started;
    if (started) return installed;
    started = 1;
    {
        wchar_t folder[1024];
        if (own_folder(folder, 1024)) read_unicode_config(folder);
    }
    __try {
        installed = install_all();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    if (installed && unicode_on) {
        utf8_drawing = 1;
        unicode_write_marker(L"Fish Tycoon Fix Patcher Data");
        names_start(L"Fish Tycoon Fix Patcher Data");
    }
    return installed;
}

/* The Translations setting's question (its contract, feat/translations): "Translations.dll"
   writes its text in Windows-1252 unless a DLL loaded before it exports this and it returns
   nonzero, when it writes UTF-8. Nonzero only once this DLL is installed AND draws UTF-8 text
   (utf8_drawing, set once installed): it does, so it answers 1 and translated text comes as
   UTF-8, drawn letter by letter (../common/unicode_glyphs.h). The loader always loads this DLL
   before any other loader tail (src/ds_fish_loader.py, with_tails). */
int __stdcall FtfpUnicodeTextActive(void) {
    return installed && utf8_drawing;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        self_module = instance;
        DisableThreadLibraryCalls(instance);
    } else if (reason == DLL_PROCESS_DETACH && installed) {
        /* the game quits: a name typed since the last draw still goes beside the save */
        names_sync();
    }
    return TRUE;
}
