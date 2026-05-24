from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist_app" / "UPSCAL"
INTERNAL = DIST / "_internal"


def _inside_dist(path: Path) -> bool:
    try:
        path.resolve().relative_to(DIST.resolve())
        return True
    except ValueError:
        return False


def _remove_path(path: Path) -> int:
    if not path.exists() or not _inside_dist(path):
        return 0
    if path.is_dir():
        count = sum(1 for child in path.rglob("*") if child.is_file())
        shutil.rmtree(path)
        return count
    path.unlink()
    return 1


def main() -> int:
    if not DIST.exists():
        print(f"[prune] skipped: {DIST} does not exist")
        return 0

    removed = 0
    for item in (INTERNAL / "cv2").glob("opencv_videoio_ffmpeg*.dll"):
        removed += _remove_path(item)

    translations = INTERNAL / "PyQt6" / "Qt6" / "translations"
    keep_translations = {"qtbase_en.qm", "qtbase_ko.qm"}
    if translations.exists():
        for item in translations.glob("qtbase_*.qm"):
            if item.name not in keep_translations:
                removed += _remove_path(item)

    imageformats = INTERNAL / "PyQt6" / "Qt6" / "plugins" / "imageformats"
    for name in ("qicns.dll", "qpdf.dll", "qtga.dll", "qwbmp.dll"):
        removed += _remove_path(imageformats / name)

    print(f"[prune] removed {removed} unused packaged files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
