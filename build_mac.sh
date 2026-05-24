#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VERSION="$("$PYTHON" - <<'PY'
import pathlib
import re

text = pathlib.Path("app_qt.py").read_text(encoding="utf-8")
match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
print(match.group(1) if match else "0.0.0")
PY
)"

ARCH="$(uname -m)"
case "$ARCH" in
  arm64|aarch64) DIST_ARCH="arm64" ;;
  x86_64|amd64) DIST_ARCH="x64" ;;
  *) DIST_ARCH="$ARCH" ;;
esac

"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt pyinstaller
"$PYTHON" tools/build_icon_assets.py
"$PYTHON" tools/download_models.py

rm -rf build_tmp_mac dist_mac

"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "UPSCAL" \
  --icon "$(pwd)/installer/UPSCAL.icns" \
  --distpath "dist_mac" \
  --workpath "build_tmp_mac" \
  --specpath "build_tmp_mac" \
  --add-data "$(pwd)/models:models" \
  --add-data "$(pwd)/Icon.png:." \
  --add-data "$(pwd)/update_config.json:." \
  --hidden-import "upscaler" \
  --hidden-import "esrgan_runtime" \
  --exclude-module "basicsr" \
  --exclude-module "realesrgan" \
  --exclude-module "facexlib" \
  --exclude-module "torchvision" \
  --exclude-module "gradio" \
  --exclude-module "matplotlib" \
  --exclude-module "scipy" \
  --exclude-module "numba" \
  --exclude-module "llvmlite" \
  --exclude-module "pandas" \
  --exclude-module "IPython" \
  --exclude-module "jupyter" \
  app_qt.py

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "dist_mac/UPSCAL.app" || true
fi

OUT="dist_mac/UPSCAL_macOS_${DIST_ARCH}_v${VERSION}.zip"
ditto -c -k --keepParent "dist_mac/UPSCAL.app" "$OUT"
echo "Done: $OUT"
