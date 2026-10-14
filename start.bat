@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title TG Agent

if not exist ".venv\Scripts\python.exe" (
    echo [TG Agent] Creating virtual environment...
    py -3 -m venv .venv 2>/dev/null || python -m venv .venv || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
)

rem Reinstall dependencies whenever requirements.txt changes
fc /b requirements.txt ".venv\requirements.installed" >/dev/null 2>&1
if errorlevel 1 (
    echo [TG Agent] Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || (echo Dependency installation failed & pause & exit /b 1)
    copy /y requirements.txt ".venv\requirements.installed" >nul
)

".venv\Scripts\python.exe" -X utf8 -m tgagent %*
if errorlevel 1 pause
