/* Unicode Text (Plant Tycoon) -- "Render Unicode with In-Game Fonts", stage 1: Latin-1.

   TYPING.  Plant Tycoon is an SDL 2 game. Its event loop takes typed text from
   SDL_TEXTINPUT (0x404385): the event's text is UTF-8, and the loop posts a "character"
   event (type 5: 0, char) only when that text is one byte long (cmp eax, 1 at 0x40439B),
   so only ASCII; anything else typed is dropped. The text box (its key handler 0x40CA90)
   stores a character 0x20-0xFF as one byte (cmp edx, 0x1f / cmp edx, 0xff at 0x40CB2F),
   so it takes Latin-1 as it is; it only never got any.

   The 9 bytes at 0x40439B (cmp eax, 1; jne 0x404467) become a jump to stub_input: one byte
   goes on the game's own way (0x4043A4); a two-byte UTF-8 sequence for U+00A0-U+00FF
   (C2 A0 - C3 BF) is posted as that Latin-1 byte, zero-extended, exactly as the game posts
   its own (0x402190 the events, 0x402000 post); anything else is dropped as before
   (0x404467, the next event).

   DRAWING.  The game's one font, PTfontsmall (made by 0x402300(name, table, 0): 0x412D9F
   push table 0x47A550, 0x412DA4 push name), already has U+00A2-U+00FF; it lacks only
   U+00A0 (no-break space) and U+00A1 (inverted exclamation mark). The patcher ships its
   picture again as Images\PTfontsmall_unicode.png, the game's own picture with those two
   letters added below, patcher-made in its style (scripts/build_unicode_assets.py), and
   unicode_fonts.h holds the table: the game's own records, then the two added ones. The
   two push immediates point at this DLL's name and table, so the game's own loader and
   draw do the rest. Only when the picture is in the game's Images folder.

   Both sites hold their stock bytes, or nothing is written (../ftfp_ds_fish/install_sites.h).
   Nothing is saved: a name is the game's own bytes. The result is in
   "Plant Tycoon Fix Patcher DLLs\Unicode Text.log"; once installed, the save folder gets
   "Plant Tycoon Fix Patcher Data\Unicode Text.ini" so the patcher's tools know this copy takes
   such names (../common/unicode_marker.h). */

#include <windows.h>
#include <string.h>
#include <wchar.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "../common/unicode_marker.h"
#include "unicode_fonts.h"
#include "unicode_sites.h"

/* ---- names and text: ../common/unicode_names.h, ../common/unicode_text.h */
#define GAME_STATE_GLOBAL 0x0049333Cu      /* the game state (0x41FCD0 makes it) */
#define GAME_SLOT_NAMES 0x53FC2            /* the player list: 5 rows of 33 bytes */
#define GAME_SLOT_STRIDE 0x21
/* setLimit(1, 0x20) of the player list's five rows and the new player's box (each call + 5) */
#define GAME_NAME_LIMIT_RETURNS 0x00415B71u, 0x00415C02u, 0x00415C96u, 0x00415D2Cu, 0x00415DDAu, \
    0x00415F03u, 0x0041AF03u
/* getText(name, 0x20) into a player's name: the rows, the new player's name (each call + 5) */
#define GAME_NAME_TEXT_RETURNS 0x0041603Bu, 0x0041619Du, 0x004161ECu, 0x00416234u, 0x0041627Cu, \
    0x004162C1u, 0x0041B01Du
#define GAME_DEFAULT_FONT 0x5C             /* the graphics' default font */
#define GAME_SET_TEXT_RESUME 0x0040C386u
#define GAME_SET_LIMIT_TARGET 0x0040C2C0u
#define GAME_DRAW_FRAME 0x44
#define GAME_DRAW_RESUME 0x00408E27u
#define GAME_WIDTH_RESUME 0x00402387u

#define CODE_ADDR(fn) ((const void *)(UINT_PTR)(fn))

#include "../common/unicode_utf8.h"
#include "../common/unicode_names.h"
#include "../common/unicode_text.h"
#include "../common/unicode_hooks.h"
#include "../common/unicode_draw.h"


#define INPUT_ONE_BYTE 0x004043A4        /* the game's own path for one byte (ASCII) */
#define INPUT_NEXT 0x00404467            /* the next event */
#define EVENTS_GET 0x00402190
#define EVENTS_POST 0x00402000


static HMODULE self_module;
static int installed;
static int pictures_missing;

/* eax = the UTF-8 text's length, the text at [esp+0x30], ebx = 0 (the game's). */
__declspec(naked) static void stub_input(void) {
    __asm {
        cmp eax, 1
        jne two
        mov eax, INPUT_ONE_BYTE
        jmp eax
    two:
        cmp eax, 2
        jne next
        movzx eax, byte ptr [esp + 0x30]
        movzx ecx, byte ptr [esp + 0x31]
        mov edx, ecx
        and edx, 0xC0
        cmp edx, 0x80
        jne next
        cmp eax, 0xC2
        je latin1
        cmp eax, 0xC3
        jne next
    latin1:
        and eax, 3
        shl eax, 6
        and ecx, 0x3F
        or eax, ecx
        cmp eax, 0xA0
        jb next
        push eax                         /* the character, 0xA0-0xFF */
        push ebx                         /* the code the game posts with text: 0 */
        push 5                           /* a character */
        mov eax, EVENTS_GET
        call eax
        mov ecx, eax
        mov eax, EVENTS_POST
        call eax
    next:
        mov eax, INPUT_NEXT
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

#define TOTAL_SITES (2 + NAME_SITES)
static ftfp_site_write writes[TOTAL_SITES];

static int install_all(void) {
    unsigned int table = (unsigned int)(UINT_PTR)table_ptfontsmall;
    unsigned int name = (unsigned int)(UINT_PTR)name_ptfontsmall;
    if (!picture_present(name_ptfontsmall)) {
        pictures_missing = 1;
        return 0;
    }
    ftfp_site_branch(&writes[0], SITE_INPUT_VA, SITE_INPUT_LEN, SITE_INPUT_EXPECT, 0xE9, CODE_ADDR(stub_input));
    writes[1].va = SITE_FONT_VA;
    writes[1].length = SITE_FONT_LEN;
    writes[1].expect = SITE_FONT_EXPECT;
    memcpy(writes[1].bytes, SITE_FONT_EXPECT, SITE_FONT_LEN);
    memcpy(writes[1].bytes + 1, &table, 4);
    memcpy(writes[1].bytes + 6, &name, 4);
    name_site_writes(&writes[2]);
    return ftfp_install_sites(writes, TOTAL_SITES);
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
    const char *text;
    DWORD written;
    HANDLE file;
    if (!own_folder(path, 1024) || wcslen(path) + 20 >= 1024) return;
    wcscat_s(path, 1024, L"Unicode Text.log");
    if (installed) {
        text = "Unicode Text: installed (typing Latin-1, the font, long names)\r\n";
    } else if (pictures_missing) {
        text = "Unicode Text: not installed (the font picture is missing from Images)\r\n";
    } else {
        text = "Unicode Text: not installed (the game's code is not the stock code)\r\n";
    }
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, text, (DWORD)strlen(text), &written, NULL);
    CloseHandle(file);
}

/* Called once at start by the executable's startup loader, before WinMain. */
int __stdcall FtfpStartup(void) {
    static int started;
    if (started) return installed;
    started = 1;
    __try {
        installed = install_all();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    if (installed) {
        unicode_write_marker(L"Plant Tycoon Fix Patcher Data");
        names_start(L"Plant Tycoon Fix Patcher Data");
    }
    return installed;
}

/* The Translations setting's question (its contract, feat/translations): "Translations.dll"
   writes its text in Windows-1252 unless a DLL loaded before it exports this and it returns
   nonzero, when it writes UTF-8. Nonzero only once this DLL is installed AND draws UTF-8 text
   (utf8_drawing, a later stage); while it draws the game's bytes (Latin-1, and the
   Windows-1252 letters 0x80-0x9F its fonts now have) it answers 0, so translated text comes
   as Windows-1252 bytes and is drawn with those letters. The loader always loads this DLL
   before any other loader tail (src/ds_fish_loader.py, with_tails). */
int __stdcall FtfpUnicodeTextActive(void) {
    return installed && utf8_drawing;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        self_module = instance;
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
