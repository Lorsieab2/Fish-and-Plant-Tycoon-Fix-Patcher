# Universal supply slots payload audit (2026-09-29)

**Audited setting:** Fish Tycoon `universal_supply_slots`, manifest v1.2.10. It consists of:

- a 961-byte payload at VA `0x43F2A0`–`0x43F660`;
- hooks at `0x428133` (store purchase), `0x420B70` (item use), and `0x4213A7`, `0x421476` and `0x421549` (egg clears);
- six prompt-string rewrites.

**Method:**
- capstone disassembly of the vanilla and every patched build;
- unicorn emulation of the purchase and use paths against the prebuilt patched executables, with stubbed callees and a synthetic state block.

**Not done:** the game was not launched for this audit.

**Conclusion:** the patched code matches the setting description in every scenario examined. The only problems arise when a save moves between a build with this setting and one without it (6d, 6e). The [full audit](2026-09-30-full-audit-and-v1.0.16-release.md), section 4.4, covers the resulting fix.

## Established layout (vanilla)

- **Game state:** `[obj+0x10]` in the store object, `[obj+0x34]` in the tank object.
- **Slot records:** 0x1C bytes each, at `state + 0x2B8 + slot*0x1C` for slots 0–3.
  - Fields: +0 item index, +4 flag, +8 count, +0xC icon1, +0x10 icon2.
  - UI slots #2/#3/#4 are indices 1/2/3, with counts at `0x2DC`/`0x2F8`/`0x314`.
- **Purchase dispatcher** `0x427F30` calls the writer `0x427540(slot, item, icon1, icon2)`:
  - items 0, 1 go to slot 1 (medication);
  - items 2, 3, 4 go to slot 2 (chemicals; 4 is Unknown Chemical, 3 is Growth Hormone);
  - items 5, 6, 7 go to slot 3 (common, unusual and rare eggs).
- **Count:** the writer sets every item's count to 3.

## Results

| # | Check | Result |
|---|---|---|
| 1a | The two payload variants differ only at `0x43F4EB` (`add eax,1` vs `add eax,3`). The payload, hooks, NOP and strings are byte-identical across all 8 builds with this setting. Nothing is written between `0x43F661` and `0x43F800`. VirtualSize is `0x3F000`. | PASS (static) |
| 1b | All 58 branch and call targets land on instruction boundaries: every internal target plus the external ones (`0x4221A0`, `0x401D00`, `0x422440`, `0x427540`, `0x428225`, `0x4281D6`, `0x42813C`, `0x420B78`). The hooks decode to the right targets. No direct branch or absolute pointer anywhere in the exe lands inside the replaced bytes. | PASS (static) |
| 1c | Rejoin state is correct. At `0x42813C` (items 8+) the original `cmp edi,0x19 / ja` is reproduced, and ECX still holds the state pointer. The dialog sequence copies vanilla `0x4281DF`–`0x428220`. EBX and `[esp+0x10]` are only overwritten on paths that go straight to the epilogue at `0x428225`. The egg continuations redefine EAX/ECX/EDX before using them. | PASS (static + emulated) |
| 2a | The Buy confirmation (string 0xEC) appears first; No leaves slots and money untouched. | PASS (emulated) |
| 2b | Search order: a matching stack in slots 2 → 3 → 4, then the first empty slot, then the replace prompts (0xEF → slot #2, 0xEE → #3, 0xED → #4, per the string table at `0x457E50`). Answering No to all three changes nothing and spends nothing. | PASS (emulated) |
| 2c | Amounts: medications, item 2 and Growth Hormone +3 (as vanilla); Unknown Chemical +1, or +3 with three-use on; eggs +1. Vanilla writes 3 for eggs too but clears the whole record on use, so it's one hatch either way. Empty, stacked and replaced slots get the same amounts. | PASS (emulated) |
| 2d | Money is deducted exactly once (one call to the writer `0x427540`). | PASS (emulated) |
| 2e | The icon table at `0x43F504` matches the vanilla dispatcher's icon pushes for all eight items. | PASS (static) |
| 2f | Store indices 8, 11 and 25 behave exactly as vanilla; indices above 0x19 go to `0x4281D6` as vanilla. | PASS (emulated / static) |
| 3 | Use trampoline: the right case runs for every item in a non-native slot. The displaced record is always restored, including a click outside the tank. `ret 8` balances, and EBX/ESI/EDI/EBP are preserved. Slot 0, the starter egg (item 0x1A), selected slot 99 and native == physical all pass straight through. Empty slots can't be selected. | PASS (emulated) |
| 4 | The egg routine clears exactly the five fields the original 42-byte block cleared, and only when the count reaches zero. The call/ret pairs balance. The unhooked site `0x42161A` is reached only by the starter egg (count 1), which can never stack. | PASS (emulated) |
| 5 | With three-use off, an Unknown Chemical bought into an empty slot gets count 1 (stacking gives 2). With three-use on, it gets 3. | PASS (emulated) |
| 6a | Count overflow isn't realistic: counts are 32-bit and go up by at most 3 per purchase. | PASS (static) |
| 6b | Save and load copy `0x1E3C8` bytes verbatim with no clamp; the slot counts are included. | PASS (static) |
| 6c | The prompt strings fit their spans and are null-terminated, and nothing references the tail bytes that became 00. | PASS (static) |
| 6d | Items bought before the setting was on get too many uses. | DEFECT, fixed by warning (#19) |
| 6e | Items stacked or relocated with the setting on misbehave if it is later switched off. | Compatibility risk, fixed by warning (#19) |
| 6f | The tutorial hint at `0x41CF90` only looks at slot #2. | Unsure and cosmetic; may be developer-dead |
| 6g | The technical doc said the use hook "restores the physical selected slot"; it leaves the handler's 99, as vanilla does. | Doc defect, fixed (#19) |

## 6d: too many uses for pre-existing items

- **Cause:** the vanilla writer gives count 3, then vanilla resets Unknown Chemical to 1 on use (`0x4210B7`) or clears the whole egg record on hatch. The patch NOPs `0x4210B7` and makes eggs decrement instead.
- **Scenario:** a save made without the setting holds an unused egg in slot #4 (or an Unknown Chemical in slot #3), and universal slots is then applied.
- **Result:** the egg hatches 3 times, and the chemical gives 3 uses.
- **Evidence:** emulated on both builds with count 3. That count 3 survives save and load rests on static evidence only.

## 6e: items misbehave after switching the setting off (static)

The unpatched handler switches only on the selected slot. So, with the setting off:

- A chemical sitting in slot #2 runs the medication cure.
- A medication in slot #4 lands in the egg case and does nothing.
- A stack of eggs is wiped by one hatch.

## Observations (not defects)

- The game never displays counts.
- The starter egg shares the common egg's icon but never stacks with it.
- The German prompts now say "Slot" where vanilla said "Regal". The German text may be developer-dead in the LDW build; see the full audit, 4.5.

## Limits

- **No live test.** Dialogs, sound, rand, fish spawning and the fish loops were stubbed in emulation.
- **Dialog convention:** that 0 means Yes is taken from vanilla `0x428205`.
- **Cross-reference sweep:** the sweep for other readers of the slot fields used linear disassembly.
