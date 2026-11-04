$ErrorActionPreference = "Stop"

# "Snail and Curing.dll": the Cleaning Snail and the Plant of Curing stack
# (see native/ftfp_snail_curing/ftfp_snail_curing.c).
# Shipped from assets\fish_tycoon_snail_curing; pin it with scripts/pin_snail_curing.py.
# Same toolchain and flags as the other companions (and tests/store_emulator.py):
# MSVC x86, static CRT, /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_snail_curing"
$outputRoot = Join-Path $projectRoot "assets\fish_tycoon_snail_curing"
$buildRoot = Join-Path $projectRoot "build\ftfp_snail_curing"
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
    (Join-Path $nativeRoot "ftfp_snail_curing.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_snail_curing.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_snail_curing.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "Snail and Curing.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib `
    user32.lib
if ($LASTEXITCODE -ne 0) {
    throw "Snail and Curing.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Snail and Curing.dll") | Format-List
