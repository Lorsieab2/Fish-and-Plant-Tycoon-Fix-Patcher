# Golden Seahorse: the defects, and how it was finally fixed

The setting shipped broken in v1.0.6 and stayed broken until v1.0.12. This is
the record of what was wrong and what actually fixed it.

Addresses use VA = 0x400000 + file offset, which holds for every section in
this build.

## What actually blocks a second purchase

Ownership lives in one dword per item at `state + index*20 + 0x78`. Three
separate places read it, and all three had to be handled:

| VA | What it does | Symptom when it fires |
|---|---|---|
| 0x4282CA | compares the ownership dword against the `+0x7C` field | Buy is refused outright |
| 0x427B66 | returns before the price is deducted | prompt appears, nothing charged or granted |
| 0x42735C | selects the panel text | shows "This is in your inventory." not the price |

Each is now wrapped so store item 11, the Golden Seahorse, takes the normal buy
path while every other item runs the original instructions unchanged.

The middle one is the reason a half-fix looked like progress: patching only the
store handler produced a confirm prompt that charged nothing, because the
purchase routine checks ownership a second time.

## How it was found

Static reading failed three times, each time landing on a plausible gate that
turned out not to be on the seahorse's path. What settled it was a runtime
watch. With the ownership address computed from live values, "find out what
accesses this address" named the instructions directly: 0x00427358 firing
continuously as the panel redrew, and 0x004282B6 and 0x004282CA firing once
each on the click.

The lesson worth keeping: the blocking check is not an ownership *test* but an
equality comparison between two fields, which is why searching the
disassembly for ownership tests kept missing it. The field's `+0x78`
displacement is also folded into a scaled index (`lea edx,[eax+eax*4+0x1E]`
then `[eax+edx*4]`), so it never appears as a literal `0x78` in the listing.

## Earlier defects, all superseded

## 1. It targeted the wrong item

The patches acted on store item index **18**. The Golden Seahorse is index
**11**; index 18 is the Diver Ornament.

The store name records begin at VA 0x004578B4 with 24-byte entries starting at
`Ick Treatment`. Counting from there:

| index | item | index | item |
|---|---|---|---|
| 0-7 | the eight stackable consumables | 11 | **Golden Seahorse** |
| 8 | Aeration System | 18 | Diver Ornament |
| 9 | Temperature Regulator | 22 | Second Tank |
| 10 | Cleaning Snail | 23-25 | the three research items |

That count of 26 matches the `cmp edi, 0x19` bound on both store switches, and
indices 0-7 are exactly the eight consumables the universal slots feature
targets — which is how the project's own technical notes describe them.

## 2. The section VirtualSize overlapped .rdata

Both `extend_text_virtual_size_for_golden_seahorse_repurchase*` patches wrote
`.text` VirtualSize as `0x00040000`, the section's raw *end offset* rather than
a size. `.text` starts at RVA 0x1000, so the section claimed RVA
0x1000-0x41000 while `.rdata` begins at 0x40000.

Windows rejects an image whose sections overlap, reporting only **"This app
can't run on your PC"**. All eight setting combinations that enabled Golden
Seahorse produced an executable that could not start. Fixed in v1.0.9 by using
`0x3F000`, the value the slots patch already used.

## 3. The store-selection redirect missed its wrapper by one byte

```
jmp at VA 0x4282B0, next instruction 0x4282B5, rel32 +0x1754A
0x4282B5 + 0x1754A = 0x43F7FF          the wrapper is at 0x43F800
```

It landed on zero padding, decoding as
`add byte ptr [ebx+0x0F12F883], al` — a wild memory read. The wrapper's own
`je` also pointed at VA 0x4282B2, inside the six bytes the redirect itself
overwrites.

## 4. The purchase-side hook was on an unrelated code path

VA 0x4281BE is the switch arm for the three research items, indices 23-25. The
Golden Seahorse dispatches to 0x42816B instead, so its `cmp edi, 0x12` could
never match there. Worse, the wrapper installed at VA 0x43F820 ran off its own
end: both exits after the original comparison landed in unwritten padding, so
enabling the setting crashed the game on any research item.

## The fix

The seahorse has exactly one ownership gate, in the store selection routine at
VA 0x004282A0:

    0x004282AD  test esi, esi            ; owned entry for the selected item
    0x004282B0  jne  0x004282E6          ; owned -> message 0x1D, return
    0x004282B2  lea  edi, [eax+eax*4+0x1E]
    0x004282B6  cmp  dword [edx+edi*4], 3

Six bytes at 0x004282B0 become `jmp 0x0043F800` plus a NOP. The 26-byte wrapper
there is:

    0x0043F800  cmp  eax, 0xB            ; the Golden Seahorse?
    0x0043F803  je   0x0043F811          ; yes -> continue as if unowned
    0x0043F809  test esi, esi            ; no  -> the original test
    0x0043F80B  jne  0x004282E6          ;        and the original branch
    0x0043F811  lea  edi, [eax+eax*4+0x1E]
    0x0043F815  jmp  0x004282B6

Every other item follows the original path exactly. The seahorse's
purchase-completion arm at VA 0x0042800E has no ownership check, so no second
patch is needed, and the two patches aimed at 0x004281BE are removed — the
research items are byte-identical to vanilla again.

## Verification

- All 16 setting combinations: no section overruns another, PE checksums match
  their bytes, pinned hashes match.
- The redirect resolves to 0x43F800 exactly, and the wrapper disassembles to
  the six instructions above.
- With the setting off, the wrapper region is untouched zero padding.
- The three-setting build without Golden Seahorse is byte-identical to the
  output recorded in `QA.md` for v1.0.3, so this work disturbed nothing else.
- In-game confirmation that an owned Golden Seahorse can be bought again is
  recorded in `QA.md` under v1.0.12: the price shows, the purchase charges,
  and the seahorse appears in the first free tank.
