$ErrorActionPreference = "Stop"

# "Sort Seeds.dll": the Sort Seeds button on Plant Tycoon's Seed Storage screen (see native/ftfp_sort_seeds/ftfp_sort_seeds.c).
# Same toolchain and flags as the Virtual Villagers Fun Patcher's companions:
# MSVC x86, static CRT, kernel32 only, /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_sort_seeds"
$outputRoot = Join-Path $projectRoot "assets\plant_tycoon_sort_seeds"
$buildRoot = Join-Path $projectRoot "build\ftfp_sort_seeds"
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
    (Join-Path $nativeRoot "ftfp_sort_seeds.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_sort_seeds.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_sort_seeds.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "Sort Seeds.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib
if ($LASTEXITCODE -ne 0) {
    throw "Sort Seeds.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Sort Seeds.dll") | Format-List

# The logic harness (tests/test_sort_seeds.py reads its output).
& (Join-Path $vsTools "bin\Hostx64\x86\cl.exe") `
    /nologo /O2 /MT /W4 /WX /GS- `
    ("/Fo" + $buildRoot + "\") `
    ("/Fe" + (Join-Path $buildRoot "sort_seeds_logic_harness.exe")) `
    /I (Join-Path $vsTools "include") `
    /I (Join-Path $sdkRoot "Include\$sdkVersion\um") `
    /I (Join-Path $sdkRoot "Include\$sdkVersion\shared") `
    /I (Join-Path $sdkRoot "Include\$sdkVersion\ucrt") `
    (Join-Path $nativeRoot "sort_seeds_logic_harness.c") `
    /link `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    kernel32.lib
if ($LASTEXITCODE -ne 0) {
    throw "The Sort Seeds logic harness failed to compile."
}
& (Join-Path $buildRoot "sort_seeds_logic_harness.exe") | Out-File -Encoding ascii (Join-Path $buildRoot "logic.txt")
