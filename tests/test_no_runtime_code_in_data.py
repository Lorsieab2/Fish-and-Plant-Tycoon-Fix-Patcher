"""No patcher DLL builds code at run time in its data pages.

Under DEP a trampoline, code cave or stolen-bytes buffer kept in a DLL's .data/.bss is not executable, so the
game crashes at the first jump into it even though an emulator (which ignores page protection) passes. Found
live in Virtual Families 2's B207 (a trampoline array whose pages were never made executable). Fish and Plant
Tycoon's DLLs have none: their added code is `__declspec(naked)` functions in the DLL's own .text, the game's
code jumps into them, and nothing allocates or generates code. This test keeps it that way.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

NATIVE = Path(__file__).resolve().parents[1] / "native"
SOURCES = sorted(p for p in NATIVE.rglob("*") if p.suffix in (".c", ".h", ".inc"))

# A byte array whose name says it holds code.
CODE_ARRAY = re.compile(
    r"\b(static\s+)?(unsigned\s+char|uint8_t|BYTE)\s+\w*(tramp|stub|cave|thunk|gate|steal)\w*\s*\[", re.I)
# Writing a jump, call or push opcode as the first byte of a buffer.
WRITES_OPCODE = re.compile(r"\[\s*0\s*\]\s*=\s*0x(E9|E8|68|FF|C3)\b|\*\s*\(\s*(unsigned\s+char|BYTE)\s*\*\s*\)\s*\w+\s*=\s*0x(E9|E8)\b")


def code_lines(path: Path):
    """Lines of a source file, leaving out the buffers of EXPECTED bytes (what a site must hold before it is
    patched, e.g. USE_GATE_EXPECT, call_expect): they are only compared, never executed."""
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if "expect" not in line.lower():
            yield number, line


class NoRuntimeCodeInData(unittest.TestCase):
    def test_sources_were_found(self) -> None:
        self.assertGreater(len(SOURCES), 20)

    def test_no_executable_memory_is_allocated(self) -> None:
        for path in SOURCES:
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("VirtualAlloc", text, f"{path.name} allocates memory: make it executable and test it")
            self.assertNotIn("HeapCreate", text, f"{path.name} creates an executable heap?")

    def test_no_code_arrays_in_data(self) -> None:
        for path in SOURCES:
            for number, line in code_lines(path):
                if " const " in line:
                    continue            # a const array is read-only data compared with the game's bytes
                self.assertIsNone(CODE_ARRAY.search(line),
                                  f"{path.name}:{number}: a code buffer in data; VirtualProtect it executable "
                                  f"(PAGE_EXECUTE_READWRITE) or move it into .text, and extend this test")

    def test_no_jump_opcodes_are_written_into_buffers(self) -> None:
        for path in SOURCES:
            for number, line in code_lines(path):
                self.assertIsNone(WRITES_OPCODE.search(line),
                                  f"{path.name}:{number}: writes an opcode into a buffer; make that buffer executable")

    def test_every_site_patch_goes_through_virtualprotect(self) -> None:
        sites = (NATIVE / "ftfp_ds_fish" / "install_sites.h").read_text(encoding="utf-8")
        self.assertIn("PAGE_EXECUTE_READWRITE", sites)


if __name__ == "__main__":
    unittest.main()
