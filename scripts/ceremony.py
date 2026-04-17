#!/usr/bin/env python3
"""
Ceremony classifier — Heijunka (leveled workload) for the RSI framework.

Toyota Principle 4: Level out the workload.

Not every change needs the same ceremony. A one-line config fix doesn't
need 2 bug hypotheses, 2 optimization suggestions, and a pattern review.
That's muda (waste). But a cross-module refactor needs MORE than the
standard loop.

This module classifies changes by scope and returns the appropriate
ceremony level, matching process weight to actual risk.

Ceremony levels:
  - minimal:     Capture only (proof-wrong still mandatory). Config, docs, typos.
  - standard:    Full A->B->C. Normal code changes.
  - thorough:    A->B->C + open hypotheses review + FAIL-index check.
  - major:       A->B->C + 5-Whys consideration + architecture review.
"""

import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ---------------------------------------------------------------------------
# Change classification
# ---------------------------------------------------------------------------

# File patterns that indicate low-risk changes
LOW_RISK_PATTERNS = {
    ".md",
    ".txt",
    ".rst",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".gitignore",
    ".editorconfig",
    ".prettierrc",
}

# File patterns that indicate high-risk changes
HIGH_RISK_DIRS = {"src/", "lib/", "app/", "pkg/", "internal/"}


def classify_change(
    files_changed: list[str] | None = None,
    lines_added: int = 0,
    lines_removed: int = 0,
) -> dict[str, Any]:
    """Classify a change and return the required ceremony level.

    Returns:
        {
            "level": "minimal|standard|thorough|major",
            "reason": str,
            "files_changed": int,
            "lines_changed": int,
            "risk_factors": list[str],
            "required_steps": list[str],
        }
    """
    if files_changed is None:
        files_changed = _get_changed_files()

    total_lines = lines_added + lines_removed
    if not total_lines:
        total_lines = _count_changed_lines()

    num_files = len(files_changed)
    risk_factors = []

    # Analyze file types
    code_files = []
    doc_files = []
    config_files = []
    test_files = []

    for f in files_changed:
        p = Path(f)
        if p.suffix in LOW_RISK_PATTERNS:
            if p.suffix == ".md":
                doc_files.append(f)
            else:
                config_files.append(f)
        elif "test" in f.lower() or "_test." in f or f.startswith("tests/"):
            test_files.append(f)
        else:
            code_files.append(f)

    # Check for cross-module changes
    directories = {str(Path(f).parent) for f in code_files}
    if len(directories) > 3:
        risk_factors.append(f"Cross-module: {len(directories)} directories touched")

    # Check for API/interface changes
    for f in code_files:
        content = _read_file_safe(f)
        if content:
            if "def __init__" in content or "class " in content:
                if "api" in f.lower() or "interface" in f.lower() or "schema" in f.lower():
                    risk_factors.append(f"API/interface change: {f}")
            if "migration" in f.lower():
                risk_factors.append(f"Database migration: {f}")

    # Determine level
    if not code_files and total_lines < 20:
        level = "minimal"
        reason = "Documentation/config only, small change"
    elif num_files <= 2 and total_lines < 30 and not risk_factors:
        level = "standard"
        reason = f"{num_files} file(s), {total_lines} lines, no risk factors"
    elif num_files <= 5 and total_lines < 100 and len(risk_factors) <= 1:
        level = "standard"
        reason = f"{num_files} file(s), {total_lines} lines"
    elif num_files > 5 or total_lines > 200 or len(risk_factors) > 1:
        level = "major"
        reason = f"{num_files} file(s), {total_lines} lines, {len(risk_factors)} risk factor(s)"
    else:
        level = "thorough"
        reason = f"{num_files} file(s), {total_lines} lines, {len(risk_factors)} risk factor(s)"

    # Force thorough+ if risk factors exist
    if risk_factors and level == "standard":
        level = "thorough"
        reason += " (elevated due to risk factors)"

    return {
        "level": level,
        "reason": reason,
        "files_changed": num_files,
        "lines_changed": total_lines,
        "code_files": len(code_files),
        "doc_files": len(doc_files),
        "config_files": len(config_files),
        "test_files": len(test_files),
        "risk_factors": risk_factors,
        "required_steps": CEREMONY_STEPS[level],
    }


# ---------------------------------------------------------------------------
# Ceremony step definitions
# ---------------------------------------------------------------------------

CEREMONY_STEPS = {
    "minimal": [
        "Capture: record what changed and why",
        "Proof-wrong: one specific hypothesis (mandatory even for docs)",
        "Commit with memory update",
    ],
    "standard": [
        "Self-verify: syntax + tests",
        "Module A: capture (task, succeeded, failed, proof-wrong)",
        "Module B: review (2 bugs, 2 optimizations, 1 maintainability)",
        "Module C: optimize (prioritize, document patterns)",
        "Commit with memory update",
    ],
    "thorough": [
        "Self-verify: syntax + tests",
        "Module A: capture (task, succeeded, failed, proof-wrong)",
        "Module B: review (2 bugs, 2 optimizations, 1 maintainability)",
        "Review open hypotheses from calibration tracker",
        "Check FAIL-index for relevant failure modes",
        "Module C: optimize (prioritize, document patterns)",
        "Commit with memory update",
    ],
    "major": [
        "Self-verify: syntax + tests",
        "Module A: capture (task, succeeded, failed, proof-wrong)",
        "Module B: review (3+ bugs, 3+ optimizations, 2+ maintainability)",
        "Review ALL open hypotheses from calibration tracker",
        "Check FAIL-index for ALL related failure modes",
        "Consider 5-Whys if this change addresses a defect",
        "Architecture review: side-effect scan across modules",
        "Module C: optimize (prioritize, document patterns)",
        "Commit with memory update",
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_changed_files() -> list[str]:
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
    for output in [result.stdout, staged.stdout]:
        for line in output.strip().split("\n"):
            line = line.strip()
            if line:
                files.add(line)
    return sorted(files)


def _count_changed_lines() -> int:
    result = subprocess.run(
        ["git", "diff", "--stat", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    # Parse last line: " N files changed, X insertions(+), Y deletions(-)"
    for line in reversed(result.stdout.strip().split("\n")):
        if "changed" in line:
            import re

            nums = re.findall(r"(\d+)", line)
            if len(nums) >= 2:
                return sum(int(n) for n in nums[1:])
    return 0


def _read_file_safe(filepath: str) -> str:
    try:
        return (PROJECT_ROOT / filepath).read_text(encoding="utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    from scripts.colors import bold, cyan, green, red, yellow

    parser = argparse.ArgumentParser(description="RSI Ceremony Classifier — Heijunka")
    parser.add_argument("--files", nargs="*", help="Files to classify (default: git diff)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    result = classify_change(files_changed=args.files)

    if args.json:
        import json

        print(json.dumps(result, indent=2))
        return

    level_color = {
        "minimal": green,
        "standard": cyan,
        "thorough": yellow,
        "major": red,
    }
    color = level_color.get(result["level"], str)

    print(f"\n{'=' * 60}")
    print(f"CEREMONY LEVEL: {color(bold(result['level'].upper()))}")
    print(f"{'=' * 60}\n")
    print(f"  Reason:  {result['reason']}")
    print(
        f"  Files:   {result['files_changed']} ({result['code_files']} code, {result['doc_files']} docs, {result['config_files']} config, {result['test_files']} tests)"
    )
    print(f"  Lines:   {result['lines_changed']}")

    if result["risk_factors"]:
        print(f"\n  {yellow('Risk factors:')}")
        for rf in result["risk_factors"]:
            print(f"    ! {rf}")

    print(f"\n  {bold('Required steps:')}")
    for i, step in enumerate(result["required_steps"], 1):
        print(f"    {i}. {step}")
    print()


if __name__ == "__main__":
    main()
