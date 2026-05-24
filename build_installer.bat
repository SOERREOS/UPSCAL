@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "SETUP_EXE=dist_installer\UPSCAL_Setup_v0.1.0.exe"

echo ================================================
echo   UPSCAL - Build Windows Installer
echo ================================================
echo.

if not exist "dist_app\UPSCAL\UPSCAL.exe" (
    echo [INFO] Self-contained app folder not found. Building it first...
    call build_app.bat
    if not exist "dist_app\UPSCAL\UPSCAL.exe" (
        echo [ERROR] App folder build failed.
        if not defined UPSCAL_NO_PAUSE pause
        exit /b 1
    )
)

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC for %%I in (ISCC.exe) do if not "%%~$PATH:I"=="" set "ISCC=%%~$PATH:I"

if not defined ISCC (
    echo [ERROR] Inno Setup 6 compiler was not found.
    echo.
    echo Install Inno Setup 6, then run this file again:
    echo   https://jrsoftware.org/isinfo.php
    echo.
    echo Installer script is ready at:
    echo   installer\UPSCAL.iss
    if not defined UPSCAL_NO_PAUSE pause
    exit /b 1
)

set "PYTHON="
if exist "venv_new\Scripts\python.exe" set "PYTHON=venv_new\Scripts\python.exe"
if not defined PYTHON if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not defined PYTHON if exist "venv\Scripts\python.exe" set "PYTHON=venv\Scripts\python.exe"
if defined PYTHON (
    echo [icon] Generating installer icon assets...
    "%PYTHON%" tools\build_icon_assets.py
    if errorlevel 1 (
        echo [ERROR] Icon asset generation failed.
        if not defined UPSCAL_NO_PAUSE pause
        exit /b 1
    )
)

echo [1/1] Compiling installer...
"%ISCC%" "installer\UPSCAL.iss"

if errorlevel 1 (
    echo [ERROR] Installer build failed. Check the messages above.
    if not defined UPSCAL_NO_PAUSE pause
    exit /b 1
)

if exist "%SETUP_EXE%" (
    echo.
    echo ================================================
    echo   Done! %SETUP_EXE% created.
    echo ================================================
) else (
    echo [ERROR] Installer build failed. Check the messages above.
)

if not defined UPSCAL_NO_PAUSE pause
