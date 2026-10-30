$ErrorActionPreference = "Stop"

# "Optimize Prices.dll" for both games: the Optimize Prices button on Fish Tycoon's Species
# Chart (native/ftfp_fish_prices) and in Plant Tycoon's Nursery (native/ftfp_plant_prices),
# both on the price maths in native/common/price_math.h.
# Same toolchain and flags as the other companions (and tests/store_emulator.py's rebuild):
# MSVC x86, static CRT, /Brepro for a byte-identical rebuild.

$projectRoot = Split-Path -Parent $PSScriptRoot
$sdkRoot = "C:\Program Files (x86)\Windows Kits\10"
$sdkVersion = "10.0.26100.0"
$vsTools = "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231"

foreach ($game in @(@("ftfp_fish_prices", "fish_tycoon_optimize_prices"), @("ftfp_plant_prices", "plant_tycoon_optimize_prices"))) {
    $project = $game[0]
    $nativeRoot = Join-Path $projectRoot "native\$project"
    $outputRoot = Join-Path $projectRoot ("assets\" + $game[1])
    $buildRoot = Join-Path $projectRoot "build\$project"
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
        (Join-Path $nativeRoot "$project.c") `
        /link `
        /Brepro `
        ("/DEF:" + (Join-Path $nativeRoot "$project.def")) `
        ("/LIBPATH:" + (Join-Path $vsTools "lib\x86")) `
        ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\um\x86")) `
        ("/LIBPATH:" + (Join-Path $sdkRoot "Lib\$sdkVersion\ucrt\x86")) `
        ("/IMPLIB:" + (Join-Path $buildRoot "$project.lib")) `
        ("/OUT:" + (Join-Path $outputRoot "Optimize Prices.dll")) `
        /RELEASE `
        /SAFESEH:NO `
        kernel32.lib `
        user32.lib
    if ($LASTEXITCODE -ne 0) {
        throw "$project compilation failed."
    }
    Get-FileHash -Algorithm SHA256 (Join-Path $outputRoot "Optimize Prices.dll") | Format-List
}
