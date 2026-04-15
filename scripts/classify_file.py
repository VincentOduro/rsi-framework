#!/usr/bin/env python3
"""
classify_file.py — Returns sensitivity level for a given filepath.

Reads .rsi/architecture.yaml and matches the filepath against glob patterns.
First match wins. If no pattern matches, defaults to "guarded" (safe default).

Usage:
    python3 scripts/classify_file.py src/core/api.py       # -> guarded
    python3 scripts/classify_file.py CLAUDE.md              # -> constitution
    python3 scripts/classify_file.py tests/test_foo.py      # -> open
    python3 scripts/classify_file.py --batch file1 file2    # Multiple files
    python3 scripts/classify_file.py --json src/api.py      # JSON output
"""

import argparse
import fnmatch
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
ARCHITECTURE_FILE = PROJECT_ROOT / ".rsi" / "architecture.yaml"

# Sensitivity levels in match priority order
SENSITIVITY_LEVELS = ["constitution", "guarded", "open"]
DEFAULT_SENSITIVITY = "guarded"


def _load_architecture() -> dict:
    """Load and parse architecture.yaml. Uses simple parser to avoid PyYAML dependency."""
    if not ARCHITECTURE_FILE.exists():
        return {}

    content = ARCHITECTURE_FILE.read_text()

    # Simple YAML-subset parser: extract file_sensitivity patterns
    # Handles the specific structure in architecture.yaml without requiring PyYAML
    result = {}
    current_level = None
    in_patterns = False

    for line in content.split("\n"):
        stripped = line.strip()

        # Detect sensitivity level headers
        for level in SENSITIVITY_LEVELS:
            if stripped == f"{level}:":
                current_level = level
                result[current_level] = []
                in_patterns = False
                break

        # Detect patterns list start
        if stripped == "patterns:":
            in_patterns = True
            continue

        # Parse pattern entries
        if in_patterns and stripped.startswith("- "):
            pattern = stripped[2:].strip().strip('"').strip("'")
            if pattern and not pattern.startswith("#"):
                if current_level:
                    result[current_level].append(pattern)

        # End of patterns section (next non-indented non-empty non-comment line)
        if in_patterns and stripped and not stripped.startswith("-") and not stripped.startswith("#") and stripped != "patterns:":
            if not stripped.startswith("description:"):
                in_patterns = False

    return result


def classify_file(filepath: str) -> str:
    """Classify a file's sensitivity level.

    Args:
        filepath: Path relative to project root

    Returns:
        "constitution", "guarded", or "open"
    """
    patterns = _load_architecture()

    # Normalize path separators
    filepath = filepath.replace("\\", "/")

    for level in SENSITIVITY_LEVELS:
        for pattern in patterns.get(level, []):
            if fnmatch.fnmatch(filepath, pattern):
                return level
            # Also check just the filename for simple patterns
            if "/" not in pattern and fnmatch.fnmatch(Path(filepath).name, pattern):
                return level

    return DEFAULT_SENSITIVITY


def classify_files(filepaths: list[str]) -> dict[str, str]:
    """Classify multiple files. Returns {filepath: sensitivity}."""
    return {fp: classify_file(fp) for fp in filepaths}


def is_worker_allowed(filepath: str) -> bool:
    """Check if the worker role is allowed to modify this file."""
    return classify_file(filepath) != "constitution"


def main():
    parser = argparse.ArgumentParser(
        description="Classify file sensitivity level from .rsi/architecture.yaml"
    )
    parser.add_argument("files", nargs="*", help="File path(s) to classify")
    parser.add_argument("--batch", action="store_true", help="Classify multiple files")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--check-worker", action="store_true",
                        help="Exit 1 if any file is constitution-level (for hook integration)")
    args = parser.parse_args()

    if not args.files:
        parser.print_help()
        sys.exit(0)

    results = classify_files(args.files)

    if args.check_worker:
        blocked = {f: s for f, s in results.items() if s == "constitution"}
        if blocked:
            for f, s in blocked.items():
                print(f"BLOCKED: {f} is {s}-level. Worker cannot modify.", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for filepath, sensitivity in results.items():
            print(f"  {sensitivity:<14} {filepath}")


if __name__ == "__main__":
    main()
