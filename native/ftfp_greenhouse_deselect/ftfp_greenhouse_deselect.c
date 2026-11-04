/* Click to Deselect -- a click on the greenhouse's empty background clears the selected plant.

   WHAT.  With a plant (or an empty pot) selected and nothing in the hand, a press on the greenhouse's
   background selects nothing: the left panel shows the game's own "No plant selected" and the selection
   frame goes, as at the start of the screen.  A press that already does something is the game's, as before.

   WHERE THE SELECTION LIVES.  The greenhouse state (scene+0x68) holds the selected pot's number (row * 5 +
   column) at +0x63E58, and 99 (0x63) when none is selected (the screen's reset writes it, 0x4231F8; the
   selecting function 0x423630 writes the number); the scene's byte +0x104 shows the selection frame (0x428EB2
   draws it; the reset clears it, 0x423213).  The panel (0x428250, called from the overlay at 0x428FB9) reads
   the number and draws string 0x18D, "No plant selected", for 99.  The hand is state+0x56C (0 = nothing).

   THE HOOKS.  The press (0x426040, from the mouse slot's type 2) tests, in order: the shelf and tool tray,
   the tap and hose, the pots (0x423970: the 5 x 3 cells of the benches, x 270-730, y 43-475; with nothing
   held, a press on a cell selects it by calling 0x423630 at 0x427295), and then, off the cells, the trash
   click and the put-back (0x4272DC-0x427367).  Two sites, both inside that press:
     * 0x427295, the call of the select: it goes to a function here (the same registers and arguments, the
       same `ret 0xC`), which calls the stock select, except for a cell whose slot holds no plant (the
       byte state+0x2188+0x38+k*0x5600, which the overlay's plant draw tests at 0x428FE3): that is empty
       bench, and with a plant selected it clears the selection instead;
     * 0x42734C, where a press off the cells that the trash did not take goes on: `mov edx, [esi+0x68];
       cmp dword ptr [edx+0x56C], 0` (10 bytes) become a jump to a stub here, which runs the check below,
       then those two instructions, and jumps back to 0x427356.
   Buttons, Counts' button and Extra Greenhouses' arrows take their clicks before the stock press.

   WHICH CLICKS.  Only when nothing is held (a tool, seed, pollen or pot in the hand is untouched), a plant is
   selected, and the point is the floor: off the cells, right of the left panel (x >= 240), above the bottom
   bar (y < 506) and not in the faucet's rectangle (754,430, 50 x 75, tested next by the stock press); or an
   empty bench cell.  A plant, a pot, or the selected plant clicked again is the game's own.

   INSTALL.  "Click to Deselect.dll" is a loader tail (src/ds_fish_loader.py): the startup loader loads it
   after every other companion.  Both sites are checked against the stock bytes and written, or nothing is
   written; "Click to Deselect.log" beside the DLL says which. */
#include <windows.h>
#include "../ftfp_ds_fish/install_sites.h"

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))

#define SCENE_STATE 0x68
#define SCENE_FRAME 0x104
#define S_HELD 0x56C
#define S_SELECTED 0x63E58
#define NONE_SELECTED 0x63
#define FLOOR_LEFT 240
#define FLOOR_BOTTOM 506
#define NEXT_LEFT 0x2F2
#define NEXT_TOP 0x1AE
#define NEXT_WIDTH 0x32
#define NEXT_HEIGHT 0x4B

#define PRESS_SITE_VA 0x0042734Cu
#define PRESS_SITE_BACK 0x00427356u
static const unsigned char PRESS_SITE[10] = { 0x8B, 0x56, 0x68,                               /* mov edx, [esi+0x68] */
                                              0x83, 0xBA, 0x6C, 0x05, 0x00, 0x00, 0x00 };    /* cmp [edx+0x56C], 0 */

#define SELECT_SITE_VA 0x00427295u
static const unsigned char SELECT_SITE[5] = { 0xE8, 0x96, 0xC3, 0xFF, 0xFF };               /* call 0x423630 */
#define SELECT_VA 0x00423630u
#define POT_BASE 0x2188
#define POT_STRIDE 0x5600
#define POT_PLANT_SPRITE 0x38

typedef void (__fastcall *select_fn)(char *scene, int edx, int row, int col, int flag);
static const select_fn stock_select = (select_fn)SELECT_VA;

static HMODULE self_module;

static void __fastcall on_press(char *scene, int x, int y) {
    __try {
        char *state = AT(scene, SCENE_STATE, char *);
        if (state == NULL || AT(state, S_HELD, int) != 0 || AT(state, S_SELECTED, int) == NONE_SELECTED) return;
        if (x < FLOOR_LEFT || y >= FLOOR_BOTTOM) return;
        if (x >= NEXT_LEFT && x <= NEXT_LEFT + NEXT_WIDTH && y >= NEXT_TOP && y <= NEXT_TOP + NEXT_HEIGHT) return;
        AT(state, S_SELECTED, int) = NONE_SELECTED;
        AT(scene, SCENE_FRAME, char) = 0;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
}

/* 0x427295 in the press: the stock call of the select (thiscall scene, row, col, flag; ret 0xC) for the cell
   under the press.  An empty cell, with a plant selected and nothing in the hand, clears the selection. */
static void __fastcall on_select(char *scene, int edx, int row, int col, int flag) {
    int clear = 0;
    __try {
        char *state = AT(scene, SCENE_STATE, char *);
        if (state != NULL && AT(state, S_HELD, int) == 0 && AT(state, S_SELECTED, int) != NONE_SELECTED
            && row >= 0 && row < 3 && col >= 0 && col < 5
            && AT(state, POT_BASE + (row * 5 + col) * POT_STRIDE + POT_PLANT_SPRITE, char) == 0) {
            AT(state, S_SELECTED, int) = NONE_SELECTED;
            AT(scene, SCENE_FRAME, char) = 0;
            clear = 1;
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        clear = 0;
    }
    if (!clear) stock_select(scene, edx, row, col, flag);
}

/* Jumped to from 0x42734C (esi = scene, ebx = x, ebp = y): registers and flags kept, then the two
   instructions the jump replaced, then on to the `je` after them. */
static const DWORD press_back = PRESS_SITE_BACK;
__declspec(naked) static void stub_press(void) {
    __asm {
        pushad
        pushfd
        push ebp
        mov edx, ebx
        mov ecx, esi
        call on_press
        popfd
        popad
        mov edx, [esi + 0x68]
        cmp dword ptr [edx + 0x56C], 0
        jmp dword ptr [press_back]
    }
}

static ftfp_site_write writes[2];
static int installed = 0;

static int append_text(char *out, int at, const char *text) {
    while (*text && at < 150) out[at++] = *text++;
    return at;
}

static void write_install_log(void) {
    wchar_t path[1024];
    wchar_t *slash;
    char line[160];
    DWORD written, n = GetModuleFileNameW(self_module, path, 1024);
    HANDLE file;
    int len = 0;
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL || wcslen(path) + 32 >= 1024) return;
    slash[1] = L'\0';
    wcscat_s(path, 1024, L"Click to Deselect.log");
    len = append_text(line, len, installed ? "Click to Deselect: installed\r\n"
                                           : "Click to Deselect: not installed (the code at 0x0042734C or 0x00427295 is not the stock code)\r\n");
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* Called once by the executable's startup stub, before WinMain. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        ftfp_site_branch(&writes[0], PRESS_SITE_VA, sizeof PRESS_SITE, PRESS_SITE, 0xE9, (const void *)(UINT_PTR)stub_press);
        ftfp_site_branch(&writes[1], SELECT_SITE_VA, sizeof SELECT_SITE, SELECT_SITE, 0xE8, (const void *)(UINT_PTR)on_select);
        installed = ftfp_install_sites(writes, 2);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    return installed;
}

int __stdcall FtfpDeselectInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        self_module = instance;
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
