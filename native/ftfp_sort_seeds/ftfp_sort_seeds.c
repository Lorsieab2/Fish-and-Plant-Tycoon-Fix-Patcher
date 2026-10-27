/* Sort Seeds -- a "Sort Seeds" button on Plant Tycoon's Seed Storage screen.

   WHAT.  One click sorts every seed in the unlocked seed box space and packs
   them from the first slot on, left to right and top to bottom: the First
   Seed Box's drawer, then the Second's and the Third's (when bought), then,
   with "Extra Seed Boxes.dll", the Fourth, Fifth and Sixth.  Locked drawers
   are never written.  The order, lowest first:
     1. the class of the plant the seed grows (the game's own A < B < C < D,
        from its foliage and flower genes: D if either is above 17, else C if
        either is even, else B if either is 3, 7, 11 or 15, else A);
     2. that plant's foliage, then its flower;
     3. the parents: the seed's own plant's foliage and flower, then the
        pollen donor's; an unknown parent (a shop seed's "?", gene 0 or
        less) sorts before every known one;
   seeds equal on all of these keep their order.

   SAFETY.  The seeds never move one by one.  The sort reads every present
   seed of the unlocked space into a list, sorts the list, builds the new
   drawer contents in a scratch copy, and then checks that the copy holds
   exactly the same seeds, byte for byte and as many, as the drawers did.
   Only then does it copy the scratch over the drawers; on any mismatch
   (or any fault) nothing is written.  Slots outside the unlocked space are
   copied through untouched, the seed tray is never read or written, and the
   button does nothing while a seed is held.

   HOW.  The startup loader (or "Unused Flowers.dll", when that setting is
   on) loads this DLL and calls FtfpStartup() before WinMain.  It wraps two
   slots of the Seed Storage scene's vtable, command and activate, around
   whatever is there (the stock functions, or "Extra Seed Boxes.dll"'s
   wrappers, which load first): activate adds the button once, command runs
   the sort for the button's id.  With the extra boxes, their DLL's
   FtfpSeedBoxesChests export says where each chest is and how many of its
   rows are unlocked. */
#include <windows.h>
#include <string.h>

#define BOX_RECORDS 120
#define BOX_COLUMNS 10
#define RECORD_BYTES 0x24
#define BOX_BYTES (BOX_RECORDS * RECORD_BYTES)
#define CHESTS 2
#define MAX_SEEDS (CHESTS * BOX_RECORDS)
#define STATE_BOX 0x52CCC
#define STATE_HELD 0x56C
#define STATE_SECOND_BOX 0x80C
#define STATE_THIRD_BOX 0x8AC
#define REC_PRESENT 0x18
#define NO_HOVER 0x63
#define SORT_ID 9
#define SOUND_BUTTON 0xC
#define BUTTON_X 396
#define BUTTON_Y 6

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))
#define SCENE_STATE(scene) AT(scene, 0x2C, char *)

typedef void (__stdcall *empty_record_fn)(void *record);
#ifndef FTFP_TEST_EMPTY_RECORD
static const empty_record_fn empty_record = (empty_record_fn)0x0041D420u;
#else
static void __stdcall empty_record(void *record) { FTFP_TEST_EMPTY_RECORD(record); }   /* tests only */
#endif

/* -------------------------------------------------------------- the order */

typedef struct seed_key {
    int k[8];               /* class, foliage, flower, own foliage, own flower, donor foliage, donor flower, position */
    const unsigned char *record;
} seed_key;

static int gene(const unsigned char *record, int at) { return *(const int *)(record + at); }

static int is_high(int g) { return g > 17; }
static int is_even(int g) { return (g & 1) == 0; }
static int is_b(int g) { return g == 3 || g == 7 || g == 11 || g == 15; }

/* The game's gene class (health, pests and seed value all use it): 0 A, 1 B, 2 C, 3 D. */
static int plant_class(int foliage, int flower) {
    if (is_high(foliage) || is_high(flower)) return 3;
    if (is_even(foliage) || is_even(flower)) return 2;
    if (is_b(foliage) || is_b(flower)) return 1;
    return 0;
}

static int parent(int g) { return g > 0 ? g : 0; }        /* unknown ("?") first */

static void make_key(seed_key *key, const unsigned char *record, int position) {
    int foliage = gene(record, 0x10), flower = gene(record, 0x14);
    key->k[0] = foliage > 0 && flower > 0 ? plant_class(foliage, flower) : 4;   /* no child genes: last */
    key->k[1] = foliage;
    key->k[2] = flower;
    key->k[3] = parent(gene(record, 0x00));
    key->k[4] = parent(gene(record, 0x04));
    key->k[5] = parent(gene(record, 0x08));
    key->k[6] = parent(gene(record, 0x0C));
    key->k[7] = position;
    key->record = record;
}

static int key_less(const seed_key *a, const seed_key *b) {
    int i;
    for (i = 0; i < 8; ++i) {
        if (a->k[i] != b->k[i]) return a->k[i] < b->k[i];
    }
    return 0;
}

/* Insertion sort: at most 240 seeds, stable, no allocation. */
static void sort_keys(seed_key *keys, int count) {
    int i, j;
    for (i = 1; i < count; ++i) {
        seed_key held = keys[i];
        for (j = i; j > 0 && key_less(&held, &keys[j - 1]); --j) keys[j] = keys[j - 1];
        keys[j] = held;
    }
}

/* The records as a sorted list of byte strings, for the before/after check. */
static void sort_bytes(const unsigned char **list, int count) {
    int i, j;
    for (i = 1; i < count; ++i) {
        const unsigned char *held = list[i];
        for (j = i; j > 0 && memcmp(held, list[j - 1], RECORD_BYTES) < 0; --j) list[j] = list[j - 1];
        list[j] = held;
    }
}

static int collect(unsigned char *const *chests, const int *slots, int count,
                   const unsigned char **out) {
    int c, s, n = 0;
    for (c = 0; c < count; ++c) {
        for (s = 0; s < slots[c]; ++s) {
            const unsigned char *record = chests[c] + s * RECORD_BYTES;
            if (record[REC_PRESENT] != 0) out[n++] = record;
        }
    }
    return n;
}

/* Sorts the seeds of chests[0..count) (slots[c] unlocked slots each, from
   slot 0) into scratch[0..count), checks them and copies them back.
   Returns the number of seeds sorted, or -1 when nothing was written. */
static int sort_chests(unsigned char *const *chests, const int *slots, int count,
                       unsigned char (*scratch)[BOX_BYTES]) {
    static seed_key keys[MAX_SEEDS];
    static const unsigned char *before[MAX_SEEDS], *after[MAX_SEEDS];
    unsigned char *scratch_chests[CHESTS];
    int c, s, i, n, m, next = 0;
    if (count < 1 || count > CHESTS) return -1;
    for (c = 0; c < count; ++c) {
        if (slots[c] < 0 || slots[c] > BOX_RECORDS) return -1;
    }
    n = collect(chests, slots, count, before);
    for (i = 0; i < n; ++i) make_key(&keys[i], before[i], i);
    sort_keys(keys, n);
    for (c = 0; c < count; ++c) {
        memcpy(scratch[c], chests[c], BOX_BYTES);      /* locked slots stay as they are */
        for (s = 0; s < slots[c]; ++s) {
            unsigned char *to = scratch[c] + s * RECORD_BYTES;
            if (next < n) memcpy(to, keys[next++].record, RECORD_BYTES);
            else empty_record(to);
        }
        scratch_chests[c] = scratch[c];
    }
    if (next != n) return -1;                           /* more seeds than space: cannot happen */
    m = collect(scratch_chests, slots, count, after);
    if (m != n) return -1;
    sort_bytes(before, n);
    sort_bytes(after, m);
    for (i = 0; i < n; ++i) {
        if (memcmp(before[i], after[i], RECORD_BYTES) != 0) return -1;
    }
    for (c = 0; c < count; ++c) {
        if (memcmp(scratch[c] + slots[c] * RECORD_BYTES, chests[c] + slots[c] * RECORD_BYTES,
                   (size_t)(BOX_RECORDS - slots[c]) * RECORD_BYTES) != 0) return -1;
    }
    for (c = 0; c < count; ++c) memcpy(chests[c], scratch[c], BOX_BYTES);
    return n;
}

#ifndef FTFP_TEST_EMPTY_RECORD

/* ------------------------------------------------------------- the game */

typedef void *(__cdecl *new_fn)(unsigned int size);
typedef void (__fastcall *anim_finish_fn)(void *anim, int edx);
typedef void (__fastcall *file_button_fn)(void *button, int edx, int id, const char *file, int x, int y, void *parent, int zero);
typedef void (__fastcall *add_control_fn)(void *scene, int edx, void *control);
typedef void (__fastcall *sound_fn)(void *sound, int edx, int id);
typedef int (__fastcall *scene_command_fn)(void *scene, int edx, int msg, int id);
typedef void (__fastcall *scene_activate_fn)(void *scene, int edx, int on);
typedef int (__cdecl *chests_fn)(char *state, unsigned char **chests, int *rows);

static const new_fn game_new = (new_fn)0x0044E894u;
static const anim_finish_fn anim_finish = (anim_finish_fn)0x004211D0u;
static const file_button_fn file_button = (file_button_fn)0x00401AA0u;
static const add_control_fn add_control = (add_control_fn)0x0040B400u;
static const sound_fn play_sound = (sound_fn)0x0044A580u;

#define SCENE_COMMAND_VA 0x0046970Cu
#define SCENE_COMMAND_STOCK 0x00433F80u
#define SCENE_ACTIVATE_VA 0x00469724u
#define SCENE_ACTIVATE_STOCK 0x00433930u

static scene_command_fn next_command = NULL;
static scene_activate_fn next_activate = NULL;
static chests_fn boxes_chests = NULL;
static void *button = NULL;
static int installed = 0;
static int last_sorted = -2;

/* The stock chest's unlocked rows: 0x41DE60's rule (4 per box owned). */
static int stock_rows(const char *state) {
    int level = AT(state, STATE_THIRD_BOX, unsigned char) ? 2 : AT(state, STATE_SECOND_BOX, unsigned char) ? 1 : 0;
    return (level + 1) * 4;
}

static void sort_seeds(char *scene) {
    static unsigned char scratch[CHESTS][BOX_BYTES];
    char *state = SCENE_STATE(scene);
    unsigned char *chests[CHESTS];
    int rows[CHESTS], slots[CHESTS], count = 1, c;
    void *anim = AT(scene, 0x40, void *);
    if (state == NULL || AT(state, STATE_HELD, int) != 0) return;
    if (anim != NULL && AT(anim, 0, unsigned char)) anim_finish(anim, 0);
    chests[0] = (unsigned char *)state + STATE_BOX;
    rows[0] = stock_rows(state);
    if (boxes_chests != NULL) {
        count = boxes_chests(state, chests, rows);
        if (count < 1 || count > CHESTS) return;
    }
    for (c = 0; c < count; ++c) {
        if (chests[c] == NULL || rows[c] < 0 || rows[c] > BOX_RECORDS / BOX_COLUMNS) return;
        slots[c] = rows[c] * BOX_COLUMNS;
    }
    last_sorted = sort_chests(chests, slots, count, scratch);
    AT(scene, 0x48, int) = NO_HOVER;
}

/* ---------------------------------------------------------- the question */

/* The game's own question box, the one "Are you sure you want to restart the
   current game?" uses (0x42A5FD-0x42A646): 0x42AB50 builds it from a string
   id, 0x401C90 runs it until a button is clicked (0 for the first button,
   OK) and 0x42AAA0 takes it down.  Its text and its two button labels come
   from the string table (0x44CA70: entry = [0x493CC0 + id*4], text = the
   entry's +0xC override if set, else +8), so for the moment it is built the
   restart question shows this text and OK / Cancel read Yes / No. */
typedef void (__fastcall *question_fn)(void *dialog, int edx, int id, int a, int b, int c, int d);
typedef int (__fastcall *run_modal_fn)(void *dialog, int edx, void *parent, int zero);
typedef void (__fastcall *dialog_done_fn)(void *dialog, int edx);
static const question_fn build_question = (question_fn)0x0042AB50u;
static const run_modal_fn run_modal = (run_modal_fn)0x00401C90u;
static const dialog_done_fn dialog_done = (dialog_done_fn)0x0042AAA0u;
#define STRING_ENTRIES 0x00493CC0u
#define STRING_LAST 0x1B2
#define STR_YES 0x10
#define STR_NO 0x11
#define STR_OK 0x12
#define STR_CANCEL 0x13
#define STR_RESTART_QUESTION 0x3E

static const char QUESTION[] =
    "Sort Seeds in Seed Boxes?\n\n"
    "This will rearrange all seeds throughout\n"
    "your available seed boxes. Some may move\n"
    "to other pages.\n"
    "Click YES to Confirm, NO to Cancel.";

static char *string_entry(int id) {
    char *entry;
    if (id < 1 || id > STRING_LAST) return NULL;
    entry = *(char **)(UINT_PTR)(STRING_ENTRIES + (unsigned int)id * 4u);
    return entry != NULL && AT(entry, 0, int) == id ? entry : NULL;
}

static const char *string_text(int id) {
    char *entry = string_entry(id);
    if (entry == NULL) return NULL;
    return AT(entry, 0xC, const char *) ? AT(entry, 0xC, const char *) : AT(entry, 8, const char *);
}

/* 1 when the player clicked Yes. */
static int ask_to_sort(char *scene) {
    static unsigned char dialog[0x1000];           /* the stock code keeps it on its stack */
    static const int ids[3] = { STR_RESTART_QUESTION, STR_OK, STR_CANCEL };
    const char *texts[3];
    const char *saved[3];
    char *entries[3];
    int i, answer = -1;
    texts[0] = QUESTION;
    texts[1] = string_text(STR_YES);
    texts[2] = string_text(STR_NO);
    for (i = 0; i < 3; ++i) {
        entries[i] = string_entry(ids[i]);
        if (entries[i] == NULL || texts[i] == NULL) return 0;
    }
    for (i = 0; i < 3; ++i) {
        saved[i] = AT(entries[i], 0xC, const char *);
        AT(entries[i], 0xC, const char *) = texts[i];
    }
    __try {
        memset(dialog, 0, sizeof dialog);
        build_question(dialog, 0, STR_RESTART_QUESTION, 1, 1, 0, 0);
    } __finally {
        for (i = 0; i < 3; ++i) AT(entries[i], 0xC, const char *) = saved[i];
    }
    answer = run_modal(dialog, 0, scene, 0);
    dialog_done(dialog, 0);
    return answer == 0;
}

static int __fastcall scene_command(char *scene, int edx, int msg, int id) {
    if (msg == 8 && id == SORT_ID) {
        play_sound(AT(scene, 0x38, void *), 0, SOUND_BUTTON);
        __try {
            if (AT(SCENE_STATE(scene), STATE_HELD, int) == 0 && ask_to_sort(scene)) sort_seeds(scene);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            last_sorted = -3;
        }
        return 1;
    }
    return next_command(scene, edx, msg, id);
}

static void __fastcall scene_activate(char *scene, int edx, int on) {
    next_activate(scene, edx, on);
    if (on && button == NULL) {
        void *b = game_new(0x14);
        if (b != NULL) {
            file_button(b, 0, SORT_ID, "sort_seeds_button.png", BUTTON_X, BUTTON_Y, scene, 0);
            add_control(scene, 0, b);
            button = b;
        }
    }
}

/* ----------------------------------------------------------------- install */

static int in_module(const void *address, HMODULE module) {
    MEMORY_BASIC_INFORMATION info;
    return module != NULL && VirtualQuery(address, &info, sizeof info) == sizeof info
           && (HMODULE)info.AllocationBase == module;
}

/* A vtable slot holds the stock function or "Extra Seed Boxes.dll"'s wrapper. */
static int known_slot(unsigned int va, unsigned int stock, HMODULE boxes) {
    MEMORY_BASIC_INFORMATION info;
    DWORD value;
    if (VirtualQuery((const void *)(UINT_PTR)va, &info, sizeof info) != sizeof info || info.State != MEM_COMMIT) return 0;
    value = *(const DWORD *)(UINT_PTR)va;
    return value == stock || in_module((const void *)(UINT_PTR)value, boxes);
}

static int write_slot(unsigned int va, const void *to) {
    DWORD old, ignored;
    if (!VirtualProtect((void *)(UINT_PTR)va, 4, PAGE_READWRITE, &old)) return 0;
    *(DWORD *)(UINT_PTR)va = (DWORD)(UINT_PTR)to;
    VirtualProtect((void *)(UINT_PTR)va, 4, old, &ignored);
    return 1;
}

static void write_install_log(void) {
    wchar_t path[1024];
    const char *line = installed ? "Sort Seeds: installed\r\n"
                                 : "Sort Seeds: NOT installed (the Seed Storage scene is not the stock one)\r\n";
    DWORD n = GetModuleFileNameW(NULL, path, 1024), written;
    wchar_t *slash;
    HANDLE file;
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(path) + 64 >= 1024) return;
    wcscat_s(path, 1024, L"Plant Tycoon Fix Patcher DLLs\\Sort Seeds.log");
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)strlen(line), &written, NULL);
    CloseHandle(file);
}

/* Called once before WinMain, by the startup loader or "Unused Flowers.dll"
   (after "Extra Seed Boxes.dll" installed, when that is present). */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        HMODULE boxes = GetModuleHandleW(L"Extra Seed Boxes.dll");
        if (boxes != NULL) boxes_chests = (chests_fn)GetProcAddress(boxes, "FtfpSeedBoxesChests");
        if (boxes != NULL && boxes_chests == NULL) boxes = NULL;     /* an older Seed Boxes DLL: no wrappers to trust */
        if (known_slot(SCENE_COMMAND_VA, SCENE_COMMAND_STOCK, boxes)
            && known_slot(SCENE_ACTIVATE_VA, SCENE_ACTIVATE_STOCK, boxes)) {
            next_command = *(scene_command_fn *)(UINT_PTR)SCENE_COMMAND_VA;
            next_activate = *(scene_activate_fn *)(UINT_PTR)SCENE_ACTIVATE_VA;
            if (write_slot(SCENE_COMMAND_VA, (const void *)(UINT_PTR)scene_command)) {
                if (write_slot(SCENE_ACTIVATE_VA, (const void *)(UINT_PTR)scene_activate)) installed = 1;
                else write_slot(SCENE_COMMAND_VA, (const void *)(UINT_PTR)next_command);
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    return installed;
}

int __stdcall FtfpSortSeedsLastResult(void) { return last_sorted; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}

#endif
