"""The Translations window (Tools tab): choose the game's language, make a translation in a built-in
editor, add one you were sent (button or drag and drop), export or delete (to the Recycle Bin) one or
several, share one on GitHub, and download the ones shared there (Download from GitHub...,
translations_github.py).

The work is in translations.py (files, the choice, sharing) and translation_format.py (the format);
the game side is Translations.dll. Nothing here asks for, stores or sends an email address: the
credit name is typed by the player each time, never filled in from anywhere.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import queue
import re
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import webbrowser

import translation_format as tfmt
import text_wrap as twrap
import translation_strings as tstr
import translations as tr
import translations_github as tgh

TITLE = "Translations"
GAMES = tfmt.GAME_TITLES
ENGLISH = tfmt.ENGLISH_ORIGINAL
OTHER_LANGUAGE = "Other language..."
ENGLISH_ROW = ENGLISH + "   (built into the game; cannot be deleted)"
CHOOSE_ONE = "Choose one translation in the list first."
AUTOSAVE_MS = 800

HELP = (
    "Translations",
    [
        "Play Fish Tycoon and Plant Tycoon in another language, or make a translation yourself. Patch the "
        "game with the \"Translations\" setting on (it is on by default), then choose the language here: it "
        "applies from the next game start, without patching again. \"English (original)\" changes nothing.",
        "Make a translation: choose a language and press Make a translation... The patcher writes a file with "
        "every English line of the game and of the patcher's own texts, and opens it in the built-in editor: "
        "the English on the left, your translation on the right, search, \"show untranslated only\", how much "
        "is done, and a preview in the game's own font that warns when a line is too long. Wrap to fit "
        "re-breaks the selected translation so no line is wider than the widest line of the English, and Wrap "
        "all does every line that is wider (it shows the count first; Undo wrap takes the last one back): the "
        "games break lines only where you do, so a longer translation, or Chinese, Japanese or Thai, needs it. "
        "It only moves line breaks and spaces, never the words or a placeholder. Placeholders such "
        "as %d, %s and {name} must stay; the editor shows them in colour and says when one is missing. It "
        "saves by itself. The file is plain UTF-8 text, so Notepad or a spreadsheet (as tab-separated text) "
        "work too.",
        "Numbers: a line with %d can choose its words by the number, e.g. \"%d {%1: one=poisson | "
        "other=poissons}\". docs/translations.md explains everything.",
        "Add translation file... (or drag a .txt file onto this window) checks a file you were sent and adds "
        "it to the list. Export translation... saves a copy anywhere.",
        "The list is for managing the files; the language the game uses is chosen above, under \"Language in "
        "the game\". Click a translation to select it, Ctrl+click to add or remove one, Shift+click to select "
        "a range, and Ctrl+A or Select All for all of them. Export translation... with several selected saves "
        "one file each into a folder you choose. Delete... moves the selected files to the Recycle Bin (it "
        "asks first, and No changes nothing; you can restore them from there). \"English (original)\" is "
        "built into the game and is never deleted. A translation that came with the patcher can be deleted "
        "from your copy too; it comes back with the next patcher update. If the game uses a translation you "
        "delete, it goes back to English (original).",
        "After a patcher update, new lines appear untranslated in the editor and your translation keeps "
        "working; a line whose English changed shows the new English until you translate it again.",
        tr.SHARE_INVITE + " " + tr.SHARE_HOW + " You need a free GitHub account (" + tr.SIGNUP_URL + "). "
        + tfmt.EMAIL_MESSAGE,
        "Download from GitHub... lists the translations shared in the patcher's public GitHub folder, with "
        "their language, credit, last change and whether an update is available. Choose one or more and press "
        "Download: each is checked before it is installed. No account is needed and nothing about you is sent. "
        "Every shared file is sent to VirusTotal, where its partners can see it, so never put private details "
        "in a translation.",
    ],
)


def _one_line(text: str) -> str:
    return text.replace("\n", " ⏎ ").replace("\t", " ")


# --------------------------------------------------------------------------- drag and drop


class FileDrop:
    """Windows drag and drop of files onto a Tk window (WM_DROPFILES): DragAcceptFiles on its frame,
    its window procedure subclassed through ctypes; each dropped path goes to `handler`, the same one
    the Add button uses. On any failure the window simply has the button only (`active` is False)."""

    WM_DROPFILES = 0x0233
    GWLP_WNDPROC = -4

    def __init__(self, window: tk.Misc, handler) -> None:
        self.window = window
        self.handler = handler
        self.active = False
        self._old = None
        self._proc = None
        try:
            self._install()
        except Exception:
            self.active = False

    def _install(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        self.window.update_idletasks()
        hwnd = int(self.window.wm_frame(), 16)
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.CallWindowProcW.restype = LRESULT
        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                           wintypes.LPARAM]
        shell32.DragQueryFileW.restype = wintypes.UINT
        shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        shell32.DragFinish.argtypes = [ctypes.c_void_p]
        shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]

        def proc(h, message, wparam, lparam):
            if message == self.WM_DROPFILES:
                paths = []
                try:
                    count = shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0)
                    for index in range(count):
                        size = shell32.DragQueryFileW(wparam, index, None, 0) + 1
                        buffer = ctypes.create_unicode_buffer(size)
                        shell32.DragQueryFileW(wparam, index, buffer, size)
                        paths.append(buffer.value)
                finally:
                    shell32.DragFinish(wparam)
                if paths:
                    self.window.after(0, lambda: self.handler([Path(p) for p in paths]))
                return 0
            return user32.CallWindowProcW(self._old, h, message, wparam, lparam)

        self._proc = WNDPROC(proc)
        self._user32, self._hwnd = user32, hwnd
        old = user32.SetWindowLongPtrW(hwnd, self.GWLP_WNDPROC, ctypes.cast(self._proc, ctypes.c_void_p))
        if not old:
            raise OSError("SetWindowLongPtrW failed")
        self._old = old
        # A patcher run as administrator still takes drops from Explorer.
        try:
            user32.ChangeWindowMessageFilterEx(hwnd, self.WM_DROPFILES, 1, None)
            user32.ChangeWindowMessageFilterEx(hwnd, 0x004A, 1, None)
            user32.ChangeWindowMessageFilterEx(hwnd, 0x0049, 1, None)
        except Exception:
            pass
        shell32.DragAcceptFiles(hwnd, True)
        self.active = True

    def remove(self) -> None:
        if self.active and self._old:
            try:
                self._user32.SetWindowLongPtrW(self._hwnd, self.GWLP_WNDPROC, self._old)
            except Exception:
                pass
        self.active = False


# --------------------------------------------------------------------------- the window


class TranslationsWindow:
    def __init__(self, master, game: str | None, folders: dict[str, list], folder: Path | None = None,
                 choices_path: Path | None = None) -> None:
        self.master = master
        self.folders = {g: [str(f) for f in v if f] for g, v in folders.items()}
        self.folder = folder or tr.TRANSLATIONS_DIR
        self.choices_path = choices_path
        self.entries_cache: dict[str, list[tfmt.Entry]] = {}
        self.items: list[tr.Installed] = []
        self.editors: list[TranslationEditor] = []

        win = self.window = tk.Toplevel(master)
        win.title(TITLE)
        win.geometry("760x620")
        win.minsize(640, 520)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)

        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Label(row, text="Game:").pack(side="left")
        self.game_var = tk.StringVar(master=win, value=GAMES.get(game or "fish", "Fish Tycoon"))
        box = ttk.Combobox(row, textvariable=self.game_var, values=list(GAMES.values()), state="readonly", width=14)
        box.pack(side="left", padx=(4, 0))
        box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Button(row, text="?", width=2, command=self.show_guide).pack(side="right")

        group = ttk.LabelFrame(frame, text="Language in the game", padding=10)
        group.pack(fill="x", pady=(10, 0))
        self.language_var = tk.StringVar(master=win, value=ENGLISH)
        self.language_box = ttk.Combobox(group, textvariable=self.language_var, state="readonly", width=48)
        self.language_box.pack(anchor="w")
        self.language_box.bind("<<ComboboxSelected>>", lambda _e: self.choose())
        self.choice_status = tk.StringVar(master=win, value="")
        ttk.Label(group, textvariable=self.choice_status, wraplength=700, foreground="#245a9a").pack(anchor="w", pady=(4, 0))

        group = ttk.LabelFrame(frame, text="Make a translation", padding=10)
        group.pack(fill="x", pady=(10, 0))
        names = [name for name, _code in tr.LANGUAGES] + [OTHER_LANGUAGE]
        self.new_language = tk.StringVar(master=win, value=names[0])
        ttk.Combobox(group, textvariable=self.new_language, values=names, state="readonly", width=28).pack(side="left")
        ttk.Button(group, text="Make a translation...", command=self.make).pack(side="left", padx=(8, 0))

        group = ttk.LabelFrame(frame, text="Translations in the patcher", padding=10)
        group.pack(fill="both", expand=True, pady=(10, 0))
        # The list manages the files (several at once); the language the game uses is the dropdown above.
        # Row 0 is English (original), built into the game: it can be selected but is never deleted.
        self.listbox = tk.Listbox(group, height=7, activestyle="none", selectmode=tk.EXTENDED, exportselection=False)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", lambda _e: self.edit())
        for key in ("<Control-a>", "<Control-A>"):
            self.listbox.bind(key, self._select_all_key)
        self.listbox.bind("<Delete>", self._delete_key)
        ttk.Label(group, text="Ctrl+click adds or removes one, Shift+click selects a range, Ctrl+A selects all.",
                  foreground="#666666").pack(anchor="w", pady=(2, 0))
        buttons = ttk.Frame(group)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Add translation file...", command=self.add_dialog).pack(side="left")
        ttk.Button(buttons, text="Edit...", command=self.edit).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Check", command=self.check).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Open folder", command=self.open_folder).pack(side="left", padx=(8, 0))
        buttons = ttk.Frame(group)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Select All", command=self.select_all).pack(side="left")
        ttk.Button(buttons, text="Export translation...", command=self.export).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Delete...", command=self.delete).pack(side="left", padx=(8, 0))
        self.drop_hint = tk.StringVar(master=win, value="")
        ttk.Label(group, textvariable=self.drop_hint, foreground="#666666").pack(anchor="w", pady=(4, 0))

        group = ttk.LabelFrame(frame, text="Share", padding=10)
        group.pack(fill="x", pady=(10, 0))
        ttk.Label(group, text=tr.SHARE_INVITE, wraplength=700).pack(anchor="w")
        ttk.Label(group, text=tr.SHARE_HOW, wraplength=700).pack(anchor="w", pady=(2, 6))
        share_row = ttk.Frame(group)
        share_row.pack(anchor="w")
        ttk.Button(share_row, text="Share on GitHub...", command=self.share).pack(side="left")
        ttk.Button(share_row, text="?", width=2, command=self.show_guide).pack(side="left", padx=(4, 0))
        ttk.Button(share_row, text="Download from GitHub...", command=self.download_from_github).pack(side="left",
                                                                                                    padx=(8, 0))

        ttk.Button(frame, text="Close", command=self.close).pack(anchor="e", pady=(10, 0))
        win.protocol("WM_DELETE_WINDOW", self.close)
        win.bind("<Escape>", lambda _e: self.close())

        self.drop = FileDrop(win, self.add_files)
        self.drop_hint.set("Or drag a translation file (.txt) onto this window." if self.drop.active else "")
        self.refresh()

    # ---------------------------------------------------------------- state
    @property
    def game(self) -> str:
        return next((g for g, t in GAMES.items() if t == self.game_var.get()), "fish")

    def refresh(self) -> None:
        game = self.game
        self.items = tr.installed(game, self.folder)
        labels = [ENGLISH] + [i.label + ("  (came with the patcher or GitHub)" if i.shipped else "") for i in self.items]
        self.language_box.configure(values=labels)
        chosen = tr.chosen_path(game, tr.load_choices(self.choices_path), self.folder)
        index = next((n + 1 for n, i in enumerate(self.items) if chosen and i.path.resolve() == chosen.resolve()), 0)
        self.language_var.set(labels[index])
        self.listbox.delete(0, "end")
        self.listbox.insert("end", ENGLISH_ROW)
        for item in self.items:
            self.listbox.insert("end", f"{item.label}   [{item.path.name}]" + ("   (came with the patcher or GitHub)" if item.shipped else ""))
        copies = tr.game_copies(game, self.game_folders(game))
        if copies:
            self.choice_status.set(f"Applies from the next game start ({len(copies)} copy/copies of {GAMES[game]} "
                                   "with the Translations setting).")
        else:
            self.choice_status.set(f"No copy of {GAMES[game]} with the Translations setting was found: patch "
                                   "the game with it on (One Game tab), then choose the language here.")

    def game_folders(self, game: str) -> list[str]:
        return self.folders.get(game, [])

    def selected_items(self) -> list[tr.Installed]:
        """The selected translation files, in list order (row 0, English (original), is not a file)."""
        return [self.items[n - 1] for n in self.listbox.curselection() if 0 < n <= len(self.items)]

    def selected(self) -> tr.Installed | None:
        """The one translation Edit, Check and Share act on: the only one selected, or the only one there is."""
        chosen = self.selected_items()
        if len(chosen) == 1:
            return chosen[0]
        if not self.listbox.curselection() and len(self.items) == 1:
            return self.items[0]
        return None

    def select_all(self) -> None:
        self.listbox.selection_set(0, "end")
        self.listbox.focus_set()

    def _select_all_key(self, _event=None) -> str:
        self.select_all()
        return "break"

    def _delete_key(self, _event=None) -> str:
        self.delete()
        return "break"

    # ---------------------------------------------------------------- choosing
    def choose(self) -> list[Path]:
        game = self.game
        labels = list(self.language_box.cget("values"))
        index = labels.index(self.language_var.get()) if self.language_var.get() in labels else 0
        path = self.items[index - 1].path if index > 0 else None
        written = tr.apply_choice(game, path, self.game_folders(game), self.choices_path, self.folder)
        language = self.items[index - 1].language if index > 0 else ENGLISH
        if written:
            self.choice_status.set(f"{GAMES[game]} will be in {language} from its next start "
                                   f"({len(written)} copy/copies updated). No patching needed.")
        else:
            self.choice_status.set(f"Remembered: {language}. No copy of {GAMES[game]} with the Translations "
                                   "setting was found yet; the next patch uses it.")
        return written

    # ---------------------------------------------------------------- the English lines
    def entries(self, game: str, ask: bool = True) -> list[tfmt.Entry] | None:
        if game in self.entries_cache:
            return self.entries_cache[game]
        candidates = list(self.game_folders(game))
        exe = tstr.find_vanilla_exe(game, candidates)
        if exe is None and ask:
            messagebox.showinfo(TITLE, f"Choose your original (unpatched) {GAMES[game]} folder: the patcher reads "
                                       "the game's English lines from it (it never changes it).", parent=self.window)
            folder = filedialog.askdirectory(parent=self.window, title=f"The original {GAMES[game]} folder")
            if folder:
                exe = tstr.find_vanilla_exe(game, [folder])
                if exe is None:
                    messagebox.showerror(TITLE, f"That folder has no original {tstr.EXE_NAMES[game]}.", parent=self.window)
        if exe is None:
            return None
        self.entries_cache[game] = tstr.entries_for(game, exe.read_bytes())
        return self.entries_cache[game]

    # ---------------------------------------------------------------- making and editing
    def make(self) -> Path | None:
        game = self.game
        name = self.new_language.get()
        code = dict(tr.LANGUAGES).get(name, "")
        if name == OTHER_LANGUAGE:
            name = (simpledialog.askstring(TITLE, "The language's own name (as its speakers write it):",
                                           parent=self.window) or "").strip()
            if not name:
                return None
            code = (simpledialog.askstring(TITLE, "Its language code (e.g. fr, tr, ja, zh-Hans); leave empty "
                                                  "if you do not know it:", parent=self.window) or "").strip()
        if tfmt.contains_email(name) or tfmt.contains_email(code):
            messagebox.showerror(TITLE, tfmt.EMAIL_MESSAGE, parent=self.window)
            return None
        entries = self.entries(game)
        if entries is None:
            return None
        path = self.folder / tfmt.file_name(GAMES[game], name)
        if not path.exists():
            self.folder.mkdir(parents=True, exist_ok=True)
            path.write_bytes(tfmt.to_bytes(tfmt.new_file(game, entries, name, code or "und")))
        self.refresh()
        self.open_editor(path)
        return path

    def edit(self) -> None:
        item = self.selected()
        if item is None:
            messagebox.showinfo(TITLE, CHOOSE_ONE, parent=self.window)
            return
        if item.shipped and not messagebox.askyesno(
                TITLE, "This translation came with the patcher. Edit a copy of it as your own?", parent=self.window):
            return
        path = item.path
        if item.shipped:
            # Never the shipped file's bare name: Fish's and Plant's fr.tsv would share one copy.
            path = tr.own_copy_path(item, self.folder)
            if not path.exists():
                self.folder.mkdir(parents=True, exist_ok=True)
                path.write_bytes(item.path.read_bytes())
            self.refresh()
        self.open_editor(path)

    def open_editor(self, path: Path) -> TranslationEditor:
        game = self.game
        editor = TranslationEditor(self.window, game, path, self.entries(game, ask=False),
                                   self.game_folders(game), on_save=self._saved)
        self.editors.append(editor)
        return editor

    def _saved(self, path: Path) -> None:
        """A file the game uses was edited: its copies in the game folders follow."""
        game = self.game
        chosen = tr.chosen_path(game, tr.load_choices(self.choices_path), self.folder)
        if chosen is not None and chosen.resolve() == path.resolve():
            info = tr.read_info(path, game)
            for copy in tr.game_copies(game, self.game_folders(game)):
                tr.write_choice(copy, game, path, info.language if info else "")

    # ---------------------------------------------------------------- adding, checking, exporting
    def add_dialog(self) -> None:
        names = filedialog.askopenfilenames(parent=self.window, title="Add translation file",
                                            filetypes=(("Translation files", "*.txt"), ("All files", "*.*")))
        if names:
            self.add_files([Path(n) for n in names])

    def add_files(self, paths: list[Path]) -> list[Path]:
        """Check each file and add it (the Add button and drag and drop both come here)."""
        added: list[Path] = []
        messages: list[str] = []
        for path in paths:
            game = self._game_of(path)
            if game is None:
                messages.append(f"{path.name}: not a translation for Fish Tycoon or Plant Tycoon (format 1).")
                continue
            try:
                target, report = tr.install_file(path, game, self.entries(game, ask=False), self.folder)
            except tr.TranslationProblem as exc:
                messages.append(f"{path.name}: {exc}")
                continue
            added.append(target)
            messages.append(f"{path.name}: added for {GAMES[game]} as {target.name}.\n{report.summary()}")
        if paths:
            self.refresh()
            messagebox.showinfo(TITLE, "\n\n".join(messages)[:6000], parent=self.window)
        return added

    @staticmethod
    def _game_of(path: Path) -> str | None:
        try:
            data = path.read_bytes() if path.stat().st_size <= tr.MAX_FILE else b""
        except OSError:
            return None
        parsed = tfmt.parse_bytes(data)
        title = parsed.game.strip()
        return next((g for g, t in GAMES.items() if t == title), None)

    def check(self) -> str:
        item = self.selected()
        if item is None:
            messagebox.showinfo(TITLE, CHOOSE_ONE, parent=self.window)
            return ""
        parsed = tfmt.parse_bytes(item.path.read_bytes(), self.game)
        summary = tfmt.validate(parsed, self.entries(self.game, ask=False)).summary()
        messagebox.showinfo(TITLE, summary[:6000], parent=self.window)
        return summary

    def export(self) -> list[Path]:
        """Export translation...: one selected file to a name of the player's choice; several, one file
        each (under their own names) into a folder the player chooses."""
        items = self.selected_items()
        if not items and not self.listbox.curselection() and len(self.items) == 1:
            items = list(self.items)
        if not items:
            messagebox.showinfo(TITLE, "Choose the translation(s) to export in the list first.", parent=self.window)
            return []
        if len(items) == 1:
            name = filedialog.asksaveasfilename(parent=self.window, title="Export translation",
                                                initialfile=items[0].path.name, defaultextension=".txt",
                                                filetypes=(("Translation files", "*.txt"),))
            return [tr.export_file(items[0].path, Path(name))] if name else []
        folder = filedialog.askdirectory(parent=self.window, title=f"Export {len(items)} translations into")
        if not folder:
            return []
        targets = [(item.path, Path(folder) / item.path.name) for item in items]
        targets = [(s, t) for s, t in targets if t.resolve() != s.resolve()]
        existing = [t.name for _s, t in targets if t.exists()]
        if existing and not messagebox.askyesno(
                TITLE, "These files are already in that folder:\n\n" + "\n".join(existing)
                + "\n\nReplace them? (No exports only the others.)", default="no", parent=self.window):
            targets = [(s, t) for s, t in targets if t.name not in existing]
        exported: list[Path] = []
        problems: list[str] = []
        for source, target in targets:
            try:
                exported.append(tr.export_file(source, target))
            except OSError as exc:
                problems.append(f"{source.name}: {exc.strerror or exc}")
        message = f"Exported {len(exported)} file(s) into {folder}."
        if problems:
            message += "\n\nNot exported:\n" + "\n".join(problems)
        messagebox.showinfo(TITLE, message, parent=self.window)
        return exported

    # ---------------------------------------------------------------- deleting
    def delete_prompt(self, items: list[tr.Installed], english: bool, active: tr.Installed | None) -> str:
        game = GAMES[self.game]
        lines = [f"Move {len(items)} translation file(s) for {game} to the Recycle Bin?", ""]
        lines += [f"  {item.path.name}" + ("   (came with the patcher)" if item.shipped else "") for item in items]
        if english:
            lines += ["", f"{ENGLISH} is built into the game and cannot be deleted: it is skipped."]
        if any(item.shipped for item in items):
            lines += ["", "Translations that came with the patcher are deleted from your copy only: they come "
                          "back with the next patcher update."]
        if active is not None:
            lines += ["", f"{game} uses {active.label} now: it goes back to {ENGLISH}."]
        lines += ["", "You can restore the files from the Recycle Bin."]
        return "\n".join(lines)

    def delete(self) -> list[Path]:
        """Delete...: the selected files go to the Recycle Bin after one Yes/No (No, the default, does
        nothing). English (original) is skipped; if the game uses a deleted file it goes back to English,
        exactly as choosing English does."""
        english = 0 in self.listbox.curselection()
        items = self.selected_items()
        if not items:
            text = "Choose the translation(s) to delete in the list first."
            if english:
                text = f"{ENGLISH} is built into the game and cannot be deleted. " + text
            messagebox.showinfo(TITLE, text, parent=self.window)
            return []
        game = self.game
        chosen = tr.chosen_path(game, tr.load_choices(self.choices_path), self.folder)
        active = next((i for i in items if chosen is not None and i.path.resolve() == chosen.resolve()), None)
        if not messagebox.askyesno(TITLE, self.delete_prompt(items, english, active), default="no", icon="warning",
                                   parent=self.window):
            return []
        try:
            removed = tr.recycle([item.path for item in items])
        except OSError as exc:
            messagebox.showerror(TITLE, f"Could not move the files to the Recycle Bin: {exc}\n\nNothing was deleted.",
                                 parent=self.window)
            self.refresh()
            return []
        gone = {Path(p).resolve() for p in removed}
        for editor in [e for e in self.editors if e.path.resolve() in gone]:
            editor.discard()                    # saving it later would bring the file back
            self.editors.remove(editor)
        self.refresh()
        if active is not None:                  # exactly what choosing English (original) does
            self.language_var.set(ENGLISH)
            self.choose()
        return list(removed)

    def open_folder(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["explorer", str(self.folder)])
        except OSError:
            pass

    # ---------------------------------------------------------------- sharing
    def share(self) -> str | None:
        """Share on GitHub...: the owner's Yes/No first (No does nothing), the credit name typed by the
        player, then the file exported, shown in its folder, and GitHub's form opened."""
        if not messagebox.askyesno("Share on GitHub", tr.SHARE_CONFIRMATION, default="no", icon="warning",
                                   parent=self.window):
            return None
        item = self.selected()
        if item is None:
            messagebox.showinfo(TITLE, "Choose your translation in the list first, then press Share on GitHub... "
                                       "again.", parent=self.window)
            return None
        name = CreditDialog(self.window).result
        if name is None:
            return None
        try:
            name = tr.check_credit_name(name)
        except tr.TranslationProblem as exc:
            messagebox.showerror(TITLE, str(exc), parent=self.window)
            return None
        game = self.game
        parsed = tfmt.parse_bytes(item.path.read_bytes(), game)
        report = tfmt.validate(parsed, self.entries(game, ask=False))
        if not report.usable:
            messagebox.showerror(TITLE, "This file cannot be shared:\n\n" + report.summary()[:4000], parent=self.window)
            return None
        shared = self.folder / "Shared"
        shared.mkdir(parents=True, exist_ok=True)
        target = shared / item.path.name
        tr.export_file(item.path, target)
        tr.set_credit(target, name)
        url = tr.issue_url(game, item.language or item.path.stem.split(" - ", 1)[-1], report.coverage)
        self._show_in_folder(target)
        webbrowser.open(url)
        messagebox.showinfo(TITLE, f"{target.name} is ready in its folder (now open). On the GitHub page that "
                                   "opened, drag the file into the form and press Submit.", parent=self.window)
        return url

    def download_from_github(self) -> "DownloadDialog":
        """Download from GitHub...: the translations shared in the public folder, read-only."""
        return DownloadDialog(self.window, self.game, self.folder, on_done=self.refresh)

    @staticmethod
    def _show_in_folder(path: Path) -> None:
        try:
            subprocess.Popen(["explorer", "/select,", str(path)])
        except OSError:
            pass

    # ---------------------------------------------------------------- the rest
    def show_guide(self) -> tk.Toplevel:
        window = tk.Toplevel(self.window)
        window.title("How to use: Translations")
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=HELP[0], font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        for line in HELP[1]:
            ttk.Label(frame, text=line, wraplength=520, justify="left").pack(anchor="w", pady=(0, 6))
        link = tk.Label(frame, text="Create a GitHub account: " + tr.SIGNUP_URL, foreground="#0057c2", cursor="hand2")
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda _e: webbrowser.open(tr.SIGNUP_URL))
        ttk.Button(frame, text="Close", command=window.destroy).pack(anchor="e", pady=(8, 0))
        return window

    def close(self) -> None:
        for editor in self.editors:
            editor.save()
        self.drop.remove()
        self.window.destroy()


class CreditDialog:
    """The credit name: typed by the player, required, never filled in (not from git, Windows,
    GitHub or a save). result is the typed text, or None when cancelled."""

    test_answer = None          # tests only: a function that types into the dialog instead of the player

    def __init__(self, master) -> None:
        self.result: str | None = None
        win = self.window = tk.Toplevel(master)
        win.title("Credit name")
        win.transient(master)
        frame = ttk.Frame(win, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Credit name (required):", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.var = tk.StringVar(master=win, value="")
        self.entry = ttk.Entry(frame, textvariable=self.var, width=40)
        self.entry.pack(anchor="w", pady=(4, 4))
        ttk.Label(frame, text=tr.CREDIT_HINT, wraplength=420, foreground="#a33").pack(anchor="w")
        self.error = tk.StringVar(master=win, value="")
        ttk.Label(frame, textvariable=self.error, foreground="#c00", wraplength=420).pack(anchor="w")
        row = ttk.Frame(frame)
        row.pack(anchor="e", pady=(8, 0))
        ttk.Button(row, text="OK", command=self.ok).pack(side="left")
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="left", padx=(8, 0))
        win.bind("<Return>", lambda _e: self.ok())
        win.bind("<Escape>", lambda _e: win.destroy())
        self.entry.focus_set()
        if CreditDialog.test_answer is not None:
            CreditDialog.test_answer(self)
        else:
            win.grab_set()
            master.wait_window(win)

    def ok(self) -> None:
        try:
            self.result = tr.check_credit_name(self.var.get())
        except tr.TranslationProblem as exc:
            self.error.set(str(exc))
            return
        self.window.destroy()


class DownloadDialog:
    """Download from GitHub...: every translation in translations/<game>/ on the patcher's GitHub
    (the default branch), with its language and credit (read from the file once downloaded), the
    date it last changed there, and whether it is installed or has an update. Several can be chosen;
    each is checked as data before it is installed (translations_github.download)."""

    COLUMNS = (("language", "Language", 170), ("credit", "Credit", 150), ("changed", "Last changed", 100),
               ("status", "Status", 120), ("file", "File", 110))

    def __init__(self, master, game: str, folder: Path, on_done=None, threaded: bool = True, opener=None) -> None:
        self.game = game
        self.folder = folder
        self.on_done = on_done
        self.threaded = threaded
        self.opener = opener
        self.rows: list[tgh.Row] = []
        self.results: queue.Queue = queue.Queue()
        win = self.window = tk.Toplevel(master)
        win.title(f"Download from GitHub - {GAMES[game]}")
        win.transient(master)
        win.geometry("720x380")
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, wraplength=690, justify="left", text=(
            f"Translations shared on the patcher's GitHub (translations/{game}/). Choose one or more (Ctrl or "
            "Shift click) and press Download: each file is checked before it is installed. Nothing about you "
            "is sent and no GitHub account is needed.")).pack(anchor="w")
        self.tree = ttk.Treeview(frame, columns=[c for c, _t, _w in self.COLUMNS], show="headings",
                                 selectmode="extended", height=10)
        for column, title, width in self.COLUMNS:
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, stretch=True)
        self.tree.pack(fill="both", expand=True, pady=(8, 0))
        self.status = tk.StringVar(master=win, value="")
        ttk.Label(frame, textvariable=self.status, wraplength=690, foreground="#245a9a").pack(anchor="w", pady=(6, 0))
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Download", command=self.download_selected).pack(side="left")
        ttk.Button(row, text="Refresh", command=self.refresh).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Close", command=win.destroy).pack(side="right")
        win.bind("<Escape>", lambda _e: win.destroy())
        self.refresh()

    def load(self):
        """The list from GitHub (run in a thread): rows, or the problem to show."""
        try:
            remotes = tgh.list_remote(self.game, opener=self.opener)
            for remote in remotes:
                remote.changed = tgh.last_changed(remote, opener=self.opener)
            return remotes
        except tgh.GitHubProblem as exc:
            return exc

    def refresh(self) -> None:
        self.status.set("Asking GitHub...")
        if not self.threaded:
            self.loaded(self.load())
            return
        threading.Thread(target=lambda: self.results.put(self.load()), daemon=True).start()
        self.window.after(100, self._poll)

    def _poll(self) -> None:
        if not self.window.winfo_exists():
            return
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            self.window.after(100, self._poll)
            return
        self.loaded(result)

    def loaded(self, result) -> None:
        if not self.window.winfo_exists():
            return
        if isinstance(result, Exception):
            self.status.set(str(result))
            return
        self.rows = [tgh.row(remote, self.folder) for remote in result]
        self.fill()
        self.status.set(f"{len(self.rows)} translation(s) for {GAMES[self.game]} on GitHub." if self.rows else
                        f"No translation for {GAMES[self.game]} has been shared on GitHub yet.")

    def fill(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for n, item in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(n), values=(item.language, item.credit or "-",
                                                            item.remote.changed or "unknown", item.status,
                                                            item.remote.name))

    def download_selected(self) -> list[Path]:
        chosen = [self.rows[int(i)] for i in self.tree.selection() if i.isdigit() and int(i) < len(self.rows)]
        if not chosen:
            messagebox.showinfo(TITLE, "Choose one or more translations in the list first.", parent=self.window)
            return []
        saved: list[Path] = []
        messages: list[str] = []
        self.window.configure(cursor="watch")
        self.window.update_idletasks()
        try:
            for item in chosen:
                try:
                    saved.append(tgh.download(item.remote, self.folder, opener=self.opener))
                    messages.append(f"{item.remote.name}: installed.")
                except tgh.GitHubProblem as exc:
                    messages.append(str(exc))
        finally:
            self.window.configure(cursor="")
        self.rows = [tgh.row(item.remote, self.folder) for item in self.rows]
        self.fill()
        if self.on_done is not None:
            self.on_done()
        messagebox.showinfo(TITLE, "\n\n".join(messages)[:6000], parent=self.window)
        return saved


# --------------------------------------------------------------------------- the editor

PLACEHOLDER_RE = re.compile(tfmt.CONVERSION_RE.pattern + r"|\{[^{}]*\}")


class TranslationEditor:
    STATUS = {"new": "untranslated", "done": "translated", "error": "check it", "changed": "English changed",
              "old": "not in this version"}

    def __init__(self, master, game: str, path: Path, entries: list[tfmt.Entry] | None, folders: list[str],
                 on_save=None) -> None:
        self.game, self.path, self.on_save = game, Path(path), on_save
        self.entries = {e.key: e for e in (entries or [])}
        self.dirty = False
        self._after = None
        self.fonts = None
        self.font_folder = None
        self.file = tfmt.parse_bytes(self.path.read_bytes(), game)
        self.update_note = ""
        if entries and not self.file.fatal:
            report = tfmt.update_to_inventory(self.file, entries)
            if report.added or report.changed:
                self.update_note = (f"{len(report.added)} new line(s) and {len(report.changed)} with changed English "
                                    "since this file was made are marked untranslated.")
                self.dirty = True
        self.bases = {tfmt.base_key(k) for k in self.entries}
        self.font_candidates = folders

        win = self.window = tk.Toplevel(master)
        win.title(f"Translation editor - {self.path.name}")
        win.geometry("1100x780")
        win.minsize(820, 560)
        frame = ttk.Frame(win, padding=8)
        frame.pack(fill="both", expand=True)
        if self.file.fatal:
            ttk.Label(frame, text="This file cannot be edited here: " + self.file.fatal, foreground="#c00",
                      wraplength=900).pack(anchor="w")
            return

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        self.search = tk.StringVar(master=win, value="")
        entry = ttk.Entry(top, textvariable=self.search, width=30)
        entry.pack(side="left", padx=(4, 12))
        self.search.trace_add("write", lambda *_a: self.fill())
        self.untranslated_only = tk.BooleanVar(master=win, value=False)
        ttk.Checkbutton(top, text="Show untranslated only", variable=self.untranslated_only,
                        command=self.fill).pack(side="left")
        self.progress = tk.StringVar(master=win, value="")
        ttk.Label(top, textvariable=self.progress, font=("Segoe UI", 10, "bold")).pack(side="right")
        if self.update_note:
            ttk.Label(frame, text=self.update_note, foreground="#245a9a").pack(anchor="w")

        panes = ttk.PanedWindow(frame, orient="vertical")
        panes.pack(fill="both", expand=True, pady=(6, 0))
        table = ttk.Frame(panes)
        self.tree = ttk.Treeview(table, columns=("status", "english", "translation"), show="headings",
                                 selectmode="browse")
        for column, text, width in (("status", "Status", 120), ("english", "English", 440),
                                    ("translation", "Translation", 440)):
            self.tree.heading(column, text=text)
            self.tree.column(column, width=width, stretch=column != "status")
        bar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.tree.tag_configure("error", foreground="#c00")
        self.tree.tag_configure("changed", foreground="#a60")
        self.tree.tag_configure("old", foreground="#888")
        self.tree.tag_configure("group", foreground="#245a9a", font=("Segoe UI", 9, "bold"))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.show_row())
        panes.add(table, weight=3)

        edit = ttk.Frame(panes)
        self.notes = tk.StringVar(master=win, value="")
        ttk.Label(edit, textvariable=self.notes, foreground="#555", wraplength=1000).pack(anchor="w")
        ttk.Label(edit, text="English:").pack(anchor="w")
        self.english_text = tk.Text(edit, height=4, wrap="word", background="#f3f3f3")
        self.english_text.pack(fill="x")
        ttk.Label(edit, text="Translation:").pack(anchor="w", pady=(4, 0))
        self.translation_text = tk.Text(edit, height=5, wrap="word", undo=True)
        self.translation_text.pack(fill="x")
        for widget in (self.english_text, self.translation_text):
            widget.tag_configure("placeholder", foreground="#0057c2", background="#e6efff")
        self.translation_text.bind("<KeyRelease>", lambda _e: self.changed())
        self.translation_text.bind("<<Paste>>", lambda _e: self.window.after(1, self.changed))
        tools = ttk.Frame(edit)
        tools.pack(fill="x", pady=(4, 0))
        ttk.Button(tools, text="Copy English", command=self.copy_english).pack(side="left")
        ttk.Button(tools, text="Wrap to fit", command=self.wrap_selected).pack(side="left", padx=(12, 0))
        ttk.Button(tools, text="Wrap all", command=self.wrap_all).pack(side="left", padx=(4, 0))
        self.undo_button = ttk.Button(tools, text="Undo wrap", command=self.undo_wrap, state="disabled")
        self.undo_button.pack(side="left", padx=(4, 0))
        self.insert_row = ttk.Frame(tools)
        self.insert_row.pack(side="left", padx=(12, 0))
        self.message = tk.StringVar(master=win, value="")
        self.message_label = ttk.Label(edit, textvariable=self.message, wraplength=1000)
        self.message_label.pack(anchor="w", pady=(4, 0))
        self.preview_note = tk.StringVar(master=win, value="")
        ttk.Label(edit, textvariable=self.preview_note, foreground="#555").pack(anchor="w")
        self.preview = tk.Label(edit, background="#18284a")
        self.preview.pack(anchor="w", pady=(2, 0))
        panes.add(edit, weight=2)

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", pady=(6, 0))
        self.saved = tk.StringVar(master=win, value="Saved automatically.")
        ttk.Label(bottom, textvariable=self.saved, foreground="#555").pack(side="left")
        ttk.Button(bottom, text="Close", command=self.close).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", self.close)

        self.current: tfmt.Row | None = None
        self.wrap_undo: list[tuple[tfmt.Row, str]] = []
        self.fill()
        if self.dirty:
            self.save()

    # ---------------------------------------------------------------- rows
    def status(self, row: tfmt.Row) -> str:
        if self.entries and row.key not in self.entries:
            return "changed" if tfmt.base_key(row.key) in self.bases else "old"
        if not row.translation:
            return "new"
        errors, _w = tfmt.check_translation(row.english, row.translation, self.file.code)
        entry = self.entries.get(row.key)
        if errors or (entry and entry.max_length and tfmt.too_long(row.translation, entry.max_length, entry.wide, entry.english, entry.is_format)):
            return "error"
        return "done"

    def fill(self) -> None:
        if not hasattr(self, "tree"):
            return
        query = self.search.get().casefold()
        self.tree.delete(*self.tree.get_children())
        self.visible: dict[str, tfmt.Row] = {}
        shown: list[tuple[str, int, tfmt.Row, str]] = []
        for n, row in enumerate(self.file.rows):
            status = self.status(row)
            if self.untranslated_only.get() and status not in ("new", "error"):
                continue
            if query and query not in row.english.casefold() and query not in row.translation.casefold() \
                    and query not in row.key.casefold():
                continue
            entry = self.entries.get(row.key)
            shown.append((tstr.group_of(entry.notes if entry else row.notes), n, row, status))
        # Grouped by patch ("Patch: ..." in the notes), the game's own lines first, each group headed.
        order: dict[str, int] = {"": -1}
        for group, *_rest in shown:
            order.setdefault(group, len(order))
        shown.sort(key=lambda item: (order[item[0]], item[1]))
        last = None
        for group, n, row, status in shown:
            if group != last:
                last = group
                self.tree.insert("", "end", iid=f"g{n}", tags=("group",),
                                 values=("", f"— {('Patch: ' + group) if group else 'The game'} —", ""))
            iid = f"r{n}"
            self.visible[iid] = row
            self.tree.insert("", "end", iid=iid, values=(self.STATUS[status], _one_line(row.english),
                                                         _one_line(row.translation)), tags=(status,))
        self.update_progress()

    def update_progress(self) -> None:
        rows = [r for r in self.file.rows if not self.entries or r.key in self.entries]
        done = sum(1 for r in rows if self.status(r) == "done")
        percent = 100.0 * done / len(rows) if rows else 0.0
        self.progress.set(f"{done} of {len(rows)} lines translated ({percent:.0f}%)")

    def show_row(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.current = self.visible.get(selection[0])
        if self.current is None:
            return
        row = self.current
        entry = self.entries.get(row.key)
        notes = row.notes or (entry.notes if entry else "")
        self.notes.set(f"{row.key}   {notes}")
        for widget, text in ((self.english_text, row.english), (self.translation_text, row.translation)):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
            self._mark(widget)
        self.english_text.configure(state="disabled")
        for child in self.insert_row.winfo_children():
            child.destroy()
        template = tfmt.parse_template(row.english)
        tokens = [c.text for c in template.conversions] + ["{" + v + "}" for v in sorted(template.variables)]
        for token in tokens:
            ttk.Button(self.insert_row, text=f"Insert {token}", command=lambda t=token: self.insert(t)).pack(side="left", padx=(0, 4))
        numbers = [n for n, c in enumerate(template.conversions, 1) if c.is_number]
        if numbers:
            snippet = f"{{%{numbers[0]}: one=... | other=...}}"
            ttk.Button(self.insert_row, text="Insert a number choice",
                       command=lambda s=snippet: self.insert(s)).pack(side="left", padx=(0, 4))
        self.validate()
        self.schedule_preview()

    def _mark(self, widget: tk.Text) -> None:
        widget.tag_remove("placeholder", "1.0", "end")
        text = widget.get("1.0", "end-1c")
        for match in PLACEHOLDER_RE.finditer(text):
            widget.tag_add("placeholder", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    def insert(self, token: str) -> None:
        self.translation_text.insert("insert", token)
        self.changed()

    def copy_english(self) -> None:
        if self.current is None:
            return
        self.translation_text.delete("1.0", "end")
        self.translation_text.insert("1.0", self.current.english)
        self.changed()

    def changed(self) -> None:
        if self.current is None:
            return
        text = self.translation_text.get("1.0", "end-1c")
        if text == self.current.translation:
            return
        self.current.translation = text
        self._mark(self.translation_text)
        status = self.status(self.current)
        iid = next((i for i, r in self.visible.items() if r is self.current), None)
        if iid is not None:
            self.tree.item(iid, values=(self.STATUS[status], _one_line(self.current.english), _one_line(text)),
                           tags=(status,))
        self.validate()
        self.update_progress()
        self.dirty = True
        self.saved.set("Unsaved changes...")
        if self._after is not None:
            self.window.after_cancel(self._after)
        self._after = self.window.after(AUTOSAVE_MS, self.save)
        self.schedule_preview()

    def validate(self) -> list[str]:
        row = self.current
        if row is None:
            return []
        errors, warnings = tfmt.check_translation(row.english, row.translation, self.file.code)
        entry = self.entries.get(row.key)
        if row.translation and entry and entry.max_length and tfmt.too_long(row.translation, entry.max_length, entry.wide, entry.english, entry.is_format):
            errors.append(tfmt.too_long_message(entry.max_length))
        if tfmt.contains_email(row.translation):
            errors.append(tfmt.EMAIL_MESSAGE)
        if any(ord(c) > 0xFF and c not in "€‚ƒ„…†‡ˆ‰Š‹Œ"
               "Ž‘’“”•–—˜™š›œžŸ"
               for c in row.translation):
            warnings.append("some letters are outside Latin-1: the game shows them with the patcher's Unicode font "
                            "setting on, and as ? without it")
        if errors:
            self.message.set("This line will show English: " + "; ".join(errors))
            self.message_label.configure(foreground="#c00")
        elif warnings:
            self.message.set("Note: " + "; ".join(warnings))
            self.message_label.configure(foreground="#a60")
        else:
            self.message.set("OK" if row.translation else "Not translated yet (the game shows the English).")
            self.message_label.configure(foreground="#2a7a2a")
        return errors

    # ---------------------------------------------------------------- the preview
    def schedule_preview(self) -> None:
        self.window.after(150, self.render_preview)

    def game_font(self):
        """The game's first font, for measuring and the preview (None when no copy of the game is found)."""
        import text_maker as tm
        if self.fonts is None:
            folder = tm.find_game_folder(self.game, self.font_candidates)
            self.fonts = tm.load_fonts(self.game, folder) if folder else []
        return self.fonts[0] if self.fonts else None

    def measure_line(self, text: str) -> int:
        """Pixels a line is wide as the game draws it (the Text Maker's layout, placeholders filled in)."""
        import text_maker as tm
        return tm.layout(self.game_font(), tfmt.evaluate(text))[1]

    def render_preview(self) -> None:
        row = self.current
        if row is None or not self.window.winfo_exists():
            return
        try:
            import text_maker as tm
            font = self.game_font()
            if font is None:
                self.preview_note.set("Preview: no copy of the game with its fonts was found (the One Game tab's folders).")
                return
            text = tfmt.evaluate(row.translation or row.english)
            image = tm.render(font, text, 0xFFFFFF, "Shadow", 1, (24, 40, 72))
            self._photo = image.photo(tk, self.window, max_side=1000)
            self.preview.configure(image=self._photo)
            note = f"Preview in {font.label}"
            if row.translation:
                have = twrap.english_width(row.translation, self.measure_line)
                room = twrap.english_width(row.english, self.measure_line)
                if have > room:
                    note += (f" -- a line is wider than the English's widest ({have} vs {room} pixels): "
                             "it may not fit its space. Wrap to fit re-breaks it.")
            self.preview_note.set(note)
        except Exception as exc:  # the preview never stops the editor
            self.preview_note.set(f"Preview unavailable ({exc.__class__.__name__}).")

    # ---------------------------------------------------------------- wrap to fit
    def wrap_row(self, row: tfmt.Row) -> twrap.WrapResult | None:
        """The row's translation re-broken to the widest line of its English (None without a game font)."""
        if self.game_font() is None:
            return None
        room = twrap.english_width(row.english, self.measure_line)
        return twrap.wrap(row.translation, room, self.measure_line)

    def _set_translation(self, row: tfmt.Row, text: str) -> None:
        if row is self.current:
            self.translation_text.edit_separator()
            self.translation_text.delete("1.0", "end")
            self.translation_text.insert("1.0", text)
            self.translation_text.edit_separator()
            self.changed()
        else:
            row.translation = text
            self.dirty = True
            self.saved.set("Unsaved changes...")
            if self._after is not None:
                self.window.after_cancel(self._after)
            self._after = self.window.after(AUTOSAVE_MS, self.save)

    @staticmethod
    def _wrap_report(results: list[twrap.WrapResult]) -> str:
        cannot = [run for r in results for run in r.cannot_wrap]
        cut = sum(r.cut for r in results)
        parts = []
        if cut:
            parts.append(f"{cut} word(s) wider than the room were cut")
        if cannot:
            parts.append(f"cannot wrap (no spaces, no word list): {', '.join(cannot[:3])}")
        return "; ".join(parts)

    def wrap_note(self, text: str) -> None:
        self.preview_note.set(text)

    def wrap_selected(self) -> str:
        row = self.current
        if row is None or not row.translation:
            self.wrap_note("Select a translated line first.")
            return ""
        result = self.wrap_row(row)
        if result is None:
            self.wrap_note("Wrap needs a copy of the game with its fonts (the One Game tab's folders).")
            return ""
        if result.text == row.translation.replace("\r\n", "\n"):
            self.wrap_note(("Already fits. " if not result.cannot_wrap else "") + self._wrap_report([result]))
            return row.translation
        self.wrap_undo = [(row, row.translation)]
        self.undo_button.configure(state="normal")
        self._set_translation(row, result.text)
        self.wrap_note("Wrapped. " + self._wrap_report([result]))
        return result.text

    def wide_rows(self) -> list[tfmt.Row]:
        """Rows (all of the file, not just the filter) whose translation is wider than its English."""
        if self.game_font() is None:
            return []
        return [r for r in self.file.rows if not r.is_info and r.translation
                and (not self.entries or r.key in self.entries)
                and twrap.needs_wrap(r.translation, r.english, self.measure_line)]

    def wrap_all(self) -> int:
        if self.game_font() is None:
            self.wrap_note("Wrap needs a copy of the game with its fonts (the One Game tab's folders).")
            return 0
        rows = self.wide_rows()
        if not rows:
            messagebox.showinfo("Wrap all", "No translation is wider than its English.", parent=self.window)
            return 0
        if not messagebox.askyesno("Wrap all", f"{len(rows)} line(s) are wider than their English. Re-break "
                                   "them to fit? Only line breaks and spaces change; Undo wrap takes it back.",
                                   parent=self.window):
            return 0
        undo, results = [], []
        for row in rows:
            result = self.wrap_row(row)
            if result is not None and result.text != row.translation:
                undo.append((row, row.translation))
                results.append(result)
                self._set_translation(row, result.text)
        self.wrap_undo = undo
        self.undo_button.configure(state="normal" if undo else "disabled")
        self.fill()
        self.update_progress()
        self.wrap_note(f"Wrapped {len(undo)} line(s). " + self._wrap_report(results))
        return len(undo)

    def undo_wrap(self) -> int:
        undo, self.wrap_undo = self.wrap_undo, []
        for row, old in undo:
            self._set_translation(row, old)
        self.undo_button.configure(state="disabled")
        if undo:
            self.fill()
            self.update_progress()
            self.wrap_note(f"Undid the wrap of {len(undo)} line(s).")
        return len(undo)

    # ---------------------------------------------------------------- saving
    def save(self) -> None:
        if self.file.fatal or not self.dirty:
            return
        self._after = None
        try:
            self.path.write_bytes(tfmt.to_bytes(self.file))
            self.dirty = False
            if hasattr(self, "saved"):
                self.saved.set(f"Saved {self.path.name}.")
            if self.on_save:
                self.on_save(self.path)
        except OSError as exc:
            if hasattr(self, "saved"):
                self.saved.set(f"Could not save: {exc.strerror or exc}")

    def close(self) -> None:
        self.save()
        self.window.destroy()

    def discard(self) -> None:
        """Its file was deleted: close without saving (saving would bring the file back)."""
        self.dirty = False
        if self._after is not None:
            try:
                self.window.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        if self.window.winfo_exists():
            self.window.destroy()


def open_window(master, game: str | None, folders: dict[str, list]) -> TranslationsWindow:
    return TranslationsWindow(master, game if game in GAMES else None, folders)
