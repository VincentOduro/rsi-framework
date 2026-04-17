#!/usr/bin/env python3
"""
review_queue.py — Surfaces pending reviews, blocks new work until queue drained.

Jidoka: stop the line when there's a quality issue.
The overlord must review worker output before starting new work.

Usage:
    python3 scripts/review_queue.py list                    # List pending
    python3 scripts/review_queue.py show TASK-047           # Show details
    python3 scripts/review_queue.py accept TASK-047         # Accept
    python3 scripts/review_queue.py reject TASK-047 --reason "Missing edge case"
    python3 scripts/review_queue.py revise TASK-047 --instruction "Add jitter"
    python3 scripts/review_queue.py gate                    # Exit 0=clear, 1=blocked
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
REVIEWS_DIR = PROJECT_ROOT / ".memory" / "reviews"
PENDING_DIR = REVIEWS_DIR / "pending"
ACCEPTED_DIR = REVIEWS_DIR / "accepted"
REJECTED_DIR = REVIEWS_DIR / "rejected"
TASKS_DIR = PROJECT_ROOT / ".rsi" / "tasks"
DELEGATIONS_LOG = PROJECT_ROOT / ".memory" / "metrics" / "delegations.jsonl"


def _ensure_dirs():
    for d in [PENDING_DIR, ACCEPTED_DIR, REJECTED_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _pending_reviews() -> list[Path]:
    _ensure_dirs()
    return sorted(PENDING_DIR.glob("*.md"))


def _update_delegation_log(task_id: str, verdict: str):
    """Update the delegation log with final verdict."""
    if not DELEGATIONS_LOG.exists():
        return
    events = []
    with open(DELEGATIONS_LOG) as f:
        for line in f:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Update the most recent event for this task
    for event in reversed(events):
        if event.get("task_id") == task_id and event.get("verdict") == "PENDING":
            event["verdict"] = verdict
            event["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            break

    with open(DELEGATIONS_LOG, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args):
    pending = _pending_reviews()
    if not pending:
        print("No pending reviews. Queue is clear.")
        return

    print(f"\n{'=' * 50}")
    print(f"PENDING REVIEWS — {len(pending)} item(s)")
    print(f"{'=' * 50}\n")
    for review_file in pending:
        task_id = review_file.stem
        # Extract first line after # Review:
        content = review_file.read_text()
        desc = ""
        for line in content.split("\n"):
            if line.startswith("**Task:**"):
                desc = line.replace("**Task:**", "").strip()
                break
        print(f"  {task_id}  {desc[:50]}")
    print(f"\nReview with: python3 scripts/review_queue.py show <task_id>")


def cmd_show(args):
    review_file = PENDING_DIR / f"{args.task_id}.md"
    if not review_file.exists():
        # Check accepted/rejected
        for d in [ACCEPTED_DIR, REJECTED_DIR]:
            alt = d / f"{args.task_id}.md"
            if alt.exists():
                print(alt.read_text())
                return
        print(f"Review not found: {args.task_id}", file=sys.stderr)
        sys.exit(1)

    print(review_file.read_text())


def cmd_accept(args):
    _ensure_dirs()
    review_file = PENDING_DIR / f"{args.task_id}.md"
    if not review_file.exists():
        print(f"No pending review for {args.task_id}", file=sys.stderr)
        sys.exit(1)

    # Move to accepted
    dest = ACCEPTED_DIR / f"{args.task_id}.md"
    content = review_file.read_text()
    content = content.replace("**Status:** PENDING REVIEW", "**Status:** ACCEPTED")
    dest.write_text(content)
    review_file.unlink()

    _update_delegation_log(args.task_id, "ACCEPTED")

    # Record metric
    try:
        from scripts.metrics import record
        record("delegation_reviewed", task=args.task_id, verdict="accepted")
    except ImportError:
        pass

    print(f"ACCEPTED: {args.task_id}")
    try:
        print(f"Moved to: {dest.relative_to(PROJECT_ROOT)}")
    except ValueError:
        print(f"Moved to: {dest}")

    # Apply changes from stored result (never re-calls MiniMax API)
    if args.apply:
        task_file = TASKS_DIR / f"{args.task_id}.json"
        result_file = REVIEWS_DIR / "results" / f"{args.task_id}.json"

        if result_file.exists() and task_file.exists():
            print("Applying from stored result (no API call)...")
            task = json.loads(task_file.read_text())
            result = json.loads(result_file.read_text())

            # Import and call apply_changes directly
            sys.path.insert(0, str(PROJECT_ROOT))
            from scripts.delegate import apply_changes
            applied = apply_changes(task, result)
            if applied:
                print(f"Applied: {', '.join(applied)}")
            else:
                print("No changes applied (verify failed or empty result)")
        elif task_file.exists():
            print(f"WARNING: No stored result for {args.task_id}.")
            print(f"Result file missing: {result_file}")
            print(f"Re-run delegation: python3 scripts/rsi.py delegate {task_file}")
        else:
            print(f"Task file not found: {task_file}")


def cmd_reject(args):
    _ensure_dirs()
    review_file = PENDING_DIR / f"{args.task_id}.md"
    if not review_file.exists():
        print(f"No pending review for {args.task_id}", file=sys.stderr)
        sys.exit(1)

    dest = REJECTED_DIR / f"{args.task_id}.md"
    content = review_file.read_text()
    content = content.replace("**Status:** PENDING REVIEW", f"**Status:** REJECTED")
    reason = args.reason or "(no reason given)"
    content += f"\n## Rejection Reason\n{reason}\n"
    dest.write_text(content)
    review_file.unlink()

    _update_delegation_log(args.task_id, "REJECTED")

    try:
        from scripts.metrics import record
        record("delegation_reviewed", task=args.task_id, verdict="rejected", reason=reason)
    except ImportError:
        pass

    print(f"REJECTED: {args.task_id}")
    print(f"Reason: {reason}")


def cmd_revise(args):
    review_file = PENDING_DIR / f"{args.task_id}.md"
    if not review_file.exists():
        print(f"No pending review for {args.task_id}", file=sys.stderr)
        sys.exit(1)

    instruction = args.instruction or "(no instruction given)"

    # Update review file with revision note
    content = review_file.read_text()
    content += f"\n## Revision Requested\n**Instruction:** {instruction}\n**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
    review_file.write_text(content)

    # Re-delegate with revision instruction
    task_file = TASKS_DIR / f"{args.task_id}.json"
    if task_file.exists():
        print(f"Sending revision to worker: {instruction}")
        import subprocess
        subprocess.run(
            [sys.executable, "scripts/delegate.py", str(task_file), "--revise", instruction],
            cwd=PROJECT_ROOT,
        )
    else:
        print(f"Task file not found: {task_file}. Manual revision needed.", file=sys.stderr)


def cmd_gate(args):
    """Check if review queue blocks new work. Exit 0=clear, 1=blocked."""
    pending = _pending_reviews()
    if pending:
        count = len(pending)
        print(f"JIDOKA: {count} pending review(s) from worker model.")
        print("Review queue must be cleared before starting new work.")
        print("Run: python3 scripts/review_queue.py list")
        sys.exit(1)
    else:
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="RSI Review Queue — Jidoka for worker output")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List pending reviews")
    sub.add_parser("gate", help="Check if queue blocks work (exit code)")

    show_p = sub.add_parser("show", help="Show review details")
    show_p.add_argument("task_id")

    accept_p = sub.add_parser("accept", help="Accept worker output")
    accept_p.add_argument("task_id")
    accept_p.add_argument("--apply", action="store_true", help="Also apply changes to disk")

    reject_p = sub.add_parser("reject", help="Reject worker output")
    reject_p.add_argument("task_id")
    reject_p.add_argument("--reason", help="Rejection reason")

    revise_p = sub.add_parser("revise", help="Request revision from worker")
    revise_p.add_argument("task_id")
    revise_p.add_argument("--instruction", help="Revision instruction")

    args = parser.parse_args()
    cmd = {
        "list": cmd_list,
        "show": cmd_show,
        "accept": cmd_accept,
        "reject": cmd_reject,
        "revise": cmd_revise,
        "gate": cmd_gate,
    }[args.command]
    cmd(args)


if __name__ == "__main__":
    main()
