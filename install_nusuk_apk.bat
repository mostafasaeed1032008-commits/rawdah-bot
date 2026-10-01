@echo off
setlocal
title NusukBot PC - Install Nusuk APK on MuMu
cd /d "%~dp0"

set "ADB_BIN=%~dp0platform-tools\adb.exe"
if not exist "%ADB_BIN%" set "ADB_BIN=adb"

echo ============================================================
echo   Installing Nusuk App on MuMu Player...
echo ============================================================

if not exist "%~dp0Nusuk.apk" (
    echo [ERROR] Nusuk.apk was not found in the project directory!
    pause
    exit /b 1
)

echo [1/2] Connecting to MuMu Player...
"%ADB_BIN%" connect 127.0.0.1:16384
"%ADB_BIN%" connect 127.0.0.1:7555

echo.
echo [2/2] Installing Nusuk.apk (239MB - please wait 1-2 minutes)...
"%ADB_BIN%" install -r "%~dp0Nusuk.apk"

if errorlevel 1 (
    echo.
    echo [ERROR] Installation failed.
    echo Make sure MuMu Player is open and running, or drag and drop Nusuk.apk directly into MuMu window.
) else (
    echo.
    echo ============================================================
    echo   Nusuk App installed successfully on MuMu Player!
    echo ============================================================
)
pause
