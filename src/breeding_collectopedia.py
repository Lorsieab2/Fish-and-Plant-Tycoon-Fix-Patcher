"""The Breeding Guide's Collectopedia tab: a checklist of every species, each body x fin
(Fish Tycoon) or foliage x flower (Plant Tycoon), ticked where the save has ever obtained it.

The ticks are the guide's own "discovered" rule (breeding_guide.View): each species' own
discovered record in the save, and the patcher's DS Exclusive Fish / Unused Flowers species
from that setting's data file, only when that setting is on for the save. They are read
fresh, read only, every time the window reads the save, and the player cannot change them:
only the save decides.

With Show Spoilers off an unticked species is a locked "?" entry: never named, no
picture, and a part no discovered species has is "?" too (no name, no picture), exactly as
the guide's other spoiler-off views. With spoilers on everything is named.

Everything here is plain data (the window only draws it), so the tests check it without a
window.
"""

from __future__ import annotations

from breeding_guide import KIND_NAMES, KIND_TITLES, Sheet, filter_rows, setting_name

TAB_ID = "collectopedia"
TITLE = "Collectopedia"
LOCKED = "?"
FILTERS = (("all", "All"), ("collected", "Collected"), ("missing", "Missing"))
MODES = (("grid", "Grid"), ("list", "List"))
# The rarity words, lowest first (Fish: Common / Uncommon / Rare; Plant: the soil tiers 1-5).
TIER_ORDER = ("Common", "Uncommon", "Rare", "Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5")


def _plural(kind: str) -> str:
    return KIND_TITLES.get(kind, kind.title()).lower()


def _name(kind: str) -> str:
    return KIND_NAMES.get(kind, kind.title())


class Collectopedia:
    """The checklist for one View (one model, save and spoiler choice)."""

    def __init__(self, view) -> None:
        self.view = view
        self.model = view.model
        self.species = list(view.all_species)
        first = self.species[0]
        # Rows: bodies (Fish) or foliage (Plant), the species key's first part; columns: fins
        # or flowers, its second. Both in the game's own order.
        self.row_kind, self.col_kind = first.parts[0].kind, first.parts[1].kind
        self.rows = self.model.parts(self.row_kind)
        self.cols = self.model.parts(self.col_kind)
        self.by_key = {tuple(s.key): s for s in self.species}

    # ---- what may be shown
    @property
    def spoilers(self) -> bool:
        return self.view.spoilers

    def ticked(self, key) -> bool:
        return tuple(key) in self.view.discovered

    def part_label(self, part) -> str:
        """A part's name, or "?" when spoilers are off and no discovered species has it."""
        name = self.view.part_name(part.kind, part.index)
        return name if name is not None else LOCKED

    def part_known(self, part) -> bool:
        return self.view.part_name(part.kind, part.index) is not None

    def named(self, key) -> bool:
        """A species is named (and pictured) when ticked, or with spoilers on."""
        return self.spoilers or self.ticked(key)

    def species_label(self, key) -> str:
        return self.by_key[tuple(key)].name if self.named(key) else LOCKED

    def rarity_label(self, key) -> str:
        """The species' rarity word; spoilers off and not collected, only when both its parts
        are discovered (a species is as rare as its rarer part, so that tells nothing new)."""
        s = self.by_key[tuple(key)]
        if self.named(key) or all(self.part_known(p) for p in s.parts):
            return s.rarity
        return LOCKED

    def tooltip(self, key) -> str:
        s = self.by_key[tuple(key)]
        parts = ", ".join(f"{self.part_label(p)} {p.kind}" for p in (s.parts[1], s.parts[0]))
        if self.named(key):
            state = "collected" if self.ticked(key) else "not collected yet"
            patcher = f"; {setting_name(self.model.game)}" if s.patcher else ""
            return f"{s.name} ({parts}): {s.rarity}{patcher}; {state}."
        return f"Not collected yet ({parts})."

    # ---- counts
    def collected(self) -> tuple[int, int]:
        return sum(self.ticked(s.key) for s in self.species), len(self.species)

    def tiers(self) -> list[tuple[str, int, int]]:
        """(rarity word, collected, all) per rarity tier, lowest first."""
        counts: dict[str, list[int]] = {}
        for s in self.species:
            entry = counts.setdefault(s.rarity, [0, 0])
            entry[0] += self.ticked(s.key)
            entry[1] += 1
        order = [t for t in TIER_ORDER if t in counts] + sorted(t for t in counts if t not in TIER_ORDER)
        return [(t, counts[t][0], counts[t][1]) for t in order]

    def part_counts(self, kind: str) -> list[tuple[object, int, int]]:
        """(part, collected, all) for every part of a kind: the species with that part."""
        slot = 0 if kind == self.row_kind else 1
        out = []
        for part in self.model.parts(kind):
            having = [s for s in self.species if s.parts[slot].index == part.index]
            out.append((part, sum(self.ticked(s.key) for s in having), len(having)))
        return out

    def part_progress(self, kind: str) -> list[str]:
        """"Fin Silky: 12 of 28 bodies" for each part a player may see; with spoilers off the
        undiscovered ones are one line, unnamed (none of their species is collected)."""
        other = _plural(self.col_kind if kind == self.row_kind else self.row_kind)
        lines, hidden, hidden_total = [], 0, 0
        for part, got, total in self.part_counts(kind):
            if not self.part_known(part):
                hidden += 1
                hidden_total += total
                continue
            lines.append(f"{_name(kind)} {part.name}: {got} of {total} {other}")
        if hidden:
            lines.append(f"{hidden} undiscovered {_plural(kind)}: 0 of {hidden_total} species")
        return lines

    def summary(self) -> str:
        got, total = self.collected()
        if not self.view.has_save:
            return f"No save chosen: 0 of {total} species collected."
        percent = 100 * got / total if total else 0.0
        text = f"{got} of {total} species collected ({percent:.1f}%)"
        patcher = [s for s in self.species if s.patcher]
        if patcher:
            text += (f", {len(patcher)} of them {setting_name(self.model.game)} "
                     f"({sum(self.ticked(s.key) for s in patcher)} collected)")
        return text + "."

    def tier_text(self) -> str:
        return "By rarity: " + "; ".join(f"{t} {got} of {total}" for t, got, total in self.tiers()) + "."

    # ---- the list
    def columns(self) -> list[str]:
        return ["Species", _name(self.row_kind), _name(self.col_kind), "Rarity", "Collected", "Patcher"]

    def row(self, key) -> list:
        s = self.by_key[tuple(key)]
        named = self.named(key)
        patcher = setting_name(self.model.game) if s.patcher and named else ""
        return [self.species_label(key), self.part_label(s.parts[0]), self.part_label(s.parts[1]),
                self.rarity_label(key), "Yes" if self.ticked(key) else "No", patcher]

    def keep(self, key, which: str) -> bool:
        if which == "collected":
            return self.ticked(key)
        if which == "missing":
            return not self.ticked(key)
        return True

    def sheet(self, which: str = "all") -> Sheet:
        """The sortable list (and what Export writes): every species, or only the collected
        or the missing ones; the locked ones as "?"."""
        rows, tags, keys, details = [], [], [], []
        for s in self.species:
            if not self.keep(s.key, which):
                continue
            rows.append(self.row(s.key))
            tag = ()
            if s.patcher and self.named(s.key):
                tag += ("patcher",)
            if not self.ticked(s.key):
                tag += ("undiscovered",)
            tags.append(tag)
            keys.append(tuple(s.key))
            details.append(self.tooltip(s.key))
        sheet = Sheet(TITLE, self.columns(), rows, kinds=["text"] * 6, tags=tags, keys=keys, details=details)
        sheet.header = self.summary() + " " + self.tier_text()
        sheet.intro = self.intro()
        if not rows:
            sheet.message = {"collected": "Nothing collected in this save yet.",
                             "missing": "Every species is collected."}.get(which, "")
        return sheet

    def intro(self) -> str:
        return "\n".join([self.summary(), self.tier_text(), ""]
                         + self.part_progress(self.row_kind) + [""] + self.part_progress(self.col_kind))

    def matching(self, sheet: Sheet, search: str) -> set:
        """The keys of the sheet's rows a search matches (on what the list shows)."""
        return {sheet.keys[i] for i in filter_rows(sheet, search)}

    def texts(self) -> list[str]:
        """Every text the tab can show, for the no-leak tests."""
        out = [TITLE, self.summary(), self.tier_text(), self.intro()]
        out += [label for _v, label in FILTERS + MODES]
        for which, _label in FILTERS:
            sheet = self.sheet(which)
            out += [sheet.header, sheet.message] + list(sheet.columns)
            out += [str(c) for row in sheet.rows for c in row] + list(sheet.details)
        out += [self.part_label(p) for p in self.rows + self.cols]
        out += [self.tooltip(s.key) for s in self.species]
        for kind in (self.row_kind, self.col_kind):
            out += self.part_progress(kind)
        return out
