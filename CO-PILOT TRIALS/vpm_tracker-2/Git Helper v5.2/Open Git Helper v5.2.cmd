@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0Git Helper v5.2.exe" (
    start "" "%~dp0Git Helper v5.2.exe"
    exit /b
)

python -c "import PyQt6" >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0launch_git_helper_v5_2.pyw"
    exit /b
)

echo Git Helper v5.2.exe is missing and this Python does not have PyQt6.
echo Use the standalone exe build in this folder, or ask Claude to rebuild it.
echo.
pause
