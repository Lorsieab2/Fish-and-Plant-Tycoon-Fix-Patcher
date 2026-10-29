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

#endif
