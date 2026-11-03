"""The public translations folder (translations/<game>/<code>.tsv): its README, its names, the
data-only check, the pull-request validator and its workflow, the VirusTotal scan (mocked), the
release's "(TEST)" rule, and the Translations window's Download from GitHub... (mocked HTTP)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock
import urllib.error

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import accept_translation as at  # noqa: E402
import check_translation_pr as cpr  # noqa: E402
import translation_format as tfmt  # noqa: E402
import translation_public as tp  # noqa: E402
import translations as tr  # noqa: E402
import translations_github as tgh  # noqa: E402
import virustotal_scan as vt  # noqa: E402

WORKFLOWS = ROOT / ".github" / "workflows"
README = ROOT / "translations" / "README.md"
REPO = "Lorsieab2/Fish-and-Plant-Tycoon-Fix-Patcher"
ENTRIES = [tfmt.Entry(tfmt.make_key("strings", "1", "Age: "), "Age: "),
           tfmt.Entry(tfmt.make_key("strings", "69", "You have sold %d fish!"), "You have sold %d fish!")]


def translation(game: str = "fish", language: str = "Français", code: str = "fr", translator: str = "Ann Lee",
                texts=("Âge : ", "")) -> bytes:
    f = tfmt.new_file(game, ENTRIES, language, code, translator)
    for row, text in zip(f.rows, texts):
        row.translation = text
    return tfmt.to_bytes(f)


def on(flow: dict):
    return flow[True] if True in flow else flow["on"]       # YAML 1.1 reads "on" as True


# --------------------------------------------------------------------------- README and docs


class Readme(unittest.TestCase):
    def test_readme_has_the_share_warning_word_for_word(self) -> None:
        text = README.read_text(encoding="utf-8")
        quoted = " ".join(line[1:].strip() for line in text.splitlines() if line.startswith(">"))
        for paragraph in tr.SHARE_CONFIRMATION.split("\n\n"):
            self.assertIn(paragraph, quoted)
        for sentence in ("Please DO NOT put ANY PRIVATE DETAILS YOU DO NOT WANT TO MAKE PUBLIC!",
                         "Email addresses are never saved and are rejected from translation files."):
            self.assertIn(sentence, text)

    def test_readme_explains_the_easy_way(self) -> None:
        text = " ".join(README.read_text(encoding="utf-8").replace("\t", "\\t").split())
        text = text.replace("\\t", "\t")
        for needed in ("Upload files", "pull request automatically", "@translator", "fr.tsv", "UTF-8",
                       "VirusTotal's partners can see"):
            self.assertIn(needed, text)
        self.assertNotRegex(text, r"[\w.+-]+@[\w-]+\.[\w.]+")

    def test_docs_mention_virustotal_and_download(self) -> None:
        for path in (ROOT / "docs" / "translations.md", ROOT / "How to Use.txt", README):
            text = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn("VirusTotal's partners can see", text, path.name)
        for path in (ROOT / "docs" / "translations.md", ROOT / "How to Use.txt", ROOT / "README.md"):
            self.assertIn("Download from GitHub...", path.read_text(encoding="utf-8"), path.name)

    def test_the_folders_exist(self) -> None:
        for game in tp.GAMES:
            self.assertTrue((ROOT / "translations" / game).is_dir())


# --------------------------------------------------------------------------- names


class Names(unittest.TestCase):
    def test_plain_name(self) -> None:
        self.assertEqual(tp.public_name("fr"), "fr.tsv")
        self.assertEqual(tp.public_name("pt-BR", ["fr.tsv"]), "pt-BR.tsv")
        with self.assertRaises(ValueError):
            tp.public_name("../x")

    def test_one_collision_uses_the_credit_slug(self) -> None:
        self.assertEqual(tp.public_name("fr", ["fr.tsv"], "Ann Lee"), "fr-ann-lee.tsv")
        self.assertEqual(tp.public_name("fr", ["FR.TSV"], "Ann Lee"), "fr-ann-lee.tsv")   # no case on Windows

    def test_two_collisions_add_a_number(self) -> None:
        taken = ["fr.tsv", "fr-ann-lee.tsv"]
        self.assertEqual(tp.public_name("fr", taken, "Ann Lee"), "fr-ann-lee-2.tsv")
        self.assertEqual(tp.public_name("fr", taken + ["fr-ann-lee-2.tsv"], "Ann Lee"), "fr-ann-lee-3.tsv")

    def test_slug_from_a_non_ascii_credit(self) -> None:
        self.assertEqual(tp.credit_slug("Zoë Ångström"), "zoe-angstrom")
        self.assertEqual(tp.credit_slug("山田 太郎"), "translator")
        self.assertEqual(tp.credit_slug("  --Ann__Lee!! "), "ann-lee")
        long = tp.credit_slug("A" * 30 + " " + "b" * 30)
        self.assertLessEqual(len(long), 40)
        for slug in (long, tp.credit_slug("Zoë Ångström"), tp.credit_slug("Ñandú 2")):
            self.assertRegex(slug, r"^[a-z0-9-]{1,40}$")
            self.assertFalse(slug.endswith("-"))

    def test_names_fit_their_code(self) -> None:
        self.assertTrue(tp.name_fits_code("fr", "fr"))
        self.assertTrue(tp.name_fits_code("fr-ann-lee-2", "fr"))
        self.assertTrue(tp.name_fits_code("pt-BR-zoe", "pt-BR"))
        self.assertFalse(tp.name_fits_code("de", "fr"))
        self.assertFalse(tp.name_fits_code("fr-", "fr"))
        self.assertEqual(tp.slug_of("fr-ann-lee.tsv"), "ann-lee")
        self.assertEqual(tp.slug_of("pt-BR.tsv"), "")
        self.assertEqual(tp.slug_of("zh-Hans-mei.tsv"), "mei")

    def test_accept_never_overwrites(self) -> None:
        root = Path(tempfile.mkdtemp())
        folder = root / "translations" / "fish"
        folder.mkdir(parents=True)
        (folder / "fr.tsv").write_bytes(translation(translator="Someone"))
        work = Path(tempfile.mkdtemp())
        body = ("### Game\n\nFish Tycoon\n\n### Language\n\nFrançais\n\n### Credit name\n\nZoë Ångström\n\n"
                "### Translation file\n\n[f.txt](https://github.com/user-attachments/files/1/f.txt)\n\n"
                "### Licence\n\n- [X] mine\n")
        for expected in ("fr-zoe-angstrom.tsv", "fr-zoe-angstrom-2.tsv"):
            result = at.accept({"issue": {"number": 3, "body": body}}, work, fetch=lambda _u: translation(), root=root)
            self.assertEqual(result, "accepted")
            self.assertEqual((work / "target.txt").read_text(encoding="utf-8"), f"translations/fish/{expected}")
        self.assertEqual(tfmt.parse_bytes((folder / "fr.tsv").read_bytes()).translator, "Someone")

    def test_accept_refuses_a_file_that_was_not_scanned(self) -> None:
        work, root = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        body = ("### Game\n\nFish Tycoon\n\n### Credit name\n\nAnn\n\n### Translation file\n\n"
                "[f.txt](https://github.com/user-attachments/files/1/f.txt)\n\n### Licence\n\n- [X] mine\n")
        event = {"issue": {"number": 3, "body": body}}
        self.assertEqual(at.accept(event, work, fetch=lambda _u: translation(), root=root, expected="0" * 64), "refused")
        self.assertIn("VirusTotal", (work / "comment.md").read_text(encoding="utf-8"))
        good = tp.sha256(translation())
        self.assertEqual(at.accept(event, work, fetch=lambda _u: translation(), root=root, expected=good), "accepted")


# --------------------------------------------------------------------------- the data-only check


class Check(unittest.TestCase):
    def test_good_file(self) -> None:
        result = tp.check_file("translations/fish/fr.tsv", translation())
        self.assertTrue(result.ok, result.problems)
        self.assertEqual((result.language, result.code, result.translator), ("Français", "fr", "Ann Lee"))
        self.assertTrue(tp.check_file("translations/fish/Fish Tycoon - Français.txt", translation()).ok)

    def test_refusals_name_the_line(self) -> None:
        cases = {
            "email": (translation(texts=("Écrivez à ann@example.com", "")), "email address"),
            "placeholder": (translation(texts=("", "Vous avez vendu des poissons !")), "Line "),
            "bad choice": (translation(texts=("", "%d {%1: one=poisson | lots=poissons}")), "Line "),
            "nothing": (translation(texts=("", "")), "no translated line"),
            "other game": (translation(game="plant"), "Fish Tycoon"),
        }
        for name, (data, why) in cases.items():
            result = tp.check_file("translations/fish/fr.tsv", data)
            self.assertFalse(result.ok, name)
            self.assertIn(why, "\n".join(result.problems), name)
            self.assertNotIn("ann@example.com", "\n".join(result.problems))
        email = tp.check_file("translations/fish/fr.tsv", translation(texts=("ann@example.com", "")))
        self.assertTrue(any(p.startswith("Line 9:") for p in email.problems), email.problems)

    def test_precheck_refuses_anything_else(self) -> None:
        for path, data in (("translations/fish/fr.exe", translation()), ("translations/fish/x.zip", b"PK\x03\x04"),
                           ("translations/other/fr.tsv", translation()), ("src/fr.tsv", translation()),
                           ("translations/fish/fr.tsv", b"\xff\xfe" + "x".encode("utf-16-le")),
                           ("translations/fish/fr.tsv", b"MZ\x90\x00\x03"),
                           ("translations/fish/fr.tsv", b"a" * (tp.MAX_BYTES + 1)),
                           ("translations/fish/.hidden.tsv", translation()),
                           ("translations/fish/../x.tsv", translation())):
            with self.assertRaises(tp.NotATranslation, msg=path):
                tp.precheck(path, data)
        self.assertEqual(tp.precheck("translations/plant/ja.tsv", translation(game="plant")), "plant")

    def test_name_must_match_code(self) -> None:
        result = tp.check_file("translations/fish/de.tsv", translation())
        self.assertFalse(result.ok)
        self.assertTrue(tp.check_file("translations/fish/fr-ann-lee.tsv", translation()).ok)

    def test_blob_sha_is_gits(self) -> None:
        self.assertEqual(tp.blob_sha(b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
        self.assertEqual(tp.blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")


# --------------------------------------------------------------------------- the release


class Release(unittest.TestCase):
    def test_test_files_never_ship_and_accepted_ones_do(self) -> None:
        import build_release
        root = Path(tempfile.mkdtemp())
        fish, plant = root / "translations" / "fish", root / "translations" / "plant"
        fish.mkdir(parents=True)
        plant.mkdir(parents=True)
        (fish / "fr.tsv").write_bytes(translation())
        (fish / "Fish Tycoon - Deutsch.txt").write_bytes(translation(language="Deutsch", code="de"))
        (fish / "de.tsv").write_bytes(translation(language="(TEST) Deutsch", code="de"))
        (fish / "es.tsv").write_bytes(translation(language="Español", code="es", translator="(TEST) Bot"))
        (plant / "it-test.tsv").write_bytes(translation(game="plant", language="Italiano", code="it"))
        (plant / ".gitkeep").write_bytes(b"")
        (root / "translations" / "README.md").write_text("x", encoding="utf-8")
        files = build_release.shipped_translations(root)
        self.assertEqual(files, ["translations/fish/Fish Tycoon - Deutsch.txt", "translations/fish/fr.tsv"])

    def test_the_real_release_list_has_no_test_file(self) -> None:
        import build_release
        for path in build_release.shipped_translations() + build_release.FILES:
            self.assertNotIn("(TEST)", path)
            if path.startswith("translations/"):
                self.assertFalse(tp.is_test_translation(Path(path).name, (ROOT / path).read_bytes()), path)
        self.assertIn("src/translation_public.py", build_release.FILES)
        self.assertIn("src/translations_github.py", build_release.FILES)


# --------------------------------------------------------------------------- the workflows


class Workflows(unittest.TestCase):
    def load(self, name: str) -> tuple[dict, str]:
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        return yaml.safe_load(text), text

    def assert_no_shell_interpolation(self, flow: dict) -> None:
        for job in flow["jobs"].values():
            for step in job["steps"]:
                run = step.get("run", "")
                self.assertNotIn("${{", run, step.get("name"))
                self.assertNotIn("VT_API_KEY", run)
                self.assertNotRegex(run, r"\becho\b.*(KEY|TOKEN|secret)")

    def assert_secret_only_in_env(self, text: str) -> None:
        for line in text.splitlines():
            if "secrets.VT_API_KEY" in line:
                self.assertRegex(line.strip(), r"^VT_API_KEY: \$\{\{ secrets\.VT_API_KEY \}\}$")

    def test_pr_validator_triggers_and_permissions(self) -> None:
        flow, text = self.load("translation-pr.yml")
        self.assertEqual(on(flow), {"pull_request_target": {"types": ["opened", "synchronize", "reopened", "labeled"],
                                                            "paths": ["translations/**"]}})
        self.assertEqual(flow["permissions"], {"contents": "read", "pull-requests": "write", "issues": "write"})
        for job in flow["jobs"].values():
            self.assertNotIn("permissions", job)
        self.assertIn("accept-translation", flow["jobs"]["scan"]["if"])

    def test_pr_code_is_never_checked_out(self) -> None:
        flow, text = self.load("translation-pr.yml")
        for job in flow["jobs"].values():
            for step in job["steps"]:
                if str(step.get("uses", "")).startswith("actions/checkout"):
                    self.assertNotIn("ref", step.get("with", {}))
                    self.assertNotIn("repository", step.get("with", {}))
                    self.assertFalse(step["with"]["persist-credentials"])
        for field in ("head.ref", "head.sha", "head.repo", "pull_request.title", "pull_request.body", "merge"):
            self.assertNotIn(field, text)
        self.assertNotIn("git fetch", text)
        self.assertNotIn("pip install", text)

    def test_scan_runs_before_the_validator(self) -> None:
        flow, text = self.load("translation-pr.yml")
        self.assertEqual(flow["jobs"]["validate"]["needs"], "scan")
        self.assertIn("scripts/virustotal_scan.py --pr", text)
        self.assertIn("python -I scripts/check_translation_pr.py", text)
        self.assert_no_shell_interpolation(flow)
        self.assert_secret_only_in_env(text)
        scan_env = flow["jobs"]["scan"]["steps"][-1]["env"]
        self.assertEqual(scan_env["VT_API_KEY"], "${{ secrets.VT_API_KEY }}")
        self.assertNotIn("VT_API_KEY", str(flow["jobs"]["validate"]))

    def test_accept_flow_scans_first(self) -> None:
        flow, text = self.load("accept-translation.yml")
        self.assertEqual(flow["jobs"]["accept"]["needs"], "scan")
        self.assertEqual(flow["jobs"]["scan"]["permissions"], {"contents": "read", "issues": "write"})
        self.assertEqual(flow["jobs"]["accept"]["env"]["EXPECTED_SHA256"], "${{ needs.scan.outputs.sha256 }}")
        self.assertIn("scripts/virustotal_scan.py --issue", text)
        self.assert_no_shell_interpolation(flow)
        self.assert_secret_only_in_env(text)

    def test_push_rescan(self) -> None:
        flow, text = self.load("scan-translations.yml")
        self.assertEqual(on(flow), {"push": {"branches": ["main"], "paths": ["translations/**"]}})
        self.assertEqual(flow["permissions"], {"contents": "read"})
        self.assertIn("--push", text)
        self.assert_no_shell_interpolation(flow)
        self.assert_secret_only_in_env(text)

    def test_no_email_in_any_workflow(self) -> None:
        for name in ("translation-pr.yml", "accept-translation.yml", "scan-translations.yml"):
            self.assertNotRegex(self.load(name)[1], r"[\w.+-]+@[\w-]+\.[\w.]+")


# --------------------------------------------------------------------------- the pull-request validator


class PullRequest(unittest.TestCase):
    SHA = "a" * 40

    def event(self, association: str = "NONE") -> dict:
        return {"pull_request": {"number": 12, "head": {"sha": self.SHA}, "author_association": association}}

    def fake_http(self, files: dict[str, bytes], listing: list[dict], heads=None):
        """`heads`: the pull request's head each time it is asked again (default: always SHA)."""
        calls = []
        heads = list(heads or [])

        def http(method, url, token="", body=None, accept="", limit=0):
            calls.append((method, url))
            if url.endswith("/pulls/12"):
                return json.dumps({"head": {"sha": heads.pop(0) if heads else self.SHA}}).encode()
            if "/pulls/12/files" in url:
                return json.dumps(listing).encode()
            if "/contents/" in url:
                self.assertIn(f"ref={self.SHA}", url)
                path = url.split("/contents/", 1)[1].split("?", 1)[0]
                return files[path]
            if url.endswith("/issues/12/comments"):
                return b"{}"
            raise AssertionError(url)
        return http, calls

    def test_good_and_bad_files(self) -> None:
        files = {"translations/fish/fr.tsv": translation(),
                 "translations/fish/de.tsv": translation(language="Deutsch", code="de", texts=("me@example.com", ""))}
        listing = [{"filename": p, "status": "added"} for p in files] + [
            {"filename": "translations/plant/old.tsv", "status": "removed"},
            {"filename": "src/other.py", "status": "modified"}]
        http, calls = self.fake_http(files, listing)
        with mock.patch.object(cpr, "http", http):
            found = cpr.collect(REPO, self.event(), "token")
        self.assertEqual([p for p, _d, _n in found],
                         ["translations/fish/fr.tsv", "translations/fish/de.tsv", "translations/plant/old.tsv"])
        self.assertFalse(any("src/other.py" in url for _m, url in calls))
        ok, comment = cpr.validate(found)
        self.assertFalse(ok)
        self.assertIn("`translations/fish/fr.tsv`: **passed**", comment)
        self.assertIn("`translations/fish/de.tsv`: **refused**", comment)
        self.assertIn("Line 9", comment)
        self.assertNotIn("me@example.com", comment)
        ok, comment = cpr.validate(found[:1])
        self.assertTrue(ok)
        self.assertIn("merging", comment)

    def test_readme_needs_the_owner(self) -> None:
        listing = [{"filename": "translations/README.md", "status": "modified"}]
        http, _calls = self.fake_http({"translations/README.md": b"# hi\n"}, listing)
        with mock.patch.object(cpr, "http", http):
            self.assertFalse(cpr.validate(cpr.collect(REPO, self.event(), ""))[0])
            self.assertTrue(cpr.validate(cpr.collect(REPO, self.event("OWNER"), ""))[0])

    def test_event_is_checked(self) -> None:
        for bad in ({}, {"pull_request": {"number": "12; rm -rf /", "head": {"sha": self.SHA}}},
                    {"pull_request": {"number": 12, "head": {"sha": "$(id)"}}}):
            with self.assertRaises(cpr.ApiError):
                cpr.pr_context(bad)

    def test_http_only_to_api_github(self) -> None:
        for url in ("http://api.github.com/x", "https://evil.example/x", "https://raw.githubusercontent.com/x"):
            with self.assertRaises(cpr.ApiError):
                cpr.http("GET", url)


# --------------------------------------------------------------------------- VirusTotal (mocked)


class FakeVT:
    """VirusTotal's API in memory, with a clock that only the scanner's sleeps move."""

    def __init__(self, known: dict | None = None, analyses: list[dict] | None = None, statuses=None) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self.requests: list[tuple[str, str, float]] = []
        self.known = known or {}
        self.analyses = list(analyses or [])
        self.statuses = list(statuses or [])
        self.uploaded = b""

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def transport(self, method, url, headers, body, timeout):
        assert url.startswith("https://www.virustotal.com/api/v3/"), url
        assert headers["x-apikey"] == "KEY"
        self.requests.append((method, url, self.now))
        if self.statuses:
            status = self.statuses.pop(0)
            if status != 200:
                return status, b""
        if method == "GET" and "/files/" in url:
            sha = url.rsplit("/", 1)[1]
            if sha not in self.known:
                return 404, b'{"error": {"code": "NotFoundError"}}'
            return 200, json.dumps({"data": {"attributes": self.known[sha]}}).encode()
        if method == "POST":
            self.uploaded = body
            return 200, b'{"data": {"type": "analysis", "id": "abc123=="}}'
        if "/analyses/" in url:
            return 200, json.dumps({"data": {"attributes": self.analyses.pop(0)}}).encode()
        raise AssertionError(url)

    def client(self) -> vt.Client:
        return vt.Client("KEY", self.transport, self.sleep, self.clock)


def results(**categories: str) -> dict:
    return {engine: {"category": category, "engine_name": engine} for engine, category in categories.items()}


class VirusTotal(unittest.TestCase):
    DATA = translation()
    PATH = "translations/fish/fr.tsv"

    def test_clean_known_file_passes(self) -> None:
        fake = FakeVT({tp.sha256(self.DATA): {"last_analysis_results": results(A="harmless", B="undetected"),
                                              "last_analysis_stats": {"harmless": 1, "undetected": 1}}})
        verdict = vt.scan(fake.client(), self.PATH, self.DATA)
        self.assertTrue(verdict.passed)
        self.assertEqual(len(fake.requests), 1)
        self.assertEqual(fake.uploaded, b"")

    def test_flagged_file_fails_and_names_its_engines(self) -> None:
        fake = FakeVT({tp.sha256(self.DATA): {"last_analysis_results": results(Zeta="malicious", Alpha="suspicious",
                                                                               C="harmless")}})
        verdicts = vt.scan_all([(self.PATH, self.DATA)], "KEY", fake.client())
        self.assertEqual(verdicts[0].status, "flagged")
        self.assertEqual(verdicts[0].engines, ["Alpha", "Zeta"])
        ok, text = vt.report(verdicts, False)
        self.assertFalse(ok)
        self.assertIn("Alpha, Zeta", text)

    def test_unknown_file_is_uploaded_and_polled_until_it_passes(self) -> None:
        fake = FakeVT(analyses=[{"status": "queued"}, {"status": "in-progress"},
                                {"status": "completed", "results": results(A="undetected"), "stats": {}}])
        verdict = vt.scan(fake.client(), self.PATH, self.DATA)
        self.assertTrue(verdict.passed, verdict)
        self.assertIn(self.DATA, fake.uploaded)
        self.assertEqual([m for m, _u, _t in fake.requests], ["GET", "POST", "GET", "GET", "GET"])

    def test_unknown_file_is_uploaded_and_polled_until_it_fails(self) -> None:
        fake = FakeVT(analyses=[{"status": "queued"},
                                {"status": "completed", "results": results(Bad="malicious"), "stats": {"malicious": 1}}])
        verdict = vt.scan(fake.client(), self.PATH, self.DATA)
        self.assertEqual((verdict.status, verdict.engines), ("flagged", ["Bad"]))

    def test_timeout_fails(self) -> None:
        fake = FakeVT(analyses=[{"status": "queued"}] * 200)
        verdict = vt.scan(fake.client(), self.PATH, self.DATA, timeout=120)
        self.assertEqual(verdict.status, "not scanned")
        self.assertIn("did not finish", verdict.detail)
        self.assertFalse(verdict.passed)

    def test_unreachable_and_bad_key_fail(self) -> None:
        def down(*_a):
            raise urllib.error.URLError("no route")
        self.assertEqual(vt.scan(vt.Client("KEY", down, lambda _s: None), self.PATH, self.DATA).status, "not scanned")
        fake = FakeVT(statuses=[401])
        verdict = vt.scan(fake.client(), self.PATH, self.DATA)
        self.assertEqual(verdict.status, "not scanned")
        self.assertNotIn("KEY", verdict.detail)

    def test_missing_key_fails(self) -> None:
        verdicts = vt.scan_all([(self.PATH, self.DATA)], "")
        self.assertEqual(verdicts[0].status, "not scanned")
        ok, text = vt.report(verdicts, True)
        self.assertFalse(ok)
        self.assertIn("VT_API_KEY repository secret is not set", text)

    def test_rate_limit_and_pace_are_respected(self) -> None:
        fake = FakeVT({tp.sha256(self.DATA): {"last_analysis_results": results(A="harmless")}}, statuses=[429, 200])
        client = fake.client()
        self.assertTrue(vt.scan(client, self.PATH, self.DATA).passed)
        self.assertIn(vt.RATE_LIMIT_WAIT, fake.sleeps)
        vt.scan(client, self.PATH, self.DATA)
        times = [t for _m, _u, t in fake.requests]
        self.assertTrue(all(b - a >= vt.MIN_INTERVAL for a, b in zip(times, times[1:])), times)
        self.assertGreaterEqual(60 / vt.MIN_INTERVAL, 4 - 1e-9)
        self.assertLessEqual(60 / vt.MIN_INTERVAL, 4)

    def test_precheck_runs_first(self) -> None:
        fake = FakeVT()
        verdicts = vt.scan_all([("translations/fish/x.exe", b"MZ")], "KEY", fake.client())
        self.assertEqual(verdicts[0].status, "refused")
        self.assertEqual(fake.requests, [])

    def test_only_virustotal_is_contacted(self) -> None:
        with mock.patch.object(vt, "API", "https://evil.example/api/v3"):
            self.assertEqual(vt.scan(FakeVT().client(), self.PATH, self.DATA).status, "not scanned")

    def test_main_masks_the_key_and_never_prints_it(self) -> None:
        work = Path(tempfile.mkdtemp())
        event = work / "event.json"
        event.write_text(json.dumps({"commits": []}), encoding="utf-8")
        out = io.StringIO()
        with mock.patch.dict("os.environ", {"VT_API_KEY": "SECRET123", "GITHUB_ACTIONS": "true"}), \
                mock.patch("sys.stdout", out):
            self.assertEqual(vt.main(["--push", str(event), str(work / "w")]), 0)
        printed = out.getvalue()
        self.assertEqual(printed.count("SECRET123"), 1)
        self.assertIn("::add-mask::SECRET123", printed)
        self.assertNotIn("SECRET123", (work / "w" / "comment.md").read_text(encoding="utf-8"))
        with mock.patch.dict("os.environ", {"VT_API_KEY": ""}, clear=False), mock.patch("sys.stdout", io.StringIO()):
            (ROOT / "translations").exists()
            event.write_text(json.dumps({"commits": [{"added": ["translations/README.md"]}]}), encoding="utf-8")
            self.assertEqual(vt.main(["--push", str(event), str(work / "w2")]), 0)   # nothing to scan


# --------------------------------------------------------------------------- Download from GitHub... (mocked)


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeGitHub:
    def __init__(self, files: dict[str, bytes], listing_extra=(), fail=None) -> None:
        self.files = files
        self.extra = list(listing_extra)
        self.fail = fail
        self.urls: list[str] = []
        self.headers: list[dict] = []

    def open(self, request, timeout=None):
        url = request.full_url
        self.urls.append(url)
        self.headers.append(dict(request.header_items()))
        assert timeout and timeout <= 30
        if self.fail is not None:
            raise self.fail
        if "/contents/translations/fish" in url:
            items = [{"type": "file", "name": n, "sha": tp.blob_sha(d), "size": len(d),
                      "download_url": f"https://raw.githubusercontent.com/{REPO}/main/translations/fish/{n}"}
                     for n, d in self.files.items()] + self.extra
            return Reply(json.dumps(items).encode())
        if "/commits?" in url:
            return Reply(b'[{"commit": {"committer": {"date": "2026-10-30T12:00:00Z"}}}]')
        if url.startswith("https://raw.githubusercontent.com/"):
            return Reply(self.files[url.rsplit("/", 1)[1]])
        raise AssertionError(url)


class Download(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp()) / "translations"
        self.good = translation()
        self.bad = translation(language="Deutsch", code="de", texts=("x@example.com", ""))

    def test_listing(self) -> None:
        fake = FakeGitHub({"fr.tsv": self.good, "fr-zoe.tsv": self.good}, listing_extra=[
            {"type": "dir", "name": "sub", "sha": "b" * 40, "size": 0, "download_url": None},
            {"type": "file", "name": "evil.exe", "sha": "c" * 40, "size": 3, "download_url": "https://raw.githubusercontent.com/x"},
            {"type": "file", "name": "x.tsv", "sha": "d" * 40, "size": 3, "download_url": "https://evil.example/x.tsv"},
            {"type": "file", "name": "big.tsv", "sha": "e" * 40, "size": tp.MAX_BYTES + 1,
             "download_url": f"https://raw.githubusercontent.com/{REPO}/main/translations/fish/big.tsv"}])
        remotes = tgh.list_remote("fish", opener=fake)
        self.assertEqual([r.name for r in remotes], ["fr-zoe.tsv", "fr.tsv"])
        self.assertEqual(fake.urls[0], f"https://api.github.com/repos/{REPO}/contents/translations/fish")
        self.assertNotIn("ref=", fake.urls[0])                   # the default branch only
        self.assertEqual(tgh.last_changed(remotes[0], opener=fake), "2026-10-30")
        rows = [tgh.row(r, self.folder) for r in remotes]
        self.assertEqual(rows[0].credit, "zoe (from the file name)")
        self.assertEqual(rows[1].credit, tgh.NOT_DOWNLOADED)
        self.assertEqual({r.status for r in rows}, {tgh.NOT_INSTALLED})
        for headers in fake.headers:
            self.assertNotIn("Authorization", headers)
            self.assertNotIn("Cookie", headers)

    def test_download_and_update_status(self) -> None:
        fake = FakeGitHub({"fr.tsv": self.good})
        remote = tgh.list_remote("fish", opener=fake)[0]
        path = tgh.download(remote, self.folder, opener=fake)
        self.assertEqual(path, self.folder / "fish" / "fr.tsv")
        self.assertEqual(path.read_bytes(), self.good)
        row = tgh.row(remote, self.folder)
        self.assertEqual((row.status, row.language, row.credit), (tgh.INSTALLED, "Français", "Ann Lee"))
        self.assertIn("Français", [i.language for i in tr.installed("fish", self.folder)])
        newer = FakeGitHub({"fr.tsv": translation(texts=("Âge : ", "Vous avez vendu %d poissons !"))})
        self.assertEqual(tgh.row(tgh.list_remote("fish", opener=newer)[0], self.folder).status, tgh.UPDATE)

    def test_validation_failure_installs_nothing(self) -> None:
        fake = FakeGitHub({"de.tsv": self.bad})
        remote = tgh.list_remote("fish", opener=fake)[0]
        with self.assertRaises(tgh.GitHubProblem) as caught:
            tgh.download(remote, self.folder, opener=fake)
        self.assertIn("was not installed", str(caught.exception))
        self.assertNotIn("x@example.com", str(caught.exception))
        self.assertFalse((self.folder / "fish" / "de.tsv").exists())

    def test_changed_bytes_are_refused(self) -> None:
        fake = FakeGitHub({"fr.tsv": self.good})
        remote = tgh.list_remote("fish", opener=fake)[0]
        fake.files["fr.tsv"] = translation(texts=("Autre", ""))
        with self.assertRaises(tgh.GitHubProblem):
            tgh.download(remote, self.folder, opener=fake)

    def test_network_error_and_rate_limit(self) -> None:
        with self.assertRaises(tgh.GitHubProblem) as caught:
            tgh.list_remote("fish", opener=FakeGitHub({}, fail=urllib.error.URLError("offline")))
        self.assertIn("internet", str(caught.exception))
        with self.assertRaises(tgh.GitHubProblem):
            tgh.list_remote("fish", opener=FakeGitHub({}, fail=TimeoutError()))
        limited = urllib.error.HTTPError("u", 403, "rate", {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"}, None)
        with self.assertRaises(tgh.GitHubProblem) as caught:
            tgh.list_remote("fish", opener=FakeGitHub({}, fail=limited))
        self.assertIn("60 requests an hour", str(caught.exception))
        missing = urllib.error.HTTPError("u", 404, "missing", {}, None)
        self.assertEqual(tgh.list_remote("fish", opener=FakeGitHub({}, fail=missing)), [])
        self.assertEqual(tgh.last_changed(tgh.Remote("fish", "fr.tsv", "translations/fish/fr.tsv", "a" * 40, 1, ""),
                                          opener=FakeGitHub({}, fail=limited)), "")

    def test_host_allow_list(self) -> None:
        for url in ("https://evil.example/x", "http://api.github.com/x", "https://github.com/x",
                    "https://api.github.com.evil.example/x", "file:///C:/x"):
            with self.assertRaises(tgh.GitHubProblem, msg=url):
                tgh.get(url, 10, opener=FakeGitHub({}))
        remote = tgh.Remote("fish", "fr.tsv", "translations/fish/fr.tsv", "a" * 40, 1, "https://evil.example/fr.tsv")
        with self.assertRaises(tgh.GitHubProblem):
            tgh.download(remote, self.folder, opener=FakeGitHub({}))
        with self.assertRaises(tgh.GitHubProblem):
            tgh._Guard().redirect_request(None, None, 302, "", {}, "https://evil.example/")

    def test_names_cannot_leave_the_folder(self) -> None:
        for name in ("../x.tsv", "..\\x.tsv", "a/b.tsv", ".tsv", "x.exe", "con:x.tsv"):
            self.assertFalse(tp.is_translation_name(name), name)
            with self.assertRaises(tgh.GitHubProblem):
                tgh.download(tgh.Remote("fish", name, "", "a" * 40, 1, "https://raw.githubusercontent.com/x"),
                             self.folder, opener=FakeGitHub({}))


class DownloadWindow(unittest.TestCase):
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

    def test_button_list_and_multi_download(self) -> None:
        import translations_window as tw
        folder = Path(tempfile.mkdtemp()) / "translations"
        folder.mkdir()
        window = tw.TranslationsWindow(self.root, "fish", {"fish": [], "plant": []}, folder=folder,
                                       choices_path=folder / "c.json")
        try:
            texts = []
            stack = [window.window]
            while stack:
                widget = stack.pop()
                stack.extend(widget.winfo_children())
                try:
                    texts.append(widget.cget("text"))
                except tk.TclError:
                    pass
            self.assertIn("Download from GitHub...", texts)
            self.assertNotIn("Get from GitHub...", texts)
            fake = FakeGitHub({"fr.tsv": translation(), "de.tsv": translation(language="Deutsch", code="de")})
            dialog = tw.DownloadDialog(window.window, "fish", folder, on_done=window.refresh, threaded=False, opener=fake)
            self.assertEqual(str(dialog.tree.cget("selectmode")), "extended")
            self.assertEqual(len(dialog.rows), 2)
            self.assertEqual(dialog.tree.item("0")["values"][2], "2026-10-30")
            dialog.tree.selection_set(("0", "1"))
            with mock.patch.object(tw.messagebox, "showinfo") as info:
                saved = dialog.download_selected()
            self.assertEqual(sorted(p.name for p in saved), ["de.tsv", "fr.tsv"])
            self.assertIn("installed", info.call_args[0][1])
            self.assertEqual({r.status for r in dialog.rows}, {tgh.INSTALLED})
            self.assertEqual(len(window.items), 2)
            offline = tw.DownloadDialog(window.window, "fish", folder, threaded=False,
                                        opener=FakeGitHub({}, fail=urllib.error.URLError("x")))
            self.assertIn("internet", offline.status.get())
            offline.window.destroy()
            dialog.window.destroy()
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
