# Technical details

## Exact supported build

The analysis and patch apply only to the 700,416-byte PE32 x86 executable with
SHA-256 `D1F83E3E3CAFE177452E2F8B6AF4B68CACED783B77A304370389375DB611D6F9`.

## Original old-age branch

The relevant block begins at VA `0x0042E219` (file offset `0x2E219`):

```text
0042E219  mov  edx,[esi+8]
0042E21C  fld  dword ptr [edx+10h]
0042E21F  fcomp qword ptr [004695E0h] ; 1720.0
0042E225  fnstsw ax
0042E227  test ah,41h
0042E22A  jne  0042E244              ; age below threshold skips
0042E22C  push 3E8h                  ; 1000
0042E231  call 004033B0              ; original Random
0042E236  add  esp,4
0042E239  cmp  eax,9
0042E23C  jg   0042E244
0042E23E  mov  eax,[esi+8]
0042E241  mov  [eax+24h],ebp         ; ebp is zero: health = 0
```

The floating-point comparison enters the roll at internal age `1720` or later.
The RNG returns `0..999`; signed results `<=9` execute the health-zero write.
There are ten successful values out of 1000, so the original conditional chance
is exactly 1% per eligible update.

## Patch

Only the immediate byte of `cmp eax,9` is changed:

```text
File offset: 0x2E23B
Original:    09
Fixed:       FF
Instruction: cmp eax,-1
```

The existing `jg` then skips the death write for every possible nonnegative RNG
result. The age comparison, RNG call, stack cleanup, branch target, and original
health write remain byte-for-byte unchanged. Preserving the RNG call also avoids
shifting the game's later random-number sequence.

The PE checksum field at file offset `0x150` changes from `0x000B01BF` to
`0x000AF7C0`. The complete fixed executable SHA-256 is
`BFF2115EDB34284E63B04363CC5E6FBDF4845DA489F8E98292C505CA5CD4C046`.

## Scope

This patch prevents only this explicitly identified old-age health-zero write.
It does not prevent health loss or death from other mechanics. Visible long-term
gameplay behavior still requires player confirmation.
