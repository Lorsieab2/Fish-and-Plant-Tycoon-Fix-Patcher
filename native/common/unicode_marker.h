/* unicode_marker.h -- "Unicode Text.dll" tells the patcher's tools that this copy of the game
   types and draws Latin-1 names.

   Once installed, the DLL writes "<Documents>\LDW\<exe name>\<Game> Fix Patcher Data\Unicode Text.ini"
   (the save folder the game uses, folders made if missing). The tools (src/save_tools.py,
   unicode_names) accept such names for that save folder only while it is there; the file holds
   one line naming the setting and is never read by the game. Shared by the Fish and Plant
   Tycoon DLLs; FTFP_DATA_FOLDER names the game's data folder. */
#ifndef FTFP_UNICODE_MARKER_H
#define FTFP_UNICODE_MARKER_H

#include <windows.h>
#include <wchar.h>
#include <string.h>

#define FTFP_UNICODE_MARKER L"Unicode Text.ini"

typedef BOOL (WINAPI *unicode_special_folder_fn)(HWND, LPWSTR, int, BOOL);

/* "<Documents>\LDW\<exe name>\<data folder>", each folder made if missing. */
static int unicode_data_folder(const wchar_t *data_folder, wchar_t *out, DWORD cap) {
    wchar_t exe[MAX_PATH];
    wchar_t *name, *dot;
    unicode_special_folder_fn special;
    HMODULE shell = LoadLibraryW(L"shell32.dll");
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
    if (shell == NULL || n == 0 || n >= MAX_PATH) return 0;
    special = (unicode_special_folder_fn)GetProcAddress(shell, "SHGetSpecialFolderPathW");
    if (special == NULL || !special(NULL, out, 0x0005 /* CSIDL_PERSONAL */, FALSE)) return 0;
    name = wcsrchr(exe, L'\\');
    name = name ? name + 1 : exe;
    dot = wcsrchr(name, L'.');
    if (dot) *dot = L'\0';
    if (wcslen(out) + wcslen(name) + wcslen(data_folder) + 40 >= cap) return 0;
    wcscat_s(out, cap, L"\\LDW");
    CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\");
    wcscat_s(out, cap, name);
    CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\");
    wcscat_s(out, cap, data_folder);
    CreateDirectoryW(out, NULL);
    return 1;
}

static void unicode_write_marker(const wchar_t *data_folder) {
    static const char text[] = "Unicode Text: this copy types and draws names in any script (UTF-8).\r\n";
    wchar_t path[1024];
    DWORD written;
    HANDLE file;
    if (!unicode_data_folder(data_folder, path, 1024)) return;
    wcscat_s(path, 1024, L"\\");
    wcscat_s(path, 1024, FTFP_UNICODE_MARKER);
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, text, (DWORD)(sizeof text - 1), &written, NULL);
    CloseHandle(file);
}

#endif
