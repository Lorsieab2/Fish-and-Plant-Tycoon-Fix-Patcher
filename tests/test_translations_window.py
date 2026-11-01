"""The Translations window and its helpers (src/translations_window.py, src/translations.py):
the language list and the choice written into the game copies, adding (button and drag and drop
share one handler), the editor's autosave, progress and filters, and Share on GitHub: the owner's
exact Yes/No first (No does nothing), a credit name typed by the player (required, never filled
in, never an email), the export, and GitHub's form opened with the game and language."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import translation_format as tfmt  # noqa: E402
import translations as tr  # noqa: E402
import translations_window as tw  # noqa: E402

OWNER_TEXT = (
    "This button allows you to share your game translation to the patcher's Public Github. IF ACCEPTED, "
    "everyone who uses this patcher will be able to see your translation in the game and your username will "
    "be included in the credits. Please DO NOT put ANY PRIVATE DETAILS YOU DO NOT WANT TO MAKE PUBLIC!\n\n"
    "Email addresses are never saved and are rejected from translation files.\n\n"
    "This feature is meant to be a community collaboration tool for game modding only.\n\n"
    "You will need a Github account to proceed. Continue?"
)

ENTRIES = [tfmt.Entry(tfmt.make_key("strings", "1", "Age: "), "Age: "),
           tfmt.Entry(tfmt.make_key("strings", "4", "Sick"), "Sick"),
           tfmt.Entry(tfmt.make_key("strings", "69", "You have sold %d fish!"), "You have sold %d fish!")]


def write_translation(folder: Path, language: str, translator: str = "", game: str = "fish",
                      translations=("Âge : ", "", "")) -> Path:
    f = tfmt.new_file(game, ENTRIES, language, "fr", translator)
    for row, text in zip(f.rows, translations):
        row.translation = text
    path = folder / tfmt.file_name(tfmt.GAME_TITLES[game], language)
    path.write_bytes(tfmt.to_bytes(f))
    return path


class Texts(unittest.TestCase):
    def test_the_owners_confirmation_exactly(self) -> None:
        self.assertEqual(tr.SHARE_CONFIRMATION, OWNER_TEXT)
        self.assertEqual(tr.SHARE_INVITE, "If you want to share your translation, consider going to the Patcher's "
                                          "GitHub page and adding it!")
        self.assertEqual(tr.SHARE_HOW, "How: press Share on GitHub..., drag the file in, press Submit.")
        self.assertIn(tfmt.EMAIL_MESSAGE, tr.CREDIT_HINT)
        self.assertEqual(tfmt.EMAIL_MESSAGE, "Email addresses are never saved and are rejected from translation files.")

    def test_the_guide_says_an_account_is_needed(self) -> None:
        text = " ".join(tw.HELP[1])
        self.assertIn("GitHub account", text)
        self.assertIn("https://github.com/signup", text)
        self.assertIn(tfmt.EMAIL_MESSAGE, text)

    def test_issue_url(self) -> None:
        url = tr.issue_url("fish", "Français", 42.4)
        self.assertTrue(url.startswith("https://github.com/Lorsieab2/Fish-and-Plant-Tycoon-Fix-Patcher/issues/new?"))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query["template"], ["translation.yml"])
        self.assertEqual(query["game"], ["Fish Tycoon"])
        self.assertEqual(query["language"], ["Français"])
        self.assertEqual(query["coverage"], ["42%"])
        self.assertNotIn("@", urllib.parse.unquote(url))

    def test_credit_name_rules(self) -> None:
        for bad in ("", "   ", "me@example.com", "me [at] example [dot] com", "a＠b", "x" * 61):
            with self.assertRaises(tr.TranslationProblem):
                tr.check_credit_name(bad)
        self.assertEqual(tr.check_credit_name("  Ann   Lee "), "Ann Lee")

    def test_tools_tab_has_the_window(self) -> None:
        import tools_tab
        self.assertIs(tools_tab.HELP["translations"], tw.HELP)
        self.assertTrue(hasattr(tools_tab.ToolsTab, "translations"))


class Choice(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.folder = self.tmp / "translations"
        self.folder.mkdir()
        self.copy = self.tmp / "Fish Tycoon - Modded Upgrades"
        (self.copy / "Fish Tycoon Fix Patcher DLLs").mkdir(parents=True)
        (self.copy / "Fish Tycoon Fix Patcher DLLs" / "Translations.dll").write_bytes(b"MZ")
        self.choices = self.tmp / "choice.json"

    def test_installed_and_labels(self) -> None:
        write_translation(self.folder, "Français", "Ann")
        (self.folder / "fish").mkdir()
        write_translation(self.folder / "fish", "Deutsch", "Bob")
        write_translation(self.folder, "Español", game="plant")
        items = tr.installed("fish", self.folder)
        self.assertEqual([i.label for i in items], ["Deutsch (by Bob)", "Français (by Ann)"])
        self.assertTrue(items[0].shipped)
        self.assertEqual([i.language for i in tr.installed("plant", self.folder)], ["Español"])

    def test_choosing_writes_every_copy_and_english_removes_it(self) -> None:
        path = write_translation(self.folder, "Français")
        written = tr.apply_choice("fish", path, [str(self.tmp / "Fish Tycoon")], self.choices, self.folder)
        self.assertEqual(written, [self.copy.resolve()])
        ini = (self.copy / "Fish Tycoon Fix Patcher DLLs" / "Translation.ini").read_bytes().decode("utf-8-sig")
        self.assertIn("language=Français", ini)
        self.assertIn(f"file={path.resolve()}", ini)
        self.assertEqual((self.copy / "Fish Tycoon Fix Patcher DLLs" / "Translation.txt").read_bytes(), path.read_bytes())
        self.assertEqual(tr.load_choices(self.choices)["fish"], path.name)
        tr.apply_choice("fish", None, [str(self.copy)], self.choices, self.folder)
        self.assertFalse((self.copy / "Fish Tycoon Fix Patcher DLLs" / "Translation.ini").exists())
        self.assertEqual(tr.load_choices(self.choices)["fish"], "")

    def test_a_copy_without_the_dll_is_left_alone(self) -> None:
        plain = self.tmp / "Fish Tycoon - Modded"
        plain.mkdir()
        path = write_translation(self.folder, "Français")
        self.assertFalse(tr.write_choice(plain, "fish", path, "Français"))
        self.assertEqual(list(plain.iterdir()), [])

    def test_install_refuses_email_and_other_games(self) -> None:
        bad = write_translation(self.tmp, "Français", translations=("Âge : écrivez à a@b.com", "", ""))
        with self.assertRaises(tr.TranslationProblem) as caught:
            tr.install_file(bad, "fish", ENTRIES, self.folder)
        self.assertIn(tfmt.EMAIL_MESSAGE, str(caught.exception))
        self.assertNotIn("a@b.com", str(caught.exception))
        plant = write_translation(self.tmp, "Italiano", game="plant")
        with self.assertRaises(tr.TranslationProblem):
            tr.install_file(plant, "fish", ENTRIES, self.folder)
        good = write_translation(self.tmp, "Polski")
        target, report = tr.install_file(good, "fish", ENTRIES, self.folder)
        self.assertEqual(target, self.folder / "Fish Tycoon - Polski.txt")
        self.assertAlmostEqual(report.coverage, 100 / 3)


class Window(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"no Tk: {exc}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.folder = self.tmp / "translations"
        self.folder.mkdir()
        self.copy = self.tmp / "Fish Tycoon - Modded Upgrades"
        (self.copy / "Fish Tycoon Fix Patcher DLLs").mkdir(parents=True)
        (self.copy / "Fish Tycoon Fix Patcher DLLs" / "Translations.dll").write_bytes(b"MZ")
        self.path = write_translation(self.folder, "Français", "Ann")
        self.window = tw.TranslationsWindow(self.root, "fish", {"fish": [str(self.copy)], "plant": []},
                                            folder=self.folder, choices_path=self.tmp / "choice.json")
        self.window.entries_cache["fish"] = ENTRIES

    def tearDown(self) -> None:
        if self.window.window.winfo_exists():
            self.window.close()

    def test_dropdown_and_choice(self) -> None:
        values = list(self.window.language_box.cget("values"))
        self.assertEqual(values, ["English (original)", "Français (by Ann)"])
        self.window.language_var.set(values[1])
        written = self.window.choose()
        self.assertEqual(written, [self.copy.resolve()])
        self.assertIn("next start", self.window.choice_status.get())

    def test_drop_and_button_share_one_handler(self) -> None:
        if self.window.drop.active:
            self.assertEqual(self.window.drop.handler, self.window.add_files)
        other = write_translation(self.tmp, "Deutsch")
        with mock.patch.object(tw.messagebox, "showinfo") as info:
            added = self.window.add_files([other])
        self.assertEqual(added, [self.folder / "Fish Tycoon - Deutsch.txt"])
        self.assertIn("Coverage", info.call_args[0][1])
        self.assertEqual(len(self.window.items), 2)

    def test_share_no_does_nothing(self) -> None:
        self.window.listbox.selection_set(0)
        with mock.patch.object(tw.messagebox, "askyesno", return_value=False) as ask, \
                mock.patch.object(tw.webbrowser, "open") as browser, \
                mock.patch.object(tw.TranslationsWindow, "_show_in_folder") as shown:
            self.assertIsNone(self.window.share())
        self.assertEqual(ask.call_args[0][1], OWNER_TEXT)
        self.assertEqual(ask.call_args[1]["default"], "no")
        browser.assert_not_called()
        shown.assert_not_called()
        self.assertFalse((self.folder / "Shared").exists())

    def test_share_yes_credit_typed_then_export_and_github(self) -> None:
        self.window.listbox.selection_set(0)
        seen = {}

        def answer(dialog):
            seen["initial"] = dialog.var.get()
            dialog.var.set("me@example.com")
            dialog.ok()
            seen["email_refused"] = dialog.error.get()
            dialog.var.set("")
            dialog.ok()
            seen["empty_refused"] = dialog.error.get()
            dialog.var.set("Ann Lee")
            dialog.ok()
        tw.CreditDialog.test_answer = answer
        try:
            with mock.patch.dict(os.environ, {"USERNAME": "WindowsUser", "GIT_AUTHOR_NAME": "Git Name"}), \
                    mock.patch.object(tw.messagebox, "askyesno", return_value=True), \
                    mock.patch.object(tw.messagebox, "showinfo"), \
                    mock.patch.object(tw.webbrowser, "open") as browser, \
                    mock.patch.object(tw.TranslationsWindow, "_show_in_folder") as shown:
                url = self.window.share()
        finally:
            tw.CreditDialog.test_answer = None
        self.assertEqual(seen["initial"], "")                                  # never filled in
        self.assertIn(tfmt.EMAIL_MESSAGE, seen["email_refused"])
        self.assertIn("required", seen["empty_refused"])
        browser.assert_called_once_with(url)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual((query["game"], query["language"]), (["Fish Tycoon"], ["Français"]))
        exported = shown.call_args[0][0]
        parsed = tfmt.parse_bytes(exported.read_bytes(), "fish")
        self.assertEqual(parsed.translator, "Ann Lee")
        self.assertNotIn(b"@example", exported.read_bytes())

    def test_editor_autosave_progress_and_filter(self) -> None:
        editor = self.window.open_editor(self.path)
        self.assertEqual(editor.progress.get(), "1 of 3 lines translated (33%)")
        editor.untranslated_only.set(True)
        editor.fill()
        shown = [r.english for r in editor.visible.values()]
        self.assertEqual(shown, ["Sick", "You have sold %d fish!"])
        iid = next(i for i, r in editor.visible.items() if r.english == "You have sold %d fish!")
        editor.tree.selection_set(iid)
        editor.show_row()
        editor.translation_text.insert("1.0", "Vendu {%1: one=un poisson | other=%d poissons}")
        editor.changed()
        self.assertIn("will show English", editor.message.get())             # %d inside a choice
        editor.translation_text.delete("1.0", "end")
        editor.translation_text.insert("1.0", "Vous avez vendu %d {%1: one=poisson | other=poissons} !")
        editor.changed()
        self.assertEqual(editor.message.get(), "OK")
        editor.save()
        parsed = tfmt.parse_bytes(self.path.read_bytes(), "fish")
        self.assertEqual(len(parsed.translations()), 2)
        self.assertEqual(editor.progress.get(), "2 of 3 lines translated (67%)")
        editor.close()

    def test_editor_adds_new_lines_after_an_update(self) -> None:
        newer = ENTRIES + [tfmt.Entry(tfmt.make_key("strings", "2", "Status: "), "Status: ")]
        self.window.entries_cache["fish"] = newer
        editor = self.window.open_editor(self.path)
        self.assertIn("1 new line", editor.update_note)
        parsed = tfmt.parse_bytes(self.path.read_bytes(), "fish")
        self.assertEqual([r.english for r in parsed.rows][-1], "Status: ")
        self.assertEqual(parsed.translations()[ENTRIES[0].key], "Âge : ")
        editor.close()


class Setting(unittest.TestCase):
    def test_loaded_last_by_the_startup_loader(self) -> None:
        import ds_fish_loader as dl
        self.assertIs(dl.fish_profile({"translations"}), dl.FISH_TRANSLATIONS)
        self.assertIs(dl.plant_profile({"translations"}), dl.PLANT_TRANSLATIONS)
        for enabled in ({"ds_fish"}, {"extra_tanks", "ds_fish", "tank_greenhouse_counts", "optimize_prices"},
                        {"maximizable_window"}):
            names = dl.fish_profile(enabled | {"translations"}).dll_names
            self.assertEqual(names[-1], "Translations.dll")
            self.assertEqual(names[:-1], dl.fish_profile(enabled).dll_names)
        for enabled in ({"new_flowers", "plant_upgrades"}, {"extra_greenhouses", "new_flowers", "extra_chemical_slots"}):
            names = dl.plant_profile(enabled | {"translations"}).dll_names
            self.assertEqual(names[-1], "Translations.dll")
            self.assertEqual(names[:-1], dl.plant_profile(enabled).dll_names)

    def test_manifest_setting(self) -> None:
        import json
        import hashlib
        dll = (ROOT / "assets" / "translations" / "Translations.dll").read_bytes()
        for game, folder in (("fish", "Fish Tycoon Fix Patcher DLLs"), ("plant", "Plant Tycoon Fix Patcher DLLs")):
            manifest = json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))
            setting = next(s for s in manifest["settings"] if s["id"] == "translations")
            self.assertTrue(setting["default"])
            self.assertTrue(setting["separate_output"])
            companion = setting["companion"]
            self.assertTrue(companion["startup_loader"])
            self.assertEqual(companion["loader_tail"], "Translations.dll")
            self.assertEqual(companion["files"], [{"path": "Translations.dll", "destination": f"{folder}/Translations.dll",
                                                   "size": len(dll), "sha256": hashlib.sha256(dll).hexdigest().upper()}])
            pins = manifest["patched_sha256_by_settings"]
            self.assertIn("translations", pins)
            without = [k for k in pins if "translations" not in k.split(",")]
            for key in without[:: max(1, len(without) // 50)]:
                self.assertIn(",".join(sorted(set(key.split(",")) | {"translations"})), pins)

    def test_a_new_patch_gets_the_chosen_language(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        copy = tmp / "copy"
        (copy / "Plant Tycoon Fix Patcher DLLs").mkdir(parents=True)
        (copy / "Plant Tycoon Fix Patcher DLLs" / "Translations.dll").write_bytes(b"MZ")
        folder = tmp / "translations"
        folder.mkdir()
        path = write_translation(folder, "Italiano", game="plant")
        with mock.patch.object(tr, "TRANSLATIONS_DIR", folder), mock.patch.object(tr, "CHOICE_PATH", tmp / "c.json"):
            tr.save_choices({"plant": path.name})
            self.assertTrue(tr.write_choice_into(copy, "plant"))
        ini = (copy / "Plant Tycoon Fix Patcher DLLs" / "Translation.ini").read_text(encoding="utf-8-sig")
        self.assertIn("language=Italiano", ini)


if __name__ == "__main__":
    unittest.main()
