/* A patcher setting that only changes what a store DLL does ships a small
   ".ini" file beside that DLL; the DLL checks for it once at start-up.
   Shared by the Fish and Plant Tycoon store DLLs (Time Warp, Free upgrades,
   Add Money). */
#ifndef FTFP_SETTING_FILE_H
#define FTFP_SETTING_FILE_H

#include <windows.h>
#include <wchar.h>

/* "<folder of this DLL>\<name>" exists: that setting is on. */
static int ftfp_setting_on(HMODULE self, const wchar_t *name) {
    wchar_t path[1024];
    wchar_t *slash;
    DWORD n = GetModuleFileNameW(self, path, 1024);
    if (n == 0 || n >= 1024 || (slash = wcsrchr(path, L'\\')) == NULL) return 0;
    slash[1] = L'\0';
    if (wcslen(path) + wcslen(name) + 1 >= 1024) return 0;
    wcscat_s(path, 1024, name);
    return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}

/* "Everything is Free" ships "Everything Free.ini" beside the DLLs: every
   price the player pays is $0.  The stock store's own charges are byte
   patches in the executable (scripts/pin_everything_free.py); a DLL that
   sells something itself checks ftfp_everything_free() once at start-up
   and then charges, shows and requires $0.  It implies Free upgrades. */
#define FTFP_EVERYTHING_FREE_FILE L"Everything Free.ini"
#define ftfp_everything_free(self) ftfp_setting_on((self), FTFP_EVERYTHING_FREE_FILE)

#endif
