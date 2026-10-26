$ErrorActionPreference = "Stop"

# "FTFP DS Fish.dll": the DS exclusive fish (see native/ftfp_ds_fish/ftfp_ds_fish.c).
# Regenerate native/ftfp_ds_fish/ds_sites.h and ds_data.h first with
# scripts/build_ds_fish_headers.py. Shipped from assets\fish_tycoon_ds.
# Same toolchain and flags as the Virtual Villagers Fun Patcher's companions:
# MSVC x86, static CRT, kernel32 only, /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_ds_fish"
$outputRoot = Join-Path $projectRoot "assets\fish_tycoon_ds"
$buildRoot = Join-Path $projectRoot "build\ftfp_ds_fish"
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
    (Join-Path $nativeRoot "ftfp_ds_fish.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_ds_fish.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_ds_fish.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "FTFP DS Fish.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib
if ($LASTEXITCODE -ne 0) {
    throw "FTFP DS Fish.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "FTFP DS Fish.dll") | Format-List
