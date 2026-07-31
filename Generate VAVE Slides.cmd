@echo off
setlocal
title Generate VAVE Slides
cd /d "%~dp0"

set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "CODEX_NODE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
set "PRESENTATION_SKILL=%USERPROFILE%\.codex\plugins\cache\openai-primary-runtime\presentations\26.730.11710\skills\presentations"
set "GENERATOR_WORKSPACE=%TEMP%\VPM-VAVE-Slides"
set "WORKBOOK=%~dp0..\outputs\vave-slide-pack\VAVE-Slide-Input.xlsx"
set "SEED_WORKBOOK=%GENERATOR_WORKSPACE%\VAVE-Slide-Seed.xlsx"
set "POWERPOINT=%~dp0..\outputs\vave-slide-pack\VAVE-Slides-Generated.pptx"
set "SLIDE_TEMPLATE=%~dp0EXTRA\VAVE-Slide-Template.pptx"

if not exist "%CODEX_PYTHON%" (
    echo The bundled Codex Python runtime was not found:
    echo %CODEX_PYTHON%
    goto :failed
)
if not exist "%CODEX_NODE%" (
    echo The bundled Codex Node runtime was not found:
    echo %CODEX_NODE%
    goto :failed
)
if not exist "%PRESENTATION_SKILL%\container_tools\setup_artifact_tool_workspace.mjs" (
    echo The Codex presentation runtime was not found:
    echo %PRESENTATION_SKILL%
    goto :failed
)
if not exist "%SLIDE_TEMPLATE%" (
    echo The internal VAVE PowerPoint template is missing:
    echo %SLIDE_TEMPLATE%
    echo Restore the EXTRA folder before running this command.
    goto :failed
)

echo [1/4] Validating the Excel export logic...
"%CODEX_PYTHON%" -m unittest tests.test_vave_slide_export -v
if errorlevel 1 goto :failed

echo.
echo [2/4] Preparing the PowerPoint generation runtime...
if not exist "%GENERATOR_WORKSPACE%" mkdir "%GENERATOR_WORKSPACE%"
pushd "%USERPROFILE%"
"%CODEX_NODE%" "%PRESENTATION_SKILL%\container_tools\setup_artifact_tool_workspace.mjs" --workspace "%GENERATOR_WORKSPACE%"
set "SETUP_RESULT=%ERRORLEVEL%"
popd
if not "%SETUP_RESULT%"=="0" goto :failed
copy /Y "%~dp0EXTRA\generate_vave_slides.mjs" "%GENERATOR_WORKSPACE%\generate_vave_slides.mjs" >nul
if errorlevel 1 goto :failed
copy /Y "%~dp0EXTRA\prepare_vave_input.mjs" "%GENERATOR_WORKSPACE%\prepare_vave_input.mjs" >nul
if errorlevel 1 goto :failed

echo.
echo [3/4] Using the persistent editable Excel input...
if exist "%WORKBOOK%" (
    echo Preserving your existing workbook:
    echo %WORKBOOK%
) else (
    echo No input workbook exists yet. Creating the initial editable workbook...
    set "VPM_VAVE_VALIDATION_OUTPUT=%SEED_WORKBOOK%"
    "%CODEX_PYTHON%" "%~dp0EXTRA\validate_vave_slide_export.py"
    if errorlevel 1 goto :failed
    "%CODEX_NODE%" "%GENERATOR_WORKSPACE%\prepare_vave_input.mjs" "%SEED_WORKBOOK%" "%WORKBOOK%" "%GENERATOR_WORKSPACE%\input-qa"
    if errorlevel 1 goto :failed
)

echo.
echo [4/4] Building the editable, automatically paginated VAVE slides...
"%CODEX_NODE%" "%GENERATOR_WORKSPACE%\generate_vave_slides.mjs" --xlsx "%WORKBOOK%" --template "%SLIDE_TEMPLATE%" --out "%POWERPOINT%" --qa-dir "%GENERATOR_WORKSPACE%\qa"
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
if not "%VPM_VALIDATE_NO_PAUSE%"=="1" pause
exit /b 1
