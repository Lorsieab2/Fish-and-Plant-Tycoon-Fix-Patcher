/* Extra Seed Boxes -- the Fourth to Ninth Seed Box in PC Plant Tycoon.

   WHAT.  The stock seed box is one 120-seed chest of three 40-seed drawers:
   the First Seed Box is open from the start, the Second and Third are bought
   in the store.  This mod adds two more chests with the same three drawers:
   the Fourth, Fifth and Sixth Seed Box, then the Seventh, Eighth and Ninth
   ("Even more space for your seeds!"), sold on the store's Upgrades view
   (Store Upgrades and Items.dll) and bought in order like the stock ones.
   Once the Fourth is owned, gold arrows on the Seed Storage title bar step
   through the chests that have a box ("Boxes 1-3", "Boxes 4-6", "Boxes 7-9",
   then round again); each works exactly like the stock one, because the
   chest on screen is always the one in the game's own box array.  The
   greenhouse knows them too: a seed sent to the seed box goes to the first
   free slot of boxes 1-3, then of boxes 4-6, then of boxes 7-9, and "Your
   seed box is already full!" only comes when all of them are full.

   HOW.  "Store Upgrades and Items.dll" loads this DLL and calls
   FtfpSeedBoxesStartup() before WinMain, which writes every site in
   box_sites.h -- all of them or none -- after checking each holds exactly
   its vanilla bytes: the drawer-level function, and four slots of the Seed
   Storage scene's vtable (mouse, command, draw, activate) that wrap the stock
   functions, and the greenhouse's send-to-box function.
   docs/plant-tycoon-upgrades-design.md has every address.

   STATE.  The game's box array holds the stock chest inside every save (and
   whenever the Seed Storage screen opens), so saves keep their stock
   layout and load as vanilla without the mod.  The two new chests and the
   six purchases are kept per slot in
   "<save folder>\Plant Tycoon Fix Patcher Data\Seed Boxes <slot>.dat"
   (version 2; a version 1 file, the Fourth-Sixth only, still loads). */
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
#define EXTRA_BOXES 6                   /* Fourth to Ninth */
#define BOXES_PER_CHEST 3
#define CHESTS 3                        /* the stock chest (boxes 1-3), boxes 4-6, boxes 7-9 */
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

/* Chest c lives in the game's array when c == resident, else in held[c]
   (held[resident] is stale and never read). */
static unsigned char held[CHESTS][BOX_BYTES];
static int chest = 0;                           /* the chest the Seed Storage screen shows */
static int resident = 0;                        /* the chest in the game's array */
static unsigned char owned[EXTRA_BOXES];        /* Fourth to Ninth */
static void *arrows[2];

/* The boxes owned in order: a box counts only when every box before it is owned. */
static int owned_count(void) {
    int n = 0;
    while (n < EXTRA_BOXES && owned[n]) ++n;
    return n;
}

/* Boxes owned in new chest c (1 or 2): 0 to 3. */
static int chest_boxes(int c) {
    int n = owned_count() - (c - 1) * BOXES_PER_CHEST;
    return n < 0 ? 0 : n > BOXES_PER_CHEST ? BOXES_PER_CHEST : n;
}

static int chest_open(int c) { return c == 0 || (c > 0 && c < CHESTS && chest_boxes(c) > 0); }

static void make_resident(char *state, int c) {
    if (c == resident || c < 0 || c >= CHESTS) return;
    memcpy(held[resident], state + STATE_BOX, BOX_BYTES);
    memcpy(state + STATE_BOX, held[c], BOX_BYTES);
    resident = c;
}

static void clear_new_chests(void) {
    int c, i;
    for (c = 1; c < CHESTS; ++c) {
        for (i = 0; i < BOX_RECORDS; ++i) empty_record(held[c] + i * RECORD_BYTES);
    }
    memset(owned, 0, sizeof owned);
    chest = resident = 0;
}

/* A save put the stock chest back while another one was on screen. */
static void ensure_resident(char *state) {
    make_resident(state, chest);
}

/* 0x41DE60 for a new chest: one drawer per box owned in it. */
static int __cdecl new_chest_level(void) {
    int n = chest_boxes(resident);
    return n > 0 ? n - 1 : 0;
}

/* 0x4245F0(this = greenhouse; tray slot, &row, &col): the stock search over
   the chest in the game's array, run on the stock chest first, then on
   boxes 4-6, then on boxes 7-9 (the chest that took the seed is left in the
   array so the caller's row/col and the flying seed point at it; the Seed
   Storage screen and every save put the stock chest back). */
typedef int (__fastcall *send_fn)(void *greenhouse, int edx, int slot, int *row, int *col);
static void stock_send(void);

static int __cdecl send_to_box(char *greenhouse, int slot, int *row, int *col) {
    char *state = AT(greenhouse, 0x68, char *);
    int c;
    for (c = 0; c < CHESTS; ++c) {
        if (!chest_open(c)) break;                      /* the chests open in order */
        make_resident(state, c);
        if ((((send_fn)(UINT_PTR)stock_send)(greenhouse, 0, slot, row, col) & 0xFF) != 0) return 1;
    }
    make_resident(state, 0);
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
    make_resident(state, to);
    chest = to;
    show_upgrade_tips(scene);
}

/* The next chest with a box, forwards (+1) or backwards (-1), round again. */
static int next_chest(int from, int step) {
    int c = from, i;
    for (i = 0; i < CHESTS; ++i) {
        c = (c + step + CHESTS) % CHESTS;
        if (chest_open(c)) return c;
    }
    return 0;
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
        switch_chest(scene, next_chest(chest, id == ARROW_NEXT ? 1 : -1));
        return 1;
    }
    return stock_command(scene, edx, msg, id);
}

static void __fastcall scene_draw(char *scene, int edx) {
    static const char *const labels[CHESTS] = { "Boxes 1-3", "Boxes 4-6", "Boxes 7-9" };
    ensure_resident(SCENE_STATE(scene));
    stock_draw(scene, edx);
    if (owned[0] && chest >= 0 && chest < CHESTS) {
        draw_text_centred(graphics(), 0, labels[chest], 660, 9, TEXT_COLOUR, 0);
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

/* For "Sort Seeds.dll": where each chest is right now and how many of its
   rows are unlocked (4 per box owned), for up to `capacity` chests.  Returns
   the number of chests filled in (3), or 0 when `capacity` is too small.
   (The version 1 export, FtfpSeedBoxesChests, knew two chests; it is gone, so
   an older Sort Seeds DLL finds no export and stays off.) */
int __cdecl FtfpSeedBoxesChestList(char *state, unsigned char **chests, int *rows, int capacity) {
    int stock_level, c;
    if (state == NULL || chests == NULL || rows == NULL || capacity < CHESTS) return 0;
    stock_level = AT(state, 0x8AC, unsigned char) ? 2 : AT(state, 0x80C, unsigned char) ? 1 : 0;
    for (c = 0; c < CHESTS; ++c) {
        chests[c] = resident == c ? (unsigned char *)state + STATE_BOX : held[c];
        rows[c] = (c == 0 ? stock_level + 1 : chest_boxes(c)) * 4;
    }
    return CHESTS;
}

/* ----------------------------------------------------------------- sidecar */

#define SIDECAR_MAGIC 0x58425350u      /* "PSBX" */
#define SIDECAR_VERSION 2u             /* 1: the Fourth-Sixth only (sidecar_body_v1) */
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

/* Version 1: the Fourth, Fifth and Sixth (owned[0..2], owned[3] 0) and boxes 4-6. */
typedef struct sidecar_body_v1 {
    unsigned char owned[4];
    unsigned char chest[BOX_BYTES];
} sidecar_body_v1;

/* Version 2: the Fourth to Ninth (owned[0..5], owned[6..7] 0), boxes 4-6, then boxes 7-9. */
typedef struct sidecar_body {
    unsigned char owned[8];
    unsigned char chest[CHESTS - 1][BOX_BYTES];
} sidecar_body;

/* Called before the game writes its save: the stock chest goes back into the
   game's array for the write (and returns on the screen's next frame). */
static void __cdecl on_save(const char *state_unused, int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    DWORD header[3], written;
    static sidecar_body body;
    int c;
    (void)state_unused;
    if (slot <= 0 || resident != 0 || !sidecar_path(slot, path, 1024, 1)) return;
    memset(body.owned, 0, sizeof body.owned);
    memcpy(body.owned, owned, EXTRA_BOXES);
    for (c = 1; c < CHESTS; ++c) memcpy(body.chest[c - 1], held[c], BOX_BYTES);   /* never resident here */
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
    if (slot > 0) make_resident(state, 0);
    on_save(state, slot);
}

/* Reads a version 2 file, or a version 1 file into the same body (boxes 7-9
   not owned and empty).  1 when the file is whole and its header is right. */
static int read_sidecar(HANDLE file, sidecar_body *body) {
    DWORD header[3], got, more;
    if (!ReadFile(file, header, sizeof header, &got, NULL) || got != sizeof header || header[0] != SIDECAR_MAGIC) return 0;
    if (header[1] == SIDECAR_VERSION && header[2] == sizeof *body) {
        return ReadFile(file, body, sizeof *body, &got, NULL) && got == sizeof *body
               && ReadFile(file, &more, 1, &got, NULL) && got == 0;          /* nothing after it */
    }
    if (header[1] == 1u && header[2] == sizeof(sidecar_body_v1)) {
        static sidecar_body_v1 old;
        int i;
        if (!ReadFile(file, &old, sizeof old, &got, NULL) || got != sizeof old
            || !ReadFile(file, &more, 1, &got, NULL) || got != 0) return 0;
        memset(body->owned, 0, sizeof body->owned);
        memcpy(body->owned, old.owned, BOXES_PER_CHEST);
        memcpy(body->chest[0], old.chest, BOX_BYTES);
        for (i = 0; i < BOX_RECORDS; ++i) empty_record(body->chest[1] + i * RECORD_BYTES);
        return 1;
    }
    return 0;
}

static void __cdecl on_load(const char *state, int slot) {
    wchar_t path[1024];
    HANDLE file;
    int ok = 0;
    static sidecar_body body;
    (void)state;
    if (slot <= 0) return;
    clear_new_chests();
    if (sidecar_path(slot, path, 1024, 0)) {
        file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (file != INVALID_HANDLE_VALUE) {
            ok = read_sidecar(file, &body);
            CloseHandle(file);
            if (!ok) {                                    /* set aside, never deleted */
                wchar_t aside[1100];
                wcscpy_s(aside, 1100, path);
                wcscat_s(aside, 1100, L".unreadable");
                MoveFileExW(path, aside, MOVEFILE_REPLACE_EXISTING);
            }
        }
    }
    if (ok) {
        int i, c;
        for (i = 0; i < EXTRA_BOXES; ++i) owned[i] = (unsigned char)(body.owned[i] != 0);
        for (c = 1; c < CHESTS; ++c) memcpy(held[c], body.chest[c - 1], BOX_BYTES);
    }
    show_arrows();
}

static void __cdecl on_delete(int slot) {
    wchar_t path[1024];
    if (slot > 0 && sidecar_path(slot, path, 1024, 0)) DeleteFileW(path);
}

static void __cdecl on_new_game(void) {
    clear_new_chests();
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
        call new_chest_level
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

/* "<game>\Plant Tycoon Fix Patcher DLLs\Extra Seed Boxes.log". */
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
    wcscat_s(path, 1024, L"Plant Tycoon Fix Patcher DLLs\\Extra Seed Boxes.log");
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

/* Version 2: owned and set_owned take boxes 0-5 (the Fourth to Ninth); version 1 took 0-2. */
static const ftfp_box_events events = { 2, before_save, on_load, on_delete, on_new_game,
                                        FtfpSeedBoxOwned, FtfpSeedBoxSetOwned };

/* Called once by "Store Upgrades and Items.dll" after it installed, before WinMain. */
const ftfp_box_events *__stdcall FtfpSeedBoxesStartup(void) {
    if (!installed) {
        __try {
            clear_new_chests();
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
