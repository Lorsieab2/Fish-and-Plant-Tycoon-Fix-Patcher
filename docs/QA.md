# QA

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
