#!/usr/bin/env python3
"""Build a reproducible source release bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_PARTS = {".git", ".venv", ".opencode", "__pycache__", ".pytest_cache", ".mypy_cache", ".DS_Store", "dist"}


def read_version() -> str:
    return (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def include(path: Path) -> bool:
    return not any(part in EXCLUDED_PARTS for part in path.relative_to(PROJECT_ROOT).parts)


def build(output_dir: Path) -> Path:
    version = read_version()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"automated-followspot-system-{version}.tar.gz"
    root_name = f"automated-followspot-system-{version}"

    with tarfile.open(archive, "w:gz") as bundle:
        for path in PROJECT_ROOT.rglob("*"):
            if path == archive or not path.is_file() or not include(path):
                continue
            relative = path.relative_to(PROJECT_ROOT)
            bundle.add(path, arcname=Path(root_name) / relative)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {
        "name": "automated-followspot-system",
        "version": version,
        "archive": archive.name,
        "sha256": digest,
        "source_root": str(PROJECT_ROOT),
    }
    (output_dir / f"automated-followspot-system-{version}.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "dist")
    args = parser.parse_args()
    archive = build(args.output)
    print(archive)


if __name__ == "__main__":
    main()
