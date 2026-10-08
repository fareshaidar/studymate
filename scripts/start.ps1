<#
.SYNOPSIS
    Start StudyMate: one server for the app and its API, at http://127.0.0.1:8000.

.DESCRIPTION
    Runs uvicorn app.web:site from the backend folder (so it uses backend\.env and
    backend\data), and opens the browser once the server answers. Stop it with Ctrl+C.
    Run scripts\setup.ps1 once before the first start.

    It only checks that backend\.env exists; it never reads, prints or changes it.

.PARAMETER Port
    The port to listen on (default 8000).

.PARAMETER NoBrowser
    Don't open the browser.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start.ps1
#>
param(
    [int]$Port = 8000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
$url = "http://127.0.0.1:$Port"

function Stop-Start([string]$message) {
    Write-Host ""
    Write-Host "Not started: $message" -ForegroundColor Red
    exit 1
}

$runSetup = "powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
if (-not (Test-Path $venvPython)) {
    Stop-Start "the Python environment is missing. Run setup first:  $runSetup"
}
if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) {
    Stop-Start "the frontend isn't built. Run setup first:  $runSetup"
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Stop-Start "backend\.env is missing. Run setup first:  $runSetup"
}
# Get-NetTCPConnection lists ports something is already listening on.
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Stop-Start ("port $Port is already in use (is StudyMate already running?). Close the " +
        "other program, or start on another port:  " +
        "powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Port 8001")
}

if (-not $NoBrowser) {
    # A background job waits until the server answers, then opens the browser, so the
    # page never loads before the server is ready.
    $opener = Start-Job -ArgumentList $url -ScriptBlock {
        param($url)
        for ($i = 0; $i -lt 120; $i++) {
            try {
                Invoke-WebRequest "$url/api/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
                Start-Process $url
                return
            } catch {
                Start-Sleep -Seconds 1
            }
        }
    }
}

Write-Host "Starting StudyMate at $url  (press Ctrl+C to stop)" -ForegroundColor Green
Push-Location $backend
try {
    # From backend\, so the app finds backend\.env and keeps its data in backend\data.
    & $venvPython -m uvicorn app.web:site --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
    if ($opener) {
        Remove-Job $opener -Force
    }
}
