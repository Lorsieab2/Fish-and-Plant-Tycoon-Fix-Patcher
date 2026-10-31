/* Muta-Flower and Muta-Foliage -- two chemicals on the Plant Tycoon Upgrades view (included by
   ftfp_plant_upgrades.c, after the Auto items).

   WHAT.  Each is $2,500 ($0 with Free upgrades) for 3 doses, bought through the stock chemical
   dialog as the Revival Potion is, into the chemical tray.  A dose is the stock Mutation Liquid's
   dose (chemical 34) for one gene only: Muta-Flower changes the flower, Muta-Foliage the foliage.

   THE GAME'S RULES.  The Mutation Liquid (case 7 of the chemical switch at 0x4266B6):
     * the targeting is the use's, the same for every chemical (0x426660-0x4266A0): the pot it is
       dropped on (row, column), which must be planted (+0x38) with a foliage (+0x4C); then one
       dose is spent (0x416540).  Live or dead, any age;
     * the step, 0x42FA80(row, column) on the greenhouse's plant table (+0x70): Random(2) != 0
       steps the flower (0x42FAB2), else the foliage (0x42FAF5); each steps by Random(2) != 0 down,
       else up (exactly 50% each).  The flower: above 23 becomes 22 (above 37 becomes 36 with
       Unused Flowers, which rewrites 0x42FACE and 0x42FAD5), 0 becomes 2.  The foliage: 24
       becomes 22, 0 becomes 2, and the plant's picture is grown again for the new foliage
       (0x42F660, its flowers and growth kept); a pot with no plant object keeps its foliage;
     * then the new species is discovered (0x426F11, which Unused Flowers hooks at 0x426F0B for its
       flowers), the encyclopedia is told (0x41EB00), the sparkles and the tail (0x42720B).
   A Muta dose runs exactly that code with the first Random(2) left out: the flower branch
   (Muta-Flower) or the foliage branch (Muta-Foliage) of 0x42FA80 itself, entered at its own
   address with the frame the function's prologue builds (muta_branch), then the rest of the
   Mutation Liquid's case from 0x426EFA.  So the changed gene steps up or down 50/50 with the
   game's own bounces, the other gene never changes, and every effect after the step (discovery,
   Unused Flowers' discovery, the encyclopedia, the sparkles) is the Mutation Liquid's. */

#define MUTA_FLOWER_ID 48                   /* chemicals sheet row 21 (frames 42, 43) */
#define MUTA_FOLIAGE_ID 49                  /* row 22 (frames 44, 45) */
#define MUTA_PRICE 2500
#define MUTA_FLOWER_NAME_ID 0x1FB
#define MUTA_FOLIAGE_NAME_ID 0x1FC
#define MUTA_Y (55 + 2 * 61)                /* the chemicals shelf's third row, beside Extra Chemical Slots */
#define MUTA_FLOWER_X (598 + 57)
#define MUTA_FOLIAGE_X (598 + 2 * 57)

static const char MUTA_FLOWER_TITLE[] = "Muta-Flower\n";
static const char MUTA_FLOWER_DESC[] = "Mutates the flowering parts of plants.\nContains 3 doses.\n";
static const char MUTA_FLOWER_NAME[] = "Muta-Flower";
static const char MUTA_FOLIAGE_TITLE[] = "Muta-Foliage\n";
static const char MUTA_FOLIAGE_DESC[] = "Mutates the leafy parts of plants.\nContains 3 doses.\n";
static const char MUTA_FOLIAGE_NAME[] = "Muta-Foliage";

typedef struct muta_item {
    int id, x;
    const char *title;
    RECT rect;
} muta_item;

static const muta_item MUTA_ITEM[2] = {
    { MUTA_FLOWER_ID, MUTA_FLOWER_X, MUTA_FLOWER_TITLE, { MUTA_FLOWER_X + 12, MUTA_Y + 8, MUTA_FLOWER_X + 57, MUTA_Y + 60 } },
    { MUTA_FOLIAGE_ID, MUTA_FOLIAGE_X, MUTA_FOLIAGE_TITLE, { MUTA_FOLIAGE_X + 12, MUTA_Y + 8, MUTA_FOLIAGE_X + 57, MUTA_Y + 60 } },
};

static char *muta_tip[2];
static char muta_tip_text[2][64];

static int is_muta(int id) { return id == MUTA_FLOWER_ID || id == MUTA_FOLIAGE_ID; }

/* ------------------------------------------------------------ the dose */

static const DWORD k_muta_flower = 0x0042FAB2u;       /* 0x42FA80's flower branch */
static const DWORD k_muta_foliage = 0x0042FAF5u;      /* its foliage branch */

/* cdecl (plants, row, column, foliage): one branch of 0x42FA80, as a call of it would run it.
   The function's prologue (0x42FA80-0x42FAA6) is rebuilt here instruction for instruction --
   its local, ebx, esi, edi saved; edi the plant table, ebx row x 5 + column, esi the pot
   ([edi] + 0x2188 + ebx x 0x5600) -- then the branch runs to its own `ret 8`. */
__declspec(naked) static void muta_branch(void) {
    __asm {
        push ebp
        push ebx
        push esi
        push edi
        mov edi, [esp + 0x14]
        mov ebx, [esp + 0x18]
        mov ecx, [esp + 0x1C]
        mov edx, [esp + 0x20]
        push ecx                          /* the call's arguments: row, column */
        push ebx
        call prologue
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret
    prologue:
        push ecx                          /* the function's local */
        push ebx
        push esi
        push edi
        lea eax, [ecx + ebx * 4]          /* column + row x 4 */
        add ebx, eax                      /* row x 5 + column */
        mov eax, [edi]
        mov ecx, ebx
        imul ecx, ecx, 0x5600
        lea esi, [ecx + eax + 0x2188]
        test edx, edx
        jnz foliage
        jmp dword ptr [k_muta_flower]
    foliage:
        jmp dword ptr [k_muta_foliage]
    }
}

typedef void (__cdecl *muta_branch_fn)(void *plants, int row, int col, int foliage);

static void __cdecl apply_muta(char *greenhouse, int col, int row, int id) {
    void *plants = AT(greenhouse, 0x70, void *);
    if (plants == NULL) return;
    ((muta_branch_fn)(UINT_PTR)muta_branch)(plants, row, col, id == MUTA_FOLIAGE_ID);
}

/* ------------------------------------------------------------ the store */

static void muta_tip_set(int i) {
    sprintf_s(muta_tip_text[i], 64, "%sPrice: $ %i", MUTA_ITEM[i].title, price(MUTA_PRICE));
}

__declspec(noinline) static void muta_make_tips(char *scene) {
    int i;
    for (i = 0; i < 2; ++i) {
        char *tip;
        if (muta_tip[i] != NULL) continue;
        tip = (char *)game_new(0x10);
        if (tip == NULL) return;
        muta_tip_set(i);
        tooltip_ctor(tip, 0, 96 + i, &MUTA_ITEM[i].rect, scene, muta_tip_text[i], TOOLTIP_FONT, 0, 0);
        add_control(scene, 0, tip);
        muta_tip[i] = tip;
    }
}

__declspec(noinline) static void muta_set_tips(int shown) {
    int i;
    for (i = 0; i < 2; ++i) {
        if (muta_tip[i] == NULL) continue;
        muta_tip_set(i);
        tooltip_text(muta_tip[i], 0, muta_tip_text[i], TOOLTIP_COLOUR, 0, 0);
        AT(muta_tip[i], 8, unsigned char) = (unsigned char)shown;
    }
}

static void muta_draw(void *mgr) {
    int i;
    for (i = 0; i < 2; ++i) {
        draw_shadow(mgr, 0, SHEET_SHADOW, MUTA_ITEM[i].x + 0x19, MUTA_Y + 0x1E, 1.0f, 100);
        draw_sprite(mgr, 0, SHEET_CHEMICALS, 2 * MUTA_ITEM[i].id - 54, MUTA_ITEM[i].x, MUTA_Y, 1.0f, 100, 1);
    }
}

static void open_dialog(char *scene, int index);

static void muta_click(char *scene, int x, int y) {
    int i;
    for (i = 0; i < 2; ++i) {
        if (inside(&MUTA_ITEM[i].rect, x, y)) open_dialog(scene, MUTA_ITEM[i].id);
    }
}
