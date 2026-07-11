@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0Git Helper v5.exe" (
    start "" "%~dp0Git Helper v5.exe"
    exit /b
)

python -c "import PyQt6" >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0launch_git_helper_v5.pyw"
    exit /b
)

if exist "%~dp0launch_git_helper_v5.pyw" (
    echo Git Helper needs PyQt6, but the selected Python does not have it.
    echo Building the standalone app avoids this requirement.
    echo.
)

echo Git Helper v5.exe is missing or could not be opened.
pause
