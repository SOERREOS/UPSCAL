from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTALLER = ROOT / "dist_installer" / "UPSCAL_Setup.exe"
DEFAULT_OUT = ROOT / "dist_installer" / "latest.json"
CONFIG_PATH = ROOT / "update_config.json"


def detect_app_version() -> str:
    source = (ROOT / "app_qt.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', source)
    if not match:
        raise SystemExit("Could not detect APP_VERSION in app_qt.py")
    return match.group(1)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def default_installer_path(version: str) -> Path:
    versioned = ROOT / "dist_installer" / f"UPSCAL_Setup_v{version}.exe"
    if versioned.exists():
        return versioned
    return DEFAULT_INSTALLER


def normalize_repo(value: str) -> str:
    repo = value.strip()
    repo = repo.removeprefix("https://github.com/").removeprefix("http://github.com/")
    repo = repo.strip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    if repo.count("/") != 1:
        raise SystemExit("Repo must look like OWNER/REPO or https://github.com/OWNER/REPO")
    return repo


def main() -> int:
    parser = argparse.ArgumentParser(description="Create UPSCAL latest.json for GitHub Releases.")
    parser.add_argument("--repo", required=True, help="GitHub repo, for example REOS/UPSCAL")
    parser.add_argument("--version", default="", help="Release version. Defaults to APP_VERSION.")
    parser.add_argument("--tag", default="", help="Release tag. Defaults to v{version}.")
    parser.add_argument("--installer", default="", help="Installer file path. Defaults to the current versioned setup exe.")
    parser.add_argument("--asset-name", default="", help="Installer asset name on GitHub. Defaults to the installer file name.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output latest.json path.")
    parser.add_argument("--notes-ko", default="", help="Korean release notes.")
    parser.add_argument("--notes-en", default="", help="English release notes.")
    parser.add_argument("--write-config", action="store_true", help="Write update_config.json manifest_url.")
    args = parser.parse_args()

    repo = normalize_repo(args.repo)
    version = (args.version or "").strip() or detect_app_version()
    tag = (args.tag or "").strip() or f"v{version}"
    installer = Path(args.installer).resolve() if args.installer else default_installer_path(version).resolve()
    out_path = Path(args.out).resolve()

    if not installer.exists():
        raise SystemExit(f"Installer not found: {installer}")

    asset_name = (args.asset_name or "").strip() or installer.name
    download_url = f"https://github.com/{repo}/releases/download/{tag}/{asset_name}"
    manifest_url = f"https://github.com/{repo}/releases/latest/download/latest.json"
    manifest = {
        "version": version,
        "url": download_url,
        "sha256": sha256_file(installer),
        "notes_ko": args.notes_ko,
        "notes_en": args.notes_en,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.write_config:
        CONFIG_PATH.write_text(
            json.dumps({"manifest_url": manifest_url}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"Wrote: {out_path}")
    print(f"Upload these release assets to GitHub tag {tag}:")
    print(f"  {installer}")
    print(f"  {out_path}")
    print(f"Manifest URL for update_config.json:")
    print(f"  {manifest_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
