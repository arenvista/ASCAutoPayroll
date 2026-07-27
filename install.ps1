# ASCAutoPayroll installer for Windows (PowerShell).
# - Installs uv (the Python package manager) if it's missing
# - Installs the app and its dependencies
# - Creates a launcher .bat and a Desktop shortcut
#
# Usage:  double-click install.bat   (or run this file from PowerShell)
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Say  ($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn ($m) { Write-Host "WARNING: $m" -ForegroundColor Yellow }

Say "Installing ASCAutoPayroll"

# 1. Ensure uv is available.
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Say "Installing uv (one-time)..."
    powershell -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    # uv installs to %USERPROFILE%\.local\bin; make it usable in this session.
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: uv is still not on PATH. Open a new terminal and run install.bat again." -ForegroundColor Red
    exit 1
}

# 2. Install the app + dependencies into a local virtual environment.
Say "Installing dependencies (this may take a minute)..."
uv sync

# 3. Firefox is required by Selenium at runtime.
$firefoxPaths = @(
    "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
    "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe"
)
$hasFirefox = ($firefoxPaths | Where-Object { Test-Path $_ }) -or `
              (Get-Command firefox -ErrorAction SilentlyContinue)
if ($hasFirefox) { Say "Firefox detected." }
else { Warn "Firefox not found. Install it from https://www.mozilla.org/firefox/ before running." }

# 4. Create a double-clickable launcher .bat.
$launcher = Join-Path $ScriptDir "AutoPayroll.bat"
@"
@echo off
cd /d "%~dp0"
uv run autopayroll
if errorlevel 1 pause
"@ | Set-Content -Encoding ASCII -Path $launcher
Say "Created launcher: AutoPayroll.bat"

# 5. Create a Desktop shortcut pointing at the launcher.
try {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcut = Join-Path $desktop "ASCAutoPayroll.lnk"
    $wsh = New-Object -ComObject WScript.Shell
    $sc = $wsh.CreateShortcut($shortcut)
    $sc.TargetPath = $launcher
    $sc.WorkingDirectory = $ScriptDir
    $sc.Save()
    Say "Created Desktop shortcut: ASCAutoPayroll"
} catch {
    Warn "Could not create a Desktop shortcut ($($_.Exception.Message)). Use AutoPayroll.bat instead."
}

Write-Host ""
Say "Done. Launch the app by double-clicking AutoPayroll.bat or the Desktop shortcut."
Write-Host "    (or run 'uv run autopayroll' from a terminal in this folder)"
