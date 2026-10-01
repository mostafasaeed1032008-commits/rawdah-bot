@echo off
setlocal enabledelayedexpansion
title NusukBot PC - Test Connection ^& Preflight
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
    echo يرجى تحميل وتثبيت بايثون مع تحديد خيار Add to PATH من:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ============================================================
echo   Running NusukBot PC Connection Test ^& Preflight...
echo ============================================================
"%PY_CMD%" test_connection.py
pause
