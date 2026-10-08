<#
.SYNOPSIS
    One-time setup of StudyMate on Windows. Safe to run again.

.DESCRIPTION
    1. Checks that Python 3.11 and Node.js 22.12+ are installed (stops with a clear message if not).
    2. Creates the Python environment backend\.venv (reused if it exists) and installs the
       backend's packages.
    3. Creates backend\.env from backend\.env.example ONLY if backend\.env doesn't exist yet.
       An existing backend\.env is never overwritten, read or printed.
    4. Installs the frontend's packages and builds it into frontend\dist.

    It never touches backend\data (your documents and conversations).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>

# Native programs (py, pip, npm) report failure through $LASTEXITCODE, checked after each call.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
$envFile = Join-Path $backend ".env"
$envExample = Join-Path $backend ".env.example"

$MinNode = [version]"22.12.0"

function Write-Step([string]$message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Stop-Setup([string]$message) {
    Write-Host ""
    Write-Host "Setup stopped: $message" -ForegroundColor Red
    exit 1
}

# Run a native program and stop if it fails. Its output is shown as it runs.
function Invoke-Checked([string]$what, [scriptblock]$command) {
    & $command
    if ($LASTEXITCODE -ne 0) {
        Stop-Setup "$what failed (exit code $LASTEXITCODE). See the messages above."
    }
}

# --- 1. Check the tools first, before installing anything ---

Write-Step "Checking Python 3.11"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Stop-Setup ("the Python launcher 'py' was not found. Install Python 3.11 from " +
        "https://www.python.org/downloads/ (keep 'py launcher' ticked), then open a new " +
        "PowerShell window and run this script again.")
}
# "Continue" for this one call: in Windows PowerShell, error text from a program whose
# errors are redirected (2>$null) would otherwise stop the script with a raw error
# instead of the clear message below.
$ErrorActionPreference = "Continue"
$pythonVersion = (& py -3.11 -c "import sys; print(sys.version.split()[0])" 2>$null)
$pyExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($pyExit -ne 0 -or -not $pythonVersion) {
    Stop-Setup ("Python 3.11 is not installed (the 'py' launcher found no 3.11). Install " +
        "Python 3.11 from https://www.python.org/downloads/, then run this script again.")
}
Write-Host "Python $pythonVersion found."

Write-Step "Checking Node.js ($MinNode or newer)"
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or
    -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Stop-Setup ("Node.js was not found. Install the LTS version (22 or 24) from " +
        "https://nodejs.org/, then open a new PowerShell window and run this script again.")
}
$nodeText = (& node --version).TrimStart("v")
if ([version]$nodeText -lt $MinNode) {
    Stop-Setup ("Node.js $nodeText is too old: StudyMate needs $MinNode or newer. Install the " +
        "LTS version (22 or 24) from https://nodejs.org/, then run this script again.")
}
Write-Host "Node.js $nodeText found."

# --- 2. Backend environment and packages ---

Write-Step "Python environment (backend\.venv)"
if (Test-Path $venvPython) {
    Write-Host "backend\.venv already exists: reusing it."
} else {
    Invoke-Checked "Creating backend\.venv" { py -3.11 -m venv (Join-Path $backend ".venv") }
    Write-Host "Created backend\.venv."
}

Write-Step "Installing the backend's packages (the first time this takes several minutes)"
Invoke-Checked "Installing the backend's packages" {
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $backend "requirements.txt")
}

# --- 3. backend\.env: create it once, never overwrite or print it ---

Write-Step "Settings file (backend\.env)"
if (Test-Path $envFile) {
    Write-Host "backend\.env already exists: left unchanged."
} else {
    # Only reached when backend\.env doesn't exist (the Test-Path check above). That check
    # is what protects an existing .env: Copy-Item itself WOULD overwrite a file.
    Copy-Item -Path $envExample -Destination $envFile
    Write-Host "Created backend\.env from backend\.env.example."
    Write-Host "Open backend\.env and put your Gemini API key after GEMINI_API_KEY=" -ForegroundColor Yellow
}

# --- 4. Frontend packages and build ---

Write-Step "Installing the frontend's packages"
Push-Location $frontend
try {
    # npm ci installs exactly what package-lock.json lists, and never changes it.
    Invoke-Checked "Installing the frontend's packages" { npm.cmd ci --no-audit --no-fund }

    Write-Step "Building the frontend (frontend\dist)"
    Invoke-Checked "Building the frontend" { npm.cmd run build }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next:"
Write-Host "  1. Make sure backend\.env contains your key: GEMINI_API_KEY=<your key>"
Write-Host "  2. Start StudyMate:  powershell -ExecutionPolicy Bypass -File scripts\start.ps1"
