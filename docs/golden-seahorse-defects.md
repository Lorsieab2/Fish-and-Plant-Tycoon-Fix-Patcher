# Golden Seahorse repurchase: defects found

The optional `golden_seahorse_repurchase` setting shipped in v1.0.6. It is
defective in three separate ways, two of which are fatal at runtime. It should
stay off until the wrappers are re-derived.

Addresses below use VA = 0x400000 + file offset, which holds for every section
in this build.

## 1. Section VirtualSize overlapped .rdata (fixed in v1.0.9)

Both `extend_text_virtual_size_for_golden_seahorse_repurchase*` patches wrote
`.text` VirtualSize as `0x00040000`. That is the section's raw *end offset*, not
a size. `.text` starts at RVA 0x1000, so the section claimed RVA
0x1000-0x41000 while `.rdata` begins at RVA 0x40000 — an overlap of 0x1000.

Windows rejects an image whose sections overlap, with **"This app can't run on
your PC"** and nothing more. Every one of the 8 setting combinations that
enabled Golden Seahorse produced an executable that could not start.

The slots-only variant of the same patch already used the correct `0x0003F000`,
and `docs/fish-tycoon-technical-details.md` documents 0x3F000 as the intended
value. Corrected to 0x3F000 in v1.0.9.

## 2. The store-selection redirect misses its wrapper by one byte

`redirect_golden_seahorse_store_selection` replaces six bytes at VA 0x4282B0
(`jnz +0x34` / `lea edi,[eax+eax*4+0x1E]`) with `E9 4A 75 01 00 90`.

```
jmp at VA 0x4282B0, next instruction 0x4282B5, rel32 +0x1754A
0x4282B5 + 0x1754A = 0x43F7FF
```

The wrapper is installed at **VA 0x43F800**. The jump lands one byte earlier, on
zero padding, where execution decodes as:

```
00 83 f8 12 0f 84    add byte ptr [ebx+0x0F12F883], al
```

That reads a wild address and faults. The correct rel32 is `+0x1754B`.

## 3. Internal branch targets do not agree with any base address

Decoding the 26 wrapper bytes at the address they are installed at, VA
0x43F800:

| instruction | resolves to | correct? |
|---|---|---|
| `je` | 0x4282B2 | no — the redirect overwrites 0x4282B0-0x4282B5 |
| `jne` | 0x4282E6 | yes — matches the original `jnz +0x34` target |
| `jmp` | 0x4282B7 | no — the resume point is 0x4282B6 |

Decoding the same bytes at 0x43F7FF, the address the redirect actually jumps
to, moves every target down by one: the `jmp` becomes correct (0x4282B6) and
the `jne` becomes wrong (0x4282E5).

So the bytes cannot be correct at either address. The `je` is wrong in both
cases: it points into the six bytes the redirect itself replaces, which is
where the original `lea edi,[eax+eax*4+0x1E]` used to live. The wrapper carries
its own copy of that `lea`, so the `je` was presumably meant to target that
copy.

The purchase-side wrapper at VA 0x43F820 has a similar loose end: its trailing
`jmp +0x13` resolves to VA 0x43F84B, which is unwritten zero padding. Its
redirect, `redirect_golden_seahorse_purchase_handler` at VA 0x4281BE, does land
correctly on VA 0x43F820.

## What has and has not been done

Fixed in v1.0.9: defect 1, the VirtualSize overlap. That was the reported
"This app can't run on your PC" failure, and the fix is verified across all 16
setting combinations.

Not fixed: defects 2 and 3. Repairing them means re-deriving what the two
wrappers are supposed to do at each branch, which needs the disassembly context
the feature was written from. Patching the rel32 values by inspection alone
would be guessing at intent, and a wrong guess crashes the game in the store.

Until then the setting is documented as non-working in the patcher itself and
defaults to off. The other three Fish Tycoon settings are unaffected; their
combined build matches the SHA-256 recorded in `docs/QA.md` for v1.0.3.
