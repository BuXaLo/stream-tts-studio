@echo off
chcp 65001 >nul
title "TTS Studio and OBS Overlay Backend"

set "BASE_DIR=%~dp0"
set "PYTHON=%BASE_DIR%cosyvoice3\upy\python.exe"
set "APP=%BASE_DIR%server\app.py"


"%PYTHON%" -u "%APP%"

if errorlevel 1 (
    echo.
    echo [ERROR] Сервер завершил работу с ошибкой.
    pause
)