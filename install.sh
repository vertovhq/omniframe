#!/usr/bin/env bash
# ARGUS Studio: one-step install for macOS and Linux.
#   bash install.sh
# Needs Python 3.11+, Node.js 18+ and ffmpeg on PATH (see INSTALL.md). Creates .venv if it is missing.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "[0/4] Virtual environment .venv..."
  python3 -m venv .venv
fi
PY=.venv/bin/python

echo "[1/4] Python package, dev tools, pretty output and the edge-tts voice..."
"$PY" -m pip install -e ".[dev,pretty,voice]"

echo "[2/4] Remotion render engine (needs Node.js 18 or newer)..."
(cd engine && npm install --no-audit --no-fund)

echo "[3/4] .env file..."
[ -f .env ] || cp .env.example .env

echo "[4/4] Adding ARGUS to your AI IDEs (an existing argus entry is kept)..."
.venv/bin/argus-install

echo "Done. Restart your IDE. Optional: add keys to .env (ElevenLabs or Gemini voice); the free edge voice works without keys."
