@echo off
setlocal
title Generate VAVE Slides
cd /d "%~dp0"

set "PORTABLE_RUNTIME=%~dp0portable-runtime"
set "PORTABLE_NODE=%PORTABLE_RUNTIME%\node.exe"
set "ARTIFACT_TOOL=%PORTABLE_RUNTIME%\node_modules\@oai\artifact-tool\dist\artifact_tool.mjs"
set "WORKBOOK=%~dp0VAVE Slide Files\VAVE-Slide-Input.xlsx"
set "POWERPOINT=%~dp0VAVE Slide Files\VAVE-Slides-Generated.pptx"
set "SLIDE_TEMPLATE=%~dp0EXTRA\VAVE-Slide-Template.pptx"
set "QA_DIR=%TEMP%\VPM-VAVE-Slides-QA"
set "VPMT_SOURCE=%~1"

if not defined VPMT_SOURCE (
    for /f "delims=" %%F in ('dir /b /a-d /o-d "%~dp0*.vpmt" 2^>nul') do if not defined VPMT_SOURCE set "VPMT_SOURCE=%~dp0%%F"
)

if not exist "%PORTABLE_NODE%" (
    echo The folder-local portable Node runtime is missing:
    echo %PORTABLE_NODE%
    goto :failed
)
if not exist "%ARTIFACT_TOOL%" (
    echo The folder-local PowerPoint generation library is missing:
    echo %ARTIFACT_TOOL%
    goto :failed
)
if not exist "%SLIDE_TEMPLATE%" (
    echo The internal VAVE PowerPoint template is missing:
    echo %SLIDE_TEMPLATE%
    echo Restore the EXTRA folder before running this command.
    goto :failed
)
if not exist "%WORKBOOK%" (
    echo The editable VAVE Excel input is missing:
    echo %WORKBOOK%
    echo Restore VAVE-Slide-Input.xlsx before running this command.
    goto :failed
)
if not defined VPMT_SOURCE (
    echo No .vpmt source file was found in:
    echo %~dp0
    echo Copy the current .vpmt file into this folder or drag it onto Generate VAVE Slides.cmd.
    goto :failed
)
if not exist "%VPMT_SOURCE%" (
    echo The .vpmt source file does not exist:
    echo %VPMT_SOURCE%
    goto :failed
)

echo [1/3] Refreshing Excel from the current VPM Tracker file...
echo %VPMT_SOURCE%
"%PORTABLE_NODE%" "%~dp0EXTRA\sync_vave_input.mjs" --vpmt "%VPMT_SOURCE%" --xlsx "%WORKBOOK%"
if errorlevel 1 goto :failed

echo.
echo [2/3] Reading the refreshed editable Excel input...
echo %WORKBOOK%

echo.
echo [3/3] Building the editable, automatically paginated VAVE slides...
"%PORTABLE_NODE%" "%~dp0EXTRA\generate_vave_slides.mjs" --xlsx "%WORKBOOK%" --template "%SLIDE_TEMPLATE%" --out "%POWERPOINT%" --qa-dir "%QA_DIR%"
if errorlevel 1 goto :failed

echo.
echo VAVE SLIDES CREATED
echo %POWERPOINT%
if not "%VPM_VALIDATE_NO_OPEN%"=="1" start "" "%POWERPOINT%"
if not "%VPM_VALIDATE_NO_PAUSE%"=="1" pause
exit /b 0

:failed
echo.
echo VAVE SLIDE GENERATION FAILED
echo If the files exist, close VAVE-Slide-Input.xlsx and VAVE-Slides-Generated.pptx, then try again.
if not "%VPM_VALIDATE_NO_PAUSE%"=="1" pause
exit /b 1
