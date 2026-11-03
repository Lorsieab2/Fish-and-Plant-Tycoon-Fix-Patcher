"""Send every user-submitted translation file to VirusTotal; refuse anything an engine flags.

    python -I scripts/virustotal_scan.py --pr <work folder>            (translation-pr.yml)
    python -I scripts/virustotal_scan.py --issue <event.json> <work>   (accept-translation.yml)
    python -I scripts/virustotal_scan.py --push <event.json> <work>    (scan-translations.yml)

The owner's rule: "PLEASE RUN EVERY SINGLE USER-SUBMITTED FILE THROUGH VIRUSTOTAL AND REJECT
ANYTHING THAT IS FLAGGED." So, for each file, as DATA ONLY (nothing in a file is ever run):

1. Pre-check (src/translation_public.py): a UTF-8 .tsv (or .txt) file of at most 2 MB under
   translations/<game>/. Anything else -- a binary, an archive, a script, another extension -- is
   refused before VirusTotal.
2. Look its SHA-256 up (GET /api/v3/files/{sha256}). When VirusTotal does not know it, upload it
   (POST /api/v3/files) and poll /api/v3/analyses/{id} until the analysis completes, within
   FILE_TIMEOUT seconds. Requests are spaced MIN_INTERVAL seconds apart (the free API allows 4 a
   minute) and a 429 answer waits RATE_LIMIT_WAIT seconds before trying again.
3. Any engine that says "malicious" or "suspicious" FAILS the check, and the engines are named.
   VirusTotal unreachable, a timeout, a refused key or no key at all also FAILS ("not scanned"):
   the check never passes by default.

Only https://www.virustotal.com is contacted, and only the file itself is sent. The API key comes
only from the VT_API_KEY environment variable (the repository secret); it is never printed, and is
masked in the log (::add-mask::) in case anything ever would. The result goes to the job summary,
<work>/comment.md and, for a pull request or issue that failed, a comment on it. In --issue mode the
scanned file's SHA-256 is written to $GITHUB_OUTPUT (sha256=...), and scripts/accept_translation.py
refuses a download that differs. Exit code 1 when anything failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import translation_public as tp  # noqa: E402

API = "https://www.virustotal.com/api/v3"
HOST = "www.virustotal.com"
MIN_INTERVAL = 15.0          # seconds between requests: the free API allows 4 a minute
RATE_LIMIT_WAIT = 60.0       # after a 429 answer
RATE_LIMIT_TRIES = 5
POLL_INTERVAL = 20.0
FILE_TIMEOUT = 15 * 60.0     # the most one file may take, upload and analysis included
REQUEST_TIMEOUT = 60
FLAGGED = ("malicious", "suspicious")
NO_KEY = ("The VT_API_KEY repository secret is not set, so the files were NOT scanned and the check fails. "
          "The owner adds it in Settings, Secrets and variables, Actions.")
PRIVACY = ("Submitted files are sent to VirusTotal, where VirusTotal's partners can see them: never put private "
           "details in a translation.")


class ScanError(Exception):
    """VirusTotal could not give an answer (unreachable, timeout, refused key...)."""


@dataclass
class Verdict:
    path: str
    status: str                       # "clean", "flagged", "not scanned", "refused"
    sha256: str = ""
    engines: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "clean"

    def line(self) -> str:
        path = " ".join(self.path.replace("`", "'").split())
        if self.status == "clean":
            return f"- `{path}`: clean ({self.detail})"
        if self.status == "flagged":
            return f"- `{path}`: **FLAGGED** by {', '.join(self.engines) or 'VirusTotal'} ({self.detail})"
        if self.status == "refused":
            return f"- `{path}`: **refused before scanning**: {self.detail}"
        return f"- `{path}`: **not scanned**: {self.detail}"


def default_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> tuple[int, bytes]:
    """One HTTPS request to VirusTotal; redirects are never followed."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as reply:
            return reply.status, reply.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        return exc.code, b""


class Client:
    """VirusTotal API v3 with the free API's pace. `transport`, `sleep` and `clock` are replaced in
    the tests."""

    def __init__(self, key: str, transport=default_transport, sleep=time.sleep, clock=time.monotonic) -> None:
        self.key = key
        self.transport = transport
        self.sleep = sleep
        self.clock = clock
        self.last = None

    def _pace(self) -> None:
        if self.last is not None:
            wait = self.last + MIN_INTERVAL - self.clock()
            if wait > 0:
                self.sleep(wait)
        self.last = self.clock()

    def request(self, method: str, path: str, body: bytes | None = None, content_type: str = "") -> tuple[int, dict]:
        url = API + path
        parts = urllib.parse.urlparse(url)
        if parts.scheme != "https" or parts.hostname != HOST:
            raise ScanError("refused to contact anything but www.virustotal.com")
        headers = {"x-apikey": self.key, "Accept": "application/json", "User-Agent": "translation-scan"}
        if content_type:
            headers["Content-Type"] = content_type
        for _attempt in range(RATE_LIMIT_TRIES):
            self._pace()
            try:
                status, data = self.transport(method, url, headers, body, REQUEST_TIMEOUT)
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                raise ScanError(f"VirusTotal could not be reached ({getattr(exc, 'reason', None) or type(exc).__name__})") from None
            if status == 429:
                self.sleep(RATE_LIMIT_WAIT)
                continue
            if status in (401, 403):
                raise ScanError("VirusTotal refused the API key")
            try:
                return status, (json.loads(data.decode("utf-8")) if data else {})
            except ValueError:
                raise ScanError(f"VirusTotal's answer ({status}) could not be read") from None
        raise ScanError("VirusTotal's rate limit did not clear")


def _flagged_engines(results: dict) -> list[str]:
    engines = []
    for engine, result in (results or {}).items():
        if isinstance(result, dict) and result.get("category") in FLAGGED:
            engines.append(str(result.get("engine_name") or engine))
    return sorted(set(engines), key=str.casefold)


def _verdict(path: str, digest: str, results: dict, stats: dict) -> Verdict:
    engines = _flagged_engines(results)
    bad = sum(int((stats or {}).get(k) or 0) for k in FLAGGED)
    total = len(results or {}) or sum(int(v or 0) for v in (stats or {}).values() if isinstance(v, int))
    if engines or bad:
        return Verdict(path, "flagged", digest, engines or ["(engines not named)"],
                       f"{max(len(engines), bad)} of {total} engines")
    return Verdict(path, "clean", digest, detail=f"0 of {total} engines flagged it")


def _multipart(name: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----translation-scan-" + uuid.uuid4().hex
    safe = "".join(c for c in name if c.isalnum() or c in "._-") or "translation.tsv"
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{safe}\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n").encode("ascii")
    return head + data + f"\r\n--{boundary}--\r\n".encode("ascii"), f"multipart/form-data; boundary={boundary}"


def scan(client: Client, path: str, data: bytes, timeout: float = FILE_TIMEOUT) -> Verdict:
    """Look the file up; upload and poll when VirusTotal does not know it."""
    digest = tp.sha256(data)
    start = client.clock()
    try:
        status, reply = client.request("GET", f"/files/{digest}")
        if status == 200:
            attributes = (reply.get("data") or {}).get("attributes") or {}
            results = attributes.get("last_analysis_results") or {}
            if results:
                return _verdict(path, digest, results, attributes.get("last_analysis_stats") or {})
        elif status != 404:
            raise ScanError(f"VirusTotal answered {status} to the lookup")
        body, content_type = _multipart(path.rsplit("/", 1)[-1], data)
        status, reply = client.request("POST", "/files", body, content_type)
        analysis = str((reply.get("data") or {}).get("id") or "")
        if status != 200 or not analysis or not all(c.isalnum() or c in "=-_" for c in analysis):
            raise ScanError(f"VirusTotal did not take the upload ({status})")
        while True:
            if client.clock() - start > timeout:
                raise ScanError(f"VirusTotal's analysis did not finish within {int(timeout)} seconds")
            status, reply = client.request("GET", f"/analyses/{urllib.parse.quote(analysis, safe='')}")
            if status != 200:
                raise ScanError(f"VirusTotal answered {status} to the analysis")
            attributes = (reply.get("data") or {}).get("attributes") or {}
            if attributes.get("status") == "completed":
                return _verdict(path, digest, attributes.get("results") or {}, attributes.get("stats") or {})
            client.sleep(POLL_INTERVAL)
    except ScanError as why:
        return Verdict(path, "not scanned", digest, detail=str(why))


def scan_all(files: list[tuple[str, bytes]], key: str, client: Client | None = None) -> list[Verdict]:
    """Pre-check and scan every file. No key: every file is "not scanned" (a failure)."""
    verdicts: list[Verdict] = []
    for path, data in files:
        try:
            tp.precheck(path, data)
        except tp.NotATranslation as why:
            verdicts.append(Verdict(path, "refused", tp.sha256(data), detail=str(why)))
            continue
        if not key:
            verdicts.append(Verdict(path, "not scanned", tp.sha256(data), detail=NO_KEY))
            continue
        client = client or Client(key)
        verdicts.append(scan(client, path, data))
    return verdicts


def report(verdicts: list[Verdict], key_missing: bool) -> tuple[bool, str]:
    ok = bool(verdicts) and all(v.passed for v in verdicts)
    parts = ["<!-- virustotal-scan -->", "## VirusTotal scan", ""]
    if key_missing:
        parts += [f"**{NO_KEY}**", ""]
    parts += [v.line() for v in verdicts] or ["No submitted file to scan."]
    if not verdicts:
        ok = True
    parts += ["", "Passed: no engine flagged any file." if ok else
              "**Failed.** A flagged file is refused; a file that was not scanned is refused until it can be.",
              "", PRIVACY]
    return ok, "\n".join(parts)


# --------------------------------------------------------------------------- the three modes


def _pr_files(event: dict, repo: str, token: str) -> tuple[int, list[tuple[str, bytes]]]:
    import check_translation_pr as pr
    number, _sha, _who = pr.pr_context(event)
    return number, [(path, data) for path, data, _note in pr.collect(repo, event, token) if data is not None]


def _issue_file(event: dict) -> tuple[int, list[tuple[str, bytes]]]:
    import accept_translation as at
    issue = event.get("issue") or {}
    number = int(issue.get("number") or 0)
    fields = at.form_fields(str(issue.get("body") or ""))
    game = at.GAMES.get(fields.get("game", "").strip(), "")
    url = at.attachment_url(fields.get("translation file", ""))
    extension = "." + urllib.parse.urlparse(url).path.rsplit(".", 1)[-1].lower()
    return number, [(f"{tp.FOLDER}/{game or 'unknown'}/attachment{extension}", at.download(url))]


def _push_files(event: dict, root: Path = ROOT) -> list[tuple[str, bytes]]:
    paths: set[str] = set()
    for commit in event.get("commits") or []:
        for key in ("added", "modified"):
            paths.update(str(p) for p in commit.get(key) or [] if str(p).startswith(tp.FOLDER + "/"))
    files = []
    for path in sorted(paths - set(tp.REPOSITORY_FILES)):
        target = (root / path).resolve()
        if root.resolve() in target.parents and target.is_file():
            files.append((path, target.read_bytes()[: tp.MAX_BYTES + 1]))
    return files


def _summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write(text + "\n")


def _output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write(f"{name}={value}\n")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[0] not in ("--pr", "--issue", "--push"):
        raise SystemExit(__doc__)
    key = os.environ.get("VT_API_KEY", "").strip()
    if key and os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{key}")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    mode = argv[0]
    work = Path(argv[-1])
    work.mkdir(parents=True, exist_ok=True)
    number = 0
    try:
        if mode == "--pr":
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
            number, files = _pr_files(event, repo, token)
        else:
            event = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
            if mode == "--issue":
                number, files = _issue_file(event)
            else:
                files = _push_files(event)
    except Exception as exc:  # noqa: BLE001 - anything at all fails the check, never passes it
        reason = str(exc).replace(key, "***") if key else str(exc)
        files, verdicts = [], [Verdict("(the submitted files)", "not scanned", detail=f"could not be fetched: {reason}")]
    else:
        verdicts = scan_all(files, key)
    ok, text = report(verdicts, not key)
    (work / "comment.md").write_text(text, encoding="utf-8")
    _summary(text)
    if mode == "--issue" and ok and verdicts:
        _output("sha256", verdicts[0].sha256)
    if not ok and number and mode in ("--pr", "--issue"):
        import check_translation_pr as pr
        try:
            pr.post_comment(repo, number, text, token)
        except pr.ApiError as exc:
            print(f"Could not comment: {exc}")
    print("passed" if ok else "failed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
