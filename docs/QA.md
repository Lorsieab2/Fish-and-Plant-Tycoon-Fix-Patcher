# v1.0.3 QA

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
