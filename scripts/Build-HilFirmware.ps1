[CmdletBinding()]
param(
    [switch]$Release,
    [switch]$Offline,
    [string]$ArtifactDirectory = 'artifacts/firmware',
    [string]$PythonExecutable = 'python'
)

$ErrorActionPreference = 'Stop'

$workspacePath = Split-Path -Parent $PSScriptRoot
$firmwarePath = Join-Path $workspacePath 'f411_blinky'
$targetName = 'thumbv7em-none-eabihf'
$profileName = if ($Release) { 'release' } else { 'debug' }
$artifactTool = Join-Path $PSScriptRoot 'firmware_artifact.py'
if (-not [IO.Path]::IsPathRooted($ArtifactDirectory)) {
    $ArtifactDirectory = Join-Path $workspacePath $ArtifactDirectory
}
$ArtifactDirectory = [IO.Path]::GetFullPath($ArtifactDirectory)

# Keep the configured linker flags and output location reproducible. A changed
# build environment needs an explicit contract instead of silently reusing ELF.
foreach ($overrideName in @('CARGO_TARGET_DIR', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_TARGET_THUMBV7EM_NONE_EABIHF_RUSTFLAGS')) {
    if ([Environment]::GetEnvironmentVariable($overrideName)) {
        throw "$overrideName is set. Remove this build override before producing the standard HIL artifact."
    }
}

$snapshotOutput = & $PythonExecutable $artifactTool snapshot --workspace $workspacePath
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to record the firmware source snapshot.'
}
$sourceSnapshot = ($snapshotOutput -join "`n") | ConvertFrom-Json

$cargoArguments = @('build', '--locked', '--target', $targetName)
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

    $packageArguments = @(
        $artifactTool, 'create', '--workspace', $workspacePath,
        '--image', $hilImage, '--output', $ArtifactDirectory,
        '--profile', $profileName,
        '--expected-source-fingerprint', $sourceSnapshot.fingerprint,
        '--expected-commit', $sourceSnapshot.commit
    )
    if ($Offline) { $packageArguments += '--offline' }
    $manifestOutput = & $PythonExecutable @packageArguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to package the firmware artifact with matching source provenance.'
    }
    $manifest = ($manifestOutput -join "`n") | ConvertFrom-Json

    $relativeImage = 'f411_blinky/target/{0}/{1}/f411_blinky.elf' -f $targetName, $profileName
    Write-Output "Image path: $relativeImage"
    Write-Output "SHA256: $($hilHash.ToLowerInvariant())"
    Write-Output "Artifact directory: $ArtifactDirectory"
    Write-Output "Source commit: $($manifest.source.commit)"
    Write-Output "Source dirty: $($manifest.source.dirty)"
}
finally {
    Pop-Location
}
