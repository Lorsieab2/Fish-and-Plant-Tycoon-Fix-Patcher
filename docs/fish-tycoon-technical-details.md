# Fish Tycoon Fix Patcher v1.2.4: technical details

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
English and German slot prompts are changed to generic item-replacement text.

The manifest stores exact expected/replacement bytes, all seven nonempty
setting hashes, and mutually exclusive PE checksum records. The patcher rejects
any executable identity or byte sequence that does not match. It also pins the
original `.rsrc` section's size and SHA-256; the independent verifier requires
that section—including the base game application icon—to remain byte-identical.
After the fixed folder is installed, the patcher sends Windows
`SHCNE_UPDATEITEM` for the output EXE so Explorer refreshes any stale generic
white icon cached for that path.
