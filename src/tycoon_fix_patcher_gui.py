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

from tycoon_fix_patcher import (
    CombinedPatchError,
    GAMES,
    capture_run,
    default_output_dir,
    patch_settings,
    restore_game,
)


APP_NAME = "Fish & Plant Tycoon Fix Patcher"
CREATOR_DESCRIPTION = "🪴 Created with Codex AI. Made with love by Lorsieab2 :) 🐟"
ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "patcher_local_settings.json"
RELEASES_URL = (
    "https://github.com/Lorsieab2/Fish-and-Plant-Tycoon-Fix-Patcher/releases"
)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1000x880")
        self.minsize(860, 720)
        self.busy = False
        self.game_choice = tk.StringVar(value="fish")
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
        self.status_var = tk.StringVar(
            value="Choose one game or both games. Close the games before patching."
        )
        self._load_settings()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)

        heading = ttk.Frame(outer)
        heading.pack(fill="x")
        ttk.Label(
            heading, text="🐟🪴", font=("Segoe UI Emoji", 30)
        ).pack(side="left", padx=(0, 12))
        ttk.Label(
            heading, text=APP_NAME, font=("Segoe UI", 18, "bold")
        ).pack(side="left")
        ttk.Label(
            outer,
            text=CREATOR_DESCRIPTION,
            font=("Segoe UI Emoji", 10, "bold"),
        ).pack(anchor="w", pady=(2, 4))
        ttk.Label(
            outer,
            text=(
                "Creates verified fixed copies in separate folders. "
                "The selected vanilla folders are never replaced."
            ),
        ).pack(anchor="w")
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
        notebook.add(one, text="One Game")
        notebook.add(both, text="Both Games")
        self._build_one_tab(one)
        self._build_both_tab(both)

        status = ttk.LabelFrame(outer, text="Status and verification log", padding=10)
        status.pack(fill="both", expand=True, pady=(10, 0))
        ttk.Label(
            status, textvariable=self.status_var, wraplength=920, justify="left"
        ).pack(anchor="w")
        self.log = tk.Text(status, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(8, 0))

        ttk.Label(
            outer,
            text=CREATOR_DESCRIPTION,
            font=("Segoe UI Emoji", 9),
            foreground="#555555",
        ).pack(anchor="w", pady=(8, 0))

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
            text="Create Fixed Copy",
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
        ttk.Button(
            actions,
            text="Restore Output EXE from Backup",
            command=self._start_restore,
        ).pack(side="left", padx=8)

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

        actions = ttk.Frame(tab)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(
            actions,
            text="Find Both in Parent Folder...",
            command=self._find_both,
        ).pack(side="left")
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
            "Modded output folder",
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
        for row, (setting_id, setting) in enumerate(patch_settings(game_id).items()):
            ttk.Checkbutton(
                patches,
                text=str(setting.get("name", setting_id)),
                variable=self.patch_vars[game_id][setting_id],
                command=self._save_settings,
            ).grid(row=row * 2, column=0, sticky="w")
            if not compact:
                ttk.Label(
                    patches,
                    text=str(setting.get("description", "")),
                    wraplength=820,
                    foreground="#444444",
                ).grid(row=row * 2 + 1, column=0, sticky="w", padx=(24, 0), pady=(0, 4))

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
            variables["output"].set(str(default_output_dir(game_id, chosen)))
        self._save_settings()

    def _browse_output(self, game_id: str) -> None:
        spec = GAMES[game_id]
        current = self.path_vars[game_id]["output"].get().strip()
        chosen = filedialog.askdirectory(
            title=f"Choose the parent location for {spec.fixed_folder_name}",
            initialdir=current or str(Path.home()),
        )
        if not chosen:
            return
        candidate = Path(chosen)
        if candidate.name.casefold() != spec.fixed_folder_name.casefold():
            candidate /= spec.fixed_folder_name
        self.path_vars[game_id]["output"].set(str(candidate))
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
        root = Path(chosen)
        children = [path for path in root.iterdir() if path.is_dir()]
        problems = []
        for game_id, spec in GAMES.items():
            candidates = [root / spec.exe_name]
            candidates.extend(child / spec.exe_name for child in children)
            matches = [path for path in candidates if path.is_file()]
            if len(matches) == 1:
                vanilla = matches[0].parent
                self.path_vars[game_id]["vanilla"].set(str(vanilla))
                self.path_vars[game_id]["output"].set(
                    str(default_output_dir(game_id, vanilla))
                )
            elif not matches:
                problems.append(f"Not found: {spec.exe_name}")
            else:
                problems.append(f"More than one match: {spec.exe_name}")
        self._save_settings()
        if problems:
            messagebox.showwarning(APP_NAME, "\n".join(problems))
        else:
            self.status_var.set("Found both exact executable filenames. Ready to validate.")

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
                output = str(default_output_dir(game_id, vanilla))
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
            else ("Dry run" if dry_run else "Create fixed copy")
        )
        self.busy = True
        self.one_apply.configure(state="disabled")
        self.both_apply.configure(state="disabled")
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
        self.busy = True
        self.one_apply.configure(state="disabled")
        self.both_apply.configure(state="disabled")
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
        self.busy = False
        self.one_apply.configure(state="normal")
        self.both_apply.configure(state="normal")
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
        self.busy = False
        self.one_apply.configure(state="normal")
        self.both_apply.configure(state="normal")
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
            body, text="Fixed game folder(s) created successfully!", font=("Segoe UI", 15, "bold")
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
        game_data = data.get("games", {})
        for game_id in GAMES:
            saved = game_data.get(game_id, {}) if isinstance(game_data, dict) else {}
            if isinstance(saved, dict):
                self.path_vars[game_id]["vanilla"].set(str(saved.get("vanilla", "")))
                self.path_vars[game_id]["output"].set(str(saved.get("output", "")))
                self.path_vars[game_id]["backup"].set(str(saved.get("backup", "")))
                enabled = saved.get("enabled")
                if isinstance(enabled, list):
                    for setting_id, variable in self.patch_vars[game_id].items():
                        variable.set(setting_id in enabled)

    def _save_settings(self) -> None:
        data = {
            "selected_game": self.game_choice.get(),
            "games": {
                game_id: {
                    "vanilla": self.path_vars[game_id]["vanilla"].get().strip(),
                    "output": self.path_vars[game_id]["output"].get().strip(),
                    "backup": self.path_vars[game_id]["backup"].get().strip(),
                    "enabled": self._selected_settings(game_id),
                }
                for game_id in GAMES
            },
        }
        SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _close(self) -> None:
        if self.busy and not messagebox.askyesno(
            APP_NAME, "An operation is running. Close anyway?"
        ):
            return
        self._save_settings()
        self.destroy()


def main() -> int:
    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
