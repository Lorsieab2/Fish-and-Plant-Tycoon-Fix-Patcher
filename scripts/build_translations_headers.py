"""Write native/ftfp_translations/translation_tables.h from src/translation_strings.py.

    python -X utf8 scripts/build_translations_headers.py [--check]

The runtime DLL ("Translations.dll") needs, for every game line and patcher text it may
replace, the same limits the patcher's editor and validator use: which game ids the game copies
into fixed buffers (BUFFER_IDS), which it never translates (NEVER_TRANSLATED), and every
patcher DLL text (MOD_STRINGS: its DLL, its id, the hash of its English, its limit, UTF-16 or
not). --check exits 1 when the committed header is not what this writes (the tests run it).
Then rebuild the DLL: scripts/build_ftfp_translations.ps1.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import translation_strings as ts  # noqa: E402

HEADER = ROOT / "native" / "ftfp_translations" / "translation_tables.h"


def c_string(text: str) -> str:
    out = ['"']
    for ch in text:
        code = ord(ch)
        if ch in '"\\':
            out.append("\\" + ch)
        elif 32 <= code < 127:
            out.append(ch)
        else:
            out.append(f"\\x{code:02X}\" \"")
    out.append('"')
    return "".join(out)


def ids(values) -> str:
    return ", ".join(f"0x{v:03X}" for v in sorted(values))


def render() -> str:
    lines = [
        "/* translation_tables.h -- written by scripts/build_translations_headers.py from",
        "   src/translation_strings.py; do not edit.  The limits the runtime keeps to, the same as the",
        "   patcher's editor and validator. */",
        "#ifndef FTFP_TRANSLATION_TABLES_H",
        "#define FTFP_TRANSLATION_TABLES_H",
        "",
        f"#define TR_ABSOLUTE_MAX {ts.ABSOLUTE_MAX}",
        "",
        "/* Game ids the game copies into fixed buffers: a translation may be English + max(8, English / 2)",
        "   bytes long (Plant Tycoon's store item titles, eShortDesc..., too). */",
    ]
    for game, name in (("fish", "FISH"), ("plant", "PLANT")):
        lines.append(f"static const unsigned short TR_{name}_BUFFER[] = {{ {ids(ts.BUFFER_IDS[game])} }};")
        lines.append(f"#define TR_{name}_BUFFER_N {len(ts.BUFFER_IDS[game])}")
    lines.append("")
    lines.append("/* Ids never translated: texts the game writes into saves. */")
    for game, name in (("fish", "FISH"), ("plant", "PLANT")):
        lines.append(f"static const unsigned short TR_{name}_NEVER[] = {{ {ids(ts.NEVER_TRANSLATED[game])} }};")
        lines.append(f"#define TR_{name}_NEVER_N {len(ts.NEVER_TRANSLATED[game])}")
    lines += [
        "",
        "/* The patcher DLLs' texts: game (1 Fish, 2 Plant), UTF-16 or not, the limit (bytes of UTF-8, or",
        "   UTF-16 units), the hash of the English (the key's), the DLL and the key's id. */",
        "typedef struct tr_mod_text {",
        "    unsigned char game;",
        "    unsigned char wide;",
        "    short limit;",
        "    unsigned int hash;",
        "    const char *dll;",
        "    const char *id;",
        "} tr_mod_text;",
        "",
        "static const tr_mod_text TR_MOD_TEXTS[] = {",
    ]
    count = 0
    for game in ("fish", "plant"):
        seen = set()
        for m in ts.MOD_STRINGS:
            if m.game != game:
                continue
            key = ts.mod_key(m)
            if key in seen:
                continue
            seen.add(key)
            ident, digest = key[len("mod/"):].rsplit("~", 1)
            lines.append(f"    {{ {1 if game == 'fish' else 2}, {int(m.wide)}, {ts.mod_limit(m)}, 0x{digest}u, "
                         f"{c_string(m.dll)}, {c_string(ident)} }},")
            count += 1
    lines += [
        "};",
        f"#define TR_MOD_TEXT_COUNT {count}",
        "",
        "#endif /* FTFP_TRANSLATION_TABLES_H */",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    text = render()
    if "--check" in sys.argv[1:]:
        current = HEADER.read_text(encoding="utf-8") if HEADER.is_file() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"{HEADER} is out of date: run scripts/build_translations_headers.py")
            return 1
        return 0
    HEADER.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {HEADER.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
