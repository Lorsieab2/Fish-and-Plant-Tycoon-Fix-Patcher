$ErrorActionPreference = "Stop"

# "Extra Supply Slots.dll": the "Extra supply slots" setting (see native/ftfp_supply_slots/ftfp_supply_slots.c).
# Regenerate native/ftfp_supply_slots/slot_sites.h first with scripts/build_supply_slots_headers.py. Shipped from assets\fish_tycoon_supply_slots.
# Same toolchain and flags as the Virtual Villagers Fun Patcher's companions:
# MSVC x86, static CRT, kernel32 and user32 (as tests/store_emulator.py rebuilds it), /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_supply_slots"
$outputRoot = Join-Path $projectRoot "assets\fish_tycoon_supply_slots"
$buildRoot = Join-Path $projectRoot "build\ftfp_supply_slots"
$sdkRoot = "C:\Program Files (x86)\Windows Kits\10"
$sdkVersion = "10.0.26100.0"
$vsTools = "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231"

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null

& (Join-Path $vsTools "bin\Hostx64\x86\cl.exe") `
    /nologo `
    /LD `
    /O2 `
    /MT `
    /W4 `
    /WX `
    /GS- `
    /Brepro `
    ("/Fo" + $buildRoot + "\") `
    /I (Join-Path $vsTools "include") `
    /I (Join-Path $sdkRoot "Include\$sdkVersion\um") `
    /I (Join-Path $sdkRoot "Include\$sdkVersion\shared") `
    /I (Join-Path $sdkRoot "Include\$sdkVersion\ucrt") `
    (Join-Path $nativeRoot "ftfp_supply_slots.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_supply_slots.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_supply_slots.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "Extra Supply Slots.dll")) `
    /BASE:0x13000000 `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib `
    user32.lib
if ($LASTEXITCODE -ne 0) {
    throw "Extra Supply Slots.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Extra Supply Slots.dll") | Format-List


