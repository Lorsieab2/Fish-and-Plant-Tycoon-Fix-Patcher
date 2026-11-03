"""Unicode Font (Tools tab -> "Unicode Font..."): pick the font "Use Unicode Font (overrides in-game
fonts)" draws all of the game's text with, in both games.

Any font installed in Windows (with a search), or a .ttf / .otf / .ttc file. The choice is the
patcher's own (one for both games, kept for every later patch): the family is the same "Font="
the quick font box beside the setting writes into "Unicode Text.ini", and a font file adds
"File=<its name>": the patcher copies the file beside "Unicode Text.dll", which loads it for the
game only (AddFontResourceExW with FR_PRIVATE: nothing is installed in Windows;
native/common/unicode_config.h). Save also updates the modded copies already made, when they have
Unicode Text.ini, so the next start of the game uses the new font without patching again.

The previews draw each game font's sample as Use Unicode Font will (src/text_maker.py
render_unicode_font: the font's line height, baseline and alpha steps, the em fitted so that "The
quick brown fox jumps over the lazy dog 0123456789" is as wide as the game font draws it, within
60%..130%), beside the game's own drawing of the same text.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from picture_image import Image
import text_maker as tm

TITLE = "Unicode Font"
DEFAULT_FACE = "Segoe UI"
SAMPLE = "Player: Zoë Åström, İlkay, Łukasz 日本 한국 🐟"
FONT_FILES = (("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*"))
INI = "Unicode Text.ini"
DLL_FOLDERS = {"fish": "Fish Tycoon Fix Patcher DLLs", "plant": "Plant Tycoon Fix Patcher DLLs"}

HELP = (
    "Unicode Font",
    [
        "Chooses the font \"Use Unicode Font (overrides in-game fonts)\" draws all of the game's text with: "
        "any font installed in Windows (type in the search box), or a font file (.ttf, .otf, .ttc) you have.",
        "The previews show each of the game's fonts as the game will draw it: the game's own line height, "
        "baseline and shading, the font's size fitted so a line is as wide as the game's own. A letter the "
        "font lacks comes from Segoe UI and the fallback chain (Segoe UI Historic, Symbol and Emoji, the CJK "
        "fonts, Nirmala UI, Ebrima ..., the Noto fonts if installed, then the fonts the patcher ships), and "
        "a letter no font has is an empty box.",
        "Save keeps the choice for every later patch (both games) and updates the modded copies already "
        "made. A font file is copied beside Unicode Text.dll and loaded for the game only; nothing is "
        "installed in Windows. The quick Font box beside the setting on the patch tabs is the same choice.",
    ],
)


def installed_faces(master) -> list[str]:
    """The installed font families (not the vertical "@" ones), Segoe UI first."""
    try:
        from tkinter import font as tkfont
        names = sorted({f for f in tkfont.families(master) if f and not f.startswith("@")}, key=str.casefold)
    except tk.TclError:
        names = []
    return [DEFAULT_FACE] + [f for f in names if f != DEFAULT_FACE]


def matching(faces: list[str], search: str) -> list[str]:
    words = search.casefold().split()
    return [f for f in faces if all(w in f.casefold() for w in words)]


def font_file_family(path: Path) -> str | None:
    """A font file's family name (its name table), as Windows will know it once loaded."""
    return tm._family_name(Path(path))


def set_ini_values(data: bytes, values: dict[str, str | None]) -> bytes:
    """Unicode Text.ini with each key set (None: removed), every other line kept as it was."""
    lines = data.decode("utf-8", "replace").splitlines()
    out, done = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if "=" in line and key in values:
            if values[key] is not None and key not in done:
                out.append(f"{key}={values[key]}")
            done.add(key)
            continue
        out.append(line)
    out += [f"{k}={v}" for k, v in values.items() if v is not None and k not in done]
    return ("\r\n".join(out) + "\r\n").encode("utf-8")


def apply_to_copy(output_dir: Path, game: str, face: str, font_file: Path | None) -> Path | None:
    """The choice written into a modded copy's Unicode Text.ini (Font=, File=) and the font file copied
    beside the DLL; the ini's path, or None when the copy has no Unicode Text.ini."""
    import fish_patcher
    folder = Path(output_dir) / DLL_FOLDERS[game]
    ini = folder / INI
    if not ini.is_file():
        return None
    name = None
    chosen = fish_patcher.unicode_font_file(font_file)
    if chosen is not None:
        name = fish_patcher.font_file_name(chosen)
        shutil.copyfile(chosen, folder / name)
    ini.write_bytes(set_ini_values(ini.read_bytes(), {"Font": fish_patcher.clean_font_name(face), "File": name}))
    return ini


def preview_rows(fonts: list[tm.GameFont], face: str, font_file: Path | None, text: str = SAMPLE):
    """(label, the game's own drawing, Use Unicode Font's drawing) for each game font."""
    files = [str(font_file)] if font_file else []
    rows = []
    for font in fonts:
        if not font.in_game:
            continue
        own = tm.render(font, text, 0xFFFFFF, "None", 1, None, False)
        try:
            unicode = tm.render_unicode_font(font, text, face, files)
        except Exception:                  # Windows' font drawing is not there: no preview
            unicode = Image(1, font.line_height)
        rows.append((font.label, own, unicode))
    return rows


class UnicodeFontWindow:
    def __init__(self, app, folders: dict[str, list]) -> None:
        self.app = app
        self.folders = folders
        self.fonts: dict[str, list[tm.GameFont]] = {}
        self._photos = []
        current_file = str(getattr(app, "unicode_font_file", tk.StringVar(master=app)).get() or "")
        self.font_file = Path(current_file) if current_file else None
        win = self.window = tk.Toplevel(app)
        win.title(TITLE)
        win.geometry("1000x720")
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)

        left = ttk.Frame(frame)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Installed fonts (search):").pack(anchor="w")
        self.search = tk.StringVar(master=win)
        entry = ttk.Entry(left, textvariable=self.search, width=34)
        entry.pack(anchor="w", fill="x")
        self.search.trace_add("write", lambda *_a: self.fill_faces())
        self.list = tk.Listbox(left, height=24, exportselection=False, width=34)
        self.list.pack(fill="y", expand=True, pady=(4, 0))
        self.list.bind("<<ListboxSelect>>", lambda _e: self.face_picked())
        ttk.Button(left, text="Choose a font file...", command=self.choose_file).pack(anchor="w", pady=(6, 0))
        ttk.Button(left, text="Segoe UI (the default)", command=lambda: self.set_face(DEFAULT_FACE, None)).pack(
            anchor="w", pady=(4, 0))

        right = ttk.Frame(frame)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.chosen = tk.StringVar(master=win)
        ttk.Label(right, textvariable=self.chosen, foreground="#245a9a").pack(anchor="w")
        ttk.Label(right, text="Each game font: as the stock game shows it, then as Use Unicode Font will draw it "
                              "(2x):").pack(anchor="w", pady=(6, 0))
        self.canvas = tk.Canvas(right, background="#182848", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=(4, 0))
        bottom = ttk.Frame(right)
        bottom.pack(fill="x", pady=(8, 0))
        self.status = tk.StringVar(master=win)
        ttk.Label(bottom, textvariable=self.status, wraplength=600, justify="left").pack(side="left")
        ttk.Button(bottom, text="Close", command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="Save", command=self.save).pack(side="right", padx=(0, 8))

        self.faces = installed_faces(win)
        self.face = str(getattr(app, "unicode_font", tk.StringVar(master=app, value=DEFAULT_FACE)).get()
                        or DEFAULT_FACE)
        self.fill_faces()
        self.load_fonts()
        self.refresh()

    def fill_faces(self) -> None:
        self.list.delete(0, "end")
        for face in matching(self.faces, self.search.get()):
            self.list.insert("end", face)

    def face_picked(self) -> None:
        picked = self.list.curselection()
        if picked:
            self.set_face(self.list.get(picked[0]), None)

    def set_face(self, face: str, font_file: Path | None) -> None:
        self.face, self.font_file = face, font_file
        self.refresh()

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(parent=self.window, title="Choose a font file", filetypes=FONT_FILES)
        if not path:
            return
        family = font_file_family(Path(path))
        if not family:
            messagebox.showerror(TITLE, f"{path} is not a font file Windows can use.", parent=self.window)
            return
        self.set_face(family, Path(path))

    def load_fonts(self) -> None:
        for game in tm.GAME_TITLES:
            folder = tm.find_game_folder(game, self.folders.get(game, []))
            try:
                self.fonts[game] = tm.load_fonts(game, folder) if folder else []
            except (OSError, ValueError):
                self.fonts[game] = []

    def refresh(self) -> None:
        where = f" (from {self.font_file.name})" if self.font_file else ""
        self.chosen.set(f"Chosen: {self.face}{where}")
        self.canvas.delete("all")
        self._photos = []
        y = 8
        for game, fonts in self.fonts.items():
            for label, own, unicode in preview_rows(fonts, self.face, self.font_file):
                self.canvas.create_text(8, y, text=f"{tm.GAME_TITLES[game]}: {label}", anchor="nw", fill="#ffffff")
                y += 18
                for picture in (own, unicode):
                    photo = picture.scaled(2).photo(tk, self.window)
                    self._photos.append(photo)
                    self.canvas.create_image(8, y, image=photo, anchor="nw")
                    y += picture.height * 2 + 6
                y += 6
        if not any(self.fonts.values()):
            self.status.set("No copy of either game found for the previews: choose the game folders on the Game "
                            "tabs. The choice can still be saved.")

    def save(self) -> None:
        app = self.app
        if "unicode_font" in vars(app):
            app.unicode_font.set(self.face)
        if "unicode_font_file" in vars(app):
            app.unicode_font_file.set(str(self.font_file) if self.font_file else "")
        saved = getattr(app, "_save_settings", lambda: "")()
        updated = []
        for game in DLL_FOLDERS:
            try:
                output = app.path_vars[game]["output"].get().strip()
            except (AttributeError, KeyError):
                output = ""
            if output:
                try:
                    if apply_to_copy(Path(output), game, self.face, self.font_file) is not None:
                        updated.append(tm.GAME_TITLES[game])
                except OSError as error:
                    messagebox.showerror(TITLE, f"Could not update {output}:\n{error}", parent=self.window)
        note = f" Updated the modded copies of {', '.join(updated)}." if updated else ""
        self.status.set(("Saved: the next patch uses it." if not saved else f"Not saved: {saved}") + note)


def open_window(app, folders: dict[str, list]) -> UnicodeFontWindow:
    return UnicodeFontWindow(app, folders)
