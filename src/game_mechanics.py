"""Game Mechanics: how Fish Tycoon and Plant Tycoon really work underneath.

A read-only page "for the curious", worked out from each game's own code.
It never opens or writes a save or game file, so it can stay open while a
game runs. Each game's facts live in their own module
(game_mechanics_fish.py, game_mechanics_plant.py); this one holds the fact
model, the labels, the exact odds of the games' random rolls and the plain
text renderer. The window is game_mechanics_window.py.

    python src/game_mechanics.py            prints the whole page
    python src/game_mechanics.py fish       one game

Rules every fact follows (the owner's, shared with the Virtual Villagers
and Virtual Families patchers):

- Every bullet carries a label:
  - VERIFIED-E: the game's code was run (emulated) and counted exactly;
  - VERIFIED-C: read on a code path the running game takes;
  - UNCONFIRMED: an estimate, dead code or not proven either way.
- Exact numbers, never vague wording. A chance is the game's own test and
  its exact odds.
- Times say whether they are real-life or in-game, and at which speed.
- The page describes the real effect, not what the game's text claims.
- The unpatched game comes first. A setting that changes a fact gets a
  "With the patcher" line on that fact only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

LABELS = {
    "E": "VERIFIED-E",
    "C": "VERIFIED-C",
    "U": "UNCONFIRMED",
}
LABEL_HELP = (
    "VERIFIED-E: the game's code was run (emulated) with the values the game gives it, and the "
    "odds were counted exactly. VERIFIED-C: read in the game's code, on a path the running game "
    "takes. UNCONFIRMED: an estimate, dead code, or not yet shown either way."
)

RAND_PERIOD = 32768        # MSVC rand(): 0..32767, each value equally often over its period


def rand_count(n: int, k: int) -> int:
    """How many rand() values make `rand() % n < k` (both games' Random(n))."""
    if n <= 1:
        return RAND_PERIOD if k > 0 else 0          # Random(0) and Random(1) are always 0
    k = max(0, min(k, n))
    full, extra = divmod(RAND_PERIOD, n)
    return full * k + min(k, extra)


def chance(n: int, k: int) -> str:
    """The exact chance that Random(n) < k, as the page prints it (e.g. 41.04%)."""
    value = 100 * rand_count(n, k) / RAND_PERIOD
    text = f"{value:.2f}%"
    if text in ("0.00%", "100.00%") and 0 < rand_count(n, k) < RAND_PERIOD:
        text = f"{value:.4f}%"
    return text


def below(n: int, k: int) -> str:
    """`Random(n) < k` and its exact chance."""
    return f"Random({n}) < {k} ({chance(n, k)})"


def at_least(n: int, k: int) -> str:
    """`Random(n) >= k` and its exact chance."""
    value = 100 * (RAND_PERIOD - rand_count(n, k)) / RAND_PERIOD
    return f"Random({n}) >= {k} ({value:.2f}%)"


def at_most(n: int, m: int) -> str:
    """`Random(n) <= m` and its exact chance."""
    return f"Random({n}) <= {m} ({chance(n, m + 1)})"


@dataclass(frozen=True)
class Fact:
    text: str
    label: str = "C"
    subs: tuple[str, ...] = ()
    # (setting id, what that setting changes): rendered as "With the patcher
    # (<name>, on/off by default): <text>", only for settings the manifest has.
    patched: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.label not in LABELS:
            raise ValueError(f"unknown label {self.label!r}")


@dataclass(frozen=True)
class Group:
    title: str
    facts: tuple[Fact, ...]
    note: str = ""


@dataclass(frozen=True)
class GamePage:
    game_id: str
    title: str
    intro: str
    time_and_units: str
    groups: tuple[Group, ...] = field(default_factory=tuple)


def manifest_settings(game_id: str) -> dict[str, dict]:
    path = ROOT / "data" / f"{game_id}_manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {s["id"]: s for s in manifest.get("settings", []) if isinstance(s, dict) and "id" in s}


def patched_line(game_id: str, setting_id: str, text: str, settings: dict[str, dict] | None = None) -> str | None:
    settings = manifest_settings(game_id) if settings is None else settings
    setting = settings.get(setting_id)
    if setting is None:
        return None
    default = "on by default" if setting.get("default") else "off by default"
    return f"With the patcher ({setting.get('name', setting_id)}, {default}): {text}"


def load_page(game_id: str) -> GamePage:
    if game_id == "fish":
        import game_mechanics_fish as module
    elif game_id == "plant":
        import game_mechanics_plant as module
    else:
        raise ValueError(game_id)
    return module.page()


GAMES = ("fish", "plant")


def render_lines(page: GamePage) -> list[tuple[str, str]]:
    """The page as (style, text) lines: heading, text, bullet, sub, patched."""
    settings = manifest_settings(page.game_id)
    lines: list[tuple[str, str]] = [("title", page.title), ("text", page.intro), ("text", LABEL_HELP),
                                    ("heading", "Time and units"), ("text", page.time_and_units)]
    for group in page.groups:
        lines.append(("heading", group.title))
        if group.note:
            lines.append(("text", group.note))
        for fact in group.facts:
            lines.append(("bullet", f"[{LABELS[fact.label]}] {fact.text}"))
            for sub in fact.subs:
                lines.append(("sub", sub))
            for setting_id, text in fact.patched:
                line = patched_line(page.game_id, setting_id, text, settings)
                if line:
                    lines.append(("patched", line))
    return lines


def render_text(page: GamePage) -> str:
    out: list[str] = []
    for style, text in render_lines(page):
        if style == "title":
            out += [text, "=" * len(text), ""]
        elif style == "heading":
            out += ["", text, "-" * len(text)]
        elif style == "text":
            out += [text, ""]
        elif style == "bullet":
            out.append(f"- {text}")
        else:
            out.append(f"    - {text}")
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str]) -> int:
    games = argv[1:] or list(GAMES)
    for game_id in games:
        sys.stdout.write(render_text(load_page(game_id)))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main(sys.argv))
