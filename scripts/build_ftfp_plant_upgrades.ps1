$ErrorActionPreference = "Stop"

# "Store Upgrades and Items.dll": the store's Upgrades view in Plant Tycoon (see native/ftfp_plant_upgrades/ftfp_plant_upgrades.c).
# Regenerate native/ftfp_plant_upgrades/upgrade_sites.h first with
# scripts/build_plant_upgrades_headers.py. Shipped from assets\plant_tycoon_upgrades.
# Same toolchain and flags as the Virtual Villagers Fun Patcher's companions:
# MSVC x86, static CRT, kernel32 and user32 (Time Warp's popups), /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_plant_upgrades"
$outputRoot = Join-Path $projectRoot "assets\plant_tycoon_upgrades"
$buildRoot = Join-Path $projectRoot "build\ftfp_plant_upgrades"
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
    (Join-Path $nativeRoot "ftfp_plant_upgrades.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_plant_upgrades.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_plant_upgrades.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "Store Upgrades and Items.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib `
    user32.lib
if ($LASTEXITCODE -ne 0) {
    throw "Store Upgrades and Items.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Store Upgrades and Items.dll") | Format-List
