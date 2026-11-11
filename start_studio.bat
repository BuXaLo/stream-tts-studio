@echo off
chcp 65001 >nul
title TTS Studio Monitor
setlocal
set "BASE_DIR=%~dp0"
set "PYTHONW=%BASE_DIR%cosyvoice3\upy\pythonw.exe"
set "APP=%BASE_DIR%server\app.py"

if not exist "%PYTHONW%" (
    echo [INFO] pythonw.exe не найден. Запускается резервный консольный режим.
    call "%BASE_DIR%start_server.bat"
    exit /b %errorlevel%
)

set "STUDIO_MONITOR_MODE=1"
start "TTS Studio" "%PYTHONW%" "%APP%"
exit /b 0
