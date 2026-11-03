"""Check the translation files a pull request adds or changes under translations/.

    python -I scripts/check_translation_pr.py <work folder>

Run by .github/workflows/translation-pr.yml (pull_request_target) AFTER its VirusTotal job
(scripts/virustotal_scan.py --pr) has passed. This script comes from the BASE branch; the pull
request's code is never checked out or run. Everything about the pull request is untrusted DATA:

* the pull request's number and head commit are read from the event file ($GITHUB_EVENT_PATH),
  never through a shell;
* the changed files are listed, and each one under translations/ fetched at the head commit, only
  through api.github.com (the contents API, at most 2 MB each), as bytes;
* each is checked by src/translation_public.py (UTF-8, translations/<game>/<code>.tsv, format, game,
  keys, placeholders, person and number choices, no email address; every refusal names its line),
  the same check scripts/accept_translation.py uses for the Share on GitHub issues;
* the result is commented on the pull request through the API (GITHUB_TOKEN, issues: write) and
  written to <work>/comment.md and the job summary. Exit code 1 when any file is refused.

The owner accepts a translation by merging the pull request (the "accept-translation" label runs
the checks again first). Nothing here ever prints a token.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import translation_format as tfmt  # noqa: E402
import translation_public as tp  # noqa: E402

API = "https://api.github.com"
ALLOWED_HOSTS = ("api.github.com",)
TIMEOUT = 30
MARKER = "<!-- translation-check -->"
TRUSTED_AUTHORS = ("OWNER", "MEMBER", "COLLABORATOR")


class ApiError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).hostname not in ALLOWED_HOSTS:
            raise ApiError("GitHub answered with a redirect to another host.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http(method: str, url: str, token: str = "", body: bytes | None = None, accept: str = "application/vnd.github+json",
         limit: int = 8 * 1024 * 1024) -> bytes:
    """One request to api.github.com (nothing else), at most `limit` + 1 bytes read."""
    parts = urllib.parse.urlparse(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise ApiError(f"refused to contact {parts.hostname or url}")
    headers = {"Accept": accept, "User-Agent": "translation-check", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=TIMEOUT) as reply:
            return reply.read(limit + 1)
    except urllib.error.HTTPError as exc:
        raise ApiError(f"GitHub answered {exc.code} for {parts.path}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise ApiError(f"GitHub could not be reached ({getattr(exc, 'reason', exc)})") from None


def pr_context(event: dict) -> tuple[int, str, str]:
    """(number, head commit SHA, author association) from the event, checked."""
    pr = event.get("pull_request") or {}
    number = pr.get("number")
    sha = str((pr.get("head") or {}).get("sha") or "")
    if not isinstance(number, int) or number <= 0 or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ApiError("the event has no usable pull request number and head commit")
    return number, sha, str(pr.get("author_association") or "")


def changed_files(repo: str, number: int, token: str) -> list[dict]:
    files: list[dict] = []
    for page in range(1, 31):                         # GitHub lists at most 3,000 files
        url = f"{API}/repos/{repo}/pulls/{number}/files?per_page=100&page={page}"
        batch = json.loads(http("GET", url, token).decode("utf-8"))
        if not isinstance(batch, list):
            raise ApiError("GitHub's file list was not a list")
        files.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            break
    return files


def fetch_file(repo: str, path: str, ref: str, token: str) -> bytes:
    """The file's bytes at that commit, as data (more than MAX_BYTES is cut at MAX_BYTES + 1, which
    the pre-check then refuses)."""
    url = (f"{API}/repos/{repo}/contents/{urllib.parse.quote(path, safe='/')}"
           f"?ref={urllib.parse.quote(ref, safe='')}")
    return http("GET", url, token, accept="application/vnd.github.raw", limit=tp.MAX_BYTES)


def collect(repo: str, event: dict, token: str) -> list[tuple[str, bytes | None, str]]:
    """Every changed path under translations/: (path, its bytes or None, a note when not fetched)."""
    number, sha, association = pr_context(event)
    found: list[tuple[str, bytes | None, str]] = []
    for item in changed_files(repo, number, token):
        path = str(item.get("filename") or "")
        if not path.startswith(tp.FOLDER + "/"):
            continue
        if item.get("status") == "removed":
            found.append((path, None, "removed (nothing to check; the owner decides)"))
        elif path in tp.REPOSITORY_FILES and association in TRUSTED_AUTHORS:
            found.append((path, None, "a repository file changed by the owner (not a translation; not checked)"))
        else:
            found.append((path, fetch_file(repo, path, sha, token), ""))
    return found


def _fence(text: str) -> str:
    return text.replace("```", "'''")


def _plain(text: str) -> str:
    """A file's own text (language, credit) shown in code quotes: no backticks, one short line."""
    return " ".join(text.replace("`", "'").split())[:80]


def validate(files: list[tuple[str, bytes | None, str]]) -> tuple[bool, str]:
    """(every file passed, the comment)."""
    ok = True
    parts = [MARKER, "## Translation check", ""]
    if not files:
        parts.append("This pull request changes nothing under `translations/`.")
    for path, data, note in files:
        shown = " ".join(path.replace("`", "'").split())
        if data is None:
            parts.append(f"- `{shown}`: {note}")
            continue
        result = tp.check_file(path, data)
        if result.ok:
            credit = f", credit: `{_plain(result.translator)}`" if result.translator else ""
            parts.append(f"- `{shown}`: **passed** (`{_plain(result.language)}` `{_plain(result.code)}`{credit}). "
                         + " ".join(result.notes[:1]))
            if len(result.notes) > 1:
                parts += ["", "  ```", *("  " + _fence(n) for n in result.notes[1:30]), "  ```"]
        else:
            ok = False
            parts += [f"- `{shown}`: **refused**", "", "  ```", *("  " + _fence(p) for p in result.problems[:60]),
                      "  ```"]
    parts += ["", ("All translation files passed. The owner accepts them by merging this pull request."
                   if ok else "Please fix the lines above (the patcher's Translations window, Check, shows the same "
                              "report) and push again."),
              "", tfmt.EMAIL_MESSAGE]
    return ok, "\n".join(parts)[:60000]


def post_comment(repo: str, number: int, body: str, token: str) -> None:
    http("POST", f"{API}/repos/{repo}/issues/{number}/comments", token,
         body=json.dumps({"body": body}).encode("utf-8"))


def write_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write(text + "\n")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    work = Path(sys.argv[1])
    work.mkdir(parents=True, exist_ok=True)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        number, _sha, _who = pr_context(event)
        ok, comment = validate(collect(repo, event, token))
    except (ApiError, OSError, KeyError, ValueError) as exc:
        write_summary(f"Translation check could not run: {exc}")
        print(f"Translation check could not run: {exc}")
        return 1
    (work / "comment.md").write_text(comment, encoding="utf-8")
    write_summary(comment)
    try:
        post_comment(repo, number, comment, token)
    except ApiError as exc:
        print(f"Could not comment: {exc}")
    print("passed" if ok else "refused")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
