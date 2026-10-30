$ErrorActionPreference = "Stop"

# "Multiple Ornaments.dll": decorative copies of the tank ornaments (see native/ftfp_ornaments/ftfp_ornaments.c).
# Regenerate native/ftfp_ornaments/orn_sites.h first with scripts/build_ornaments_headers.py.
# Shipped from assets\fish_tycoon_ornaments. Same toolchain and flags as the other companions:
# MSVC x86, static CRT, kernel32 and user32, /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_ornaments"
$outputRoot = Join-Path $projectRoot "assets\fish_tycoon_ornaments"
$buildRoot = Join-Path $projectRoot "build\ftfp_ornaments"
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
    (Join-Path $nativeRoot "ftfp_ornaments.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_ornaments.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_ornaments.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "Multiple Ornaments.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib `
    user32.lib
if ($LASTEXITCODE -ne 0) {
    throw "Multiple Ornaments.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Multiple Ornaments.dll") | Format-List
