"""Sharing translations on GitHub: the issue form, the "accept-translation" Action (minimal
permissions, no issue field ever in a shell command, the bot's identity, the size limit) and
scripts/accept_translation.py (the issue read as data, the file checked as data only, only the
typed credit name added, problems commented), and the release shipping translations/<game>/."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import accept_translation as at  # noqa: E402
import translation_format as tfmt  # noqa: E402
import translations as tr  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "accept-translation.yml"
TEMPLATE = ROOT / ".github" / "ISSUE_TEMPLATE" / "translation.yml"
URL = "https://github.com/user-attachments/files/123456/Fish.Tycoon.-.Francais.txt"


def translation(translator: str = "", text: str = "Âge : ") -> bytes:
    entries = [tfmt.Entry(tfmt.make_key("strings", "1", "Age: "), "Age: ")]
    f = tfmt.new_file("fish", entries, "Français", "fr", translator)
    f.rows[0].translation = text
    return tfmt.to_bytes(f)


def body(game="Fish Tycoon", language="Français", credit="Ann Lee", licence="- [X] I made this translation",
         file=f"[Fish Tycoon - Français.txt]({URL})") -> str:
    return (f"### Game\n\n{game}\n\n### Language\n\n{language}\n\n### Credit name\n\n{credit}\n\n### Coverage\n\n"
            f"_No response_\n\n### Translation file\n\n{file}\n\n### Licence\n\n{licence}\n")


class Workflow(unittest.TestCase):
    def setUp(self) -> None:
        self.flow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_minimal_permissions(self) -> None:
        self.assertEqual(self.flow["permissions"], {"contents": "write", "pull-requests": "write", "issues": "write"})
        job = self.flow["jobs"]["accept"]
        self.assertNotIn("permissions", job)

    def test_runs_only_on_the_owners_label(self) -> None:
        on = self.flow[True] if True in self.flow else self.flow["on"]          # YAML 1.1 reads "on" as True
        self.assertEqual(on, {"issues": {"types": ["labeled"]}})
        condition = self.flow["jobs"]["accept"]["if"]
        self.assertIn("github.event.label.name == 'accept-translation'", condition)
        self.assertIn("'translation'", condition)

    def test_no_issue_field_in_any_shell_command(self) -> None:
        for step in self.flow["jobs"]["accept"]["steps"]:
            run = step.get("run", "")
            self.assertNotIn("${{", run, step.get("name"))
        env = self.flow["jobs"]["accept"]["env"]
        self.assertEqual(env["ISSUE_NUMBER"], "${{ github.event.issue.number }}")
        for field in ("issue.body", "issue.title", "comment.body", "issue.user"):
            self.assertNotIn(field, self.text)

    def test_checks_as_data_and_commits_as_the_bot_without_an_email(self) -> None:
        self.assertIn("python -I scripts/accept_translation.py \"$GITHUB_EVENT_PATH\"", self.text)
        self.assertIn('git config user.name "github-actions[bot]"', self.text)
        self.assertIn('git config user.email ""', self.text)
        self.assertNotRegex(self.text, r"[\w.+-]+@[\w-]+\.[\w.]+")
        self.assertEqual(at.MAX_BYTES, 2 * 1024 * 1024)

    def test_issue_form(self) -> None:
        form = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(form["labels"], ["translation"])
        fields = {item.get("id"): item for item in form["body"] if item.get("id")}
        self.assertEqual(set(fields), {"game", "language", "credit", "coverage", "file", "licence"})
        for required in ("game", "language", "credit", "file"):
            self.assertTrue(fields[required]["validations"]["required"], required)
        self.assertTrue(fields["licence"]["attributes"]["options"][0]["required"])
        self.assertEqual(fields["game"]["attributes"]["options"], ["Fish Tycoon", "Plant Tycoon"])
        self.assertIn(tfmt.EMAIL_MESSAGE, TEMPLATE.read_text(encoding="utf-8").replace("\n        ", " "))
        url = tr.issue_url("plant", "Türkçe")
        for field in ("game", "language"):
            self.assertIn(f"&{field}=", url)
        self.assertIn(f"template={TEMPLATE.name}", url)


class Accept(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp())
        self.root = Path(tempfile.mkdtemp())
        self.added: list[Path] = []

    def run_event(self, text: str, data: bytes = b"") -> str:
        fetch = mock.Mock(return_value=data or translation())
        result = at.accept({"issue": {"number": 7, "body": text}}, self.work, fetch=fetch, root=self.root)
        target = self.work / "target.txt"
        if target.exists():
            self.added.append(self.root / target.read_text(encoding="utf-8"))
        return result

    def test_accepted_with_only_the_typed_credit(self) -> None:
        self.assertEqual(self.run_event(body(), translation("someone else")), "accepted")
        path = self.added[0]
        self.assertEqual(path.parent, self.root / "translations" / "fish")
        self.assertEqual(path.name, "Fish Tycoon - Français.txt")
        parsed = tfmt.parse_bytes(path.read_bytes(), "fish")
        self.assertEqual(parsed.translator, "Ann Lee")
        pr = (self.work / "pr_body.md").read_text(encoding="utf-8")
        self.assertIn("Closes #7", pr)
        self.assertIn("Coverage", pr)

    def test_refusals_are_commented(self) -> None:
        cases = {
            "email in file": (body(), translation(text="Âge : écrivez à x@y.com"), "email"),
            "email credit": (body(credit="ann@example.com"), b"", "email"),
            "no credit": (body(credit="_No response_"), b"", "credit name is missing"),
            "licence": (body(licence="- [ ] I made this translation"), b"", "licence"),
            "game": (body(game="Virtual Villagers"), b"", "Game"),
            "not github": (body(file="[x.txt](https://evil.example/x.txt)"), b"", "No translation file"),
            "other game": (body(game="Plant Tycoon"), b"", "cannot be used"),
            "nothing translated": (body(), translation(text=""), "no translated line"),
        }
        for name, (text, data, why) in cases.items():
            for leftover in ("comment.md", "result.txt", "target.txt"):
                (self.work / leftover).unlink(missing_ok=True)
            self.assertEqual(self.run_event(text, data), "refused", name)
            comment = (self.work / "comment.md").read_text(encoding="utf-8")
            self.assertIn(why, comment, name)
            self.assertNotIn("x@y.com", comment)
            self.assertNotIn("ann@example.com", comment)

    def test_downloads_only_from_github_and_at_most_the_limit(self) -> None:
        with self.assertRaises(at.Refused):
            at.download("http://github.com/user-attachments/files/1/a.txt")
        with self.assertRaises(at.Refused):
            at.download("https://example.com/a.txt")

        class Reply:
            def __init__(self, size):
                self.size = size

            def read(self, n):
                return b"x" * min(n, self.size)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        with mock.patch("urllib.request.OpenerDirector.open", return_value=Reply(at.MAX_BYTES + 10)):
            with self.assertRaises(at.Refused):
                at.download(URL)
        with mock.patch("urllib.request.OpenerDirector.open", return_value=Reply(10)):
            self.assertEqual(at.download(URL), b"x" * 10)

    def test_form_fields(self) -> None:
        fields = at.form_fields(body())
        self.assertEqual(fields["game"], "Fish Tycoon")
        self.assertEqual(fields["coverage"], "")
        self.assertEqual(at.attachment_url(fields["translation file"]), URL)


class Release(unittest.TestCase):
    def test_shipped_translations_are_in_the_zip_list(self) -> None:
        import build_release
        files = build_release.shipped_translations()
        on_disk = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "translations").glob("*/*.txt"))
        self.assertEqual(sorted(files), on_disk)
        for module in ("src/translations.py", "src/translations_window.py", "src/translation_format.py",
                       "src/translation_strings.py", "docs/translations.md"):
            self.assertIn(module, build_release.FILES)


if __name__ == "__main__":
    unittest.main()
