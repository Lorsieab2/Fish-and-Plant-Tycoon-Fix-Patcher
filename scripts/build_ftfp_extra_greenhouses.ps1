$ErrorActionPreference = "Stop"

# "Extra Greenhouses.dll": five more greenhouses in Plant Tycoon (see native/ftfp_extra_greenhouses/ftfp_extra_greenhouses.c).
# Regenerate native/ftfp_extra_greenhouses/greenhouse_sites.h first with
# scripts/build_extra_greenhouses_headers.py. Shipped from assets\plant_tycoon_greenhouses.
# Same toolchain and flags as the Virtual Villagers Fun Patcher's companions:
# MSVC x86, static CRT, kernel32 only, /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_extra_greenhouses"
$outputRoot = Join-Path $projectRoot "assets\plant_tycoon_greenhouses"
$buildRoot = Join-Path $projectRoot "build\ftfp_extra_greenhouses"
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
    (Join-Path $nativeRoot "ftfp_extra_greenhouses.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_extra_greenhouses.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_extra_greenhouses.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "Extra Greenhouses.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib
if ($LASTEXITCODE -ne 0) {
    throw "Extra Greenhouses.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Extra Greenhouses.dll") | Format-List

