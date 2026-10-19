[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BundlePath,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedCommit,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$ExpectedSha256,

    [string]$PythonExecutable = 'python',
    [string]$HilExecutable = 'agentic-hil',
    [switch]$AllowDirty
)

$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
$resolvedBundle = (Resolve-Path -LiteralPath $BundlePath).Path
$pythonCommand = (Get-Command $PythonExecutable -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$hilCommand = (Get-Command $HilExecutable -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$arguments = @(
    (Join-Path $PSScriptRoot 'hil_artifact.py'),
    '--bundle', $resolvedBundle,
    '--expected-commit', $ExpectedCommit.ToLowerInvariant(),
    '--expected-sha256', $ExpectedSha256.ToLowerInvariant(),
    '--hil-executable', $hilCommand
)
if ($AllowDirty) {
    $arguments += '--allow-dirty'
}

Push-Location -LiteralPath $workspacePath
try {
    & $pythonCommand @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Verified artifact HIL failed with exit code $LASTEXITCODE. See the recorded evidence path."
    }
}
finally {
    Pop-Location
}
