# ARGUS Studio: one-step install for Windows.
#   powershell -ExecutionPolicy Bypass -File install.ps1
# Needs Python 3.11+, Node.js 18+ and ffmpeg on PATH (see INSTALL.md). Creates .venv if it is missing.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "[0/4] Virtual environment .venv..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "python -m venv failed: is Python 3.11+ installed and on PATH?" }
}

Write-Host "[1/4] Python package, dev tools, pretty output and the edge-tts voice..."
& $py -m pip install -e ".[dev,pretty,voice]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "[2/4] Remotion render engine (needs Node.js 18 or newer)..."
Push-Location engine
npm install --no-audit --no-fund
$npmExit = $LASTEXITCODE
Pop-Location
if ($npmExit -ne 0) { throw "npm install failed" }

Write-Host "[3/4] .env file..."
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }

Write-Host "[4/4] Adding ARGUS to your AI IDEs (an existing argus entry is kept)..."
& (Join-Path $PSScriptRoot ".venv\Scripts\argus-install.exe")

Write-Host "Done. Restart your IDE. Optional: add keys to .env (ElevenLabs or Gemini voice); the free edge voice works without keys."
