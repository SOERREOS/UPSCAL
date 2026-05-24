@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "REPO=SOERREOS/UPSCAL"
set "VERSION=%~1"
set "GH="

where gh >nul 2>nul
if not errorlevel 1 set "GH=gh"
if not defined GH if exist "%ProgramFiles%\GitHub CLI\gh.exe" set "GH=%ProgramFiles%\GitHub CLI\gh.exe"
if not defined GH if exist "%ProgramFiles(x86)%\GitHub CLI\gh.exe" set "GH=%ProgramFiles(x86)%\GitHub CLI\gh.exe"
if not defined GH if exist "%LocalAppData%\Programs\GitHub CLI\gh.exe" set "GH=%LocalAppData%\Programs\GitHub CLI\gh.exe"

if not defined GH (
    echo [ERROR] GitHub CLI is not installed.
    echo Install it, then run:
    echo   winget install --id GitHub.cli
    echo   gh auth login
    exit /b 1
)

"%GH%" auth status >nul 2>nul
if errorlevel 1 (
    echo [ERROR] GitHub CLI is not logged in.
    echo Run:
    echo   gh auth login
    exit /b 1
)

set "INSTALLER="
for %%F in ("dist_installer\UPSCAL_Setup_v*.exe") do set "INSTALLER=%%~fF"
if not defined INSTALLER if exist "dist_installer\UPSCAL_Setup.exe" set "INSTALLER=%CD%\dist_installer\UPSCAL_Setup.exe"

if not defined INSTALLER (
    echo [ERROR] Installer file not found.
    echo Run build_installer.bat first.
    exit /b 1
)

echo [1/3] Creating latest.json...
set "PYTHON="
if exist "venv_new\Scripts\python.exe" set "PYTHON=venv_new\Scripts\python.exe"
if not defined PYTHON if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not defined PYTHON if exist "venv\Scripts\python.exe" set "PYTHON=venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"

if "%VERSION%"=="" (
    "%PYTHON%" tools\make_github_release_manifest.py --repo "%REPO%" --installer "%INSTALLER%" --write-config
) else (
    "%PYTHON%" tools\make_github_release_manifest.py --repo "%REPO%" --version "%VERSION%" --installer "%INSTALLER%" --write-config
)
if errorlevel 1 exit /b 1

for /f "usebackq delims=" %%V in (`"%PYTHON%" -c "import json; print(json.load(open('dist_installer/latest.json', encoding='utf-8'))['version'])"`) do set "VERSION=%%V"
for /f "usebackq delims=" %%A in (`"%PYTHON%" -c "import json; print(json.load(open('dist_installer/latest.json', encoding='utf-8'))['url'].rsplit('/', 1)[-1])"`) do set "ASSET_NAME=%%A"
set "TAG=v%VERSION%"

if "%VERSION%"=="" (
    echo [ERROR] Could not read version from dist_installer\latest.json.
    exit /b 1
)
if "%ASSET_NAME%"=="" (
    echo [ERROR] Could not read asset name from dist_installer\latest.json.
    exit /b 1
)

echo [2/3] Creating or updating GitHub release %TAG%...
"%GH%" release view "%TAG%" --repo "%REPO%" >nul 2>nul
if errorlevel 1 (
    "%GH%" release create "%TAG%" --repo "%REPO%" --title "UPSCAL %VERSION%" --notes "UPSCAL %VERSION%"
) else (
    echo Release already exists. Assets will be replaced.
)
if errorlevel 1 exit /b 1

echo [3/3] Uploading release assets...
"%GH%" release upload "%TAG%" "dist_installer\%ASSET_NAME%" "dist_installer\latest.json" --repo "%REPO%" --clobber
if errorlevel 1 exit /b 1

echo.
echo Done:
echo   https://github.com/%REPO%/releases/tag/%TAG%
