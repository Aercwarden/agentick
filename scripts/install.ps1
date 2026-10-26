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
$needsBootstrap = $true
if (-not $DryRun) {
    & (Join-Path $BinDir "python.exe") -c 'from importlib.metadata import version; from pip._vendor.packaging.version import Version; import sys; sys.exit(Version(version("pip")) < Version("26.2.2"))'
    $needsBootstrap = $LASTEXITCODE -ne 0
}
if ($needsBootstrap) {
    Run (Join-Path $BinDir "python.exe") @("-m", "pip", "install", "--upgrade", "--require-hashes", "--only-binary=:all:", "-r", (Join-Path $ProjectRoot "scripts/bootstrap-requirements.txt"))
}
Run (Join-Path $BinDir "python.exe") @("-m", "pip", "install", "--upgrade", "pip>=26.2.2")
Run (Join-Path $BinDir "python.exe") @("-m", "pip", "install", "--upgrade", "--upgrade-strategy", "eager", "-e", $ProjectRoot)

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
