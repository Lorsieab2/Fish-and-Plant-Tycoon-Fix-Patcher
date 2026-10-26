/* FTFP Seed Boxes -- the Fourth, Fifth and Sixth Seed Box in PC Plant Tycoon.

   WHAT.  The stock seed box is one 120-seed chest of three 40-seed drawers:
   the First Seed Box is open from the start, the Second and Third are bought
   in the store.  This mod adds a second chest with the same three drawers,
   the Fourth, Fifth and Sixth Seed Box ("Even more space for your seeds!"),
   sold on the store's Upgrades view (FTFP Plant Upgrades.dll) and bought in
   order like the stock ones.  Once the Fourth is owned, gold arrows on the
   Seed Storage title bar switch between the two chests; each works exactly
   like the stock one, because the chest on screen is always the one in the
   game's own box array.  The greenhouse knows them too: a seed sent to the
   seed box goes to the first free slot of boxes 1-3, then of boxes 4-6, and
   "Your seed box is already full!" only comes when all of them are full.

   HOW.  "FTFP Plant Upgrades.dll" loads this DLL and calls
   FtfpSeedBoxesStartup() before WinMain, which writes every site in
   box_sites.h -- all of them or none -- after checking each holds exactly
   its vanilla bytes: the drawer-level function, and four slots of the Seed
   Storage scene's vtable (mouse, command, draw, activate) that wrap the stock
   functions, and the greenhouse's send-to-box function.
   docs/plant-tycoon-upgrades-design.md has every address.

   STATE.  The game's box array holds the stock chest inside every save (and
   whenever the Seed Storage screen opens), so saves keep their stock
   layout and load as vanilla without the mod.  The second chest and the
   three purchases are kept per slot in
   "<save folder>\Plant Tycoon Fix Patcher Data\Seed Boxes <slot>.dat". */
#include <windows.h>
#include <string.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "box_sites.h"

#define BOX_RECORDS 120
#define RECORD_BYTES 0x24
#define BOX_BYTES (BOX_RECORDS * RECORD_BYTES)
#define STATE_BOX 0x52CCC
#define STATE_HELD 0x56C
#define HELD_BOX_FIRST 100
#define NO_HOVER 0x63
#define EXTRA_BOXES 3
#define ARROW_PREV 7
#define ARROW_NEXT 8
#define SOUND_BUTTON 0xC

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))
#define SCENE_STATE(scene) AT(scene, 0x2C, char *)

typedef void *(__cdecl *new_fn)(unsigned int size);
typedef void (__stdcall *empty_record_fn)(void *record);
typedef void (__fastcall *anim_finish_fn)(void *anim, int edx);
typedef void (__fastcall *file_button_fn)(void *button, int edx, int id, const char *file, int x, int y, void *parent, int zero);
typedef void (__fastcall *add_control_fn)(void *scene, int edx, void *control);
typedef void (__fastcall *set_active_fn)(void *control, int edx, int on);
typedef void (__fastcall *sound_fn)(void *sound, int edx, int id);
typedef void *(__cdecl *graphics_fn)(void);
typedef void (__fastcall *text_fn)(void *graphics, int edx, const char *text, int x, int y, int colour, int font);

static const new_fn game_new = (new_fn)0x0044E894u;
static const empty_record_fn empty_record = (empty_record_fn)0x0041D420u;
static const anim_finish_fn anim_finish = (anim_finish_fn)0x004211D0u;
static const file_button_fn file_button = (file_button_fn)0x00401AA0u;
static const add_control_fn add_control = (add_control_fn)0x0040B400u;
static const sound_fn play_sound = (sound_fn)0x0044A580u;
static const graphics_fn graphics = (graphics_fn)0x00407A90u;
static const text_fn draw_text_centred = (text_fn)0x004092B0u;
#define TEXT_COLOUR (*(int *)0x0048EA2Cu)

typedef int (__fastcall *scene_mouse_fn)(void *scene, int edx, int msg, int x, int y);
typedef int (__fastcall *scene_command_fn)(void *scene, int edx, int msg, int id);
typedef void (__fastcall *scene_draw_fn)(void *scene, int edx);
typedef void (__fastcall *scene_activate_fn)(void *scene, int edx, int on);
typedef int (__fastcall *box_level_fn)(void *state, int edx);
static const scene_mouse_fn stock_mouse = (scene_mouse_fn)SITE_SCENE_MOUSE_STOCK;
static const scene_command_fn stock_command = (scene_command_fn)SITE_SCENE_COMMAND_STOCK;
static const scene_draw_fn stock_draw = (scene_draw_fn)SITE_SCENE_DRAW_STOCK;
static const scene_activate_fn stock_activate = (scene_activate_fn)SITE_SCENE_ACTIVATE_STOCK;
static const box_level_fn box_level = (box_level_fn)0x0041DE60u;

/* ------------------------------------------------------------------- chests */

static unsigned char other_chest[BOX_BYTES];    /* the chest not in the game's array */
static int chest = 0;                           /* the chest the Seed Storage screen shows */
static int resident = 0;                        /* the chest in the game's array */
static unsigned char owned[EXTRA_BOXES];        /* Fourth, Fifth, Sixth */
static void *arrows[2];

static int owned_count(void) { return owned[0] + (owned[0] && owned[1]) + (owned[0] && owned[1] && owned[2]); }

static void swap_chests(char *state) {
    static unsigned char temp[BOX_BYTES];
    memcpy(temp, state + STATE_BOX, BOX_BYTES);
    memcpy(state + STATE_BOX, other_chest, BOX_BYTES);
    memcpy(other_chest, temp, BOX_BYTES);
    resident = !resident;
}

static void clear_second_chest(void) {
    int i;
    for (i = 0; i < BOX_RECORDS; ++i) empty_record(other_chest + i * RECORD_BYTES);
    memset(owned, 0, sizeof owned);
    chest = resident = 0;
}

/* A save put the stock chest back while the second one was on screen. */
static void ensure_resident(char *state) {
    if (resident != chest) swap_chests(state);
}

/* 0x41DE60 for the second chest: one drawer per box owned. */
static int __cdecl second_chest_level(void) {
    int n = owned_count();
    return n > 0 ? n - 1 : 0;
}

/* 0x4245F0(this = greenhouse; tray slot, &row, &col): the stock search over
   the chest in the game's array, run on the stock chest first, then on the
   second one (left in the array so the caller's row/col and the flying seed
   point at it; the Seed Storage screen and every save put the stock chest
   back). */
typedef int (__fastcall *send_fn)(void *greenhouse, int edx, int slot, int *row, int *col);
static void stock_send(void);

static int __cdecl send_to_box(char *greenhouse, int slot, int *row, int *col) {
    char *state = AT(greenhouse, 0x68, char *);
    if (resident != 0) swap_chests(state);
    if ((((send_fn)(UINT_PTR)stock_send)(greenhouse, 0, slot, row, col) & 0xFF) != 0) return 1;
    if (owned_count() == 0) return 0;
    swap_chests(state);
    if ((((send_fn)(UINT_PTR)stock_send)(greenhouse, 0, slot, row, col) & 0xFF) != 0) return 1;
    swap_chests(state);
    return 0;
}

static void show_upgrade_tips(char *scene) {
    int level = box_level(SCENE_STATE(scene), 0);
    void *tip = AT(scene, 0x0C, void *);
    if (tip) ((set_active_fn)AT(AT(tip, 0, char *), 0x14, void *))(tip, 0, level < 2);
    tip = AT(scene, 0x08, void *);
    if (tip) ((set_active_fn)AT(AT(tip, 0, char *), 0x14, void *))(tip, 0, level < 1);
}

static void switch_chest(char *scene, int to) {
    char *state = SCENE_STATE(scene);
    void *anim = AT(scene, 0x40, void *);
    ensure_resident(state);
    if (to == chest) return;
    if (anim != NULL && AT(anim, 0, unsigned char)) anim_finish(anim, 0);
    if (AT(state, STATE_HELD, int) >= HELD_BOX_FIRST) AT(state, STATE_HELD, int) = 0;   /* it never left its slot */
    AT(scene, 0x48, int) = NO_HOVER;
    swap_chests(state);
    chest = to;
    show_upgrade_tips(scene);
}

static void show_arrows(void) {
    int i;
    for (i = 0; i < 2; ++i) {
        if (arrows[i] != NULL) AT(arrows[i], 8, unsigned char) = (unsigned char)(owned[0] != 0);
    }
}

/* ------------------------------------------------------- the scene's vtable */

static int __fastcall scene_mouse(char *scene, int edx, int msg, int x, int y) {
    ensure_resident(SCENE_STATE(scene));
    return stock_mouse(scene, edx, msg, x, y);
}

static int __fastcall scene_command(char *scene, int edx, int msg, int id) {
    if (msg == 8 && (id == ARROW_PREV || id == ARROW_NEXT) && owned[0]) {
        play_sound(AT(scene, 0x38, void *), 0, SOUND_BUTTON);
        switch_chest(scene, !chest);
        return 1;
    }
    return stock_command(scene, edx, msg, id);
}

static void __fastcall scene_draw(char *scene, int edx) {
    ensure_resident(SCENE_STATE(scene));
    stock_draw(scene, edx);
    if (owned[0]) {
        draw_text_centred(graphics(), 0, chest ? "Boxes 4-6" : "Boxes 1-3", 660, 9, TEXT_COLOUR, 0);
    }
}

static void __fastcall scene_activate(char *scene, int edx, int on) {
    if (on) ensure_resident(SCENE_STATE(scene));
    else switch_chest(scene, 0);
    stock_activate(scene, edx, on);
    if (on && arrows[0] == NULL) {
        static const char *const files[2] = { "leftarrow.png", "rightarrow.png" };
        static const int ids[2] = { ARROW_PREV, ARROW_NEXT }, xs[2] = { 338, 716 };
        int i;
        for (i = 0; i < 2; ++i) {
            void *button = game_new(0x14);
            if (button == NULL) break;
            file_button(button, 0, ids[i], files[i], xs[i], -9, scene, 0);
            add_control(scene, 0, button);
            arrows[i] = button;
        }
    }
    show_arrows();
}

/* ----------------------------------------------------------------- the store */

int __cdecl FtfpSeedBoxOwned(int box) { return box >= 0 && box < EXTRA_BOXES ? owned[box] : 0; }

void __cdecl FtfpSeedBoxSetOwned(int box, int value) {
    if (box >= 0 && box < EXTRA_BOXES) owned[box] = (unsigned char)(value != 0);
    show_arrows();
}

/* ----------------------------------------------------------------- sidecar */

#define SIDECAR_MAGIC 0x58425350u      /* "PSBX" */
#define SIDECAR_VERSION 1u
typedef BOOL (WINAPI *special_folder_fn)(HWND, LPWSTR, int, BOOL);

/* "<Documents>\LDW\<exe name>\Plant Tycoon Fix Patcher Data\Seed Boxes <slot>.dat". */
static int sidecar_path(int slot, wchar_t *out, DWORD cap, int make_folder) {
    wchar_t exe[MAX_PATH];
    wchar_t *name, *dot;
    special_folder_fn special;
    HMODULE shell = LoadLibraryW(L"shell32.dll");
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
    if (shell == NULL || n == 0 || n >= MAX_PATH) return 0;
    special = (special_folder_fn)GetProcAddress(shell, "SHGetSpecialFolderPathW");
    if (special == NULL || !special(NULL, out, 0x0005 /* CSIDL_PERSONAL */, FALSE)) return 0;
    name = wcsrchr(exe, L'\\');
    name = name ? name + 1 : exe;
    dot = wcsrchr(name, L'.');
    if (dot) *dot = L'\0';
    if (wcslen(out) + wcslen(name) + 90 >= cap) return 0;
    wcscat_s(out, cap, L"\\LDW\\");
    wcscat_s(out, cap, name);
    wcscat_s(out, cap, L"\\Plant Tycoon Fix Patcher Data");
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\Seed Boxes ");
    {
        wchar_t digits[12];
        int i = 0, v = slot;
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 11);
        while (i) { size_t len = wcslen(out); out[len] = digits[--i]; out[len + 1] = L'\0'; }
    }
    wcscat_s(out, cap, L".dat");
    return 1;
}

typedef struct sidecar_body {
    unsigned char owned[4];
    unsigned char chest[BOX_BYTES];
} sidecar_body;

/* Called before the game writes its save: the stock chest goes back into the
   game's array for the write (and returns on the screen's next frame). */
static void __cdecl on_save(const char *state_unused, int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    DWORD header[3], written;
    static sidecar_body body;
    (void)state_unused;
    if (slot <= 0 || !sidecar_path(slot, path, 1024, 1)) return;
    memcpy(body.owned, owned, EXTRA_BOXES);
    body.owned[3] = 0;
    memcpy(body.chest, other_chest, BOX_BYTES);       /* the second chest (it is never resident here) */
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    header[0] = SIDECAR_MAGIC;
    header[1] = SIDECAR_VERSION;
    header[2] = (DWORD)sizeof body;
    if (WriteFile(file, header, sizeof header, &written, NULL) && written == sizeof header
        && WriteFile(file, &body, sizeof body, &written, NULL) && written == sizeof body) {
        CloseHandle(file);
        MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING);
    } else {
        CloseHandle(file);
        DeleteFileW(temp);
    }
}

static void __cdecl before_save(char *state, int slot) {
    if (slot > 0 && resident != 0) swap_chests(state);
    on_save(state, slot);
}

static void __cdecl on_load(const char *state, int slot) {
    wchar_t path[1024];
    HANDLE file;
    DWORD header[3], got;
    int ok = 0;
    static sidecar_body body;
    (void)state;
    if (slot <= 0) return;
    clear_second_chest();
    if (sidecar_path(slot, path, 1024, 0)) {
        file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (file != INVALID_HANDLE_VALUE) {
            ok = ReadFile(file, header, sizeof header, &got, NULL) && got == sizeof header
                 && header[0] == SIDECAR_MAGIC && header[1] == SIDECAR_VERSION && header[2] == sizeof body
                 && ReadFile(file, &body, sizeof body, &got, NULL) && got == sizeof body;
            CloseHandle(file);
            if (!ok) {
                wchar_t aside[1100];
                wcscpy_s(aside, 1100, path);
                wcscat_s(aside, 1100, L".unreadable");
                MoveFileExW(path, aside, MOVEFILE_REPLACE_EXISTING);
            }
        }
    }
    if (ok) {
        int i;
        for (i = 0; i < EXTRA_BOXES; ++i) owned[i] = (unsigned char)(body.owned[i] != 0);
        memcpy(other_chest, body.chest, BOX_BYTES);
    }
    show_arrows();
}

static void __cdecl on_delete(int slot) {
    wchar_t path[1024];
    if (slot > 0 && sidecar_path(slot, path, 1024, 0)) DeleteFileW(path);
}

static void __cdecl on_new_game(void) {
    clear_second_chest();
    show_arrows();
}

/* ------------------------------------------------------------------- stubs */

static const DWORD k_level_back = SITE_BOX_LEVEL_BACK;
static const DWORD k_send_back = SITE_SEND_TO_BOX_BACK;

/* 0x41DE60 drawer level (thiscall, ecx = state): of the chest in the game's array. */
__declspec(naked) static void stub_level(void) {
    __asm {
        cmp dword ptr [resident], 0
        je stock
        push ecx
        call second_chest_level
        pop ecx
        ret
    stock:
        cmp byte ptr [ecx + 0x8AC], 0
        jmp k_level_back
    }
}

/* The stock 0x4245F0 (its first instructions, then the rest of it). */
__declspec(naked) static void stock_send(void) {
    __asm {
        push ebx
        push esi
        mov esi, ecx
        mov ecx, [esi + 0x68]
        jmp k_send_back
    }
}

/* 0x4245F0 (thiscall, ret 0xC). */
__declspec(naked) static void stub_send(void) {
    __asm {
        push dword ptr [esp + 12]      /* &col */
        push dword ptr [esp + 12]      /* &row */
        push dword ptr [esp + 12]      /* tray slot */
        push ecx
        call send_to_box
        add esp, 16
        ret 0xC
    }
}

/* ----------------------------------------------------------------- install */

#define CODE_ADDR(f) ((const void *)(UINT_PTR)(f))
#define TOTAL_SITES 6
static ftfp_site_write writes[TOTAL_SITES];
static int installed = 0;

static void site_pointer(ftfp_site_write *w, unsigned int va, const unsigned char *expect, const void *to) {
    DWORD value = (DWORD)(UINT_PTR)to;
    w->va = va;
    w->length = 4;
    w->expect = expect;
    memcpy(w->bytes, &value, 4);
}

static int prepare(void) {
    ftfp_site_write *w = writes;
    ftfp_site_branch(w++, SITE_BOX_LEVEL_VA, SITE_BOX_LEVEL_LEN, SITE_BOX_LEVEL_EXPECT, 0xE9, CODE_ADDR(stub_level));
    ftfp_site_branch(w++, SITE_SEND_TO_BOX_VA, SITE_SEND_TO_BOX_LEN, SITE_SEND_TO_BOX_EXPECT, 0xE9, CODE_ADDR(stub_send));
    site_pointer(w++, SITE_SCENE_MOUSE_VA, SITE_SCENE_MOUSE_EXPECT, CODE_ADDR(scene_mouse));
    site_pointer(w++, SITE_SCENE_COMMAND_VA, SITE_SCENE_COMMAND_EXPECT, CODE_ADDR(scene_command));
    site_pointer(w++, SITE_SCENE_DRAW_VA, SITE_SCENE_DRAW_EXPECT, CODE_ADDR(scene_draw));
    site_pointer(w++, SITE_SCENE_ACTIVATE_VA, SITE_SCENE_ACTIVATE_EXPECT, CODE_ADDR(scene_activate));
    return (int)(w - writes) == TOTAL_SITES;
}

static int append_text(char *out, int at, const char *text) {
    while (*text && at < 158) out[at++] = *text++;
    return at;
}

static int append_hex(char *out, int at, unsigned int v) {
    int shift;
    at = append_text(out, at, "0x");
    for (shift = 28; shift >= 0 && at < 158; shift -= 4) out[at++] = "0123456789ABCDEF"[(v >> shift) & 0xF];
    return at;
}

/* "<game>\Plant Tycoon Fix Patcher Files\FTFP Seed Boxes.log". */
static void write_install_log(void) {
    wchar_t path[1024];
    char line[160];
    DWORD n = GetModuleFileNameW(NULL, path, 1024), written;
    wchar_t *slash;
    HANDLE file;
    int len = 0;
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(path) + 64 >= 1024) return;
    wcscat_s(path, 1024, L"Plant Tycoon Fix Patcher Files\\FTFP Seed Boxes.log");
    if (installed) {
        len = append_text(line, len, "Seed Boxes: installed (all sites)\r\n");
    } else if (ftfp_failed_site != 0) {
        len = append_text(line, len, "Seed Boxes: NOT installed; the code at ");
        len = append_hex(line, len, ftfp_failed_site);
        len = append_text(line, len, " is not the stock code this build expects\r\n");
    } else {
        len = append_text(line, len, "Seed Boxes: NOT installed\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* The Plant Upgrades DLL passes on the save, load, delete and new-game events. */
typedef struct ftfp_box_events {
    int version;
    void (__cdecl *save)(char *state, int slot);
    void (__cdecl *load)(const char *state, int slot);
    void (__cdecl *remove)(int slot);
    void (__cdecl *new_game)(void);
    int (__cdecl *owned)(int box);
    void (__cdecl *set_owned)(int box, int value);
} ftfp_box_events;

static const ftfp_box_events events = { 1, before_save, on_load, on_delete, on_new_game,
                                        FtfpSeedBoxOwned, FtfpSeedBoxSetOwned };

/* Called once by "FTFP Plant Upgrades.dll" after it installed, before WinMain. */
const ftfp_box_events *__stdcall FtfpSeedBoxesStartup(void) {
    if (!installed) {
        __try {
            clear_second_chest();
            if (prepare() && ftfp_install_sites(writes, TOTAL_SITES)) installed = 1;
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            installed = 0;
        }
        write_install_log();
    }
    return installed ? &events : NULL;
}

int __stdcall FtfpSeedBoxesInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}
