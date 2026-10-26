# Fish Tycoon: Bigger tanks (26 fish)

The setting **Bigger tanks: 26 fish** (`bigger_tanks`, off by default) raises every tank from 21 fish to 26.
It is 45 byte patches in `data/fish_manifest.json` (`tank26_*`, each requiring the setting), written by
`scripts/pin_tank_expansion.py`, which also rebuilds the PE checksum record and the pinned hash of every
combination of the byte-patch settings. No DLL is involved.

Why there is room: each tank's block in the game's state holds 31 fish records of 0x288 bytes (the tank
constructor 0x41A9A0 builds them), the save copies the whole state, and the game only ever uses slots 0-20.
Slots 21-25 become fish slots; slots 26-30 stay unused by the game and hold the DS Store Items' animals.

Not checked in the game yet: the research below is static.


Static analysis. The target is the vanilla `Fish Tycoon.exe`, image base 0x400000, file offset = VA - 0x400000.
A record (tank t, slot s) is at state + 0x390 + t*0x51EC + s*0x288. Each tank has 31 records, and all 31 are saved.
Every site was verified by `%TEMP%\ftx\s26\sites26.py`. It asserts each old byte and prints the capstone text before and after.
`recs.json` next to it holds the same data.

## 1. Method

* I collected every `0x288` stride or `imul ...,0x288` in .text (68 hits) and every `0x51EC`. I also collected every caller of the view
  accessors 0x413B30, 0x413B50 and 0x413BD0, of REMOVE_FISH 0x418E20, and of AddFish 0x419C50.
* For each of those functions I listed every back-edge and its bound (`loops.py`).
* I classified all 43 `0x15` immediates in .text, and every `0x14` immediate in the functions that touch records.
* I searched for loops whose stride is a multiple of 0x288 (0x510, 0x798, ...). This found **six loops unrolled x3** (7 x 3 = 21)
  that the first site list missed.
* I checked every compare against 0x3528 and against any tank-end address. This covered tanks 0..3, offsets relative to the tank, to state and to state+8,
  and field offsets added to the end. Only 0x3528 itself turned up (5 sites).
* Strings: there is no "21" or "twenty-one" anywhere. The only related strings are "The tank is full!", "There is no room in any of
  your tanks for the seahorse!" and "One of your tanks is full! ...". None of them needs editing. The help pages are bitmaps
  (help1..4_bg.bmp) and I did not inspect them.

These matched the search but are not slot limits (checked and rejected):
* 0x41236A and 0x414C6D: animation frame >= 21.
* 0x418CF0, 0x418D62, 0x41981A, 0x41982C, 0x419617, 0x420A94 and 0x420AF4: species tables (21 bodies x 31 fins).
* 0x41D196, 0x422B01, 0x41D865, 0x41D8DB and 0x41EF73: sprite ids and screen coordinates.
* 0x420668 and 0x425535: tutorial ids.
* 0x4210A5: `push 0x15` is a sparkle effect id.
* 0x421362: the item switch.
* 0x427E1B: the seahorse age, 21.
* 0x420407: the tank-3 base, 0xF5C4.
* Every `cmp [rec+0xC],0x14` (adult age), every body check on `[rec+0x4C]`, and the `0x14` body and fin ids in 0x41FD.. and 0x4219.. .

The `add edi,0x288` at 0x420875 in fish_companion_slots.md is only a stride. The bound of that loop is at 0x4206E0.

## 2. The sites

### A. Slot-index bounds, 0x15 -> 0x1A (10 sites, pure immediates)

| site | function | limits |
|---|---|---|
| 0x419C72 | AddFish 0x419C50 | first free slot; every add goes through it (drop, hatch, seahorse, starter fish, eggs) |
| 0x4140C5 | view build 0x413D80 | one entry per live slot |
| 0x415893 | view refresh 0x415460 | same |
| 0x4206B1 | update 0x41FE70, pass 1 (tanks 0..3) | age, food, health, hatch, disease, death |
| 0x4206E0 | update, pass 2 (`[esp+0x18]` down-counter, tanks 0..3) | the adult, breeding and achievement pass |
| 0x41A90C | reset 0x41A8F0 (tanks 0..2) | REMOVE_FISH on a new game |
| 0x4198F7 | reset 0x4198F0 (tanks 0..3) | clears +0 on a new game |
| 0x41DF20 | magic-fish scan 0x41DE90 | magic fish effects |
| 0x413538 | thoughts 0x413530 | `Random(21)` slot of tank 2 becomes `Random(26)` |
| 0x425567 | tutorial step 0xD (0x4252C0) | makes the first adult fish in tank 0 or 2 sick (the brief called this the "sell-scene count") |

### B. Byte-offset ends relative to the tank, 0x3528 -> 0x41D0 (26*0x288) (4 sites)

* 0x421043: Unknown Chemical mutation, current tank.
* 0x42118E: vitamins / health item.
* 0x42128A: growth hormone.
* 0x424495: customer fish scan, tank 2.

### C. Loops over view ENTRIES (sparkles after an item), 0x15 -> 0x1B (4 sites)

The loops at 0x420E24, 0x4210AF, 0x4211FE and 0x4212FD run over the **view entry index** 0..20, not over slots. They use the active byte
(0x413BD0) and the tank/slot getters (0x413B30, 0x413B50). Fish are entries 1..F, so vanilla already misses its 21st fish. That is a
stock off-by-one, and it is cosmetic: that fish gets no sparkle. With 0x1B the loops cover entries 0..26, which is all 26 fish. The change is purely
cosmetic (the effect pool holds 0x42 effects). 0x1A would keep the stock off-by-one. The item's real effect runs on the records (group B)
or on all `count` entries (0x420CD0, which has no bound).

### D. Loops unrolled x3 (7 iterations x 3 slots) -> 13 iterations x 2 slots (NOT just immediates)

26 is not a multiple of 3. A count of 9 would reach slot 26 (a companion), and a count of 8 would stop at slot 23.
So each loop is rewritten to 13 iterations of 2 slots:
* the count 7 becomes 13;
* the stride 0x798 becomes 0x510;
* the third check of each iteration is disabled.

Every change keeps the instruction length. The "third_skip" records change a `je` opcode to `jmp` (74 -> EB); that is an opcode change,
not an immediate. The second check in each iteration (`[eax]`, `[eax+0x288]` and so on) still points at a valid slot (2k+1).

| loop | what | bytes |
|---|---|---|
| 0x41E260..0x41E28D (in 0x41DF50, sickness roll) | +6 sickness chance per sick fish (rec+0x40) in the tank | count 0x41E260, je 0x41E280, stride 0x41E285 |
| 0x41FCA8..0x41FD5E (0x41FC90, fish-egg item, called via 0x421646) | "any fish in tanks 0/1/2?": 7 eggs if none, else 3 | t0: **code edit at 0x41FCA8** (below), je 0x41FCCF, stride 0x41FCD6; t1: 0x41FCE6, 0x41FD0F, 0x41FD16; t2: 0x41FD26, 0x41FD4F, 0x41FD56 |
| 0x423050..0x4230CD (0x422F10, debug path when `[state+0x1E168]==9999`) | writes rec+4 and rec+8 of every slot, tanks 0..3 | the third write pair is re-pointed at slot 2k+1, which is harmless because writing it twice gives the same result: 0x42309A, 0x4230A9, 0x4230B9; stride 0x4230AF; end 0x4230B4 `cmp eax,0x3528` -> 0x41D0 |
| 0x423800..0x42389A (sell screen) | adult, healthy, non-body-22 fish in tank 2 | count `lea edx,[edi+7]` at 0x42381F, je 0x423873, stride 0x423892 |
| 0x423E85..0x423EE8 (0x423E00, sell scene opening) | adults in tank 2 | count 0x423E85, je 0x423EC9, stride 0x423EE0 |
| 0x423F62..0x423FE5 (same function) | live non-body-22 fish in tank 2 | count 0x423F62; **0x423F82 `lea ebx,[edx+0xF]` -> `[edx+9]`** (see below); je 0x423FC8; stride 0x423FDE |

Why 0x423F82 changes: ebx is body 22, computed as 7 + 15. With a count of 13 it must still be 22, so the displacement becomes 9 (13 + 9).

**0x41FCA8 is the only code edit.** The first loop's count is `mov ecx,ebp`. ebp = 7 is also the egg count used after the loops, so there is
no immediate to change. Replace the 8 bytes `8B CD 8D 9B 00 00 00 00` (`mov ecx,ebp` plus the 6-byte alignment `lea ebx,[ebx]`) with
`B9 0D 00 00 00 90 90 90`. The loop top at 0x41FCB0 does not move.

### Full byte table (45 records, all verified against vanilla)

| name | VA | file off (instr) | bytes old -> new | capstone old -> new |
|---|---|---|---|---|
| addfish_free_slot | 0x419C72 | 0x19C72 | `83F815` -> `83F81A` | `cmp eax, 0x15` -> `cmp eax, 0x1a` |
| view_build_slots | 0x4140C5 | 0x140C5 | `83F815` -> `83F81A` | `cmp eax, 0x15` -> `cmp eax, 0x1a` |
| view_refresh_slots | 0x415893 | 0x15893 | `83F815` -> `83F81A` | `cmp eax, 0x15` -> `cmp eax, 0x1a` |
| update_loop1_slots | 0x4206B1 | 0x206B1 | `83F915` -> `83F91A` | `cmp ecx, 0x15` -> `cmp ecx, 0x1a` |
| update_loop2_count | 0x4206E0 | 0x206E0 | `C744241815000000` -> `C74424181A000000` | `mov dword ptr [esp + 0x18], 0x15` -> `mov dword ptr [esp + 0x18], 0x1a` |
| reset_remove_slots | 0x41A90C | 0x1A90C | `83FE15` -> `83FE1A` | `cmp esi, 0x15` -> `cmp esi, 0x1a` |
| reset_clear_count | 0x4198F7 | 0x198F7 | `BE15000000` -> `BE1A000000` | `mov esi, 0x15` -> `mov esi, 0x1a` |
| magic_scan_slots | 0x41DF20 | 0x1DF20 | `83FA15` -> `83FA1A` | `cmp edx, 0x15` -> `cmp edx, 0x1a` |
| thoughts_random_slot | 0x413538 | 0x13538 | `6A15` -> `6A1A` | `push 0x15` -> `push 0x1a` |
| tutorial_sick_slots | 0x425567 | 0x25567 | `83F815` -> `83F81A` | `cmp eax, 0x15` -> `cmp eax, 0x1a` |
| medicine_a_end | 0x421043 | 0x21043 | `81FB28350000` -> `81FBD0410000` | `cmp ebx, 0x3528` -> `cmp ebx, 0x41d0` |
| medicine_b_end | 0x42118E | 0x2118E | `81FB28350000` -> `81FBD0410000` | `cmp ebx, 0x3528` -> `cmp ebx, 0x41d0` |
| medicine_c_end | 0x42128A | 0x2128A | `81FB28350000` -> `81FBD0410000` | `cmp ebx, 0x3528` -> `cmp ebx, 0x41d0` |
| customers_end | 0x424495 | 0x24495 | `81FE28350000` -> `81FED0410000` | `cmp esi, 0x3528` -> `cmp esi, 0x41d0` |
| sparkle_entries_a | 0x420E24 | 0x20E24 | `83FF15` -> `83FF1B` | `cmp edi, 0x15` -> `cmp edi, 0x1b` |
| sparkle_entries_b | 0x4210AF | 0x210AF | `83FF15` -> `83FF1B` | `cmp edi, 0x15` -> `cmp edi, 0x1b` |
| sparkle_entries_c | 0x4211FE | 0x211FE | `83FF15` -> `83FF1B` | `cmp edi, 0x15` -> `cmp edi, 0x1b` |
| sparkle_entries_d | 0x4212FD | 0x212FD | `83FF15` -> `83FF1B` | `cmp edi, 0x15` -> `cmp edi, 0x1b` |
| sick_crowd_count | 0x41E260 | 0x1E260 | `B907000000` -> `B90D000000` | `mov ecx, 7` -> `mov ecx, 0xd` |
| sick_crowd_third_skip | 0x41E280 | 0x1E280 | `7403` -> `EB03` | `je 0x41e285` -> `jmp 0x41e285` |
| sick_crowd_stride | 0x41E285 | 0x1E285 | `0598070000` -> `0510050000` | `add eax, 0x798` -> `add eax, 0x510` |
| eggs_t0_third_skip | 0x41FCCF | 0x1FCCF | `7405` -> `EB05` | `je 0x41fcd6` -> `jmp 0x41fcd6` |
| eggs_t0_stride | 0x41FCD6 | 0x1FCD6 | `0598070000` -> `0510050000` | `add eax, 0x798` -> `add eax, 0x510` |
| eggs_t1_count | 0x41FCE6 | 0x1FCE6 | `B907000000` -> `B90D000000` | `mov ecx, 7` -> `mov ecx, 0xd` |
| eggs_t1_third_skip | 0x41FD0F | 0x1FD0F | `7405` -> `EB05` | `je 0x41fd16` -> `jmp 0x41fd16` |
| eggs_t1_stride | 0x41FD16 | 0x1FD16 | `0598070000` -> `0510050000` | `add eax, 0x798` -> `add eax, 0x510` |
| eggs_t2_count | 0x41FD26 | 0x1FD26 | `B907000000` -> `B90D000000` | `mov ecx, 7` -> `mov ecx, 0xd` |
| eggs_t2_third_skip | 0x41FD4F | 0x1FD4F | `7405` -> `EB05` | `je 0x41fd56` -> `jmp 0x41fd56` |
| eggs_t2_stride | 0x41FD56 | 0x1FD56 | `0598070000` -> `0510050000` | `add eax, 0x798` -> `add eax, 0x510` |
| cheat_age_third_a | 0x42309A | 0x2309A | `899C2AA4080000` -> `899C2A1C060000` | `mov dword ptr [edx + ebp + 0x8a4], ebx` -> `mov dword ptr [edx + ebp + 0x61c], ebx` |
| cheat_age_third_b | 0x4230A9 | 0x230A9 | `8BAAAC080000` -> `8BAA24060000` | `mov ebp, dword ptr [edx + 0x8ac]` -> `mov ebp, dword ptr [edx + 0x624]` |
| cheat_age_stride | 0x4230AF | 0x230AF | `0598070000` -> `0510050000` | `add eax, 0x798` -> `add eax, 0x510` |
| cheat_age_end | 0x4230B4 | 0x230B4 | `3D28350000` -> `3DD0410000` | `cmp eax, 0x3528` -> `cmp eax, 0x41d0` |
| cheat_age_third_c | 0x4230B9 | 0x230B9 | `89AAA8080000` -> `89AA20060000` | `mov dword ptr [edx + 0x8a8], ebp` -> `mov dword ptr [edx + 0x620], ebp` |
| sell_adults_count | 0x42381F | 0x2381F | `8D5707` -> `8D570D` | `lea edx, [edi + 7]` -> `lea edx, [edi + 0xd]` |
| sell_adults_third_skip | 0x423873 | 0x23873 | `741D` -> `EB1D` | `je 0x423892` -> `jmp 0x423892` |
| sell_adults_stride | 0x423892 | 0x23892 | `0598070000` -> `0510050000` | `add eax, 0x798` -> `add eax, 0x510` |
| sellscene_adults_count | 0x423E85 | 0x23E85 | `B907000000` -> `B90D000000` | `mov ecx, 7` -> `mov ecx, 0xd` |
| sellscene_adults_third_skip | 0x423EC9 | 0x23EC9 | `7415` -> `EB15` | `je 0x423ee0` -> `jmp 0x423ee0` |
| sellscene_adults_stride | 0x423EE0 | 0x23EE0 | `0598070000` -> `0510050000` | `add eax, 0x798` -> `add eax, 0x510` |
| sellscene_comp_count | 0x423F62 | 0x23F62 | `BA07000000` -> `BA0D000000` | `mov edx, 7` -> `mov edx, 0xd` |
| sellscene_comp_body22 | 0x423F82 | 0x23F82 | `8D5A0F` -> `8D5A09` | `lea ebx, [edx + 0xf]` -> `lea ebx, [edx + 9]` |
| sellscene_comp_third_skip | 0x423FC8 | 0x23FC8 | `7414` -> `EB14` | `je 0x423fde` -> `jmp 0x423fde` |
| sellscene_comp_stride | 0x423FDE | 0x23FDE | `0598070000` -> `0510050000` | `add eax, 0x798` -> `add eax, 0x510` |
| eggs_t0_count_code | 0x41FCA8 | 0x1FCA8 | `8BCD8D9B00000000` -> `B90D000000909090` | `mov ecx, ebp ; lea ebx, [ebx]` -> `mov ecx, 0xd ; nop ; nop ; nop` |

## 3. Per-slot arrays sized for 21

None found. What I checked:
* customers: keep a slot index and read the record;
* thoughts: no array;
* the sell scene, 0x4236D0 and 0x424010: copy from the record;
* species, journal and research: 21 bodies x 31 fins, plus scalars at `state+0xF9xx`, none of them per slot;
* isolation: tank 3 is the same 31-record block;
* view: 150 entries of 0x84 bytes, with `count` at view+0x5DD8. The refresh 0x415460 keeps a stack copy of 0x96 entries;
* screensaver: built on the view.

Every use of an entry's slot in the binary (`+0x44`, or 0x413B50) goes straight into `imul ...,0x288`, which addresses the record.
The uses are at 0x411073, 0x411D4B, 0x411DD2, 0x411E1D, 0x411E85, 0x414312, 0x415084, 0x4150C9, 0x415BC1, 0x4193C5, 0x41D8B7,
0x41D9D7, 0x41F01D (drop), 0x41F841, 0x41F914, 0x420CDF, 0x420DE9, 0x421073, 0x4211C2 and 0x4212C2.
26 fish + 5 companions + 1 isolation fish = 32 entries, which is within the 150 cap.

## 4. Overlaps

* **Fix Patcher manifest** (44 patches): no byte overlaps.
  * The nearest is `unknown_chemical_remove_runtime_count_reset_*` at VA 0x4210B7 (10 bytes). sparkle_entries_b changes only
    0x4210B1, so the gap is 6 bytes (0x4210B2 `jl` and 0x4210B4 `mov` are in between).
  * `stack_*_egg_uses` (0x4213A7, 0x421476, 0x421549), `redirect_item_use` 0x420B70 and the 0x43F2A0 payload contain no slot loop (I scanned them).
* **DS Fish DLL** (ds_sites.h), **DS Store DLL** (store_sites.h) and every other `native/*/*sites*.h`: no overlap.
  These sites are in the same functions as ours but share no bytes:
  * SITE_TIER_HEALTH 0x41DF68 and SITE_TIER_DISEASE 0x41E157, in 0x41DF50 before the crowd loop at 0x41E260;
  * SITE_TICK 0x420470 and SITE_DEATH 0x420622, in update pass 1;
  * SITE_CUSTOMERS 0x42426F, in the customer loop, whose end is at 0x424495;
  * SITE_THOUGHTS 0x41355F, in the thoughts function, where our byte is 0x413539;
  * SITE_MUTATE_* 0x420EFB and 0x420F27, in the Unknown Chemical loop, whose end is at 0x421043;
  * SITE_EGG_USE 0x421356 and SITE_TIER_GOAL 0x41FC0F.
* **Manifest bookkeeping (not a byte overlap):** every combination of settings has its own `update_pe_checksum_*` record (offset 0x150)
  and its own `patched_sha256_by_settings` entry. A new setting doubles them (16 -> 32 combinations).
* **DLL code that must follow the setting:** `ftfp_ds_store.c` has `#define SLOTS 21` (used at lines 224, 358 and 640: free fish slot,
  owned scan, eel checks). With the setting on, these must use 26. For example, the DLL can read the live byte at 0x419C74 (0x15 or 0x1A) when it installs.

## 5. Slots 21..30 after the change

* Stock code does not read or write slots 21..30 today, with two exceptions. The save and load (0x419100, 0x41AE70) copy the whole
  block raw. The constructor 0x41A9A0 visits all 31 records and zeroes their sub-arrays. The loops listed above are all the slot loops in the game.
* After the 45 records, every stock slot loop stops at slot 25:
  * groups A and B: `< 26`;
  * group D: 13 x 2 = slots 0..25, including the debug loop.
* **No stock loop reaches slots 26..30.** They can be reached only through view entries. Those entries exist only if the DS Store DLL widens the
  view builders (section 6).
* **Old saves:** in a vanilla save, slots 21..25 hold whatever the heap held (almost certainly zero, but not guaranteed;
  fish_companion_slots.md 1.2). With the setting on, these slots hold live fish, so anything non-zero there is treated as a fish: it ages, it can be sold, it is shown.
  A pure byte patch cannot clean them. If the DLL is present, it should zero any record in 21..25 that fails a plausibility check on load:
  * body and fin in range;
  * age <= 21;
  * a sane timestamp at +0.

  Saves written by an Option-B build of the DS Store DLL, which used 21..30 for animals, need their animals moved from 21..25 to 26..30.
* **Turning the setting off** with fish in 21..25 keeps them in the save, but they stop updating and are not shown. If the DLL widens the builders, they are shown but still do not update (section 6).

## 6. DS Store DLL widening the two view builders to 31

* **Bytes:**
  * 0x4140C5 is `83 F8 15` in vanilla and `83 F8 1A` with the 26-fish setting. The DLL writes `83 F8 1F`.
  * 0x415893 is the same.
  * The byte that changes is at **0x4140C7 / 0x415895**. The DLL should accept 0x15 or 0x1A there and write 0x1F.
  * This byte is also a manifest patch byte. The patcher edits the file and the DLL edits memory afterwards, so there is no conflict as long as the DLL accepts either value.
* **Paths that use an entry's slot:** all of them go through `imul slot,0x288`. None has a bound or another array.
  * pick 0x414E30 (hit rectangle only);
  * drop 0x41EFF0 (AddFish / REMOVE_FISH; the isolation tank refuses body 22 at 0x41F3C4);
  * trash 0x41E720 -> 0x418E20;
  * draw 0x415AD0, 0x4145F0, and the held fish 0x415BA0;
  * mover 0x415E90 and its callees 0x411520, 0x4115D0, 0x411630, 0x411A00, 0x411A60, 0x414300, 0x411D30;
  * bubbles 0x411DA0;
  * feeding 0x412160 (body 22 is exempt from overfeeding);
  * 0x411050 (reads the body) and 0x411FE0.

  **Nothing breaks, and nothing indexes an array sized 21 or 26.**
* **Side effects to know about (not breakage):**
  * The cure loop 0x420CD0 runs over all `count` entries. It also clears rec+0x40 (disease) on companions, which is harmless.
  * The sparkle loops in group C (bound 0x1B) give a companion a sparkle when it sits at entry <= 26, which happens when the tank has fewer than 26 fish.
  * Dropping a companion on a tank button calls AddFish, which would move it into fish slots 0..25. The DLL's H4 must intercept that
    for slot >= 26: change its test from `>= 21` to `>= 26`.
* With the setting **off** and the DLL writing 31, any non-zero record in 21..25 also gets an entry. The DLL should zero or skip
  invalid records in 21..25, as described in section 5.
* The isolation entry is still F+1 after the widened loop, because the builder appends it after the loop. So it now comes after the companions. That is fine.

## 7. Python lists

SITES_26 gives each site as (name, va, capstone text, imm_off, imm_size, old, new). The "_third_skip" records use imm_off 0 for the
opcode byte, 0x74 -> 0xEB. CODE_26 holds the one 8-byte rewrite. MANIFEST_26 gives the same changes as whole-instruction manifest
records (file offset, expected, replacement).
