#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p tools/.cache/huggingface tools/.cache/uv
export HF_HOME="$ROOT_DIR/tools/.cache/huggingface"
export HUGGINGFACE_HUB_CACHE="$ROOT_DIR/tools/.cache/huggingface/hub"
export UV_CACHE_DIR="$ROOT_DIR/tools/.cache/uv"

echo "========================================================================"
echo "  StoryTube Studio - Local Image Pipeline Installer (Mac / Linux)"
echo "========================================================================"
echo "  Model cache: $HF_HOME"
echo ""

# ------------------------------------------------------------------------
# 1. Check Python 3.10+, Git, and FFmpeg
# ------------------------------------------------------------------------
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "[FAIL] Python 3.10+ not found. Download: https://www.python.org/downloads/"
  exit 1
fi

if ! "$PYTHON_BIN" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"; then
  echo "[FAIL] Python 3.10 or newer is required. Download: https://www.python.org/downloads/"
  exit 1
fi
echo "[PASS] $($PYTHON_BIN --version)"

if ! command -v git >/dev/null 2>&1; then
  echo "[FAIL] Git not found. Install: https://git-scm.com/downloads"
  exit 1
fi
echo "[PASS] Git installed"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[FAIL] FFmpeg not found. Mac: 'brew install ffmpeg' | Linux: 'sudo apt install ffmpeg'"
  exit 1
fi
echo "[PASS] FFmpeg installed"

if ! command -v uv >/dev/null 2>&1; then
  echo "[INFO] Installing 'uv' package manager required by FastSD CPU..."
  "$PYTHON_BIN" -m pip install --user uv --quiet || curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "[FAIL] 'uv' not found in PATH. Install: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi
echo "[PASS] uv installed"

# ------------------------------------------------------------------------
# 2. Clone FastSD CPU into ./tools/fastsdcpu & run official installer
# ------------------------------------------------------------------------
mkdir -p tools
if [ ! -d "tools/fastsdcpu/.git" ]; then
  echo "[INFO] Cloning FastSD CPU into ./tools/fastsdcpu ..."
  git clone https://github.com/rupeshs/fastsdcpu.git tools/fastsdcpu
else
  echo "[INFO] ./tools/fastsdcpu already exists; pulling latest..."
  (cd tools/fastsdcpu && git pull --ff-only || true)
fi

OS_NAME="$(uname -s)"
echo "[INFO] Running FastSD CPU official installer..."
pushd tools/fastsdcpu >/dev/null
if [ "$OS_NAME" = "Darwin" ] && [ -f "install-mac.sh" ]; then
  chmod +x install-mac.sh
  echo "" | ./install-mac.sh
else
  chmod +x install.sh
  echo "" | ./install.sh
fi
chmod +x start-webserver.sh || true
popd >/dev/null

# ------------------------------------------------------------------------
# 3. Pre-download SD 1.5 + LCM-LoRA + TAESD weights
# ------------------------------------------------------------------------
echo ""
echo "[INFO] Pre-downloading SD 1.5 + LCM-LoRA models (~4-5 GB)..."
"tools/fastsdcpu/env/bin/python" -c "
from huggingface_hub import snapshot_download
for repo in ('Lykon/dreamshaper-8', 'latent-consistency/lcm-lora-sdv1-5', 'madebyollin/taesd'):
    snapshot_download(repo)
print('MODELS_DOWNLOADED_OK')
" || echo "[WARN] Model pre-download skipped; FastSD CPU will download on first generation."

# ------------------------------------------------------------------------
# 4. Download portable Real-ESRGAN ncnn Vulkan CLI into ./tools/upscayl/
# ------------------------------------------------------------------------
echo ""
mkdir -p tools/upscayl
if [ "$OS_NAME" = "Darwin" ]; then
  RE_URL="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-macos.zip"
else
  RE_URL="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip"
fi

if [ ! -f "tools/upscayl/realesrgan-ncnn-vulkan" ]; then
  echo "[INFO] Downloading Real-ESRGAN ncnn Vulkan CLI from $RE_URL ..."
  curl -L "$RE_URL" -o tools/upscayl/realesrgan.zip
  unzip -o tools/upscayl/realesrgan.zip -d tools/upscayl >/dev/null
  rm -f tools/upscayl/realesrgan.zip
  chmod +x tools/upscayl/realesrgan-ncnn-vulkan
fi
echo "[PASS] Real-ESRGAN ncnn Vulkan CLI ready (includes realesrgan-x4plus-anime)"

# ------------------------------------------------------------------------
# 5. Setup StoryTube Studio backend venv, frontend packages, and .env
# ------------------------------------------------------------------------
if [ ! -d "backend/.venv" ]; then
  "$PYTHON_BIN" -m venv backend/.venv
fi
source backend/.venv/bin/activate
pip install -r backend/requirements.txt --quiet

if [ -d "frontend" ] && command -v npm >/dev/null 2>&1 && [ ! -d "frontend/node_modules" ]; then
  (cd frontend && npm install --silent)
fi

if [ ! -f ".env" ]; then
  cp .env.example .env
fi

"$PYTHON_BIN" -c "
from pathlib import Path
p = Path('.env')
lines = p.read_text(encoding='utf-8').splitlines()
updates = {
    'DEFAULT_PROVIDER': 'local_sd',
    'FASTSD_URL': 'http://127.0.0.1:8000',
    'UPSCAYL_BIN': './tools/upscayl/realesrgan-ncnn-vulkan',
}
out = []
seen = set()
for line in lines:
    k = line.split('=', 1)[0].strip() if '=' in line else ''
    if k in updates:
        out.append(f'{k}={updates[k]}')
        seen.add(k)
    else:
        out.append(line)
for k, v in updates.items():
    if k not in seen:
        out.append(f'{k}={v}')
p.write_text('\n'.join(out) + '\n', encoding='utf-8')
"
echo "[PASS] .env configured with FASTSD_URL and UPSCAYL_BIN"

# ------------------------------------------------------------------------
# 6. Self-test: generate 512x288 image via FastSD CPU and upscale 4x -> 1920x1080
# ------------------------------------------------------------------------
echo ""
echo "[INFO] Running local pipeline self-test (512x288 generation + 4x upscale)..."
backend/.venv/bin/python -c "
import sys, tempfile
from pathlib import Path
from PIL import Image

sys.path.insert(0, 'backend')
from app.services import local_image_service

print('--- Self-Test Results ---')
local_image_service.ensure_fastsd_running()
svc = local_image_service.check_services()
print(('PASS' if svc['fastsd_ok'] else 'FAIL') + ': FastSD CPU -> ' + svc['fastsd_message'])
print(('PASS' if svc['upscayl_ok'] else 'FAIL') + ': Real-ESRGAN -> ' + svc['upscayl_message'])
if not svc['fastsd_ok']:
    print('FIX: Start FastSD CPU manually: cd tools/fastsdcpu && ./start-webserver.sh')
    sys.exit(1)

with tempfile.TemporaryDirectory() as td:
    tdp = Path(td)
    raw = tdp / 'test_512.png'
    up = tdp / 'test_1080p.png'
    local_image_service.generate_image(
        prompt=local_image_service.build_local_sd_prompt('sunlit green meadow with a small wooden cottage'),
        negative_prompt='photo, realistic, blurry, text, watermark',
        seed=123456,
        out_path=raw,
    )
    with Image.open(raw) as im:
        print('PASS: Generated base image size =', im.size)
    _, warn = local_image_service.upscale_image(raw, up)
    with Image.open(up) as im2:
        print(('WARN: ' + warn if warn else 'PASS: Upscaled & fitted size = ' + str(im2.size)))
" || echo "[WARN] Self-test did not complete cleanly. See fix instructions above."

echo ""
echo "========================================================================"
echo "  FINAL MANUAL CHECKLIST"
echo "========================================================================"
echo "  1. Open .env and set GEMINI_API_KEY (needed for script, scenes, TTS, SEO)."
echo "  2. Run ./start.sh to launch FastSD CPU, StoryTube Backend, and Frontend."
echo "  3. Open http://localhost:5173 and click 'Test One Image' on Step 6."
echo "========================================================================"
