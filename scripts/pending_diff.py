#!/usr/bin/env python3
"""
pending_diff.py — Unified diff of a pending worker result vs disk.

After delegation, the overlord reviews changes. The bloated way: Read
each modified file from disk, then Read the worker's stored result, then
mentally diff them. The cheap way: print the unified diff directly.

Worker output sits in .memory/reviews/results/<TASK-ID>.json with shape:
    {"changes": {"path": "full file content", ...}, ...}

This script diffs each entry against current disk content (or marks
'(new file)' if disk has no copy).

Usage:
    python scripts/pending_diff.py TASK-047           # all files in result
    python scripts/pending_diff.py TASK-047 --stat    # shortstat only
    python scripts/pending_diff.py TASK-047 path/to/file.py  # one file
    python scripts/pending_diff.py TASK-047 --context 1      # tighter diff
"""

import argparse
import difflib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
RESULTS_DIR = PROJECT_ROOT / ".memory" / "reviews" / "results"


def _safe_path(filepath: str) -> Path | None:
    p = Path(filepath)
    if p.is_absolute() or (len(filepath) >= 2 and filepath[1] == ":"):
        return None
    candidate = (PROJECT_ROOT / p).resolve()
    try:
        candidate.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    return candidate


def _normalize(content: str) -> str:
    """Apply same newline fixes as delegate.apply_changes."""
    if "\\n" in content and "\n" not in content:
        content = content.replace("\\n", "\n")
    if "\\t" in content and "\t" not in content:
        content = content.replace("\\t", "\t")
    if content and not content.endswith("\n"):
        content += "\n"
    return content


def _diff_one(filepath: str, new_content: str, context: int) -> tuple[str, int, int]:
    """Return (diff_text, added, removed) for one file."""
    safe = _safe_path(filepath)
    if safe is None:
        return (f"=== {filepath}\n  ERROR: path escapes project root\n", 0, 0)

    new_content = _normalize(new_content)
    new_lines = new_content.splitlines(keepends=True)

    if safe.exists():
        old = safe.read_text(encoding="utf-8")
        old_lines = old.splitlines(keepends=True)
        from_label = filepath
        to_label = filepath + " (worker)"
    else:
        old_lines = []
        from_label = "/dev/null"
        to_label = filepath + " (NEW FILE)"

    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=from_label,
            tofile=to_label,
            n=context,
        )
    )

    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

    return ("".join(diff), added, removed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diff a pending worker result vs disk. Cheaper than Read+Read."
    )
    parser.add_argument("task_id", help="e.g. TASK-047")
    parser.add_argument("file", nargs="?", help="Optional: limit to one file")
    parser.add_argument(
        "--stat",
        action="store_true",
        help="Print only summary (path, +added/-removed). Skip diff body.",
    )
    parser.add_argument(
        "--context", type=int, default=3, help="Lines of context (default 3)"
    )
    args = parser.parse_args()

    result_path = RESULTS_DIR / f"{args.task_id}.json"
    if not result_path.exists():
        print(f"ERROR: No stored result for {args.task_id}", file=sys.stderr)
        print(f"  Looked at: {result_path}", file=sys.stderr)
        sys.exit(1)

    raw_bytes = result_path.read_bytes()
    text = None
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        print(f"ERROR: Could not decode {result_path} as utf-8/cp1252/latin-1", file=sys.stderr)
        sys.exit(1)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Result JSON malformed: {exc}", file=sys.stderr)
        sys.exit(1)

    changes = result.get("changes", {})
    if not changes:
        print(f"No changes in {args.task_id} result.")
        return

    if args.file:
        if args.file not in changes:
            print(f"ERROR: '{args.file}' not in result. Files in result:", file=sys.stderr)
            for f in changes:
                print(f"  {f}", file=sys.stderr)
            sys.exit(1)
        items = [(args.file, changes[args.file])]
    else:
        items = list(changes.items())

    if args.stat:
        print(f"=== {args.task_id}  {len(items)} file(s)")
        total_a = total_r = 0
        for path, new in items:
            _, added, removed = _diff_one(path, new, args.context)
            total_a += added
            total_r += removed
            print(f"  +{added:>4} -{removed:>4}  {path}")
        print(f"  ---  +{total_a} -{total_r} total")
        return

    for path, new in items:
        diff_text, added, removed = _diff_one(path, new, args.context)
        print(f"=== {path}  +{added} -{removed}")
        if diff_text:
            print(diff_text, end="" if diff_text.endswith("\n") else "\n")
        else:
            print("  (no changes — worker output matches disk)")
        print()


if __name__ == "__main__":
    main()
