#!/usr/bin/env python3
"""Tkinter GUI for the combined Fish and Plant Tycoon fix patcher."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

import cheat
import experimental
import tools_tab

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
FLOWER_NAMES_CREDIT = "Plant Tycoon flower names (Add unused flowers): credit to Virtual_Lady and Lorsieab2."
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

# --- Patch selection: the four preset buttons and Patch Selection Settings ---
# Laid out and worded as in the Virtual Villagers Fun Patcher (all the owner's
# patchers match). Each preset REPLACES the ticks in both games; a setting
# that needs another one brings it along (requires_settings).
PRESET_BUTTONS = (
    ("Select All Patches", "select_all"),
    ("Default Patches", "default_patches"),
    ("Owner's Defaults", "owners_defaults"),
    ("Deselect All Patches", "deselect_all"),
)
PRESET_TITLES = {key: text for text, key in PRESET_BUTTONS}
# The owner (2026-11-01): "a new Owner's Default's setting will turn every
# patch ON, except for the "everything is free" cheat." By exact id, as VV's
# Owner's Defaults lists the patches it leaves off. Free upgrades and Add
# Money are therefore ticked by it. The owner (2026-11-01): Owner's Defaults has
# "Render Unicode with In-Game Fonts" OFF (the owner's copies draw text with the
# Unicode font instead).
OWNERS_DEFAULTS_OFF = frozenset({"everything_free", "unicode_ingame_fonts"})
# The owner (2026-11-01): "anything that sets prices to 0 is DEFAULT OFF".
# Every setting that makes a price $0; tests pin them off by default and out
# of Default Patches.
PRICE_ZERO_SETTINGS = frozenset({"free_upgrades", "everything_free"})
PATCH_SELECTION_TITLE = "Patch Selection Settings"
PATCH_SELECTION_HEADING = "Tick or untick patches in every game at once"
PATCH_SELECTION_TEXT = (
    "Choose patches below, then press Tick These or Untick These. Each patch is "
    "changed in every game that has it (the games are listed beside its name). "
    "A patch that needs another one turns it on too, just as when you tick it yourself, "
    "and of two patches that cannot be on together only one stays ticked."
)
# The "?" guides for the patch selection buttons (VV: data/how_to_use.json).
PATCH_HELP = {
    "select_all": (
        "Select All Patches",
        [
            "Ticks every patch in both games.",
            "Except Everything is Free (a CHEAT), which you tick yourself.",
            "Of two patches that cannot both be on (the two Unicode text settings), it ticks the "
            "default one, Render Unicode with In-Game Fonts.",
            "It replaces the current ticks; any row can still be changed by hand afterwards.",
        ],
    ),
    "default_patches": (
        "Default Patches",
        [
            "Ticks each game's recommended set, the one a fresh install starts with: every fix, "
            "and the new fish, flowers, store items, Time Warp and the EXPERIMENTAL settings, so "
            "the copies are the \"- Modded Upgrades\" ones.",
            "Cheats and anything free stay off until you tick them: every setting that makes prices "
            "$0 (Free upgrades and Everything is Free), Add Money, Buy Multiple Golden Seahorses "
            "and the Optimize Prices button.",
            "It replaces the current ticks; any row can still be changed by hand afterwards.",
        ],
    ),
    "owners_defaults": (
        "Owner's Defaults",
        [
            "Ticks the patcher owner's own choice: every patch in both games except Everything is Free "
            "and Render Unicode with In-Game Fonts.",
            "On top of Default Patches that includes Free upgrades (every item on the Upgrades "
            "screen costs $0), Add Money, Buy Multiple Golden Seahorses and the Optimize Prices "
            "button.",
            "It replaces the current ticks; any row can still be changed by hand afterwards.",
        ],
    ),
    "deselect_all": (
        "Deselect All Patches",
        ["Unticks every patch in both games, so you can tick just the ones you want."],
    ),
    "patch_selection_settings": (
        "Patch Selection Settings",
        [
            "Opens a list of every patch by name, with the games that have it.",
            "Tick the patches you want, then press Tick These to turn them on in every game that "
            "has them, or Untick These to turn them off.",
            "A patch that needs another patch turns that one on too, just as when you tick it yourself.",
        ],
    ),
}


def with_requirements(game_id: str, ids) -> set[str]:
    """The settings plus every setting they need, as ticking them by hand does."""
    settings = patch_settings(game_id)
    chosen = {setting_id for setting_id in ids if setting_id in settings}
    pending = list(chosen)
    while pending:
        for needed in settings[pending.pop()].get("requires_settings", []):
            if needed in settings and needed not in chosen:
                chosen.add(needed)
                pending.append(needed)
    return chosen


def conflicts(game_id: str) -> dict[str, set[str]]:
    """Each setting's `conflicts_settings` (both ways round): settings that are never on together,
    such as the two Unicode text settings. Ticking one unticks the other."""
    settings = patch_settings(game_id)
    found: dict[str, set[str]] = {}
    for setting_id, setting in settings.items():
        for other in setting.get("conflicts_settings", []) or []:
            if other in settings:
                found.setdefault(setting_id, set()).add(other)
                found.setdefault(other, set()).add(setting_id)
    return found


def preferred_order(game_id: str, ids) -> list[str]:
    """`ids` in the order to tick them so that, of two that exclude each other, the default one
    (the one a fresh install has on) is ticked last and so stays on."""
    settings = patch_settings(game_id)
    return sorted(ids, key=lambda sid: (bool(settings.get(sid, {}).get("default", False)), sid))


def resolve_conflicts(game_id: str, ids) -> set[str]:
    """`ids` with at most one of each set of settings that exclude each other: the default one
    is kept (Select All Patches ticks "Render Unicode with In-Game Fonts", not "Use Unicode Font")."""
    chosen: set[str] = set()
    clash = conflicts(game_id)
    for sid in reversed(preferred_order(game_id, ids)):
        if not clash.get(sid, set()) & chosen:
            chosen.add(sid)
    return chosen


def preset_selection(preset: str, game_id: str) -> set[str]:
    """The exact settings a preset button ticks in one game."""
    settings = patch_settings(game_id)
    if preset == "select_all":
        ids = {sid for sid, s in settings.items() if cheat.in_enable_all(s)}
    elif preset == "default_patches":
        ids = {sid for sid, s in settings.items() if s.get("default", False)}
    elif preset == "owners_defaults":
        ids = {sid for sid in settings if sid not in OWNERS_DEFAULTS_OFF}
    elif preset == "deselect_all":
        ids = set()
    else:
        raise ValueError(f"unknown preset: {preset}")
    return with_requirements(game_id, resolve_conflicts(game_id, ids))


def patches_by_name() -> list[tuple[str, list[tuple[str, str]]]]:
    """One entry per patch name: (name, [(game_id, setting_id), ...]), in the
    order the patches first appear (Fish Tycoon's list, then Plant Tycoon's)."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for game_id in GAMES:
        for setting_id, setting in patch_settings(game_id).items():
            name = str(setting.get("name", setting_id))
            grouped.setdefault(name, []).append((game_id, setting_id))
    return list(grouped.items())


def games_label(entries: list[tuple[str, str]]) -> str:
    games = {game_id for game_id, _sid in entries}
    if len(games) == len(GAMES):
        return "both games"
    return ", ".join(GAMES[game_id].title for game_id in GAMES if game_id in games)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self._load_brand_images()
        self.geometry("1000x880")
        self.minsize(860, 620)
        self.busy = False
        self.game_choice = tk.StringVar(master=self, value="fish")
        self.output_parent = tk.StringVar(master=self)
        self.path_vars = {
            game_id: {
                "vanilla": tk.StringVar(master=self),
                "output": tk.StringVar(master=self),
                "backup": tk.StringVar(master=self),
            }
            for game_id in GAMES
        }
        self.patch_vars = {
            game_id: {
                setting_id: tk.BooleanVar(master=self, value=bool(setting.get("default", False)))
                for setting_id, setting in patch_settings(game_id).items()
            }
            for game_id in GAMES
        }
        self._link_setting_requirements()
        self.status_var = tk.StringVar(master=self,
            value="Choose one game or both games. Close the games before patching."
        )
        self.detect_status_var = tk.StringVar(master=self,
            value=(
                "Choose the folder that holds the game folders, and the patcher "
                "finds the exact Fish Tycoon.exe and Plant Tycoon.exe inside it."
            )
        )
        self.busy_controls: list[tk.Widget] = []
        # The Breeding Guide's options (Show Spoilers), remembered with the rest.
        self.breeding_settings: dict = {"show_spoilers": False}
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
            # Two settings that exclude each other: ticking one unticks the other.
            for setting_id, others in conflicts(game_id).items():
                for other in others:
                    if setting_id in variables and other in variables:
                        mine, theirs = variables[setting_id], variables[other]
                        mine.trace_add("write", lambda *_a, m=mine, t=theirs: m.get() and t.get() and t.set(False))

    def _load_brand_images(self) -> None:
        self.fish_picture = tk.PhotoImage(master=self, file=str(FISH_PICTURE_PATH))
        self.plant_picture = tk.PhotoImage(master=self, file=str(PLANT_PICTURE_PATH))
        self.fish_heading = self.fish_picture.subsample(4, 4)
        self.plant_heading = self.plant_picture.subsample(4, 4)
        self.fish_emoji = self.fish_picture.subsample(8, 8)
        self.plant_emoji = self.plant_picture.subsample(8, 8)

        # A native title bar accepts one square icon, so compose both supplied
        # pictures into that icon without modifying either source PNG.
        self.window_fish = self.fish_picture.subsample(12, 12)
        self.window_plant = self.plant_picture.subsample(12, 12)
        self.window_icon = tk.PhotoImage(master=self, width=32, height=32)
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
        self._build_patch_selection(outer)

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
        ttk.Label(outer, text=FLOWER_NAMES_CREDIT, font=("Segoe UI", 9)).pack(anchor="w")

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

    # --- Patch selection (both games) -------------------------------------

    def _build_patch_selection(self, outer: tk.Widget) -> None:
        """The VV patcher's row: Select All Patches, Default Patches, Owner's
        Defaults, Deselect All Patches (each with a "?"), and below it Patch
        Selection Settings... on its own row."""
        box = ttk.LabelFrame(outer, text="Patch selection (both games)", padding=8)
        box.pack(fill="x", pady=(0, 10))
        self.patch_selection_box = box
        actions = ttk.Frame(box)
        actions.pack(anchor="w")
        for index, (text, key) in enumerate(PRESET_BUTTONS):
            button = ttk.Button(actions, text=text, command=lambda k=key: self._apply_preset(k))
            button.pack(side="left", padx=(0 if index == 0 else 8, 0))
            self.busy_controls.append(button)
            self._patch_help_button(actions, key).pack(side="left", padx=(2, 0))
        settings_row = ttk.Frame(box)
        settings_row.pack(anchor="w", pady=(6, 0))
        button = ttk.Button(
            settings_row,
            text="Patch Selection Settings...",
            command=self._open_patch_selection_settings,
        )
        button.pack(side="left")
        self.busy_controls.append(button)
        self._patch_help_button(settings_row, "patch_selection_settings").pack(
            side="left", padx=(2, 0)
        )

    def _patch_help_button(self, parent: tk.Widget, key: str) -> ttk.Button:
        PATCH_HELP[key]  # a key with no guide fails while the window is built
        return ttk.Button(parent, text="?", width=2, command=lambda: self._show_patch_help(key))

    def _show_patch_help(self, key: str) -> tk.Toplevel:
        """The small "How to use" window for one button, as the Tools tab's."""
        windows = self.__dict__.setdefault("patch_help_windows", {})
        window = windows.get(key)
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            return window
        title, lines = PATCH_HELP[key]
        window = tk.Toplevel(self)
        window.title(f"How to use: {title}")
        window.transient(self)
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=title, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        for line in lines:
            ttk.Label(frame, text=line, wraplength=480, justify="left").pack(anchor="w", pady=(0, 6))
        ttk.Button(frame, text="Close", command=window.destroy).pack(anchor="e", pady=(6, 0))
        window.bind("<Escape>", lambda _e: window.destroy())
        windows[key] = window
        return window

    def _set_selection(self, game_id: str, chosen: set[str]) -> None:
        """Replace one game's ticks with exactly ``chosen`` (requirements included)."""
        variables = self.patch_vars[game_id]
        # Unticks first: unticking a setting unticks what needs it, and a
        # later tick of a dependent ticks its base again.
        for setting_id, variable in variables.items():
            if setting_id not in chosen and variable.get():
                variable.set(False)
        for setting_id, variable in variables.items():
            if setting_id in chosen and not variable.get():
                variable.set(True)

    def _apply_preset(self, preset: str) -> None:
        """One of the four preset buttons: replaces the ticks in both games."""
        for game_id in GAMES:
            self._set_selection(game_id, preset_selection(preset, game_id))
        self._save_settings()
        self.status_var.set(f"{PRESET_TITLES[preset]}: set in both games.")

    def _set_named_patches(self, names, tick: bool) -> int:
        """Tick or untick every game's patch with one of these names; return
        how many of those patches now have that state."""
        wanted = set(names)
        entries = [entry for name, group in patches_by_name() if name in wanted for entry in group]
        if tick:
            # Of two chosen patches that exclude each other, the default one is ticked last and stays on.
            order = {game_id: preferred_order(game_id, [sid for g, sid in entries if g == game_id]) for game_id in GAMES}
            entries = [(game_id, sid) for game_id in GAMES for sid in order[game_id]]
        for game_id, setting_id in entries:
            self.patch_vars[game_id][setting_id].set(tick)
        self._save_settings()
        return sum(1 for game_id, setting_id in entries if self.patch_vars[game_id][setting_id].get() == tick)

    def _open_patch_selection_settings(self) -> tk.Toplevel:
        """The owner: "an option to individually toggle patches across games
        on/off". One row per patch name; Tick These / Untick These apply the
        chosen names to every game that has a patch of that name (VV's
        Patch Selection Settings window)."""
        existing = getattr(self, "_patch_selection_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_set()
            return existing
        dialog = tk.Toplevel(self)
        dialog.title(PATCH_SELECTION_TITLE)
        dialog.transient(self)
        self._patch_selection_dialog = dialog
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=PATCH_SELECTION_HEADING, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(frame, text=PATCH_SELECTION_TEXT, wraplength=560, justify="left").pack(
            anchor="w", pady=(4, 10)
        )
        choices: list[tuple[str, tk.BooleanVar]] = []
        for name, entries in patches_by_name():
            var = tk.BooleanVar(master=dialog, value=False)
            ttk.Checkbutton(frame, text=f"{name}   ({games_label(entries)})", variable=var).pack(
                anchor="w", padx=(6, 0)
            )
            choices.append((name, var))
        self._patch_selection_choices = choices
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(14, 0))

        def apply(tick: bool) -> None:
            names = [name for name, var in choices if var.get()]
            if not names:
                messagebox.showinfo(
                    PATCH_SELECTION_TITLE, "Tick at least one patch in the list first.", parent=dialog
                )
                return
            count = self._set_named_patches(names, tick)
            self.status_var.set(
                f"{'Ticked' if tick else 'Unticked'} {count} patch"
                f"{'' if count == 1 else 'es'} across the games: {', '.join(names)}."
            )

        self._patch_selection_apply = apply
        ttk.Button(buttons, text="Tick These", command=lambda: apply(True)).pack(side="left")
        ttk.Button(buttons, text="Untick These", command=lambda: apply(False)).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        return dialog

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
        body = ttk.Frame(patches)
        body.grid(row=0, column=0, sticky="ew")
        patches.columnconfigure(0, weight=1)
        for setting_id, setting in patch_settings(game_id).items():
            entry = ttk.Frame(body)
            entry.pack(fill="x", anchor="w", pady=(0, 6))
            header = ttk.Frame(entry)
            header.pack(anchor="w")
            ttk.Checkbutton(
                header,
                text=str(setting.get("name", setting_id)),
                variable=self.patch_vars[game_id][setting_id],
                command=self._save_settings,
            ).pack(side="left")
            # The owner's label for the settings that change how much the game
            # holds (src/experimental.py): beside the name, in every tab.
            experimental_setting = experimental.is_experimental(setting)
            if experimental_setting:
                ttk.Label(
                    header,
                    text=experimental.LABEL,
                    foreground="#b00020",
                    font=("Segoe UI", 9, "bold"),
                ).pack(side="left", padx=(8, 0))
            # The cheat label (src/cheat.py), styled as the experimental one.
            if cheat.is_cheat(setting):
                ttk.Label(
                    header,
                    text=cheat.LABEL,
                    foreground="#b00020",
                    font=("Segoe UI", 9, "bold"),
                ).pack(side="left", padx=(8, 0))
            # What the setting adds or does, in plain words: shown everywhere,
            # including the compact Both Games panels.
            summary = str(setting.get("summary", "")).strip()
            if experimental_setting:
                summary = experimental.labelled(summary)
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
            description = str(setting.get("description", ""))
            if description.strip() == str(setting.get("summary", "")).strip():
                description = ""        # said once (Everything is Free's one sentence)
            if description or experimental_setting:
                ttk.Label(
                    entry,
                    text=experimental.labelled(description) if experimental_setting else description,
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

        shown = tk.BooleanVar(master=self, value=False)

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
        """The Tools tab, laid out and working like the Virtual Villagers Fun
        Patcher's (src/tools_tab.py)."""
        self.tools = tools_tab.ToolsTab(self, tab)

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
        breeding = data.get("breeding_guide")
        if isinstance(breeding, dict):
            self.breeding_settings = {"show_spoilers": bool(breeding.get("show_spoilers", False))}
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
            "breeding_guide": {"show_spoilers": bool(getattr(self, "breeding_settings", {}).get("show_spoilers", False))},
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
