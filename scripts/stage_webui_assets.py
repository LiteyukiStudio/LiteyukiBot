"""Stage a reproducible WebUI asset bundle into the distribution package."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "webui" / "dist"
DESTINATION = PROJECT_ROOT / "packages" / "webui" / "src" / "liteyukibot_webui" / "static"
MANIFEST = "assets.manifest.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(source: Path = SOURCE, destination: Path = DESTINATION) -> Path:
    if not (source / "index.html").is_file():
        raise RuntimeError(f"WebUI build output is missing: {source / 'index.html'}")
    destination.mkdir(parents=True, exist_ok=True)
    for child in destination.iterdir():
        if child.name != ".gitignore":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    for child in source.iterdir():
        target = destination / child.name
        shutil.copytree(child, target) if child.is_dir() else shutil.copy2(child, target)
    files = [path for path in sorted(destination.rglob("*")) if path.is_file()]
    payload = {
        "schema_version": 1,
        "files": [
            {"path": path.relative_to(destination).as_posix(), "sha256": _digest(path), "bytes": path.stat().st_size}
            for path in files
            if path.name != MANIFEST
        ],
    }
    manifest = destination / MANIFEST
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--destination", type=Path, default=DESTINATION)
    args = parser.parse_args()
    print(stage(args.source, args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
