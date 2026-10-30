/* Tank Counts -- how many fish a Fish Tycoon tank holds, on the tank screen.

   WHAT.  Three lines in the game's own font at the top left of the water,
   for the tank on screen (Tank One, Tank Two or the Sale Tank, as the tank
   buttons choose it):
     Fish: 12 of 21 (8 adults, 3 teens, 1 baby)  Dead: 2
     Creatures: Golden Seahorse, Moray Eel
     Isolation tank: 1 of 1 (1 adult)
   in English or German, as the game is.  The room is 21, or 26 with "Bigger
   tanks" (the update loop's own bound, 0x4206B1 `cmp ecx, 0x15`); the
   isolation tank holds one fish (tank 3, slot 0: the drop at 0x41F3E6 refuses
   a second).  Recomputed from the game state every frame; nothing is written.

   WHICH FISH.  Exactly the ones the tank shows.  The view builder (0x413D80)
   shows a record when +0x00 (its clock) and +0x0C (its age) are set, and
   picks its picture by age (0x413F08-0x413F9F):
     age < 1 (0x413F10)   not shown, not counted;
     age < 6 (0x413F1C)   a baby (FISH_baby_Grid.png);
     age < 20 (0x413F65)  a teen (FISH_teen_Grid.png);
     otherwise            an adult.
   The words are the game's own: "You placed a baby or teen fish in your
   selling tank!", "Any adult fish...", German "jungen oder halbwüchsigen
   Fisch", "ausgewachsene Fische".  A fish at health 0 or less (+0x3C) is
   dead (0x414778: the dead picture; "Status: Dead") and stays until it is
   thrown away: it is counted as "Dead", not among the fish.  Body 22 (+0x4C)
   is the Golden Seahorse's (0x41F3C4), and its fin (+0x50) tells the DS
   Store Items' animals apart (22 seahorse, 30 puffer, 31 ray, 32 eel): those
   are "Creatures", never fish, whether they sit in a fish slot (stock) or in
   slots 26-30 (DS Store Items, marked "FTCA" at +0x14), and a Moray Eel at
   home in its rock (an ornament record with sprite 229) is one too.  Eggs
   are not in the tank: they hatch straight into babies.

   HOW.  The startup loader loads this DLL and calls FtfpStartup() before
   WinMain.  It first loads the DLL the loader would load without this
   setting ("DS Exclusive Fish.dll", else "Maximizable Window.dll", when
   their settings put them beside this one), then writes its one site, after
   checking it holds its vanilla bytes, or writes nothing: the tank screen's
   draw (0x422010) calls its background (0x41D140) at 0x422013, and that call
   now comes here, which draws the background and then the counts, so every
   fish, ornament, bubble and button is drawn over them, never under. */
#include <windows.h>
#include "../ftfp_ds_fish/install_sites.h"
#include "../common/count_text.h"

#define AT(base, offset, type) (*(type *)((char *)(base) + (offset)))

/* The tank screen (impl): its state and its graphics. */
#define IMPL_STATE 0x34
#define IMPL_GRAPHICS 0x54

#define S_CURRENT_TANK 0x384
#define S_SCREENSAVER 0x1E4F9       /* byte: the screensaver shows the tank without its interface (0x41D181) */
#define FISH_BASE 0x390
#define TANK_STRIDE 0x51EC
#define SLOT_STRIDE 0x288
#define ISOLATION_TANK 3
#define ANIMAL_FIRST 26             /* DS Store Items' animal slots, 26-30 */
#define RECORDS 31                  /* records per tank (the tank constructor 0x41A9A0) */
#define ORN_BASE 0x5208
#define ORN_STRIDE 0x2C
#define ORN_SLOTS 6
#define O_SPRITE 0x24
#define SPR_EEL_AT_HOME 229         /* DS Store Items: the rock with its eel inside */

#define F_CLOCK 0x00
#define F_AGE 0x0C
#define F_MARK 0x14
#define F_HEALTH 0x3C
#define F_BODY 0x4C
#define F_FIN 0x50
#define ANIMAL_MARK 0x41435446      /* "FTCA" */
#define BODY_SEAHORSE 22

#define AGE_SHOWN 1                 /* 0x413F10 */
#define AGE_TEEN 6                  /* 0x413F1C `cmp eax, 6` */
#define AGE_ADULT 20                /* 0x413F65 `cmp eax, 0x14` */

#define ROOM_STOCK 21
#define ROOM_BIGGER 26
#define ROOM_AT 0x004206B3u         /* the update loop's slot bound, 21 or 26 */

#define LABEL_X 12
#define LABEL_Y 62                  /* just under the top bar (57 px) */
#define LINE_H 20                   /* paddington_tt_18's glyphs are 20 px tall */
#define WHITE 0xFFFFFFFFu
#define SHADOW 0xFF000000u

typedef void (__fastcall *scene_fn)(void *impl, int edx);
typedef void *(__cdecl *getter_fn)(void);
typedef void *(__fastcall *font_fn)(void *fonts, int edx, int index);
typedef void (__fastcall *text_fn)(void *graphics, int edx, const char *text, int x, int y, unsigned int colour,
                                   void *font);

static const scene_fn draw_background = (scene_fn)0x0041D140u;
static const getter_fn font_manager = (getter_fn)0x00418210u;
static const font_fn font_get = (font_fn)0x004181F0u;          /* 0 = paddington_tt_18 (0x4180B0) */
static const text_fn draw_text = (text_fn)0x00408B80u;          /* (text, x, y, colour, font) */
#define LANGUAGE (*(int *volatile *)0x0045B314u)               /* *LANGUAGE == 1: German */

/* ------------------------------------------------------------------ counts */

enum { SEAHORSE, PUFFER, RAY, EEL, KINDS };

typedef struct tank_count {
    int fish, adults, teens, babies, dead;
    int creatures[KINDS];
} tank_count;

static char *record(char *state, int tank, int slot) {
    return state + FISH_BASE + tank * TANK_STRIDE + slot * SLOT_STRIDE;
}

static int kind_of(int fin) {
    switch (fin) {
    case 30: return PUFFER;
    case 31: return RAY;
    case 32: return EEL;
    default: return SEAHORSE;   /* any other body-22 record swims as the seahorse */
    }
}

/* Slots [0, slots) as the tank shows them, then (for the three tanks) the
   animal slots and the eel's rock. */
static void count_tank(char *state, int tank, int slots, tank_count *out) {
    int s, k;
    ZeroMemory(out, sizeof *out);
    for (s = 0; s < slots; ++s) {
        char *f = record(state, tank, s);
        int age = AT(f, F_AGE, int);
        if (AT(f, F_CLOCK, int) == 0 || age < AGE_SHOWN) continue;
        if (AT(f, F_BODY, int) == BODY_SEAHORSE) {
            ++out->creatures[kind_of(AT(f, F_FIN, int))];
        } else if (AT(f, F_HEALTH, int) <= 0) {
            ++out->dead;
        } else {
            ++out->fish;
            if (age < AGE_TEEN) ++out->babies;
            else if (age < AGE_ADULT) ++out->teens;
            else ++out->adults;
        }
    }
    if (tank == ISOLATION_TANK) return;
    for (s = ANIMAL_FIRST; s < RECORDS; ++s) {
        char *f = record(state, tank, s);
        if (AT(f, F_CLOCK, int) != 0 && AT(f, F_BODY, int) == BODY_SEAHORSE && AT(f, F_MARK, int) == ANIMAL_MARK) {
            ++out->creatures[kind_of(AT(f, F_FIN, int))];
        }
    }
    for (k = 0; k < ORN_SLOTS; ++k) {
        unsigned char *o = (unsigned char *)state + ORN_BASE + tank * TANK_STRIDE + k * ORN_STRIDE;
        if (o[0] != 0 && AT(o, O_SPRITE, int) == SPR_EEL_AT_HOME) ++out->creatures[EEL];
    }
}

static int tank_room(void) {
    int room = *(const unsigned char *)(UINT_PTR)ROOM_AT;
    return room == ROOM_BIGGER ? ROOM_BIGGER : ROOM_STOCK;
}

/* ------------------------------------------------------------------- words */

typedef struct words {
    const char *fish, *of, *adult, *adults, *teen, *teens, *baby, *babies, *dead, *creatures, *isolation;
    const char *kind[KINDS];
} words;

/* The creatures' names are the ones the DS Store Items' store page and info
   panel use (the Golden Seahorse's is the game's own store item). */
static const words ENGLISH = {
    "Fish: ", " of ", "adult", "adults", "teen", "teens", "baby", "babies", "Dead: ", "Creatures: ",
    "Isolation tank: ",
    { "Golden Seahorse", "Magic Pufferfish", "Blue-Spotted Stingray", "Moray Eel" },
};
static const words GERMAN = {
    "Fische: ", " von ", "ausgewachsen", "ausgewachsen", "halbw\xFC" "chsig", "halbw\xFC" "chsig", "jung", "jung",
    "Tot: ", "Tiere: ", "Zuchtaquarium: ",
    { "Goldenes Seepferdchen", "Magischer Kugelfisch", "Blaupunktrochen", "Mur\xE4ne" },
};

static void fish_line(count_line *line, const words *w, const char *label, const tank_count *c, int room) {
    ct_start(line);
    ct_count(line, label, c->fish, w->of, room);
    ct_part(line, c->adults, w->adult, w->adults);
    ct_part(line, c->teens, w->teen, w->teens);
    ct_part(line, c->babies, w->baby, w->babies);
    ct_close(line);
    ct_dead(line, w->dead, c->dead);
}

/* "Creatures: Golden Seahorse x2, Moray Eel"; 0 when there are none. */
static int creature_line(count_line *line, const words *w, const tank_count *c) {
    int k, any = 0;
    ct_start(line);
    ct_text(line, w->creatures);
    for (k = 0; k < KINDS; ++k) {
        if (c->creatures[k] <= 0) continue;
        if (any) ct_text(line, ", ");
        ct_text(line, w->kind[k]);
        if (c->creatures[k] > 1) {
            ct_text(line, " x");
            ct_number(line, c->creatures[k]);
        }
        any = 1;
    }
    return any;
}

/* --------------------------------------------------------------- the draw */

static void draw_line(void *graphics, void *font, const char *text, int y) {
    draw_text(graphics, 0, text, LABEL_X + 1, y + 1, SHADOW, font);
    draw_text(graphics, 0, text, LABEL_X, y, WHITE, font);
}

static void draw_counts(char *impl) {
    char *state = AT(impl, IMPL_STATE, char *);
    void *graphics = AT(impl, IMPL_GRAPHICS, void *);
    int *language = LANGUAGE;
    const words *w = language != NULL && *language == 1 ? &GERMAN : &ENGLISH;
    void *manager, *font;
    tank_count tank, isolation;
    count_line line;
    int tank_id, y = LABEL_Y;
    if (state == NULL || graphics == NULL || AT(state, S_SCREENSAVER, unsigned char) != 0) return;
    tank_id = AT(state, S_CURRENT_TANK, int);
    if (tank_id < 0 || tank_id > 2) return;
    manager = font_manager();
    if (manager == NULL || (font = font_get(manager, 0, 0)) == NULL) return;
    count_tank(state, tank_id, tank_room(), &tank);
    count_tank(state, ISOLATION_TANK, 1, &isolation);
    fish_line(&line, w, w->fish, &tank, tank_room());
    draw_line(graphics, font, line.text, y);
    y += LINE_H;
    if (creature_line(&line, w, &tank)) {
        draw_line(graphics, font, line.text, y);
        y += LINE_H;
    }
    fish_line(&line, w, w->isolation, &isolation, 1);
    draw_line(graphics, font, line.text, y);
}

/* 0x422013's call of the background (thiscall, ecx = the tank screen). */
static void __fastcall on_background(char *impl, int edx) {
    draw_background(impl, edx);
    __try {
        draw_counts(impl);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
}

/* ----------------------------------------------------------------- install */

#define BACKGROUND_CALL_VA 0x00422013u
static const unsigned char BACKGROUND_CALL[5] = { 0xE8, 0x28, 0xB1, 0xFF, 0xFF };   /* call 0x41D140 */

static ftfp_site_write writes[1];
static int installed = 0;

EXTERN_C IMAGE_DOS_HEADER __ImageBase;
typedef int (__stdcall *startup_fn)(void);

/* The DLL the startup loader loads when this setting is off, beside this one
   (only an enabled setting's files are there): DS Exclusive Fish (which
   loads the Maximizable Window itself), else the Maximizable Window. */
static void load_next(void) {
    static const wchar_t *const names[2] = { L"DS Exclusive Fish.dll", L"Maximizable Window.dll" };
    wchar_t folder[1024], path[1024];
    wchar_t *slash;
    int i;
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, folder, 1024);
    if (n == 0 || n >= 1024 || (slash = wcsrchr(folder, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(folder) + 32 >= 1024) return;
    for (i = 0; i < 2; ++i) {
        HMODULE module;
        startup_fn startup;
        wcscpy_s(path, 1024, folder);
        wcscat_s(path, 1024, names[i]);
        if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) continue;
        module = LoadLibraryW(path);
        if (module == NULL) return;
        startup = (startup_fn)GetProcAddress(module, "FtfpStartup");
        if (startup != NULL) startup();
        return;
    }
}

/* Called once by the executable's startup stub, before WinMain. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        load_next();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    __try {
        ftfp_site_branch(writes, BACKGROUND_CALL_VA, sizeof BACKGROUND_CALL, BACKGROUND_CALL, 0xE8,
                         (const void *)(UINT_PTR)on_background);
        installed = ftfp_install_sites(writes, 1);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    return installed;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}
