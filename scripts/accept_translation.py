"""Accept a translation shared through a GitHub issue (.github/workflows/accept-translation.yml).

    python -I scripts/accept_translation.py <event.json> <work folder>

Run by the Action when the owner adds the "accept-translation" label. Everything in the issue is
untrusted DATA: the issue form is read from the event JSON file (never through a shell), the
attachment is downloaded only from GitHub's own attachment hosts, at most MAX_BYTES, and it is
only ever parsed as text by src/translation_format.py -- nothing in it is executed. Then:

* accepted: the file goes to the public folder, translations/<fish|plant>/<language code>.tsv
  (src/translation_public.py; <code>-<credit slug>.tsv when that language is already there, so
  nobody's file is overwritten), with its @translator row set to the typed credit name (and nothing
  else personal), and <work>/pr_body.md is written; the workflow commits it as github-actions[bot]
  and opens a pull request;
* refused: <work>/comment.md says why (the validator's report, with line numbers), and the
  workflow posts it on the issue.

Before this runs, the workflow's "scan" job has sent the same attachment to VirusTotal
(scripts/virustotal_scan.py); its SHA-256 comes in the EXPECTED_SHA256 environment variable and a
download that differs from what was scanned is refused.

Exit code 0 in both cases (2 = the event is not usable at all). <work>/result.txt holds
"accepted" or "refused" and <work>/target.txt the added file's path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import translation_format as tfmt  # noqa: E402
import translation_public as tp  # noqa: E402

MAX_BYTES = tp.MAX_BYTES
ALLOWED_HOSTS = ("github.com", "user-images.githubusercontent.com", "objects.githubusercontent.com",
                 "private-user-images.githubusercontent.com")
ATTACHMENT_RE = re.compile(r"https://(?:github\.com/(?:user-attachments/files/\d+/|[\w.-]+/[\w.-]+/files/\d+/)"
                           r"[^\s)\]\"'<>]+)")
GAMES = {title: game for game, title in tfmt.GAME_TITLES.items()}
CREDIT_MAX = 60


class Refused(Exception):
    pass


def form_fields(body: str) -> dict[str, str]:
    """An issue form's answers: '### Label' headings and the text under each."""
    fields: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for line in (body or "").replace("\r\n", "\n").split("\n"):
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            if current is not None:
                fields[current] = "\n".join(lines).strip()
            current, lines = heading.group(1).strip().lower(), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        fields[current] = "\n".join(lines).strip()
    return {k: ("" if v == "_No response_" else v) for k, v in fields.items()}


def credit_name(text: str) -> str:
    name = tfmt.normalise_credit(text)
    if not name:
        raise Refused("The credit name is missing.")
    if tfmt.contains_email(name) or "@" in name or "＠" in name:
        raise Refused("The credit name looks like an email address. " + tfmt.EMAIL_MESSAGE)
    if len(name) > CREDIT_MAX or any(c in name for c in "<>[]`|\\"):
        raise Refused(f"The credit name must be plain text of at most {CREDIT_MAX} letters.")
    return name


def attachment_url(text: str) -> str:
    found = ATTACHMENT_RE.findall(text or "")
    txt = [u for u in found if urllib.parse.urlparse(u).path.lower().endswith(tp.EXTENSIONS)]
    if not txt:
        raise Refused("No translation file (.tsv or .txt) is attached in the \"Translation file\" field.")
    return txt[0]


def download(url: str, limit: int = MAX_BYTES) -> bytes:
    """The attachment's bytes, following redirects only to GitHub's own hosts."""
    class Guard(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if urllib.parse.urlparse(newurl).hostname not in ALLOWED_HOSTS:
                raise Refused("The attachment does not come from GitHub.")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    if urllib.parse.urlparse(url).hostname not in ALLOWED_HOSTS or not url.startswith("https://"):
        raise Refused("The attachment does not come from GitHub.")
    opener = urllib.request.build_opener(Guard())
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "translation-check"}), timeout=60) as reply:
        data = reply.read(limit + 1)
    if len(data) > limit:
        raise Refused(f"The file is larger than {limit // 1024} KB; a translation is much smaller.")
    return data


def check(data: bytes, game: str, extension: str = tp.DOCUMENTED_EXTENSION) -> tuple[tfmt.TranslationFile, tfmt.Report]:
    """The public folder's check (src/translation_public.py: UTF-8, at most 2 MB, format, game, keys,
    placeholders, choices, no email address), the same one the pull-request validator uses."""
    result = tp.check_file(f"{tp.FOLDER}/{game}/upload{extension}", data)
    problems = [p for p in result.problems if not p.startswith("upload" + extension)]   # the name is ours
    if problems:
        raise Refused("The file cannot be used:\n" + "\n".join(problems))
    parsed = tfmt.parse_bytes(data, game)
    return parsed, tfmt.validate(parsed)


def expected_sha256() -> str:
    """The SHA-256 the scan job checked (empty when run outside the workflow)."""
    value = os.environ.get("EXPECTED_SHA256", "").strip().lower()
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else ""


def accept(event: dict, work: Path, fetch=download, root: Path = ROOT, expected: str | None = None) -> str:
    issue = event.get("issue") or {}
    fields = form_fields(str(issue.get("body") or ""))
    number = int(issue.get("number") or 0)
    try:
        game = GAMES.get(fields.get("game", "").strip())
        if game is None:
            raise Refused("The \"Game\" field must be Fish Tycoon or Plant Tycoon.")
        if "[x]" not in fields.get("licence", "").lower():
            raise Refused("The licence box is not ticked.")
        name = credit_name(fields.get("credit name", ""))
        url = attachment_url(fields.get("translation file", ""))
        data = fetch(url)
        if expected is not None and tp.sha256(data) != expected:
            raise Refused("The attachment is not the file VirusTotal scanned; please share it again.")
        parsed, report = check(data, game, "." + urllib.parse.urlparse(url).path.rsplit(".", 1)[-1].lower())
        language = parsed.language.strip()
        if not language or tfmt.contains_email(language):
            raise Refused("The file has no @language row (the language's own name).")
        folder = root / tp.FOLDER / game
        taken = [p.name for p in folder.iterdir()] if folder.is_dir() else []
        try:
            file_name = tp.public_name(parsed.value("@code"), taken, name)
        except ValueError:
            raise Refused("The file has no usable @code row (the language code, like fr or pt-BR).") from None
        parsed.set_info("@translator", "", name)
        target = folder / file_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(tfmt.to_bytes(parsed))
        recheck = tfmt.parse_bytes(target.read_bytes(), game)
        if recheck.fatal or not tfmt.validate(recheck).usable:
            target.unlink()
            raise Refused("The file changed when it was written; please share it again.")
        (work / "target.txt").write_text(target.relative_to(root).as_posix(), encoding="utf-8")
        (work / "pr_body.md").write_text(
            f"Adds the {tfmt.GAME_TITLES[game]} translation \"{language}\" shared in #{number}, credited to "
            f"{name}.\n\nChecked as data by src/translation_format.py:\n\n```\n{report.summary()}\n```\n\n"
            f"Closes #{number}\n", encoding="utf-8")
        (work / "result.txt").write_text("accepted", encoding="utf-8")
        return "accepted"
    except Refused as why:
        (work / "comment.md").write_text(
            "This translation could not be added automatically:\n\n```\n" + str(why).replace("```", "'''")[:6000]
            + "\n```\n\nPlease fix the file in the patcher's Translations window (Check shows the same report) and "
            "share it again. " + tfmt.EMAIL_MESSAGE + "\n", encoding="utf-8")
        (work / "result.txt").write_text("refused", encoding="utf-8")
        return "refused"


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    try:
        event = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 2
    work = Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    # In the Action, the scan job's SHA-256 is required: no scan, no pull request.
    expected = expected_sha256() or ("" if os.environ.get("GITHUB_ACTIONS") else None)
    print(accept(event, work, expected=expected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
