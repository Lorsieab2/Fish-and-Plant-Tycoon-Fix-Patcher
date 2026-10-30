/* The Auto-Feeder and the Auto-Healer -- two permanent items on the DS Store
   Items Upgrades page (included by ftfp_ds_store.c, before buy()).

   WHAT.  Each costs $10,000 ($0 with Free upgrades), bought once with the
   page's Buy and the game's own purchase question, and works on every live
   fish in every tank: Tank 1, Tank 2, the Sale Tank, the isolation tank, and
   with "3 extra tanks" Tanks 4-6 (on screen or not), every record the update
   reaches (21, or 30 with "Bigger tanks"):
     * the Auto-Feeder keeps each fish's food at FEED_LEVEL;
     * the Auto-Healer cures each fish's sickness and keeps its health at 100.
       A dead fish (health 0) is never touched: that is the Revival Potion's
       job.

   THE GAME'S RULES (the fish update 0x41FE70; its step loop 0x420468-0x420687
   runs once per age step, every step of a catch-up or a Time Warp one by one,
   for each live fish whose health is above 0 (0x42042E), never the seahorse-
   type animals (0x42043F); the update runs tanks 0-3, and Extra Tanks.dll runs
   it again over Tanks 4-6):
     * food is the record's +0x44, 0-100 (clamped at 0x420603).  Each step it
       drops by 1 (Fish Food research L1), 1 on 61% (L2) or 1 on 31% (L3)
       (0x420500-0x420558).  At 2 or less the fish starves: food 0 and -1 health
       a step (0x42055E-0x42058F; the Speckled Leaffish stops the health loss,
       the Plant of Incubation gives +5 on 21%).  Below 5, the step's health
       gain is lost (the health tick 0x41DF50);
     * feeding (0x412160, the food the player drops) gives every live fish in
       the view +50; one whose food would pass 100 is set to 100 and loses 2
       health (overfeeding, 0x4121CB-0x412237; the seahorse is spared), which
       can kill it.  That is the only harm food does: the game keeps no water
       quality or pollution, and the falling food is only drawn;
     * so the Auto-Feeder keeps food at 50: never 5 or less (no lost health
       gain, no starvation), and a feeding by hand on top of it reaches 100 at
       most, never more (no overfeeding).  It writes the field, as a feeding
       would, without the feeding's +50, so it can never overfeed;
     * sickness is +0x40 (1 fungus, 2 ick), rolled each step for adults
       (0x41E120); a sick fish gains no health and loses 1 more a step (0x41DF50),
       loses its pregnancy (0x4204EE), spreads its sickness (+6 to the odds of
       each other fish in its tank), and sells less easily.  The medicines clear
       +0x40 and count one Fish Cured (state + 0x34, 0x420D1D);
     * health is +0x3C, 0-100 (clamped at 0x4205DF); at 0 the fish dies (the
       death test 0x420622) and the update skips it from then on.
   The hook runs in each step right after the sickness roll, before the
   sickness can cost a pregnancy and before the food drops: the Auto-Healer
   clears +0x40 (one Fish Cured each, as the medicines count) and sets health
   100; the Auto-Feeder sets food 50.  At the step's death test the Auto-Healer
   sets health 100 again (only a fish whose health is above 0 there: one at 0
   is dying, and is left to die).  On a purchase every live fish of every
   tank gets the same at once.

   OWNED.  Per save slot, "<save folder>\Fish Tycoon Fix Patcher Data\Auto
   Upgrades <slot>.dat", written whenever the game saves that slot (before
   its own file), atomically (a .tmp file renamed over the old one); a new
   game owns neither; an unreadable file is set aside (".unreadable") and owns
   neither. */

#define AUTO_FEEDER 0
#define AUTO_HEALER 1
#define FEED_LEVEL 50                       /* + a feeding's 50 = 100, never more: no overfeeding */

static volatile unsigned char auto_owned[2];

static int auto_sold_out(int fin) {
    return fin == FIN_FEEDER ? auto_owned[AUTO_FEEDER] : fin == FIN_HEALER ? auto_owned[AUTO_HEALER] : 0;
}

/* One fish: food, sickness, health.  Never a dead one, never a store animal or the seahorse. */
__declspec(noinline) static void auto_tend(char *state, char *f) {
    if (*I(f, F_LIVE) == 0 || *I(f, F_HEALTH) <= 0 || is_animal(f) || *I(f, F_BODY) == BODY_SEAHORSE) return;
    if (auto_owned[AUTO_FEEDER]) *I(f, F_FOOD) = FEED_LEVEL;
    if (auto_owned[AUTO_HEALER]) {
        if (*I(f, F_DISEASE) != 0) {
            *I(f, F_DISEASE) = 0;
            if (state != NULL) ++*I(state, S_CURED);
        }
        *I(f, F_HEALTH) = FULL_METER;
    }
}

/* In each fish's age step, after its sickness roll (edi + [esi + 0x34] + 0x390 is the record). */
static void __cdecl auto_step(char *state, char *f) {
    if (auto_owned[AUTO_FEEDER] || auto_owned[AUTO_HEALER]) auto_tend(state, f);
}

/* At the step's death test, after the clamps: full health again for a fish that is not dying. */
static void __cdecl auto_step_end(char *f) {
    if (auto_owned[AUTO_HEALER] && *I(f, F_HEALTH) > 0 && !is_animal(f) && *I(f, F_BODY) != BODY_SEAHORSE)
        *I(f, F_HEALTH) = FULL_METER;
}

/* At once on a purchase: tanks 0-3 (and the 30 records with Bigger tanks) and the tanks Extra Tanks.dll holds. */
__declspec(noinline) static void auto_tend_all(char *state) {
    int tank, s, e, slots = fish_slots();
    for (tank = 0; tank <= last_tank(); ++tank) {
        for (s = 0; s < slots; ++s) auto_tend(state, fish(state, tank, s));
    }
    for (e = 0; e < HELD_TANKS; ++e) {
        unsigned char *b = held_block(e);
        if (b == NULL) break;
        for (s = 0; s < slots; ++s) auto_tend(state, (char *)b + s * SLOT_STRIDE);
    }
}

/* Buy: "You already own this!" (sold_out, in buy()), the price, the game's purchase question. */
__declspec(noinline) static void auto_buy(char *impl, char *state, int fin, int price) {
    int k = fin == FIN_FEEDER ? AUTO_FEEDER : AUTO_HEALER;
    if (auto_owned[k] || !confirm(impl, 0xEC)) return;
    charge(state, price);
    auto_owned[k] = 1;
    auto_tend_all(state);
}

/* Unpurchase (the owner, 2026-10-30): a click on an owned item that is already selected asks,
   with a Yes / No popup as the Time Warp's; Yes switches it off at once (no refund; buying it
   again costs the full price).  Nothing it did is undone: it only stops acting.  The sidecar
   keeps the new state with the next save, as it keeps a purchase. */
__declspec(noinline) static int auto_unpurchase(int item) {
    const store_item *it = &ITEM[item];
    int k, lang = german();
    wchar_t caption[64], text[300];
    if (it->fin != FIN_FEEDER && it->fin != FIN_HEALER) return 0;
    if (!auto_sold_out(it->fin)) return 0;
    for (k = 0; it->name[lang][k] != 0 && k < 63; ++k) caption[k] = (wchar_t)(unsigned char)it->name[lang][k];
    caption[k] = 0;
    if (lang) {
        wcscpy_s(text, 300, caption);
        wcscat_s(text, 300, L" zur\xFC" L"ckgeben? Er schaltet sich ab. Es gibt kein Geld zur\xFC" L"ck, und ein "
                 L"neuer Kauf kostet den vollen Preis.");
    } else {
        wcscpy_s(text, 300, L"Unpurchase ");
        wcscat_s(text, 300, caption);
        wcscat_s(text, 300, L"? It switches off. There is no refund, and buying it again costs the full price.");
    }
    if (tw_confirm_as(caption, text)) auto_owned[it->fin == FIN_FEEDER ? AUTO_FEEDER : AUTO_HEALER] = 0;
    return 1;
}

/* The panel's last line for an owned machine, in place of "This is in your inventory.". */
static const char *auto_owned_line(int item) {
    int fin = ITEM[item].fin;
    if ((fin != FIN_FEEDER && fin != FIN_HEALER) || !auto_sold_out(fin)) return NULL;
    return german() ? "Gekauft. Zum Zur\xFC" "ckgeben noch einmal anklicken." : "Owned. Click it again to unpurchase.";
}

/* ----------------------------------------------------------------- sidecar */

#define AUTO_MAGIC 0x55415446u              /* "FTAU" */
#define AUTO_VERSION 1u

/* "<Documents>\LDW\<exe name>\Fish Tycoon Fix Patcher Data\Auto Upgrades <slot>.dat". */
static int auto_path(int slot, wchar_t *out, DWORD cap, int make_folder) {
    wchar_t exe[MAX_PATH];
    wchar_t *name, *dot;
    typedef BOOL (WINAPI *special_fn)(HWND, LPWSTR, int, BOOL);
    special_fn special;
    HMODULE shell = GetModuleHandleW(L"shell32.dll");
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
    wchar_t digits[12];
    int d = 0;
    unsigned int v = (unsigned int)slot;
    if (shell == NULL) shell = LoadLibraryW(L"shell32.dll");
    if (shell == NULL || n == 0 || n >= MAX_PATH) return 0;
    special = (special_fn)GetProcAddress(shell, "SHGetSpecialFolderPathW");
    if (special == NULL || !special(NULL, out, 0x0005 /* CSIDL_PERSONAL */, FALSE)) return 0;
    name = wcsrchr(exe, L'\\');
    name = name ? name + 1 : exe;
    dot = wcsrchr(name, L'.');
    if (dot) *dot = L'\0';
    if (wcslen(out) + wcslen(name) + 96 >= cap) return 0;
    wcscat_s(out, cap, L"\\LDW\\");
    wcscat_s(out, cap, name);
    wcscat_s(out, cap, L"\\Fish Tycoon Fix Patcher Data");
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\Auto Upgrades ");
    do { digits[d++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && d < 11);
    while (d) { size_t len = wcslen(out); out[len] = digits[--d]; out[len + 1] = L'\0'; }
    wcscat_s(out, cap, L".dat");
    return 1;
}

__declspec(noinline) static void auto_save(int slot) {
    wchar_t path[1024], temp[1100];
    HANDLE file;
    DWORD body[4], written = 0;
    int ok;
    if (!auto_path(slot, path, 1024, 1)) return;
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    body[0] = AUTO_MAGIC;
    body[1] = AUTO_VERSION;
    body[2] = auto_owned[AUTO_FEEDER];
    body[3] = auto_owned[AUTO_HEALER];
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    ok = WriteFile(file, body, sizeof body, &written, NULL) && written == sizeof body && FlushFileBuffers(file);
    CloseHandle(file);
    if (ok) MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    else DeleteFileW(temp);
}

__declspec(noinline) static void auto_load(int slot) {
    wchar_t path[1024];
    HANDLE file;
    DWORD body[4], got = 0, extra = 0;
    unsigned char probe;
    int ok;
    auto_owned[AUTO_FEEDER] = auto_owned[AUTO_HEALER] = 0;
    if (!auto_path(slot, path, 1024, 0)) return;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;                    /* a save from before: owns neither */
    ok = ReadFile(file, body, sizeof body, &got, NULL) && got == sizeof body
         && ReadFile(file, &probe, 1, &extra, NULL) && extra == 0
         && body[0] == AUTO_MAGIC && body[1] == AUTO_VERSION && body[2] <= 1 && body[3] <= 1;
    CloseHandle(file);
    if (ok) {
        auto_owned[AUTO_FEEDER] = (unsigned char)body[2];
        auto_owned[AUTO_HEALER] = (unsigned char)body[3];
    } else {
        wchar_t aside[1100];
        wcscpy_s(aside, 1100, path);
        wcscat_s(aside, 1100, L".unreadable");
        MoveFileExW(path, aside, MOVEFILE_REPLACE_EXISTING);
    }
}

__declspec(noinline) static void auto_new_game(void) { auto_owned[AUTO_FEEDER] = auto_owned[AUTO_HEALER] = 0; }

/* ------------------------------------------------------------------- stubs */

static const DWORD k_auto_step_back = SITE_AUTO_STEP_VA + SITE_AUTO_STEP_LEN;

/* 0x4204B3, in the step loop after the sickness roll: esi = the tank screen, edi = the record's
   offset in the state (+ 0x390), ebx = 0. */
__declspec(naked) static void stub_auto_step(void) {
    __asm {
        pushad
        mov eax, [esi + 0x34]
        lea ecx, [edi + eax + 0x390]
        push ecx
        push eax
        call auto_step
        add esp, 8
        popad
        mov edx, [esi + 0x34]
        cmp dword ptr [edi + edx + 0x3D0], ebx
        jmp k_auto_step_back
    }
}
