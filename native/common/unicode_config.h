/* unicode_config.h -- "Unicode Text.dll", both games: which of its two settings it runs as.

   One DLL serves both settings; the patcher writes "Unicode Text.ini" beside it
   (src/fish_patcher.py, unicode_ini) for whichever is on:

       Mode=ingame        Render Unicode with In-Game Fonts (also with no file at all)
       Mode=system        Use Unicode Font (overrides in-game fonts)
       Font=<name>        the font chosen in the patcher (UTF-8), first in the chain

   With Mode=system every letter of the game's text is drawn with that font and the chain
   after it (unicode_glyphs.h, system_font), at the game fonts' line heights and in the
   game's colours; the game's fonts are not pointed at their extended pictures, which that
   setting does not ship. */
#ifndef FTFP_UNICODE_CONFIG_H
#define FTFP_UNICODE_CONFIG_H

/* The value after `key=` at the start of a line in `data`, copied to `out` (UTF-8), or 0. */
static int ini_value(const char *data, const char *key, char *out, int cap) {
    const char *line = data;
    int klen = s_len(key);
    while (*line) {
        int i;
        for (i = 0; i < klen && line[i] && (line[i] | 0x20) == (key[i] | 0x20); ++i) {}
        if (i == klen && line[i] == '=') {
            int n = 0;
            line += klen + 1;
            while (*line && *line != '\r' && *line != '\n' && n < cap - 1) out[n++] = *line++;
            while (n > 0 && out[n - 1] == ' ') --n;
            out[n] = '\0';
            return 1;
        }
        while (*line && *line != '\n') ++line;
        if (*line) ++line;
    }
    return 0;
}

/* Read "<folder>Unicode Text.ini" (folder ends in a backslash). */
static void read_unicode_config(const wchar_t *folder) {
    wchar_t path[1024];
    char data[1024], value[256];
    DWORD got = 0;
    HANDLE file;
    if (wcslen(folder) + 20 >= 1024) return;
    wcscpy_s(path, 1024, folder);
    wcscat_s(path, 1024, L"Unicode Text.ini");
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    if (!ReadFile(file, data, (DWORD)sizeof data - 1, &got, NULL)) got = 0;
    CloseHandle(file);
    data[got] = '\0';
    if (ini_value(data, "Mode", value, sizeof value)) {
        system_font = (value[0] | 0x20) == 's';
    }
    if (ini_value(data, "Font", value, sizeof value) && value[0]) {
        const unsigned char *p = (const unsigned char *)value;
        int n = 0;
        while (*p && n < 63) {
            unsigned int cp = utf8_next(&p);
            if (cp >= 0x10000) continue;
            chosen_font[n++] = (wchar_t)cp;
        }
        chosen_font[n] = L'\0';
    }
}

#endif
