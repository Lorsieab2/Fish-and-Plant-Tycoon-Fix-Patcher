#!/usr/bin/env python3
"""Tkinter GUI for the combined Fish and Plant Tycoon fix patcher."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import threading
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

import save_backup
import save_tools

from tycoon_fix_patcher import (
    CombinedPatchError,
    GAMES,
    capture_run,
    default_output_dir,
    find_game_in_parent,
    output_dir_at,
    patch_settings,
    restore_game,
    setting_asset_files,
    setting_checksum_note,
    setting_companion_details,
    setting_companion_files,
    setting_patch_details,
)


APP_NAME = "Fish & Plant Tycoon Fix Patcher"
CREATOR_DESCRIPTION = "🪴 Created with Codex AI, with contributions from Claude AI. Made with love by Lorsieab2 :) 🐟"
CREATOR_TEXT = "Created with Codex AI, with contributions from Claude AI. Made with love by Lorsieab2 :)"
ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "patcher_local_settings.json"
FISH_PICTURE_PATH = ROOT / "assets" / "fish.png"
PLANT_PICTURE_PATH = ROOT / "assets" / "plant.png"
# Settings files written before v1.0.15 record only which settings were
# enabled, not which existed. These are the settings those versions had, so
# anything added later falls back to its manifest default.
LEGACY_KNOWN_SETTINGS = {
    "fish": [
        "crimson_comet_20_percent_cure",
        "unknown_chemical_three_uses",
        "universal_supply_slots",
        "golden_seahorse_repurchase",
    ],
    "plant": ["no_old_age_plant_deaths"],
}
# The owner: "Check for updates" opens the base GitHub repository, not the
# releases page.
RELEASES_URL = (
    "https://github.com/Lorsieab2/Fish-and-Plant-Tycoon-Fix-Patcher/"
)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self._load_brand_images()
        self.geometry("1000x880")
        self.minsize(860, 620)
        self.busy = False
        self.game_choice = tk.StringVar(value="fish")
        self.output_parent = tk.StringVar()
        self.path_vars = {
            game_id: {
                "vanilla": tk.StringVar(),
                "output": tk.StringVar(),
                "backup": tk.StringVar(),
            }
            for game_id in GAMES
        }
        self.patch_vars = {
            game_id: {
                setting_id: tk.BooleanVar(value=bool(setting.get("default", False)))
                for setting_id, setting in patch_settings(game_id).items()
            }
            for game_id in GAMES
        }
        self._link_setting_requirements()
        self.status_var = tk.StringVar(
            value="Choose one game or both games. Close the games before patching."
        )
        self.detect_status_var = tk.StringVar(
            value=(
                "Choose the folder that holds the game folders, and the patcher "
                "finds the exact Fish Tycoon.exe and Plant Tycoon.exe inside it."
            )
        )
        self.busy_controls: list[tk.Widget] = []
        self._load_settings()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _link_setting_requirements(self) -> None:
        """A setting that builds on another (DS Store Items on DS Exclusive
        Fish) turns it on with it, and goes off when it goes off."""
        for game_id in GAMES:
            settings = patch_settings(game_id)
            variables = self.patch_vars[game_id]
            for setting_id, setting in settings.items():
                for needed in setting.get("requires_settings", []):
                    if needed not in variables:
                        continue
                    dependent, base = variables[setting_id], variables[needed]
                    dependent.trace_add("write", lambda *_a, d=dependent, b=base: d.get() and not b.get() and b.set(True))
                    base.trace_add("write", lambda *_a, d=dependent, b=base: not b.get() and d.get() and d.set(False))

    def _load_brand_images(self) -> None:
        self.fish_picture = tk.PhotoImage(file=str(FISH_PICTURE_PATH))
        self.plant_picture = tk.PhotoImage(file=str(PLANT_PICTURE_PATH))
        self.fish_heading = self.fish_picture.subsample(4, 4)
        self.plant_heading = self.plant_picture.subsample(4, 4)
        self.fish_emoji = self.fish_picture.subsample(8, 8)
        self.plant_emoji = self.plant_picture.subsample(8, 8)

        # A native title bar accepts one square icon, so compose both supplied
        # pictures into that icon without modifying either source PNG.
        self.window_fish = self.fish_picture.subsample(12, 12)
        self.window_plant = self.plant_picture.subsample(12, 12)
        self.window_icon = tk.PhotoImage(width=32, height=32)
        self.window_icon.tk.call(
            str(self.window_icon), "copy", str(self.window_plant), "-to", 1, 9
        )
        self.window_icon.tk.call(
            str(self.window_icon), "copy", str(self.window_fish), "-to", 16, 9
        )
        self.iconphoto(True, self.window_icon)

    def _creator_line(
        self, parent: tk.Widget, *, small: bool = False
    ) -> ttk.Frame:
        line = ttk.Frame(parent)
        ttk.Label(line, image=self.plant_emoji).pack(side="left")
        ttk.Label(
            line,
            text=CREATOR_TEXT,
            font=("Segoe UI", 9 if small else 10, "bold" if not small else "normal"),
        ).pack(side="left", padx=3)
        ttk.Label(line, image=self.fish_emoji).pack(side="left")
        return line

    def _build_ui(self) -> None:
        # The page is taller than most screens, so the whole body scrolls.
        viewport = ttk.Frame(self)
        viewport.pack(fill="both", expand=True)
        style = ttk.Style(self)
        self.content_canvas = tk.Canvas(
            viewport,
            background=style.lookup("TFrame", "background"),
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(
            viewport, orient="vertical", command=self.content_canvas.yview
        )
        self.content_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.content_canvas.pack(side="left", fill="both", expand=True)

        outer = ttk.Frame(self.content_canvas, padding=18)
        self.content_window = self.content_canvas.create_window(
            (0, 0), window=outer, anchor="nw"
        )
        outer.bind("<Configure>", self._content_resized)
        self.content_canvas.bind("<Configure>", self._viewport_resized)
        self.bind_all("<MouseWheel>", self._scroll_content)

        heading = ttk.Frame(outer)
        heading.pack(fill="x")
        ttk.Label(heading, image=self.plant_heading).pack(side="left")
        ttk.Label(
            heading, text=APP_NAME, font=("Segoe UI", 18, "bold")
        ).pack(side="left", padx=8)
        ttk.Label(heading, image=self.fish_heading).pack(side="left")
        self._creator_line(outer).pack(anchor="w", pady=(2, 4))
        ttk.Label(
            outer,
            text=(
                "Creates verified modded copies in separate save-isolated folders. "
                "The selected vanilla folders are never replaced."
            ),
        ).pack(anchor="w")
        self._build_detect_box(outer)
        destination = ttk.LabelFrame(
            outer, text="Where to save the modified game folders", padding=8
        )
        destination.pack(fill="x", pady=(8, 4))
        place = ttk.Frame(destination)
        place.pack(fill="x")
        ttk.Entry(place, textvariable=self.output_parent).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            place,
            text="Choose Location...",
            command=self._browse_output_parent,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            destination,
            text=(
                "Creates only “Fish Tycoon - Modded” and/or "
                "“Plant Tycoon - Modded” here; with new fish, flowers "
                "or store items, “… - Modded Upgrades” instead."
            ),
            wraplength=880,
        ).pack(anchor="w", pady=(5, 0))
        update = tk.Label(
            outer,
            text="Check for updates",
            fg="#0057c2",
            cursor="hand2",
            font=("Segoe UI", 9, "underline"),
        )
        update.pack(anchor="w", pady=(3, 10))
        update.bind("<Button-1>", lambda _event: webbrowser.open(RELEASES_URL))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        one = ttk.Frame(notebook, padding=14)
        both = ttk.Frame(notebook, padding=14)
        tools = ttk.Frame(notebook, padding=14)
        notebook.add(one, text="One Game")
        notebook.add(both, text="Both Games")
        notebook.add(tools, text="Tools")
        self._build_one_tab(one)
        self._build_both_tab(both)
        self._build_tools_tab(tools)

        status = ttk.LabelFrame(outer, text="Status and verification log", padding=10)
        status.pack(fill="both", expand=True, pady=(10, 0))
        ttk.Label(
            status, textvariable=self.status_var, wraplength=920, justify="left"
        ).pack(anchor="w")
        self.log = tk.Text(status, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(8, 0))

        self._creator_line(outer, small=True).pack(anchor="w", pady=(8, 0))

    def _content_resized(self, _event: tk.Event) -> None:
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _viewport_resized(self, event: tk.Event) -> None:
        self.content_canvas.itemconfigure(self.content_window, width=event.width)

    def _scroll_content(self, event: tk.Event) -> str | None:
        bounds = self.content_canvas.bbox("all")
        if not bounds or bounds[3] <= self.content_canvas.winfo_height():
            return None
        self.content_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _build_detect_box(self, outer: tk.Widget) -> None:
        box = ttk.LabelFrame(outer, text="Find your installed games", padding=8)
        box.pack(fill="x", pady=(8, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.detect_button = tk.Button(
            row,
            text="Find Both in Parent Folder...",
            command=self._find_both,
            bg="#12508f",
            fg="white",
            activebackground="#0e4074",
            activeforeground="white",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=5,
        )
        self.detect_button.pack(side="left")
        self.busy_controls.append(self.detect_button)
        for game_id, spec in GAMES.items():
            button = ttk.Button(
                row,
                text=f"Find {spec.title}...",
                command=lambda value=game_id: self._find_one(value),
            )
            button.pack(side="left", padx=(8, 0))
            self.busy_controls.append(button)
        ttk.Label(
            box,
            textvariable=self.detect_status_var,
            wraplength=920,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def _set_busy(self, busy: bool) -> None:
        """Lock every action while one runs, dropping rebuilt panel widgets."""
        self.busy = busy
        state = "disabled" if busy else "normal"
        live = []
        for widget in self.busy_controls:
            try:
                if not widget.winfo_exists():
                    continue
                widget.configure(state=state)
            except tk.TclError:
                continue
            live.append(widget)
        self.busy_controls = live

    def _apply_detected(self, game_id: str, vanilla: Path) -> None:
        variables = self.path_vars[game_id]
        variables["vanilla"].set(str(vanilla))
        parent = self.output_parent.get().strip()
        variables["output"].set(
            str(
                output_dir_at(game_id, parent)
                if parent
                else default_output_dir(game_id, vanilla)
            )
        )

    def _set_all_patches(self, game_id: str, enabled: bool) -> None:
        for variable in self.patch_vars[game_id].values():
            variable.set(enabled)
        self._save_settings()
        word = "enabled" if enabled else "disabled"
        self.status_var.set(f"{GAMES[game_id].title}: all patches {word}.")

    def _reset_patches_to_defaults(self, game_id: str) -> None:
        for setting_id, setting in patch_settings(game_id).items():
            self.patch_vars[game_id][setting_id].set(bool(setting.get("default", False)))
        self._save_settings()
        self.status_var.set(f"{GAMES[game_id].title}: patches reset to the defaults.")

    def _build_one_tab(self, tab: ttk.Frame) -> None:
        select = ttk.LabelFrame(tab, text="Game", padding=10)
        select.pack(fill="x")
        for column, (game_id, spec) in enumerate(GAMES.items()):
            ttk.Radiobutton(
                select,
                text=spec.title,
                value=game_id,
                variable=self.game_choice,
                command=self._rebuild_one_game,
            ).grid(row=0, column=column, sticky="w", padx=(0, 20))
        self.one_game_body = ttk.Frame(tab)
        self.one_game_body.pack(fill="both", expand=True, pady=(10, 0))
        self._rebuild_one_game()

        actions = ttk.Frame(tab)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(
            actions, text="Validate", command=lambda: self._start(False, True)
        ).pack(side="left")
        ttk.Button(
            actions, text="Dry Run", command=lambda: self._start(False, True)
        ).pack(side="left", padx=8)
        self.one_apply = tk.Button(
            actions,
            text="Create Modded Copy",
            command=lambda: self._start(False, False),
            bg="#07852f",
            fg="white",
            activebackground="#056d27",
            activeforeground="white",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=5,
        )
        self.one_apply.pack(side="left")
        self.busy_controls.append(self.one_apply)
        restore = ttk.Button(
            actions,
            text="Restore Output EXE from Backup",
            command=self._start_restore,
        )
        restore.pack(side="left", padx=8)
        self.busy_controls.append(restore)

    def _rebuild_one_game(self) -> None:
        if not hasattr(self, "one_game_body"):
            return
        for child in self.one_game_body.winfo_children():
            child.destroy()
        game_id = self.game_choice.get()
        self._build_game_panel(self.one_game_body, game_id)

    def _build_both_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(
            tab,
            text=(
                "Both exact originals are validated before either fixed folder is written."
            ),
        ).pack(anchor="w", pady=(0, 8))
        for game_id in GAMES:
            panel = ttk.LabelFrame(tab, text=GAMES[game_id].title, padding=10)
            panel.pack(fill="x", pady=5)
            self._build_game_panel(panel, game_id, compact=True)

        finders = ttk.Frame(tab)
        finders.pack(fill="x", pady=(10, 0))
        find_both = ttk.Button(
            finders,
            text="Find Both in Parent Folder...",
            command=self._find_both,
        )
        find_both.pack(side="left")
        self.busy_controls.append(find_both)

        actions = ttk.Frame(tab)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(
            actions,
            text="Validate Both",
            command=lambda: self._start(True, True),
        ).pack(side="left", padx=(16, 8))
        ttk.Button(
            actions,
            text="Dry Run Both",
            command=lambda: self._start(True, True),
        ).pack(side="left")
        self.both_apply = tk.Button(
            actions,
            text="Patch Both",
            command=lambda: self._start(True, False),
            bg="#07852f",
            fg="white",
            activebackground="#056d27",
            activeforeground="white",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=5,
        )
        self.both_apply.pack(side="left", padx=8)
        self.busy_controls.append(self.both_apply)

    def _build_game_panel(
        self, parent: tk.Widget, game_id: str, *, compact: bool = False
    ) -> None:
        spec = GAMES[game_id]
        variables = self.path_vars[game_id]
        paths = ttk.LabelFrame(parent, text="Files and folders", padding=8)
        paths.pack(fill="x")
        self._path_row(
            paths,
            0,
            "Vanilla game folder",
            variables["vanilla"],
            lambda: self._browse_vanilla(game_id),
        )
        self._path_row(
            paths,
            2,
            f"Modified folder ({spec.modded_folder_name})",
            variables["output"],
            lambda: self._browse_output(game_id),
        )
        if not compact:
            self._path_row(
                paths,
                4,
                "Backup folder (restore)",
                variables["backup"],
                lambda: self._browse_backup(game_id),
            )

        patches = ttk.LabelFrame(parent, text=f"{spec.title} patches", padding=8)
        patches.pack(fill="x", pady=(8, 0))
        presets = ttk.Frame(patches)
        presets.grid(row=0, column=0, sticky="w", pady=(0, 6))
        for text, command in (
            ("Defaults", lambda: self._reset_patches_to_defaults(game_id)),
            ("Enable All", lambda: self._set_all_patches(game_id, True)),
            ("Disable All", lambda: self._set_all_patches(game_id, False)),
        ):
            button = ttk.Button(presets, text=text, command=command)
            button.pack(side="left", padx=(0, 6))
            self.busy_controls.append(button)
        body = ttk.Frame(patches)
        body.grid(row=1, column=0, sticky="ew")
        patches.columnconfigure(0, weight=1)
        for setting_id, setting in patch_settings(game_id).items():
            entry = ttk.Frame(body)
            entry.pack(fill="x", anchor="w", pady=(0, 6))
            ttk.Checkbutton(
                entry,
                text=str(setting.get("name", setting_id)),
                variable=self.patch_vars[game_id][setting_id],
                command=self._save_settings,
            ).pack(anchor="w")
            # What the setting adds or does, in plain words: shown everywhere,
            # including the compact Both Games panels.
            summary = str(setting.get("summary", "")).strip()
            if summary:
                ttk.Label(
                    entry,
                    text=summary,
                    wraplength=780 if compact else 820,
                    justify="left",
                ).pack(anchor="w", padx=(24, 0))
            # A warning is shown in both tabs, including the compact Both
            # Games panels, which leave out descriptions.
            warning = str(setting.get("warning", "")).strip()
            if warning:
                ttk.Label(
                    entry,
                    text=f"Warning: {warning}",
                    wraplength=780 if compact else 820,
                    foreground="#9a3b00",
                    justify="left",
                ).pack(anchor="w", padx=(24, 0))
            if compact:
                continue
            ttk.Label(
                entry,
                text=str(setting.get("description", "")),
                wraplength=820,
                foreground="#444444",
                justify="left",
            ).pack(anchor="w", padx=(24, 0))
            self._technical_details(entry, game_id, setting_id)

    def _technical_details(
        self, parent: tk.Widget, game_id: str, setting_id: str
    ) -> None:
        """A collapsed list of every byte this setting changes, and why.

        Kept behind a disclosure so the window stays readable for players while
        the detail is one click away for anyone who wants it.
        """
        byte_details = setting_patch_details(game_id, setting_id)
        details = byte_details + setting_companion_details(game_id, setting_id)
        asset_files = setting_asset_files(game_id, setting_id)
        companion_files = setting_companion_files(game_id, setting_id)
        if not details and not asset_files and not companion_files:
            return
        holder = ttk.Frame(parent)
        holder.pack(fill="x", anchor="w", padx=(24, 0), pady=(2, 0))
        content = ttk.Frame(holder)
        if asset_files:
            label = f"Technical details — {len(asset_files)} file" + ("s" if len(asset_files) != 1 else "")
            ttk.Label(
                content,
                text=(
                    "Merged into the modded game folder only where the game does not "
                    "already have the file. Nothing in the executable changes."
                ),
                wraplength=760,
                justify="left",
                foreground="#333333",
            ).pack(anchor="w", pady=(4, 0))
            for path in asset_files:
                ttk.Label(
                    content,
                    text=path,
                    font=("Consolas", 9),
                    foreground="#12508f",
                ).pack(anchor="w", padx=(14, 0))
        elif companion_files:
            label = (
                f"Technical details — {len(details)} executable change" + ("s" if len(details) != 1 else "")
                + f", {len(companion_files)} file" + ("s" if len(companion_files) != 1 else "")
            )
            ttk.Label(
                content,
                text=(
                    "Copied into the modded game folder: the companion DLL into the patcher's "
                    "folder beside the executable, and the new sprites into Images."
                ),
                wraplength=760,
                justify="left",
                foreground="#333333",
            ).pack(anchor="w", pady=(4, 0))
            for path in companion_files:
                ttk.Label(
                    content,
                    text=path,
                    font=("Consolas", 9),
                    foreground="#12508f",
                ).pack(anchor="w", padx=(14, 0))
        else:
            label = f"Technical details — {len(details)} change" + ("s" if len(details) != 1 else "")
        link = tk.Label(
            holder,
            text=f"▸ {label}",
            fg="#0057c2",
            cursor="hand2",
            font=("Segoe UI", 9, "underline"),
        )
        link.pack(anchor="w")

        for detail in details:
            ttk.Label(
                content,
                text=f"{detail.where}  ·  {detail.length} bytes",
                font=("Consolas", 9, "bold"),
                foreground="#12508f",
            ).pack(anchor="w", pady=(4, 0))
            if detail.note:
                ttk.Label(
                    content,
                    text=detail.note,
                    wraplength=760,
                    justify="left",
                    foreground="#333333",
                ).pack(anchor="w", padx=(14, 0))
        checksum = setting_checksum_note(game_id) if byte_details else ""
        if checksum:
            ttk.Label(
                content,
                text=checksum,
                wraplength=760,
                justify="left",
                foreground="#666666",
            ).pack(anchor="w", pady=(6, 0))

        shown = tk.BooleanVar(value=False)

        def toggle(_event: tk.Event | None = None) -> None:
            if shown.get():
                content.pack_forget()
                link.configure(text=f"▸ {label}")
            else:
                content.pack(fill="x", anchor="w", pady=(2, 4))
                link.configure(text=f"▾ {label}")
            shown.set(not shown.get())
            self.after_idle(self._content_resized, None)

        link.bind("<Button-1>", toggle)

    # --- Tools: save backups and player slot names --------------------------

    def _build_tools_tab(self, tab: ttk.Frame) -> None:
        """Back up, restore and rename saves, for either game, in any of its
        save folders (the original game's and each modded copy's)."""
        self.tools_game = tk.StringVar(value="fish")
        self.tools_folder = tk.StringVar()
        self.tools_name_vars = [tk.StringVar() for _ in range(5)]
        self.tools_slot_labels: list[ttk.Label] = []
        self.tools_slot_controls: list[tuple[ttk.Entry, ttk.Button]] = []
        self.tools_chosen: dict[str, str] = {}      # a save folder the player browsed to, per game

        select = ttk.LabelFrame(tab, text="Game and save folder", padding=10)
        select.pack(fill="x")
        row = ttk.Frame(select)
        row.pack(fill="x")
        for game_id, spec in GAMES.items():
            ttk.Radiobutton(
                row, text=spec.title, value=game_id, variable=self.tools_game,
                command=self._tools_refresh,
            ).pack(side="left", padx=(0, 12))
        folder_row = ttk.Frame(select)
        folder_row.pack(fill="x", pady=(8, 0))
        ttk.Label(folder_row, text="Save folder:").pack(side="left")
        self.tools_folder_box = ttk.Combobox(
            folder_row, textvariable=self.tools_folder, state="readonly", width=70
        )
        self.tools_folder_box.pack(side="left", fill="x", expand=True, padx=8)
        self.tools_folder_box.bind("<<ComboboxSelected>>", lambda _e: self._tools_load_names())
        ttk.Button(folder_row, text="Browse...", command=self._tools_choose_folder).pack(side="left")
        ttk.Button(folder_row, text="Refresh", command=self._tools_refresh).pack(side="left", padx=(8, 0))
        open_link = tk.Label(
            select, text="Open this save folder", fg="#0057c2", cursor="hand2",
            font=("Segoe UI", 9, "underline"),
        )
        open_link.pack(anchor="w", pady=(4, 0))
        open_link.bind("<Button-1>", lambda _e: self._open_folder(self.tools_folder.get()))
        ttk.Label(
            select,
            text=(
                "Each copy of a game keeps its own saves in Documents\\LDW\\<exe name>. The list "
                "shows the patcher's copies, “- Modded” and “- Modded Upgrades”; use Browse for any "
                "other. Close the game before using these tools."
            ),
            wraplength=880, foreground="#444444",
        ).pack(anchor="w", pady=(4, 0))

        backup = ttk.LabelFrame(tab, text="Backup and Restore Saves", padding=10)
        backup.pack(fill="x", pady=(10, 0))
        buttons = ttk.Frame(backup)
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="Back Up Saves Now", command=self._tools_back_up).pack(side="left")
        ttk.Button(buttons, text="Open Backups Folder", command=self._tools_open_backups).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(buttons, text="Import Older .zip Backup...", command=self._tools_import_zip).pack(
            side="left", padx=(8, 0)
        )
        listing = ttk.Frame(backup)
        listing.pack(fill="x", pady=(8, 0))
        self.tools_backup_list = tk.Listbox(
            listing, height=6, activestyle="none", exportselection=False, font=("Segoe UI", 9)
        )
        self.tools_backup_list.pack(side="left", fill="x", expand=True)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.tools_backup_list.yview)
        scroll.pack(side="left", fill="y")
        self.tools_backup_list.configure(yscrollcommand=scroll.set)
        actions = ttk.Frame(backup)
        actions.pack(anchor="w", pady=(8, 0))
        ttk.Button(actions, text="Restore Whole Folder", command=lambda: self._tools_restore(None)).pack(
            side="left"
        )
        ttk.Label(actions, text="Player slot:").pack(side="left", padx=(16, 4))
        self.tools_restore_slot = tk.StringVar(value="1")
        ttk.Combobox(
            actions, textvariable=self.tools_restore_slot, values=["1", "2", "3", "4", "5"],
            width=3, state="readonly",
        ).pack(side="left")
        ttk.Button(
            actions, text="Restore This Slot",
            command=lambda: self._tools_restore(int(self.tools_restore_slot.get())),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Delete Backup", command=self._tools_delete_backup).pack(
            side="left", padx=(16, 0)
        )
        ttk.Label(
            backup,
            text=(
                "A backup is a checked copy of the save folder, kept in its own Backups folder. "
                "If the game is running it is paused for the copy and resumed afterwards. A "
                "restore needs the game closed; it puts back the whole folder or one player's "
                "slot, after backing up the saves as they are now, so a restore can itself be "
                "undone."
            ),
            wraplength=880, foreground="#444444",
        ).pack(anchor="w", pady=(6, 0))
        self.tools_backups = []

        rename = ttk.LabelFrame(tab, text="Rename Player Slots", padding=10)
        rename.pack(fill="x", pady=(10, 0))
        for index in range(5):
            line = ttk.Frame(rename)
            line.pack(fill="x", pady=2)
            label = ttk.Label(line, text=f"Slot {index + 1}:", width=34)
            label.pack(side="left")
            self.tools_slot_labels.append(label)
            entry = ttk.Entry(line, textvariable=self.tools_name_vars[index], width=34)
            entry.pack(side="left", padx=8)
            button = ttk.Button(
                line, text="Rename",
                command=lambda slot=index + 1: self._tools_rename(slot),
            )
            button.pack(side="left")
            self.tools_slot_controls.append((entry, button))
        ttk.Label(
            rename,
            text=(
                "Changes the name in the game's player list and inside that player's own save "
                "files. Only slots with a saved game can be renamed, and \"NEW PLAYER\" is not "
                "a name (the game uses it for empty slots). Up to 31 plain characters, as in the "
                "game. The save folder is backed up first."
            ),
            wraplength=880, foreground="#444444",
        ).pack(anchor="w", pady=(4, 0))

        mechanics = ttk.LabelFrame(tab, text="Game Mechanics", padding=10)
        mechanics.pack(fill="x", pady=(10, 0))
        line = ttk.Frame(mechanics)
        line.pack(anchor="w")
        ttk.Button(line, text="Game Mechanics...", command=self._tools_open_mechanics).pack(side="left")
        ttk.Button(line, text="?", width=3, command=self._tools_mechanics_help).pack(side="left", padx=(6, 0))
        ttk.Label(
            mechanics,
            text=(
                "For the curious: how both games really work underneath, worked out from their "
                "code. Every chance, timer and number, and what this patcher's settings change. "
                "Read-only; the games can stay open."
            ),
            wraplength=880, foreground="#444444",
        ).pack(anchor="w", pady=(4, 0))
        self._tools_refresh()

    def _tools_open_mechanics(self) -> None:
        import game_mechanics_window

        game_mechanics_window.open_window(self, self.tools_game.get())

    def _tools_mechanics_help(self) -> None:
        messagebox.showinfo(
            APP_NAME,
            "Game Mechanics opens a read-only page with a tab for each game: time and time "
            "away, health, food, sickness, breeding, eggs and seeds, the store items, research, "
            "selling, magic fish and magic plants, and an index of every random roll and timer.\n\n"
            "Every line is labelled. VERIFIED-E means the game's code was run and counted "
            "exactly, VERIFIED-C means it was read in the game's code, and UNCONFIRMED marks "
            "estimates. Where one of this patcher's settings changes a fact, a \"With the "
            "patcher\" line says how.\n\nIt never opens or changes a save or game file.",
        )

    def _tools_refresh(self) -> None:
        game_id = self.tools_game.get()
        folders = [str(path) for path in save_tools.modded_save_folders(game_id)]
        current = self.tools_folder.get()
        # A folder the player browsed to stays listed while it is this game's save folder.
        chosen = self.tools_chosen.get(game_id)
        if chosen and chosen not in folders and save_tools.is_save_folder(game_id, Path(chosen)):
            folders.append(chosen)
        self.tools_folder_box.configure(values=folders)
        if current not in folders:
            self.tools_folder.set(folders[0] if folders else "")
        self._tools_load_names()

    def _tools_choose_folder(self) -> None:
        game_id = self.tools_game.get()
        chosen = filedialog.askdirectory(
            title=f"Choose a {GAMES[game_id].title} save folder (it holds {GAMES[game_id].title}0.ldw)",
            initialdir=str(save_tools.ldw_folder()),
        )
        if not chosen:
            return
        if not save_tools.is_save_folder(game_id, Path(chosen)):
            messagebox.showerror(
                APP_NAME, f"That folder has no {GAMES[game_id].title}0.ldw, so it is not this game's save folder."
            )
            return
        self.tools_chosen[game_id] = str(Path(chosen))
        self.tools_folder.set(str(Path(chosen)))
        self._tools_refresh()

    def _tools_load_names(self) -> None:
        folder = self.tools_folder.get()
        names: list[str] = []
        if folder:
            try:
                names = save_tools.read_slot_names(self.tools_game.get(), Path(folder))
            except (OSError, save_tools.SaveToolError) as exc:
                self.status_var.set(f"Could not read the player list: {exc}")
        for index, label in enumerate(self.tools_slot_labels):
            current = names[index] if index < len(names) else ""
            active = bool(folder) and save_tools.slot_is_active(
                self.tools_game.get(), Path(folder), index + 1, current
            )
            label.configure(text=f"Slot {index + 1}: {current if active else '(empty)'}")
            self.tools_name_vars[index].set(current if active else "")
            for widget in self.tools_slot_controls[index]:
                widget.configure(state="normal" if active else "disabled")
        self._tools_load_backups()

    def _tools_load_backups(self) -> None:
        self.tools_backup_list.delete(0, "end")
        self.tools_backups = []
        folder = self.tools_folder.get()
        if not folder:
            return
        try:
            self.tools_backups = save_backup.list_backups(self.tools_game.get(), Path(folder))
        except OSError as exc:
            self.status_var.set(f"Could not list the backups: {exc}")
        for info in self.tools_backups:
            self.tools_backup_list.insert("end", info.describe())
        if not self.tools_backups:
            self.tools_backup_list.insert("end", "No backups yet. Back Up Saves Now makes one.")

    def _tools_selected_backup(self):
        picked = self.tools_backup_list.curselection()
        if not self.tools_backups or not picked or picked[0] >= len(self.tools_backups):
            messagebox.showerror(APP_NAME, "Choose a backup in the list first.")
            return None
        return self.tools_backups[picked[0]]

    def _tools_open_backups(self) -> None:
        folder = self._tools_folder_or_warn()
        if folder is None:
            return
        target = folder / save_backup.BACKUPS_FOLDER
        target.mkdir(exist_ok=True)
        self._open_folder(str(target))

    def _tools_folder_or_warn(self) -> Path | None:
        folder = self.tools_folder.get()
        if not folder:
            messagebox.showerror(APP_NAME, "No save folder found for this game. Play it once first.")
            return None
        return Path(folder)

    def _tools_back_up(self) -> None:
        folder = self._tools_folder_or_warn()
        if folder is None:
            return
        try:
            result = save_backup.back_up_save_folder(folder)
        except (OSError, save_backup.BackupError) as exc:
            messagebox.showerror(APP_NAME, f"No backup was made:\n\n{exc}")
            return
        lines = [
            f"{result.file_count} files ({save_backup.describe_size(result.total_bytes)}) copied "
            f"and checked into:\n\n{result.backup_folder}"
        ]
        if result.paused:
            lines.append("The game was paused for the copy and resumed.")
        lines.extend(result.resume_problems)
        self.log.insert("end", f"\n=== Saves backed up ===\n{folder}\n-> {result.backup_folder}\n")
        self.log.see("end")
        self._tools_load_backups()
        self.status_var.set(f"Saves backed up: {result.backup_folder.name}.")
        messagebox.showinfo(APP_NAME, "\n\n".join(lines))

    def _tools_restore(self, slot: int | None) -> None:
        folder = self._tools_folder_or_warn()
        info = self._tools_selected_backup() if folder is not None else None
        if info is None:
            return
        game_id = self.tools_game.get()
        try:
            plan = save_backup.plan_restore(game_id, folder, info.folder, slot)
        except (OSError, save_backup.BackupError) as exc:
            messagebox.showerror(APP_NAME, f"Nothing was restored:\n\n{exc}")
            return
        if plan.changes == 0:
            messagebox.showinfo(APP_NAME, "The saves are already the same as this backup; nothing to restore.")
            return
        what = "every save" if slot is None else f"player slot {slot}"
        name_note = ", and the slot's name in the player list" if plan.player_name is not None else ""
        if not messagebox.askyesno(
            APP_NAME,
            f"Restore {what} from the backup of {info.when.strftime('%Y-%m-%d %H:%M:%S')}?\n\n"
            f"{len(plan.replace)} files replaced, {len(plan.add)} added, {len(plan.remove)} removed"
            f"{name_note}.\n\nThe saves as they are now are backed up first. The game must be closed.",
            default="no",
        ):
            return
        try:
            result = save_backup.restore_backup(game_id, folder, info.folder, slot)
        except (OSError, save_backup.BackupError) as exc:
            messagebox.showerror(APP_NAME, f"Restore failed:\n\n{exc}")
            self._tools_load_backups()
            return
        before = result.before_restore.backup_folder if result.before_restore else None
        kept = f"Previous saves kept in {before}\n" if before else ""
        self.log.insert("end", f"\n=== Saves restored ({what}) ===\n{info.folder}\n-> {folder}\n{kept}")
        self.log.see("end")
        self._tools_load_names()
        self.status_var.set("Saves restored.")
        done = "Saves restored."
        if before:
            done += f" The previous saves were backed up to:\n\n{before}"
        messagebox.showinfo(APP_NAME, done)

    def _tools_delete_backup(self) -> None:
        folder = self._tools_folder_or_warn()
        info = self._tools_selected_backup() if folder is not None else None
        if info is None:
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Delete the backup of {info.when.strftime('%Y-%m-%d %H:%M:%S')}?\n\nThis cannot be undone.",
            default="no",
        ):
            return
        try:
            save_backup.delete_backup(folder, info.folder)
        except (OSError, save_backup.BackupError) as exc:
            messagebox.showerror(APP_NAME, str(exc))
        self._tools_load_backups()

    def _tools_import_zip(self) -> None:
        folder = self._tools_folder_or_warn()
        if folder is None:
            return
        chosen = filedialog.askopenfilename(
            title="Choose a .zip save backup from an older version",
            initialdir=str(save_tools.default_backups_folder()),
            filetypes=[("Save backups", "*.zip")],
        )
        if not chosen:
            return
        try:
            made = save_backup.import_zip_backup(self.tools_game.get(), folder, Path(chosen))
        except (OSError, zipfile.BadZipFile, save_backup.BackupError) as exc:
            messagebox.showerror(APP_NAME, f"Nothing was imported:\n\n{exc}")
            return
        self._tools_load_backups()
        messagebox.showinfo(APP_NAME, f"Imported as {made.name}. Choose it in the list to restore it.")

    def _tools_rename(self, slot: int) -> None:
        folder = self._tools_folder_or_warn()
        if folder is None:
            return
        new_name = self.tools_name_vars[slot - 1].get()
        try:
            report = save_tools.rename_slot(self.tools_game.get(), folder, slot, new_name)
        except (OSError, save_tools.SaveToolError) as exc:
            messagebox.showerror(APP_NAME, f"Rename failed; nothing was changed:\n\n{exc}")
            return
        skipped = (
            f"Left alone (name did not match): {', '.join(report['skipped'])}\n" if report["skipped"] else ""
        )
        self.log.insert(
            "end",
            f"\n=== Slot {slot} renamed ===\n{report['old_name']!r} -> {report['new_name']!r}\n"
            f"Changed: {', '.join(report['changed'])}\n{skipped}Backup: {report['backup']}\n",
        )
        self.log.see("end")
        self._tools_load_names()
        self.status_var.set(f"Slot {slot} renamed to {report['new_name']}.")

    def _path_row(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        variable: tk.StringVar,
        browse_command,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", padx=8, pady=3
        )
        ttk.Button(parent, text="Browse...", command=browse_command).grid(
            row=row, column=2, pady=3
        )
        link = tk.Label(
            parent,
            textvariable=variable,
            fg="#0057c2",
            cursor="hand2",
            font=("Segoe UI", 9, "underline"),
            anchor="w",
        )
        link.grid(row=row + 1, column=1, sticky="ew", padx=8, pady=(0, 3))
        link.bind("<Button-1>", lambda _event, var=variable: self._open_folder(var.get()))
        parent.columnconfigure(1, weight=1)

    def _browse_vanilla(self, game_id: str) -> None:
        spec = GAMES[game_id]
        current = self.path_vars[game_id]["vanilla"].get().strip()
        chosen = filedialog.askdirectory(
            title=f"Choose the folder containing {spec.exe_name}",
            initialdir=current or str(Path.home()),
        )
        if not chosen:
            return
        variables = self.path_vars[game_id]
        previous_vanilla = variables["vanilla"].get().strip()
        previous_default = (
            str(default_output_dir(game_id, previous_vanilla))
            if previous_vanilla
            else ""
        )
        variables["vanilla"].set(chosen)
        if not variables["output"].get().strip() or variables["output"].get().strip() == previous_default:
            variables["output"].set(
                str(
                    output_dir_at(game_id, self.output_parent.get().strip())
                    if self.output_parent.get().strip()
                    else default_output_dir(game_id, chosen)
                )
            )
        self._save_settings()

    def _browse_output(self, game_id: str) -> None:
        spec = GAMES[game_id]
        current = self.path_vars[game_id]["output"].get().strip()
        chosen = filedialog.askdirectory(
            title=f"Choose where to create {spec.modded_folder_name}",
            initialdir=current or str(Path.home()),
        )
        if not chosen:
            return
        candidate = Path(chosen)
        if candidate.name.casefold() != spec.modded_folder_name.casefold():
            candidate /= spec.modded_folder_name
        self.path_vars[game_id]["output"].set(str(candidate))
        self.output_parent.set(str(candidate.parent))
        self._save_settings()

    def _browse_output_parent(self) -> None:
        current = self.output_parent.get().strip()
        chosen = filedialog.askdirectory(
            title="Choose where to save the modified Fish and Plant Tycoon folders",
            initialdir=current or str(Path.home()),
        )
        if not chosen:
            return
        self.output_parent.set(chosen)
        for game_id in GAMES:
            self.path_vars[game_id]["output"].set(
                str(output_dir_at(game_id, chosen))
            )
        self._save_settings()

    def _browse_backup(self, game_id: str) -> None:
        current = self.path_vars[game_id]["backup"].get().strip()
        chosen = filedialog.askdirectory(
            title=f"Choose a timestamped {GAMES[game_id].title} backup folder",
            initialdir=current or str(Path.home()),
        )
        if chosen:
            self.path_vars[game_id]["backup"].set(chosen)
            self._save_settings()

    def _find_both(self) -> None:
        chosen = filedialog.askdirectory(
            title="Choose the parent folder containing Fish Tycoon and Plant Tycoon",
            initialdir=str(Path.home()),
        )
        if not chosen:
            return
        problems = []
        found: list[str] = []
        for game_id, spec in GAMES.items():
            matches = find_game_in_parent(game_id, chosen)
            if len(matches) == 1:
                self._apply_detected(game_id, matches[0].parent)
                found.append(spec.title)
            elif not matches:
                problems.append(f"Not found: {spec.exe_name}")
            else:
                problems.append(f"More than one match: {spec.exe_name}")
        self._save_settings()
        if problems:
            messagebox.showwarning(APP_NAME, "\n".join(problems))
        else:
            self.status_var.set("Found both exact executable filenames. Ready to validate.")

    def _find_one(self, game_id: str) -> None:
        spec = GAMES[game_id]
        current = self.path_vars[game_id]["vanilla"].get().strip()
        initial = (
            str(Path(current).parent)
            if current and Path(current).parent.is_dir()
            else str(Path.home())
        )
        chosen = filedialog.askdirectory(
            title=f"Choose the parent folder containing {spec.title}",
            initialdir=initial,
        )
        if not chosen:
            return
        matches = find_game_in_parent(game_id, chosen)
        if not matches:
            messagebox.showwarning(
                APP_NAME,
                f"Could not find {spec.vanilla_exe_name} in that folder "
                "or its immediate subfolders.",
            )
            return
        if len(matches) > 1:
            messagebox.showwarning(
                APP_NAME,
                f"Found more than one {spec.vanilla_exe_name}. "
                "Please choose the exact vanilla game folder instead.",
            )
            return
        self._apply_detected(game_id, matches[0].parent)
        self._save_settings()
        self.detect_status_var.set(f"Filled in: {spec.title}.")
        self.status_var.set(
            f"Found the exact {spec.vanilla_exe_name}. Ready to validate."
        )

    def _selected_settings(self, game_id: str) -> list[str]:
        return sorted(
            setting_id
            for setting_id, variable in self.patch_vars[game_id].items()
            if variable.get()
        )

    def _configs(self, both: bool) -> dict[str, dict]:
        ids = list(GAMES) if both else [self.game_choice.get()]
        configs = {}
        for game_id in ids:
            variables = self.path_vars[game_id]
            vanilla = variables["vanilla"].get().strip().strip('"')
            output = variables["output"].get().strip().strip('"')
            if not vanilla:
                raise CombinedPatchError(
                    f"Choose the {GAMES[game_id].title} vanilla game folder."
                )
            if not output:
                if self.output_parent.get().strip():
                    output = str(
                        output_dir_at(game_id, self.output_parent.get().strip())
                    )
                else:
                    output = str(default_output_dir(game_id, vanilla))
                variables["output"].set(output)
            elif Path(output).name.casefold() != GAMES[
                game_id
            ].modded_folder_name.casefold():
                output = str(output_dir_at(game_id, output))
                variables["output"].set(output)
            configs[game_id] = {
                "vanilla_dir": vanilla,
                "output_dir": output,
                "enabled": self._selected_settings(game_id),
            }
        return configs

    def _start(self, both: bool, dry_run: bool) -> None:
        if self.busy:
            return
        try:
            configs = self._configs(both)
        except CombinedPatchError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self._save_settings()
        label = (
            ("Both-games dry run" if dry_run else "Patch both games")
            if both
            else ("Dry run" if dry_run else "Create modded copy")
        )
        self._set_busy(True)
        self.status_var.set(f"{label} in progress...")
        self.log.insert("end", f"\n=== {label} ===\n")

        def worker() -> None:
            try:
                results, text = capture_run(configs, dry_run=dry_run)
                self.after(
                    0, lambda: self._finish(label, results, text, "", dry_run)
                )
            except Exception as exc:
                self.after(
                    0, lambda value=str(exc): self._finish(label, [], "", value, dry_run)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _start_restore(self) -> None:
        if self.busy:
            return
        game_id = self.game_choice.get()
        variables = self.path_vars[game_id]
        backup = variables["backup"].get().strip().strip('"')
        output = variables["output"].get().strip().strip('"')
        if not backup or not output:
            messagebox.showerror(
                APP_NAME, "Choose the backup folder and modded output folder first."
            )
            return
        self._save_settings()
        self._set_busy(True)
        self.status_var.set("Restore in progress...")
        self.log.insert("end", "\n=== Restore output EXE from backup ===\n")

        def worker() -> None:
            try:
                text = restore_game(game_id, backup, output)
                self.after(0, lambda: self._finish_restore(text, ""))
            except Exception as exc:
                self.after(
                    0, lambda value=str(exc): self._finish_restore("", value)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _finish_restore(self, text: str, error: str) -> None:
        self._set_busy(False)
        if text:
            self.log.insert("end", text)
            self.log.see("end")
        if error:
            self.status_var.set("Restore failed.")
            messagebox.showerror(APP_NAME, error)
            return
        self.status_var.set("Restore completed successfully.")
        messagebox.showinfo(
            APP_NAME, "The original executable was restored in the modded folder."
        )

    def _finish(
        self,
        label: str,
        results: list[dict],
        text: str,
        error: str,
        dry_run: bool,
    ) -> None:
        self._set_busy(False)
        if text:
            self.log.insert("end", text)
            self.log.see("end")
        if error:
            self.status_var.set(f"{label} failed.")
            messagebox.showerror(APP_NAME, error)
            return
        self.status_var.set(f"{label} completed successfully.")
        if dry_run:
            messagebox.showinfo(
                APP_NAME,
                "Exact executable identity and all selected patch bytes validated.\n"
                "No game files were written.",
            )
        else:
            self._show_success(results)

    def _show_success(self, results: list[dict]) -> None:
        win = tk.Toplevel(self)
        win.title(f"{APP_NAME} complete")
        win.geometry("840x420")
        win.minsize(700, 340)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, text="Modded game folder(s) created successfully!", font=("Segoe UI", 15, "bold")
        ).pack(anchor="w")
        ttk.Label(
            body, text="Click any path below to open it in File Explorer."
        ).pack(anchor="w", pady=(4, 12))
        for result in results:
            title = Path(str(result["target"]["path"])).name
            group = ttk.LabelFrame(body, text=title, padding=8)
            group.pack(fill="x", pady=4)
            self._success_link(group, "Vanilla folder", str(result["vanilla_game_dir"]))
            self._success_link(group, "Modded folder", str(result["output_dir"]))
            if result.get("backup_dir"):
                self._success_link(group, "Backup folder", str(result["backup_dir"]))
        ttk.Label(body, text="Have fun! -Lorsieab2 :)").pack(anchor="w", pady=(12, 0))
        ttk.Button(body, text="Close", command=win.destroy).pack(anchor="e")

    def _success_link(self, parent: tk.Widget, label: str, path: str) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=f"{label}:").pack(side="left")
        link = tk.Label(
            row,
            text=path,
            fg="#0057c2",
            cursor="hand2",
            font=("Segoe UI", 9, "underline"),
        )
        link.pack(side="left", padx=8)
        link.bind("<Button-1>", lambda _event, value=path: self._open_folder(value))

    def _open_folder(self, raw: str) -> None:
        if not raw.strip():
            messagebox.showerror(APP_NAME, "Choose a folder first.")
            return
        path = Path(raw.strip().strip('"')).expanduser()
        if not path.is_dir():
            messagebox.showerror(APP_NAME, f"Folder does not exist:\n\n{path}")
            return
        try:
            subprocess.Popen(["explorer", str(path.resolve())])
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open folder:\n\n{exc}")

    def _load_settings(self) -> None:
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        selected = data.get("selected_game")
        if selected in GAMES:
            self.game_choice.set(selected)
        self.output_parent.set(str(data.get("output_parent", "")))
        game_data = data.get("games", {})
        for game_id in GAMES:
            saved = game_data.get(game_id, {}) if isinstance(game_data, dict) else {}
            if isinstance(saved, dict):
                self.path_vars[game_id]["vanilla"].set(str(saved.get("vanilla", "")))
                saved_output = str(saved.get("output", ""))
                if saved_output and Path(saved_output).name.casefold() == (
                    f"{GAMES[game_id].title} - Fixed".casefold()
                ):
                    saved_output = str(
                        Path(saved_output).parent / GAMES[game_id].modded_folder_name
                    )
                self.path_vars[game_id]["output"].set(saved_output)
                self.path_vars[game_id]["backup"].set(str(saved.get("backup", "")))
                enabled = saved.get("enabled")
                if isinstance(enabled, list):
                    # Only settings the file knew about are restored; a setting
                    # added since it was saved keeps its manifest default
                    # instead of reading as unticked.
                    known = saved.get("known")
                    if not isinstance(known, list):
                        known = LEGACY_KNOWN_SETTINGS.get(game_id, [])
                    for setting_id, variable in self.patch_vars[game_id].items():
                        if setting_id in known:
                            variable.set(setting_id in enabled)

    def _save_settings(self) -> str:
        """Save the remembered paths and choices; return why not, or ""."""
        data = {
            "selected_game": self.game_choice.get(),
            "output_parent": self.output_parent.get().strip(),
            "games": {
                game_id: {
                    "vanilla": self.path_vars[game_id]["vanilla"].get().strip(),
                    "output": self.path_vars[game_id]["output"].get().strip(),
                    "backup": self.path_vars[game_id]["backup"].get().strip(),
                    "enabled": self._selected_settings(game_id),
                    "known": list(self.patch_vars[game_id]),
                }
                for game_id in GAMES
            },
        }
        try:
            SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            # A patcher extracted somewhere read-only (Program Files, a locked
            # folder) must still patch and still close; only the remembered
            # paths and choices are lost.
            problem = (
                f"Could not save your settings to {SETTINGS_PATH} ({exc.strerror or exc}). "
                "Patching still works; your choices will not be remembered."
            )
            self.status_var.set(problem)
            # The status line is overwritten as soon as a run starts, so the
            # log keeps a lasting copy, once per session rather than per click.
            if not getattr(self, "settings_save_logged", False):
                self.settings_save_logged = True
                self.log.insert("end", problem + "\n")
                self.log.see("end")
            return problem
        return ""

    def _close(self) -> None:
        if self.busy and not messagebox.askyesno(
            APP_NAME, "An operation is running. Close anyway?"
        ):
            return
        problem = self._save_settings()
        if problem:
            messagebox.showwarning(APP_NAME, problem)
        self.destroy()


def main() -> int:
    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
