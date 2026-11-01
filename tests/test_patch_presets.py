"""The patch selection buttons, laid out and worded as in the Virtual Villagers Fun Patcher.

The owner (2026-11-01): "anything that sets prices to 0 is DEFAULT OFF - (a new Owner's Default's
setting will turn every patch ON, except for the "everything is free" cheat). And add an option to
individually toggle patches across games on/off".

  * Select All Patches / Default Patches / Owner's Defaults / Deselect All Patches (each with a
    "?") replace the ticks in both games with exactly the sets pinned here;
  * every setting that makes a price $0 is off by default and out of Default Patches;
  * Patch Selection Settings ticks or unticks a patch name in every game that has it;
  * the choices are remembered in patcher_local_settings.json.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import tycoon_fix_patcher_gui as gui  # noqa: E402
from tycoon_fix_patcher import patch_settings  # noqa: E402

# The owner's defaults (2026-11-01): "Anything that costs (money tech points food etc) and anything
# that adds new content to the game (besides the stuff I explicitly mentioned to turn off) stays ON
# by default." Off: the cheats and anything free.
DEFAULT_OFF = {"everything_free", "free_upgrades", "add_money", "golden_seahorse_repurchase",
               "optimize_prices", "unicode_system_font"}
DEFAULTS = {
    "fish": {
        "fix_vanilla_bugs", "crimson_comet_20_percent_cure", "unknown_chemical_three_uses",
        "universal_supply_slots", "maximizable_window", "tank_greenhouse_counts",
        "ds_fish", "ds_store", "time_warp", "bigger_tanks", "extra_tanks", "extra_supply_slots",
        "multiple_ornaments", "unicode_ingame_fonts",
    },
    "plant": {
        "fix_vanilla_bugs", "no_old_age_plant_deaths", "seed_refresh_key", "add_missing_ldw_assets",
        "tank_greenhouse_counts", "new_flowers", "plant_upgrades", "sort_seeds", "time_warp",
        "extra_greenhouses", "extra_nurseries", "extra_chemical_slots", "unicode_ingame_fonts",
    },
}
EVERY = {game: set(patch_settings(game)) for game in ("fish", "plant")}
EXPECTED = {
    # of the two Unicode settings (they exclude each other) Select All keeps the default one
    "select_all": {game: EVERY[game] - {"everything_free", "unicode_system_font"} for game in EVERY},
    "default_patches": DEFAULTS,
    "owners_defaults": {game: EVERY[game] - {"everything_free", "unicode_ingame_fonts"} for game in EVERY},
    "deselect_all": {game: set() for game in EVERY},
}


def _tk_or_skip(case: unittest.TestCase) -> None:
    import tkinter

    try:
        tkinter.Tk().destroy()
    except tkinter.TclError as exc:
        case.skipTest(f"no display for Tk: {exc}")


def _ticked(app) -> dict[str, set[str]]:
    return {game: {sid for sid, var in variables.items() if var.get()}
            for game, variables in app.patch_vars.items()}


def _texts(widget) -> list[str]:
    out, pending = [], [widget]
    while pending:
        current = pending.pop(0)
        pending.extend(current.winfo_children())
        try:
            out.append(str(current.cget("text")))
        except Exception:
            continue
    return out


class PresetSetTests(unittest.TestCase):
    def test_each_preset_is_exactly_its_set(self) -> None:
        for preset, per_game in EXPECTED.items():
            for game, expected in per_game.items():
                self.assertEqual(gui.preset_selection(preset, game), expected, (preset, game))

    def test_owners_defaults_includes_the_paid_cheats_but_not_everything_is_free(self) -> None:
        # Literally per the owner: every patch on, Everything is Free off; Free upgrades and Add
        # Money are on.
        for game in EVERY:
            chosen = gui.preset_selection("owners_defaults", game)
            self.assertNotIn("everything_free", chosen)
            self.assertTrue({"free_upgrades", "add_money", "time_warp"} <= chosen, game)
        self.assertEqual(gui.OWNERS_DEFAULTS_OFF, {"everything_free", "unicode_ingame_fonts"})

    def test_presets_keep_requirements(self) -> None:
        for preset in EXPECTED:
            for game in EVERY:
                chosen = gui.preset_selection(preset, game)
                for sid in chosen:
                    for needed in patch_settings(game)[sid].get("requires_settings", []):
                        self.assertIn(needed, chosen, (preset, game, sid))

    def test_with_requirements_follows_chains(self) -> None:
        self.assertEqual(gui.with_requirements("fish", {"time_warp"}), {"time_warp", "ds_store", "ds_fish"})
        self.assertEqual(gui.with_requirements("plant", {"free_upgrades"}),
                         {"free_upgrades", "plant_upgrades", "new_flowers"})


class PriceZeroDefaultOffTests(unittest.TestCase):
    """The owner: "anything that sets prices to 0 is DEFAULT OFF"."""

    def test_price_zero_settings_are_off_by_default_in_both_games(self) -> None:
        self.assertEqual(gui.PRICE_ZERO_SETTINGS, {"free_upgrades", "everything_free"})
        for game in EVERY:
            settings = patch_settings(game)
            for sid in gui.PRICE_ZERO_SETTINGS:
                self.assertIn(sid, settings, game)
                self.assertIs(settings[sid].get("default", False), False, (game, sid))
                self.assertNotIn(sid, gui.preset_selection("default_patches", game), (game, sid))

    def test_free_and_cheat_settings_are_off_by_default_in_both_games(self) -> None:
        # The owner (2026-11-01): "for players 'free stuff' has a cost and cheat stuff is off
        # unless they toggle the patch on." (Time Warp costs $500 and stays on.)
        for game in EVERY:
            settings = patch_settings(game)
            defaults = gui.preset_selection("default_patches", game)
            for sid in ("free_upgrades", "everything_free", "add_money"):
                self.assertIs(settings[sid].get("default", False), False, (game, sid))
                self.assertNotIn(sid, defaults, (game, sid))
            for sid, setting in settings.items():
                if setting.get("cheat"):
                    self.assertIs(setting.get("default", False), False, (game, sid))

    def test_owner_keeps_these_on_by_default(self) -> None:
        # The owner (2026-11-01) kept these default ON after the audit of the default-on settings.
        kept = {
            "fish": ("crimson_comet_20_percent_cure", "universal_supply_slots",
                     "unknown_chemical_three_uses"),
            "plant": ("no_old_age_plant_deaths", "seed_refresh_key"),
        }
        for game, ids in kept.items():
            settings = patch_settings(game)
            for sid in ids:
                self.assertIs(settings[sid].get("default"), True, (game, sid))
                self.assertIn(sid, gui.preset_selection("default_patches", game), (game, sid))

    def test_the_complete_default_list(self) -> None:
        for game in EVERY:
            settings = patch_settings(game)
            self.assertEqual({sid for sid, s in settings.items() if s.get("default")}, DEFAULTS[game], game)
            self.assertEqual(EVERY[game] - DEFAULTS[game], DEFAULT_OFF & EVERY[game], game)
        self.assertNotIn("golden_seahorse_repurchase", EVERY["plant"])
        for game, sid in (("fish", "golden_seahorse_repurchase"), ("fish", "optimize_prices"),
                          ("plant", "optimize_prices")):
            self.assertIs(patch_settings(game)[sid]["default"], False, (game, sid))
            self.assertIn(sid, gui.preset_selection("owners_defaults", game), (game, sid))

    def test_defaults_build_the_modded_upgrades_copy(self) -> None:
        # With new content on by default, the default patch makes "<Game> - Modded Upgrades".
        import fish_patcher

        for game in EVERY:
            manifest = json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))
            title = "Fish Tycoon" if game == "fish" else "Plant Tycoon"
            folder, exe = fish_patcher.output_names(
                manifest, DEFAULTS[game], Path("C:/x") / f"{title} - Modded", f"{title} - Modded.exe")
            self.assertEqual((folder.name, exe), (f"{title} - Modded Upgrades", f"{title} - Modded Upgrades.exe"))

    def test_every_setting_that_makes_something_free_is_listed(self) -> None:
        # A new setting that makes a price $0 must join PRICE_ZERO_SETTINGS (and so be off).
        pattern = re.compile(r"\$0\b|\bfree\b|costs nothing", re.IGNORECASE)
        for game in EVERY:
            for sid, setting in patch_settings(game).items():
                text = f"{setting.get('name', '')} {setting.get('summary', '')}"
                if pattern.search(text):
                    self.assertIn(sid, gui.PRICE_ZERO_SETTINGS, (game, sid, text))


class HelpTextTests(unittest.TestCase):
    def test_every_button_has_a_guide(self) -> None:
        keys = [key for _text, key in gui.PRESET_BUTTONS] + ["patch_selection_settings"]
        self.assertEqual(sorted(gui.PATCH_HELP), sorted(keys))
        self.assertEqual([text for text, _k in gui.PRESET_BUTTONS],
                         ["Select All Patches", "Default Patches", "Owner's Defaults", "Deselect All Patches"])

    def test_owners_defaults_guide_says_what_it_ticks(self) -> None:
        text = " ".join(gui.PATCH_HELP["owners_defaults"][1])
        self.assertIn("every patch in both games except Everything is Free", text)
        self.assertIn("Free upgrades", text)
        self.assertIn("Add Money", text)
        default = " ".join(gui.PATCH_HELP["default_patches"][1])
        self.assertIn("Free upgrades and Everything is Free", default)

    def test_patch_selection_window_texts(self) -> None:
        self.assertEqual(gui.PATCH_SELECTION_TITLE, "Patch Selection Settings")
        self.assertEqual(gui.PATCH_SELECTION_HEADING, "Tick or untick patches in every game at once")
        self.assertEqual(
            gui.PATCH_SELECTION_TEXT,
            "Choose patches below, then press Tick These or Untick These. Each patch is changed in "
            "every game that has it (the games are listed beside its name). A patch that needs "
            "another one turns it on too, just as when you tick it yourself, and of two patches that "
            "cannot be on together only one stays ticked.",
        )

    def test_patches_by_name_groups_both_games(self) -> None:
        groups = dict(gui.patches_by_name())
        self.assertEqual(groups["Fix Vanilla Bugs"], [("fish", "fix_vanilla_bugs"), ("plant", "fix_vanilla_bugs")])
        self.assertEqual(gui.games_label(groups["Everything is Free"]), "both games")
        self.assertEqual(gui.games_label(groups["Crimson Comet 20% curing fix"]), "Fish Tycoon")
        self.assertEqual(gui.games_label(groups["No old-age plant deaths"]), "Plant Tycoon")
        total = sum(len(entries) for entries in groups.values())
        self.assertEqual(total, sum(len(ids) for ids in EVERY.values()))


class PatchSelectionGuiTests(unittest.TestCase):
    def setUp(self) -> None:
        _tk_or_skip(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "patcher_local_settings.json"
        patcher = mock.patch.object(gui, "SETTINGS_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _app(self):
        import tkinter
        for attempt in range(3):
            try:
                app = gui.App()
                break
            except tkinter.TclError:                  # Tk's startup can fail once while many workers start Tk
                if attempt == 2:
                    raise
                time.sleep(0.5)
        app.withdraw()
        def close() -> None:
            try:
                app.destroy()
            except Exception:
                pass                                  # already closed by the test

        self.addCleanup(close)
        return app

    def test_buttons_and_labels_in_the_main_window(self) -> None:
        app = self._app()
        box = app.patch_selection_box
        rows = box.winfo_children()
        first = [str(w.cget("text")) for w in rows[0].winfo_children()]
        self.assertEqual(first, ["Select All Patches", "?", "Default Patches", "?", "Owner's Defaults", "?",
                                 "Deselect All Patches", "?"])
        second = [str(w.cget("text")) for w in rows[1].winfo_children()]
        self.assertEqual(second, ["Patch Selection Settings...", "?"])
        # The per-game Enable All / Disable All / Defaults buttons are gone.
        texts = _texts(app)
        for old in ("Enable All", "Disable All", "Defaults"):
            self.assertNotIn(old, texts)
        window = app._show_patch_help("owners_defaults")
        self.assertEqual(window.title(), "How to use: Owner's Defaults")

    def test_fresh_install_starts_with_default_patches(self) -> None:
        app = self._app()
        self.assertEqual(_ticked(app), DEFAULTS)

    def test_presets_replace_the_ticks_in_both_games(self) -> None:
        app = self._app()
        app.patch_vars["fish"]["everything_free"].set(True)      # ticked by hand
        for preset in ("owners_defaults", "deselect_all", "select_all", "default_patches", "owners_defaults"):
            app._apply_preset(preset)
            self.assertEqual(_ticked(app), EXPECTED[preset], preset)
        self.assertEqual(app.status_var.get(), "Owner's Defaults: set in both games.")
        # Rows can still be changed by hand afterwards.
        app.patch_vars["plant"]["everything_free"].set(True)
        self.assertTrue(app.patch_vars["plant"]["everything_free"].get())

    def test_cross_game_tick_and_untick(self) -> None:
        app = self._app()
        app._apply_preset("deselect_all")
        dialog = app._open_patch_selection_settings()
        self.assertEqual(dialog.title(), "Patch Selection Settings")
        texts = _texts(dialog)
        self.assertIn("Tick or untick patches in every game at once", texts)
        self.assertIn(gui.PATCH_SELECTION_TEXT, texts)
        self.assertIn("Fix Vanilla Bugs   (both games)", texts)
        self.assertIn("Crimson Comet 20% curing fix   (Fish Tycoon)", texts)
        self.assertIn("No old-age plant deaths   (Plant Tycoon)", texts)
        for button in ("Tick These", "Untick These", "Close"):
            self.assertIn(button, texts)
        self.assertIs(app._open_patch_selection_settings(), dialog)        # one window at a time

        choices = dict(app._patch_selection_choices)
        choices["Fix Vanilla Bugs"].set(True)
        choices["Time Warp"].set(True)
        app._patch_selection_apply(True)
        self.assertEqual(_ticked(app), {
            "fish": {"fix_vanilla_bugs", "time_warp", "ds_store", "ds_fish"},
            "plant": {"fix_vanilla_bugs", "time_warp", "plant_upgrades", "new_flowers"},
        })
        self.assertEqual(app.status_var.get(),
                         "Ticked 4 patches across the games: Fix Vanilla Bugs, Time Warp.")
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIn("time_warp", saved["games"]["plant"]["enabled"])

        choices["Time Warp"].set(False)
        app._patch_selection_apply(False)
        self.assertEqual(_ticked(app), {
            "fish": {"time_warp", "ds_store", "ds_fish"},
            "plant": {"time_warp", "plant_upgrades", "new_flowers"},
        })
        self.assertEqual(app.status_var.get(),
                         "Unticked 2 patches across the games: Fix Vanilla Bugs.")
        dialog.destroy()

    def test_choices_persist_across_restarts(self) -> None:
        app = self._app()
        app._apply_preset("owners_defaults")
        app.patch_vars["fish"]["bigger_tanks"].set(False)
        app._save_settings()
        app.destroy()
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(set(saved["games"]["fish"]["enabled"]),
                         EXPECTED["owners_defaults"]["fish"] - {"bigger_tanks"})
        self.assertEqual(set(saved["games"]["plant"]["enabled"]), EXPECTED["owners_defaults"]["plant"])
        again = self._app()
        self.assertEqual(_ticked(again), {
            "fish": EXPECTED["owners_defaults"]["fish"] - {"bigger_tanks"},
            "plant": EXPECTED["owners_defaults"]["plant"],
        })



# Two settings that exclude each other (the owner, 2026-11-01: the two Unicode text settings,
# "Render Unicode with In-Game Fonts" (default on) and "Use Unicode Font" (default off), are
# MUTUALLY EXCLUSIVE in the GUI, the presets and Patch Selection Settings). Shown here on a
# made-up pair beside the real settings, so the mechanism is pinned whatever the manifests hold.
def _with_pair(real):
    def settings(game_id: str) -> dict:
        out = {sid: dict(s) for sid, s in real(game_id).items()}
        out["pair_default"] = {"id": "pair_default", "name": "Pair default", "default": True,
                               "conflicts_settings": ["pair_other"]}
        out["pair_other"] = {"id": "pair_other", "name": "Pair other", "default": False}
        return out
    return settings


class ConflictTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(gui, "patch_settings", _with_pair(gui.patch_settings))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_conflicts_go_both_ways(self) -> None:
        clash = gui.conflicts("fish")
        self.assertEqual(clash["pair_default"], {"pair_other"})
        self.assertEqual(clash["pair_other"], {"pair_default"})

    def test_presets_never_tick_both_and_keep_the_default_one(self) -> None:
        for preset in EXPECTED:
            for game in EVERY:
                chosen = gui.preset_selection(preset, game)
                self.assertFalse({"pair_default", "pair_other"} <= chosen, (preset, game))
        for game in EVERY:
            self.assertIn("pair_default", gui.preset_selection("select_all", game))
            self.assertNotIn("pair_other", gui.preset_selection("select_all", game))
            self.assertIn("pair_default", gui.preset_selection("default_patches", game))
        self.assertEqual(gui.resolve_conflicts("fish", {"pair_default", "pair_other", "ds_fish"}),
                         {"pair_default", "ds_fish"})
        self.assertEqual(gui.resolve_conflicts("fish", {"pair_other"}), {"pair_other"})

    def test_the_patcher_refuses_both(self) -> None:
        import fish_patcher
        manifest = {"settings": list(_with_pair(gui.patch_settings)("fish").values())}
        with self.assertRaisesRegex(fish_patcher.PatchError, "cannot both be on"):
            fish_patcher.check_setting_requirements(manifest, {"pair_default", "pair_other"})
        fish_patcher.check_setting_requirements(manifest, {"pair_other"})
        self.assertEqual(fish_patcher.conflicting_settings(manifest),
                         {"pair_default": {"pair_other"}, "pair_other": {"pair_default"},
                          "unicode_ingame_fonts": {"unicode_system_font"},
                          "unicode_system_font": {"unicode_ingame_fonts"}})

    def test_the_real_unicode_pair(self) -> None:
        """Every conflict in the manifests names a real setting of that game, both ways round."""
        for game in EVERY:
            settings = patch_settings(game)
            for sid, setting in settings.items():
                for other in setting.get("conflicts_settings", []):
                    self.assertIn(other, settings, (game, sid))
                    self.assertNotIn(other, setting.get("requires_settings", []), (game, sid))
            # Use Unicode Font (overrides in-game fonts): off by default, on in Owner's Defaults,
            # excluding Render Unicode with In-Game Fonts both ways; Select All and Default Patches
            # keep only the default one of the two.
            system = settings["unicode_system_font"]
            self.assertEqual(system["name"], "Use Unicode Font (overrides in-game fonts)")
            self.assertIs(system["default"], False)
            self.assertIs(system["separate_output"], True)
            self.assertEqual(system["conflicts_settings"], ["unicode_ingame_fonts"])
            self.assertEqual(settings["unicode_ingame_fonts"]["conflicts_settings"], ["unicode_system_font"])
            self.assertNotIn("unicode_system_font", gui.OWNERS_DEFAULTS_OFF)
            self.assertIn("unicode_system_font", gui.preset_selection("owners_defaults", game))
            self.assertNotIn("unicode_ingame_fonts", gui.preset_selection("owners_defaults", game))
            for preset in ("select_all", "default_patches"):
                self.assertIn("unicode_ingame_fonts", gui.preset_selection(preset, game))
                self.assertNotIn("unicode_system_font", gui.preset_selection(preset, game))


class ConflictGuiTests(unittest.TestCase):
    def setUp(self) -> None:
        _tk_or_skip(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for patcher in (mock.patch.object(gui, "SETTINGS_PATH", Path(self.tmp.name) / "settings.json"),
                        mock.patch.object(gui, "patch_settings", _with_pair(gui.patch_settings))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_ticking_one_unticks_the_other(self) -> None:
        import tkinter
        for attempt in range(3):
            try:
                app = gui.App()
                break
            except tkinter.TclError:
                if attempt == 2:
                    raise
                time.sleep(0.5)
        app.withdraw()
        self.addCleanup(app.destroy)
        fish = app.patch_vars["fish"]
        self.assertTrue(fish["pair_default"].get())
        fish["pair_other"].set(True)
        self.assertEqual((fish["pair_default"].get(), fish["pair_other"].get()), (False, True))
        fish["pair_default"].set(True)
        self.assertEqual((fish["pair_default"].get(), fish["pair_other"].get()), (True, False))
        for preset in ("select_all", "owners_defaults", "default_patches"):
            app._apply_preset(preset)
            self.assertFalse(fish["pair_default"].get() and fish["pair_other"].get(), preset)
        # Patch Selection Settings: ticking both names leaves the default one on
        app._set_named_patches(["Pair other", "Pair default"], True)
        self.assertEqual((fish["pair_default"].get(), fish["pair_other"].get()), (True, False))
        app._set_named_patches(["Pair default"], False)
        app._set_named_patches(["Pair other"], True)
        self.assertEqual((fish["pair_default"].get(), fish["pair_other"].get()), (False, True))


if __name__ == "__main__":
    unittest.main()
