#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="$ROOT_DIR/.venv"

echo "[bootstrap] Project root: $ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[bootstrap] Error: python3 not found"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[bootstrap] Error: npm not found"
  exit 1
fi

if [[ ! -d "$VENV_PATH" ]]; then
  echo "[bootstrap] Creating Python virtual environment..."
  python3 -m venv "$VENV_PATH"
fi

echo "[bootstrap] Installing backend dependencies..."
"$VENV_PATH/bin/python" -m pip install --upgrade pip
"$VENV_PATH/bin/python" -m pip install -r "$ROOT_DIR/backend/requirements.txt"

echo "[bootstrap] Installing frontend dependencies..."
cd "$ROOT_DIR/frontend"
npm install

echo "[bootstrap] Done. Run: ./scripts/run-dev.sh"
