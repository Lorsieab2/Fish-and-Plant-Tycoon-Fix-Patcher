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

import text_wrap as twrap  # noqa: E402
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
        self.window.listbox.selection_set(1)                                # row 0 is English (original)
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
        self.window.listbox.selection_set(1)                                # row 0 is English (original)
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

    def _wrap_open(self, translations):
        path = write_translation(self.folder, "Wrap", game="fish", translations=translations)
        editor = self.window.open_editor(path)
        editor.game_font = lambda: object()       # a fake font: 10 pixels a letter, 20 a CJK character
        editor.measure_line = lambda text: sum(20 if ord(c) >= 0x3000 else 10 for c in tfmt.evaluate(text))
        return editor

    def _wrap_select(self, editor, english: str) -> None:
        iid = next(i for i, r in editor.visible.items() if r.english == english)
        editor.tree.selection_set(iid)
        editor.show_row()

    def test_wrap_selected_and_undo(self) -> None:
        editor = self._wrap_open(("Âge:", "", "Vous avez vendu beaucoup de poissons"))
        self._wrap_select(editor, "You have sold %d fish!")
        editor.wrap_selected()
        text = editor.translation_text.get("1.0", "end-1c")
        room = len("You have sold %d fish!") * 10
        self.assertGreater(text.count("\n"), 0)
        self.assertTrue(all(editor.measure_line(line) <= room for line in text.split("\n")))
        self.assertEqual(text.split(), "Vous avez vendu beaucoup de poissons".split())
        self.assertEqual(editor.current.translation, text)
        self.assertEqual(editor.undo_wrap(), 1)
        self.assertEqual(editor.current.translation, "Vous avez vendu beaucoup de poissons")
        self.assertEqual(editor.translation_text.get("1.0", "end-1c"), "Vous avez vendu beaucoup de poissons")
        editor.close()

    def test_wrap_selected_is_a_no_op_when_it_fits(self) -> None:
        editor = self._wrap_open(("Âge:", "", "Vendu %d !"))
        self._wrap_select(editor, "You have sold %d fish!")
        editor.wrap_selected()
        self.assertEqual(editor.current.translation, "Vendu %d !")
        self.assertIn("Already fits", editor.preview_note.get())
        editor.close()

    def test_wrap_all_counts_asks_first_and_keeps_placeholders(self) -> None:
        editor = self._wrap_open(("Âge:", "Malade", "Vous avez vendu %d poissons aujourd hui"))
        self.assertEqual([r.english for r in editor.wide_rows()], ["Sick", "You have sold %d fish!"])
        with mock.patch.object(tw.messagebox, "askyesno", return_value=False) as ask:
            self.assertEqual(editor.wrap_all(), 0)
        self.assertIn("2 line(s)", ask.call_args[0][1])
        self.assertEqual([r.translation for r in editor.file.rows if r.english == "Sick"], ["Malade"])
        with mock.patch.object(tw.messagebox, "askyesno", return_value=True):
            self.assertEqual(editor.wrap_all(), 2)
        rows = {r.english: r.translation for r in editor.file.rows}
        self.assertIn("%d", rows["You have sold %d fish!"])
        self.assertEqual(rows["Sick"], "Mala\nde")
        self.assertEqual(editor.wide_rows(), [])
        self.assertEqual(editor.undo_wrap(), 2)
        self.assertEqual({r.english: r.translation for r in editor.file.rows}["Sick"], "Malade")
        editor.close()

    def test_warning_and_wrap_agree(self) -> None:
        editor = self._wrap_open(("Âge:", "Malade", "Vous avez vendu %d poissons"))
        for row in editor.file.rows:
            if row.translation:
                result = editor.wrap_row(row)
                self.assertFalse(twrap.needs_wrap(result.text, row.english, editor.measure_line))
        editor.close()


def _buttons(widget: tk.Misc) -> dict[str, tk.Misc]:
    found = {}
    for child in widget.winfo_children():
        try:
            found[str(child.cget("text"))] = child
        except tk.TclError:
            pass
        found.update(_buttons(child))
    return found


class Recycling(unittest.TestCase):
    """translations.recycle: SHFileOperationW with the Recycle Bin flags, never a plain delete."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.a = self.tmp / "a.txt"
        self.b = self.tmp / "b b.txt"
        self.a.write_text("a", encoding="utf-8")
        self.b.write_text("b", encoding="utf-8")

    def test_one_call_with_every_file_and_the_recycle_flags(self) -> None:
        calls = []
        moved = tr.recycle([self.a, self.b], operation=lambda paths, flags: (calls.append((paths, flags)), (0, False))[1])
        self.assertEqual(moved, [self.a.resolve(), self.b.resolve()])
        self.assertEqual(calls, [([str(self.a.resolve()), str(self.b.resolve())], tr.RECYCLE_FLAGS)])
        for flag in (tr.FOF_ALLOWUNDO, tr.FOF_NOCONFIRMATION, tr.FOF_SILENT):
            self.assertTrue(tr.RECYCLE_FLAGS & flag)
        self.assertEqual(tr.FO_DELETE, 3)

    def test_a_failing_call_raises_and_nothing_else_is_tried(self) -> None:
        for result in ((0x78, False), (0, True)):
            with mock.patch.object(Path, "unlink") as unlink, mock.patch("os.remove") as remove, \
                    mock.patch("shutil.rmtree") as rmtree, self.assertRaises(OSError):
                tr.recycle([self.a], operation=lambda _p, _f, r=result: r)
            for plain_delete in (unlink, remove, rmtree):
                plain_delete.assert_not_called()
        self.assertTrue(self.a.exists())
        with self.assertRaises(OSError):
            tr.recycle([self.tmp / "missing.txt"], operation=lambda _p, _f: self.fail("called"))


class ManyTranslations(unittest.TestCase):
    """The list selects several (Ctrl, Shift, Ctrl+A, Select All); Delete... and Export... act on them."""

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
        (self.folder / "fish").mkdir(parents=True)
        self.copy = self.tmp / "Fish Tycoon - Modded Upgrades"
        self.dlls = self.copy / "Fish Tycoon Fix Patcher DLLs"
        self.dlls.mkdir(parents=True)
        (self.dlls / "Translations.dll").write_bytes(b"MZ")
        self.choices = self.tmp / "choice.json"
        self.shipped = write_translation(self.folder / "fish", "Deutsch", "Bob")      # row 1 (came with the patcher)
        self.spanish = write_translation(self.folder, "Español")                       # row 2
        self.french = write_translation(self.folder, "Français", "Ann")                # row 3
        self.window = tw.TranslationsWindow(self.root, "fish", {"fish": [str(self.copy)], "plant": []},
                                            folder=self.folder, choices_path=self.choices)
        self.window.entries_cache["fish"] = ENTRIES
        self.lb = self.window.listbox

    def tearDown(self) -> None:
        if self.window.window.winfo_exists():
            self.window.close()

    def click(self, row: int, state: int = 0) -> None:
        self.window.window.update()
        x, y, _w, h = self.lb.bbox(row)
        self.lb.event_generate("<Button-1>", x=x + 2, y=y + h // 2, state=state)
        self.lb.event_generate("<ButtonRelease-1>", x=x + 2, y=y + h // 2, state=state)
        self.window.window.update()

    def test_the_list(self) -> None:
        self.assertEqual(self.lb.cget("selectmode"), "extended")
        self.assertEqual(self.lb.get(0), tw.ENGLISH_ROW)
        self.assertEqual([i.path for i in self.window.items], [self.shipped, self.spanish, self.french])
        self.assertEqual(self.lb.size(), 4)
        values = list(self.window.language_box.cget("values"))            # the language to use stays a dropdown
        self.assertEqual(values[0], "English (original)")
        self.assertEqual(len(values), 4)

    def test_click_ctrl_click_and_shift_click(self) -> None:
        self.click(1)
        self.assertEqual(self.lb.curselection(), (1,))
        self.click(3, state=0x0004)                                         # Ctrl+click adds
        self.assertEqual(self.lb.curselection(), (1, 3))
        self.click(1, state=0x0004)                                         # Ctrl+click again removes
        self.assertEqual(self.lb.curselection(), (3,))
        self.click(2)                                                       # a plain click selects one
        self.assertEqual(self.lb.curselection(), (2,))
        self.click(3)
        self.assertEqual(self.lb.curselection(), (3,))
        self.click(1, state=0x0001)                                         # Shift+click selects the range
        self.assertEqual(self.lb.curselection(), (1, 2, 3))
        self.assertEqual(self.window.selected_items(), [i for i in self.window.items])
        self.assertIsNone(self.window.selected())                           # Edit, Check, Share need one
        with mock.patch.object(tw.messagebox, "showinfo") as info, \
                mock.patch.object(tw.TranslationsWindow, "open_editor") as editor:
            self.window.edit()
        editor.assert_not_called()
        self.assertEqual(info.call_args[0][1], tw.CHOOSE_ONE)

    def test_ctrl_a_and_select_all(self) -> None:
        self.click(2)
        self.lb.focus_force()
        self.window.window.update()
        self.lb.event_generate("<Control-a>")
        self.assertEqual(self.lb.curselection(), (0, 1, 2, 3))
        self.lb.selection_clear(0, "end")
        _buttons(self.window.window)["Select All"].invoke()
        self.assertEqual(self.lb.curselection(), (0, 1, 2, 3))
        self.assertIn("Delete...", _buttons(self.window.window))

    def test_delete_prompt_no_is_the_default_and_does_nothing(self) -> None:
        self.window.select_all()
        with mock.patch.object(tw.messagebox, "askyesno", return_value=False) as ask, \
                mock.patch.object(tr, "recycle") as recycle:
            self.assertEqual(self.window.delete(), [])
        recycle.assert_not_called()
        self.assertEqual(ask.call_args[1]["default"], "no")
        text = ask.call_args[0][1]
        self.assertIn("Move 3 translation file(s) for Fish Tycoon to the Recycle Bin?", text)
        for path in (self.shipped, self.spanish, self.french):
            self.assertIn(path.name, text)
            self.assertTrue(path.exists())
        self.assertIn("English (original) is built into the game and cannot be deleted: it is skipped.", text)
        self.assertIn("come back with the next patcher update", text)
        self.assertEqual(self.lb.size(), 4)

    def test_yes_recycles_exactly_the_selected_files_without_english(self) -> None:
        for row in (0, 1, 3):
            self.lb.selection_set(row)
        with mock.patch.object(tw.messagebox, "askyesno", return_value=True), \
                mock.patch.object(tr, "recycle", side_effect=lambda paths: [Path(p).resolve() for p in paths]) as recycle:
            removed = self.window.delete()
        recycle.assert_called_once_with([self.shipped, self.french])
        self.assertEqual(removed, [self.shipped.resolve(), self.french.resolve()])
        self.assertTrue(self.spanish.exists())

    def test_only_english_selected_deletes_nothing(self) -> None:
        self.lb.selection_set(0)
        with mock.patch.object(tw.messagebox, "showinfo") as info, \
                mock.patch.object(tw.messagebox, "askyesno") as ask, mock.patch.object(tr, "recycle") as recycle:
            self.assertEqual(self.window.delete(), [])
        ask.assert_not_called()
        recycle.assert_not_called()
        self.assertIn("cannot be deleted", info.call_args[0][1])

    def recycle_for_real_here(self, paths):
        """Stands in for the Recycle Bin: the files leave the folder."""
        for path in paths:
            Path(path).unlink()
        return [Path(p).resolve() for p in paths]

    def test_deleting_the_active_one_goes_back_to_english(self) -> None:
        self.window.language_var.set("Français (by Ann)")
        self.assertEqual(self.window.choose(), [self.copy.resolve()])
        self.assertTrue((self.dlls / "Translation.ini").exists())
        self.assertTrue((self.dlls / "Translation.txt").exists())
        editor = self.window.open_editor(self.french)
        editor.dirty = True                                                 # unsaved work must not bring it back
        self.lb.selection_set(3)
        with mock.patch.object(tw.messagebox, "askyesno", return_value=True) as ask, \
                mock.patch.object(tr, "recycle", side_effect=self.recycle_for_real_here):
            self.window.delete()
        self.assertIn("Fish Tycoon uses Français (by Ann) now: it goes back to English (original).", ask.call_args[0][1])
        self.assertFalse(self.french.exists())
        self.assertFalse(editor.window.winfo_exists())
        self.assertNotIn(editor, self.window.editors)
        self.assertFalse((self.dlls / "Translation.ini").exists())          # as choosing English does
        self.assertFalse((self.dlls / "Translation.txt").exists())
        self.assertEqual(tr.load_choices(self.choices)["fish"], "")
        self.assertEqual(self.window.language_var.get(), "English (original)")
        self.assertEqual(self.lb.size(), 3)

    def test_deleting_another_one_keeps_the_choice(self) -> None:
        self.window.language_var.set("Français (by Ann)")
        self.window.choose()
        self.lb.selection_set(2)
        with mock.patch.object(tw.messagebox, "askyesno", return_value=True) as ask, \
                mock.patch.object(tr, "recycle", side_effect=self.recycle_for_real_here):
            self.window.delete()
        self.assertNotIn("goes back", ask.call_args[0][1])
        self.assertEqual(tr.load_choices(self.choices)["fish"], self.french.name)
        self.assertTrue((self.dlls / "Translation.ini").exists())
        self.assertEqual(self.window.language_var.get(), "Français (by Ann)")

    def test_a_failing_recycle_bin_deletes_nothing(self) -> None:
        self.window.language_var.set("Français (by Ann)")
        self.window.choose()
        self.window.select_all()
        with mock.patch.object(tw.messagebox, "askyesno", return_value=True), \
                mock.patch.object(tw.messagebox, "showerror") as error, \
                mock.patch.object(tr, "_shell_file_operation", return_value=(0x78, False)) as operation:
            self.assertEqual(self.window.delete(), [])
        operation.assert_called_once()
        self.assertIn("Nothing was deleted", error.call_args[0][1])
        for path in (self.shipped, self.spanish, self.french):
            self.assertTrue(path.exists())
        self.assertEqual(tr.load_choices(self.choices)["fish"], self.french.name)
        self.assertTrue((self.dlls / "Translation.ini").exists())
        self.assertEqual(self.lb.size(), 4)

    def test_export_several_one_file_each(self) -> None:
        out = self.tmp / "out"
        out.mkdir()
        (out / self.spanish.name).write_bytes(b"old")
        for row in (1, 2, 3):
            self.lb.selection_set(row)
        with mock.patch.object(tw.filedialog, "askdirectory", return_value=str(out)), \
                mock.patch.object(tw.filedialog, "asksaveasfilename") as save_as, \
                mock.patch.object(tw.messagebox, "askyesno", return_value=False) as ask, \
                mock.patch.object(tw.messagebox, "showinfo") as info:
            exported = self.window.export()
        save_as.assert_not_called()
        self.assertEqual(ask.call_args[1]["default"], "no")                # replacing asks first; No skips it
        self.assertEqual(exported, [out / self.shipped.name, out / self.french.name])
        self.assertEqual((out / self.spanish.name).read_bytes(), b"old")
        self.assertEqual((out / self.french.name).read_bytes(), self.french.read_bytes())
        self.assertIn("Exported 2 file(s)", info.call_args[0][1])
        with mock.patch.object(tw.filedialog, "askdirectory", return_value=str(out)), \
                mock.patch.object(tw.messagebox, "askyesno", return_value=True), \
                mock.patch.object(tw.messagebox, "showinfo"):
            self.assertEqual(len(self.window.export()), 3)
        self.assertEqual((out / self.spanish.name).read_bytes(), self.spanish.read_bytes())

    def test_export_one_keeps_the_save_as_dialog(self) -> None:
        self.lb.selection_set(2)
        target = self.tmp / "mine.txt"
        with mock.patch.object(tw.filedialog, "asksaveasfilename", return_value=str(target)), \
                mock.patch.object(tw.filedialog, "askdirectory") as folder:
            self.assertEqual(self.window.export(), [target])
        folder.assert_not_called()
        self.assertEqual(target.read_bytes(), self.spanish.read_bytes())

    def test_the_guide_explains_it(self) -> None:
        text = " ".join(tw.HELP[1])
        for words in ("Ctrl+click", "Shift+click", "Ctrl+A", "Select All", "Delete...", "Recycle Bin",
                      "next patcher update", "goes back to English (original)"):
            self.assertIn(words, text)


class Setting(unittest.TestCase):
    def test_loaded_last_as_a_loader_tail(self) -> None:
        import json
        import fish_patcher
        for game, cases in (("fish", ({"ds_fish"}, {"extra_tanks", "ds_fish", "tank_greenhouse_counts",
                                                     "optimize_prices"}, set())),
                            ("plant", ({"new_flowers", "plant_upgrades"},
                                       {"extra_greenhouses", "new_flowers", "extra_chemical_slots"}, set()))):
            manifest = json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))
            for enabled in cases:
                names = fish_patcher.loader_profile(manifest, enabled | {"translations"}, game).dll_names
                self.assertEqual(names[-1], "Translations.dll")
                both = fish_patcher.loader_profile(manifest, enabled | {"translations", "unicode_ingame_fonts"}
                                                   if any(s["id"] == "unicode_ingame_fonts" for s in manifest["settings"])
                                                   else enabled | {"translations"}, game).dll_names
                self.assertEqual(both[-1], "Translations.dll")              # after Unicode Text.dll
                self.assertEqual(fish_patcher.pin_settings(manifest, enabled | {"translations"}), enabled)

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
            self.assertNotIn("startup_loader", companion)
            self.assertEqual(companion["loader_tail"], "Translations.dll")
            self.assertEqual(companion["files"], [{"path": "Translations.dll", "destination": f"{folder}/Translations.dll",
                                                   "size": len(dll), "sha256": hashlib.sha256(dll).hexdigest().upper()}])
            self.assertFalse(any("translations" in k.split(",") for k in manifest["patched_sha256_by_settings"]))
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
