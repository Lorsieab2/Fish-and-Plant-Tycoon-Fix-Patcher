# The Game Mechanics window

Tools tab → **Game Mechanics...** (the **?** beside it explains it). It is a
read-only page "for the curious": how Fish Tycoon and Plant Tycoon really
work underneath, worked out from each game's code. It reads nothing but the
patcher's own manifests and never opens or writes a save or game file, so a
game can stay open while it is shown.

## Layout

- One tab per game.
- At the top of each tab, links to its groups, 4 per row, then one
  scrolling page.
- Each group is a bold heading with bullets; sub-facts are indented under
  their bullet.
- Text is Segoe UI 10, headings Segoe UI 12 bold, and labels Segoe UI 9
  bold.
- Close, or Escape, closes the window, and only one is open at a time.
- `python src/game_mechanics.py [fish|plant]` prints the same page as plain
  text for review.

## Rules for every line

These are shared with the Virtual Villagers and Virtual Families patchers.

- **Labels.** Each bullet starts with one:
  - **VERIFIED-E** (green): the game's code was run (emulated), and its odds
    were counted exactly;
  - **VERIFIED-C** (blue): read in the game's code, on a path the running
    game takes;
  - **UNCONFIRMED** (red): an estimate, dead code, or not shown either way.
    It is dropped once a fact is proven in the running game, by live code,
    or by the owner's word.
- **Exact numbers.** Both games roll `Random(n)` = the C runtime's
  `rand() % n`, where `rand()` takes each value 0-32767 equally often. A
  chance is shown as the game's own test with its exact odds, counted over
  those 32768 values (`game_mechanics.chance`). For example,
  `Random(100) <= 40` is 41.04%, `Random(100) < 50` is 50.05%, and
  `Random(10000) < 10` is 0.12%. No vague wording.
- **Units.** Every time says whether it is real-life or in-game, and at
  which speed. Each tab opens with a "Time and units" note.
- **Real effects.** Facts describe what the code does, not what the game's
  text claims: for example the swapped Plant of Incubation / Nutrition
  labels, and the Crimson Comet's cure that never fires. Things that cannot
  happen are not listed. Stock bugs are described, not fixed.
- **Patches.** The unpatched game comes first. Where a setting of this
  patcher changes a fact, a "With the patcher (<setting>, on/off by
  default): ..." line follows it. Setting names and defaults are read from
  the manifest, so a setting this build does not have is not mentioned.

## Files

- `src/game_mechanics.py`: the fact model (`Fact`, `Group`, `GamePage`), the
  labels, the exact odds, and the text renderer.
- `src/game_mechanics_fish.py`, `src/game_mechanics_plant.py`: each game's
  facts.
- `src/game_mechanics_window.py`: the Tk window.
- `tests/test_game_mechanics.py` checks:
  - the odds, and that every chance printed matches its test;
  - that every bullet has a label;
  - that no vague wording appears;
  - that patched lines name real settings;
  - that the window writes nothing.
