"""Picture Studio (Tools tab -> "Picture Studio..."): the fish and plants in a save, and
pictures you make yourself, drawn exactly as the game draws them, saved as transparent PNGs.

One window for both games, laid out like the Breeding Guide, with a renderer per game
(docs/picture-studio-interface.md): src/pictures_fish.py for Fish Tycoon and
src/pictures_plant.py for Plant Tycoon, picked up as soon as that module exists.

* "From my save": the save folder and player (read only), everything the save holds by
  tank or greenhouse (the extra ones from the patcher's files too), each drawn as the game
  draws it now; "Save PNG..." and "Save all in this tank/greenhouse...".
* "Make your own": a tab per subject (fish, creatures, decorations / plants ...), its parts,
  age or growth and state, by the game's own rules; with Show Spoilers off (the Breeding
  Guide's setting) only the parts the save has discovered.
* PNGs: transparent, cut to the drawn pixels with a small margin (or none), at the game's
  size, 2x or 4x (crisp) or any width and height (smooth).

The pictures come from the player's own game copy, kept in "Picture Studio Pictures" beside
the patcher (picture_image.picture_source); no game art ships with the patcher. Nothing is
ever written but the PNGs the player saves.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import breeding_guide
import picture_image as pi
import save_tools

TITLES = breeding_guide.TITLES
RENDERER_MODULES = {"fish": "pictures_fish", "plant": "pictures_plant"}
COMING = "Pictures for this game are coming in a later update."
PREVIEW = 300                         # the preview area's side, in pixels
CONTAINERS = {"fish": "tank", "plant": "greenhouse"}

HELP = (
    "Picture Studio",
    [
        "Shows the fish and plants in your saves, and pictures you make yourself, drawn exactly as the game "
        "draws them, and saves them as PNG pictures with a clear (transparent) background.",
        "From my save: pick the save folder and the player. The list shows everything the save holds, tank "
        "by tank (Fish Tycoon: Tanks 1-3, the isolation tank, and Tanks 4-6 with the patcher's 3 extra tanks) "
        "or greenhouse by greenhouse (Plant Tycoon, with the patcher's extra greenhouses), then the creatures "
        "and decorations. Click one to see it as the game draws it now, at its own age, growth and state. "
        "Fish can be shown swimming either way, or turning, at any of their frames.",
        "Make your own: pick the parts (a body and a fin, or a foliage and a flower), the age or growth "
        "stage and the state, and see the picture the game would draw. The stages follow the game's own "
        "rules. Creatures and decorations are on their own tabs. The patcher's parts and creatures (DS "
        "Exclusive Fish, DS Store Items, Unused Flowers) are offered when the save's game copy was patched "
        "with them.",
        "Show Spoilers is the Breeding Guide's setting: off, Make your own offers only the parts your save "
        "has discovered.",
        "Saving: \"Save PNG...\" saves the picture shown. Pick the size first: the game's own size, 2x or 4x "
        "(each pixel made a crisp square), or your own width and height (smoothly scaled; leave one empty to "
        "keep the shape). The picture is cut to what is drawn, with a small clear margin, or none if you untick "
        "it. \"Save all in this tank\" (or greenhouse) saves every picture in it into a new folder.",
        "The pictures come from your own copy of the game: the first time the window finds one, it copies the "
        "pictures it needs into its own folder, \"Picture Studio Pictures\" beside the patcher, and uses them "
        "from then on. If it has not found one yet, click \"Find game...\" and pick your game folder. Your saves "
        "and game folders are only read, never changed.",
    ],
)


def show_help(parent: tk.Misc) -> tk.Toplevel:
    title, lines = HELP
    window = tk.Toplevel(parent)
    window.title(f"How to use: {title}")
    window.transient(parent)
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=title, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
    ttk.Button(frame, text="Close", command=window.destroy).pack(side="bottom", anchor="e", pady=(6, 0))
    body = ttk.Frame(frame)
    body.pack(fill="both", expand=True)
    rows = max(10, min(32, (window.winfo_screenheight() - 200) // 17))
    text = tk.Text(body, width=78, height=rows, wrap="word", font=("Segoe UI", 9), relief="flat", borderwidth=0,
                   background=ttk.Style(window).lookup("TFrame", "background") or "#f0f0f0")
    scroll = ttk.Scrollbar(body, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)
    text.insert("1.0", "\n\n".join(lines))
    text.configure(state="disabled")
    window.help_text = text
    window.bind("<Escape>", lambda _e: window.destroy())
    return window


# ------------------------------------------------------------------ what the save's copy has

LOG_NAMES = {"fish": "FishTycoonBugFixPatchLog.json", "plant": "PlantTycoonFixPatchLog.json"}
# Patcher files beside a save that show a setting was on, when no game copy is found.
SIDECAR_SIGNS = {
    "fish": (("ds_fish", "DS Fish {slot}.dat"), ("ds_store", "Tank Animals {slot}.dat"),
             ("extra_tanks", "Extra Tanks {slot}.dat"), ("multiple_ornaments", "Ornaments {slot}.dat")),
    "plant": (("new_flowers", "New Flowers {slot}.dat"),),
}
SIDECAR_FOLDERS = {"fish": "Fish Tycoon Fix Patcher Data", "plant": "Plant Tycoon Fix Patcher Data"}


def detect_settings(game_id: str, save_folder: Path | None, slot: int | None, parents=()) -> tuple[frozenset, str]:
    """(setting ids, why): the patcher settings the save's game copy was patched with (its patch
    log beside the .exe), else the patcher files beside the save. Read only."""
    if save_folder is None:
        return frozenset(), "No save chosen: only the stock game's parts."
    copy = breeding_guide.find_game_copy(save_folder, parents)
    if copy is not None:
        try:
            log = json.loads((copy / LOG_NAMES[game_id]).read_text(encoding="utf-8"))
            enabled = log.get("enabled_settings")
        except (OSError, ValueError, AttributeError):
            enabled = None
        if isinstance(enabled, list):
            return frozenset(str(s) for s in enabled), f"The patcher's settings come from {copy}."
    found = set()
    if slot is not None:
        folder = Path(save_folder) / SIDECAR_FOLDERS[game_id]
        found = {setting for setting, name in SIDECAR_SIGNS.get(game_id, ()) if (folder / name.format(slot=slot)).is_file()}
    return frozenset(found), "No game copy was found for this save; its patcher files were read instead."


def load_renderer_module(game_id: str):
    try:
        return importlib.import_module(RENDERER_MODULES[game_id])
    except ImportError:
        return None


# ------------------------------------------------------------------ export choices


def export_options(size: str, width: str = "", height: str = "", margin: bool = True) -> dict:
    """The options for picture_image.export from the window's choices: "1x" / "2x" / "4x", or
    "custom" with a width and/or height in pixels."""
    options: dict = {"margin": pi.MARGIN if margin else 0}
    if size == "custom":
        def number(text: str) -> int:
            text = str(text or "").strip()
            if not text:
                return 0
            if not text.isdigit() or int(text) <= 0:
                raise pi.PictureError("A width or height is a whole number of pixels, 1 or more.")
            return int(text)
        options["size"] = (number(width), number(height))
    else:
        options["scale"] = dict(pi.SIZES).get(size, 1)
    return options


# ------------------------------------------------------------------ the window

_open_window: "PictureStudio | None" = None


def open_window(parent: tk.Misc, game_id: str = "fish", *, settings: dict | None = None, save_settings=None,
                documents: Path | None = None, game_parents=()) -> "PictureStudio":
    """Open (or raise) Picture Studio. `settings` is the Breeding Guide's (its "show_spoilers"
    is shared); `game_parents` are folders the game copies may sit in."""
    global _open_window
    if _open_window is not None and _open_window.window.winfo_exists():
        _open_window.window.deiconify()
        _open_window.window.lift()
        if game_id in TITLES:
            _open_window.game_var.set(TITLES[game_id])
        return _open_window
    _open_window = PictureStudio(parent, game_id, settings=settings, save_settings=save_settings,
                                 documents=documents, game_parents=game_parents)
    return _open_window


class PictureStudio:
    def __init__(self, parent: tk.Misc, game_id: str = "fish", *, settings: dict | None = None,
                 save_settings=None, documents: Path | None = None, game_parents=()) -> None:
        self.settings = settings if settings is not None else {}
        self.save_settings = save_settings
        self.documents = documents
        self.game_parents = list(game_parents)
        self.window = tk.Toplevel(parent)
        self.window.title("Picture Studio")
        screen_w, screen_h = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        width, height = min(1180, screen_w - 60), min(800, screen_h - 110)
        self.window.geometry(f"{width}x{height}+{max(0, (screen_w - width) // 2)}+{max(0, (screen_h - height) // 3)}")
        self.window.minsize(min(760, width), min(500, height))
        self.window.bind("<Escape>", lambda _e: self.close())
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.game_var = tk.StringVar(master=self.window, value=TITLES.get(game_id, TITLES["fish"]))
        self.folder_var = tk.StringVar(master=self.window)
        self.slot_var = tk.StringVar(master=self.window)
        self.status_var = tk.StringVar(master=self.window)
        self.spoilers_var = tk.BooleanVar(master=self.window, value=bool(self.settings.get("show_spoilers", False)))
        self.size_var = tk.StringVar(master=self.window, value="1x")
        self.width_var = tk.StringVar(master=self.window)
        self.height_var = tk.StringVar(master=self.window)
        self.margin_var = tk.BooleanVar(master=self.window, value=True)
        self.facing_var = tk.StringVar(master=self.window, value="left")
        self.frame_var = tk.StringVar(master=self.window, value="Frame 1")
        self.folders: list[Path] = []
        self.slots: list[tuple[int, str]] = []
        self.renderer = None
        self.module = None
        self.extras: frozenset = frozenset()
        self.discovered = None
        self.items: list[pi.SavedItem] = []
        self.shown: dict[str, object] = {}            # "save" / "custom" -> the Image shown
        self.custom_boxes: dict[str, dict] = {}
        self.subjects: list[pi.Subject] = []
        self.problem_text = ""
        self.quiet = False                            # tests: messages are kept, not shown
        self.last_message = ""
        self._build()
        self.game_var.trace_add("write", lambda *_a: self._load_folders())
        self.spoilers_var.trace_add("write", lambda *_a: self._spoilers_changed())
        self._load_folders()

    # ---- layout
    def _build(self) -> None:
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)
        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text="Game:").pack(side="left")
        ttk.Combobox(top, textvariable=self.game_var, values=list(TITLES.values()), state="readonly",
                     width=14).pack(side="left", padx=(4, 12))
        ttk.Label(top, text="Save folder:").pack(side="left")
        self.folder_box = ttk.Combobox(top, textvariable=self.folder_var, state="readonly", width=34)
        self.folder_box.pack(side="left", padx=(4, 12))
        self.folder_box.bind("<<ComboboxSelected>>", lambda _e: self._load_slots())
        ttk.Label(top, text="Player:").pack(side="left")
        self.slot_box = ttk.Combobox(top, textvariable=self.slot_var, state="readonly", width=26)
        self.slot_box.pack(side="left", padx=(4, 12))
        self.slot_box.bind("<<ComboboxSelected>>", lambda _e: self._reload())
        ttk.Button(top, text="?", width=2, command=lambda: show_help(self.window)).pack(side="right")
        self.find_button = ttk.Button(top, text="Find game...", command=self.find_game)
        ttk.Label(outer, textvariable=self.status_var, foreground="#245a9a", wraplength=1100,
                  justify="left").pack(anchor="w", pady=(6, 0))

        options = ttk.LabelFrame(outer, text="Options", padding=(10, 4))
        options.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(options, text="Show Spoilers", variable=self.spoilers_var).pack(side="left")
        ttk.Label(options, text="(every part, not only the ones you have discovered)").pack(side="left", padx=(6, 18))
        ttk.Label(options, text="PNG size:").pack(side="left")
        for label, value in (("Game size", "1x"), ("2x", "2x"), ("4x", "4x"), ("Custom:", "custom")):
            ttk.Radiobutton(options, text=label, value=value, variable=self.size_var).pack(side="left", padx=(4, 0))
        self.width_entry = ttk.Entry(options, textvariable=self.width_var, width=6)
        self.width_entry.pack(side="left", padx=(2, 0))
        ttk.Label(options, text="x").pack(side="left", padx=2)
        self.height_entry = ttk.Entry(options, textvariable=self.height_var, width=6)
        self.height_entry.pack(side="left")
        ttk.Label(options, text="px").pack(side="left", padx=(2, 12))
        ttk.Checkbutton(options, text="Small margin", variable=self.margin_var).pack(side="left")

        self.body = ttk.Frame(outer)
        self.body.pack(fill="both", expand=True, pady=(8, 0))
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Button(bottom, text="Close", command=self.close).pack(side="right")

    def close(self) -> None:
        global _open_window
        if _open_window is self:
            _open_window = None
        if self.window.winfo_exists():
            self.window.destroy()

    @property
    def game_id(self) -> str:
        return next((g for g, t in TITLES.items() if t == self.game_var.get()), "fish")

    # ---- save choice (as the Breeding Guide's)
    def _load_folders(self) -> None:
        try:
            self.folders = save_tools.save_folders(self.game_id, self.documents)
        except OSError:
            self.folders = []
        self.folder_box.configure(values=[f.name for f in self.folders])
        if self.folders:
            modded = [i for i, f in enumerate(self.folders) if " - Modded" in f.name]
            self.folder_box.current(modded[0] if modded else 0)
        else:
            self.folder_var.set("")
        self._load_slots()

    def _load_slots(self) -> None:
        self.slots = []
        folder = self.current_folder()
        if folder is not None:
            try:
                names = save_tools.read_slot_names(self.game_id, folder)
            except (OSError, save_tools.SaveToolError):
                names = []
            self.slots = [(slot, name) for slot, name in enumerate(names, start=1)
                          if save_tools.slot_is_active(self.game_id, folder, slot, name)]
        self.slot_box.configure(values=[f"Player {slot}: {name}" for slot, name in self.slots])
        if self.slots:
            self.slot_box.current(0)
        else:
            self.slot_var.set("")
        self._reload()

    def current_folder(self) -> Path | None:
        index = self.folder_box.current()
        return self.folders[index] if 0 <= index < len(self.folders) else None

    def current_slot(self) -> int | None:
        index = self.slot_box.current()
        return self.slots[index][0] if 0 <= index < len(self.slots) else None

    def _spoilers_changed(self) -> None:
        self.settings["show_spoilers"] = bool(self.spoilers_var.get())
        if self.save_settings is not None:
            try:
                self.save_settings()
            except Exception:                      # remembering is a convenience, never an error
                pass
        self._fill_custom()

    # ---- the renderer
    def _reload(self) -> None:
        game = self.game_id
        folder, slot = self.current_folder(), self.current_slot()
        parents = breeding_guide.lookup_parents(self.game_parents)
        self.extras, extras_reason = detect_settings(game, folder, slot, parents)
        copy = breeding_guide.find_game_copy(folder, parents) if folder is not None else None
        self.module = load_renderer_module(game)
        self.renderer = None
        self.discovered = None
        problems = []
        if self.module is not None:
            copies = breeding_guide.art_copies(game, folder, self.game_parents)
            source = pi.picture_source(game, copies, self.module.required_files(), self.module.patcher_art())
            self.renderer = self.module.load(source)
            if source.problem:
                problems.append(source.problem)
            model = breeding_guide.load_model(game, copy, "ds_fish" in self.extras or "new_flowers" in self.extras)
            if model is not None and folder is not None and slot is not None:
                try:
                    self.discovered = set(model.discovered(folder, slot))
                except Exception as exc:           # an unreadable save shows as no discoveries
                    problems.append(f"The save's discoveries could not be read: {exc}")
                    self.discovered = set()
        self.problem_text = " ".join(problems)
        save = f"{self.folder_var.get()}, {self.slot_var.get()}." if slot is not None else "No save chosen."
        self.status_var.set(" ".join(x for x in (save, self.problem_text, extras_reason) if x))
        if self.problem_text and self.renderer is not None:
            self.find_button.pack(side="right", padx=(0, 8))
        else:
            self.find_button.pack_forget()
        self._refresh()

    def _refresh(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self.shown.clear()
        if self.renderer is None:
            ttk.Label(self.body, text=COMING, font=("Segoe UI", 11)).pack(anchor="w", pady=20)
            self.status_var.set(COMING)
            return
        self.notebook = ttk.Notebook(self.body)
        self.notebook.pack(fill="both", expand=True)
        self._build_save_tab()
        self._build_custom_tab()

    # ---- From my save
    def _preview_pane(self, parent, kind: str) -> dict:
        pane = ttk.Frame(parent, padding=(10, 0))
        style = ttk.Style(self.window)
        canvas = tk.Canvas(pane, width=PREVIEW, height=PREVIEW, highlightthickness=1, highlightbackground="#c0c0c0",
                           background=style.lookup("TFrame", "background") or "#f0f0f0")
        canvas.pack(anchor="n")
        info = ttk.Label(pane, text="", wraplength=PREVIEW, justify="left")
        info.pack(anchor="w", pady=(6, 0))
        return {"pane": pane, "canvas": canvas, "info": info, "kind": kind}

    def _build_save_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab, text="From my save")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="both", expand=True)
        self.save_tree = ttk.Treeview(left, columns=("what",), show="tree headings", selectmode="browse")
        self.save_tree.heading("#0", text="In the save")
        self.save_tree.heading("what", text="Kind")
        self.save_tree.column("#0", width=430)
        self.save_tree.column("what", width=100, stretch=False)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.save_tree.yview)
        self.save_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.save_tree.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(tab)
        right.pack(side="left", fill="y")
        self.save_preview = self._preview_pane(right, "save")
        self.save_preview["pane"].pack(fill="x")
        ways = ttk.Frame(right, padding=(10, 6))
        ways.pack(fill="x")
        ttk.Label(ways, text="Swimming:").grid(row=0, column=0, sticky="w")
        self.facing_box = ttk.Combobox(ways, state="readonly", width=18,
                                       values=["Swimming left", "Swimming right", "Turning"])
        self.facing_box.current(0)
        self.facing_box.grid(row=0, column=1, sticky="w", padx=(4, 0))
        ttk.Label(ways, text="Frame:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.frame_box = ttk.Combobox(ways, state="readonly", width=18, values=[f"Frame {k + 1}" for k in range(6)])
        self.frame_box.current(0)
        self.frame_box.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))
        for box in (self.facing_box, self.frame_box):
            box.bind("<<ComboboxSelected>>", lambda _e: self._show_saved())
        buttons = ttk.Frame(right, padding=(10, 6))
        buttons.pack(fill="x")
        self.save_png_button = ttk.Button(buttons, text="Save PNG...", command=lambda: self.save_png("save"))
        self.save_png_button.pack(anchor="w")
        word = CONTAINERS.get(self.game_id, "tank")
        self.save_all_button = ttk.Button(buttons, text=f"Save all in this {word}...", command=self.save_all)
        self.save_all_button.pack(anchor="w", pady=(6, 0))
        self.save_tree.bind("<<TreeviewSelect>>", lambda _e: self._show_saved())
        self._fill_save_list()

    def _fill_save_list(self) -> None:
        tree = self.save_tree
        tree.delete(*tree.get_children())
        self.items = []
        self.item_nodes: dict[str, pi.SavedItem] = {}
        self.location_nodes: dict[str, str] = {}
        folder, slot = self.current_folder(), self.current_slot()
        if folder is None or slot is None:
            self.save_preview["info"].configure(text="Pick a save folder and a player to see what the save holds.")
            return
        try:
            self.items = self.renderer.saved_items(folder, slot)
        except Exception as exc:
            self.save_preview["info"].configure(text=f"The save could not be read: {exc}", foreground="#a01010")
            return
        for item in self.items:
            parent = self.location_nodes.get(item.location)
            if parent is None:
                parent = tree.insert("", "end", text=item.location, open=True)
                self.location_nodes[item.location] = parent
            node = tree.insert(parent, "end", text=item.label, values=(item.kind,))
            self.item_nodes[node] = item
        if not self.items:
            self.save_preview["info"].configure(text="Nothing in this save is drawn yet.")

    def selected_item(self) -> pi.SavedItem | None:
        selection = self.save_tree.selection()
        return self.item_nodes.get(selection[0]) if selection else None

    def selected_location(self) -> str | None:
        selection = self.save_tree.selection()
        if not selection:
            return None
        node = selection[0]
        item = self.item_nodes.get(node)
        return item.location if item is not None else self.save_tree.item(node, "text")

    def saved_options(self) -> dict:
        facing = ("left", "right", "turn")[max(0, self.facing_box.current())]
        return {"facing": facing, "frame": max(0, self.frame_box.current())}

    def render_item(self, item: pi.SavedItem):
        options = self.saved_options() if self.game_id == "fish" else {}
        return self.renderer.render_saved(self.current_folder(), self.current_slot(), item.id, **options)

    def _show_saved(self) -> None:
        item = self.selected_item()
        if item is None:
            return
        try:
            image = self.render_item(item)
        except Exception as exc:
            self._show(self.save_preview, None, f"{item.label}: this cannot be drawn ({exc}).")
            self.shown.pop("save", None)
            return
        self.shown["save"] = image
        self._show(self.save_preview, image, item.detail or item.label)

    def _show(self, preview: dict, image, text: str) -> None:
        canvas = preview["canvas"]
        canvas.delete("all")
        preview["info"].configure(text=text, foreground="")
        if image is None:
            return
        shown = image.cropped(pi.MARGIN)
        biggest = max(shown.width, shown.height, 1)
        if biggest <= PREVIEW:
            factor = max(1, min(4, PREVIEW // biggest))
            photo = shown.photo(tk, self.window)
            if factor > 1:
                photo = photo.zoom(factor)
        else:
            photo = shown.photo(tk, self.window, max_side=PREVIEW)
        canvas.create_image(PREVIEW // 2, PREVIEW // 2, image=photo)
        canvas.photo = photo

    # ---- Make your own
    def _build_custom_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab, text="Make your own")
        self.custom_tab = tab
        left = ttk.Frame(tab)
        left.pack(side="left", fill="both", expand=True)
        self.custom_notebook = ttk.Notebook(left)
        self.custom_notebook.pack(fill="both", expand=True)
        right = ttk.Frame(tab)
        right.pack(side="left", fill="y")
        self.custom_preview = self._preview_pane(right, "custom")
        self.custom_preview["pane"].pack(fill="x")
        buttons = ttk.Frame(right, padding=(10, 6))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Save PNG...", command=lambda: self.save_png("custom")).pack(anchor="w")
        self.custom_notebook.bind("<<NotebookTabChanged>>", lambda _e: self._show_custom())
        self._fill_custom()

    def _fill_custom(self) -> None:
        if self.renderer is None or not hasattr(self, "custom_notebook") or not self.custom_notebook.winfo_exists():
            return
        picks = {key: {f: box["var"].get() for f, box in fields.items()} for key, fields in self.custom_boxes.items()}
        for tab in self.custom_notebook.tabs():
            self.custom_notebook.forget(tab)
        self.custom_boxes = {}
        self.subjects = self.renderer.custom_choices(self.extras, bool(self.spoilers_var.get()), self.discovered)
        for subject in self.subjects:
            frame = ttk.Frame(self.custom_notebook, padding=10)
            self.custom_notebook.add(frame, text=subject.title)
            boxes = {}
            for row, field in enumerate(subject.fields):
                ttk.Label(frame, text=f"{field.label}:").grid(row=row, column=0, sticky="w", pady=3)
                labels = [o.label + ("  (patcher)" if o.patcher else "") for o in field.options]
                var = tk.StringVar(master=self.window)
                box = ttk.Combobox(frame, textvariable=var, values=labels, state="readonly", width=40)
                box.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=3)
                keep = picks.get(subject.key, {}).get(field.key)
                if keep in labels:
                    box.current(labels.index(keep))
                else:
                    keys = [o.key for o in field.options]
                    if field.default in keys:
                        box.current(keys.index(field.default))
                    elif labels:
                        box.current(0)
                box.bind("<<ComboboxSelected>>", lambda _e: self._show_custom())
                boxes[field.key] = {"box": box, "var": var, "field": field}
            if subject.note:
                ttk.Label(frame, text=subject.note, wraplength=520, justify="left", foreground="#555555").grid(
                    row=len(subject.fields), column=0, columnspan=2, sticky="w", pady=(10, 0))
            if any(not b["field"].options for b in boxes.values()):
                ttk.Label(frame, text="Nothing to pick here yet: discover some in the game, or tick Show Spoilers.",
                          foreground="#a01010").grid(row=len(subject.fields) + 1, column=0, columnspan=2, sticky="w",
                                                     pady=(6, 0))
            self.custom_boxes[subject.key] = boxes
        self._show_custom()

    def current_subject(self) -> pi.Subject | None:
        try:
            index = self.custom_notebook.index(self.custom_notebook.select())
        except tk.TclError:
            return None
        return self.subjects[index] if 0 <= index < len(self.subjects) else None

    def custom_spec(self) -> dict | None:
        subject = self.current_subject()
        if subject is None:
            return None
        spec: dict = {"subject": subject.key}
        for key, box in self.custom_boxes[subject.key].items():
            index = box["box"].current()
            options = box["field"].options
            spec[key] = options[index].key if 0 <= index < len(options) else None
        return spec

    def _show_custom(self) -> None:
        spec = self.custom_spec()
        if spec is None:
            return
        try:
            image = self.renderer.render_custom(spec)
        except Exception as exc:
            self.shown.pop("custom", None)
            self._show(self.custom_preview, None, f"This cannot be drawn: {exc}")
            return
        self.shown["custom"] = image
        self._show(self.custom_preview, image, "")

    # ---- saving
    def export_choice(self) -> dict:
        return export_options(self.size_var.get(), self.width_var.get(), self.height_var.get(), self.margin_var.get())

    def picture_name(self, which: str) -> str:
        if which == "save":
            item = self.selected_item()
            return pi.safe_file_name(item.label if item else "picture")
        spec = self.custom_spec() or {}
        subject = self.current_subject()
        parts = []
        if subject is not None:
            for key, box in self.custom_boxes.get(subject.key, {}).items():
                index = box["box"].current()
                if 0 <= index < len(box["field"].options):
                    parts.append(box["field"].options[index].label)
        return pi.safe_file_name(" - ".join(parts) or spec.get("subject", "picture"))

    def save_png(self, which: str, path: str | None = None) -> Path | None:
        image = self.shown.get(which)
        if image is None:
            self._tell("info", "Pick a picture first.")
            return None
        try:
            options = self.export_choice()
        except pi.PictureError as exc:
            self._tell("warning", str(exc))
            return None
        if path is None:
            path = filedialog.asksaveasfilename(parent=self.window, title="Save PNG", defaultextension=".png",
                                                initialfile=self.picture_name(which) + ".png",
                                                filetypes=[("PNG picture", "*.png")])
        if not path:
            return None
        try:
            return pi.save_png(image, path, **options)
        except (OSError, pi.PictureError) as exc:
            self._tell("warning", f"The picture could not be saved: {exc}")
            return None

    def save_all(self, folder: str | None = None) -> Path | None:
        location = self.selected_location()
        if location is None:
            self._tell("info", f"Pick a {CONTAINERS.get(self.game_id, 'tank')} (or anything in it) "
                                "first.")
            return None
        try:
            options = self.export_choice()
        except pi.PictureError as exc:
            self._tell("warning", str(exc))
            return None
        if folder is None:
            folder = filedialog.askdirectory(parent=self.window, title="Save the pictures in...")
        if not folder:
            return None
        player = self.slot_var.get().split(": ", 1)[-1] if self.current_slot() is not None else "Save"
        target = Path(folder) / pi.safe_file_name(f"{player} - {location}")
        n = 2
        while target.exists():
            target = Path(folder) / pi.safe_file_name(f"{player} - {location} ({n})")
            n += 1
        failed = []
        saved = 0
        try:
            target.mkdir(parents=True)
        except OSError as exc:
            self._tell("warning", f"The folder could not be made: {exc}")
            return None
        for item in self.items:
            if item.location != location:
                continue
            try:
                image = self.render_item(item)
                pi.save_png(image, pi.unique_path(target, pi.safe_file_name(item.label)), **options)
                saved += 1
            except (OSError, pi.PictureError) as exc:
                failed.append(f"{item.label}: {exc}")
        text = f"{saved} picture(s) saved in {target}."
        if failed:
            text += "\nNot saved:\n" + "\n".join(failed[:10])
        self._tell("info", text)
        return target

    def _tell(self, kind: str, text: str) -> None:
        self.last_message = text
        if not self.quiet:
            (messagebox.showwarning if kind == "warning" else messagebox.showinfo)("Picture Studio", text, parent=self.window)

    # ---- the pictures
    def find_game(self, chosen: str | None = None) -> str:
        """"Find game...": pick a game folder; the pictures are copied from it into the
        Studio's own folder (the game folder is only read)."""
        game = self.game_id
        title = TITLES.get(game, "the game")
        if self.module is None:
            return ""
        if chosen is None:
            chosen = filedialog.askdirectory(parent=self.window, title=f"Choose your {title} game folder")
        if not chosen:
            return ""
        folder = Path(chosen)
        copies = [folder] if breeding_guide.is_game_copy(game, folder) else breeding_guide.art_copies(game, None, [folder])
        if not copies:
            result = f"No {title} game was found in {folder} or the folders in it."
            self._tell("warning", result)
            return result
        source = pi.picture_source(game, copies, self.module.required_files(), self.module.patcher_art())
        if source.problem:
            self._tell("warning", f"The pictures could not be read: {source.problem}",)
            return source.problem
        self.game_parents.append(str(copies[0]))
        self._reload()
        return ""
