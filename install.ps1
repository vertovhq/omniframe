# ARGUS Studio: one-step install for Windows.
#   powershell -ExecutionPolicy Bypass -File install.ps1
# Run it inside an activated virtual environment (.venv), see INSTALL.md.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[1/3] Python package, dev tools, pretty output and the edge-tts voice..."
pip install -e ".[dev,pretty,voice]"

Write-Host "[2/3] Remotion render engine (needs Node.js 18 or newer)..."
Push-Location engine
npm install --no-audit --no-fund
Pop-Location

Write-Host "[3/3] .env file..."
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
Write-Host "Done. Optional: add ARGUS_GEMINI_API_KEY to .env (https://aistudio.google.com/apikey), then reload your MCP client."
