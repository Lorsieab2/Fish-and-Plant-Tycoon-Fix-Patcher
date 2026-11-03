"""The three translation-safety rules (the VV chat's Codex review, checked here too):

1. A check speaks only for the commit it checked: the workflows cancel stale runs, the scripts ask
   GitHub for the pull request's head again before acting, and the Share on GitHub... flow commits
   exactly the bytes VirusTotal scanned (SHA-256) and re-reads the issue just before pushing.
2. Names: a player's file never takes the name of one that came with the patcher or from GitHub,
   Edit... copies are per game, Download from GitHub... never takes another translator's file's
   place, and a remembered choice is its source plus its name.
3. Adding (or downloading) a translation replaces an installed one only when the language, @code AND
   @translator match; otherwise both are kept. The replaced one goes to the Recycle Bin (mocked
   here): nothing is ever deleted for good.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import accept_translation as at  # noqa: E402
import check_translation_pr as cpr  # noqa: E402
import translation_format as tfmt  # noqa: E402
import translation_public as tp  # noqa: E402
import translations as tr  # noqa: E402
import translations_github as tgh  # noqa: E402
import virustotal_scan as vt  # noqa: E402
from test_translation_public import FakeGitHub, on, translation  # noqa: E402

WORKFLOWS = ROOT / ".github" / "workflows"
REPO = "Lorsieab2/Fish-and-Plant-Tycoon-Fix-Patcher"
ENTRIES = [tfmt.Entry(tfmt.make_key("strings", "1", "Age: "), "Age: "),
           tfmt.Entry(tfmt.make_key("strings", "69", "You have sold %d fish!"), "You have sold %d fish!")]


def load(name: str) -> tuple[dict, str]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return yaml.safe_load(text), text


def no_plain_delete():
    """Patches every plain delete; the caller asserts none was called."""
    return (mock.patch.object(Path, "unlink"), mock.patch("os.remove"), mock.patch("os.unlink"),
            mock.patch("shutil.rmtree"))


class FakeRecycleBin:
    """tr.recycle stand-in: moves the files into a folder of its own (as the Recycle Bin would)."""

    def __init__(self) -> None:
        self.bin = Path(tempfile.mkdtemp())
        self.calls: list[list[Path]] = []

    def __call__(self, paths):
        paths = [Path(p).resolve() for p in paths]
        self.calls.append(paths)
        for n, path in enumerate(paths):
            os.rename(path, self.bin / f"{n}-{path.name}")
        return paths


# --------------------------------------------------------------------------- 1. the workflows


class StaleRunWorkflows(unittest.TestCase):
    def test_pr_check_cancels_stale_runs_and_other_labels_never_cancel_it(self) -> None:
        flow, text = load("translation-pr.yml")
        self.assertIs(flow["concurrency"]["cancel-in-progress"], True)
        group = flow["concurrency"]["group"]
        self.assertIn("github.event.pull_request.number", group)
        self.assertIn("github.event.label.name == 'accept-translation'", group)
        self.assertIn("github.run_id", group)              # an unrelated label: a group of its own
        self.assertEqual(on(flow)["pull_request_target"]["types"], ["opened", "synchronize", "reopened", "labeled"])

    def test_accept_flow_cancels_stale_runs(self) -> None:
        flow, _text = load("accept-translation.yml")
        self.assertIs(flow["concurrency"]["cancel-in-progress"], True)
        group = flow["concurrency"]["group"]
        self.assertIn("github.event.issue.number", group)
        self.assertIn("github.event.label.name == 'accept-translation'", group)
        self.assertIn("github.run_id", group)

    def test_accept_commits_exactly_the_scanned_bytes_and_rechecks_before_pushing(self) -> None:
        flow, text = load("accept-translation.yml")
        steps = flow["jobs"]["accept"]["steps"]
        names = [s.get("id") or s.get("name") for s in steps]
        final = next(s for s in steps if s.get("id") == "final")
        self.assertIn("scripts/virustotal_scan.py --file", final["run"])
        self.assertEqual(final["env"]["VT_API_KEY"], "${{ secrets.VT_API_KEY }}")
        opening = steps[-1]
        self.assertLess(names.index("final"), len(steps) - 1)
        self.assertEqual(opening["env"]["FINAL_SHA256"], "${{ steps.final.outputs.sha256 }}")
        run = opening["run"]
        order = [run.index(part) for part in ('git add -- "$target"', 'git show ":$target" | sha256sum',
                                              '"$staged" != "$FINAL_SHA256"', "git commit",
                                              'gh api "repos/$GITHUB_REPOSITORY/issues/$ISSUE_NUMBER"',
                                              "accept_translation.py --recheck", "git push")]
        self.assertEqual(order, sorted(order))
        self.assertIn("set -euo pipefail", run)            # a failed recheck stops before the push
        self.assertEqual(flow["jobs"]["accept"]["env"]["EXPECTED_SHA256"], "${{ needs.scan.outputs.sha256 }}")
        for step in steps:
            self.assertNotIn("${{", step.get("run", ""))

    def test_any_automatic_merge_is_pinned_to_the_checked_commit(self) -> None:
        # The owner merges translation pull requests by hand; should a workflow ever merge, it must
        # name the commit that was checked.
        for path in WORKFLOWS.glob("*.yml"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if "gh pr merge" in line and not line.lstrip().startswith("#"):
                    self.assertIn("--match-head-commit", line, path.name)


# --------------------------------------------------------------------------- 1. the scripts


class PullRequestHead(unittest.TestCase):
    SHA = "a" * 40
    NEWER = "b" * 40

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp())
        self.event_path = self.work / "event.json"
        self.event = {"pull_request": {"number": 12, "head": {"sha": self.SHA}, "author_association": "NONE"}}
        self.event_path.write_text(json.dumps(self.event), encoding="utf-8")
        self.files = {"translations/fish/fr.tsv": translation()}
        self.listing = [{"filename": "translations/fish/fr.tsv", "status": "added"}]

    def fake_http(self, heads):
        calls: list[tuple[str, str]] = []
        heads = list(heads)

        def http(method, url, token="", body=None, accept="", limit=0):
            calls.append((method, url))
            if url.endswith("/pulls/12"):
                return json.dumps({"head": {"sha": heads.pop(0)}}).encode()
            if "/pulls/12/files" in url:
                return json.dumps(self.listing).encode()
            if "/contents/" in url:
                assert f"ref={self.SHA}" in url, url              # always the checked commit
                return self.files[url.split("/contents/", 1)[1].split("?", 1)[0]]
            if url.endswith("/issues/12/comments"):
                return b"{}"
            raise AssertionError(url)
        return http, calls

    def env(self):
        return mock.patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(self.event_path), "GITHUB_REPOSITORY": REPO,
                                            "GITHUB_TOKEN": "t", "GITHUB_STEP_SUMMARY": "", "GITHUB_OUTPUT": ""})

    def test_collect_refuses_when_the_head_moved_while_listing(self) -> None:
        http, _calls = self.fake_http([self.NEWER])
        with mock.patch.object(cpr, "http", http), self.assertRaises(cpr.HeadMoved):
            cpr.collect(REPO, self.event, "t")

    def test_the_comment_names_the_checked_commit(self) -> None:
        http, _calls = self.fake_http([self.SHA])
        with mock.patch.object(cpr, "http", http):
            ok, comment = cpr.validate(cpr.collect(REPO, self.event, "t"), self.SHA)
        self.assertTrue(ok)
        self.assertIn(self.SHA[:12], comment)

    def test_validator_never_comments_after_a_newer_push(self) -> None:
        http, calls = self.fake_http([self.SHA, self.NEWER])       # moved after the check, before the comment
        with self.env(), mock.patch.object(cpr, "http", http), mock.patch.object(sys, "argv", ["x", str(self.work)]):
            self.assertEqual(cpr.main(), 1)
        self.assertFalse([c for c in calls if c[0] == "POST"])

    def test_validator_comments_when_the_head_stayed(self) -> None:
        http, calls = self.fake_http([self.SHA, self.SHA])
        with self.env(), mock.patch.object(cpr, "http", http), mock.patch.object(sys, "argv", ["x", str(self.work)]):
            self.assertEqual(cpr.main(), 0)
        self.assertEqual([c for c in calls if c[0] == "POST"], [("POST", f"{cpr.API}/repos/{REPO}/issues/12/comments")])

    def test_scan_fails_quietly_when_the_head_moved_during_the_scan(self) -> None:
        http, calls = self.fake_http([self.SHA, self.NEWER])
        clean = [vt.Verdict("translations/fish/fr.tsv", "clean", "0" * 64, detail="0 of 70")]
        with self.env(), mock.patch.object(cpr, "http", http), mock.patch.object(vt, "scan_all", return_value=clean):
            self.assertEqual(vt.main(["--pr", str(self.work)]), 1)
        self.assertFalse([c for c in calls if c[0] == "POST"])      # never speaks for the newer commit
        self.assertIn("changed during the check", (self.work / "comment.md").read_text(encoding="utf-8"))

    def test_scan_passes_when_the_head_stayed(self) -> None:
        http, _calls = self.fake_http([self.SHA, self.SHA])
        clean = [vt.Verdict("translations/fish/fr.tsv", "clean", "0" * 64, detail="0 of 70")]
        with self.env(), mock.patch.object(cpr, "http", http), mock.patch.object(vt, "scan_all", return_value=clean):
            self.assertEqual(vt.main(["--pr", str(self.work)]), 0)


class WrittenFileScan(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.work = Path(tempfile.mkdtemp())
        (self.root / "translations" / "fish").mkdir(parents=True)
        self.data = translation(translator="Zoë")
        (self.root / "translations" / "fish" / "fr.tsv").write_bytes(self.data)

    def test_the_written_file_is_read_from_target_txt(self) -> None:
        target = self.work / "target.txt"
        target.write_text("translations/fish/fr.tsv", encoding="utf-8")
        self.assertEqual(vt._written_file(target, self.root), [("translations/fish/fr.tsv", self.data)])
        for bad in ("../outside.tsv", "translations/fish/../../x.tsv", "src/x.tsv", "translations/fish/missing.tsv"):
            target.write_text(bad, encoding="utf-8")
            with self.assertRaises((ValueError, tp.NotATranslation), msg=bad):
                vt._written_file(target, self.root)

    def test_the_scanned_sha256_is_the_written_files(self) -> None:
        output = self.work / "out.txt"
        files = [("translations/fish/fr.tsv", self.data)]
        clean = [vt.Verdict("translations/fish/fr.tsv", "clean", tp.sha256(self.data), detail="0 of 70")]
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": "", "VT_API_KEY": "k",
                                          "ISSUE_NUMBER": "3"}), \
                mock.patch.object(vt, "_written_file", return_value=files), \
                mock.patch.object(vt, "scan_all", return_value=clean) as scan_all:
            self.assertEqual(vt.main(["--file", str(self.work / "target.txt"), str(self.work)]), 0)
        scan_all.assert_called_once_with(files, "k")
        self.assertEqual(output.read_text(encoding="utf-8"), f"sha256={tp.sha256(self.data)}\n")

    def test_a_flagged_written_file_gives_no_sha256(self) -> None:
        output = self.work / "out.txt"
        flagged = [vt.Verdict("translations/fish/fr.tsv", "flagged", "1" * 64, ["X"], "1 of 70")]
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": "", "VT_API_KEY": "k",
                                          "ISSUE_NUMBER": ""}), \
                mock.patch.object(vt, "_written_file", return_value=[("translations/fish/fr.tsv", b"x")]), \
                mock.patch.object(vt, "scan_all", return_value=flagged):
            self.assertEqual(vt.main(["--file", str(self.work / "target.txt"), str(self.work)]), 1)
        self.assertFalse(output.exists())


class IssueRecheck(unittest.TestCase):
    BODY = ("### Game\n\nFish Tycoon\n\n### Credit name\n\nAnn\n\n### Translation file\n\n"
            "[f.txt](https://github.com/user-attachments/files/1/f.txt)\n\n### Licence\n\n- [X] mine\n")

    def current(self, body=BODY, labels=("translation", "accept-translation"), state="open") -> dict:
        return {"body": body, "state": state, "labels": [{"name": n} for n in labels]}

    def test_unchanged_issue_passes(self) -> None:
        self.assertEqual(at.still_current({"issue": {"body": self.BODY}}, self.current()), "")

    def test_a_changed_attachment_label_or_state_stops_the_run(self) -> None:
        event = {"issue": {"body": self.BODY}}
        other = self.BODY.replace("files/1/f.txt", "files/2/f.txt")
        self.assertIn("translation file", at.still_current(event, self.current(body=other)))
        self.assertIn("credit name", at.still_current(event, self.current(body=self.BODY.replace("Ann", "Bob"))))
        self.assertIn("label", at.still_current(event, self.current(labels=("translation",))))
        self.assertIn("closed", at.still_current(event, self.current(state="closed")))

    def test_recheck_exit_codes(self) -> None:
        work = Path(tempfile.mkdtemp())
        (work / "event.json").write_text(json.dumps({"issue": {"body": self.BODY}}), encoding="utf-8")
        (work / "same.json").write_text(json.dumps(self.current()), encoding="utf-8")
        (work / "edited.json").write_text(json.dumps(self.current(body=self.BODY.replace("Ann", "Eve"))),
                                          encoding="utf-8")
        self.assertEqual(at.recheck_main([str(work / "event.json"), str(work / "same.json")]), 0)
        self.assertEqual(at.recheck_main([str(work / "event.json"), str(work / "edited.json")]), 1)
        self.assertEqual(at.recheck_main([str(work / "event.json"), str(work / "missing.json")]), 1)


# --------------------------------------------------------------------------- 2. names and the remembered choice


def write(path: Path, game: str = "fish", language: str = "Français", code: str = "fr", translator: str = "",
          text: str = "Âge : ") -> Path:
    f = tfmt.new_file(game, ENTRIES, language, code, translator)
    f.rows[0].translation = text
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tfmt.to_bytes(f))
    return path


class Names(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.folder = self.tmp / "translations"
        self.folder.mkdir()

    def test_taken_names_include_shipped_and_downloaded_files(self) -> None:
        write(self.folder / "fish" / "fr.tsv")
        write(self.folder / "plant" / "Plant Tycoon - Deutsch.txt", game="plant", language="Deutsch", code="de")
        write(self.folder / "Fish Tycoon - Español.txt", language="Español", code="es")
        self.assertEqual(tr.taken_names(self.folder), {"fish", "plant", "fr.tsv", "plant tycoon - deutsch.txt",
                                                       "fish tycoon - español.txt"})

    def test_free_name(self) -> None:
        self.assertEqual(tr.free_name("a.txt", {"b.txt"}), "a.txt")
        self.assertEqual(tr.free_name("A.txt", {"a.txt"}), "A (2).txt")
        self.assertEqual(tr.free_name("a.txt", {"a.txt", "a (2).txt"}), "a (3).txt")

    def test_an_added_file_never_takes_a_shipped_name(self) -> None:
        shipped = write(self.folder / "fish" / "Fish Tycoon - Français.txt", translator="Old")   # older layout
        source = write(self.tmp / "in" / "mine.txt", translator="Ann")
        target, _report = tr.install_file(source, "fish", ENTRIES, self.folder)
        self.assertEqual(target, self.folder / "Fish Tycoon - Français (2).txt")
        self.assertEqual(tfmt.parse_bytes(shipped.read_bytes()).translator, "Old")

    def test_edit_copies_are_per_game_and_never_the_bare_shipped_name(self) -> None:
        fish = tr.read_info(write(self.folder / "fish" / "fr.tsv"), "fish")
        plant = tr.read_info(write(self.folder / "plant" / "fr.tsv", game="plant"), "plant")
        fish_copy, plant_copy = tr.own_copy_path(fish, self.folder), tr.own_copy_path(plant, self.folder)
        self.assertNotEqual(fish_copy, plant_copy)
        self.assertEqual(fish_copy, self.folder / "Fish Tycoon - fr (own copy).tsv")
        self.assertEqual(plant_copy, self.folder / "Plant Tycoon - fr (own copy).tsv")
        for copy in (fish_copy, plant_copy):
            self.assertNotIn(copy.name.casefold(), {"fr.tsv"})
        fish_copy.write_bytes(fish.path.read_bytes())
        self.assertEqual(tr.own_copy_path(fish, self.folder), fish_copy)        # Edit... again reopens it
        plant_copy.write_bytes(b"not a translation")
        self.assertEqual(tr.own_copy_path(plant, self.folder), self.folder / "Plant Tycoon - fr (own copy) (2).tsv")

    def test_the_window_edits_its_own_copy(self) -> None:
        import tkinter as tk
        import translations_window as tw
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no Tk: {exc}")
        root.withdraw()
        try:
            shipped = write(self.folder / "fish" / "fr.tsv", translator="Ann")
            write(self.folder / "plant" / "fr.tsv", game="plant", translator="Bob")
            window = tw.TranslationsWindow(root, "fish", {"fish": [], "plant": []}, folder=self.folder,
                                           choices_path=self.tmp / "c.json")
            window.entries_cache["fish"] = ENTRIES
            index = next(n for n, i in enumerate(window.items) if i.path == shipped)
            window.listbox.selection_clear(0, "end")
            window.listbox.selection_set(index + 1)            # row 0 is English (original)
            with mock.patch.object(tw.messagebox, "askyesno", return_value=True), \
                    mock.patch.object(window, "open_editor") as open_editor:
                window.edit()
            opened = open_editor.call_args[0][0]
            self.assertEqual(opened, self.folder / "Fish Tycoon - fr (own copy).tsv")
            self.assertEqual(opened.read_bytes(), shipped.read_bytes())
            window.close()
        finally:
            root.destroy()

    def test_the_remembered_choice_is_source_and_name(self) -> None:
        shipped = write(self.folder / "fish" / "fr.tsv", translator="Ann")
        mine = write(self.folder / "fr.tsv", translator="Me")                 # the same bare name
        choices = self.tmp / "choice.json"
        tr.apply_choice("fish", shipped, [], choices, self.folder)
        self.assertEqual(tr.load_choices(choices)["fish"], "fish/fr.tsv")
        self.assertEqual(tr.chosen_path("fish", tr.load_choices(choices), self.folder), shipped)
        tr.apply_choice("fish", mine, [], choices, self.folder)
        self.assertEqual(tr.load_choices(choices)["fish"], "fr.tsv")
        self.assertEqual(tr.chosen_path("fish", tr.load_choices(choices), self.folder), mine)
        outside = write(self.tmp / "elsewhere" / "fr.tsv")
        self.assertEqual(tr.relative_name(outside, self.folder), str(outside.resolve()))
        self.assertEqual(tr.chosen_path("fish", {"fish": tr.relative_name(outside, self.folder)}, self.folder),
                         outside.resolve())


class DownloadNames(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.folder = self.tmp / "translations"

    def test_another_translators_file_with_that_name_is_kept(self) -> None:
        old = write(self.folder / "fish" / "fr.tsv", translator="Someone")       # came with an older patcher
        old_bytes = old.read_bytes()
        choices = self.tmp / "c.json"
        tr.apply_choice("fish", old, [], choices, self.folder)
        fake = FakeGitHub({"fr.tsv": translation(translator="Ann Lee")})
        remote = tgh.list_remote("fish", opener=fake)[0]
        bin_ = FakeRecycleBin()
        with mock.patch.object(tr, "recycle", bin_):
            saved = tgh.download(remote, self.folder, opener=fake)
        self.assertEqual(saved, self.folder / "fish" / "fr-ann-lee.tsv")
        self.assertEqual(old.read_bytes(), old_bytes)
        self.assertEqual(bin_.calls, [])
        self.assertEqual(tgh.row(remote, self.folder).status, tgh.INSTALLED)
        self.assertEqual(tgh.download(remote, self.folder, opener=fake), saved)   # again: nothing new
        self.assertEqual(tr.chosen_path("fish", tr.load_choices(choices), self.folder), old)   # still Someone's
        self.assertEqual(sorted(p.name for p in (self.folder / "fish").iterdir()), ["fr-ann-lee.tsv", "fr.tsv"])

    def test_a_downloaded_name_skips_the_players_names_too(self) -> None:
        write(self.folder / "fish" / "fr.tsv", translator="Someone")
        write(self.folder / "fr-ann-lee.tsv", translator="Me")                  # the player's own, flat folder
        fake = FakeGitHub({"fr.tsv": translation(translator="Ann Lee")})
        with mock.patch.object(tr, "recycle", FakeRecycleBin()):
            saved = tgh.download(tgh.list_remote("fish", opener=fake)[0], self.folder, opener=fake)
        self.assertEqual(saved.name, "fr-ann-lee-2.tsv")

    def test_the_same_translators_update_recycles_the_old_version(self) -> None:
        old = write(self.folder / "fish" / "fr.tsv", translator="Ann Lee", text="Vieux")
        old_bytes = old.read_bytes()
        new = translation(translator="Ann Lee", texts=("Âge : ", "Vous avez vendu %d poissons !"))
        fake = FakeGitHub({"fr.tsv": new})
        bin_ = FakeRecycleBin()
        unlink, remove, os_unlink, rmtree = no_plain_delete()
        with mock.patch.object(tr, "recycle", bin_), unlink as u, remove as r, os_unlink as ou, rmtree as rt:
            saved = tgh.download(tgh.list_remote("fish", opener=fake)[0], self.folder, opener=fake)
        for plain in (u, r, ou, rt):
            plain.assert_not_called()
        self.assertEqual(saved, old)
        self.assertEqual(saved.read_bytes(), new)
        self.assertEqual(bin_.calls, [[old.resolve()]])
        self.assertEqual([p.read_bytes() for p in bin_.bin.iterdir()], [old_bytes])

    def test_a_failing_recycle_bin_replaces_nothing(self) -> None:
        old = write(self.folder / "fish" / "fr.tsv", translator="Ann Lee", text="Vieux")
        old_bytes = old.read_bytes()
        fake = FakeGitHub({"fr.tsv": translation(translator="Ann Lee")})
        with mock.patch.object(tr, "recycle", side_effect=OSError("no bin")), self.assertRaises(tgh.GitHubProblem):
            tgh.download(tgh.list_remote("fish", opener=fake)[0], self.folder, opener=fake)
        self.assertEqual(old.read_bytes(), old_bytes)
        self.assertEqual([p.name for p in (self.folder / "fish").iterdir()], ["fr.tsv"])     # no .part left


# --------------------------------------------------------------------------- 3. adding: update or keep both


class AddKeepsOthers(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.folder = self.tmp / "translations"
        self.folder.mkdir()
        self.inbox = self.tmp / "in"
        self.old = write(self.folder / "Fish Tycoon - Français.txt", translator="Ann", text="Vieux")
        self.old_bytes = self.old.read_bytes()

    def add(self, source: Path, bin_=None):
        bin_ = bin_ or FakeRecycleBin()
        unlink, remove, os_unlink, rmtree = no_plain_delete()
        with mock.patch.object(tr, "recycle", bin_), unlink as u, remove as r, os_unlink as ou, rmtree as rt:
            target, _report = tr.install_file(source, "fish", ENTRIES, self.folder)
        for plain in (u, r, ou, rt):
            plain.assert_not_called()                         # nothing is ever deleted for good
        return target, bin_

    def test_same_language_code_and_translator_is_an_update(self) -> None:
        source = write(self.inbox / "new.txt", translator=" ann ", text="Neuf")
        target, bin_ = self.add(source)
        self.assertEqual(target, self.old)
        self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertEqual(bin_.calls, [[self.old.resolve()]])                 # the old one: Recycle Bin
        self.assertEqual([p.read_bytes() for p in bin_.bin.iterdir()], [self.old_bytes])

    def test_another_translator_keeps_both(self) -> None:
        source = write(self.inbox / "new.txt", translator="Zoe", text="Neuf")
        target, bin_ = self.add(source)
        self.assertEqual(target, self.folder / "Fish Tycoon - Français (by Zoe).txt")
        self.assertEqual(self.old.read_bytes(), self.old_bytes)
        self.assertEqual(bin_.calls, [])
        self.assertEqual(len(tr.installed("fish", self.folder)), 2)

    def test_another_code_keeps_both(self) -> None:
        source = write(self.inbox / "new.txt", code="fr-CA", translator="Ann", text="Neuf")
        target, bin_ = self.add(source)
        self.assertNotEqual(target, self.old)
        self.assertEqual(self.old.read_bytes(), self.old_bytes)
        self.assertEqual(bin_.calls, [])

    def test_uncredited_files_are_nobodys_update(self) -> None:
        self.old.unlink()
        old = write(self.folder / "Fish Tycoon - Français.txt", text="Vieux")
        old_bytes = old.read_bytes()
        target, bin_ = self.add(write(self.inbox / "new.txt", text="Neuf"))
        self.assertEqual(target, self.folder / "Fish Tycoon - Français (2).txt")
        self.assertEqual(old.read_bytes(), old_bytes)
        self.assertEqual(bin_.calls, [])

    def test_the_same_bytes_again_change_nothing(self) -> None:
        source = self.inbox / "same.txt"
        self.inbox.mkdir()
        shutil.copyfile(self.old, source)
        target, bin_ = self.add(source)
        self.assertEqual((target, bin_.calls), (self.old, []))
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["Fish Tycoon - Français.txt"])

    def test_a_failing_recycle_bin_replaces_nothing(self) -> None:
        source = write(self.inbox / "new.txt", translator="Ann", text="Neuf")
        with mock.patch.object(tr, "recycle", side_effect=OSError("no bin")), self.assertRaises(tr.TranslationProblem):
            tr.install_file(source, "fish", ENTRIES, self.folder)
        self.assertEqual(self.old.read_bytes(), self.old_bytes)


if __name__ == "__main__":
    unittest.main()
