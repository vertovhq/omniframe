#!/usr/bin/env bash
# ARGUS Studio: one-step install for macOS and Linux.
#   bash install.sh
# Run it inside an activated virtual environment (.venv), see INSTALL.md.
set -e
cd "$(dirname "$0")"

echo "[1/4] Python package, dev tools, pretty output and the edge-tts voice..."
pip install -e ".[dev,pretty,voice]"

echo "[2/4] Playwright Chromium (only for the optional Flow route, provider='flow')..."
pip install -e ".[flow]" >/dev/null 2>&1 && python -m playwright install chromium || \
  echo "  skipped. You can add it later: pip install -e '.[flow]' && python -m playwright install chromium"

echo "[3/4] Remotion render engine (needs Node.js 18 or newer)..."
(cd engine && npm install --no-audit --no-fund)

echo "[4/4] .env file..."
[ -f .env ] || cp .env.example .env
echo "Done. Optional: add ARGUS_GEMINI_API_KEY to .env (https://aistudio.google.com/apikey), then reload your MCP client."
