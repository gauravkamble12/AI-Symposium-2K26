#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "[run-dev] Missing virtual environment. Run ./scripts/bootstrap.sh first."
  exit 1
fi

cleanup() {
  echo ""
  echo "[run-dev] Stopping services..."
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

echo "[run-dev] Starting backend on :8000"
cd "$ROOT_DIR"
"$VENV_PY" -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "[run-dev] Starting frontend on :5173"
cd "$ROOT_DIR/frontend"
npm run dev -- --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

echo "[run-dev] Frontend: http://localhost:5173"
echo "[run-dev] Backend:  http://localhost:8000"
echo "[run-dev] Press Ctrl+C to stop both"

wait "$BACKEND_PID" "$FRONTEND_PID"
