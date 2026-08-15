[CmdletBinding()]
param(
    [ValidateRange(1, 100)]
    [int]$Top = 20,
    [ValidateSet("en", "zh", "ru")]
    [string]$Locale = "zh"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$arguments = @(
    "analyze",
    $RepositoryRoot,
    "--top",
    $Top,
    "--locale",
    $Locale,
    "--exclude",
    "packages/webui/src/liteyukibot_webui/static/**",
    "webui/dist/**",
    "webui/node_modules/**",
    ".venv/**",
    "**/__pycache__/**",
    "**/.mypy_cache/**",
    "**/.pytest_cache/**",
    "**/.ruff_cache/**",
    "**/target/**"
)

& fuck-u-code @arguments
if ($LASTEXITCODE -ne 0) {
    throw "fuck-u-code failed with exit code $LASTEXITCODE"
}
