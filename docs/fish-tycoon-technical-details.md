# Fish Tycoon Fix Patcher v1.2.6: technical details

## Crimson Comet curing

At VA `0x004204CE`, the original program calls its exclusive-upper-bound RNG
helper with zero. The five-byte call is redirected to a 14-byte wrapper at
`0x00401E11`. The wrapper calls the same helper with 100 and returns true only
for unsigned values below 20. The original `(11,11)` scanner, disease clear,
and counter increment remain in place.

## Unknown Chemical count correction

The instruction at VA/file `0x004210B7`/`0x210B7` writes one to the active
chemical count while the item is used. Setting it to three would reset the
counter on every use. v1.2 replaces the complete ten-byte instruction with
NOPs, preserving the count established by the purchase path. Universal slots
add one per Unknown Chemical purchase when the three-use setting is off and
three when it is on. The original decrement at `0x00421305` remains unchanged.

## Universal slots and stacking

The purchase hook at `0x00428133` accepts only store indices `0..7`. It first
constructs the original localized store confirmation with string ID `0xEC` and
cancels without changes unless the player selects Yes. After the dialog calls,
it reloads the state pointer from `[esi+0x10]` before reading any slot record;
this prevents the full-inventory path from dereferencing dialog-clobbered ECX. It then searches
occupied slot records 2, 3, 4 for the same item index, then searches for an
empty icon field in slot order, then presents generic replacement prompts.
The purchase writer remains `0x00427540`; the wrapper replaces its default count
with the previous stack count plus the item-specific purchase amount.

The use hook at `0x00420B70` temporarily swaps a complete 28-byte slot record
into the original category slot, calls the unmodified original handler through
a trampoline, swaps the records back, and restores the physical selected slot.
This retains the original item effects without duplicating them.

The optional Golden Seahorse repurchase setting targets store item index `11`.
Counting the store name records at VA `0x004578B4`, which carry 24-byte entries
beginning at `Ick Treatment`, places the Golden Seahorse at index 11; index 18
is the Diver Ornament. The count of 26 items matches the `cmp edi, 0x19` bound
on both store switches, and indices 0-7 are exactly the eight stackable
consumables the universal slots feature targets.

The only ownership gate on that item's path is in the store selection routine
at VA `0x004282A0`:

    0x004282AD  test esi, esi            ; owned entry for the selected item
    0x004282B0  jne  0x004282E6          ; owned -> message 0x1D, return
    0x004282B2  lea  edi, [eax+eax*4+0x1E]
    0x004282B6  cmp  dword [edx+edi*4], 3

Six bytes at `0x004282B0` become a jump to a 26-byte wrapper at VA
`0x0043F800`, which compares the index against 11, skips the ownership test for
that one item, performs the displaced `lea`, and resumes at `0x004282B6`. Every
other item runs the original `test`/`jne` pair unchanged. The seahorse's
purchase-completion arm at VA `0x0042800E` has no ownership check, so no second
patch is needed.

v1.0.6 through v1.0.10 also hooked VA `0x004281BE`. That is the arm for the
three research items, indices 23-25, which the seahorse never reaches; the
wrapper installed there ran off its own end into padding. Those two patches are
removed. See `golden-seahorse-defects.md`.

The original handler ends with `ret 8`, including the Common, Unusual, and Rare
Egg paths. Its internal invocation therefore removes the wrapper's duplicated
coordinate arguments. After swapping the modified record back, the wrapper
restores its saved registers and uses the same `ret 8` convention for the outer
caller. It leaves the original handler's completed-action selected-slot value
of `99` intact.

Each 42-byte egg-clear replacement starts with `call egg_consume` followed by a
direct jump to that egg type's original hatch continuation: `0x004213D1`,
`0x004214A0`, or `0x00421573`. The shared routine's `ret` therefore always has
the return address pushed by its matching `call`. The v1.2.0-v1.2.3 hooks used
`jmp egg_consume`; the routine's unmatched `ret` consumed a local value as an
address. A captured v1.2.3 crash proved that value was `3`, matching EIP
`0x00000003`.

Common, Unusual, and Rare Egg clear blocks at `0x004213A7`, `0x00421476`, and
`0x00421549` call a shared routine that decrements slot 4's count and clears the
record only at zero. Other item cases are not added to the supported set.

The payload occupies verified zero padding beginning at file `0x3F2A0` / VA
`0x0043F2A0`. The first `.text` section VirtualSize is extended from `0x3E29F`
to `0x3F000`; raw size, file size, section layout, and SizeOfImage do not change.

`0x3F000` is the largest value this field may take. `.text` begins at RVA
`0x1000`, so `0x1000 + 0x3F000` is `0x40000`, exactly where `.rdata` begins.
A larger value makes the two sections overlap, and Windows then refuses to load
the image at all, reporting only "This app can't run on your PC". v1.0.6
through v1.0.8 wrote `0x40000` here on any setting combination that enabled
Golden Seahorse — the section's raw end offset rather than a size — so all
eight of those combinations produced an executable that could not start. See
`golden-seahorse-defects.md`.
English and German slot prompts are changed to generic item-replacement text.

The manifest stores exact expected/replacement bytes, a pinned output hash for
all fifteen nonempty setting combinations, and one mutually exclusive PE
checksum record per combination. The three-setting build without Golden
Seahorse is byte-identical to the output recorded in `QA.md` for v1.0.3. The patcher rejects
any executable identity or byte sequence that does not match. It also pins the
original `.rsrc` section's size and SHA-256; the independent verifier requires
that section—including the base game application icon—to remain byte-identical.
After the fixed folder is installed, the patcher sends Windows
`SHCNE_UPDATEITEM` for the output EXE so Explorer refreshes any stale generic
white icon cached for that path.
