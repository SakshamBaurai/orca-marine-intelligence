@echo off
title ORCA - Marine Intelligence & 3D Globe System
cd /d "%~dp0"

echo ===================================================
echo   Starting ORCA Marine Intelligence System...
echo ===================================================

echo [1/2] Launching FastAPI Backend on http://localhost:8000...
set PYTHONPATH=%cd%;%cd%\orca_forecasting
start "ORCA Backend" cmd /k "title ORCA Backend && .\.venv\Scripts\python.exe -m uvicorn orca_forecasting.service.app:app --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak >nul

echo [2/2] Launching Frontend Preview on http://localhost:3000...
start "ORCA Frontend" cmd /k "title ORCA Frontend && npx vite preview --port 3000 --host 127.0.0.1"

timeout /t 2 /nobreak >nul

echo Opening ORCA Globe in your default browser...
start http://localhost:3000/globe.html

echo.
echo ===================================================
echo   ORCA is running! Keep the terminal windows open.
echo   URL: http://localhost:3000/globe.html
echo ===================================================
