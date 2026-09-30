#!/usr/bin/env bash
# One-time setup: Python venv + deps, spaCy model, Tesseract (if apt available), frontend deps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if command -v apt-get >/dev/null 2>&1 && ! command -v tesseract >/dev/null 2>&1; then
  (sudo apt-get update && sudo apt-get install -y tesseract-ocr) || echo "tesseract not installed (OCR for scanned PDFs disabled)"
fi
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements-dev.txt
.venv/bin/python -m spacy download en_core_web_sm -q || true
[ -f .env ] || cp .env.example .env
cd frontend && npm ci --no-audit --no-fund
echo "Setup complete. Start with: scripts/dev.sh"
