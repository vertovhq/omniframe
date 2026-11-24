#!/usr/bin/env bash
# ARGUS Studio: one-step install for macOS and Linux.
#   bash install.sh
# Run it inside an activated virtual environment (.venv), see INSTALL.md.
set -e
cd "$(dirname "$0")"

echo "[1/3] Python package, dev tools, pretty output and the edge-tts voice..."
pip install -e ".[dev,pretty,voice]"

echo "[2/3] Remotion render engine (needs Node.js 18 or newer)..."
(cd engine && npm install --no-audit --no-fund)

echo "[3/3] .env file..."
[ -f .env ] || cp .env.example .env
echo "Done. Optional: add ARGUS_GEMINI_API_KEY to .env (https://aistudio.google.com/apikey), then reload your MCP client."
