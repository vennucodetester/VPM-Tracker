@echo off
setlocal
cd /d "%~dp0"
set "GIT_HELPER_TARGET_DIR=%~dp0..\..\.."

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0git_helper_v4.py"
    exit /b
)

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3 "%~dp0git_helper_v4.py"
    exit /b
)

echo Python was not found. Install Python, then try this launcher again.
pause
