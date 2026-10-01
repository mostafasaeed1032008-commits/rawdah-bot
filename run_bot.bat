@echo off
setlocal enabledelayedexpansion
title NusukBot PC - Web Dashboard
cd /d "%~dp0"

:: Add bundled platform-tools to PATH
if exist "%~dp0platform-tools" set "PATH=%~dp0platform-tools;%PATH%"

set "PY_CMD="
where python >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"
if not defined PY_CMD (
    where py >nul 2>&1 && set "PY_CMD=py -3"
)
if not defined PY_CMD (
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        "%ProgramFiles%\Python312\python.exe"
        "%ProgramFiles%\Python311\python.exe"
        "%ProgramFiles%\Python310\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
    ) do (
        if exist %%P (
            set "PY_CMD=%%~P"
            goto :found_python
        )
    )
)

:found_python
if not defined PY_CMD (
    echo [ERROR] لم يتم العثور على بايثون (Python) في هذا الجهاز!
    echo يرجى تحميل بايثون من الموقع الرسمي وتثبيته مع تفعيل Add to PATH:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ============================================================
echo   Starting NusukBot PC Web Dashboard Server...
echo ============================================================
echo Python: %PY_CMD%
echo Opening browser at http://localhost:5000 ...
start "" "http://localhost:5000"
"%PY_CMD%" app_server.py
if errorlevel 1 (
    echo.
    echo [ERROR] Web Dashboard exited with an error.
    pause
)
