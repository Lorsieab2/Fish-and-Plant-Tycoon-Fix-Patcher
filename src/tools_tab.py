"""The Tools tab and its windows, laid out and working like the Virtual
Villagers Fun Patcher's (src/vv_fun_patcher_gui.py there: _build_tools_tab,
Back Up Saves, Restore Saves, Rename Tribe), for one consistent tool across
the owner's patchers:

* "The game chosen on the One Game tab": Back Up Saves, Restore Saves...,
  Rename Players..., Game Mechanics..., Breeding Guide... and Picture
  Studio..., each a link with a "?" guide.
* "Each game": the same six for Fish Tycoon and Plant Tycoon, one row per
  game, then Back Up Saves (Both)..., Rename Players..., Game Mechanics...,
  Breeding Guide... and Picture Studio... buttons.
* Back Up Saves lists the game's modded save folders (ticked: the patcher's
  own) and backs the ticked ones up, pausing a running game; Restore Saves
  lists every backup of the game, newest first, to restore whole or one slot,
  or delete; Rename Players picks the game, save folder and player.

The work itself is in save_backup.py and save_tools.py.
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import zipfile

import breeding_guide
import picture_studio
import save_backup
import save_tools

GAMES = {"fish": "Fish Tycoon", "plant": "Plant Tycoon"}
LINK = {"foreground": "#0057c2", "cursor": "hand2", "font": ("Segoe UI", 9, "underline")}

# The "?" guides, one per tool (VV: data/how_to_use.json).
HELP = {
    "back_up_saves": (
        "Back Up Saves",
        [
            "Copies a modded copy's save folder into a new dated folder inside it: "
            "<save folder>\\Backups\\Backup <date and time>.",
            "Everything is copied: the game's saves and the patcher's own files for each player. "
            "Every copy is read back and checked against the original (size and SHA-256), and keeps "
            "the original's times. A copy that fails is kept as \"INCOMPLETE\" and never offered.",
            "If the game is running, it is paused for the copy (a moment) and then resumes by itself. "
            "Both games save when you quit and autosave while running, so a backup of a running game "
            "holds its last save or autosave; quit the game first to back up the very latest.",
            "The window lists the game's modded save folders; the patcher's own (\"- Modded\" and "
            "\"- Modded Upgrades\") are ticked.",
        ],
    ),
    "restore_saves": (
        "Restore Saves",
        [
            "Lists every backup of the game, newest first, with the players each one holds.",
            "Restore puts back the whole save folder, or one player only (that player's save files, "
            "the patcher's files for that player, and the player's name in the player list). It tells "
            "you exactly which files it will replace, add and remove before it starts.",
            "The game must be closed. Your saves as they are now are backed up first, as "
            "\"Backup <date> (before restore)\", so a restore can always be undone.",
            "Delete Backup removes one backup for good. Import Older .zip Backup adds a zip backup made "
            "by v1.0.17 to the list.",
        ],
    ),
    "rename_players": (
        "Rename Players",
        [
            "Changes a player's name in the game's player list and inside that player's own save files.",
            "Only players with a saved game can be renamed, and \"NEW PLAYER\" is not a name (the game "
            "uses it for empty slots). Up to 31 plain characters, as in the game.",
            "The game must be closed: it saves when you quit, which would put the old name back. The "
            "save folder is backed up first, as \"Backup <date> (before rename)\".",
        ],
    ),
    "game_mechanics": (
        "Game Mechanics",
        [
            "A read-only page with a tab for each game: time and time away, health, food, sickness, "
            "breeding, eggs and seeds, the store items, research, selling, magic fish and plants, and an "
            "index of every random roll and timer.",
            "Every line is labelled: VERIFIED-E means the game's code was run and counted exactly, "
            "VERIFIED-C means it was read in the game's code, and UNCONFIRMED marks estimates. Where one "
            "of this patcher's settings changes a fact, a \"With the patcher\" line says how.",
            "It never opens or changes a save or game file.",
        ],
    ),
    "breeding_guide": breeding_guide.HELP,
    "picture_studio": picture_studio.HELP,
}


class ToolsTab:
    def __init__(self, app, tab: ttk.Frame) -> None:
        self.app = app
        self.help_windows: dict[str, tk.Toplevel] = {}
        self.chosen_text = tk.StringVar(master=tab)
        self._build(tab)
        app.game_choice.trace_add("write", lambda *_a: self._show_chosen())
        self._show_chosen()

    # ------------------------------------------------------------------ layout

    def _link(self, parent, text: str, command) -> tk.Label:
        label = tk.Label(parent, text=text, **LINK)
        label.bind("<Button-1>", lambda _e: command())
        return label

    def _help(self, parent, key: str) -> ttk.Button:
        return ttk.Button(parent, text="?", width=2, command=lambda: self.show_help(key))

    def _build(self, tab: ttk.Frame) -> None:
        box = ttk.LabelFrame(tab, text="The game chosen on the One Game tab", padding=10)
        box.pack(fill="x")
        ttk.Label(box, textvariable=self.chosen_text, foreground="#245a9a").pack(anchor="w")
        links = ttk.Frame(box)
        links.pack(anchor="w", pady=(6, 0))
        for index, (text, key, command) in enumerate((
            ("Back Up Saves", "back_up_saves", lambda: self.back_up([self.app.game_choice.get()])),
            ("Restore Saves...", "restore_saves", lambda: self.restore(self.app.game_choice.get())),
            ("Rename Players...", "rename_players", lambda: self.rename(self.app.game_choice.get())),
            ("Game Mechanics...", "game_mechanics", lambda: self.mechanics(self.app.game_choice.get())),
            ("Breeding Guide...", "breeding_guide", lambda: self.breeding(self.app.game_choice.get())),
            ("Picture Studio...", "picture_studio", lambda: self.studio(self.app.game_choice.get())),
        )):
            self._link(links, text, command).pack(side="left", padx=(0 if index == 0 else 18, 0))
            self._help(links, key).pack(side="left", padx=(3, 0))

        box = ttk.LabelFrame(tab, text="Each game (their folders on the One Game and Both Games tabs)", padding=10)
        box.pack(fill="x", pady=(10, 0))
        grid = ttk.Frame(box)
        grid.pack(anchor="w")
        columns = (
            ("back_up_saves", "Back up saves", lambda game: self.back_up([game])),
            ("restore_saves", "Restore saves...", self.restore),
            ("rename_players", "Rename players...", self.rename),
            ("game_mechanics", "Game mechanics...", self.mechanics),
            ("breeding_guide", "Breeding guide...", self.breeding),
            ("picture_studio", "Picture studio...", self.studio),
        )
        for column, (key, _text, _command) in enumerate(columns, start=1):
            self._help(grid, key).grid(row=0, column=column, padx=(12, 0), pady=(0, 2))
        for row, (game_id, title) in enumerate(GAMES.items(), start=1):
            ttk.Label(grid, text=f"{row}. {title}").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            for column, (_key, text, command) in enumerate(columns, start=1):
                self._link(grid, text, lambda c=command, g=game_id: c(g)).grid(
                    row=row, column=column, padx=(12, 0), pady=2)
        buttons = ttk.Frame(box)
        buttons.pack(fill="x", pady=(10, 0))
        for index, (text, key, command) in enumerate((
            ("Back Up Saves (Both)...", "back_up_saves", lambda: self.back_up(list(GAMES))),
            ("Rename Players...", "rename_players", lambda: self.rename(None)),
            ("Game Mechanics...", "game_mechanics", lambda: self.mechanics(None)),
            ("Breeding Guide...", "breeding_guide", lambda: self.breeding(None)),
            ("Picture Studio...", "picture_studio", lambda: self.studio(None)),
        )):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0 if index == 0 else 8, 0))
            self._help(buttons, key).pack(side="left", padx=(2, 0))

    def _show_chosen(self) -> None:
        self.chosen_text.set(GAMES.get(self.app.game_choice.get(), "No game chosen yet"))

    # -------------------------------------------------------------------- help

    def show_help(self, key: str) -> tk.Toplevel:
        window = self.help_windows.get(key)
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            return window
        title, lines = HELP[key]
        window = tk.Toplevel(self.app)
        window.title(f"How to use: {title}")
        window.transient(self.app)
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=title, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        for line in lines:
            ttk.Label(frame, text=line, wraplength=480, justify="left").pack(anchor="w", pady=(0, 6))
        ttk.Button(frame, text="Close", command=window.destroy).pack(anchor="e", pady=(6, 0))
        window.bind("<Escape>", lambda _e: window.destroy())
        self.help_windows[key] = window
        return window

    def _dialog(self, title: str) -> tuple[tk.Toplevel, ttk.Frame]:
        dialog = tk.Toplevel(self.app)
        dialog.title(title)
        dialog.transient(self.app)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        return dialog, frame

    def _log(self, text: str) -> None:
        self.app.log.insert("end", text)
        self.app.log.see("end")

    # --------------------------------------------------------------- back up

    def back_up(self, games: list[str]) -> None:
        found = [(game_id, folder) for game_id in games for folder in save_backup.find_save_folders(game_id)]
        if not found:
            names = " or ".join(GAMES[g] for g in games)
            messagebox.showinfo(
                "Back Up Saves",
                f"No modded save folders were found for {names} in {save_tools.ldw_folder()}.\n\n"
                "A modded copy makes its save folder the first time it is played.",
            )
            return
        dialog, frame = self._dialog("Back Up Saves")
        ttk.Label(frame, text="Choose the save folders to back up:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=("Each folder is copied into a new dated folder inside it: <save folder>\\Backups\\Backup "
                  "<date and time>. If the game is running it is paused for the copy and then resumes by "
                  "itself; it holds its last save or autosave, so quit the game first to back up the very "
                  "latest."),
            wraplength=640, justify="left",
        ).pack(anchor="w", pady=(4, 10))
        choices: list[tuple[Path, tk.BooleanVar]] = []
        current = None
        for game_id, folder in found:
            if game_id != current:
                current = game_id
                ttk.Label(frame, text=GAMES[game_id]).pack(anchor="w", pady=(6, 0))
            label = folder.name
            try:
                if save_backup.game_running(folder):
                    label += "   (running: will be paused for the copy)"
            except save_backup.BackupError:
                pass
            var = tk.BooleanVar(master=frame, value=save_backup.is_patcher_save_folder(game_id, folder.name))
            ttk.Checkbutton(frame, text=label, variable=var).pack(anchor="w", padx=(14, 0))
            choices.append((folder, var))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(14, 0))

        def start() -> None:
            chosen = [folder for folder, var in choices if var.get()]
            if not chosen:
                messagebox.showinfo("Back Up Saves", "Tick at least one save folder.", parent=dialog)
                return
            dialog.destroy()
            self._run_backups(chosen)

        ttk.Button(buttons, text="Back Up Selected", command=start).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=(8, 0))
        dialog.grab_set()

    def _run_backups(self, folders: list[Path]) -> None:
        outcomes = []
        for folder in folders:
            try:
                outcomes.append((folder, save_backup.back_up_save_folder(folder), None))
            except (save_backup.BackupError, OSError) as exc:
                outcomes.append((folder, None, str(exc)))
        made = sum(1 for _f, result, _e in outcomes if result is not None)
        self.app.status_var.set(f"Back Up Saves: {made} of {len(outcomes)} save folder(s) backed up.")
        dialog, frame = self._dialog("Back Up Saves")
        for folder, result, error in outcomes:
            ttk.Label(frame, text=folder.name, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 0))
            if result is None:
                ttk.Label(frame, text=f"NOT backed up: {error}", wraplength=640, justify="left",
                          foreground="#a01010").pack(anchor="w", padx=(14, 0))
                continue
            lines = [
                f"Backed up {result.file_count} file(s), {save_backup.describe_size(result.total_bytes)}; every "
                "copy was checked against the original (size and SHA-256).",
                f"Backup folder: {result.backup_folder}",
            ]
            if result.paused:
                lines.append("The game was running: it was paused for the copy and resumed.")
            lines.extend(f"Warning: {problem}" for problem in result.resume_problems)
            for line in lines:
                ttk.Label(frame, text=line, wraplength=640, justify="left").pack(anchor="w", padx=(14, 0))
            self._log(f"\n=== Saves backed up ===\n{folder}\n-> {result.backup_folder}\n")
        ttk.Button(frame, text="Close", command=dialog.destroy).pack(anchor="w", pady=(14, 0))

    # --------------------------------------------------------------- restore

    def restore(self, game_id: str) -> None:
        folders = save_backup.find_save_folders(game_id)
        if not folders:
            messagebox.showinfo("Restore Saves", f"No modded save folders were found for {GAMES[game_id]}.")
            return
        title = GAMES[game_id]
        dialog, frame = self._dialog(f"Restore Saves - {title}")
        ttk.Label(frame, text="Choose a backup to restore:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=("Newest first. The game must be closed: quit it from its own menu before restoring. Your "
                  "saves as they are now are backed up first, as \"Backup <date> (before restore)\", so a "
                  "restore can be undone."),
            wraplength=720, justify="left",
        ).pack(anchor="w", pady=(4, 8))
        listbox = tk.Listbox(frame, width=115, height=12, exportselection=False, font=("Segoe UI", 9))
        listbox.pack(fill="both", expand=True)
        details = ttk.Label(frame, text="", wraplength=720, justify="left")
        details.pack(anchor="w", pady=(6, 0))
        scope = tk.StringVar(master=frame, value="whole")
        slot_choice = tk.StringVar(master=frame)
        options = ttk.Frame(frame)
        options.pack(anchor="w", pady=(8, 0))
        ttk.Radiobutton(options, text="The whole save folder", value="whole", variable=scope).grid(
            row=0, column=0, sticky="w")
        ttk.Radiobutton(options, text="One player only:", value="slot", variable=scope).grid(
            row=1, column=0, sticky="w")
        slots = ttk.Combobox(options, textvariable=slot_choice, state="readonly", width=40)
        slots.grid(row=1, column=1, sticky="w", padx=(8, 0))
        entries: list[tuple[Path, save_backup.BackupInfo]] = []

        def describe(folder: Path, info: save_backup.BackupInfo) -> str:
            variant = folder.name.removeprefix(f"{title} - ")
            return f"[{variant}]   {info.describe()}"

        def refresh() -> None:
            entries.clear()
            listbox.delete(0, "end")
            for folder in folders:
                for info in save_backup.list_backups(game_id, folder):
                    entries.append((folder, info))
            entries.sort(key=lambda item: item[1].when, reverse=True)
            for folder, info in entries:
                listbox.insert("end", describe(folder, info))
            if entries:
                listbox.selection_set(0)
            else:
                listbox.insert("end", "No backups yet. Use Back Up Saves to make one.")
            selected()

        def current():
            picked = listbox.curselection()
            return entries[picked[0]] if entries and picked else None

        def selected(_event=None) -> None:
            item = current()
            if item is None:
                details.configure(text="")
                slots.configure(values=[])
                slot_choice.set("")
                return
            details.configure(text=f"Backup folder: {item[1].folder}")
            values = [f"Player {slot}: {name}" for slot, name in item[1].players.items()]
            slots.configure(values=values)
            slot_choice.set(values[0] if values else "")

        def chosen_slot():
            if scope.get() != "slot":
                return None
            text = slot_choice.get()
            return int(text.split(":", 1)[0].removeprefix("Player ")) if text.startswith("Player ") else False

        def do_restore() -> None:
            item = current()
            if item is None:
                return
            slot = chosen_slot()
            if slot is False:
                messagebox.showinfo("Restore Saves", "This backup holds no player save to choose.", parent=dialog)
                return
            self._run_restore(dialog, game_id, item[0], item[1], slot)
            refresh()

        def delete() -> None:
            item = current()
            if item is None:
                return
            folder, info = item
            if not messagebox.askyesno(
                "Delete Backup",
                f"Delete this backup permanently?\n\n{describe(folder, info)}\n\n{info.folder}\n\n"
                "Your current saves are not affected.",
                parent=dialog, default="no",
            ):
                return
            try:
                save_backup.delete_backup(folder, info.folder)
            except (save_backup.BackupError, OSError) as exc:
                messagebox.showerror("Delete Backup", str(exc), parent=dialog)
            refresh()

        def import_zip() -> None:
            chosen = filedialog.askopenfilename(
                parent=dialog, title="Choose a .zip save backup made by v1.0.17",
                initialdir=str(save_tools.default_backups_folder()), filetypes=[("Save backups", "*.zip")],
            )
            if not chosen:
                return
            name = Path(chosen).name.casefold()
            folder = next((f for f in folders if name.startswith(f.name.casefold() + " ")), None)
            if folder is None:
                folder = folders[0]
                if not messagebox.askyesno(
                    "Import Older .zip Backup",
                    f"Which save folder this zip came from is not in its name. Add it to {folder.name}?",
                    parent=dialog,
                ):
                    return
            try:
                made = save_backup.import_zip_backup(game_id, folder, Path(chosen))
            except (OSError, zipfile.BadZipFile, save_backup.BackupError) as exc:
                messagebox.showerror("Import Older .zip Backup", f"Nothing was imported:\n\n{exc}", parent=dialog)
                return
            refresh()
            messagebox.showinfo("Import Older .zip Backup", f"Added to {folder.name} as {made.name}.", parent=dialog)

        listbox.bind("<<ListboxSelect>>", selected)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Restore...", command=do_restore).pack(side="left")
        ttk.Button(buttons, text="Delete Backup...", command=delete).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Import Older .zip Backup...", command=import_zip).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side="left", padx=(8, 0))
        refresh()
        dialog.grab_set()

    def _run_restore(self, parent, game_id: str, folder: Path, info, slot) -> None:
        try:
            if save_backup.game_running(folder):
                messagebox.showerror(
                    "Restore Saves",
                    f"{save_backup.game_exe_name(folder)} is running.\n\nQuit the game from its own menu first, "
                    "then restore: a running game writes its saves over the restored ones when it quits. "
                    "Nothing was changed.",
                    parent=parent,
                )
                return
            plan = save_backup.plan_restore(game_id, folder, info.folder, slot)
        except (save_backup.BackupError, OSError) as exc:
            messagebox.showerror("Restore Saves", str(exc), parent=parent)
            return
        if plan.changes == 0:
            messagebox.showinfo("Restore Saves", "Your saves already match this backup; there is nothing to restore.",
                                parent=parent)
            return
        what = "the whole save folder" if slot is None else f"player {slot} only"
        lines = ([f"Replace: {p}" for p in plan.replace] + [f"Add: {p}" for p in plan.add]
                 + [f"Remove: {p}" for p in plan.remove])
        if plan.player_name is not None:
            lines.append(f"Player {slot}'s name in the player list: {plan.player_name}")
        shown = "\n".join(lines[:20]) + (f"\n... and {len(lines) - 20} more" if len(lines) > 20 else "")
        when = info.when.strftime("%Y-%m-%d %H:%M:%S")
        if not messagebox.askyesno(
            "Restore Saves",
            f"Restore {what} of {folder.name} from the backup of {when}?\n\n{len(plan.replace)} file(s) will be "
            f"replaced, {len(plan.add)} added and {len(plan.remove)} removed:\n\n{shown}\n\nYour saves as they "
            "are now are backed up first, so this can be undone.",
            parent=parent, default="no",
        ):
            return
        try:
            result = save_backup.restore_backup(game_id, folder, info.folder, slot)
        except (save_backup.BackupError, OSError) as exc:
            self.app.status_var.set("Restore Saves: the restore did not complete.")
            messagebox.showerror("Restore Saves", str(exc), parent=parent)
            return
        undo = (f"\n\nYour saves from before the restore are in:\n{result.before_restore.backup_folder}"
                if result.before_restore else "")
        self.app.status_var.set(f"Restore Saves: {folder.name} restored from the backup of {when}.")
        self._log(f"\n=== Saves restored ({what}) ===\n{info.folder}\n-> {folder}\n")
        messagebox.showinfo(
            "Restore Saves",
            f"Restored {what} from the backup of {when}: every file was checked against the backup.{undo}",
            parent=parent,
        )

    # ---------------------------------------------------------------- rename

    def rename(self, game_id: str | None) -> None:
        dialog, frame = self._dialog("Rename Players")
        ttk.Label(
            frame,
            text=("Changes a player's name in the game's player list and inside that player's own save files. "
                  "The game must be closed: it saves when you quit it, which would put the old name back. "
                  "The save folder is backed up first, into <save folder>\\Backups\\Backup <date and time> "
                  "(before rename)."),
            wraplength=560, justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        titles = list(GAMES.values())
        game_var = tk.StringVar(master=dialog, value=GAMES[game_id] if game_id else titles[0])
        folder_var = tk.StringVar(master=dialog)
        name_var = tk.StringVar(master=dialog)
        counter_var = tk.StringVar(master=dialog)
        problem_var = tk.StringVar(master=dialog)
        state: dict = {"folders": [], "slots": []}
        ttk.Label(frame, text="Game:").grid(row=1, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=game_var, values=titles, state="readonly", width=48).grid(
            row=1, column=1, columnspan=2, sticky="we", pady=2)
        ttk.Label(frame, text="Save folder:").grid(row=2, column=0, sticky="w")
        folder_box = ttk.Combobox(frame, textvariable=folder_var, state="readonly", width=48)
        folder_box.grid(row=2, column=1, columnspan=2, sticky="we", pady=2)
        ttk.Label(frame, text="Player:").grid(row=3, column=0, sticky="nw", pady=(4, 0))
        slot_list = tk.Listbox(frame, height=5, width=60, exportselection=False, font=("Segoe UI", 9))
        slot_list.grid(row=3, column=1, columnspan=2, sticky="we", pady=(4, 2))
        ttk.Label(frame, text="New name:").grid(row=4, column=0, sticky="w", pady=(8, 0))
        name_entry = ttk.Entry(frame, textvariable=name_var, width=36)
        name_entry.grid(row=4, column=1, sticky="w", pady=(8, 0))
        counter = ttk.Label(frame, textvariable=counter_var)
        counter.grid(row=4, column=2, sticky="w", padx=(8, 0), pady=(8, 0))
        ttk.Label(frame, textvariable=problem_var, foreground="#a01010", wraplength=560, justify="left").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))
        rename_button = ttk.Button(buttons, text="Rename")
        rename_button.pack(side="left")
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side="left", padx=(8, 0))

        def game() -> str:
            return next(g for g, t in GAMES.items() if t == game_var.get())

        def chosen():
            picked = slot_list.curselection()
            return state["slots"][picked[0]] if picked and state["slots"] else None

        def check(*_args) -> None:
            fmt = save_tools.FORMATS[game()]
            name = name_var.get()
            counter_var.set(f"{len(name)} / {fmt.max_name} characters")
            counter.configure(foreground="#a01010" if len(name) > fmt.max_name else "")
            item = chosen()
            problem = None
            if not state["folders"]:
                problem = "No save folder was found for this game."
            elif item is None:
                problem = "Choose a player."
            elif name:
                try:
                    save_tools.validate_name(game(), name)
                except save_tools.SaveToolError as exc:
                    problem = str(exc)
                if problem is None and name == item[1]:
                    problem = "That is already this player's name."
            problem_var.set(problem or "")
            rename_button.configure(state="normal" if problem is None and name else "disabled")

        def load_slots(*_args) -> None:
            slot_list.delete(0, "end")
            state["slots"] = []
            index = folder_box.current()
            if 0 <= index < len(state["folders"]):
                folder = state["folders"][index]
                try:
                    names = save_tools.read_slot_names(game(), folder)
                except (OSError, save_tools.SaveToolError) as exc:
                    problem_var.set(f"The player list could not be read: {exc}")
                    names = []
                for slot, name in enumerate(names, start=1):
                    if save_tools.slot_is_active(game(), folder, slot, name):
                        state["slots"].append((slot, name))
                        slot_list.insert("end", f"Player {slot}: {name}")
                if not state["slots"]:
                    slot_list.insert("end", "No saved players in this folder.")
                else:
                    slot_list.selection_set(0)
            check()

        def load_folders(*_args) -> None:
            state["folders"] = save_backup.find_save_folders(game())
            folder_box.configure(values=[folder.name for folder in state["folders"]])
            if state["folders"]:
                folder_box.current(0)
            else:
                folder_var.set("")
            load_slots()

        def start() -> None:
            item = chosen()
            if item is None or not state["folders"]:
                return
            folder = state["folders"][folder_box.current()]
            new_name = name_var.get()
            if not messagebox.askyesno(
                "Rename Players",
                f"Rename \"{item[1]}\" (player {item[0]}) in {folder.name} to \"{new_name}\"?\n\n"
                "The save folder is backed up first.",
                parent=dialog,
            ):
                return
            try:
                report = save_tools.rename_slot(game(), folder, item[0], new_name)
            except (OSError, save_tools.SaveToolError, save_backup.BackupError) as exc:
                self.app.status_var.set("Rename Players: nothing was renamed.")
                messagebox.showerror("Rename Players", str(exc), parent=dialog)
                load_slots()
                return
            self.app.status_var.set(f"Rename Players: {report['old_name']} is now {report['new_name']}.")
            self._log(f"\n=== Player renamed ===\n{folder}: {report['old_name']!r} -> {report['new_name']!r}\n")
            messagebox.showinfo(
                "Rename Players",
                f"\"{report['old_name']}\" is now \"{report['new_name']}\" (player {item[0]}, {folder.name}).\n\n"
                f"{len(report['changed'])} save file(s) changed.\n\nBackup: {report['backup']}",
                parent=dialog,
            )
            name_var.set("")
            load_slots()

        rename_button.configure(command=start)
        game_var.trace_add("write", load_folders)
        folder_box.bind("<<ComboboxSelected>>", load_slots)
        slot_list.bind("<<ListboxSelect>>", check)
        name_var.trace_add("write", check)
        frame.columnconfigure(1, weight=1)
        load_folders()
        dialog.grab_set()
        name_entry.focus_set()

    # -------------------------------------------------------------- mechanics

    def mechanics(self, game_id: str | None) -> None:
        import game_mechanics_window

        game_mechanics_window.open_window(self.app, game_id or self.app.game_choice.get())

    # --------------------------------------------------------------- breeding

    def breeding(self, game_id: str | None) -> None:
        """The Breeding Guide, told every folder the patcher knows a game copy may be in:
        the output folder, each game's "- Modded" output copy and the folder it sits in
        (where "- Modded Upgrades" goes too), and the game folder picked on the Game tab
        and the folder it sits in. The guide finds the save's own copy there, to see which
        settings it was patched with, and any copy to read the pictures from."""
        app = self.app
        parents = [app.output_parent.get().strip()]
        for game in GAMES:
            for key in ("output", "vanilla"):
                folder = app.path_vars[game][key].get().strip().strip('"')
                if folder:
                    parents.extend([folder, str(Path(folder).parent)])
        breeding_guide.open_window(
            app, game_id or app.game_choice.get(), settings=app.breeding_settings,
            save_settings=app._save_settings, game_parents=[p for p in parents if p],
        )

    # ---------------------------------------------------------- picture studio

    def studio(self, game_id: str | None) -> None:
        """Picture Studio, with the Breeding Guide's Show Spoilers setting (one setting for
        both) and the same folders to find the game copies in. It reads none of the patcher
        window's own settings ("Enable All" and the rest): what a save has comes from the
        save's own game copy and files."""
        app = self.app
        parents = [app.output_parent.get().strip()]
        for game in GAMES:
            for key in ("output", "vanilla"):
                folder = app.path_vars[game][key].get().strip().strip('"')
                if folder:
                    parents.extend([folder, str(Path(folder).parent)])
        picture_studio.open_window(
            app, game_id or app.game_choice.get(), settings=app.breeding_settings,
            save_settings=app._save_settings, game_parents=[p for p in parents if p],
        )
