"""The owner's "cheat" label for settings that are plainly cheats (Everything is
Free): a setting definition with ``"cheat": true``.

Such a setting is off by default ("Defaults" leaves it off), "Enable All"
leaves it off too (it is turned on only by ticking it by hand), and the
patcher shows CHEAT beside its name, styled as the EXPERIMENTAL label
(src/experimental.py). The pin scripts build their setting definitions through
``mark`` so the manifests carry the flag; the GUI reads it through
``is_cheat`` and ``in_enable_all``.
"""

from __future__ import annotations

from typing import Any, Mapping

FLAG = "cheat"
LABEL = "CHEAT"


def is_cheat(setting: Mapping[str, Any]) -> bool:
    return bool(setting.get(FLAG, False))


def in_enable_all(setting: Mapping[str, Any]) -> bool:
    """Whether "Enable All" turns this setting on: every setting but a cheat."""
    return not is_cheat(setting)


def mark(setting: dict[str, Any]) -> dict[str, Any]:
    """A setting definition made a cheat: off by default, the flag right after "default"."""
    marked: dict[str, Any] = {}
    for key, value in setting.items():
        if key == FLAG:
            continue
        marked[key] = value
        if key == "default":
            marked[key] = False
            marked[FLAG] = True
    if FLAG not in marked:
        marked["default"] = False
        marked[FLAG] = True
    return marked
