$ErrorActionPreference = "Stop"

# "Unicode Text.dll" (Fish Tycoon): "Render Unicode with In-Game Fonts" -- typing
# and drawing Latin-1 (see native/ftfp_fish_unicode/ftfp_fish_unicode.c). Its fonts
# come from scripts/build_unicode_assets.py. Shipped from assets\fish_tycoon_unicode;
# after a rebuild, update the DLL's size and SHA-256 in data/fish_manifest.json.
# Same toolchain and flags as the other companions (and tests/store_emulator.py):
# MSVC x86, static CRT, /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_fish_unicode"
$outputRoot = Join-Path $projectRoot "assets\fish_tycoon_unicode"
$buildRoot = Join-Path $projectRoot "build\ftfp_fish_unicode"
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
    (Join-Path $nativeRoot "ftfp_fish_unicode.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_fish_unicode.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_fish_unicode.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "Unicode Text.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib `
    user32.lib
if ($LASTEXITCODE -ne 0) {
    throw "Unicode Text.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Unicode Text.dll") | Format-List
