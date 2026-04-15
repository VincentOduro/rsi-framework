#!/usr/bin/env python3
"""
Metrics engine — value stream measurement for the RSI framework.

Toyota Principle 7: Visual control — no hidden problems.
Toyota Principle 2: Continuous process flow — measure the flow.

Tracks:
  - Cycle time: duration from task start to task complete
  - First-pass yield: % of verifications that pass on first attempt
  - Defect rate: bugs found per completed task
  - Ceremony cost: time spent in framework process
  - Framework signal: % of findings that led to action

Storage: .memory/metrics/events.jsonl (append-only, one JSON object per line)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
METRICS_DIR = PROJECT_ROOT / ".memory" / "metrics"
EVENTS_FILE = METRICS_DIR / "events.jsonl"


# ---------------------------------------------------------------------------
# Event recording
# ---------------------------------------------------------------------------

def _ensure_dir() -> None:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(event_type: str, **kwargs) -> dict:
    """Append a metric event. Returns the event dict."""
    _ensure_dir()
    event = {"ts": _now(), "type": event_type, **kwargs}
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")
    return event


def record_task_start(task: str, round_id: str = "") -> dict:
    return record("task_start", task=task, round=round_id)


def record_task_complete(task: str, round_id: str = "", first_pass: bool = True) -> dict:
    return record("task_complete", task=task, round=round_id, first_pass=first_pass)


def record_verify_result(passed: bool, attempt: int = 1, files: list[str] | None = None) -> dict:
    return record("verify_result", passed=passed, attempt=attempt, files=files or [])


def record_ceremony(level: str, duration_minutes: float, task: str = "") -> dict:
    return record("ceremony_complete", level=level, duration_min=duration_minutes, task=task)


def record_defect(task: str, severity: str, found_by: str = "review", description: str = "") -> dict:
    return record("defect_found", task=task, severity=severity, found_by=found_by, description=description)


def record_finding_outcome(finding_id: str, led_to_action: bool, action: str = "") -> dict:
    return record("finding_outcome", finding_id=finding_id, led_to_action=led_to_action, action=action)


# ---------------------------------------------------------------------------
# Event querying
# ---------------------------------------------------------------------------

def load_events(event_type: str | None = None, days: int | None = None) -> list[dict]:
    """Load events, optionally filtered by type and recency."""
    if not EVENTS_FILE.exists():
        return []
    events = []
    cutoff = None
    if days is not None:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with open(EVENTS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type and event.get("type") != event_type:
                continue
            if cutoff:
                try:
                    ts = datetime.fromisoformat(event["ts"])
                    if ts < cutoff:
                        continue
                except (KeyError, ValueError):
                    continue
            events.append(event)
    return events


# ---------------------------------------------------------------------------
# Computed metrics
# ---------------------------------------------------------------------------

def cycle_times(days: int = 30) -> list[dict]:
    """Compute cycle time for each completed task in the period.
    Returns list of {task, started, completed, hours}."""
    starts = {}
    for e in load_events("task_start", days=days):
        task = e.get("task", "")
        if task:
            starts[task] = e["ts"]

    results = []
    for e in load_events("task_complete", days=days):
        task = e.get("task", "")
        if task and task in starts:
            try:
                t0 = datetime.fromisoformat(starts[task])
                t1 = datetime.fromisoformat(e["ts"])
                hours = (t1 - t0).total_seconds() / 3600
                results.append({"task": task, "started": starts[task], "completed": e["ts"], "hours": round(hours, 2)})
            except (ValueError, TypeError):
                pass
    return results


def first_pass_yield(days: int = 30) -> dict:
    """Fraction of verify results that passed on first attempt.
    Returns {passed, total, yield_pct}."""
    events = load_events("verify_result", days=days)
    first_attempts = [e for e in events if e.get("attempt", 1) == 1]
    total = len(first_attempts)
    passed = sum(1 for e in first_attempts if e.get("passed"))
    return {"passed": passed, "total": total, "yield_pct": round(passed / total * 100, 1) if total else 0.0}


def defect_rate(days: int = 30) -> dict:
    """Defects per completed task.
    Returns {defects, tasks_completed, rate}."""
    defects = len(load_events("defect_found", days=days))
    tasks = len(load_events("task_complete", days=days))
    return {"defects": defects, "tasks_completed": tasks, "rate": round(defects / tasks, 2) if tasks else 0.0}


def ceremony_stats(days: int = 30) -> dict:
    """Ceremony time statistics.
    Returns {total_minutes, count, avg_minutes, by_level}."""
    events = load_events("ceremony_complete", days=days)
    total = sum(e.get("duration_min", 0) for e in events)
    by_level: dict[str, list[float]] = {}
    for e in events:
        level = e.get("level", "unknown")
        by_level.setdefault(level, []).append(e.get("duration_min", 0))
    level_stats = {}
    for level, durations in by_level.items():
        level_stats[level] = {"count": len(durations), "avg_min": round(sum(durations) / len(durations), 1)}
    return {
        "total_minutes": round(total, 1),
        "count": len(events),
        "avg_minutes": round(total / len(events), 1) if events else 0,
        "by_level": level_stats,
    }


def signal_ratio(days: int = 30) -> dict:
    """Fraction of findings that led to action (signal vs noise).
    Returns {actioned, total, ratio_pct}."""
    events = load_events("finding_outcome", days=days)
    total = len(events)
    actioned = sum(1 for e in events if e.get("led_to_action"))
    return {"actioned": actioned, "total": total, "ratio_pct": round(actioned / total * 100, 1) if total else 0.0}


def summary(days: int = 7) -> dict:
    """Full metrics summary for the dashboard."""
    ct = cycle_times(days)
    avg_ct = round(sum(c["hours"] for c in ct) / len(ct), 2) if ct else 0
    return {
        "period_days": days,
        "tasks_completed": len(load_events("task_complete", days=days)),
        "avg_cycle_time_hours": avg_ct,
        "first_pass_yield": first_pass_yield(days),
        "defect_rate": defect_rate(days),
        "ceremony": ceremony_stats(days),
        "signal_ratio": signal_ratio(days),
        "defects_by_severity": _defects_by_severity(days),
    }


def _defects_by_severity(days: int = 30) -> dict:
    events = load_events("defect_found", days=days)
    counts: dict[str, int] = {}
    for e in events:
        sev = e.get("severity", "UNKNOWN")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="RSI Metrics Engine")
    sub = parser.add_subparsers(dest="cmd")

    rec = sub.add_parser("record", help="Record a metric event")
    rec.add_argument("event_type", help="Event type (task_start, task_complete, verify_result, defect_found, ceremony_complete, finding_outcome)")
    rec.add_argument("--task", default="")
    rec.add_argument("--round", default="")
    rec.add_argument("--passed", action="store_true")
    rec.add_argument("--attempt", type=int, default=1)
    rec.add_argument("--first-pass", action="store_true")
    rec.add_argument("--severity", default="MEDIUM")
    rec.add_argument("--level", default="standard")
    rec.add_argument("--duration", type=float, default=0)
    rec.add_argument("--description", default="")
    rec.add_argument("--finding-id", default="")
    rec.add_argument("--led-to-action", action="store_true")

    sub.add_parser("summary", help="Show metrics summary")
    sub.add_parser("cycle-times", help="Show cycle times")
    sub.add_parser("yield", help="Show first-pass yield")
    sub.add_parser("defects", help="Show defect rate")
    sub.add_parser("ceremony", help="Show ceremony stats")
    sub.add_parser("signal", help="Show signal ratio")

    args = parser.parse_args()

    if args.cmd == "record":
        t = args.event_type
        if t == "task_start":
            e = record_task_start(args.task, args.round)
        elif t == "task_complete":
            e = record_task_complete(args.task, args.round, args.first_pass)
        elif t == "verify_result":
            e = record_verify_result(args.passed, args.attempt)
        elif t == "defect_found":
            e = record_defect(args.task, args.severity, description=args.description)
        elif t == "ceremony_complete":
            e = record_ceremony(args.level, args.duration, args.task)
        elif t == "finding_outcome":
            e = record_finding_outcome(args.finding_id, args.led_to_action)
        else:
            e = record(t, task=args.task)
        print(json.dumps(e, indent=2))
    elif args.cmd == "summary":
        print(json.dumps(summary(), indent=2))
    elif args.cmd == "cycle-times":
        for ct in cycle_times():
            print(f"  {ct['task']:<30} {ct['hours']}h")
    elif args.cmd == "yield":
        y = first_pass_yield()
        print(f"  First-pass yield: {y['yield_pct']}% ({y['passed']}/{y['total']})")
    elif args.cmd == "defects":
        d = defect_rate()
        print(f"  Defect rate: {d['rate']} per task ({d['defects']} defects / {d['tasks_completed']} tasks)")
    elif args.cmd == "ceremony":
        c = ceremony_stats()
        print(f"  Total: {c['total_minutes']}min across {c['count']} ceremonies (avg {c['avg_minutes']}min)")
        for level, stats in c.get("by_level", {}).items():
            print(f"    {level}: {stats['count']}x, avg {stats['avg_min']}min")
    elif args.cmd == "signal":
        s = signal_ratio()
        print(f"  Signal ratio: {s['ratio_pct']}% ({s['actioned']}/{s['total']} findings led to action)")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
