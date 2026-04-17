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
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
RSI_FRAMEWORK_DIR = PROJECT_ROOT / "rsi-framework"

# Detect if this script IS the framework (running from within rsi-framework/)
# In that case, PROJECT_ROOT == framework root, not parent of rsi-framework/
if not RSI_FRAMEWORK_DIR.exists():
    # We're running from within the framework itself
    if (PROJECT_ROOT / "FRAMEWORK.md").exists():
        RSI_FRAMEWORK_DIR = PROJECT_ROOT
    else:
        # Neither rsi-framework/ subdir nor FRAMEWORK.md exists — framework not found
        pass

FRAMEWORK_MARKER = PROJECT_ROOT / ".memory" / ".framework_version"
FEEDBACK_FILE = PROJECT_ROOT / ".memory" / "framework-feedback.md"
FRAMEWORK_TEMPLATE_DIR = RSI_FRAMEWORK_DIR / "MEMORY_TEMPLATE"


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

    content = framework_md.read_text()
    match = re.search(r"\*\*?Status:\*\*?\s*v?(\d+\.\d+)", content, re.IGNORECASE)
    if match:
        return match.group(1), framework_md
    return "unknown", framework_md


def _extract_version_from_marker() -> str:
    """Read the recorded framework version from marker file."""
    if not FRAMEWORK_MARKER.exists():
        return "none"
    return FRAMEWORK_MARKER.read_text().strip()


def _load_feedback() -> str:
    """Load existing feedback if any."""
    if not FEEDBACK_FILE.exists():
        return ""
    return FEEDBACK_FILE.read_text()


def _save_feedback(content: str) -> None:
    """Save feedback content."""
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_FILE.write_text(content)


def cmd_status(args) -> None:
    """Show framework version status."""
    if not RSI_FRAMEWORK_DIR.exists():
        print(f"{red('ERROR:')} No rsi-framework/ found at {RSI_FRAMEWORK_DIR}")
        print("Copy the framework into your project first, then run --adopt.")
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
    print(f"  Framework path:            {RSI_FRAMEWORK_DIR.relative_to(PROJECT_ROOT)}")
    print(f"  Feedback file:            {FEEDBACK_FILE.relative_to(PROJECT_ROOT)}")

    if recorded_version == "none":
        print(f"\n  {yellow('WARNING:')} Run --adopt to record your framework version.")
    elif local_version != recorded_version and recorded_version != "none":
        print(f"\n  {cyan('INFO:')} Update available: v{recorded_version} -> v{local_version}")
        print("  Run --pull to update.")
    else:
        print(f"\n  {green('OK:')} Framework is up to date.")

    print()


def cmd_check(args) -> None:
    """Check if framework update is available."""
    if not RSI_FRAMEWORK_DIR.exists():
        print(f"{red('ERROR:')} No rsi-framework/ found. Copy it first, then run --adopt.")
        sys.exit(1)

    if not FRAMEWORK_MARKER.exists():
        print(f"{yellow('WARNING:')} No adoption marker found. Run --adopt first.")
        sys.exit(1)

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
    """Pull latest framework (backup + replace)."""
    if not RSI_FRAMEWORK_DIR.exists():
        print(f"{red('ERROR:')} No rsi-framework/ found.")
        sys.exit(1)

    old_version, _ = _extract_version_from_framework()
    recorded_version = _extract_version_from_marker()

    if old_version == recorded_version:
        print(f"{green('Already on latest version:')} v{old_version}")
        return

    # Backup
    backup_dir = PROJECT_ROOT / ".memory" / "framework-backup"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"v{old_version}-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"Backing up current framework to {backup_path.relative_to(PROJECT_ROOT)}...")
    shutil.copytree(RSI_FRAMEWORK_DIR, backup_path, dirs_exist_ok=True)

    # Update marker
    FRAMEWORK_MARKER.parent.mkdir(parents=True, exist_ok=True)
    FRAMEWORK_MARKER.write_text(old_version)

    # Find what changed
    changes = _report_changes(old_version)

    print(f"\n{green('BACKUP COMPLETE')}")
    print(f"  Backup location: {backup_path.relative_to(PROJECT_ROOT)}")
    if changes:
        print(f"\n  {cyan('CHANGES:')}")
        for change in changes:
            print(f"    - {change}")
    print(f"\n  Updated version marker: v{old_version}")
    print("\n  To verify the update:")
    print("    python3 scripts/self_verify.py --changed-only")
    print("\n  To record this update in memory:")
    print(
        f"    python3 scripts/post_implementation.py --task 'Updated RSI framework' --succeeded 'Pulled v{old_version} -> v{old_version}' --proof-wrong 'If backup is corrupted, framework files may be unrecoverable'"
    )


def _report_changes(new_version: str) -> list[str]:
    """Report what's new in the updated framework."""
    changes = []

    changelog = RSI_FRAMEWORK_DIR / "CHANGELOG.md"
    if changelog.exists():
        content = changelog.read_text()
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
    FRAMEWORK_MARKER.write_text(version)

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
**Adopted framework version:** {FRAMEWORK_MARKER.read_text().strip() if FRAMEWORK_MARKER.exists() else "unknown"}
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
        print(FEEDBACK_FILE.read_text())
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
RSI Framework Sync — v1.0

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
