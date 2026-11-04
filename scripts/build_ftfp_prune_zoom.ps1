$ErrorActionPreference = "Stop"

# "Prune Zoom.dll": the greenhouse zooms in on the plant under the shears (see
# native/ftfp_prune_zoom/ftfp_prune_zoom.c). A loader tail. Shipped from
# assets\plant_tycoon_prune_zoom.
# Same toolchain and flags as the Virtual Villagers Fun Patcher companions:
# MSVC x86, static CRT, kernel32 only, /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $projectRoot "native\ftfp_prune_zoom"
$outputRoot = Join-Path $projectRoot "assets\plant_tycoon_prune_zoom"
$buildRoot = Join-Path $projectRoot "build\ftfp_prune_zoom"
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
    (Join-Path $nativeRoot "ftfp_prune_zoom.c") `
    /link `
    /Brepro `
    ("/DEF:" + (Join-Path $nativeRoot "ftfp_prune_zoom.def")) `
    ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
    ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
    ("/IMPLIB:" + (Join-Path $buildRoot "ftfp_prune_zoom.lib")) `
    ("/OUT:" + (Join-Path $outputRoot "Prune Zoom.dll")) `
    /RELEASE `
    /SAFESEH:NO `
    kernel32.lib
if ($LASTEXITCODE -ne 0) {
    throw "Prune Zoom.dll compilation failed."
}
Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Prune Zoom.dll") | Format-List

