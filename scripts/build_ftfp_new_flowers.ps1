$ErrorActionPreference = "Stop"

# "FTFP New Flowers.dll": the 14 new flowers in Plant Tycoon (see native/ftfp_new_flowers/ftfp_new_flowers.c).
# Regenerate native/ftfp_new_flowers/flower_sites.h and flower_stubs.h first with
# scripts/build_new_flowers_headers.py. Shipped from assets\plant_tycoon_flowers.
# Same toolchain and flags as the Virtual Villagers Fun Patcher's companions:
# MSVC x86, static CRT, kernel32 only, /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_new_flowers"
$outputRoot = Join-Path $projectRoot "assets\plant_tycoon_flowers"
$buildRoot = Join-Path $projectRoot "build\ftfp_new_flowers"
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
    (Join-Path $nativeRoot "ftfp_new_flowers.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_new_flowers.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_new_flowers.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "FTFP New Flowers.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib
if ($LASTEXITCODE -ne 0) {
    throw "FTFP New Flowers.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "FTFP New Flowers.dll") | Format-List
