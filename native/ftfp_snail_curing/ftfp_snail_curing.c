/* Snail and Curing (Fish Tycoon) -- "Snail and Plant of Curing stack".

   Stock, the sickness tick (0x41E120) halves a fish's sickness odds X once at most: the
   Plant of Curing (+0x190 of the game state, edi) halves it always, and only without the
   plant does the Cleaning Snail (+0x140) halve it when Random(100) <= 49 (0x41E21C):

     cmp [edi+0x190],0 / jne halve / cmp [edi+0x140],0 / je skip /
     push 0x64 / call Random(0x403240) / add esp,4 / cmp eax,0x31 / jg skip /
     halve: mov eax,esi / cdq / sub eax,edx / sar eax,1 / mov esi,eax

   Here the two are separate: the plant halves X, then the snail halves it again when its
   roll is <= 49. These 42 bytes (up to 0x41E246, where the stock code goes on with
   mov eax,[ebx+0x34]) are rewritten:

     cmp [edi+0x190],0 / je +2 / sar esi,1 /
     cmp [edi+0x140],0 / je skip / push 0x64 / call Random / pop ecx /
     cmp eax,0x31 / jg skip / sar esi,1 / nop x7

   "sar esi,1" is the stock halving (cdq / sub / sar) for X >= 0, and X is always 0 or more
   here (it is set from the constants 2, 5, 20, 30 and so on); the longer form would not fit.
   The halving comes before the +6 per other sick fish and the +15 / +30 for age, which are
   never halved. ecx and edx are free here (the stock Random call clobbers them).

   All 42 bytes hold their stock code, or nothing is written (../ftfp_ds_fish/install_sites.h).
   The result is in "Fish Tycoon Fix Patcher DLLs\Snail and Curing.log". */

#include <windows.h>
#include <string.h>
#include <wchar.h>
#define FTFP_SITE_MAX_BYTES 48   /* the site is 42 bytes */
#include "../ftfp_ds_fish/install_sites.h"

#define CURING_SITE_VA 0x0041E21Cu
#define CURING_SITE_LEN 42
#define RANDOM_VA 0x00403240u

extern IMAGE_DOS_HEADER __ImageBase;

static const unsigned char STOCK[CURING_SITE_LEN] = {
    0x83, 0xBF, 0x90, 0x01, 0x00, 0x00, 0x00, 0x75, 0x18, 0x83, 0xBF, 0x40, 0x01, 0x00, 0x00, 0x00,
    0x74, 0x18, 0x6A, 0x64, 0xE8, 0x0B, 0x50, 0xFE, 0xFF, 0x83, 0xC4, 0x04, 0x83, 0xF8, 0x31, 0x7F,
    0x09, 0x8B, 0xC6, 0x99, 0x2B, 0xC2, 0xD1, 0xF8, 0x8B, 0xF0};

static int installed = 0;

static void build(ftfp_site_write *w) {
    unsigned char *b = w->bytes;
    unsigned int rel = RANDOM_VA - (CURING_SITE_VA + 27u);
    static const unsigned char head[] = {
        0x83, 0xBF, 0x90, 0x01, 0x00, 0x00, 0x00,   /* 0  cmp dword ptr [edi+0x190],0 */
        0x74, 0x02,                                 /* 7  je +2 */
        0xD1, 0xFE,                                 /* 9  sar esi,1 */
        0x83, 0xBF, 0x40, 0x01, 0x00, 0x00, 0x00,   /* 11 cmp dword ptr [edi+0x140],0 */
        0x74, 0x0F,                                 /* 18 je 35 */
        0x6A, 0x64,                                 /* 20 push 0x64 */
        0xE8};                                      /* 22 call Random */
    static const unsigned char tail[] = {
        0x59,                                       /* 27 pop ecx */
        0x83, 0xF8, 0x31,                           /* 28 cmp eax,0x31 */
        0x7F, 0x02,                                 /* 31 jg 35 */
        0xD1, 0xFE};                                /* 33 sar esi,1 */
    memset(b, 0x90, CURING_SITE_LEN);
    memcpy(b, head, sizeof head);
    memcpy(b + 23, &rel, 4);
    memcpy(b + 27, tail, sizeof tail);
    w->va = CURING_SITE_VA;
    w->length = CURING_SITE_LEN;
    w->expect = STOCK;
}

static int append_text(char *out, int at, const char *s) {
    while (*s && at < 158) out[at++] = *s++;
    return at;
}

static void write_install_log(void) {
    wchar_t path[1024];
    char line[160];
    DWORD n = GetModuleFileNameW((HMODULE)&__ImageBase, path, 1024), written;
    wchar_t *slash;
    HANDLE file;
    int len = 0;
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return;
    slash[1] = L'\0';
    if (wcslen(path) + 32 >= 1024) return;
    wcscat_s(path, 1024, L"Snail and Curing.log");
    if (installed) {
        len = append_text(line, len, "Snail and Curing: installed\r\n");
    } else {
        len = append_text(line, len, "Snail and Curing: not installed (0x0041E21C is not the stock code)\r\n");
    }
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, line, (DWORD)len, &written, NULL);
    CloseHandle(file);
}

/* Called once by the executable's startup loader, before WinMain. */
int __stdcall FtfpStartup(void) {
    ftfp_site_write w;
    if (installed) return 1;
    __try {
        memset(&w, 0, sizeof w);
        build(&w);
        installed = ftfp_install_sites(&w, 1);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        installed = 0;
    }
    write_install_log();
    return installed;
}

/* For the patcher's tests. */
int __stdcall FtfpSnailCuringInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
