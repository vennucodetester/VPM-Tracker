@echo off
setlocal
title VPM Tracker Rev Up
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0rev_up.py"
    pause
    exit /b
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0rev_up.py"
    pause
    exit /b
)

if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "%~dp0rev_up.py"
    pause
    exit /b
)

echo Python was not found. Install Python, then try this launcher again.
pause
