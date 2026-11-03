"""Download from GitHub...: the public translations folder on the patcher's GitHub, read-only.

* It lists translations/<game>/ on the default branch through GitHub's public API, with no login:
  https://api.github.com/repos/Lorsieab2/Fish-and-Plant-Tycoon-Fix-Patcher/contents/translations/<game>
  and asks the commits API when each file last changed (for display).
* A file the player already has is compared by content: the contents API's "sha" is the git blob
  SHA-1 of the file, so a local copy whose blob SHA differs is "Update available".
* Downloading reads at most MAX_BYTES from raw.githubusercontent.com, checks the bytes are the ones
  GitHub listed (blob SHA), then checks them as DATA ONLY with the public folder's own validator
  (src/translation_public.py) before anything is written into the player's translations/<game>/.

Only api.github.com and raw.githubusercontent.com are ever contacted (https, a timeout, redirects
only between those two). Nothing about the player is sent: no login, no token, no git or GitHub
credentials are ever read, and the requests carry only a User-Agent naming the patcher.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as _dt
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import translation_public as tp
import translations as tr

REPOSITORY = "Lorsieab2/Fish-and-Plant-Tycoon-Fix-Patcher"
API = "https://api.github.com"
ALLOWED_HOSTS = ("api.github.com", "raw.githubusercontent.com")
TIMEOUT = 15
LIST_LIMIT = 1024 * 1024
MAX_BYTES = tp.MAX_BYTES
USER_AGENT = "Fish-and-Plant-Tycoon-Fix-Patcher"
NOT_DOWNLOADED = "(not downloaded yet)"
NOT_INSTALLED = "Not installed"
INSTALLED = "Installed"
UPDATE = "Update available"


class GitHubProblem(Exception):
    """Something the player must hear about (shown as is)."""


class NotFound(GitHubProblem):
    pass


@dataclass
class Remote:
    game: str
    name: str
    path: str
    sha: str
    size: int
    download_url: str
    changed: str = ""            # "2026-11-02" (the last commit that changed it), "" when unknown


@dataclass
class Row:
    """One line of the Download from GitHub... list."""
    remote: Remote
    language: str
    credit: str
    status: str


def _check_host(url: str) -> None:
    parts = urllib.parse.urlparse(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise GitHubProblem(f"Refused to download from {parts.hostname or url}: only GitHub is used.")


class _Guard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    # No credentials of any kind: no auth handler, no cookies, no token.
    return urllib.request.build_opener(_Guard())


def get(url: str, limit: int, accept: str = "application/vnd.github+json", opener=None) -> bytes:
    """GET from GitHub (the two allowed hosts only), at most `limit` bytes, or GitHubProblem."""
    _check_host(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with (opener or _opener()).open(request, timeout=TIMEOUT) as reply:
            data = reply.read(limit + 1)
    except urllib.error.HTTPError as exc:
        headers = exc.headers or {}
        if exc.code in (403, 429) and (str(headers.get("X-RateLimit-Remaining", "")) == "0" or exc.code == 429):
            reset = ""
            try:
                when = _dt.datetime.fromtimestamp(int(headers.get("X-RateLimit-Reset", "")))
                reset = f" Try again after {when:%H:%M}."
            except (TypeError, ValueError, OverflowError, OSError):
                reset = " Try again in an hour."
            raise GitHubProblem("GitHub's limit for downloads without an account was reached (60 requests an "
                                "hour)." + reset) from None
        if exc.code == 404:
            raise NotFound("GitHub has no such file or folder.") from None
        raise GitHubProblem(f"GitHub answered with an error ({exc.code}). Try again later.") from None
    except GitHubProblem:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise GitHubProblem("Could not reach GitHub. Check the internet connection and try again.") from exc
    if len(data) > limit:
        raise GitHubProblem("GitHub sent more than expected; nothing was saved.")
    return data


def folder_url(game: str) -> str:
    return f"{API}/repos/{REPOSITORY}/contents/{tp.FOLDER}/{game}"


def list_remote(game: str, opener=None) -> list[Remote]:
    """The translations in translations/<game>/ on the default branch ([] when there is none yet)."""
    if game not in tp.GAMES:
        raise GitHubProblem(f"Unknown game {game!r}.")
    try:
        data = get(folder_url(game), LIST_LIMIT, opener=opener)
    except NotFound:
        return []
    try:
        items = json.loads(data.decode("utf-8"))
    except ValueError:
        raise GitHubProblem("GitHub's list could not be read. Try again later.") from None
    if not isinstance(items, list):
        raise GitHubProblem("GitHub's list could not be read. Try again later.")
    found: list[Remote] = []
    raw_prefix = f"/{REPOSITORY}/"
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        name, sha, url = str(item.get("name") or ""), str(item.get("sha") or ""), str(item.get("download_url") or "")
        size = item.get("size") if isinstance(item.get("size"), int) else -1
        parts = urllib.parse.urlparse(url)
        if (not tp.is_translation_name(name) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha)
                or not 0 < size <= MAX_BYTES or parts.scheme != "https" or parts.hostname != "raw.githubusercontent.com"
                or not parts.path.startswith(raw_prefix)):
            continue
        found.append(Remote(game, name, f"{tp.FOLDER}/{game}/{name}", sha, size, url))
    return sorted(found, key=lambda r: r.name.casefold())


def last_changed(remote: Remote, opener=None) -> str:
    """The date the file last changed on GitHub ("" when GitHub does not say)."""
    url = (f"{API}/repos/{REPOSITORY}/commits?path={urllib.parse.quote(remote.path, safe='/')}&per_page=1")
    try:
        commits = json.loads(get(url, LIST_LIMIT, opener=opener).decode("utf-8"))
        date = str(commits[0]["commit"]["committer"]["date"])
    except (GitHubProblem, ValueError, LookupError, TypeError):
        return ""
    return date[:10] if len(date) >= 10 and date[4] == "-" else ""


def local_path(remote: Remote, folder: Path | None = None) -> Path:
    return (folder or tr.TRANSLATIONS_DIR) / remote.game / remote.name


def installed_copy(remote: Remote, folder: Path | None = None) -> Path | None:
    """The local file that IS this GitHub file (the same git blob SHA), wherever it was saved: under
    its own name, or under a name of its own when another translator's file already had that name."""
    place = (folder or tr.TRANSLATIONS_DIR) / remote.game
    exact = local_path(remote, folder)
    try:
        others = sorted(p for p in place.iterdir() if p != exact and p.name.lower().endswith(tp.EXTENSIONS))
    except OSError:
        others = []
    for path in [exact, *others]:
        try:
            if path.is_file() and path.stat().st_size <= tr.MAX_FILE and tp.blob_sha(path.read_bytes()) == remote.sha:
                return path
        except OSError:
            continue
    return None


def row(remote: Remote, folder: Path | None = None) -> Row:
    """Its line in the list: language and credit from the downloaded copy, and its status."""
    copy = installed_copy(remote, folder)
    if copy is not None:
        info = tr.read_info(copy, remote.game)
        return Row(remote, (info.language if info else "") or "?", (info.translator if info else "") or "", INSTALLED)
    path = local_path(remote, folder)
    try:
        data = path.read_bytes() if path.is_file() and path.stat().st_size <= tr.MAX_FILE else None
    except OSError:
        data = None
    if data is None:
        # Several files for one language ("fr.tsv", "fr-ann-lee.tsv"): the name's credit slug tells
        # them apart until the file is downloaded and its own credit row can be read.
        slug = tp.slug_of(remote.name)
        return Row(remote, NOT_DOWNLOADED, f"{slug} (from the file name)" if slug else NOT_DOWNLOADED, NOT_INSTALLED)
    info = tr.read_info(path, remote.game)
    status = INSTALLED if tp.blob_sha(data) == remote.sha else UPDATE
    return Row(remote, (info.language if info else "") or "?", (info.translator if info else "") or "", status)


def download(remote: Remote, folder: Path | None = None, opener=None) -> Path:
    """Download one file, check it as data, and save it as translations/<game>/<name>.

    A file already there under that name is replaced only when the download is its update: the same
    language, @code and @translator. The old version then goes to the Recycle Bin (never deleted for
    good). Anyone else's file with that name (one that came with an older patcher, or an earlier
    GitHub file by someone else) is kept, and the download gets a name of its own
    ("<code>-<credit slug>.tsv", then "-2"...), checked against every name in the folders."""
    if not tp.is_translation_name(remote.name) or remote.game not in tp.GAMES:
        raise GitHubProblem(f"{remote.name}: not a translation file.")
    data = get(remote.download_url, MAX_BYTES, accept="application/octet-stream", opener=opener)
    if tp.blob_sha(data) != remote.sha:
        raise GitHubProblem(f"{remote.name}: the download is not the file GitHub listed (it may have just "
                            "changed). Press Refresh and try again.")
    result = tp.check_file(remote.path, data)
    if not result.ok:
        raise GitHubProblem(f"{remote.name} was not installed:\n" + "\n".join(result.problems[:20]))
    already = installed_copy(remote, folder)
    if already is not None:
        return already                              # exactly these bytes are installed
    target = local_path(remote, folder)
    replacing = False
    if target.exists():
        old = tr.read_info(target, remote.game)
        if old is not None and tr.is_update(old, result.language, result.code, result.translator):
            replacing = True
        else:
            taken = tr.taken_names(folder or tr.TRANSLATIONS_DIR)
            try:
                name = tp.public_name(result.code, taken, result.translator)
            except ValueError:
                name = tr.free_name(remote.name, taken)
            target = target.parent / name
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=target.parent, suffix=".part")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        if replacing:
            tr.recycle([target])                    # the old version: Recycle Bin, never a plain delete
        os.replace(temp, target)
    except OSError as exc:
        Path(temp).unlink(missing_ok=True)          # only our own unfinished download
        raise GitHubProblem(f"{remote.name}: could not be saved ({exc.strerror or exc}); nothing was "
                            "replaced.") from None
    return target
