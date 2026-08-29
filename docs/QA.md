# QA

## v1.0.14

- Combined unit tests: 36 passed, including seven covering the new detail view.
- Expanding every disclosure in the running GUI grows the scroll region from
  1480 to 3303 pixels with no errors, and collapsing restores it.
- Detail coverage checked against the manifest: the set of offsets shown for a
  setting equals the set it installs, checksum records excluded.
- Virtual addresses spot-checked against the documented ones: plant 0x42E23B,
  fish 0x4204CE and 0x401E11.
- Each location is listed once: Unknown Chemical shows 3, universal slots 14,
  matching their distinct offsets rather than their manifest entry counts.
- Breaking the grouping makes the new guards fail; restoring it passes.


## v1.0.13

- Combined unit tests: 29 passed, including two new drift guards.
- Reverting the technical-details heading to v1.2.6 makes the new guard fail;
  restoring it passes.
- Audited every bot finding across all nine pull requests: 7 findings, all
  answered on their threads and all fixed in code.
- Version consistency across build_release, CHANGELOG, QA and both manifests:
  passed.
- Every tag now has a release behind it.


## v1.0.12

- Combined unit tests: 27 passed.
- Golden Seahorse verified in game on the exact stock build: the store panel
  shows the price, the purchase charges, and the seahorse appears in the first
  free tank.
- Ownership address derived from live values and confirmed three ways: Fish
  Food Research at state + 23*20 + 0x78, Environment and Advertising Research
  at the next two slots, and Money at state + 0x38C matching the disassembly.
- All 16 setting combinations: no section overruns another, every PE checksum
  matches its bytes, every pinned hash matches.
- With the setting off, all three wrapper regions are untouched zero padding.
- Three-setting build without the seahorse still reproduces SHA-256
  E0EE1A85668D39A4A2D9A2E20A702E6A65465B34EE1AAE960EDF1D33CF32E75A.
- Save path traced in both executables and confirmed against a real
  installation: Documents/LDW/<game name>/<exe name><slot>.ldw.

## v1.0.11

- Combined unit tests: 24 passed.
- Store item index for the Golden Seahorse derived independently from the name
  table and cross-checked against both store switches: index 11.
- All 16 setting combinations: no section overruns another, every PE checksum
  matches its bytes, every pinned hash matches.
- Patched redirect resolves to VA 0x43F800 exactly; the wrapper disassembles to
  the intended six instructions.
- With Golden Seahorse off, the wrapper region is untouched zero padding, and
  VA 0x004281BE is byte-identical to vanilla.
- Three-setting build without Golden Seahorse still reproduces SHA-256
  E0EE1A85668D39A4A2D9A2E20A702E6A65465B34EE1AAE960EDF1D33CF32E75A.
- Control-flow audit of every patch that installs code: each branch inside an
  installed region lands on a boundary of that region, and all 14 external
  targets are boundaries in the original code (0x422440 and 0x427540 are
  function entries preceded by 0xCC padding).
- Crimson Comet, Unknown Chemical and the Plant old-age patch verified by
  disassembly, including the signedness of the Plant compare.
- Upgrading over a folder written by an earlier manifest revision now succeeds;
  a foreign, empty or missing marker is still refused.
- In-game confirmation of the repurchase: pending.


## v1.0.10

- Combined unit tests: 20 passed (the 10 scanning tests were removed with the
  scanning code).
- Every jump and call installed by every Fish patch traced to its target: all
  land on their intended wrapper except the two Golden Seahorse defects
  recorded in docs/golden-seahorse-defects.md.
- Crimson Comet wrapper decoded and confirmed: push 100, call the RNG helper at
  VA 0x403240, cure on rolls 0-19.
- All 43 patch notes and all 5 setting descriptions checked against the bytes
  they describe.
- Patch notes appear in the run log: passed.
- GUI finder buttons fill both path fields and lock while busy: passed.
- Release packaging guards: removing the defects document from the ZIP file
  list makes both link tests fail, and restoring it makes them pass.
- Three-patch Fish build (no Golden Seahorse) reproduces SHA-256
  E0EE1A85668D39A4A2D9A2E20A702E6A65465B34EE1AAE960EDF1D33CF32E75A, the output
  recorded in this log for v1.0.3.


## v1.0.9

- Combined unit tests: 30 passed.
- All 16 Fish setting combinations rebuilt from the exact stock executable:
  no section overruns the next, every PE checksum matches its bytes, and every
  pinned hash matches: passed.
- Reintroducing the 0x40000 VirtualSize made the new layout test fail with
  ".text ends at 0x41000, past .rdata at 0x40000": passed (the guard works).
- Plant Tycoon, both combinations: unaffected, layout clean.
- A no-setting run still reproduces the vanilla bytes exactly: passed.
- Player confirmation that the rebuilt all-patches Fish Tycoon launches:
  PENDING.

## v1.0.8

- Combined unit tests: 27 passed.
- Unsupported build refused by both engines with the ldw.com source named in
  the error: passed.
- No storefront library path appears in the search roots or the patcher source:
  passed.
- Nested search root below an already-walked ancestor, now written against a
  generic layout: passed.
- Search roots reduced to the locations an LDW download or installer uses:
  passed.

## v1.0.7

- Python syntax compilation: passed.
- Combined unit tests: 25 passed, including 10 new game-search and GUI cases.
- Nested search root below an already-walked ancestor (default Steam library):
  found, after the depth-tracking fix from the Codex review.
- Game search matches only the exact vanilla executable names: passed.
- Game search skips existing `- Modded` folders: passed.
- Game search depth limit, folder budget, progress callback, and missing-root
  handling: passed.
- Threaded autodetect through the real GUI against a synthetic install tree:
  both folder fields filled in, action buttons locked and released: passed.
- Patch preset buttons (Defaults, Enable All, Disable All): passed.
- Scrollable window body: scroll region exceeds the window height: passed.
- Patch engines, manifests, and pinned hashes: unchanged.

## v1.0.3

- Python syntax compilation: passed.
- Combined unit tests: passed.
- Exact Fish Tycoon stock fixture dry run and apply: passed.
- Exact Plant Tycoon stock fixture dry run and apply: passed.
- Fish output SHA-256:
  `E0EE1A85668D39A4A2D9A2E20A702E6A65465B34EE1AAE960EDF1D33CF32E75A`.
- Plant output SHA-256:
  `BFF2115EDB34284E63B04363CC5E6FBDF4845DA489F8E98292C505CA5CD4C046`.
- Non-EXE asset copy checks: passed for both game folders.
- Resource/icon preservation flags: passed for both engines.
- GUI initialization and separate remembered-path state: passed.
- Fish backup restore returned the exact stock executable SHA-256:
  `9F15F13537AD0978D1E3AA2F94A64992FB7D968648BF265810087BDC88EDBDCD`.
- Plant backup restore returned the exact stock executable SHA-256:
  `D1F83E3E3CAFE177452E2F8B6AF4B68CACED783B77A304370389375DB611D6F9`.
- Restored release ZIP CRC/content check: passed.
- Release package contains no EXE: passed.
- Exact creator description: present.
- Supplied fish and potted-plant artwork: packaged as separate transparent PNG
  files and loaded by the GUI instead of text emoji.
- Transparent image alpha/corner checks: passed for both PNG files.
- Creator line uses emoji-sized supplied PNGs instead of text emoji: passed.
- Main heading is surrounded by the supplied plant and fish PNGs: passed.
- Native title-bar icon contains both supplied pictures: passed.
