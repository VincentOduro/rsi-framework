#!/usr/bin/env python3
"""
Module C: Self-Optimization — Prioritization and Pattern Documentation

Run this after Module B (self_feedback.py) to:
1. Prioritize fixes (critical first)
2. Plan specific next round actions
3. Document patterns for reusable solutions

Usage:
    python3 scripts/self_optimization.py
    python3 scripts/self_optimization.py --plan-only   # Just show priorities, don't write files
"""

import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
MEMORY_ROOT = PROJECT_ROOT / ".memory"
TECHNICAL_DIR = MEMORY_ROOT / "technical"
AGENTS_DIR = MEMORY_ROOT / "agents"
ROUNDS_DIR = MEMORY_ROOT / "rounds"


def green(msg: str) -> str:
    return f"\033[92m{msg}\033[0m"


def yellow(msg: str) -> str:
    return f"\033[93m{msg}\033[0m"


def red(msg: str) -> str:
    return f"\033[91m{msg}\033[0m"


# Priority weights for issue categorization
PRIORITY_WEIGHTS = {
    "CRITICAL": 100,
    "HIGH": 75,
    "MEDIUM": 50,
    "LOW": 25,
    "UNKNOWN": 0,
}


def _read_file(path: Path) -> str:
    try:
        return path.read_text()
    except Exception:
        return ""


def get_feedback_log() -> list[dict]:
    """Parse the feedback log into structured entries."""
    feedback_file = TECHNICAL_DIR / "feedback-log.md"
    if not feedback_file.exists():
        return []

    content = feedback_file.read_text()
    entries = []

    # Very simple parsing — entries are separated by ---
    parts = content.split("\n## ")
    for part in parts[1:]:  # Skip header
        lines = part.split("\n")
        if not lines[0].strip():
            continue
        header = lines[0].strip()
        # Extract task name and timestamp
        timestamp = ""
        task_name = header
        if " — " in header:
            task_name, timestamp = header.rsplit(" — ", 1)

        entry = {
            "task": task_name,
            "timestamp": timestamp,
            "reviews": [],
            "optimizations": [],
            "improvements": [],
        }

        current_section = None
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("### Review:"):
                current_section = "reviews"
            elif stripped.startswith("### Optimize:"):
                current_section = "optimizations"
            elif stripped.startswith("### Improve:"):
                current_section = "improvements"
            elif stripped.startswith("- [") and current_section:
                # Extract the finding text
                text = stripped.lstrip("- [x] ").strip()
                if stripped.startswith("- [x] "):
                    entry[current_section].append({"description": text, "confirmed": True})
                else:
                    entry[current_section].append({"description": text, "confirmed": False})

        entries.append(entry)

    return entries


def get_pending_tasks() -> list[dict]:
    """Read pending tasks from current-task.md."""
    tracker = AGENTS_DIR / "current-task.md"
    if not tracker.exists():
        return []
    content = tracker.read_text()
    tasks = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ] "):
            task_text = stripped[6:]
            # Parse: "TASK_NAME — notes" or just "TASK_NAME"
            if " — " in task_text:
                name, notes = task_text.split(" — ", 1)
            else:
                name, notes = task_text, ""
            tasks.append({"name": name.strip(), "notes": notes.strip(), "done": False})
        elif stripped.startswith("- [x] "):
            task_text = stripped[6:]
            if " — " in task_text:
                name = task_text.split(" — ")[0]
            else:
                name = task_text
            tasks.append({"name": name.strip(), "notes": "", "done": True})
    return [t for t in tasks if not t.get("done")]


def _extract_priority_from_name(name: str) -> tuple[str, str]:
    """Extract priority prefix from task name. Returns (priority, cleaned_name)."""
    import re

    m = re.match(r"^\[((?:CRITICAL|HIGH|MEDIUM|LOW|UNKNOWN))\]\s*(.*)$", name, re.IGNORECASE)
    if m:
        return m.group(1).upper(), m.group(2)
    return "MEDIUM", name  # Default priority


def prioritize_fixes(feedback_entries: list[dict], pending_tasks: list[dict]) -> list[dict]:
    """Sort issues by priority (critical first)."""
    issues = []

    for entry in feedback_entries:
        for review in entry.get("reviews", []):
            issues.append(
                {
                    "source": f"feedback: {entry['task']}",
                    "description": review.get("description", ""),
                    "confirmed": review.get("confirmed", False),
                    "priority": "HIGH" if review.get("confirmed") else "MEDIUM",
                }
            )

    for task in pending_tasks:
        name = task["name"]
        priority, cleaned = _extract_priority_from_name(name)
        issues.append(
            {
                "source": "current-task",
                "description": cleaned if cleaned != name else task["name"],
                "notes": task.get("notes", ""),
                "confirmed": False,
                "priority": priority,
            }
        )

    # Sort by priority weight (descending)
    issues.sort(key=lambda x: PRIORITY_WEIGHTS.get(x["priority"], 0), reverse=True)

    return issues


def suggest_next_round(prioritized: list[dict]) -> list[str]:
    """Generate specific next round actions based on prioritized issues."""
    actions = []
    for issue in prioritized[:5]:  # Top 5
        priority = issue["priority"]
        desc = issue["description"][:60]
        actions.append(f"[{priority}] {desc}")

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for a in actions:
        if a not in seen:
            seen.add(a)
            unique.append(a)

    return unique


def _detect_pattern(description: str, files: list[str]) -> bool:
    """Heuristic: does this finding describe a reusable pattern?"""
    pattern_indicators = [
        "helper function",
        "extract",
        "reuse",
        "repeated",
        "same pattern",
        "duplicated",
        "refactor",
        "extract into",
        "DRY",
        "wrapper",
    ]
    return any(ind in description.lower() for ind in pattern_indicators)


def document_pattern(
    pattern_name: str,
    context: str,
    code_example: str,
    why_it_works: str,
) -> None:
    """Add a pattern to the patterns library."""
    patterns_file = TECHNICAL_DIR / "patterns.md"
    if not patterns_file.exists():
        patterns_file.write_text("# Patterns Library\n\n")

    entry = f"""
## {pattern_name}

**Context:** {context}

**Code example:**
```python
{code_example}
```

**Why it works:** {why_it_works}

---
"""
    patterns_file.write_text(patterns_file.read_text() + entry.lstrip())
    print(f"{green('Documented pattern:')} {pattern_name}")


def prompt_for_patterns(feedback_entries: list[dict]) -> None:
    """Prompt the user to document reusable patterns from feedback.

    Uses explicit is_pattern_candidate flag set during Module B capture.
    Falls back to _detect_pattern heuristic for old entries without the flag.
    """
    print("\n" + "=" * 60)
    print("PATTERN DOCUMENTATION")
    print("=" * 60)

    pattern_findings = []
    for entry in feedback_entries:
        for m in entry.get("improvements", []):
            if m.get("is_pattern_candidate"):
                pattern_findings.append((entry["task"], m["description"], m))
        # Fallback: also check reviews with heuristic
        for review in entry.get("reviews", []):
            desc = review.get("description", "")
            if _detect_pattern(desc, []) and not any(desc == pd[1] for pd in pattern_findings):
                pattern_findings.append((entry["task"], desc, None))

    if not pattern_findings:
        print("\nNo pattern candidates found in feedback.")
        print("(Mark improvements as [PATTERN] during Module B capture to flag them here.)")
        return

    print(f"\n{yellow('Pattern candidates (marked in Module B):')}")
    for i, (task, desc, _) in enumerate(pattern_findings, 1):
        print(f"  {i}. [{task}] {desc[:60]}")

    confirm = input("\nDocument any of these as patterns? (y/N): ").strip().lower()
    if confirm != "y":
        return

    for i, (task, desc, orig) in enumerate(pattern_findings, 1):
        print(f"\n--- Pattern {i} ---")
        name = input(f"Pattern name [{desc[:30]}...]: ").strip() or f"pattern-{i}"
        ctx = input("Context (when to use): ").strip()
        code = input("Code example (paste, Enter for placeholder): ").strip()
        if not code:
            code = "# TODO: add code example"
        why = input("Why it works: ").strip() or "TODO: explain"
        if orig and orig.get("applies_to"):
            ctx = f"{ctx} (flagged from: {orig['applies_to']})"

        document_pattern(name, ctx, code, why)


def write_priorities_to_tracker(prioritized: list[dict], actions: list[str]) -> None:
    """Update current-task.md with prioritization."""
    tracker = AGENTS_DIR / "current-task.md"
    if not tracker.exists():
        tracker.write_text("# Current Task\n\n## Active Tasks\n\n")

    content = tracker.read_text()

    # Remove old prioritization section if present
    if "## Priority Order" in content:
        content = content.split("## Priority Order")[0]

    header = f"""

## Priority Order (auto-generated {datetime.now().strftime("%Y-%m-%d")})

| Priority | Issue | Source | Status |
|---|---|---|---|
"""
    for issue in prioritized:
        status = "CONFIRMED" if issue.get("confirmed") else "review"
        header += f"| {issue['priority']} | {issue['description'][:50]} | {issue['source']} | {status} |\n"

    header += "\n### Suggested Next Round Actions\n"
    for action in actions:
        header += f"- {action}\n"

    content = content.rstrip() + "\n" + header

    tracker.write_text(content)
    print(f"{green('Updated current-task.md with priorities')}")


def main():
    parser = argparse.ArgumentParser(description="Module C: Self-optimization")
    args = parser.parse_args()

    print("=" * 60)
    print("MODULE C: SELF-OPTIMIZATION")
    print("=" * 60)

    # Gather data
    print(f"\n{yellow('Reading feedback log...')}")
    feedback_entries = get_feedback_log()
    print(f"  Found {len(feedback_entries)} feedback entries")

    print(f"{yellow('Reading pending tasks...')}")
    pending_tasks = get_pending_tasks()
    print(f"  Found {len(pending_tasks)} pending tasks")

    # Prioritize
    print(f"\n{yellow('Prioritizing fixes...')}")
    prioritized = prioritize_fixes(feedback_entries, pending_tasks)

    print(f"\n{'Priority':<12} {'Description':<55} {'Source'}")
    print("-" * 90)
    for issue in prioritized:
        desc = issue["description"][:53]
        print(f"{issue['priority']:<12} {desc:<55} {issue['source']}")

    # Suggest next round
    actions = suggest_next_round(prioritized)
    print(f"\n{yellow('Suggested next round actions:')}")
    for action in actions:
        print(f"  - {action}")

    # Write to files and prompt for patterns — always mandatory
    write_priorities_to_tracker(prioritized, actions)
    prompt_for_patterns(feedback_entries)

    print(f"\n{green('Self-optimization complete.')}")
    print("  Updated: current-task.md (priorities), patterns.md (if applicable)")


if __name__ == "__main__":
    main()
