"""The owner's experimental label (src/experimental.py): the settings that change how much the
game holds carry "experimental": true in the manifests, are on by default (the owner, 2026-11-01: new
content stays on), start their texts with
EXPERIMENTAL - USE AT OWN RISK, show that label beside their name in the GUI, and "Select All Patches"
still turns them on."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import experimental  # noqa: E402

EXPECTED = {
    "fish": {"bigger_tanks", "extra_tanks", "extra_supply_slots", "multiple_ornaments"},
    "plant": {"extra_greenhouses", "extra_nurseries", "extra_chemical_slots"},
}


def manifest(game: str) -> dict:
    return json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))


class ExperimentalSettings(unittest.TestCase):
    def test_exactly_these_settings_are_experimental(self) -> None:
        for game, ids in EXPECTED.items():
            flagged = {s["id"] for s in manifest(game)["settings"] if experimental.is_experimental(s)}
            self.assertEqual(flagged, ids, game)

    def test_on_by_default_and_labelled(self) -> None:
        for game in EXPECTED:
            for s in manifest(game)["settings"]:
                if not experimental.is_experimental(s):
                    self.assertNotIn(experimental.LABEL, s.get("summary", "") + s.get("description", ""), s["id"])
                    continue
                self.assertIs(s["default"], True, s["id"])
                self.assertTrue(s["summary"].startswith(experimental.PREFIX), s["id"])
                self.assertTrue(s["description"].startswith(experimental.PREFIX), s["id"])

    def test_mark_is_idempotent_and_keeps_order(self) -> None:
        setting = {"id": "x", "name": "X", "summary": "Does x.", "description": "More x.", "default": True,
                   "category": "main"}
        once = experimental.mark(setting)
        self.assertEqual(list(once), ["id", "name", "summary", "description", "default", "experimental", "category"])
        self.assertEqual(once["summary"], "EXPERIMENTAL - USE AT OWN RISK. Does x.")
        self.assertIs(once["default"], True)          # mark keeps the default it is given
        self.assertEqual(experimental.mark(once), once)
        self.assertIs(experimental.mark({"id": "y"})["default"], False)

    def test_pin_scripts_define_the_flag(self) -> None:
        """The pin scripts rewrite these settings from their own definitions, so the flag is there too."""
        sys.path.insert(0, str(ROOT / "scripts"))
        import pin_chem_slots
        import pin_extra_greenhouses
        import pin_extra_tanks
        import pin_multiple_ornaments
        import pin_supply_slots
        import pin_tank_expansion
        defined = [pin_tank_expansion.SETTING, pin_extra_tanks.SETTING, pin_multiple_ornaments.SETTING,
                   pin_supply_slots.SETTING,
                   *pin_extra_greenhouses.SETTINGS, pin_chem_slots.SETTING]
        self.assertEqual({s["id"] for s in defined}, EXPECTED["fish"] | EXPECTED["plant"])
        for s in defined:
            self.assertTrue(experimental.is_experimental(s), s["id"])
            self.assertIs(s["default"], True, s["id"])
        by_id = {s["id"]: s for game in EXPECTED for s in manifest(game)["settings"]}
        for s in defined:
            for key in ("summary", "description", "experimental", "default"):
                self.assertEqual(by_id[s["id"]][key], s[key], (s["id"], key))


class GuiLabel(unittest.TestCase):
    """The GUI shows the label beside the name and leaves "Select All Patches" turning everything on."""

    def test_label_next_to_the_name_and_enable_all(self) -> None:
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception as error:      # no display (CI)
            self.skipTest(f"no Tk: {error}")
        root.withdraw()
        try:
            import tycoon_fix_patcher_gui as gui
            from tkinter import ttk
            app = gui.App.__new__(gui.App)
            app.root = root
            app.patch_vars = {g: {sid: tk.BooleanVar(master=root, value=bool(s.get("default")))
                                  for sid, s in gui.patch_settings(g).items()} for g in EXPECTED}
            app.busy_controls = []
            app.path_vars = {g: {k: tk.StringVar(master=root) for k in ("vanilla", "output", "backup")}
                             for g in EXPECTED}
            app.status_var = tk.StringVar(master=root)
            app._save_settings = lambda: None
            app._technical_details = lambda *a, **k: None
            for game, ids in EXPECTED.items():
                frame = ttk.Frame(root)
                app._build_game_panel(frame, game, compact=False)
                texts: dict[str, list[str]] = {}

                def walk(widget) -> None:
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Frame):
                            labels = [c.cget("text") for c in child.winfo_children()
                                      if isinstance(c, (ttk.Checkbutton, ttk.Label))]
                            if labels:
                                texts[str(labels[0])] = [str(t) for t in labels]
                        walk(child)
                walk(frame)
                for sid, setting in gui.patch_settings(game).items():
                    row = texts[str(setting.get("name", sid))]
                    self.assertEqual(experimental.LABEL in row, sid in ids, (game, sid, row))
                for sid in ids:
                    self.assertTrue(app.patch_vars[game][sid].get(), (game, sid))     # on by default
                app._set_selection(game, gui.preset_selection("deselect_all", game))
                for sid in ids:
                    self.assertFalse(app.patch_vars[game][sid].get(), (game, sid))
                for preset in ("select_all", "owners_defaults", "default_patches"):
                    app._set_selection(game, gui.preset_selection("deselect_all", game))
                    app._set_selection(game, gui.preset_selection(preset, game))
                    for sid in ids:
                        self.assertTrue(app.patch_vars[game][sid].get(), (game, preset, sid))
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
