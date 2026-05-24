@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo   UPSCAL - Build self-contained app folder
echo ================================================
echo.

set "PYTHON="
if exist "venv_new\Scripts\python.exe" set "PYTHON=venv_new\Scripts\python.exe"
if not defined PYTHON if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not defined PYTHON if exist "venv\Scripts\python.exe" set "PYTHON=venv\Scripts\python.exe"

if not defined PYTHON (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    if not defined UPSCAL_NO_PAUSE pause
    exit /b 1
)

echo [1/2] Installing PyInstaller...
"%PYTHON%" -m pip install pyinstaller
if errorlevel 1 (
    echo [ERROR] PyInstaller install failed.
    if not defined UPSCAL_NO_PAUSE pause
    exit /b 1
)

echo.
echo [icon] Generating app and installer icon assets...
"%PYTHON%" tools\build_icon_assets.py
if errorlevel 1 (
    echo [ERROR] Icon asset generation failed.
    if not defined UPSCAL_NO_PAUSE pause
    exit /b 1
)

echo.
echo [models] Ensuring model files...
"%PYTHON%" tools\download_models.py
if errorlevel 1 (
    echo [ERROR] Model download failed.
    if not defined UPSCAL_NO_PAUSE pause
    exit /b 1
)

echo.
echo [2/2] Building dist_app\UPSCAL\UPSCAL.exe ...
"%PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --noconsole ^
  --name "UPSCAL" ^
  --icon "%CD%\installer\UPSCAL.ico" ^
  --distpath "dist_app" ^
  --workpath "build_tmp_app" ^
  --specpath "build_tmp_app" ^
  --add-data "%CD%\models;models" ^
  --add-data "%CD%\Icon.png;." ^
  --add-data "%CD%\update_config.json;." ^
  --hidden-import "upscaler" ^
  --hidden-import "esrgan_runtime" ^
  --exclude-module "basicsr" ^
  --exclude-module "realesrgan" ^
  --exclude-module "facexlib" ^
  --exclude-module "torchvision" ^
  --exclude-module "gradio" ^
  --exclude-module "matplotlib" ^
  --exclude-module "scipy" ^
  --exclude-module "numba" ^
  --exclude-module "llvmlite" ^
  --exclude-module "pandas" ^
  --exclude-module "IPython" ^
  --exclude-module "jupyter" ^
  app_qt.py

if errorlevel 1 (
    echo [ERROR] App build failed. Check the messages above.
    if not defined UPSCAL_NO_PAUSE pause
    exit /b 1
)

echo.
echo [prune] Removing unused packaged runtime files...
"%PYTHON%" tools\prune_dist_app.py
if errorlevel 1 (
    echo [ERROR] Package pruning failed.
    if not defined UPSCAL_NO_PAUSE pause
    exit /b 1
)

echo.
if exist "dist_app\UPSCAL\UPSCAL.exe" (
    echo ================================================
    echo   Done! dist_app\UPSCAL\UPSCAL.exe created.
    echo ================================================
) else (
    echo [ERROR] App build failed. Check the messages above.
)

if not defined UPSCAL_NO_PAUSE pause
