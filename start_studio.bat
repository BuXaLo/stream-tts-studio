@echo off
chcp 65001 >nul
title TTS Studio Monitor
setlocal
set "BASE_DIR=%~dp0"
set "PYTHONW=%BASE_DIR%cosyvoice3\upy\pythonw.exe"
set "LAUNCHER=%BASE_DIR%server\launcher.pyw"

if not exist "%PYTHONW%" (
    echo [INFO] pythonw.exe не найден. Запускается резервный консольный режим.
    call "%BASE_DIR%start_server.bat"
    exit /b
)

if not exist "%LAUNCHER%" (
    echo [ERROR] Не найден загрузчик: "%LAUNCHER%"
    pause
    exit /b 1
)

set "STUDIO_MONITOR_MODE=1"
start "TTS Studio" "%PYTHONW%" "%LAUNCHER%"
exit /b 0
