@echo off
setlocal
title NusukBot PC - Connect to MuMu Player
cd /d "%~dp0"

set "ADB_BIN=%~dp0platform-tools\adb.exe"
if not exist "%ADB_BIN%" set "ADB_BIN=adb"

echo ============================================================
echo   Connecting to MuMu Player via ADB...
echo ============================================================

echo [1/3] Starting ADB server...
"%ADB_BIN%" start-server

echo [2/3] Connecting to MuMu Player (Port 16384 and fallback ports)...
"%ADB_BIN%" connect 127.0.0.1:16384
"%ADB_BIN%" connect 127.0.0.1:7555
"%ADB_BIN%" connect 127.0.0.1:5555

echo.
echo [3/3] Connected devices:
"%ADB_BIN%" devices

echo.
echo ============================================================
echo   If you see '127.0.0.1:16384 device' above, MuMu is ready!
echo ============================================================
pause
