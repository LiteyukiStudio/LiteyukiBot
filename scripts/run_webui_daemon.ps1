[CmdletBinding()]
param(
    [ValidateSet("Open", "Start", "Status", "Stop")]
    [string]$Action = "Open",
    [string]$Workspace,
    [ValidateRange(0, 65535)]
    [int]$Port = 0,
    [ValidatePattern("^[a-z0-9](?:[a-z0-9-]{0,62})$")]
    [string]$Instance = "default",
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = Join-Path $RepositoryRoot "tmp\webui-daemon"
}
$Workspace = [System.IO.Path]::GetFullPath($Workspace)

function Invoke-Checked {
    param(
        [Parameter(Mandatory)]
        [string]$Command,
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

function Invoke-Liteyuki {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $commandArguments = @(
        "run", "--extra", "webui", "liteyuki", "--workspace", $Workspace, "--instance", $Instance
    ) + $Arguments
    Invoke-Checked -Command "uv" -Arguments $commandArguments
}

function Get-WebUiStatus {
    $nativeErrorPreference = Get-Variable -Name "PSNativeCommandUseErrorActionPreference" -ErrorAction SilentlyContinue
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # A missing descriptor is normal before the first detached daemon starts.
        $ErrorActionPreference = "Continue"
        if ($null -ne $nativeErrorPreference) {
            Set-Variable -Name "PSNativeCommandUseErrorActionPreference" -Value $false -Scope Local
        }
        $output = & uv run --package liteyukibot-v7-webui --extra server liteyuki --workspace $Workspace --instance $Instance web status 2>$null
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        if ($null -ne $nativeErrorPreference) {
            Remove-Variable -Name "PSNativeCommandUseErrorActionPreference" -Scope Local -ErrorAction SilentlyContinue
        }
    }
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return ($output | Out-String | ConvertFrom-Json)
}

function Write-WebUiEndpoint {
    param([Parameter(Mandatory)]$Status)

    Write-Host ("WebUI: http://{0}:{1}" -f $Status.host, $Status.port)
}

function Initialize-Workspace {
    if (-not (Test-Path (Join-Path $Workspace "liteyuki.toml"))) {
        Invoke-Liteyuki @("init", "--non-interactive", "--locale", "en-US") | Out-Host
    }
}

function Build-WebUi {
    if ($SkipBuild) {
        return
    }
    Invoke-Checked "pnpm" @("--dir", (Join-Path $RepositoryRoot "webui"), "install", "--frozen-lockfile") | Out-Host
    Invoke-Checked "pnpm" @("--dir", (Join-Path $RepositoryRoot "webui"), "build") | Out-Host
    Invoke-Checked "uv" @("run", "python", "scripts/stage_webui_assets.py") | Out-Host
}

function Start-WebUi {
    Initialize-Workspace
    Build-WebUi

    $status = Get-WebUiStatus
    if ($null -ne $status -and $status.state -eq "running") {
        return $status
    }

    Invoke-Liteyuki @("--set", "webui.mode=always", "--set", "webui.port=$Port", "run", "--detach") | Out-Host
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 250
        $status = Get-WebUiStatus
        if ($null -ne $status -and $status.state -eq "running") {
            return $status
        }
    }
    throw "daemon started but the WebUI did not become ready; inspect '$Workspace\.liteyuki\instances\$Instance\logs\daemon.log'"
}

Push-Location $RepositoryRoot
try {
    switch ($Action) {
        "Start" {
            $status = Start-WebUi
            Write-WebUiEndpoint $status
            $status | ConvertTo-Json -Compress
        }
        "Open" {
            $status = Start-WebUi
            Write-WebUiEndpoint $status
            $status | ConvertTo-Json -Compress
            Invoke-Liteyuki @("web", "open")
        }
        "Status" {
            $status = Get-WebUiStatus
            if ($null -eq $status) {
                throw "no running daemon WebUI for workspace '$Workspace' and instance '$Instance'"
            }
            $status | ConvertTo-Json -Compress
        }
        "Stop" {
            Invoke-Liteyuki @("instance", "stop")
        }
    }
}
finally {
    Pop-Location
}
