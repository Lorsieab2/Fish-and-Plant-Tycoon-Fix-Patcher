"""The executable pins' key set, shared by every pin script.

A manifest pins one executable SHA-256 per combination of settings the patcher can build
(`patched_sha256_by_settings`, keyed by the enabled settings' ids, sorted, comma-joined). The
key set follows from the settings' rules alone: every non-empty set of the settings that are
neither loader tails (they never change the executable: fish_patcher.pin_settings leaves them
out) nor asset merges (no executable effect), with each one's `requires_settings` on and no
`conflicts_settings` pair. The patcher refuses any other combination, so no other key is ever
looked up.

Each pin script updates the keys it derives and KEEPS every other pin: it never drops a key
(a script that dropped every key with its setting lost the combinations of the settings that
build on it -- pin_ds_store.py lost every Time Warp, Extra Tanks... key until their own scripts
ran again). finish() then keeps exactly the valid key set. After a change to a setting's
executable bytes, run the settings that build on it again (scripts/pin_vanilla_fixes.py lists
Fish Tycoon's order); a DLL-only change re-pins only its companion files.
"""

from __future__ import annotations

import itertools


def pinned_settings(manifest: dict) -> list[dict]:
    """The settings that take part in an executable pin's key."""
    return [s for s in manifest["settings"]
            if not (s.get("companion") or {}).get("loader_tail") and "asset_merge" not in s]


def valid_keys(manifest: dict) -> set[str]:
    settings = pinned_settings(manifest)
    ids = [s["id"] for s in settings]
    requires = {s["id"]: set(s.get("requires_settings", [])) for s in settings}
    conflicts = {s["id"]: set(s.get("conflicts_settings", [])) for s in settings}
    # settings nothing requires and that require nothing combine freely; the rest by their rules
    free = [i for i in ids if not requires[i] and not any(i in requires[j] for j in ids)
            and not conflicts[i]]
    bound = [i for i in ids if i not in free]
    groups = []
    for bits in itertools.product((0, 1), repeat=len(bound)):
        on = {i for i, b in zip(bound, bits) if b}
        if all(requires[i] <= on for i in on) and not any(conflicts[i] & on for i in on):
            groups.append(on)
    keys = set()
    for count in range(len(free) + 1):
        for combo in itertools.combinations(free, count):
            for group in groups:
                on = set(combo) | group
                if on:
                    keys.add(",".join(sorted(on)))
    return keys


def sources(manifest: dict, pins: dict[str, str], ids: set[str]) -> list[str]:
    """The pinned keys a script derives its setting's keys from: the valid keys with none of
    `ids` (the settings it pins), in the pins' order."""
    keep = valid_keys(manifest)
    return [k for k in pins if k in keep and not ids & set(k.split(","))]


def finish(manifest: dict, pins: dict[str, str]) -> dict[str, str]:
    """The pins to write: exactly the valid keys that have a pin, in the manifest's order."""
    keep = valid_keys(manifest)
    return dict(sorted(((k, v) for k, v in pins.items() if k in keep),
                       key=lambda kv: (len(kv[0].split(",")), kv[0])))
