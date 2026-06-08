param(
    [string]$Prefix = "$HOME\.agentick\venv",
    [string]$Python = "python",
    [switch]$DryRun,
    [switch]$NoUserPath
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Prefix = [System.IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Prefix))
$BinDir = Join-Path $Prefix "Scripts"
$AgcBin = Join-Path $BinDir "agc.exe"

function Info($msg) { Write-Host $msg -ForegroundColor Cyan }
function Neon($msg) { Write-Host $msg -ForegroundColor Magenta }
function Run($cmd, $arguments) {
    if ($DryRun) {
        Write-Host "  $cmd $arguments"
    } else {
        & $cmd @arguments
        if ($LASTEXITCODE -ne 0) { throw "Command failed: $cmd $arguments" }
    }
}

Neon "▰ Agentick installer"
Info "Project: $ProjectRoot"
Info "Prefix:  $Prefix"
Info "Python:  $Python"

if ($DryRun) { Write-Host "DRY RUN — no files will be created." -ForegroundColor Yellow }

$pythonCmd = Get-Command $Python -ErrorAction SilentlyContinue
if (-not $pythonCmd) { throw "Python executable not found: $Python" }

Run $Python @("-m", "venv", $Prefix)
Run (Join-Path $BinDir "python.exe") @("-m", "pip", "install", "--upgrade", "pip")
Run (Join-Path $BinDir "python.exe") @("-m", "pip", "install", "-e", $ProjectRoot)

if (-not $NoUserPath -and -not $DryRun) {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($currentPath -split ';') -notcontains $BinDir) {
        [Environment]::SetEnvironmentVariable("Path", "$BinDir;$currentPath", "User")
        Write-Host "Added Agentick to your user PATH for new terminals: $BinDir"
    } else {
        Write-Host "User PATH already contains Agentick: $BinDir"
    }
}

if (-not $DryRun) {
    if (-not (Test-Path $AgcBin)) { throw "Install completed but agc was not found at $AgcBin" }
    & $AgcBin --help *> $null
}

Write-Host ""
Neon "Agentick installed."
Write-Host "agc is installed at: $AgcBin"
if (-not $NoUserPath) {
    Write-Host "Open a new PowerShell window, or run this now:"
    Write-Host "  `$env:Path = '$BinDir;' + `$env:Path"
}
Write-Host ""
Write-Host "Then configure your provider:"
Write-Host "  agc setup"
Write-Host ""
Write-Host "Quick smoke test without API calls:"
Write-Host "  `$env:AGC_MOCK_RESPONSE='hello'; agc <task-name> --headless"
