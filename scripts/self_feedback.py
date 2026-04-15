#!/usr/bin/env python3
"""
Module B: Self-Feedback — Post-Implementation Review

Run this after Module A (post_implementation.py) for every code change.

What it does:
1. Review: Identify at least 2 potential bugs or edge cases in the code just written
2. Optimize: Suggest 2 ways to improve efficiency
3. Improve: Suggest 1 way to improve maintainability
4. Log findings to memory (technical/ directory)

Usage:
    python3 scripts/self_feedback.py
    python3 scripts/self_feedback.py --task "H-2 fix" --files src/wandering_codex/api/progression.py
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
MEMORY_ROOT = PROJECT_ROOT / ".memory"
TECHNICAL_DIR = MEMORY_ROOT / "technical"
AGENTS_DIR = MEMORY_ROOT / "agents"


def green(msg: str) -> str:
    return f"\033[92m{msg}\033[0m"


def red(msg: str) -> str:
    return f"\033[91m{msg}\033[0m"


def yellow(msg: str) -> str:
    return f"\033[93m{msg}\033[0m"


def _read_file(path: Path) -> str:
    try:
        return path.read_text()
    except Exception:
        return ""


def get_changed_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def log_feedback_to_file(
    task: str,
    reviews: list[dict],
    optimizations: list[dict],
    improvements: list[dict],
) -> None:
    """Append self-feedback findings to a feedback log."""
    feedback_file = TECHNICAL_DIR / "feedback-log.md"
    if not feedback_file.exists():
        feedback_file.write_text("# Self-Feedback Log\n\n")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    entry = f"""
## {task} — {timestamp}

### Review: Potential bugs / edge cases
"""
    for i, r in enumerate(reviews, 1):
        entry += f"{i}. [{'CONFIRMED' if r.get('confirmed') else 'UNCONFIRMED'}] {r['description']}"
        if r.get("file"):
            entry += f" (file: {r['file']}, line ~{r.get('line', '?')})"
        if r.get("verification"):
            entry += f"\n   Verification: {r['verification']}"
        entry += "\n"

    entry += "\n### Optimize: Efficiency improvements\n"
    for i, o in enumerate(optimizations, 1):
        entry += f"{i}. {o['description']}"
        if o.get("impact"):
            entry += f" — Impact: {o['impact']}"
        entry += "\n"

    entry += "\n### Improve: Maintainability\n"
    for i, m in enumerate(improvements, 1):
        pattern_marker = " [PATTERN]" if m.get("is_pattern_candidate") else ""
        entry += f"{i}. {m['description']}{pattern_marker}"
        if m.get("applies_to"):
            entry += f" — Applies to: {m['applies_to']}"
        entry += "\n"

    entry += "\n---\n"
    feedback_file.write_text(feedback_file.read_text() + entry)
    print(f"{green('Logged to feedback-log.md')}")


def review_code(files: list[str]) -> list[dict]:
    """Review the changed files for potential bugs/edge cases. Returns list of findings."""
    findings = []

    for file in files:
        path = PROJECT_ROOT / file
        if not path.exists():
            continue

        content = path.read_text()
        lines = content.splitlines()

        # Check for common bug patterns
        bug_checks = [
            ("MagicMock subscript", "MagicMock()[0] returns MagicMock, not real value — use MagicMock(data=[real_dict])"),
            (".data[0] without guard", "Accessing .data[0] without checking .data — IndexError if empty"),
            ("await inside list comprehension", "await in list comprehension doesn't work — use [await f() for f in xs] or gather()"),
            ("global without declaration", "global variable used without 'global' keyword in same function"),
            ("return await in async", "return await is redundant in async — use return directly"),
            ("mutable default arg", "Mutable default argument persists across calls — use None"),
            ("bare except:", "Bare except catches everything including SystemExit — use except Exception:"),
            ("shadowing built-in", "Variable shadows built-in name (e.g., 'id', 'type', 'list')"),
        ]

        for keyword, description in bug_checks:
            for i, line in enumerate(lines, 1):
                if keyword in line:
                    # Skip comments
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    findings.append({
                        "description": f"{description}",
                        "file": file,
                        "line": i,
                        "confirmed": False,
                        "verification": f"Found: {line.strip()[:80]}",
                    })

        # Check for unhandled edge cases in Supabase queries
        if "execute()" in content:
            # Check for execute() without try/except
            for i, line in enumerate(lines, 1):
                if ".execute()" in line and not any("try:" in lines[max(0, i-3):i] for _ in [1]):
                    stripped = line.strip()
                    if stripped.startswith("#") or "try:" in stripped:
                        continue
                    # Heuristic: if we're inside a try block, skip
                    before = "\n".join(lines[max(0, i-10):i])
                    if "try:" not in before:
                        findings.append({
                            "description": f"execute() call without visible try/except",
                            "file": file,
                            "line": i,
                            "confirmed": False,
                            "verification": f"Found: {line.strip()[:80]}",
                        })

    return findings


def _prompt_for_findings(prompt: str, min_count: int, ask_pattern: bool = False) -> list[dict]:
    """Prompt the user for findings and return as list of dicts."""
    print(f"\n{prompt}")
    print("(Enter empty line when done)")
    results = []
    while True:
        line = input(f"  > ").strip()
        if not line:
            break
        if len(results) >= min_count:
            confirm_more = input(f"  Got {len(results)}, add more? (y/n): ").strip().lower()
            if confirm_more != "y":
                break
        entry = {"description": line, "confirmed": False, "verification": ""}
        if ask_pattern:
            is_pattern = input("    Is this a reusable pattern? (y/N): ").strip().lower()
            entry["is_pattern_candidate"] = is_pattern == "y"
        results.append(entry)
    return results


def interactive_review(task: str, files: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    """Interactive self-feedback capture."""
    print("\n" + "=" * 60)
    print("MODULE B: SELF-FEEDBACK")
    print("=" * 60)
    print(f"\nTask: {task}")
    if files:
        print(f"Files: {', '.join(files)}")

    # Auto-review first
    print(f"\n{yellow('Running automated code review...')}")
    findings = review_code(files)
    if findings:
        print(f"\n{len(findings)} potential issue(s) found:")
        for f in findings:
            print(f"  [{f['file']}:{f['line']}] {f['description']}")
        confirm = input("\nKeep these findings? (Y/n): ").strip().lower()
        if confirm == "n":
            findings = []
        else:
            confirmed_str = input("Mark all confirmed? (y/N): ").strip().lower()
            if confirmed_str == "y":
                for f in findings:
                    f["confirmed"] = True
    else:
        print(f"{green('No obvious issues detected automatically.')}")

    # Manual review
    print("\n" + "-" * 40)
    manual_reviews = _prompt_for_findings(
        "Review: Identify at least 2 potential bugs or edge cases in the code just written:",
        min_count=2,
    )
    findings.extend(manual_reviews)

    print("\n" + "-" * 40)
    optimizations = _prompt_for_findings(
        "Optimize: Suggest 2 ways to improve efficiency:",
        min_count=2,
    )
    for o in optimizations:
        o["impact"] = input(f"  Impact of '{o['description'][:40]}...': ").strip()

    print("\n" + "-" * 40)
    improvements = _prompt_for_findings(
        "Improve: Suggest 1 way to improve maintainability:",
        min_count=1,
        ask_pattern=True,  # Improvements often reveal reusable patterns
    )
    for m in improvements:
        m["applies_to"] = input(f"  Applies to (file/component): ").strip()

    return findings, optimizations, improvements


def main():
    parser = argparse.ArgumentParser(description="Module B: Self-feedback")
    parser.add_argument("--task", help="Task name")
    parser.add_argument("--files", nargs="*", help="Files to review")
    args = parser.parse_args()

    if not args.files:
        files = get_changed_files()
    else:
        files = args.files

    task = args.task or input("Task name: ").strip() or "Unnamed task"

    findings, optimizations, improvements = interactive_review(task, files)

    # Log to file
    log_feedback_to_file(task, findings, optimizations, improvements)

    # Unconfirmed bugs → always create follow-up tasks (mandatory)
    unconfirmed = [f for f in findings if not f.get("confirmed")]
    if unconfirmed:
        print(f"\n{yellow('Unconfirmed issues — creating follow-up tasks:')}")
        tracker = AGENTS_DIR / "current-task.md"
        if not tracker.exists():
            (AGENTS_DIR / "current-task.md").write_text("# Current Task\n\n## Pending Tasks\n\n")
        content = tracker.read_text()
        for f in unconfirmed:
            entry = f"\n- [ ] REVIEW: {f['description']} (file: {f['file']}:{f['line']})"
            content += entry
        tracker.write_text(content)
        print(f"{green('Added follow-up tasks to current-task.md')}")

    print(f"\n{green('Self-feedback complete.')}")
    print(f"  python3 scripts/self_optimization.py")


if __name__ == "__main__":
    main()
