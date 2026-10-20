@echo off
title Jenni AI — Your Personal Assistant
color 0B

echo ============================================================
echo           Jenni AI — Your Personal Assistant
echo ============================================================
echo.

cd /d "%~dp0"

REM 1. Check Python virtual environment
if not exist "venv\Scripts\python.exe" (
    echo [*] Creating Python virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [!] Failed to create venv. Please ensure Python 3.10+ is installed.
        pause
        exit /b %errorlevel%
    )
    echo [*] Installing dependencies from requirements.txt...
    .\venv\Scripts\pip install -r requirements.txt
)

REM 2. Check Ollama
echo [*] Checking Ollama status...
ollama list >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Warning: Ollama could not be reached.
    echo     Please make sure Ollama is installed and running:
    echo     https://ollama.com
) else (
    echo [OK] Ollama is active.
)

REM 3. Launch Jenni AI FastAPI Backend Server
echo.
echo [*] Starting Jenni AI Server on http://localhost:8000 ...
echo [*] For Android phone access, check the Android Connect tab in dashboard.
echo.

start "" "http://localhost:8000"
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

pause
