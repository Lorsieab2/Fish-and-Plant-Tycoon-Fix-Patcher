"""Every text a patch can show has a translation key.

* Every string literal of every shipped patcher DLL (read from its sources, kept when the DLL as
  shipped holds it: tests/translation_coverage.py) is a key's English
  (src/translation_strings.py MOD_STRINGS), an English piece of a counted text
  (COUNTED_FALLBACKS), or in ALLOWED below with the reason it is never shown to the player.
* Every key's English is in its DLL, and every counted text is in its DLL (the DLL asks
  Translations.dll for it by that exact text).
* Every text an executable patch writes (data/<game>_manifest.json) is in a game line's English,
  so the "strings/<id>" key of the patched English covers it, or is in EXE_ALLOWED.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import translation_coverage as tc  # noqa: E402
import translation_strings as ts  # noqa: E402

# ------------------------------------------------------------------ not player-visible: rules
# (pattern, reason): a literal matching the pattern is not shown in the game.
ALLOWED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\r\n", "a line of the DLL's own log file (<DLL>.log beside it), never shown in the game"),
    (r"^[\w ]+: NOT installed; the code at $", "the start of a log line (the address follows)"),
    (r"^0123456789ABCDEF$", "hex digits for an address in the log"),
    (r"\.(png|dll|ini|log|dat|txt)$|\\", "a file or folder name"),
    (r"^\.(tmp|previous|unreadable-?)$", "the ending of a temporary or set-aside data file's name"),
    (r"^(Ftfp|SDL_)\w+$", "an export another DLL (or SDL) looks up by name"),
)

# ------------------------------------------------------------------ not player-visible: one by one
_API = "a Windows function looked up with GetProcAddress"
_FONT = "a Windows font's name (the fonts Unicode Text draws with, the Time Warp box's font)"
_INI = "a key or section of the DLL's own .ini file"
_LOG = "part of a line of the DLL's own log file"
_GERMAN = ("German mode: a patcher text with a German version keeps it in German mode "
           "(docs/translations.md); its English has a key")
ALLOWED: dict[str, tuple[set[str], str]] = {
    "api": ({"SHGetSpecialFolderPathW", "SetWindowLongW", "CallWindowProcW", "TranslateMessage", "EnumThreadWindows",
             "IsWindowVisible", "PeekMessageW", "ImmGetContext", "ImmGetCompositionStringW", "ImmReleaseContext",
             "CreateCompatibleDC", "CreateDIBSection", "SelectObject", "CreateFontW", "SetTextColor", "SetBkMode",
             "ExtTextOutW", "GdiFlush", "SetTextAlign", "ScriptItemize", "ScriptShape", "ScriptPlace",
             "ScriptGetFontProperties", "GetFontData", "GetTextMetricsW", "D2D1CreateFactory", "DWriteCreateFactory",
             "ScreenToClient"}, _API),
    "fonts": ({"Segoe UI", "Yu Gothic", "Meiryo", "Microsoft YaHei", "Malgun Gothic", "Nirmala UI", "Leelawadee UI",
               "Ebrima", "Gadugi", "Myanmar Text", "Mongolian Baiti", "Microsoft Himalaya", "Javanese Text",
               "Segoe UI Historic", "Segoe UI Emoji", "Segoe UI Symbol", "Sylfaen"}, _FONT),
    "locale": ({"en-us"}, "the locale DirectWrite measures text in"),
    "font pictures": ({"paddington_tt_18_unicode", "paddington_tt_30_unicode",
                       "FONT_TRIPLEX_SANSLIGHTLIN_BOLD_16PT_unicode", "PTfontsmall_unicode"},
                      "a font picture's name in the game's Images folder"),
    "ini": ({"Counts", "Shown", "Mode", "Paste", "Font"}, _INI),
    "data folder": ({"Fish Tycoon Fix Patcher Data", "Plant Tycoon Fix Patcher Data", "unreadable", "other-save"},
                    "a folder or file name in Documents\\LDW"),
    "ds store log": ({"Slot ", ": played and saved without DS Store Items since; its animals are back",
                      ": a Tank Animals file did not belong to this save; it was set aside",
                      " animal(s) found in the save's fish records; Tank Animals.dat could not be written, so they "
                      "stay in the save until the next save",
                      ": Tank Animals.dat could not be written; the previous one is kept"}, _LOG),
    "german": ({
        # Tank Counts
        "Fische: ", " von ", "ausgewachsen", "halbw\xfcchsig", "jung", "Tot: ", "Krank: ", "Pilzinfektion",
        "Weissp\xfcnktchen", "Niedrige Gesundheit: ", "Tiere: ", "Zuchtaquarium: ", "Z\xe4hlung: An",
        "Z\xe4hlung: Aus", "Goldenes Seepferdchen", "Magischer Kugelfisch", "Blaupunktrochen", "Mur\xe4ne",
        # DS Store Items
        "Exotische Fischeier", "Radioaktive Wachstumshormone", "Wiederbelebungstrank", "Fischfutter", " Gelege",
        " Anwendung", " Anwendungen", " Dosis", " Dosen", "Noch ", "Behandelt: $",
        "Dieser Kugelfisch verbessert auf\nmagische Weise die Umgebung und das\nLeben deiner Fische.\nWird komplett "
        "installiert ausgeliefert.",
        "Dieser Stachelrochen verbessert auf\nmagische Weise die Umgebung und das\nLeben deiner Fische.\nWird "
        "komplett installiert ausgeliefert.",
        "Diese Mur\xe4ne verbessert auf\nmagische Weise die Umgebung und das\nLeben deiner Fische. Wird komplett\n"
        "installiert ausgeliefert, mit ihrem Felsen.",
        "Diese besonderen Eier waren extrem\nschwer zu bekommen. Erforsche\nLEBENSBEDINGUNGEN, bevor du\nversuchst, "
        "sie auszubr\xfcten.",
        "Zeitsprung", "Plus 1.000 $",
        "Spring in der Zeit voraus! W\xe4hle, wie\nviele Stunden (1-72) vergehen, als w\xe4rst\ndu so lange weg "
        "gewesen. Deine Fische\naltern, fressen, und die Forschung l\xe4uft.",
        "Ein Haufen Goldm\xfcnzen! Jeder Kauf\nbringt dir 1.000 $.\nKauf so viele du willst.",
        "Jeder Fisch in deinem Becken wird ganz gesund\nund heil, junge werden sofort erwachsen,\ntr\xe4"
        "chtige geb\xe4ren Babys. Behandelte Fische\nbringen den H\xf6chstpreis, egal welcher Preis\neingestellt ist. "
        "Reicht f\xfcr 3 Behandlungen.",
        "Dieser magische Trank belebt tote\nFische sofort wieder und macht sie\nganz gesund. Reicht f\xfcr 3 "
        "Behandlungen.",
        "Ein Wundermittel, das alle Fische im\nBecken sofort klont. Achte auf genug\nPlatz im Becken!\nReicht f\xfcr "
        "3 Behandlungen.",
        "Weiteres Aquarium", "Noch ein Aquarium zum Z\xfcchten! Jeder\nKauf \xf6\x66\x66net das n\xe4\x63hste: "
        "Becken 4,\n5 und 6.",
        "Futterautomat", "F\xfcttert automatisch alle deine Fische\nin jedem Becken. Nie wieder Hunger!",
        "Heilautomat", "Heilt auf magische Weise alle Krankheiten\ndeiner Fische und macht sie ganz gesund.\nWirkt in "
        "jedem Becken.",
        "Zus\xe4tzliche Vorratsf\xe4\x63her",
        "Sieben weitere Vorratsf\xe4\x63her f\xfcr Medizin,\nChemikalien und Eier, auf zwei weiteren\nSeiten. Die "
        "Pfeile neben den F\xe4\x63hern\nbl\xe4ttern um. Ein Kauf \xf6\x66\x66net alle sieben.",
        "Ver\xe4ndert die Flossen von Fischen.\nReicht f\xfcr 3 Behandlungen.",
        "Ver\xe4ndert die K\xf6rper von Fischen.\nReicht f\xfcr 3 Behandlungen.",
        " zur\xfc\x63kgeben? Er schaltet sich ab. Es gibt kein Geld zur\xfc\x63k, und ein neuer Kauf kostet den "
        "vollen Preis.",
        "Gekauft. Zum Zur\xfc\x63kgeben noch einmal anklicken.",
        # Extra Tanks, Extra Supply Slots, Optimize Prices
        "Dieser Tank geh\xf6rt dir noch nicht!", "Die zus\xe4tzlichen Vorratsf\xe4\x63her geh\xf6ren dir noch nicht!",
        "Alle entdeckten Arten auf ihren\nbesten Preis pro Tag setzen?",
        "Alle entdeckten Arten auf ihren\nh\xf6\x63hsten Verkaufspreis setzen?\nZu diesem Preis verkaufen sich\n"
        "Fische viel langsamer.",
        " Preis gesetzt.", " Preise gesetzt.",
    }, _GERMAN),
}

# Texts written by executable patches that no game line's English holds: (patch id, text) -> reason.
EXE_ALLOWED: dict[tuple[str, str], str] = {
    ("install_universal_slots_payload_unknown_one", "RPWS"): "machine code bytes that happen to be letters",
    ("install_universal_slots_payload_unknown_one", "SVWU"): "machine code bytes that happen to be letters",
    ("install_universal_slots_payload_unknown_three", "RPWS"): "machine code bytes that happen to be letters",
    ("install_universal_slots_payload_unknown_three", "SVWU"): "machine code bytes that happen to be letters",
}
_EXE_GERMAN = ("the German column of a string-table line (German mode), translated through the same "
               "strings/<id> key as its English")


def allowed_reason(text: str) -> str | None:
    for pattern, reason in ALLOWED_PATTERNS:
        if re.search(pattern, text):
            return reason
    for items, reason in ALLOWED.values():
        if text in items:
            return reason
    return None


class DllTexts(unittest.TestCase):
    def test_every_dll_text_has_a_key(self) -> None:
        keyed = {(m.game, m.dll, m.english, m.wide) for m in ts.MOD_STRINGS}
        missing = []
        for game, dll in tc.DLLS:
            for (text, wide), where in tc.dll_texts(game, dll).items():
                if (game, dll, text, wide) in keyed or (game, dll, text) in ts.COUNTED_FALLBACKS:
                    continue
                if allowed_reason(text) is None:
                    missing.append(f"{game} {dll} {where}: {text!r}")
        self.assertEqual(missing, [], "texts a player can see with no key in src/translation_strings.py "
                                      "(or add them to ALLOWED with a reason)")

    def test_every_allowed_text_is_still_in_a_dll(self) -> None:
        held = set()
        for game, dll in tc.DLLS:
            held |= {text for text, _w in tc.dll_texts(game, dll)}
        for name, (items, reason) in ALLOWED.items():
            self.assertTrue(reason)
            for text in items:
                self.assertIn(text, held, f"ALLOWED[{name!r}] lists a text no DLL holds any more: {text!r}")

    def test_every_key_and_counted_text_is_in_its_dll(self) -> None:
        for m in ts.MOD_STRINGS:
            data = tc.shipped(m.game, m.dll)
            needle = (m.english.encode("utf-16-le") + b"\0\0") if m.wide else (m.english.encode("cp1252") + b"\0")
            self.assertIn(needle, data, (m.dll, m.english))
        for (game, dll, piece), counted in ts.COUNTED_FALLBACKS.items():
            self.assertTrue(any(m.counted and m.english == counted and m.dll == dll for m in ts.MOD_STRINGS), counted)
            texts = {t for t, _w in tc.dll_texts(game, dll)}
            self.assertIn(piece, texts, (dll, piece))

    def test_every_patch_with_a_dll_text_has_a_group(self) -> None:
        for m in ts.MOD_STRINGS:
            name = ts.setting_name(m.game, ts.patch_of(m))
            self.assertNotEqual(name, ts.patch_of(m), f"{m.dll}: {ts.patch_of(m)} is not a setting")


@unittest.skipUnless(all((tc.ROOT / "data" / f"{g}_manifest.json").is_file() for g in ("fish", "plant")), "manifests")
class ExeTexts(unittest.TestCase):
    def test_every_exe_patch_text_is_in_a_game_line(self) -> None:
        try:
            import store_emulator as se
        except ImportError:
            self.skipTest("needs the test emulator")
        exes = {"fish": se.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe",
                "plant": se.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"}
        if not all(p.is_file() for p in exes.values()):
            self.skipTest("needs the vanilla games")
        missing = []
        for game in ("fish", "plant"):
            english = [e.english for e in ts.entries_for(game, exes[game].read_bytes())]
            manifest = json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))
            for patch in manifest["patches"]:
                try:
                    data = bytes.fromhex(str(patch.get("replacement", "")).replace(" ", ""))
                except ValueError:
                    continue
                for m in re.finditer(rb"[\x0a\x20-\x7e]{4,}", data):
                    text = m.group().decode("cp1252")
                    if not re.search(r"[A-Za-z]{3}", text):
                        continue
                    if (patch["id"], text) in EXE_ALLOWED or patch["id"].endswith("_de"):
                        continue          # _de: _EXE_GERMAN
                    if not any(text in e for e in english):
                        missing.append(f"{game} {patch['id']}: {text!r}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
