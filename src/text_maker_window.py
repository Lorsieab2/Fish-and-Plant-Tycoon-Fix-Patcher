"""The Text Maker window (Tools tab): type anything, see it in the game's own font exactly as
the game draws it, and export it as a PNG. Letters a font lacks (accents, other scripts,
emoji) are made by text_maker.py and marked "patcher-made"."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from picture_image import Image
import text_maker as tm

HELP = (
    "Text Maker",
    [
        "Type any text and see it in the game's own fonts, drawn exactly as the game draws it: the "
        "game's letter pictures, widths, line height and colours (Fish Tycoon: Paddington 18 and 30 and "
        "Triplex Sans; Plant Tycoon: PT Font Small, plus PT Font Big and LDW Arial Bold, which are in its "
        "folder but never used by the game).",
        "Pick the colour (the games' own or any other), a shadow or outline, the size (1x, 2x...) and the "
        "background, then Export PNG..., with a transparent background if you like.",
        "Accents and any Unicode: the Insert Character list has the common accented letters by language, "
        "and the Any Unicode box takes a code (U+00E9, 1F41F), a name (LATIN SMALL LETTER E WITH ACUTE) or "
        "the characters themselves: Japanese, Chinese, Korean, Greek, Cyrillic, cuneiform, emoji...",
        "Letters a font lacks are made for it and listed as \"patcher-made\": accented letters from the "
        "font's own letters and accents, everything else drawn from a Windows font (Segoe UI and its "
        "Historic, Symbol and Emoji fonts, Yu Gothic, Microsoft YaHei, Malgun Gothic, Nirmala UI...) at the "
        "game font's size, baseline and stroke weight. Untick \"Make missing letters\" to see what the game "
        "itself would draw.",
        "It reads the fonts from a copy of the game (the folders on the Game tabs, or one you choose) and "
        "never changes any game file.",
    ],
)

BACKGROUNDS = (("Transparent", None), ("Black", (0, 0, 0)), ("Deep blue", (24, 40, 72)),
               ("White", (255, 255, 255)))
PREVIEW_CHECKER = ((204, 204, 204), (240, 240, 240))
PATCHER_MADE_MARK = "#ff00c8"
SAMPLE = "Fish and Plant Tycoon\nCafé, naïve, Ğğ Şş İı, 日本語, 中文 🐟🌻"


def _checker(width: int, height: int, cell: int = 8) -> Image:
    """A grey checkerboard (the preview's transparent background)."""
    image = Image(width, height)
    dark, light = (bytes((*c, 255)) for c in PREVIEW_CHECKER)
    for y in range(height):
        row = b"".join((light if (x // cell + y // cell) % 2 else dark) * min(cell, width - x)
                       for x in range(0, width, cell))
        image.data[y * width * 4:(y + 1) * width * 4] = row
    return image


class TextMakerWindow:
    def __init__(self, master, game: str | None, folders: dict[str, list]) -> None:
        self.master = master
        self.folders = {g: list(v) for g, v in folders.items()}
        self.fonts: dict[str, list[tm.GameFont]] = {}
        self.game_folder: dict[str, Path | None] = {}
        self._after = None
        self._photo = None
        self.custom_colour = 0xFFFFFF
        self.custom_background = (0, 0, 0)

        win = self.window = tk.Toplevel(master)
        win.title("Text Maker")
        win.geometry("1000x800")
        win.minsize(760, 560)
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)

        # ---- game and font
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Label(row, text="Game:").pack(side="left")
        self.game_var = tk.StringVar(master=win, value=tm.GAME_TITLES.get(game or "fish", "Fish Tycoon"))
        game_box = ttk.Combobox(row, textvariable=self.game_var, state="readonly", width=14,
                                values=list(tm.GAME_TITLES.values()))
        game_box.pack(side="left", padx=(4, 12))
        game_box.bind("<<ComboboxSelected>>", lambda _e: self._load_game())
        ttk.Label(row, text="Font:").pack(side="left")
        self.font_var = tk.StringVar(master=win)
        self.font_box = ttk.Combobox(row, textvariable=self.font_var, state="readonly", width=52)
        self.font_box.pack(side="left", padx=(4, 12))
        self.font_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Button(row, text="Game Copy...", command=self._choose_folder).pack(side="left")
        self.folder_text = tk.StringVar(master=win)
        ttk.Label(frame, textvariable=self.folder_text, foreground="#245a9a").pack(anchor="w", pady=(2, 6))

        # ---- look
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Label(row, text="Colour:").pack(side="left")
        self.colour_var = tk.StringVar(master=win, value=tm.GAME_COLOURS[0][0])
        colour_box = ttk.Combobox(row, textvariable=self.colour_var, state="readonly", width=26,
                                  values=[n for n, _c in tm.GAME_COLOURS] + ["Custom..."])
        colour_box.pack(side="left", padx=(4, 2))
        colour_box.bind("<<ComboboxSelected>>", lambda _e: self._colour_chosen())
        self.swatch = tk.Label(row, width=3, relief="solid", borderwidth=1, background="#ffffff")
        self.swatch.pack(side="left", padx=(0, 12))
        ttk.Label(row, text="Effect:").pack(side="left")
        self.effect_var = tk.StringVar(master=win, value="Shadow" if game == "plant" else "None")
        effect_box = ttk.Combobox(row, textvariable=self.effect_var, state="readonly", width=9, values=tm.EFFECTS)
        effect_box.pack(side="left", padx=(4, 12))
        effect_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Label(row, text="Size:").pack(side="left")
        self.scale_var = tk.IntVar(master=win, value=2)
        ttk.Spinbox(row, from_=1, to=8, width=3, textvariable=self.scale_var, state="readonly",
                    command=self.refresh).pack(side="left", padx=(4, 0))
        ttk.Label(row, text="x").pack(side="left", padx=(1, 12))
        ttk.Label(row, text="Background:").pack(side="left")
        self.background_var = tk.StringVar(master=win, value="Deep blue")
        background_box = ttk.Combobox(row, textvariable=self.background_var, state="readonly", width=12,
                                      values=[n for n, _b in BACKGROUNDS] + ["Custom..."])
        background_box.pack(side="left", padx=(4, 0))
        background_box.bind("<<ComboboxSelected>>", lambda _e: self._background_chosen())

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(6, 0))
        self.generate_var = tk.BooleanVar(master=win, value=True)
        ttk.Checkbutton(row, text="Make missing letters (patcher-made)", variable=self.generate_var,
                        command=self.refresh).pack(side="left")
        self.highlight_var = tk.BooleanVar(master=win, value=False)
        ttk.Checkbutton(row, text="Outline patcher-made letters in the preview", variable=self.highlight_var,
                        command=self.refresh).pack(side="left", padx=(16, 0))

        # ---- text and the character helper
        middle = ttk.Frame(frame)
        middle.pack(fill="x", pady=(8, 0))
        text_box = ttk.LabelFrame(middle, text="Text (Enter starts a new line)", padding=4)
        text_box.pack(side="left", fill="both", expand=True)
        self.text = tk.Text(text_box, height=6, width=50, wrap="none", font=("Segoe UI", 11), undo=True)
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", SAMPLE)
        self.text.bind("<<Modified>>", self._modified)

        helper = ttk.LabelFrame(middle, text="Insert character", padding=4)
        helper.pack(side="left", fill="y", padx=(8, 0))
        top = ttk.Frame(helper)
        top.pack(fill="x")
        self.group_var = tk.StringVar(master=win, value=tm.ACCENTS[0][0])
        group_box = ttk.Combobox(top, textvariable=self.group_var, state="readonly", width=20,
                                 values=[g for g, _l in tm.ACCENTS])
        group_box.pack(side="left")
        group_box.bind("<<ComboboxSelected>>", lambda _e: self._fill_letters())
        self.upper_var = tk.BooleanVar(master=win, value=False)
        ttk.Checkbutton(top, text="Capitals", variable=self.upper_var, command=self._fill_letters).pack(
            side="left", padx=(6, 0))
        self.letters = ttk.Frame(helper)
        self.letters.pack(fill="x", pady=(4, 4))
        any_row = ttk.Frame(helper)
        any_row.pack(fill="x")
        ttk.Label(any_row, text="Any Unicode:").pack(side="left")
        self.unicode_var = tk.StringVar(master=win)
        entry = ttk.Entry(any_row, textvariable=self.unicode_var, width=18)
        entry.pack(side="left", padx=(4, 4))
        entry.bind("<Return>", lambda _e: self._insert_unicode())
        ttk.Button(any_row, text="Insert", command=self._insert_unicode).pack(side="left")
        self.unicode_note = tk.StringVar(master=win, value="U+00E9, 1F41F, a name, or the characters")
        ttk.Label(helper, textvariable=self.unicode_note, foreground="#555555", wraplength=300).pack(anchor="w")
        self._fill_letters()

        # ---- preview
        preview = ttk.LabelFrame(frame, text="Preview (as the game draws it)", padding=4)
        preview.pack(fill="both", expand=True, pady=(8, 0))
        self.canvas = tk.Canvas(preview, background="#cccccc", highlightthickness=0, height=170)
        ys = ttk.Scrollbar(preview, orient="vertical", command=self.canvas.yview)
        xs = ttk.Scrollbar(preview, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        self.canvas.pack(fill="both", expand=True)

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", pady=(6, 0))
        self.status = tk.StringVar(master=win)
        ttk.Label(bottom, textvariable=self.status, wraplength=940, justify="left").pack(anchor="w")
        made = ttk.Frame(frame)
        made.pack(fill="x", pady=(4, 0))
        self.made = ttk.Treeview(made, columns=("letter", "code", "how"), show="headings", height=4)
        for column, title, width in (("letter", "Patcher-made", 90), ("code", "Unicode", 330),
                                     ("how", "How it was made", 500)):
            self.made.heading(column, text=title)
            self.made.column(column, width=width, anchor="w")
        self.made.pack(side="left", fill="x", expand=True)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Export PNG...", command=self.export).pack(side="left")
        self.transparent_var = tk.BooleanVar(master=win, value=True)
        ttk.Checkbutton(buttons, text="Transparent background", variable=self.transparent_var).pack(
            side="left", padx=(8, 0))
        ttk.Button(buttons, text="Close", command=win.destroy).pack(side="right")
        win.bind("<Escape>", lambda _e: win.destroy())
        self._load_game()

    # ------------------------------------------------------------------ state

    @property
    def game(self) -> str:
        return {v: k for k, v in tm.GAME_TITLES.items()}[self.game_var.get()]

    @property
    def font(self) -> tm.GameFont | None:
        fonts = self.fonts.get(self.game) or []
        for font in fonts:
            if font.label == self.font_var.get():
                return font
        return fonts[0] if fonts else None

    def colour(self) -> int:
        for name, value in tm.GAME_COLOURS:
            if name == self.colour_var.get():
                return value
        return self.custom_colour

    def background(self) -> tuple | None:
        for name, value in BACKGROUNDS:
            if name == self.background_var.get():
                return value
        return self.custom_background

    def text_value(self) -> str:
        return self.text.get("1.0", "end-1c")

    # ------------------------------------------------------------------ loading

    def _load_game(self, folder: Path | None = None) -> None:
        game = self.game
        if folder is None and game in self.fonts:
            self._show_fonts()
            return
        if folder is None:
            folder = tm.find_game_folder(game, self.folders.get(game, []))
        if folder is None:
            self.fonts[game] = []
            self.folder_text.set(f"No copy of {tm.GAME_TITLES[game]} found: press Game Copy... to choose its folder.")
            self._show_fonts()
            return
        try:
            self.fonts[game] = tm.load_fonts(game, folder)
        except (OSError, ValueError) as error:
            self.fonts[game] = []
            messagebox.showerror("Text Maker", f"Could not read the fonts in {folder}:\n{error}", parent=self.window)
        self.game_folder[game] = folder
        self.folder_text.set(f"Fonts from: {folder}")
        self._show_fonts()

    def _show_fonts(self) -> None:
        fonts = self.fonts.get(self.game) or []
        self.font_box.configure(values=[f.label for f in fonts])
        if fonts and self.font_var.get() not in [f.label for f in fonts]:
            self.font_var.set(fonts[0].label)
        if not fonts:
            self.font_var.set("")
        self.refresh()

    def _choose_folder(self) -> None:
        chosen = filedialog.askdirectory(parent=self.window, title=f"The {self.game_var.get()} folder")
        if not chosen:
            return
        if tm.find_game_folder(self.game, [chosen]) is None:
            messagebox.showerror("Text Maker", f"{chosen} is not a copy of {self.game_var.get()} with its fonts.",
                                 parent=self.window)
            return
        self.folders.setdefault(self.game, []).insert(0, chosen)
        self._load_game(Path(chosen))

    # ------------------------------------------------------------------ choices

    def _colour_chosen(self) -> None:
        if self.colour_var.get() == "Custom...":
            start = f"#{self.custom_colour:06x}"
            chosen = colorchooser.askcolor(start, parent=self.window, title="Text colour")
            if chosen and chosen[1]:
                self.custom_colour = int(chosen[1][1:], 16)
            self.colour_var.set("Custom...")
        self.refresh()

    def _background_chosen(self) -> None:
        if self.background_var.get() == "Custom...":
            chosen = colorchooser.askcolor("#%02x%02x%02x" % self.custom_background, parent=self.window,
                                           title="Background colour")
            if chosen and chosen[0]:
                self.custom_background = tuple(int(v) for v in chosen[0])
        self.refresh()

    def _fill_letters(self) -> None:
        for child in self.letters.winfo_children():
            child.destroy()
        letters = dict(tm.ACCENTS)[self.group_var.get()]
        if self.upper_var.get():
            letters = "".join(c.upper() if len(c.upper()) == 1 else c for c in letters)
        for i, ch in enumerate(dict.fromkeys(c for c in letters if not c.isspace())):
            tk.Button(self.letters, text=ch, width=2, font=("Segoe UI", 10), relief="groove",
                      command=lambda c=ch: self.insert(c)).grid(row=i // 10, column=i % 10)

    def insert(self, chars: str) -> None:
        self.text.insert("insert", chars)
        self.text.focus_set()
        self.refresh()

    def _insert_unicode(self) -> None:
        chars = tm.parse_unicode(self.unicode_var.get())
        if not chars:
            return
        self.insert(chars)
        self.unicode_note.set(tm.describe(chars)[:200])
        self.unicode_var.set("")

    def _modified(self, _event=None) -> None:
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.refresh()

    # ------------------------------------------------------------------ drawing

    def refresh(self) -> None:
        if self._after is not None:
            self.window.after_cancel(self._after)
        self._after = self.window.after(120, self._draw)

    def picture(self, transparent: bool) -> Image | None:
        font = self.font
        if font is None:
            return None
        return tm.render(font, self.text_value(), self.colour(), self.effect_var.get(), int(self.scale_var.get()),
                         None if transparent else self.background(), self.generate_var.get())

    def _draw(self) -> None:
        self._after = None
        self.swatch.configure(background=f"#{self.colour():06x}")
        self.canvas.delete("all")
        font = self.font
        self.made.delete(*self.made.get_children())
        if font is None:
            self.status.set("No fonts: choose a copy of the game with Game Copy...")
            return
        text = self.text_value()
        background = self.background()
        image = self.picture(background is None)
        if background is None:
            shown = _checker(image.width, image.height)
            shown.draw(image, 0, 0)
        else:
            shown = image
        self._photo = shown.photo(tk, self.window)
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, shown.width, shown.height))
        generate = self.generate_var.get()
        placed, _w, _h = tm.layout(font, text, generate)
        scale = int(self.scale_var.get())
        pad = 2 + (1 if self.effect_var.get() != "None" else 0)
        if self.highlight_var.get():
            for p in placed:
                if p.glyph.generated:
                    x0, y0 = (pad + p.x) * scale, (pad + p.y) * scale
                    self.canvas.create_rectangle(x0, y0, x0 + p.glyph.pixels.width * scale,
                                                 y0 + font.line_height * scale, outline=PATCHER_MADE_MARK, dash=(3, 2))
        made = tm.generated_in(font, text) if generate else []
        for cluster, how in made:
            self.made.insert("", "end", values=(cluster, tm.describe(cluster), how))
        count = len([c for c in tm.clusters(text) if c not in ("\n", "\r\n")])
        where = "in the game" if font.in_game else "not used by the game"
        self.status.set(
            f"{font.label}: line height {font.line_height} px, {where}. {count} characters, "
            f"{len(made)} patcher-made." + ("" if generate else " Showing what the game itself draws "
                                             "(a letter it lacks shows as its first letter or a box)."))

    def export(self) -> None:
        image = self.picture(self.transparent_var.get())
        if image is None:
            return
        font = self.font
        path = filedialog.asksaveasfilename(parent=self.window, title="Export PNG", defaultextension=".png",
                                            filetypes=[("PNG picture", "*.png")],
                                            initialfile=f"{font.key} text.png")
        if not path:
            return
        try:
            Path(path).write_bytes(image.to_png())
        except OSError as error:
            messagebox.showerror("Text Maker", f"Could not save {path}:\n{error}", parent=self.window)
            return
        self.status.set(f"Saved {path} ({image.width} x {image.height}).")


def open_window(master, game: str | None, folders: dict[str, list]) -> TextMakerWindow:
    return TextMakerWindow(master, game if game in tm.GAME_TITLES else None, folders)
