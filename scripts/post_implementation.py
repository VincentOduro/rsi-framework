#!/usr/bin/env python3
"""
Module A: Short-term Memory — Post-Implementation Capture

Run this after EVERY code change, before declaring success.

What it does:
1. Asks "What was attempted, what succeeded, what failed?"
2. Saves findings to the current round log
3. Updates the task tracker

Usage:
    python3 scripts/post_implementation.py
    python3 scripts/post_implementation.py --task "H-2 fix" --succeeded "Client moved to startup" --failed "None" --notes "Used -B flag to avoid bytecode caching"
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path("/home/ajeem/wandering_codex")
MEMORY_ROOT = PROJECT_ROOT / ".memory"
ROUNDS_DIR = MEMORY_ROOT / "rounds"
AGENTS_DIR = MEMORY_ROOT / "agents"
MEMORY_FILE = PROJECT_ROOT / "MEMORY.md"


def green(msg: str) -> str:
    return f"\033[92m{msg}\033[0m"


def red(msg: str) -> str:
    return f"\033[91m{msg}\033[0m"


def yellow(msg: str) -> str:
    return f"\033[93m{msg}\033[0m"


def get_current_round() -> Path:
    """Find the most recent round file (highest round number)."""
    rounds = sorted(ROUNDS_DIR.glob("round-*.md"), reverse=True)
    if rounds:
        return rounds[0]
    # No rounds yet — create round-001
    path = ROUNDS_DIR / "round-001.md"
    _create_round_template(path)
    return path


def _create_round_template(path: Path) -> None:
    """Create a new round file from template."""
    num = path.stem.replace("round-", "")
    content = f"""# Round {num} — {datetime.now().strftime("%Y-%m-%d")}

**Status:** IN PROGRESS
**Started:** {datetime.now().strftime("%Y-%m-%d %H:%M")}

---

## Task Description

<!-- What was the goal of this round? -->

---

## Approach Taken

<!-- How did we attempt to solve it? -->

---

## Implementation Log

### Attempt 1
**What was attempted:**
**What succeeded:**
**What failed:**
**Date:** {datetime.now().strftime("%Y-%m-%d")}

---

## Results

<!-- Metrics, test results, self-verify output -->

| Metric | Value |
|---|---|
| Tests passed | <!-- N/N --> |
| Files changed | <!-- N --> |
| self_verify | <!-- PASS/FAIL --> |

---

## Learnings

### What worked
<!-- -->

### What failed
<!-- -->

### Key insights
<!-- -->

---

## Next Steps

<!-- Specific, actionable next steps -->

---

## Status

**Status:** IN PROGRESS
**Last updated:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
"""
    path.write_text(content.lstrip())


def _parse_round_num(filename: str) -> int:
    try:
        return int(filename.replace("round-", "").replace(".md", ""))
    except ValueError:
        return 0


def create_new_round() -> Path:
    """Create the next round file and return its path."""
    existing = sorted(ROUNDS_DIR.glob("round-*.md"), key=lambda p: _parse_round_num(p.stem))
    if existing:
        last_num = _parse_round_num(existing[-1].stem)
    else:
        last_num = 0
    new_num = last_num + 1
    path = ROUNDS_DIR / f"round-{new_num:03d}.md"
    _create_round_template(path)
    print(f"{green('Created new round:')} {path.name}")
    return path


def update_round_log(
    task: str,
    succeeded: str,
    failed: str,
    proof_wrong: str,
    notes: str,
    files_changed: list[str],
) -> None:
    """Append an implementation entry to the current round log."""
    round_file = get_current_round()
    content = round_file.read_text()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Check if round is marked COMPLETE — if so, create new round
    if "**Status:** COMPLETE" in content:
        round_file = create_new_round()
        content = round_file.read_text()

    # Find the Implementation Log section and append
    marker = "## Implementation Log"
    proof_block = f"\n\n**What could prove this WRONG:** {proof_wrong}"
    entry = f"""

### Attempt (latest)
**Task:** {task}
**What succeeded:** {succeeded}
**What failed:** {failed}
**Files changed:** {", ".join(files_changed) if files_changed else "none"}
**Notes:** {notes}{proof_block}
**Date:** {timestamp}
"""
    if marker in content:
        idx = content.index(marker) + len(marker)
        # Find the next top-level heading or end of file
        remaining = content[idx:]
        next_heading = remaining.find("\n## ")
        if next_heading != -1:
            content = content[: idx + next_heading] + entry + remaining[next_heading:]
        else:
            content = content + entry
    else:
        # No implementation log section yet — add it
        section = f"""

{marker}

### Attempt (latest)
**Task:** {task}
**What succeeded:** {succeeded}
**What failed:** {failed}
**Files changed:** {", ".join(files_changed) if files_changed else "none"}
**Notes:** {notes}{proof_block}
**Date:** {timestamp}
"""
        content = content.rstrip() + section

    round_file.write_text(content)
    print(f"{green('Updated round log:')} {round_file.name}")


def update_task_tracker(
    task: str,
    status: str,  # "in_progress", "completed", "blocked"
    notes: str = "",
) -> None:
    """Update the current-task.md tracker."""
    tracker = AGENTS_DIR / "current-task.md"
    if not tracker.exists():
        _create_default_tracker(tracker)

    content = tracker.read_text()

    # Find the task entry and update it
    # Format: - [ ] TASK_NAME — ...
    marker = f"- [ ] {task}"
    marker_done = f"- [x] {task}"

    if marker in content:
        updated_marker = f"- [{'x' if status == 'completed' else ' '}] {task}"
        content = content.replace(marker, updated_marker, 1)
        if notes:
            # Add notes after the task line
            line_idx = content.index(updated_marker)
            rest = content[line_idx:]
            next_line = rest.find("\n- [")
            if next_line != -1:
                insert_pos = line_idx + next_line
                content = content[:insert_pos] + f" — {notes}" + content[insert_pos:]
            else:
                content = content + f" — {notes}"
    elif marker_done in content and status != "completed":
        # Re-open a completed task
        updated_marker = f"- [ ] {task}"
        content = content.replace(marker_done, updated_marker, 1)

    tracker.write_text(content)
    print(f"{green('Updated task tracker')}")


def run_self_verify(files: list[str]) -> bool:
    """Run self_verify.py and return True if passed."""
    if not files:
        return True
    result = subprocess.run(
        [sys.executable, "scripts/self_verify.py", "--files"] + files,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode == 0


def run_tests() -> tuple[bool, str]:
    """Run pytest and return (passed, summary_line)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    summary = ""
    for line in result.stdout.splitlines():
        if "passed" in line and "failed" not in line:
            summary = line.strip()
            break
    return result.returncode == 0, summary


def interactive_capture() -> dict:
    """Prompt the user for implementation details. Returns dict."""
    print("\n" + "=" * 60)
    print("POST-IMPLEMENTATION CAPTURE")
    print("=" * 60)

    task = input("\nTask name (e.g. H-2 fix): ").strip()
    if not task:
        task = "(unnamed task)"

    print("\nWhat was attempted?")
    attempted = input("  > ").strip()

    print("\nWhat SUCCEEDED?")
    succeeded = input("  > ").strip()

    print("\nWhat FAILED (or is uncertain)?")
    failed = input("  > ").strip()

    print("\n" + "-" * 40)
    print("MANDATORY: What could PROVE THIS WRONG?")
    print("-" * 40)
    print("Name at least one specific thing that, if true, would mean this fix is")
    print("incorrect, incomplete, or would break something else.")
    print("Be specific. Vague answers = fix is not ready.")
    print("(Enter empty line to skip — but skipping is a red flag.)")
    proof_wrong = input("  > ").strip()
    while not proof_wrong:
        print(f"  {yellow('Red flag: this is mandatory. What could prove this wrong?')}")
        proof_wrong = input("  > ").strip()

    print("\nAny notes?")
    notes = input("  > ").strip()

    files_str = input("\nFiles changed (comma-separated, press Enter for self-verify): ").strip()
    files = [f.strip() for f in files_str.split(",") if f.strip()] if files_str else []

    return {
        "task": task,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "proof_wrong": proof_wrong,
        "notes": notes,
        "files": files,
    }


def main():
    parser = argparse.ArgumentParser(description="Module A: Post-implementation memory capture")
    parser.add_argument("--task", help="Task name")
    parser.add_argument("--succeeded", help="What succeeded")
    parser.add_argument("--failed", help="What failed")
    parser.add_argument("--proof-wrong", help="MANDATORY: What could prove this wrong? (required)")
    parser.add_argument("--notes", help="Additional notes")
    parser.add_argument("--files", nargs="*", help="Files changed")
    parser.add_argument("--interactive", action="store_true", help="Interactive capture mode")
    args = parser.parse_args()

    print("=" * 60)
    print("MODULE A: SHORT-TERM MEMORY — POST-IMPLEMENTATION CAPTURE")
    print("=" * 60)

    # Get files changed from git
    if not args.files:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    else:
        files = args.files

    # Pre-flight checks — always mandatory, always blocks on failure
    if files:
        print(f"\n{green('Running self-verify on changed files...')}")
        verify_ok = run_self_verify(files)
        if not verify_ok:
            print(f"{red('SELF-VERIFY FAILED — blocking until fixed')}")
            sys.exit(1)

        print(f"\n{green('Running test suite...')}")
        tests_ok, summary = run_tests()
        if not tests_ok:
            print(f"{red('TESTS FAILED — blocking until fixed')}")
            sys.exit(1)

    # Capture details
    if args.interactive or not (args.task and args.succeeded):
        data = interactive_capture()
    else:
        data = {
            "task": args.task or "(unnamed)",
            "succeeded": args.succeeded or "",
            "failed": args.failed or "",
            "proof_wrong": args.proof_wrong or "",
            "notes": args.notes or "",
            "files": files,
        }

    # Validate proof_wrong
    if not data["proof_wrong"]:
        print(f"\n{red('--proof-wrong is REQUIRED for non-interactive capture.')}")
        print(f"Example: --proof-wrong 'If Supabase returns empty data on successful INSERT, safe_first_or_raise would raise instead of returning the id'")
        sys.exit(1)

    # Update round log
    update_round_log(
        task=data["task"],
        succeeded=data["succeeded"],
        failed=data["failed"],
        proof_wrong=data["proof_wrong"],
        notes=data["notes"],
        files_changed=data["files"],
    )

    # Update task tracker — completed if all verification passed
    status = "completed"
    if data["task"] != "(unnamed)":
        update_task_tracker(data["task"], status, data["notes"])

    # Chain to Module B and C — always mandatory
    import importlib
    feedback = importlib.import_module("scripts.self_feedback")
    print(f"\n{yellow('Running Module B: Self-Feedback...')}")
    print("=" * 60)
    findings, optimizations, improvements = feedback.interactive_review(
        data["task"], data["files"]
    )
    feedback.log_feedback_to_file(
        data["task"], findings, optimizations, improvements
    )
    print(f"\n{green('Self-feedback complete.')}")

    print(f"\n{yellow('Running Module C: Self-Optimization...')}")
    print("=" * 60)
    opt = importlib.import_module("scripts.self_optimization")
    opt.main()  # Run full Module C (always writes files)
    print(f"\n{green('Self-optimization complete.')}")


if __name__ == "__main__":
    main()
