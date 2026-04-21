#!/usr/bin/env python3
"""
framework_sync.py — RSI Framework self-update manager.

Manages framework updates for projects that copied (not cloned) the RSI framework.

Usage:
    python3 scripts/framework_sync.py --status           # Show current + available version
    python3 scripts/framework_sync.py --check            # Check if update available
    python3 scripts/framework_sync.py --pull             # Pull latest framework version
    python3 scripts/framework_sync.py --adopt            # Record adoption (first time)

Prerequisites:
    The framework must be present at PROJECT_ROOT/rsi-framework/ (the copy).
    Run --adopt the first time you copy the framework into a project.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def _resolve_framework_dir() -> tuple[Path, bool]:
    """Resolve the authoritative framework source directory.

    Priority:
      1. $RSI_FRAMEWORK_DIR env var (explicit override)
      2. PROJECT_ROOT/rsi-framework/ (legacy subdir convention)
      3. PROJECT_ROOT/.rsi-source/ (bootstrap.sh convention, current)
      4. PROJECT_ROOT itself if FRAMEWORK.md is present (self-mode — we ARE the framework)

    Returns (path, is_self_mode). When is_self_mode=True the project itself
    is the framework source; pull/check operations become no-ops or show-only.
    """
    override = os.environ.get("RSI_FRAMEWORK_DIR")
    if override:
        candidate = Path(override).resolve()
        if (candidate / "FRAMEWORK.md").exists():
            return candidate, candidate == PROJECT_ROOT

    for name in ("rsi-framework", ".rsi-source"):
        candidate = PROJECT_ROOT / name
        if (candidate / "FRAMEWORK.md").exists():
            return candidate, False

    if (PROJECT_ROOT / "FRAMEWORK.md").exists():
        return PROJECT_ROOT, True

    # Framework not found — return legacy path so existing ERROR messages still fire.
    return PROJECT_ROOT / "rsi-framework", False


RSI_FRAMEWORK_DIR, IS_SELF_MODE = _resolve_framework_dir()

FRAMEWORK_MARKER = PROJECT_ROOT / ".memory" / ".framework_version"
FEEDBACK_FILE = PROJECT_ROOT / ".memory" / "framework-feedback.md"
FRAMEWORK_TEMPLATE_DIR = RSI_FRAMEWORK_DIR / "MEMORY_TEMPLATE"

# Items copied from source → project during --pull.
# Directories are copied recursively (dirs_exist_ok=True). Files are overwritten.
SYNC_DIRS = ("scripts", "engine", "MEMORY_TEMPLATE", "adapters", "docs")
SYNC_FILES = ("FRAMEWORK.md", "CLAUDE.md", "PROOF_WRONG_GUIDE.md", "TOYOTA_PRINCIPLES.md", "STACK_EVOLUTION.md")


def green(msg: str) -> str:
    return f"\033[92m{msg}\033[0m"


def red(msg: str) -> str:
    return f"\033[91m{msg}\033[0m"


def yellow(msg: str) -> str:
    return f"\033[93m{msg}\033[0m"


def cyan(msg: str) -> str:
    return f"\033[96m{msg}\033[0m"


def _extract_version_from_framework() -> tuple[str, Path]:
    """Extract version from local rsi-framework/FRAMEWORK.md. Returns (version, path)."""
    framework_md = RSI_FRAMEWORK_DIR / "FRAMEWORK.md"
    if not framework_md.exists():
        return "unknown", framework_md

    content = framework_md.read_text(encoding="utf-8")
    match = re.search(r"\*\*?Status:\*\*?\s*v?(\d+\.\d+)", content, re.IGNORECASE)
    if match:
        return match.group(1), framework_md
    return "unknown", framework_md


def _extract_version_from_marker() -> str:
    """Read the recorded framework version from marker file."""
    if not FRAMEWORK_MARKER.exists():
        return "none"
    return FRAMEWORK_MARKER.read_text(encoding="utf-8").strip()


def _load_feedback() -> str:
    """Load existing feedback if any."""
    if not FEEDBACK_FILE.exists():
        return ""
    return FEEDBACK_FILE.read_text(encoding="utf-8")


def _save_feedback(content: str) -> None:
    """Save feedback content."""
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_FILE.write_text(content, encoding="utf-8")


def _git_pull_source() -> bool:
    """If RSI_FRAMEWORK_DIR is a git clone, pull latest. Returns True on success."""
    if IS_SELF_MODE:
        return False
    if not (RSI_FRAMEWORK_DIR / ".git").exists():
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(RSI_FRAMEWORK_DIR), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print(f"  {green('Source updated via git pull:')} {result.stdout.strip().splitlines()[-1] if result.stdout else 'already current'}")
            return True
        print(f"  {yellow('git pull failed:')} {result.stderr.strip()}")
        return False
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  {yellow('git pull error:')} {exc}")
        return False


def _copy_source_to_project() -> list[str]:
    """Copy SYNC_DIRS + SYNC_FILES from RSI_FRAMEWORK_DIR into PROJECT_ROOT.

    Skips in self-mode (source IS project). Returns list of copied paths (relative).
    """
    if IS_SELF_MODE:
        return []
    copied = []
    for d in SYNC_DIRS:
        src = RSI_FRAMEWORK_DIR / d
        if src.exists() and src.is_dir():
            dst = PROJECT_ROOT / d
            shutil.copytree(src, dst, dirs_exist_ok=True)
            copied.append(f"{d}/")
    for f in SYNC_FILES:
        src = RSI_FRAMEWORK_DIR / f
        if src.exists() and src.is_file():
            dst = PROJECT_ROOT / f
            shutil.copy2(src, dst)
            copied.append(f)
    return copied


def cmd_status(args) -> None:
    """Show framework version status."""
    if not (RSI_FRAMEWORK_DIR / "FRAMEWORK.md").exists():
        print(f"{red('ERROR:')} No framework source found at {RSI_FRAMEWORK_DIR}")
        print("Expected one of: rsi-framework/, .rsi-source/, or $RSI_FRAMEWORK_DIR override.")
        sys.exit(1)

    local_version, _ = _extract_version_from_framework()
    recorded_version = _extract_version_from_marker()
    feedback_count = _load_feedback().count("## Feedback Entry")

    print(f"\n{'=' * 60}")
    print("RSI FRAMEWORK STATUS")
    print(f"{'=' * 60}\n")
    print(f"  Local framework version:  v{local_version}")
    print(f"  Recorded adoption version: v{recorded_version}")
    print(f"  Feedback submissions:      {feedback_count}")
    try:
        source_display = RSI_FRAMEWORK_DIR.relative_to(PROJECT_ROOT)
    except ValueError:
        source_display = RSI_FRAMEWORK_DIR
    print(f"  Framework source:          {source_display}")
    print(f"  Mode:                      {'self (project IS framework)' if IS_SELF_MODE else 'child (project COPIES framework)'}")
    print(f"  Feedback file:             {FEEDBACK_FILE.relative_to(PROJECT_ROOT)}")

    if IS_SELF_MODE:
        print(f"\n  {cyan('INFO:')} Self-mode: no pull possible. Version shown is authoritative.")
    elif recorded_version == "none":
        print(f"\n  {yellow('WARNING:')} Run --adopt to record your framework version.")
    elif local_version != recorded_version:
        print(f"\n  {cyan('INFO:')} Update available: v{recorded_version} -> v{local_version}")
        print("  Run --pull to update.")
    else:
        print(f"\n  {green('OK:')} Framework is up to date.")

    print()


def cmd_check(args) -> None:
    """Check if framework update is available."""
    if not (RSI_FRAMEWORK_DIR / "FRAMEWORK.md").exists():
        print(f"{red('ERROR:')} No framework source found at {RSI_FRAMEWORK_DIR}")
        sys.exit(1)

    if IS_SELF_MODE:
        print(f"{cyan('SELF-MODE')} — this project IS the framework; --check is a no-op.")
        sys.exit(0)

    if not FRAMEWORK_MARKER.exists():
        print(f"{yellow('WARNING:')} No adoption marker found. Run --adopt first.")
        sys.exit(1)

    # Optionally refresh source from upstream before comparing.
    if getattr(args, "refresh", False):
        _git_pull_source()

    local_version, _ = _extract_version_from_framework()
    recorded_version = _extract_version_from_marker()

    if local_version == recorded_version:
        print(f"{green('UP TO DATE')} — v{local_version}")
        sys.exit(0)
    else:
        print(f"{yellow('UPDATE AVAILABLE')} — v{recorded_version} -> v{local_version}")
        print("Run --pull to update.")
        sys.exit(1)


def cmd_pull(args) -> None:
    """Pull latest framework: git-pull source, copy files into project, bump marker."""
    if not (RSI_FRAMEWORK_DIR / "FRAMEWORK.md").exists():
        print(f"{red('ERROR:')} No framework source found at {RSI_FRAMEWORK_DIR}")
        sys.exit(1)

    if IS_SELF_MODE:
        print(f"{cyan('SELF-MODE')} — this project IS the framework; nothing to pull.")
        return

    # 1. Refresh source from upstream git (if applicable).
    print(f"{cyan('[1/4]')} Refreshing source clone...")
    _git_pull_source()

    new_version, _ = _extract_version_from_framework()
    recorded_version = _extract_version_from_marker()

    # 2. Backup current project scripts/ + engine/ (NOT the source dir).
    print(f"{cyan('[2/4]')} Backing up current project framework files...")
    backup_dir = PROJECT_ROOT / ".memory" / "framework-backup"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"v{recorded_version}-{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=True)
    for d in SYNC_DIRS:
        src = PROJECT_ROOT / d
        if src.exists() and src.is_dir():
            shutil.copytree(src, backup_path / d, dirs_exist_ok=True)
    for f in SYNC_FILES:
        src = PROJECT_ROOT / f
        if src.exists() and src.is_file():
            shutil.copy2(src, backup_path / f)
    print(f"  Backup: {backup_path.relative_to(PROJECT_ROOT)}")

    # 3. Copy source → project.
    print(f"{cyan('[3/4]')} Copying source into project...")
    copied = _copy_source_to_project()
    for item in copied:
        print(f"  + {item}")

    # 4. Update version marker.
    print(f"{cyan('[4/4]')} Updating version marker...")
    FRAMEWORK_MARKER.parent.mkdir(parents=True, exist_ok=True)
    FRAMEWORK_MARKER.write_text(new_version, encoding="utf-8")

    changes = _report_changes(new_version)

    print(f"\n{green('PULL COMPLETE')} — v{recorded_version} -> v{new_version}")
    print(f"  Backup:  {backup_path.relative_to(PROJECT_ROOT)}")
    print(f"  Copied:  {len(copied)} item(s)")
    if changes:
        print(f"\n  {cyan('CHANGES:')}")
        for change in changes:
            print(f"    - {change}")
    print("\n  Verify: python3 scripts/self_verify.py --changed-only")


def _report_changes(new_version: str) -> list[str]:
    """Report what's new in the updated framework."""
    changes = []

    changelog = RSI_FRAMEWORK_DIR / "CHANGELOG.md"
    if changelog.exists():
        content = changelog.read_text(encoding="utf-8")
        version_section = re.search(
            rf"(?=##?\s+v?{new_version}\b).*?(?=##?\s+v?\d+\.\d+|\Z)", content, re.DOTALL
        )
        if version_section:
            changes.append(f"See CHANGELOG.md for v{new_version} changes")

    if (RSI_FRAMEWORK_DIR / "PROOF_WRONG_GUIDE.md").exists():
        changes.append("New: PROOF_WRONG_GUIDE.md")

    if (RSI_FRAMEWORK_DIR / "backlog.py").exists():
        changes.append("New: backlog.py (task management)")

    return changes


def cmd_adopt(args) -> None:
    """Record current framework version as the adoption baseline."""
    if not RSI_FRAMEWORK_DIR.exists():
        print(f"{red('ERROR:')} No rsi-framework/ found.")
        sys.exit(1)

    version, _ = _extract_version_from_framework()
    if version == "unknown":
        print(f"{red('ERROR:')} Could not determine framework version.")
        sys.exit(1)

    FRAMEWORK_MARKER.parent.mkdir(parents=True, exist_ok=True)
    FRAMEWORK_MARKER.write_text(version, encoding="utf-8")

    today = date.today().isoformat()
    _init_feedback_template()

    print(f"{green('ADOPTED')} RSI Framework v{version} on {today}")
    print(f"  Version marker: {FRAMEWORK_MARKER.relative_to(PROJECT_ROOT)}")
    print(f"  Feedback file:  {FEEDBACK_FILE.relative_to(PROJECT_ROOT)}")
    print("\n  Run --status to see current state.")
    print("  Run --check periodically to detect updates.")


def _init_feedback_template() -> None:
    """Initialize feedback file with template if empty."""
    if FEEDBACK_FILE.exists():
        return

    template = f"""# Framework Feedback

> Structured feedback for the RSI Framework maintainer.
> This file captures pain points, concerns, and suggestions for scrutiny.
> Submit via: paste contents of this file into a GitHub Issue on the main repo.

## Project Info

**Project:** {PROJECT_ROOT.name}
**Adopted framework version:** {FRAMEWORK_MARKER.read_text(encoding="utf-8").strip() if FRAMEWORK_MARKER.exists() else "unknown"}
**Date:** {date.today().isoformat()}

---

## Pain Points

<!-- What's frustrating or broken? -->

---

## Concerns

<!-- What worries you about the framework? -->

---

## Suggestions for Scrutiny

<!-- What should the maintainer look at? -->

---

## Usage Evidence

<!-- How has the framework been used in this project? -->

---

## Log

| Date | Action |
|---|---|
| {date.today().isoformat()} | Framework adopted |
"""
    _save_feedback(template)


def cmd_feedback(args) -> None:
    """Open or show the framework feedback file."""
    if not FEEDBACK_FILE.exists():
        _init_feedback_template()

    if args.edit:
        import subprocess

        editor = subprocess.os.environ.get("EDITOR", "nano")
        subprocess.run([editor, str(FEEDBACK_FILE)])
    elif args.show:
        print(FEEDBACK_FILE.read_text(encoding="utf-8"))
    elif args.reset:
        _init_feedback_template()
        print(f"{green('Reset')} feedback file.")
    else:
        print(f"Feedback file: {FEEDBACK_FILE}")
        print("Run --feedback --edit to modify, --feedback --show to view.")
        print("Run --feedback --reset to re-initialize.")


def cmd_help(args) -> None:
    """Show detailed help."""
    print("""
RSI Framework Sync

Adoption (first time):
    python3 scripts/framework_sync.py --adopt
        Records your current framework version. Run once after copying framework.

Update check (regular):
    python3 scripts/framework_sync.py --check
        Checks if a newer version is available.

Update pull (when update found):
    python3 scripts/framework_sync.py --pull
        Backs up current framework, pulls latest, updates version marker.

Status:
    python3 scripts/framework_sync.py --status
        Shows current version, recorded version, feedback count.

Feedback:
    python3 scripts/framework_sync.py --feedback           # Show file location
    python3 scripts/framework_sync.py --feedback --edit    # Edit feedback
    python3 scripts/framework_sync.py --feedback --show    # Show feedback
    python3 scripts/framework_sync.py --feedback --reset   # Reset template

How it works:
    - Version is extracted from rsi-framework/FRAMEWORK.md (Status: vX.Y)
    - --adopt writes version to .memory/.framework_version
    - --check compares local version vs recorded version
    - --pull backs up to .memory/framework-backup/ then updates marker
    - Feedback is stored in .memory/framework-feedback.md for maintainer review
""")


def main():
    parser = argparse.ArgumentParser(
        description="RSI Framework sync manager — check and pull updates"
    )
    parser.add_argument("--status", action="store_true", help="Show framework version status")
    parser.add_argument("--check", action="store_true", help="Check if update available")
    parser.add_argument(
        "--pull", action="store_true", help="Pull latest framework (backup + update)"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="With --check or --pull: git-pull the source clone before comparing/copying.",
    )
    parser.add_argument(
        "--adopt", action="store_true", help="Record framework adoption (first time)"
    )
    parser.add_argument("--feedback", action="store_true", help="Work with feedback file")
    parser.add_argument(
        "--feedback-edit", dest="feedback_edit", action="store_true", help="Edit feedback file"
    )
    parser.add_argument(
        "--feedback-show", dest="feedback_show", action="store_true", help="Show feedback file"
    )
    parser.add_argument(
        "--feedback-reset", dest="feedback_reset", action="store_true", help="Reset feedback file"
    )
    parser.add_argument(
        "--help-detailed", dest="help_detailed", action="store_true", help="Show detailed help"
    )

    args = parser.parse_args()

    if args.help_detailed:
        cmd_help(args)
    elif args.status:
        cmd_status(args)
    elif args.check:
        cmd_check(args)
    elif args.pull:
        cmd_pull(args)
    elif args.adopt:
        cmd_adopt(args)
    elif args.feedback:
        args.edit = args.feedback_edit
        args.show = args.feedback_show
        args.reset = args.feedback_reset
        cmd_feedback(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
