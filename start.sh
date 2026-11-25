#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "=================================================="
echo "  StoryTube Studio - Mac/Linux Launcher"
echo "=================================================="

if [ ! -f ".env" ]; then
  echo "[INFO] .env not found. Creating from .env.example..."
  cp ".env.example" ".env"
  echo "[WARN] Please edit .env and set your GEMINI_API_KEY before generating content!"
fi

FASTSD_URL_VAL="$(grep -E '^FASTSD_URL=' .env | tail -n1 | cut -d'=' -f2- | tr -d '\r' || true)"
FASTSD_URL_VAL="${FASTSD_URL_VAL:-http://127.0.0.1:8000}"
BACKEND_PORT_VAL="$(grep -E '^BACKEND_PORT=' .env | tail -n1 | cut -d'=' -f2- | tr -d '\r' || true)"
BACKEND_PORT_VAL="${BACKEND_PORT_VAL:-8001}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] Python 3.10+ is required."
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "[ERROR] Node.js 18+ is required."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[WARN] FFmpeg not found in PATH. Install on Mac via: brew install ffmpeg"
fi

if [ ! -d "backend/.venv" ]; then
  echo "[INFO] Creating Python virtual environment in backend/.venv..."
  python3 -m venv "backend/.venv"
fi

source "backend/.venv/bin/activate"
echo "[INFO] Installing/updating backend dependencies..."
pip install -r "backend/requirements.txt" --quiet

if [ ! -d "frontend/node_modules" ]; then
  echo "[INFO] Installing frontend dependencies..."
  (cd frontend && npm install)
fi

FASTSD_PID=""
cleanup() {
  echo ""
  echo "[INFO] Shutting down StoryTube Studio..."
  kill "${BACKEND_PID:-0}" "${FRONTEND_PID:-0}" "${FASTSD_PID:-0}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

mkdir -p "$ROOT_DIR/tools/.cache/huggingface"
export HF_HOME="$ROOT_DIR/tools/.cache/huggingface"
export HUGGINGFACE_HUB_CACHE="$ROOT_DIR/tools/.cache/huggingface/hub"

echo "[INFO] Checking FastSD CPU local image server at ${FASTSD_URL_VAL}..."
if python3 -c "import sys, httpx; u='${FASTSD_URL_VAL}'.rstrip('/'); sys.exit(0 if any(httpx.get(u+p, timeout=2.0).status_code<500 for p in ('/api/info','/api/config','/api/docs')) else 1)" >/dev/null 2>&1; then
  echo "[OK]   FastSD CPU is already running at ${FASTSD_URL_VAL}"
elif [ -x "tools/fastsdcpu/start-webserver.sh" ] || [ -f "tools/fastsdcpu/src/app.py" ]; then
  echo "[INFO] Launching FastSD CPU API server from ./tools/fastsdcpu..."
  (cd "$ROOT_DIR/tools/fastsdcpu" && ./start-webserver.sh) &
  FASTSD_PID=$!
  sleep 4
else
  echo "[WARN] FastSD CPU is not running and ./tools/fastsdcpu was not found."
  echo "       Run ./setup_local.sh first to install FastSD CPU + Real-ESRGAN locally."
fi

echo "[INFO] Starting StoryTube FastAPI backend on http://127.0.0.1:${BACKEND_PORT_VAL} ..."
(cd "$ROOT_DIR/backend" && uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT_VAL}" --reload) &
BACKEND_PID=$!

sleep 2

echo "[INFO] Starting Vite frontend on http://localhost:5173 ..."
(cd "$ROOT_DIR/frontend" && npm run dev) &
FRONTEND_PID=$!

echo ""
echo "[READY] StoryTube Studio is running!"
echo "  Frontend:   http://localhost:5173"
echo "  Backend:    http://127.0.0.1:${BACKEND_PORT_VAL}/docs"
echo "  FastSD CPU: ${FASTSD_URL_VAL}/api/docs"
echo "  Press Ctrl+C to stop all servers."
echo ""

wait
