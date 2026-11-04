/* No C Cheat (Fish Tycoon) -- "Disable Press C for Cash Cheat".

   Stock, the tank screen's key handler (0x41ED10) tests the typed character:

     0041ED71  sub eax,0x63        ; 'c'
     0041ED74  je 0x41EDA6         ; (74 30) -> adds 1000 to the money at state+0x38C
     0041ED76  sub eax,0x12        ; 'u' ...

   The one byte at 0x41ED75 (the jump distance 0x30) becomes 0x40, so the 'c' case jumps to
   0x41EDB6, the handler's plain "return false" exit, and adds nothing. 'u' and 'w' are untouched.

   The byte holds its stock value, or nothing is written (../ftfp_ds_fish/install_sites.h).
   The result is in "Fish Tycoon Fix Patcher DLLs\No C Cheat.log". */

#include <windows.h>
#include <string.h>
#include <wchar.h>
#define FTFP_SITE_MAX_BYTES 8
#include "../ftfp_ds_fish/install_sites.h"

#define CHEAT_SITE_VA 0x0041ED75u
#define CHEAT_SITE_LEN 1

extern IMAGE_DOS_HEADER __ImageBase;

static const unsigned char STOCK[CHEAT_SITE_LEN] = {0x30};

static int installed = 0;

static void build(ftfp_site_write *w) {
    w->bytes[0] = 0x40;
    w->va = CHEAT_SITE_VA;
    w->length = CHEAT_SITE_LEN;
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
    wcscat_s(path, 1024, L"No C Cheat.log");
    if (installed) {
        len = append_text(line, len, "No C Cheat: installed\r\n");
    } else {
        len = append_text(line, len, "No C Cheat: not installed (0x0041ED75 is not the stock code)\r\n");
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
int __stdcall FtfpNoCCheatInstalled(void) { return installed; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
