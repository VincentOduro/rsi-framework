#!/usr/bin/env python3
"""
session_brief.py -- Auto-generated session brief from .memory/ data.

Inspired by Addy Osmani's compound learning / AGENTS.md pattern.
Every session starts with accumulated context — the agent never
starts from zero.

Generated on `rsi.py init`. Also written to .memory/session-brief.md
so the agent can re-read if context is lost.

Usage:
    python3 scripts/session_brief.py          # Print brief
    python3 scripts/session_brief.py --save   # Print + save to file
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
MEMORY_ROOT = PROJECT_ROOT / ".memory"
BRIEF_FILE = MEMORY_ROOT / "session-brief.md"


def _section(title: str, items: list[str], empty_msg: str = "(none)") -> str:
    """Build a brief section."""
    lines = [f"  {title}:"]
    if items:
        for item in items[:5]:
            lines.append(f"    {item}")
        if len(items) > 5:
            lines.append(f"    ... and {len(items) - 5} more")
    else:
        lines.append(f"    {empty_msg}")
    return "\n".join(lines)


def _open_hypotheses() -> list[str]:
    """Get open proof-wrong hypotheses from calibration."""
    hyp_file = MEMORY_ROOT / "calibration" / "hypotheses.jsonl"
    if not hyp_file.exists():
        return []
    items = []
    with open(hyp_file) as f:
        for line in f:
            if line.strip():
                try:
                    h = json.loads(line)
                    if h.get("status") == "open":
                        items.append(f"{h['id']}: {h['hypothesis'][:60]}")
                except (json.JSONDecodeError, KeyError):
                    pass
    return items


def _pending_reviews() -> list[str]:
    """Get pending review queue items."""
    pending_dir = MEMORY_ROOT / "reviews" / "pending"
    if not pending_dir.exists():
        return []
    items = []
    for f in sorted(pending_dir.glob("*.md")):
        items.append(f.stem)
    return items


def _recent_fail_patterns() -> list[str]:
    """Get FAIL-index entries."""
    fail_file = MEMORY_ROOT / "technical" / "FAIL-index.md"
    if not fail_file.exists():
        return []
    items = []
    for line in fail_file.read_text(encoding="utf-8").split("\n"):
        if line.strip().startswith("| FAIL-"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3:
                items.append(f"{parts[0]}: {parts[1]}")
    return items


def _top_patterns() -> list[str]:
    """Get documented patterns from patterns.md."""
    pat_file = MEMORY_ROOT / "technical" / "patterns.md"
    if not pat_file.exists():
        return []
    items = []
    for line in pat_file.read_text(encoding="utf-8").split("\n"):
        if line.startswith("## ") and line != "## ":
            items.append(line[3:].strip())
    return items


def _last_session() -> list[str]:
    """Get summary from most recent round log."""
    rounds_dir = MEMORY_ROOT / "rounds"
    if not rounds_dir.exists():
        return []
    rounds = sorted(rounds_dir.glob("round-*.md"), reverse=True)
    if not rounds:
        return []
    latest = rounds[0]
    items = [f"Round: {latest.name}"]
    content = latest.read_text(encoding="utf-8")
    # Extract status
    for line in content.split("\n"):
        if "**Status:**" in line:
            items.append(line.strip())
            break
    return items


def _worker_trust() -> list[str]:
    """Get worker trust scores from delegation history."""
    log_file = MEMORY_ROOT / "metrics" / "delegations.jsonl"
    if not log_file.exists():
        return ["No delegation history yet"]

    by_verdict = {"ACCEPTED": 0, "REJECTED": 0, "FAILED": 0, "PENDING": 0}
    total = 0
    with open(log_file) as f:
        for line in f:
            if line.strip():
                try:
                    e = json.loads(line)
                    verdict = e.get("verdict", "PENDING")
                    by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
                    total += 1
                except json.JSONDecodeError:
                    pass

    if total == 0:
        return ["No delegation history yet"]

    accepted = by_verdict.get("ACCEPTED", 0)
    rate = round(accepted / total * 100) if total else 0
    return [
        f"Total delegations: {total}",
        f"Accept rate: {rate}% ({accepted}/{total})",
        f"Rejected: {by_verdict.get('REJECTED', 0)} | Failed: {by_verdict.get('FAILED', 0)}",
    ]


def _metrics_snapshot() -> list[str]:
    """Quick metrics snapshot."""
    events_file = MEMORY_ROOT / "metrics" / "events.jsonl"
    if not events_file.exists():
        return []

    task_count = 0
    with open(events_file) as f:
        for line in f:
            if '"task_complete"' in line:
                task_count += 1

    if task_count == 0:
        return []
    return [f"Tasks completed (all time): {task_count}"]


def generate_brief() -> str:
    """Generate the full session brief."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    hypotheses = _open_hypotheses()
    reviews = _pending_reviews()
    fails = _recent_fail_patterns()
    patterns = _top_patterns()
    last = _last_session()
    trust = _worker_trust()
    metrics = _metrics_snapshot()

    lines = [
        f"SESSION BRIEF ({now})",
        "=" * 50,
    ]

    # Blocking items first
    if reviews:
        lines.append("")
        lines.append(_section("PENDING REVIEWS (clear before new work)", reviews))

    lines.append("")
    lines.append(_section("Open hypotheses", hypotheses, "All resolved"))

    lines.append("")
    lines.append(_section("Worker trust", trust))

    lines.append("")
    lines.append(_section("FAIL-index", fails, "No entries"))

    if patterns:
        lines.append("")
        lines.append(_section("Documented patterns", patterns))

    if metrics:
        lines.append("")
        lines.append(_section("Metrics", metrics))

    if last:
        lines.append("")
        lines.append(_section("Last session", last))

    lines.append("")
    lines.append("=" * 50)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="RSI Session Brief")
    parser.add_argument("--save", action="store_true", help="Also save to .memory/session-brief.md")
    args = parser.parse_args()

    brief = generate_brief()
    print(brief)

    if args.save:
        BRIEF_FILE.parent.mkdir(parents=True, exist_ok=True)
        BRIEF_FILE.write_text(brief, encoding="utf-8")
        print(f"\nSaved to {BRIEF_FILE.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
