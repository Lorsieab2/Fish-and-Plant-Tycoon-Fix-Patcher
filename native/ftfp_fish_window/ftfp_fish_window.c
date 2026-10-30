/* Maximizable Window -- Fish Tycoon's window can be maximized and resized in
   windowed mode.

   HOW THE GAME DRAWS.  Fish Tycoon is an SDL 1.2 game (SDL.dll).  SDL makes
   the window; the game asks for its picture with SDL_SetVideoMode (thunk
   0x42A606, jmp [0x440190]) from 0x407CC7 (start), 0x403D27 / 0x403D4B
   (fullscreen switch) and 0x40877C (fullscreen restore), with flags 0
   (windowed) or SDL_FULLSCREEN.  SDL's windowed style has no maximize box or
   sizing border, and SDL's WM_GETMINMAXINFO pins the window to its size
   unless the surface is SDL_RESIZABLE.  Once a frame is drawn the game calls
   SDL_Flip (thunk 0x42A62A, jmp [0x4401C8]) from 0x408736, and SDL copies
   the picture 1:1 into the window.  Mouse input reaches the game only
   through SDL (SDL_PollEvent, SDL_GetMouseState), in two ways: the buttons
   from the window messages' client coordinates, and the pointer's position
   from SDL's own GetCursorPos + ScreenToClient after every batch of
   messages.  The game hides the Windows pointer and draws its own cursor
   at that position (0x408650).

   WHAT THIS DOES.  FtfpStartup() checks both thunks hold their stock bytes,
   both import slots hold SDL.dll's own functions and SDL.dll's import slot
   for ScreenToClient holds USER32's, then points the three slots here --
   all or none.  In windowed mode:
     * after SDL_SetVideoMode the window gets WS_MAXIMIZEBOX and WS_THICKFRAME
       and is sized so its client area is exactly the game's picture again;
     * when the client area is the picture's size, everything goes to SDL
       untouched, exactly as stock;
     * when it is any other size, the picture is drawn scaled to fill it with
       its aspect ratio kept (GDI HALFTONE, a smoothing filter; the game
       itself never scales; nearest pixel instead at a size where smoothing
       would slow the game), black bars where it does not fit, and mouse
       messages and SDL's own pointer reads are both mapped back to the
       picture's coordinates before SDL sees them, so the game's cursor is
       drawn where the click lands.
   Fullscreen is left entirely to SDL.  Sizes are the window's own client
   rectangle in the units the window procedure sees, so Windows display
   scaling needs no special case.  Nothing is saved anywhere. */

#include <windows.h>
#include <windowsx.h>

#pragma comment(lib, "gdi32.lib")

#define SDL_FULLSCREEN 0x80000000u

#define SET_VIDEO_MODE_THUNK 0x0042A606u
#define FLIP_THUNK 0x0042A62Au
#define SET_VIDEO_MODE_SLOT 0x00440190u
#define FLIP_SLOT 0x004401C8u

static const BYTE set_video_mode_thunk[6] = {0xFF, 0x25, 0x90, 0x01, 0x44, 0x00};
static const BYTE flip_thunk[6] = {0xFF, 0x25, 0xC8, 0x01, 0x44, 0x00};

/* SDL 1.2's SDL_PixelFormat, SDL_Surface (leading fields) and SDL_SysWMinfo. */
typedef struct sdl_format {
    void *palette;
    BYTE bits_per_pixel, bytes_per_pixel;
    BYTE rloss, gloss, bloss, aloss, rshift, gshift, bshift, ashift;
    DWORD rmask, gmask, bmask, amask;
} sdl_format;

typedef struct sdl_surface {
    DWORD flags;
    sdl_format *format;
    int w, h;
    WORD pitch;
    void *pixels;
} sdl_surface;

typedef struct sdl_wm_info {
    BYTE major, minor, patch;
    HWND window;
    HGLRC gl_context;
} sdl_wm_info;

typedef sdl_surface *(__cdecl *set_video_mode_fn)(int width, int height, int bpp, DWORD flags);
typedef int (__cdecl *flip_fn)(sdl_surface *surface);
typedef int (__cdecl *lock_fn)(sdl_surface *surface);
typedef void (__cdecl *unlock_fn)(sdl_surface *surface);
typedef int (__cdecl *wm_info_fn)(sdl_wm_info *info);

static set_video_mode_fn sdl_set_video_mode;
static flip_fn sdl_flip;
static lock_fn sdl_lock;
static unlock_fn sdl_unlock;
static wm_info_fn sdl_wm_info_get;

static int installed;
static HWND game_window;
static WNDPROC sdl_window_proc;
static sdl_surface *screen;     /* NULL while SDL is changing the video mode */
static int fullscreen;

/* Where the picture goes in the client area: as large as fits with its
   aspect ratio kept, centred. */
typedef struct fit {
    int x, y, w, h;
} fit;

static fit fit_picture(int client_w, int client_h, int w, int h) {
    fit f;
    if ((__int64)client_w * h <= (__int64)client_h * w) {
        f.w = client_w;
        f.h = (int)((__int64)client_w * h / w);
    } else {
        f.h = client_h;
        f.w = (int)((__int64)client_h * w / h);
    }
    f.x = (client_w - f.w) / 2;
    f.y = (client_h - f.h) / 2;
    return f;
}

/* The picture pixel under client coordinate v (clamped to the picture). */
static int to_picture(int v, int origin, int size, int picture) {
    int p;
    if (v < origin) return 0;
    p = (int)((__int64)(v - origin) * picture / size);
    return p >= picture ? picture - 1 : p;
}

/* The picture's pixels are a format GDI can draw (16, 24 or 32 bits a
   pixel, rows of whole pixels); anything else is left to SDL. */
static int drawable(void) {
    const sdl_format *format = screen->format;
    int bits = format->bits_per_pixel, bytes = format->bytes_per_pixel;
    if (bits != 16 && bits != 24 && bits != 32) return 0;
    if (bits != 24 && (format->rmask == 0 || format->gmask == 0 || format->bmask == 0)) return 0;
    return bytes != 0 && screen->pitch % bytes == 0;
}

/* True when the windowed picture is shown at another size than its own;
   then *f is where it goes and *client the client rectangle. */
static int scaled(fit *f, RECT *client) {
    if (screen == NULL || fullscreen || game_window == NULL) return 0;
    if (!GetClientRect(game_window, client) || client->right <= 0 || client->bottom <= 0) return 0;
    if (client->right == screen->w && client->bottom == screen->h) return 0;
    if (!drawable()) return 0;
    *f = fit_picture(client->right, client->bottom, screen->w, screen->h);
    return f->w > 0 && f->h > 0;
}

static void fill_black(HDC dc, int left, int top, int right, int bottom) {
    RECT r;
    if (right <= left || bottom <= top) return;
    SetRect(&r, left, top, right, bottom);
    FillRect(dc, &r, (HBRUSH)GetStockObject(BLACK_BRUSH));
}

/* The smoothing filter (HALFTONE) costs more the larger the window.  The
   game draws a frame every 33 ms (0x21 at 0x407D25) and counts the time
   SDL_Flip takes against the next one, so at a size where smoothing takes
   over a third of that three frames running, that size is drawn with
   COLORONCOLOR (nearest pixel) instead and the game keeps its speed. */
#define SLOW_DRAW_MS 11
#define SLOW_DRAWS 3

static int slow_w, slow_h, slow_count, sharp_w, sharp_h;

static int stretch_mode(int client_w, int client_h) {
    return client_w == sharp_w && client_h == sharp_h ? COLORONCOLOR : HALFTONE;
}

static void timed_draw(int client_w, int client_h, DWORD elapsed_ms) {
    if (stretch_mode(client_w, client_h) != HALFTONE) return;
    if (elapsed_ms <= SLOW_DRAW_MS) {
        slow_count = 0;
        return;
    }
    if (client_w != slow_w || client_h != slow_h) {
        slow_w = client_w;
        slow_h = client_h;
        slow_count = 0;
    }
    if (++slow_count >= SLOW_DRAWS) {
        sharp_w = client_w;
        sharp_h = client_h;
    }
}

/* Draws the game's picture scaled into dc (the caller checked drawable());
   0 if SDL could not lock it. */
static int paint_scaled(HDC dc, const fit *f, const RECT *client) {
    struct {
        BITMAPINFOHEADER header;
        DWORD masks[3];
    } info;
    const sdl_format *format = screen->format;
    int bytes = format->bytes_per_pixel;
    int mode = stretch_mode(client->right, client->bottom);
    LARGE_INTEGER start, end, frequency;
    ZeroMemory(&info, sizeof(info));
    info.header.biSize = sizeof(BITMAPINFOHEADER);
    info.header.biWidth = screen->pitch / bytes;
    info.header.biHeight = -screen->h;
    info.header.biPlanes = 1;
    info.header.biBitCount = format->bits_per_pixel;
    if (format->bits_per_pixel == 24) {
        info.header.biCompression = BI_RGB;
    } else {
        info.header.biCompression = BI_BITFIELDS;
        info.masks[0] = format->rmask;
        info.masks[1] = format->gmask;
        info.masks[2] = format->bmask;
    }
    if (sdl_lock(screen) != 0) return 0;
    QueryPerformanceCounter(&start);
    fill_black(dc, 0, 0, client->right, f->y);
    fill_black(dc, 0, f->y + f->h, client->right, client->bottom);
    fill_black(dc, 0, f->y, f->x, f->y + f->h);
    fill_black(dc, f->x + f->w, f->y, client->right, f->y + f->h);
    SetStretchBltMode(dc, mode);
    SetBrushOrgEx(dc, 0, 0, NULL);
    StretchDIBits(dc, f->x, f->y, f->w, f->h, 0, 0, screen->w, screen->h, screen->pixels,
                  (const BITMAPINFO *)&info, DIB_RGB_COLORS, SRCCOPY);
    sdl_unlock(screen);
    QueryPerformanceCounter(&end);
    QueryPerformanceFrequency(&frequency);
    timed_draw(client->right, client->bottom, (DWORD)((end.QuadPart - start.QuadPart) * 1000 / frequency.QuadPart));
    return 1;
}

static LPARAM picture_point(LPARAM lparam, const fit *f) {
    int x = to_picture(GET_X_LPARAM(lparam), f->x, f->w, screen->w);
    int y = to_picture(GET_Y_LPARAM(lparam), f->y, f->h, screen->h);
    return MAKELPARAM(x, y);
}

static LRESULT CALLBACK window_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    fit f;
    RECT client;
    if (screen != NULL && !fullscreen) {
        switch (message) {
        case WM_GETMINMAXINFO: {
            /* SDL would pin the window to its current size; keep Windows'
               own maximum and let it shrink to half the picture. */
            MINMAXINFO *info = (MINMAXINFO *)lparam;
            RECT outer;
            if (GetWindowRect(window, &outer) && GetClientRect(window, &client)) {
                info->ptMinTrackSize.x = (outer.right - outer.left) - client.right + screen->w / 2;
                info->ptMinTrackSize.y = (outer.bottom - outer.top) - client.bottom + screen->h / 2;
            }
            return 0;
        }
        case WM_PAINT:
            if (scaled(&f, &client)) {
                PAINTSTRUCT paint;
                HDC dc = BeginPaint(window, &paint);
                int done = dc != NULL && paint_scaled(dc, &f, &client);
                EndPaint(window, &paint);
                if (done) return 0;
            }
            break;
        case WM_MOUSEMOVE:
        case WM_LBUTTONDOWN:
        case WM_LBUTTONUP:
        case WM_RBUTTONDOWN:
        case WM_RBUTTONUP:
        case WM_MBUTTONDOWN:
        case WM_MBUTTONUP:
            if (scaled(&f, &client)) lparam = picture_point(lparam, &f);
            break;
        }
    }
    return CallWindowProcA(sdl_window_proc, window, message, wparam, lparam);
}

/* SDL's own ScreenToClient (its import slot in SDL.dll).  Besides the mouse
   messages, SDL reads the pointer itself: after every batch of messages its
   event pump (DIB_PumpEvents, SDL.dll 0x6812F6C0) calls GetCursorPos and
   ScreenToClient(game window) and moves its mouse there, and so do its
   regain-focus and DirectX paths (0x6812D9A0, 0x68132400).  That position is
   what SDL_GetMouseState returns, where the game draws its own cursor
   (0x408650) and what every hover reads.  Mapped here like the messages, the
   cursor the player sees is where the click lands. */
typedef BOOL (WINAPI *screen_to_client_fn)(HWND window, LPPOINT point);
static screen_to_client_fn user_screen_to_client;

static BOOL WINAPI hook_screen_to_client(HWND window, LPPOINT point) {
    fit f;
    RECT client;
    BOOL ok = user_screen_to_client(window, point);
    if (ok && point != NULL && window == game_window && scaled(&f, &client)) {
        point->x = to_picture(point->x, f.x, f.w, screen->w);
        point->y = to_picture(point->y, f.y, f.h, screen->h);
    }
    return ok;
}

/* SDL.dll's import slot for USER32's ScreenToClient, found by name in its
   import table; NULL unless it holds USER32's own function. */
static void *volatile *screen_to_client_slot(HMODULE sdl) {
    const BYTE *base = (const BYTE *)sdl;
    const IMAGE_DOS_HEADER *dos = (const IMAGE_DOS_HEADER *)base;
    const IMAGE_NT_HEADERS32 *nt;
    const IMAGE_DATA_DIRECTORY *dir;
    const IMAGE_IMPORT_DESCRIPTOR *desc;
    HMODULE user32 = GetModuleHandleA("USER32.dll");
    if (user32 == NULL || dos->e_magic != IMAGE_DOS_SIGNATURE) return NULL;
    user_screen_to_client = (screen_to_client_fn)GetProcAddress(user32, "ScreenToClient");
    if (user_screen_to_client == NULL) return NULL;
    nt = (const IMAGE_NT_HEADERS32 *)(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return NULL;
    dir = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (dir->VirtualAddress == 0) return NULL;
    for (desc = (const IMAGE_IMPORT_DESCRIPTOR *)(base + dir->VirtualAddress); desc->Name != 0; ++desc) {
        const IMAGE_THUNK_DATA32 *names, *slots;
        if (lstrcmpiA((const char *)(base + desc->Name), "USER32.dll") != 0 || desc->OriginalFirstThunk == 0) continue;
        names = (const IMAGE_THUNK_DATA32 *)(base + desc->OriginalFirstThunk);
        slots = (const IMAGE_THUNK_DATA32 *)(base + desc->FirstThunk);
        for (; names->u1.AddressOfData != 0; ++names, ++slots) {
            const IMAGE_IMPORT_BY_NAME *name;
            if (names->u1.Ordinal & IMAGE_ORDINAL_FLAG32) continue;
            name = (const IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData);
            if (lstrcmpA((const char *)name->Name, "ScreenToClient") != 0) continue;
            if (*(void *const volatile *)&slots->u1.Function != (void *)user_screen_to_client) return NULL;
            return (void *volatile *)&slots->u1.Function;
        }
    }
    return NULL;
}

/* Subclasses SDL's window (once per window SDL makes). */
static void attach_window(void) {
    sdl_wm_info info;
    ZeroMemory(&info, sizeof(info));
    info.major = 1;
    info.minor = 2;
    info.patch = 15;
    if (sdl_wm_info_get(&info) != 1 || info.window == NULL || info.window == game_window) return;
    sdl_window_proc = (WNDPROC)SetWindowLongPtrA(info.window, GWLP_WNDPROC, (LONG_PTR)window_proc);
    if (sdl_window_proc != NULL) game_window = info.window;
}

/* Gives a windowed, framed window the maximize box and a sizing border, and
   sizes it so its client area is the picture's size again. */
static void make_resizable(int w, int h) {
    LONG style = GetWindowLongA(game_window, GWL_STYLE);
    RECT outer, client;
    if ((style & WS_CAPTION) != WS_CAPTION) return;
    SetWindowLongA(game_window, GWL_STYLE, style | WS_MAXIMIZEBOX | WS_THICKFRAME);
    SetWindowPos(game_window, NULL, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
    if (GetWindowRect(game_window, &outer) && GetClientRect(game_window, &client)) {
        SetWindowPos(game_window, NULL, 0, 0,
                     (outer.right - outer.left) - client.right + w,
                     (outer.bottom - outer.top) - client.bottom + h,
                     SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
    }
}

static sdl_surface *__cdecl hook_set_video_mode(int width, int height, int bpp, DWORD flags) {
    sdl_surface *result;
    /* SDL sizes the window for the new mode from a normal (not maximized) one. */
    if (game_window != NULL && IsZoomed(game_window)) ShowWindow(game_window, SW_RESTORE);
    screen = NULL;
    result = sdl_set_video_mode(width, height, bpp, flags);
    if (result != NULL) {
        fullscreen = (result->flags & SDL_FULLSCREEN) != 0;
        attach_window();
        if (game_window != NULL && !fullscreen) make_resizable(result->w, result->h);
        screen = result;
    }
    return result;
}

static int __cdecl hook_flip(sdl_surface *surface) {
    fit f;
    RECT client;
    if (surface == screen && scaled(&f, &client)) {
        HDC dc = GetDC(game_window);
        if (dc != NULL) {
            int done = paint_scaled(dc, &f, &client);
            ReleaseDC(game_window, dc);
            if (done) return 0;
        }
    }
    return sdl_flip(surface);
}

static int same_bytes(UINT_PTR address, const BYTE *expected, SIZE_T length) {
    MEMORY_BASIC_INFORMATION region;
    if (VirtualQuery((LPCVOID)address, &region, sizeof(region)) != sizeof(region)) return 0;
    if (region.State != MEM_COMMIT || (region.Protect & (PAGE_NOACCESS | PAGE_GUARD)) != 0) return 0;
    if ((UINT_PTR)region.BaseAddress + region.RegionSize < address + length) return 0;
    return memcmp((const void *)address, expected, length) == 0;
}

/* Checks all three sites, then points the game's two SDL import slots and
   SDL.dll's ScreenToClient slot here -- all three or none. */
static int install(void) {
    HMODULE sdl = GetModuleHandleA("SDL.dll");
    void *video_mode_now, *flip_now;
    void *volatile *cursor_slot;
    DWORD old_protect, cursor_protect, ignored;
    if (sdl == NULL) return 0;
    sdl_set_video_mode = (set_video_mode_fn)GetProcAddress(sdl, "SDL_SetVideoMode");
    sdl_flip = (flip_fn)GetProcAddress(sdl, "SDL_Flip");
    sdl_lock = (lock_fn)GetProcAddress(sdl, "SDL_LockSurface");
    sdl_unlock = (unlock_fn)GetProcAddress(sdl, "SDL_UnlockSurface");
    sdl_wm_info_get = (wm_info_fn)GetProcAddress(sdl, "SDL_GetWMInfo");
    if (sdl_set_video_mode == NULL || sdl_flip == NULL || sdl_lock == NULL || sdl_unlock == NULL ||
        sdl_wm_info_get == NULL) return 0;
    if (!same_bytes(SET_VIDEO_MODE_THUNK, set_video_mode_thunk, sizeof(set_video_mode_thunk)) ||
        !same_bytes(FLIP_THUNK, flip_thunk, sizeof(flip_thunk))) return 0;
    video_mode_now = *(void *volatile *)SET_VIDEO_MODE_SLOT;
    flip_now = *(void *volatile *)FLIP_SLOT;
    if (video_mode_now != (void *)sdl_set_video_mode || flip_now != (void *)sdl_flip) return 0;
    cursor_slot = screen_to_client_slot(sdl);
    if (cursor_slot == NULL) return 0;
    if (!VirtualProtect((LPVOID)cursor_slot, sizeof(void *), PAGE_READWRITE, &cursor_protect)) return 0;
    if (!VirtualProtect((LPVOID)SET_VIDEO_MODE_SLOT, FLIP_SLOT + 4 - SET_VIDEO_MODE_SLOT, PAGE_READWRITE,
                        &old_protect)) {
        VirtualProtect((LPVOID)cursor_slot, sizeof(void *), cursor_protect, &ignored);
        return 0;
    }
    *cursor_slot = (void *)hook_screen_to_client;
    *(void *volatile *)SET_VIDEO_MODE_SLOT = (void *)hook_set_video_mode;
    *(void *volatile *)FLIP_SLOT = (void *)hook_flip;
    VirtualProtect((LPVOID)SET_VIDEO_MODE_SLOT, FLIP_SLOT + 4 - SET_VIDEO_MODE_SLOT, old_protect, &ignored);
    VirtualProtect((LPVOID)cursor_slot, sizeof(void *), cursor_protect, &ignored);
    return 1;
}

/* Called once at start, by the executable's startup stub or by
   "DS Exclusive Fish.dll", before WinMain. */
int __stdcall FtfpStartup(void) {
    if (installed) return 1;
    __try {
        installed = install();
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
