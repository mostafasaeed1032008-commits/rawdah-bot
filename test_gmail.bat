@echo off
setlocal
title NusukBot PC - Gmail OTP Test
cd /d "%~dp0"

set "PY_CMD="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY_CMD if exist "C:\Users\win10\AppData\Local\Programs\Python\Python312\python.exe" set "PY_CMD=C:\Users\win10\AppData\Local\Programs\Python\Python312\python.exe"
if not defined PY_CMD if exist "%ProgramFiles%\Python312\python.exe" set "PY_CMD=%ProgramFiles%\Python312\python.exe"
if not defined PY_CMD where py >nul 2>&1 && set "PY_CMD=py -3"

if not defined PY_CMD (
    echo [ERROR] Python 3.12 was not found.
    pause
    exit /b 1
)

"%PY_CMD%" test_gmail.py
echo.
echo ============================================================
echo   Press any key to close the window...
echo ============================================================
pause >nul
