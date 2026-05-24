# UPSCAL Project Notes

## Current Status

UPSCAL is a local AI image upscaling desktop app. The processing layer uses
Real-ESRGAN and runs locally with CUDA when PyTorch detects a compatible GPU.

The current primary UI is the PyQt6 desktop app in `app_qt.py`. It has been
migrated to the Claude final design structure:

- left workflow canvas
- center before/after preview
- bottom image queue
- right output settings and actions

## Running

```bat
venv_new\Scripts\python.exe app_qt.py
```

## Build Goal

The intended distribution path is an installable Windows EXE with no console
window.

- `build_app.bat` builds `dist_app/UPSCAL/UPSCAL.exe`, a console-free app
  folder that includes the Python runtime and Python dependencies collected by
  PyInstaller.
- `build_installer.bat` compiles `installer/UPSCAL.iss` into
  `dist_installer/UPSCAL_Setup.exe` when Inno Setup 6 is installed.
- The installer script includes the `dist_app/UPSCAL` app folder and creates
  Start Menu and Desktop shortcuts.

## Architecture

### `upscaler.py`

- `_MODEL_REGISTRY`: maps `(model_type, scale)` to Real-ESRGAN model metadata.
- `_ensure_model()`: verifies or downloads model weights into `models/`.
- `upscale_image()`: converts PIL to OpenCV, runs ESRGAN, restores details,
  and embeds DPI metadata in the returned PIL image.
- 8x upscaling is implemented as 4x plus 2x sequential passes.
- Anime 2x reuses the anime 4x model with `outscale=2`.

### `app_qt.py`

- Native PyQt6 desktop shell.
- Supports drag/drop or file picker image queueing.
- Preserves current controls: model, scale, DPI, output format, tile size,
  detail strength, processing, comparison preview, save, and reset.
- Runs `upscale_image()` in `UpscaleWorker` so the UI stays responsive.
- The model selector shows user-facing labels `사진` and `그림`; internally
  they map to Real-ESRGAN general and anime models.
- Completed queue items turn the primary action into `저장하기`.
- Runtime progress is displayed in the right action area and the bottom queue.
- Multiple queued images are processed automatically after pressing start.
- The before/after preview supports cached zoom and pan for smoother comparison.

### `installer/UPSCAL.iss`

- Inno Setup script for the final Windows installer.
- Installs to the user's local app data program folder.
- Creates Start Menu and optional Desktop shortcuts.

## Models

The `models/` folder currently contains:

- `RealESRGAN_x4plus.pth`
- `RealESRGAN_x2plus.pth`
- `RealESRGAN_x4plus_anime_6B.pth`

## Verification

No formal test suite exists yet. Current lightweight checks:

```bat
venv_new\Scripts\python.exe -m py_compile app_qt.py upscaler.py
```

Recent smoke checks also cover Qt window creation, image queue insertion, and
the detail restoration function.
