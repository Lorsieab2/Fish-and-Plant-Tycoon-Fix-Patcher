$ErrorActionPreference = "Stop"

# "Greenhouse Counts.dll": the plant counts on Plant Tycoon's greenhouse screen
# (see native/ftfp_greenhouse_counts/ftfp_greenhouse_counts.c).
# Shipped from assets\plant_tycoon_counts; pin it with scripts/pin_counts.py.
# Same toolchain and flags as the other companions (and tests/store_emulator.py):
# MSVC x86, static CRT, /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_greenhouse_counts"
$outputRoot = Join-Path $projectRoot "assets\plant_tycoon_counts"
$buildRoot = Join-Path $projectRoot "build\ftfp_greenhouse_counts"
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
    (Join-Path $nativeRoot "ftfp_greenhouse_counts.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_greenhouse_counts.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_greenhouse_counts.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "Greenhouse Counts.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib `
    user32.lib
if ($LASTEXITCODE -ne 0) {
    throw "Greenhouse Counts.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Greenhouse Counts.dll") | Format-List
