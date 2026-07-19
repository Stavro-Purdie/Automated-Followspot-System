#!/usr/bin/env python3
"""Config validation utility using JSON Schema.

Validates all configuration files against their JSON Schema definitions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import jsonschema
    from jsonschema import validate, ValidationError
except ImportError:
    print("jsonschema not installed. Run: pip install jsonschema")
    sys.exit(1)

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "config" / "schemas"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

SCHEMA_MAP: List[Tuple[str, str, str]] = [
    ("front_array_config.json", "front_array_config.schema.json", "Front Array Camera Config"),
    ("roof_array_config.json", "roof_array_config.schema.json", "Roof Array Camera Config"),
    ("spotlight_config.json", "spotlight_config.schema.json", "Spotlight Config"),
    ("reid_config.json", "reid_config.schema.json", "ReID Config"),
]


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}")
    except Exception as exc:
        raise ValueError(f"Failed to read {path}: {exc}")


def validate_config(config_path: Path, schema_path: Path, name: str) -> Tuple[bool, List[str]]:
    """Validate a config file against its schema.

    Returns:
        (success, error_messages)
    """
    errors: List[str] = []

    try:
        config = load_json(config_path)
    except ValueError as exc:
        return False, [str(exc)]

    try:
        schema = load_json(schema_path)
    except ValueError as exc:
        return False, [f"Schema load error: {exc}"]

    try:
        validate(instance=config, schema=schema)
        return True, []
    except ValidationError as exc:
        # Build a readable error path
        path = " -> ".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "root"
        errors.append(f"{name} [{path}]: {exc.message}")
        # Also include sub-errors if any
        for suberr in exc.context:
            subpath = " -> ".join(str(p) for p in suberr.absolute_path) if suberr.absolute_path else path
            errors.append(f"{name} [{subpath}]: {suberr.message}")
        return False, errors


def main() -> int:
    print("Validating configuration files against JSON Schemas...")
    print("=" * 60)

    all_ok = True
    total_errors = 0

    for config_file, schema_file, name in SCHEMA_MAP:
        config_path = CONFIG_DIR / config_file
        schema_path = SCHEMA_DIR / schema_file

        if not config_path.exists():
            print(f"⚠️  {name}: Config file not found at {config_path}")
            continue

        if not schema_path.exists():
            print(f"⚠️  {name}: Schema file not found at {schema_path}")
            continue

        print(f"\nValidating {name}...")
        print(f"  Config: {config_path}")
        print(f"  Schema: {schema_path}")

        ok, errors = validate_config(config_path, schema_path, name)
        if ok:
            print(f"  ✅ Valid")
        else:
            print(f"  ❌ Invalid ({len(errors)} errors)")
            for err in errors:
                print(f"     - {err}")
            all_ok = False
            total_errors += len(errors)

    print("\n" + "=" * 60)
    if all_ok:
        print("✅ All configurations are valid!")
        return 0
    else:
        print(f"❌ Validation failed with {total_errors} total errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())