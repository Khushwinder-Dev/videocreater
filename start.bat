@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==================================================
echo   StoryTube Studio - Windows Launcher
echo ==================================================

if not exist ".env" (
    echo [INFO] .env not found. Creating from .env.example...
    copy ".env.example" ".env" >nul
    echo [WARN] Please edit .env and set your GEMINI_API_KEY before generating content!
)

set "FASTSD_CHECK_URL=http://127.0.0.1:8000"
set "BACKEND_PORT_VAL=8001"
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if /I "%%A"=="FASTSD_URL" set "FASTSD_CHECK_URL=%%B"
    if /I "%%A"=="BACKEND_PORT" set "BACKEND_PORT_VAL=%%B"
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10+ is required and was not found in PATH.
    pause
    exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js 18+ is required and was not found in PATH.
    pause
    exit /b 1
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [WARN] FFmpeg was not found in PATH. Video rendering and audio conversion require FFmpeg.
    echo        Install via: winget install Gyan.FFmpeg
)

if not exist "backend\.venv" (
    echo [INFO] Creating Python virtual environment in backend\.venv...
    python -m venv "backend\.venv"
)

echo [INFO] Installing/updating StoryTube backend dependencies...
call "backend\.venv\Scripts\activate.bat"
pip install -r "backend\requirements.txt" --quiet

if not exist "tools\.cache\huggingface" mkdir "tools\.cache\huggingface"
set "HF_HOME=%~dp0tools\.cache\huggingface"
set "HUGGINGFACE_HUB_CACHE=%~dp0tools\.cache\huggingface\hub"

echo [INFO] Checking FastSD CPU API server at !FASTSD_CHECK_URL! ...
python -c "import sys, httpx; u='!FASTSD_CHECK_URL!'.rstrip('/'); sys.exit(0 if any(httpx.get(u+p, timeout=2.0).status_code<500 for p in ('/api/info','/api/config','/api/docs')) else 1)" >nul 2>&1
if errorlevel 1 (
    if exist "tools\fastsdcpu\start-webserver.bat" (
        echo [INFO] Starting FastSD CPU API server from .\tools\fastsdcpu ...
        start "FastSD CPU Server" cmd /k "cd /d "%~dp0tools\fastsdcpu" && call start-webserver.bat"
        timeout /t 4 /nobreak >nul
    ) else (
        echo [WARN] FastSD CPU is not running and .\tools\fastsdcpu was not found.
        echo        Run setup_local.bat first to install FastSD CPU + Real-ESRGAN locally.
    )
) else (
    echo [OK]   FastSD CPU is already running at !FASTSD_CHECK_URL!
)

if not exist "frontend\node_modules" (
    echo [INFO] Installing frontend dependencies...
    pushd frontend
    call npm install
    popd
)

echo [INFO] Starting StoryTube FastAPI backend on http://127.0.0.1:!BACKEND_PORT_VAL! ...
start "StoryTube Backend" cmd /k "cd /d "%~dp0backend" && call .venv\Scripts\activate.bat && uvicorn app.main:app --host 127.0.0.1 --port !BACKEND_PORT_VAL! --reload"

echo [INFO] Waiting 3 seconds for backend startup...
timeout /t 3 /nobreak >nul

echo [INFO] Starting Vite frontend on http://localhost:5173 ...
start "StoryTube Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo [READY] StoryTube Studio is launching!
echo   Frontend:   http://localhost:5173
echo   Backend:    http://127.0.0.1:!BACKEND_PORT_VAL!/docs
echo   FastSD CPU: !FASTSD_CHECK_URL!/api/docs
echo.
pause
