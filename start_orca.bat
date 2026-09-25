@echo off
title ORCA - Marine Intelligence & 3D Globe System
cd /d "%~dp0"

echo ===================================================
echo   Starting ORCA Marine Intelligence System...
echo ===================================================

echo [1/2] Launching FastAPI Backend on http://127.0.0.1:8000...
set PYTHONPATH=%cd%;%cd%\orca_forecasting
start "ORCA Backend" cmd /k "title ORCA Backend && cd /d "%~dp0orca_forecasting" && ..\.venv\Scripts\python.exe -m uvicorn service.app:app --host 127.0.0.1 --port 8000"

timeout /t 2 /nobreak >nul

echo [2/2] Launching Frontend Server on http://127.0.0.1:5173...
start "ORCA Frontend" cmd /k "title ORCA Frontend && .\.venv\Scripts\python.exe -m http.server 5173 --directory public"

timeout /t 2 /nobreak >nul

echo Opening ORCA Globe in your default browser...
start http://127.0.0.1:5173/globe.html

echo.
echo ===================================================
echo   ORCA is running! Keep the terminal windows open.
echo   URL: http://127.0.0.1:5173/globe.html
echo ===================================================
