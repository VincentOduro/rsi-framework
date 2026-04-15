#!/usr/bin/env python3
"""
Pre-flight check — runs BEFORE any file edit.

This script addresses the failure mode: editing a file without reading it first.

The check compares files you've modified against files you've read in this session.
If you edited a file without reading it, it warns (for local use) or blocks (CI mode).

Usage:
    python3 scripts/preflight_check.py --check-edited     # Check if edited files were read
    python3 scripts/preflight_check.py --ci               # Blocking CI mode
    python3 scripts/preflight_check.py --record FILE     # Record that FILE was read
    python3 scripts/preflight_check.py --report          # Show what's been read/edited
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
STATE_FILE = PROJECT_ROOT / ".memory" / ".preflight_state.json"


def green(msg: str) -> str:
    return f"\033[92m{msg}\033[0m"


def red(msg: str) -> str:
    return f"\033[91m{msg}\033[0m"


def yellow(msg: str) -> str:
    return f"\033[93m{msg}\033[0m"


def cyan(msg: str) -> str:
    return f"\033[96m{msg}\033[0m"


def _load_state() -> dict:
    """Load preflight state from file.
    
    Auto-seeds from git-tracked files if state is empty (no prior session).
    This ensures CI only flags genuinely NEW files (not in git history),
    not pre-existing tracked files that weren't explicitly recorded as read.
    """
    if not STATE_FILE.exists():
        tracked = get_git_tracked_files()
        seeded = {"read_files": tracked, "edited_files": set(), "sessions": [], "seeded_from": "git-ls-files"}
        return seeded
    try:
        import json
        data = json.loads(STATE_FILE.read_text())
        data["read_files"] = set(data.get("read_files", []))
        data["edited_files"] = set(data.get("edited_files", []))
        return data
    except (json.JSONDecodeError, IOError):
        tracked = get_git_tracked_files()
        seeded = {"read_files": tracked, "edited_files": set(), "sessions": [], "seeded_from": "git-ls-files"}
        return seeded


def _save_state(state: dict) -> None:
    """Save preflight state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    data = {k: list(v) if isinstance(v, set) else v for k, v in state.items()}
    STATE_FILE.write_text(json.dumps(data, indent=2))


def get_git_diff_files() -> set[str]:
    """Get files modified since last commit."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    files = set()
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("tests/"):
            files.add(line)
    for line in staged.stdout.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("tests/"):
            files.add(line)
    return files


def get_git_tracked_files() -> set[str]:
    """Get all git-tracked source files."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return {line.strip() for line in result.stdout.strip().split("\n") if line.strip()}


def cmd_record(files: list[str]) -> None:
    """Record that files were read (simulates "read in this session")."""
    state = _load_state()
    session_id = datetime.now().strftime("%Y-%m-%d-%H%M")
    state["sessions"].append({
        "time": session_id,
        "action": "read",
        "files": files,
    })
    for f in files:
        state["read_files"].add(f)
    _save_state(state)
    for f in files:
        print(f"{green('Recorded as read:')} {f}")


def cmd_report() -> None:
    """Show what's been read vs edited."""
    state = _load_state()
    edited = get_git_diff_files()
    read = state["read_files"]
    tracked = get_git_tracked_files()

    print(f"\n{'='*60}")
    print("PRE-FLIGHT REPORT")
    print(f"{'='*60}\n")

    # Edited files
    print(f"Edited since last commit ({len(edited)}):")
    if not edited:
        print("  (none)")
    else:
        for f in sorted(edited):
            status = green("  READ") if f in read else red("  NOT READ")
            print(f"    {status}  {f}")

    # Recently read
    print(f"\nRecorded as read in this session ({len(read)}):")
    if not read:
        print("  (none)")
    else:
        for f in sorted(read)[:20]:
            print(f"    {f}")
        if len(read) > 20:
            print(f"    ... and {len(read) - 20} more")

    # Tracked files that haven't been read
    never_read = tracked - read
    src_files = {f for f in never_read if f.startswith("src/")}
    print(f"\nSource files never read in this session ({len(src_files)}):")
    if not src_files:
        print("  (all source files have been read)")
    else:
        for f in sorted(src_files)[:10]:
            print(f"    {yellow(f)}")
        if len(src_files) > 10:
            print(f"    ... and {len(src_files) - 10} more")

    print(f"\n{'='*60}")


def cmd_check(args) -> None:
    """Check if edited files have been read."""
    state = _load_state()
    edited = get_git_diff_files()
    read = state["read_files"]
    tracked = get_git_tracked_files()

    if not edited:
        print(f"{green('No source files edited — pre-flight clear.')}")
        return

    print(f"\n{'='*60}")
    print("PRE-FLIGHT CHECK")
    print(f"{'='*60}\n")

    problems = []
    for f in sorted(edited):
        fpath = PROJECT_ROOT / f
        if f not in read:
            problems.append(f)
            # Check if it's a new file (not in git history)
            if f in tracked:
                print(f"  {red('EDITED WITHOUT READING:')} {f}")
            else:
                print(f"  {yellow('NEW FILE (no prior read recorded):')} {f}")
        else:
            print(f"  {green('OK:')} {f}")

    print(f"\n{'='*60}")

    if problems:
        if args.ci:
            print(f"\n{red('PRE-FLIGHT FAILED — blocking in CI mode')}")
            print(f"Edit the following files without reading them:")
            for f in problems:
                print(f"  - {f}")
            print(f"\nTo record reading:")
            print(f"  python3 scripts/preflight_check.py --record FILE")
            sys.exit(1)
        else:
            print(f"\n{yellow('WARNING:')} {len(problems)} file(s) edited without being read.")
            print(f"This is a developer discipline check, not a blocking gate.")
            print(f"\nTo record reading:")
            print(f"  python3 scripts/preflight_check.py --record <file1> <file2> ...")
            print(f"\nTo bypass this check (not recommended):")
            print(f"  git commit --no-verify")
            print(f"\nTo make this check blocking, use --ci flag.")
            sys.exit(0)  # Warning only, not blocking in non-CI mode
    else:
        print(f"\n{green('PRE-FLIGHT CLEAR — all edited files were read.')}")
        sys.exit(0)


def cmd_reset() -> None:
    """Reset pre-flight state for a fresh session."""
    state = _load_state()
    state["sessions"].append({
        "time": datetime.now().strftime("%Y-%m-%d-%H%M"),
        "action": "reset",
        "files": [],
    })
    state["read_files"] = set()
    _save_state(state)
    print(f"{green('Pre-flight state reset.')}")


def main():
    parser = argparse.ArgumentParser(description="Pre-flight check — verify files were read before editing")
    parser.add_argument("--check-edited", action="store_true", help="Check if edited files were read (non-blocking)")
    parser.add_argument("--ci", action="store_true", help="Blocking CI mode (fails if unwatched files edited)")
    parser.add_argument("--record", nargs="+", help="Record that FILE was read")
    parser.add_argument("--report", action="store_true", help="Show read vs edited status")
    parser.add_argument("--reset", action="store_true", help="Reset pre-flight state for fresh session")

    args = parser.parse_args()

    if args.record:
        cmd_record(args.record)
    elif args.report:
        cmd_report()
    elif args.reset:
        cmd_reset()
    elif args.check_edited or args.ci:
        cmd_check(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
