# Changelog

## v1.0.11

Golden Seahorse repurchase now works. It had four defects, not one.

- It targeted store item index 18, which is the Diver Ornament. The Golden
  Seahorse is index 11. Counting the 24-byte store name records from VA
  0x004578B4 gives 26 items, matching the `cmp edi, 0x19` bound on both store
  switches, with indices 0-7 the eight consumables the slots feature targets.
- The store-selection redirect resolved to VA 0x43F7FF, one byte before its
  wrapper at 0x43F800, landing on padding. Both it and the wrapper's internal
  branches are rebuilt against the correct addresses.
- The purchase-side hook at VA 0x004281BE was on the switch arm for the three
  research items, which the seahorse never reaches, and its wrapper ran off its
  own end into padding, crashing the game on any research item. Both patches
  are removed; those items are byte-identical to vanilla again.
- The section VirtualSize overlap was fixed in v1.0.9.

The setting now skips the single ownership gate at VA 0x004282B0 for item 11
only, and leaves every other item on its original path. It stays off by
default, as before. The three-setting build without it is byte-identical to the
output recorded in QA.md for v1.0.3.

Fish manifest is v1.2.6; every pinned hash and PE checksum regenerated.


## v1.0.10

- Every patch now carries an accurate technical note: the address it changes,
  the instruction or string before and after, and why. The notes are written
  into the patch log beside each change, so a run records what it did and not
  just which bytes moved.
- Rewrote the setting descriptions the patcher shows, so each one states what
  it repairs, how, and how many places it touches.
- Documented three defects in the Golden Seahorse repurchase setting, two of
  them still unfixed, in docs/golden-seahorse-defects.md. The setting is
  labelled as non-working in the patcher and stays off by default.
- Removed the install-location scanning added in v1.0.7. Finding games is back
  to choosing the parent folder that holds them, the way the Virtual Villagers
  patcher does it: Find Both in Parent Folder, or one button per game.
- The release ZIP now contains docs/golden-seahorse-defects.md, which the
  README and several patch notes link to, and tests check that every document
  referenced from the README or a patch note is actually packaged.


## v1.0.9

Fixes Fish Tycoon builds that Windows refused to start with "This app can't
run on your PC".

- The two Golden Seahorse patches set the `.text` section's VirtualSize to
  0x40000, the section's raw end offset, rather than a size. That pushed
  `.text` to RVA 0x41000, past `.rdata` at 0x40000, and the Windows loader
  rejects an image whose sections overlap. Corrected to 0x3F000, the value the
  slots patch already used and the largest that clears `.rdata`.
- Every combination that enabled Golden Seahorse was affected: 8 of the 16.
  Combinations without it were unaffected, and Plant Tycoon was never
  affected.
- No PE checksum patch covered the Golden Seahorse combinations, so those
  builds kept a checksum computed for different bytes. There is now exactly one
  checksum patch per combination, each recomputed.
- Recorded the target's PE section layout in the manifest, and added tests that
  walk every setting combination to check no section overruns the next one and
  that each combination has exactly one checksum patch. These run offline and
  need no copy of the game.
- Regenerated every pinned output hash. Fish manifest is now v1.2.5.

## v1.0.8

- Autodetect no longer searches Steam or GOG library folders. Only the free
  Windows downloads from LDW's own site are supported, and no other
  distribution has been checked against the pinned executable identities.
- Documented that supported rule in the README and How to Use, replacing the
  v1.0.7 wording that listed storefront paths among the searched locations and
  so implied those copies would work.
- Noted that autodetect only fills in a path, and that whatever it finds still
  has to pass the exact identity check.
- An unsupported executable is now refused with the supported download source
  instead of a bare size or hash mismatch, so a copy from elsewhere — wherever
  it was found — says what to do about it.

## v1.0.7

- Added an `Autodetect Games` button that searches the usual Windows install
  locations for the exact `Fish Tycoon.exe` and `Plant Tycoon.exe` and fills in
  the vanilla and modded folder fields for whatever it finds.
- Added a `Scan a Folder...` button that runs the same search, deeper, in one
  folder or drive you choose.
- The search skips Windows system folders and any existing `- Modded` folder,
  runs on a background thread with live progress, and stops at a folder and
  time budget so a slow or cloud-synced location cannot hang the patcher.
- When one game is found in more than one place, the patcher asks which install
  to use instead of guessing.
- Added `Defaults`, `Enable All`, and `Disable All` buttons to each game's
  patch list.
- Moved the per-game `Find [Game]...` buttons up beside the new autodetect
  controls, so they work on both tabs, and every action button is now locked
  while a scan, patch, or restore is running.
- The window body now scrolls, so nothing is squeezed on a shorter screen.
- The search revisits a folder reached again from a nearer root, so a game in
  the default Steam library is still found after its Program Files ancestor was
  walked first.
- README: documented the requirements, the game search, the output-folder
  naming under its own heading, and how to run the tests.

## v1.0.5

- Added separate `Find Fish Tycoon in Parent Folder...` and
  `Find Plant Tycoon in Parent Folder...` buttons to the Both Games tab,
  alongside the existing combined finder.
- The finder accepts one exact vanilla executable in the selected folder or
  one of its immediate subfolders and refuses missing or ambiguous matches.

## v1.0.4

- Renamed generated game folders to exactly `Fish Tycoon - Modded` and
  `Plant Tycoon - Modded`.
- Renamed generated executables to exactly `Fish Tycoon - Modded.exe` and
  `Plant Tycoon - Modded.exe` so each modified game uses its matching isolated
  save location.
- Added a remembered GUI option for choosing the parent location where the
  modified game folders are created.
- Removed the vanilla executable filename from each generated modded folder.

## v1.0.3

- Replaced both picture assets with the final transparent PNGs supplied by
  Lorsieab2.
- Added emoji-sized plant and fish pictures around the creator sentence.
- Surrounded the main patcher title with the plant and fish pictures.
- Added a paired plant-and-fish application icon to the native window title
  bar.

## v1.0.2

- Replaced the text emoji banner with the two exact fish and potted-plant
  pictures supplied by Lorsieab2.
- Removed the pictures' dark square backgrounds and preserved transparent PNG
  assets in the GUI and release package.

## v1.0.1

- Added the requested `🐟🪴` picture-style emoji banner.
- Added the exact creator description:
  `🪴 Created with Codex AI. Made with love by Lorsieab2 :) 🐟`

## v1.0.0

- Combined the current Fish Tycoon Fix Patcher v1.2.4 and Plant Tycoon Fix
  Patcher v1.0.0 engines and manifests.
- Added One Game and Both Games workflows modeled on the Virtual Villagers Fun
  Patcher.
- Added remembered, auto-filled vanilla/modded paths and clickable folder
  links.
- Preserved exact-build validation, guarded patches, pinned hashes, backups,
  restore, full-folder copying, readback verification, and original icon
  resources.
## v1.0.7

- Added an opt-in Golden Seahorse repurchase setting targeting store item
  index 18 and its two already-owned purchase gates.
