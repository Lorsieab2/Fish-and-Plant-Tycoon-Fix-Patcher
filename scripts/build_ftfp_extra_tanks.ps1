$ErrorActionPreference = "Stop"

# "Extra Tanks.dll": the "3 extra tanks" setting (see native/ftfp_extra_tanks/ftfp_extra_tanks.c).
# Regenerate native/ftfp_extra_tanks/tank_sites.h first with scripts/build_extra_tanks_headers.py. Shipped from assets\fish_tycoon_extra_tanks.
# Same toolchain and flags as the Virtual Villagers Fun Patcher's companions:
# MSVC x86, static CRT, kernel32 and user32 (as tests/store_emulator.py rebuilds it), /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_extra_tanks"
$outputRoot = Join-Path $projectRoot "assets\fish_tycoon_extra_tanks"
$buildRoot = Join-Path $projectRoot "build\ftfp_extra_tanks"
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
    (Join-Path $nativeRoot "ftfp_extra_tanks.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_extra_tanks.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_extra_tanks.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "Extra Tanks.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib `
    user32.lib
if ($LASTEXITCODE -ne 0) {
    throw "Extra Tanks.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Extra Tanks.dll") | Format-List


