/* chem_slots_file.h -- the Extra Chemical Slots file of one save slot.

   "<Documents>\LDW\<exe name>\Plant Tycoon Fix Patcher Data\Extra Chemical Slots <slot>.dat":
   five 32-bit words (magic "PTCS", version 1, bought 0/1, records 8, record
   bytes 12), then page 2's eight records in the stock tray layout (present
   byte and three pad bytes, chemical id, doses).  It is written to a .tmp
   file that is moved over the old one, so it is never half-written; a file
   that cannot be read is set aside as "... .dat.unreadable-<n>", never
   deleted.

   Shared by "Extra Chemical Slots.dll" (the setting on) and "Store Upgrades
   and Items.dll" (which puts page 2 back in the stock tray when the setting
   is off). */
#ifndef FTFP_CHEM_SLOTS_FILE_H
#define FTFP_CHEM_SLOTS_FILE_H

#include <windows.h>
#include <wchar.h>
#include <string.h>

#define CHEM_PAGE_SLOTS 8
#define CHEM_RECORD_BYTES 12
#define CHEM_FILE_MAGIC 0x53435450u        /* "PTCS" */
#define CHEM_FILE_VERSION 1u
#define CHEM_FILE_WORDS 5

typedef struct chem_record {
    unsigned char present;
    unsigned char pad[3];
    int id;
    int doses;
} chem_record;

typedef BOOL (WINAPI *chem_special_folder_fn)(HWND, LPWSTR, int, BOOL);

static int chem_file_path(int slot, wchar_t *out, DWORD cap, int make_folder) {
    wchar_t exe[MAX_PATH];
    wchar_t *name, *dot;
    chem_special_folder_fn special;
    HMODULE shell = LoadLibraryW(L"shell32.dll");
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
    if (slot <= 0 || shell == NULL || n == 0 || n >= MAX_PATH) return 0;
    special = (chem_special_folder_fn)GetProcAddress(shell, "SHGetSpecialFolderPathW");
    if (special == NULL || !special(NULL, out, 0x0005 /* CSIDL_PERSONAL */, FALSE)) return 0;
    name = wcsrchr(exe, L'\\');
    name = name ? name + 1 : exe;
    dot = wcsrchr(name, L'.');
    if (dot) *dot = L'\0';
    if (wcslen(out) + wcslen(name) + 100 >= cap) return 0;
    wcscat_s(out, cap, L"\\LDW\\");
    wcscat_s(out, cap, name);
    wcscat_s(out, cap, L"\\Plant Tycoon Fix Patcher Data");
    if (make_folder) CreateDirectoryW(out, NULL);
    wcscat_s(out, cap, L"\\Extra Chemical Slots ");
    {
        wchar_t digits[12];
        int i = 0, v = slot;
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 11);
        while (i) { size_t len = wcslen(out); out[len] = digits[--i]; out[len + 1] = L'\0'; }
    }
    wcscat_s(out, cap, L".dat");
    return 1;
}

/* A record as the stock tray keeps it: an empty slot is all zero. */
/* A chemical the game can hold: the stock 27-35, Store Upgrades and Items' 36-39 and its Muta-Flower
   and Muta-Foliage, 48 and 49 (their sheet rows 21 and 22; 40-47 are rows of other pictures). */
static __inline int chem_id_valid(int id) {
    return (id >= 27 && id <= 39) || id == 48 || id == 49;
}

static void chem_record_clean(chem_record *r) {
    if (!r->present || r->doses <= 0) memset(r, 0, sizeof *r);
    else { r->present = 1; r->pad[0] = r->pad[1] = r->pad[2] = 0; }
}

static int chem_file_write(int slot, int owned, const chem_record *page) {
    wchar_t path[1024], temp[1100];
    DWORD header[CHEM_FILE_WORDS], written;
    HANDLE file;
    int ok;
    if (!chem_file_path(slot, path, 1024, 1)) return 0;
    wcscpy_s(temp, 1100, path);
    wcscat_s(temp, 1100, L".tmp");
    file = CreateFileW(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    header[0] = CHEM_FILE_MAGIC;
    header[1] = CHEM_FILE_VERSION;
    header[2] = owned ? 1u : 0u;
    header[3] = CHEM_PAGE_SLOTS;
    header[4] = CHEM_RECORD_BYTES;
    ok = WriteFile(file, header, sizeof header, &written, NULL) && written == sizeof header
         && WriteFile(file, page, CHEM_PAGE_SLOTS * CHEM_RECORD_BYTES, &written, NULL)
         && written == CHEM_PAGE_SLOTS * CHEM_RECORD_BYTES
         && FlushFileBuffers(file);
    CloseHandle(file);
    if (ok) ok = MoveFileExW(temp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
    if (!ok) DeleteFileW(temp);
    return ok;
}

/* The unreadable file goes to the first free "<path>.unreadable-<n>". */
static void chem_file_set_aside(const wchar_t *path) {
    wchar_t aside[1100];
    int n;
    for (n = 1; n < 1000; ++n) {
        size_t len;
        int v = n, i = 0;
        wchar_t digits[8];
        wcscpy_s(aside, 1100, path);
        wcscat_s(aside, 1100, L".unreadable-");
        do { digits[i++] = (wchar_t)(L'0' + v % 10); v /= 10; } while (v && i < 7);
        len = wcslen(aside);
        while (i) { aside[len++] = digits[--i]; }
        aside[len] = L'\0';
        if (MoveFileExW(path, aside, 0)) return;
        if (GetLastError() != ERROR_ALREADY_EXISTS && GetLastError() != ERROR_FILE_EXISTS) return;
    }
}

/* 1 read, 0 no file (nothing bought, page 2 empty), -1 unreadable (set aside; the same as no file). */
static int chem_file_read(int slot, int *owned, chem_record *page) {
    wchar_t path[1024];
    DWORD header[CHEM_FILE_WORDS], got;
    LARGE_INTEGER size;
    chem_record body[CHEM_PAGE_SLOTS];
    HANDLE file;
    int ok, i;
    *owned = 0;
    memset(page, 0, CHEM_PAGE_SLOTS * sizeof *page);
    if (!chem_file_path(slot, path, 1024, 0)) return 0;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    ok = GetFileSizeEx(file, &size) && size.QuadPart == (LONGLONG)(sizeof header + sizeof body)
         && ReadFile(file, header, sizeof header, &got, NULL) && got == sizeof header
         && header[0] == CHEM_FILE_MAGIC && header[1] == CHEM_FILE_VERSION && header[2] <= 1u
         && header[3] == CHEM_PAGE_SLOTS && header[4] == CHEM_RECORD_BYTES
         && ReadFile(file, body, sizeof body, &got, NULL) && got == sizeof body;
    CloseHandle(file);
    for (i = 0; ok && i < CHEM_PAGE_SLOTS; ++i) {          /* a bottle is one of the game's 15 chemicals */
        if (body[i].present && body[i].doses > 0 && !chem_id_valid(body[i].id)) ok = 0;
    }
    if (!ok) {
        chem_file_set_aside(path);
        return -1;
    }
    *owned = (int)header[2];
    for (i = 0; i < CHEM_PAGE_SLOTS; ++i) {
        page[i] = body[i];
        chem_record_clean(&page[i]);
    }
    return 1;
}

static void chem_file_delete(int slot) {
    wchar_t path[1024];
    if (chem_file_path(slot, path, 1024, 0)) DeleteFileW(path);
}

#endif /* FTFP_CHEM_SLOTS_FILE_H */
