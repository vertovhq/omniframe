# ARGUS Studio: one-step install for Windows.
#   powershell -ExecutionPolicy Bypass -File install.ps1
# Run it inside an activated virtual environment (.venv), see INSTALL.md.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[1/4] Python package, dev tools, pretty output and the edge-tts voice..."
pip install -e ".[dev,pretty,voice]"

Write-Host "[2/4] Playwright Chromium (only for the optional Flow route, provider='flow')..."
try {
  pip install -e ".[flow]" 2>$null
  python -m playwright install chromium
} catch {
  Write-Host "  skipped. You can add it later: pip install -e '.[flow]'; python -m playwright install chromium"
}

Write-Host "[3/4] Remotion render engine (needs Node.js 18 or newer)..."
Push-Location engine
npm install --no-audit --no-fund
Pop-Location

Write-Host "[4/4] .env file..."
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
Write-Host "Done. Optional: add ARGUS_GEMINI_API_KEY to .env (https://aistudio.google.com/apikey), then reload your MCP client."
