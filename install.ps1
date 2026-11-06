# ARGUS Studio — установка одной командой:
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[1/4] Python-пакет + dev-зависимости + озвучка (edge-tts)..."
pip install -e ".[dev,pretty,voice]"

Write-Host "[2/4] Playwright Chromium (нужен только для Veo provider='flow')..."
try {
  pip install -e ".[flow]" 2>$null
  python -m playwright install chromium
} catch {
  Write-Host "  пропущено: поставишь позже — pip install -e '.[flow]'; playwright install chromium"
}

Write-Host "[3/4] Kinetic-движок (Node.js 18+ требуется)..."
Push-Location engine
npm install --no-audit --no-fund
Pop-Location

Write-Host "[4/4] .env..."
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
Write-Host "Готово. Впиши ARGUS_GEMINI_API_KEY в .env (https://aistudio.google.com/apikey) — и перезапусти свой AI-клиент."
