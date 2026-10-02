# Full audit and v1.0.16 release (2026-09-29/30)

- **Audited:** `main` at `a069e8c` (v1.0.15 + 4 commits).
- **Released:** v1.0.16 at `main` `94e7682a3d7b5cbe14fcf8a5e8109a270b3c99f2`.
- **Supported executables:**
  - `Fish Tycoon.exe` SHA-256 `9F15F135…BDCD`
  - `Plant Tycoon.exe` SHA-256 `D1F83E3E…D6F9`

  These are the free LDW downloads.

## 1. Summary

Every patch in the catalog does what its description says:

- All 5 settings were traced in the real game code.
- All 20 setting combinations were applied to the supported LDW executables. Each one reproduces its pinned SHA-256 and has a valid PE checksum.
- Each combination passes the full Windows loader with its patch bytes present in live memory.

The defects were in the patcher around the patches (apply/overwrite, read-only files, the GUI) and in texts and documentation. Seven defects were found and fixed, each in its own pull request. Each fix was checked against the real games, Codex-reviewed, merged, and shipped in v1.0.16.

| PR | Fix | Codex |
|---|---|---|
| #16 | Refuse an unrecognized output folder before writing anything | +1 |
| #17 | Fish engine enforces its pinned resource section | +1 |
| #18 | Patch games whose files are read-only | P2 fixed, then +1 |
| #19 | Warn that switching universal slots mid-save changes item uses | P1 and P2 fixed (two-round limit) |
| #20 | Correct the German Unknown Chemical store text too (see the correction in 4.5) | +1 |
| #21 | Keep the GUI usable when its settings file cannot be written | Two P2s fixed (two-round limit) |
| #22 | Correct where the games keep their saves | +1 |
| #23 | Release v1.0.16 (version bump, CHANGELOG, QA) | +1 |

All eight are merged (squash). CI was green on every head.

**Release:** [v1.0.16](https://github.com/Lorsieab2/Fish-and-Plant-Tycoon-Fix-Patcher/releases/tag/v1.0.16), marked Latest.

- Asset `Fish-and-Plant-Tycoon-Fix-Patcher-v1.0.16.zip`, SHA-256 `4234281DEB4565EF9992BE730CEDF9F1F8963C6E0EA2FB21AFC6EEB9547F4E9E`.
- The built, verified, uploaded and freshly downloaded copies are identical.

## 2. Safety of the owner's files

- **Saves** (the owner's `Documents\LDW`) were only listed and read. Before and after every run that launched game code, a full snapshot of the folder (1,251 files: names, sizes and modification times) was compared. They were identical every time.
- **Vanilla executables:** all of the owner's vanilla copies still match their pinned SHA-256. All patching and testing used temporary copies.
- **Processes:** every process started for testing was terminated and its handles closed.

## 3. Per-patch verification

### Fish Tycoon

**[PASS] Crimson Comet 20% curing fix** (STATIC + LOADER)
- Vanilla `0x4204CE` calls the RNG `0x403240` with bound 0. It returns 0, so a fish is never cured.
- The 14-byte wrapper at `0x401E11`, in CC padding, does `push 100 / call RNG / pop ecx / cmp al,20 / setb al / ret`. It returns 0 or 1 into the original `test eax,eax`: a true 20% roll.
- Statically, it sits in the per-fish growth-step loop. Its in-play frequency was not observed at runtime.

**[PASS] Unknown Chemical: 3 uses** (STATIC + LOADER)
- The vanilla purchase writer `0x427540` gives every item a count of 3 (`0x42759F`).
- The reset to 1 at `0x4210B7` sits only on store item 4's branch (Unknown Chemical). Removing it gives 3 uses, and the other chemicals are unaffected.
- The English store text is corrected. For the German text, see 4.5.

**[PASS] Universal supply slots 2-4** (STATIC + EMU + LOADER)
- **Structure:** a 961-byte payload, 5 redirected sites (store purchase `0x428133`, item use `0x420B70`, and the three egg clears `0x4213A7`, `0x421476` and `0x421549`) and 6 prompt strings. All 58 branch targets land on instruction boundaries, nothing jumps into replaced bytes, and the state at every rejoin point is correct.
- **Buying, emulated:**
  - The Buy confirmation appears first, and No changes nothing.
  - The search goes stack in slot 2 → 3 → 4, then the first empty slot, then the replace prompts.
  - Money is deducted once.
  - Store items 8+ behave exactly as vanilla.
- **Using, emulated:** the swap trampoline runs the right handler from any slot and always restores the record.
- **Egg decrement:** clears the same 5 fields as the original, only at zero.
- Details are in the [payload audit](2026-09-29-universal-slots-payload-audit.md). For the save-compatibility effect, see 4.4.

**[PASS] Buy Multiple Golden Seahorses** (STATIC + LOADER)
- The three blocks at `0x4282B2`, `0x427B66` and `0x42735C` are each wrapped. Item 11 takes the buy path, and every other item re-runs the original instructions.
- The repository's history records a runtime watch that confirmed the click handler is the live path.

**[PASS] Section layout and checksums** (LOADER)
- `.text` VirtualSize is extended to `0x3F000` in the 12 combinations that enable Universal Slots or Golden Seahorse, which need the extra code space. The other 4 combinations keep the vanilla `0x3E29F`. Every image, of all 16, loads.
- As a negative control, the v1.0.6–v1.0.8 overlapping image is rejected by the Windows loader. This proves the check really detects that defect.

### Plant Tycoon

**[PASS] No old-age plant deaths** (STATIC + LOADER)
- The 1720.0 threshold has one reference (`0x42E21F`).
- The `Random(1000)` operand at `0x42E23B` changes from 9 to −1 under a signed `jg`, so the old-age kill becomes unreachable.
- The function's other health-zero write is the dead-plant handling, and its other age check is a neglect penalty.

**[PASS] Add Missing Assets to LDW Version** (end to end on the real game folder)
- All 316 pinned entries were checked. Added files match their pins, and the game's own files are kept.

## 4. Defects found and fixed

### 4.1 Both Games wrote one game, then failed on the other (#16)

- **Evidence (real exes):** with an unrelated `Plant Tycoon - Modded` folder present, the dry run passed. Patch Both then wrote Fish Tycoon and only then failed on Plant Tycoon, leaving an orphaned backup.
- **Fix:** the check now runs in the preflight and dry run, before any backup is made. A failed final swap restores the previous modded folder.
- **Tests:** 4 new tests (7 subtests), all of which fail on the old engines.

### 4.2 Fish engine ignored its own `.rsrc` pin (#17)

The README promised the check and the manifest pinned it, but only the Plant engine read the pin. The fix ports the check and corrects the README's test claims.

**Dead-code note:** after the whole-file SHA-256 match, this check can never fail with a correct manifest. It only catches a manifest whose pins contradict each other. The same is true of Plant's original check and of both engines' PE-field checks. They were left in place and are flagged here.

### 4.3 Patching failed with read-only game files (#18)

- **Evidence (read-only copies of the real exes):** patching failed with `[WinError 5] Access is denied` and left a `.<game> - Modded.staging-*` folder on every attempt. Restore failed the same way.
- **Fix:** the staging copy is made writable (the vanilla folder is never touched), and cleanup and restore now handle read-only files.
- **Tests:** 6 subtests, all of which fail on the old engines.

### 4.4 Switching Universal Slots mid-save changes item uses (#19)

**Evidence:** STATIC + EMU; not observed in play.

The base game gives every purchase a count of 3, then discards the item after one use. The setting counts uses down instead. Saves keep the counts, and a re-patched copy keeps its saves. So:

- An egg or Unknown Chemical bought with the setting off gives 3 uses once it is on.
- Turning the setting off wipes stacked eggs in one hatch, and can leave an item outside its own slot unusable.

This can't be fixed in the executable, because a leftover record is identical to a genuine stack. The fix is a player-facing warning ("use up slots 2-4 before switching"), shown in both tabs.

### 4.5 German Unknown Chemical text (#20) — correction: developer-dead data

**The change:** `Reicht für eine Behandlung.` → `Reicht für 3 Behandlungen.` at file `0x45854`, in the same 28 bytes. The 8 affected pins were recomputed from the real exe. When the game's own string lookup (`0x426FD0`) is emulated on the patched build with its language flag set to German, it returns the corrected text.

**Correction, after the owner's developer-dead-code warning:** the German text appears never to be shown in the LDW build.

- **RUNTIME:**
  - The stock game was run under a debugger from a fresh start to its menus.
  - "Documents" was redirected to a sandbox, and the file APIs were guarded so the game would be killed before it could touch the owner's Documents or OneDrive.
  - Every string lookup used language = 0 (English).
- **STATIC:**
  - The executable has no `German`, `Deutsch` or `Language` string.
  - It imports no Windows locale-language API. `GetLocaleInfoA` there is only the C runtime's code-page query.
  - No game-code write that sets the flag was found.
- **Not excluded:** a data file or command-line switch that sets German. Nothing found suggests one exists.

The shipped technical doc's claim that "German players were still told one dose" is therefore **unsupported**. The patch itself is harmless. **Owner decision:** "don't worry about it". It was left as shipped.

### 4.6 GUI stuck when its settings file cannot be written (#21)

- **Evidence (real GUI):** the window could not be closed, patching never started, and nothing was shown.
- **Fix:** a failed save no longer blocks anything. The failure is written once to the log, and closing the window warns about it.

### 4.7 The docs had the save location backwards (#22)

**Evidence:**
- **OWNER:** the modded builds wrote `Documents\LDW\Fish Tycoon - Modded\Fish Tycoon0/1.ldw` (and the same for Plant Tycoon).
- **RUNTIME:** the sandboxed run created `LDW\<exe name>\Fish Tycoon0..5.ldw`.
- **STATIC:** the save routine (`0x402BB0`) takes the folder name from `GetModuleFileNameA`.

**Fix:** the README and How to Use now give `Documents\LDW\<exe name>\<game name><number>.ldw`. A guard test was added.

## 5. Integration, build and release verification

- **Before merging:** every pair of branches merged cleanly (`git merge-tree`). A local branch with all seven fixes merged passed 60 tests and every real-exe check.
- **`main` after merging:**
  - 60 tests pass.
  - All 20 combinations reproduce their pins.
  - Both Games from read-only copies creates, re-patches and restores correctly, and the vanilla copies stay byte-identical.
  - All 316 asset entries are correct.
  - The live loader check passes on all 18 images, with the negative control rejected.
- **Build:** made from a fresh clone at `94e7682`. `build_release.py` checks the CRCs and every packaged asset pin.
- **Release ZIP before upload:**
  - Extracted to an unrelated folder; all 333 entries are identical to `main`.
  - The same real-exe and loader checks pass from the extracted copy, and the GUI builds.
- **After upload:** downloaded fresh. Its SHA-256 is identical to the verified ZIP.

## 6. What remains unverified

- **In-play behaviour of each patch** (the cure roll, stacking, the seahorse purchase, plant ageing). This rests on STATIC, EMU and LOADER evidence, not on playing the game.
- **The 4.4 effect in play.** The quickest check:
  1. In a build without Universal Slots, buy an egg and save.
  2. Re-patch with the setting on.
  3. Hatch the egg: expect it to hatch 3 times.
- **Any hidden switch** that could put LDW Fish Tycoon into German (4.5).
- **Codex second rounds on #19 and #21:** the findings were fixed and verified locally, but not re-reviewed by Codex, per the two-request limit.

## 7. Observations not changed

- "Validate" and "Dry Run" (and their Both Games twins) are separate buttons that do exactly the same thing.
- A tutorial hint at `0x41CF90` appears to check only slot #2 for medication. This is STATIC only; the hint may itself be developer-dead.
- The German slot prompts say "Slot" where vanilla said "Regal". That comes from the existing universal-slots patch, and given 4.5 it is likely also unseen in the LDW build.
- The game never shows stack counts.
- The post-hash identity checks in both engines cannot fail with a correct manifest (4.2).
- CI never touches a real game exe, by design. Wrong manifest bytes would be caught at patch time, not by CI.
- Historical CHANGELOG and QA entries keep the old save-location wording.
