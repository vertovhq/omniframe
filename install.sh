#!/usr/bin/env bash
# ARGUS Studio — установка одной командой:
#   bash install.sh
set -e
cd "$(dirname "$0")"

echo "[1/4] Python-пакет + dev-зависимости + озвучка (edge-tts)..."
pip install -e ".[dev,pretty,voice]"

echo "[2/4] Playwright Chromium (нужен только для Veo provider='flow')..."
pip install -e ".[flow]" >/dev/null 2>&1 && python -m playwright install chromium || \
  echo "  пропущено: поставишь позже — pip install -e '.[flow]' && playwright install chromium"

echo "[3/4] Kinetic-движок (Node.js 18+ требуется)..."
(cd engine && npm install --no-audit --no-fund)

echo "[4/4] .env..."
[ -f .env ] || cp .env.example .env
echo "Готово. Впиши ARGUS_GEMINI_API_KEY в .env (https://aistudio.google.com/apikey) — и перезапусти свой AI-клиент."
