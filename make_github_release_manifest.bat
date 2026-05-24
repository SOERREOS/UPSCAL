@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON="
if exist "venv_new\Scripts\python.exe" set "PYTHON=venv_new\Scripts\python.exe"
if not defined PYTHON if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not defined PYTHON if exist "venv\Scripts\python.exe" set "PYTHON=venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"

if "%~1"=="" (
    echo Usage:
    echo   make_github_release_manifest.bat OWNER/REPO [version]
    echo.
    echo Example:
    echo   make_github_release_manifest.bat REOS/UPSCAL 0.1.0
    exit /b 1
)

"%PYTHON%" tools\make_github_release_manifest.py --repo "%~1" --version "%~2" --write-config
