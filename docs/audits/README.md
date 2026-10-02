# Audit reports

Reports from audits of the patcher. They are records of what was checked, how,
and what was found at the time; later releases may change the code they
describe. They are not shipped in the release ZIP.

| Date | Report | Scope |
|---|---|---|
| 2026-09-29/30 | [Full audit and v1.0.16 release](2026-09-30-full-audit-and-v1.0.16-release.md) | Every patch in both games, the patcher (GUI, defaults, apply/overwrite, restore, packaging), the seven fixes, and the v1.0.16 release verification |
| 2026-09-29 | [Universal supply slots payload audit](2026-09-29-universal-slots-payload-audit.md) | Line-by-line check of the 961-byte Fish Tycoon universal-slots payload and its hooks, with emulation |

Evidence levels used throughout:

- **STATIC**: disassembly and cross-reference reasoning.
- **EMU**: the game's own code run under unicorn emulation.
- **LOADER**: the patched executable run under a debugger to the Windows
  loader breakpoint (image mapped, imports linked, game code not yet run) and
  its bytes read from live memory.
- **RUNTIME**: the game actually running.
- **OWNER**: the owner's own saves or play.

A claim about what players see that rests only on STATIC evidence is labelled
unverified: code in the stock games can be developer-dead.
