@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "NO_PAUSE=0"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"

REM Keep Hugging Face models and uv cache inside .\tools\.cache (avoids filling C: drive)
if not exist "tools\.cache\huggingface" mkdir "tools\.cache\huggingface"
if not exist "tools\.cache\uv" mkdir "tools\.cache\uv"
set "HF_HOME=%~dp0tools\.cache\huggingface"
set "HUGGINGFACE_HUB_CACHE=%~dp0tools\.cache\huggingface\hub"
set "UV_CACHE_DIR=%~dp0tools\.cache\uv"

echo ========================================================================
echo   StoryTube Studio - Local Image Pipeline Installer (Windows)
echo ========================================================================
echo   Model cache: %HF_HOME%
echo.

REM ------------------------------------------------------------------------
REM 1. Check Python 3.10+, Git, and FFmpeg
REM ------------------------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python 3.10+ not found in PATH.
    echo        Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python 3.10 or newer is required.
    echo        Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo [PASS] Python %PY_VER%

where git >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Git is not installed or not in PATH.
    echo        Download: https://git-scm.com/downloads/win
    pause
    exit /b 1
)
echo [PASS] Git installed

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [FAIL] FFmpeg is not installed or not in PATH.
    echo        Install via: winget install Gyan.FFmpeg
    echo        Or download: https://www.gyan.dev/ffmpeg/builds/
    pause
    exit /b 1
)
echo [PASS] FFmpeg installed

where node >nul 2>&1
if errorlevel 1 (
    echo [WARN] Node.js 18+ not found. Frontend requires Node.js: https://nodejs.org/
) else (
    echo [PASS] Node.js installed
)

REM FastSD CPU's install.bat requires uv
where uv >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing 'uv' package manager required by FastSD CPU...
    python -m pip install --user uv --quiet
    for /f "delims=" %%U in ('python -m site --user-base') do set "PATH=%%U\Scripts;%PATH%"
)
where uv >nul 2>&1
if errorlevel 1 (
    echo [FAIL] 'uv' could not be found in PATH after install.
    echo        Install manually: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)
echo [PASS] uv installed

REM ------------------------------------------------------------------------
REM 2. Clone FastSD CPU into ./tools/fastsdcpu & run official install.bat
REM ------------------------------------------------------------------------
if not exist "tools" mkdir "tools"
if not exist "tools\fastsdcpu\.git" (
    echo.
    echo [INFO] Cloning FastSD CPU into .\tools\fastsdcpu ...
    git clone https://github.com/rupeshs/fastsdcpu.git "tools\fastsdcpu"
    if errorlevel 1 (
        echo [FAIL] Failed to clone FastSD CPU repository.
        pause
        exit /b 1
    )
) else (
    echo [INFO] .\tools\fastsdcpu already exists; pulling latest...
    pushd "tools\fastsdcpu"
    git pull --ff-only || echo [WARN] git pull skipped
    popd
)

if exist "tools\fastsdcpu\env\Scripts\python.exe" (
    echo [PASS] FastSD CPU environment already installed in .\tools\fastsdcpu\env
) else (
    echo [INFO] Running FastSD CPU official install.bat ...
    pushd "tools\fastsdcpu"
    call install.bat <nul
    if errorlevel 1 (
        popd
        echo [FAIL] FastSD CPU install.bat failed.
        if "%NO_PAUSE%"=="0" pause
        exit /b 1
    )
    popd
)

REM ------------------------------------------------------------------------
REM 3. Pre-download SD 1.5 + LCM-LoRA + Tiny AutoEncoder models
REM ------------------------------------------------------------------------
echo.
echo [INFO] Downloading SD 1.5 + LCM-LoRA models into Hugging Face cache (~4-5 GB)...
echo        Base model: Lykon/dreamshaper-8
echo        LCM-LoRA:   latent-consistency/lcm-lora-sdv1-5
echo        TAESD:      madebyollin/taesd
call "tools\fastsdcpu\env\Scripts\python.exe" -c "from huggingface_hub import snapshot_download; [snapshot_download(repo) for repo in ('Lykon/dreamshaper-8', 'latent-consistency/lcm-lora-sdv1-5', 'madebyollin/taesd')]; print('MODELS_DOWNLOADED_OK')"
if errorlevel 1 (
    echo [WARN] Model pre-download encountered an issue; FastSD CPU will download on first run.
)

REM ------------------------------------------------------------------------
REM 4. Download portable Real-ESRGAN ncnn Vulkan CLI into ./tools/upscayl/
REM ------------------------------------------------------------------------
echo.
echo [INFO] Downloading Real-ESRGAN ncnn Vulkan CLI (v0.2.5.0) into .\tools\upscayl ...
if not exist "tools\upscayl" mkdir "tools\upscayl"
if not exist "tools\upscayl\realesrgan-ncnn-vulkan.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip' -OutFile 'tools\upscayl\realesrgan.zip'; Expand-Archive -Path 'tools\upscayl\realesrgan.zip' -DestinationPath 'tools\upscayl' -Force; Remove-Item 'tools\upscayl\realesrgan.zip'"
    if not exist "tools\upscayl\realesrgan-ncnn-vulkan.exe" (
        echo [FAIL] Could not extract realesrgan-ncnn-vulkan.exe into .\tools\upscayl\
        pause
        exit /b 1
    )
)
echo [PASS] Real-ESRGAN ncnn Vulkan CLI ready (includes realesrgan-x4plus-anime)

REM ------------------------------------------------------------------------
REM 5. Setup StoryTube Studio backend venv, frontend packages, and .env
REM ------------------------------------------------------------------------
if not exist "backend\.venv" (
    echo [INFO] Creating StoryTube backend venv...
    python -m venv "backend\.venv"
)
call "backend\.venv\Scripts\activate.bat"
pip install -r "backend\requirements.txt" --quiet

if exist "frontend\package.json" (
    where npm >nul 2>&1
    if not errorlevel 1 (
        if not exist "frontend\node_modules" (
            echo [INFO] Installing frontend npm packages...
            pushd frontend
            call npm install --silent
            popd
        )
    )
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
)
python -c "from pathlib import Path; p=Path('.env'); lines=p.read_text(encoding='utf-8').splitlines(); updates={'DEFAULT_PROVIDER':'local_sd','FASTSD_URL':'http://127.0.0.1:8000','UPSCAYL_BIN':'./tools/upscayl/realesrgan-ncnn-vulkan.exe'}; out=[f'{k}={updates[k]}' if (k:=l.split('=',1)[0].strip()) in updates else l for l in lines]; seen={l.split('=',1)[0].strip() for l in lines if '=' in l}; out.extend(f'{k}={v}' for k,v in updates.items() if k not in seen); p.write_text('\n'.join(out)+'\n', encoding='utf-8')"
echo [PASS] .env configured with FASTSD_URL and UPSCAYL_BIN

REM ------------------------------------------------------------------------
REM 6. Self-test: generate 512x288 image via FastSD CPU and upscale 4x -> 1920x1080
REM ------------------------------------------------------------------------
echo.
echo [INFO] Running local pipeline self-test (512x288 generation + 4x upscale)...
backend\.venv\Scripts\python.exe -c "import sys, tempfile; from pathlib import Path; from PIL import Image; sys.path.insert(0, 'backend'); from app.services import local_image_service; print('--- Self-Test Results ---'); local_image_service.ensure_fastsd_running(); svc = local_image_service.check_services(); print(('PASS' if svc['fastsd_ok'] else 'FAIL') + ': FastSD CPU -> ' + svc['fastsd_message']); print(('PASS' if svc['upscayl_ok'] else 'FAIL') + ': Real-ESRGAN -> ' + svc['upscayl_message']); (sys.exit(1) if not svc['fastsd_ok'] else None); td = tempfile.TemporaryDirectory(); tdp = Path(td.name); raw = tdp / 'test_512.png'; up = tdp / 'test_1080p.png'; local_image_service.generate_image(prompt=local_image_service.build_local_sd_prompt('sunlit green meadow with a small wooden cottage'), negative_prompt='photo, realistic, blurry, text, watermark', seed=123456, out_path=raw); im = Image.open(raw); print('PASS: Generated base image size =', im.size); im.close(); _, warn = local_image_service.upscale_image(raw, up); im2 = Image.open(up); print('WARN: ' + warn if warn else 'PASS: Upscaled & fitted size = ' + str(im2.size)); im2.close(); td.cleanup()"
if errorlevel 1 (
    echo [WARN] Self-test did not complete cleanly. See fix instructions above.
) else (
    echo [PASS] End-to-end local image self-test succeeded!
)

echo.
echo ========================================================================
echo   FINAL MANUAL CHECKLIST
echo ========================================================================
echo   1. Open .env and set GEMINI_API_KEY (needed for script, scenes, TTS, SEO).
echo   2. Run start.bat to launch FastSD CPU, StoryTube Backend, and Frontend.
echo   3. Open http://localhost:5173 and click 'Test One Image' on Step 6.
echo ========================================================================
if "%NO_PAUSE%"=="0" pause
