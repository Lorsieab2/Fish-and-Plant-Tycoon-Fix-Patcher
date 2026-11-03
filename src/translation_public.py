"""The public translations folder on GitHub: translations/fish/ and translations/plant/.

Shared by every LDW patcher (the spec agreed between the patcher repos):

* a public translation is ``translations/<game>/<language code>.tsv`` (``fr.tsv``, ``ja.tsv``,
  ``pt-BR.tsv``), the documented name. When that language is already there, a new one is
  ``<code>-<credit slug>.tsv`` (``fr-ann-lee.tsv``), then ``<code>-<credit slug>-2.tsv`` and so on, so
  nobody's file is overwritten. The older ``<Game title> - <language>.txt`` name is still read
  everywhere, so no existing file breaks;
* a submitted file must be UTF-8 text (with or without a BOM) of at most MAX_BYTES, with one of
  EXTENSIONS, directly in translations/fish/ or translations/plant/; anything else (a binary, an
  archive, a script, another extension or folder) is refused before anything else looks at it;
* then it is checked as DATA ONLY by src/translation_format.py (``check_file``): it must read, be for
  the folder's game, have no email address and at least one translated line; row errors (keys,
  placeholders, person and number choices) are listed with their line numbers.

Pure Python with no game or GUI imports: the GitHub Actions (scripts/check_translation_pr.py,
scripts/virustotal_scan.py, scripts/accept_translation.py) and the patcher's "Download from GitHub..."
(src/translations_github.py) all use it, and nothing here ever runs anything from a file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
import unicodedata

import translation_format as tfmt

FOLDER = "translations"
GAMES = ("fish", "plant")
DOCUMENTED_EXTENSION = ".tsv"
EXTENSIONS = (".tsv", ".txt")
MAX_BYTES = 2 * 1024 * 1024
# A BCP 47 language code as the files use it: fr, pt-BR, zh-Hans, fil...
CODE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
# A file name GitHub may list: no folder parts, nothing hidden, nothing Windows cannot store.
_SAFE_NAME_RE = re.compile(r'^[^<>:"/\\|?*\x00-\x1f]{1,120}$')
# Repository files that live in the folder but are not translations (only the owner changes them).
REPOSITORY_FILES = ("translations/README.md", "translations/fish/.gitkeep", "translations/plant/.gitkeep")


class NotATranslation(ValueError):
    """The pre-check refused a file (wrong place, extension, size or encoding)."""


SLUG_MAX = 40
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def credit_slug(credit: str) -> str:
    """A credit name as a file-name part: ASCII, lower case, [a-z0-9-] only, at most SLUG_MAX letters
    ("Zoë Ångström" -> "zoe-angstrom"); "translator" when nothing ASCII is left (a name in another
    script)."""
    ascii_text = unicodedata.normalize("NFKD", credit or "").encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:SLUG_MAX].strip("-")
    return slug or "translator"


def public_name(code: str, taken=(), credit: str = "") -> str:
    """The name of a public translation: "<code>.tsv"; when that is taken, "<code>-<credit slug>.tsv",
    then "<code>-<credit slug>-2.tsv", "-3"... `taken` are the names already in the folder (compared
    without case, as Windows does)."""
    code = (code or "").strip()
    if not CODE_RE.match(code):
        raise ValueError(f"not a language code: {code!r}")
    used = {str(n).casefold() for n in taken}
    name = code + DOCUMENTED_EXTENSION
    if name.casefold() not in used:
        return name
    stem = f"{code}-{credit_slug(credit)}"
    name = stem + DOCUMENTED_EXTENSION
    number = 2
    while name.casefold() in used:
        name = f"{stem}-{number}{DOCUMENTED_EXTENSION}"
        number += 1
    return name


def name_fits_code(stem: str, code: str) -> bool:
    """A .tsv name's stem is its @code, or its @code then "-" and a credit slug (with a number)."""
    stem, code = stem.casefold(), (code or "").casefold()
    if not code or not CODE_RE.match(code):
        return False
    if stem == code:
        return True
    rest = stem[len(code) + 1:] if stem.startswith(code + "-") else ""
    return bool(rest) and len(rest) <= SLUG_MAX + 6 and bool(_SLUG_RE.match(rest))


def slug_of(name: str) -> str:
    """The credit slug in a "<code>-<slug>.tsv" name ("" for "<code>.tsv" or another name)."""
    if not name.lower().endswith(DOCUMENTED_EXTENSION):
        return ""
    parts = name[: -len(DOCUMENTED_EXTENSION)].split("-")
    # The code is the first part and any following 2-8 letter subtags that look like a region/script.
    rest = parts[1:]
    while rest and (re.fullmatch(r"[A-Z]{2}|[A-Z][a-z]{3}|[0-9]{3}", rest[0])):
        rest = rest[1:]
    return "-".join(rest)


def is_translation_name(name: str) -> bool:
    """A file name the public folder (and the patcher) reads as a translation."""
    return (bool(_SAFE_NAME_RE.match(name)) and not name.startswith(".") and name == name.strip()
            and name.lower().endswith(EXTENSIONS) and ".." not in name)


def game_of_path(path: str) -> str:
    """The game of "translations/<game>/<file>", or raise NotATranslation."""
    parts = (path or "").split("/")
    if len(parts) != 3 or parts[0] != FOLDER or parts[1] not in GAMES:
        raise NotATranslation(f"{path}: only translations/fish/<code>.tsv and translations/plant/<code>.tsv files "
                              "can be added here.")
    if not is_translation_name(parts[2]):
        raise NotATranslation(f"{path}: a translation file is a plain-text {DOCUMENTED_EXTENSION} file named after "
                              f"its language code (like fr{DOCUMENTED_EXTENSION}); other files are refused.")
    return parts[1]


def precheck(path: str, data: bytes) -> str:
    """Refuse anything that is not a UTF-8 translation file of at most MAX_BYTES under
    translations/<game>/ (binaries, archives, scripts, other extensions). Returns the game."""
    game = game_of_path(path)
    if len(data) > MAX_BYTES:
        raise NotATranslation(f"{path}: the file is larger than {MAX_BYTES // 1024 // 1024} MB; a translation is "
                              "much smaller.")
    body = data[3:] if data.startswith(b"\xef\xbb\xbf") else data
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NotATranslation(f"{path}: the file is not UTF-8 text (byte {exc.start} could not be read). Save it as "
                              "UTF-8 and try again.") from None
    if "\x00" in text:
        raise NotATranslation(f"{path}: the file has NUL characters; it is not a text file.")
    return game


TEST_MARK = "(TEST)"


def is_test_translation(name: str, data: bytes) -> bool:
    """A "(TEST)" file, never shipped in the release (only in the public folder): its language or
    credit starts with "(TEST)" (the header: the main rule), or its file name contains "test"."""
    if "test" in name.lower():
        return True
    parsed = tfmt.parse_bytes(data[: MAX_BYTES + 1])
    return any(value.strip().upper().startswith(TEST_MARK)
               for value in (parsed.language, parsed.translator, parsed.value("@language")))


def blob_sha(data: bytes) -> str:
    """The git blob SHA-1 of some bytes (what GitHub's contents API calls "sha")."""
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Check:
    """The result of check_file: `ok` when the file can go into the public folder."""
    path: str
    ok: bool
    problems: list[str] = field(default_factory=list)   # why it is refused (line numbers)
    notes: list[str] = field(default_factory=list)      # warnings, coverage
    language: str = ""
    code: str = ""
    translator: str = ""


def check_file(path: str, data: bytes) -> Check:
    """Pre-check, then read the file as data and check it: format, game, keys, placeholders,
    person and number choices, email addresses (every refusal names its line)."""
    try:
        game = precheck(path, data)
    except NotATranslation as why:
        return Check(path, False, [str(why)])
    parsed = tfmt.parse_bytes(data, game)
    report = tfmt.validate(parsed)
    result = Check(path, True, language=parsed.language.strip(), code=parsed.value("@code").strip(),
                   translator=parsed.translator.strip() if not tfmt.contains_email(parsed.translator) else "")
    for problem in report.errors[:200]:          # a file that cannot be used at all is one of them
        result.problems.append(str(problem))
    if tfmt.contains_email(path):
        result.problems.append("The file name has an email address. " + tfmt.EMAIL_MESSAGE)
    if not parsed.fatal:
        if report.translated == 0:
            result.problems.append("The file has no translated line.")
        if not result.language:
            result.problems.append("The @language row (the language's own name) is missing.")
        name = path.rsplit("/", 1)[-1]
        if name.lower().endswith(DOCUMENTED_EXTENSION):
            stem = name[: -len(DOCUMENTED_EXTENSION)]
            if not name_fits_code(stem, result.code):
                result.problems.append(f"{name}: a {DOCUMENTED_EXTENSION} file is named after its language code "
                                       f"(the @code row says \"{result.code or '(none)'}\"), like "
                                       f"fr{DOCUMENTED_EXTENSION}, pt-BR{DOCUMENTED_EXTENSION} or, when that "
                                       f"language is already there, fr-your-name{DOCUMENTED_EXTENSION}.")
    result.notes.append(f"Coverage: {report.translated} of {report.total} lines translated.")
    result.notes.extend(str(p) for p in report.warnings[:50])
    result.ok = not result.problems
    return result
