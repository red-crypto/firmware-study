[CmdletBinding()]
param(
    [switch]$Release,
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'

$workspacePath = Split-Path -Parent $PSScriptRoot
$firmwarePath = Join-Path $workspacePath 'f411_blinky'
$targetName = 'thumbv7em-none-eabihf'
$profileName = if ($Release) { 'release' } else { 'debug' }

$cargoArguments = @('build', '--locked')
if ($Release) {
    $cargoArguments += '--release'
}
if ($Offline) {
    $cargoArguments += '--offline'
}

Push-Location -LiteralPath $firmwarePath
try {
    # Run here so Cargo loads this firmware project's .cargo/config.toml.
    & cargo @cargoArguments
    $cargoExitCode = $LASTEXITCODE
    if ($cargoExitCode -ne 0) {
        throw "cargo build failed with exit code $cargoExitCode."
    }

    $targetDirectory = Join-Path $firmwarePath 'target'
    $buildDirectory = Join-Path (Join-Path $targetDirectory $targetName) $profileName
    $builtImage = Join-Path $buildDirectory 'f411_blinky'
    $hilImage = Join-Path $buildDirectory 'f411_blinky.elf'

    if (-not (Test-Path -LiteralPath $builtImage -PathType Leaf)) {
        throw "Cargo succeeded, but the expected firmware was not found: $builtImage. Check whether CARGO_TARGET_DIR overrides this project's target directory."
    }

    # Cargo's bare-metal executable is already ELF; only give the copy an extension.
    Copy-Item -LiteralPath $builtImage -Destination $hilImage -Force
    $builtHash = (Get-FileHash -LiteralPath $builtImage -Algorithm SHA256).Hash
    $hilHash = (Get-FileHash -LiteralPath $hilImage -Algorithm SHA256).Hash
    if ($builtHash -ne $hilHash) {
        throw 'The HIL firmware copy does not match the Cargo build artifact.'
    }

    $relativeImage = 'f411_blinky/target/{0}/{1}/f411_blinky.elf' -f $targetName, $profileName
    Write-Output "Image path: $relativeImage"
    Write-Output "SHA256: $hilHash"
}
finally {
    Pop-Location
}
