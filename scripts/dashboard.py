#!/usr/bin/env python3
"""
Andon Dashboard — visual management for the RSI framework.

Toyota Principle 7: Use visual control so no problems are hidden.

This is the andon board. One command, one screen, complete picture.
Shows health, trends, and actionable signals.

Usage:
    python3 scripts/dashboard.py             # Full dashboard
    python3 scripts/dashboard.py --days 30   # Last 30 days
    python3 scripts/dashboard.py --json      # Machine-readable
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
MEMORY_ROOT = PROJECT_ROOT / ".memory"


def _load_metrics_summary(days: int) -> dict:
    try:
        from scripts.metrics import summary

        return summary(days)
    except (ImportError, Exception):
        return {}


def _load_calibration_score() -> dict:
    try:
        from scripts.calibration import calibration_score

        return calibration_score()
    except (ImportError, Exception):
        return {}


def _count_open_defects() -> dict:
    """Count open items from backlog by priority."""
    backlog_file = MEMORY_ROOT / "backlog.md"
    if not backlog_file.exists():
        return {}
    content = backlog_file.read_text(encoding="utf-8")
    import re

    counts: dict[str, int] = {}
    # Find tasks that are not done
    for match in re.finditer(
        r"\*\*status:\*\*\s*(todo|in-progress|blocked)", content, re.IGNORECASE
    ):
        # Look backwards for priority
        start = max(0, match.start() - 200)
        context = content[start : match.end()]
        p_match = re.search(
            r"\*\*priority:\*\*\s*(CRITICAL|HIGH|MEDIUM|LOW)", context, re.IGNORECASE
        )
        if p_match:
            prio = p_match.group(1).upper()
            counts[prio] = counts.get(prio, 0) + 1
    return counts


def _count_rounds() -> int:
    rounds_dir = MEMORY_ROOT / "rounds"
    if not rounds_dir.exists():
        return 0
    return len(list(rounds_dir.glob("round-*.md")))


def _count_patterns() -> int:
    patterns_file = MEMORY_ROOT / "technical" / "patterns.md"
    if not patterns_file.exists():
        return 0
    return patterns_file.read_text(encoding="utf-8").count("## ")


def _count_fail_entries() -> int:
    fail_file = MEMORY_ROOT / "technical" / "FAIL-index.md"
    if not fail_file.exists():
        return 0
    return fail_file.read_text(encoding="utf-8").count("FAIL-")


def _count_root_causes() -> dict:
    rca_file = MEMORY_ROOT / "technical" / "root-causes.md"
    if not rca_file.exists():
        return {"total": 0, "open": 0, "closed": 0}
    content = rca_file.read_text(encoding="utf-8")
    total = content.count("## RCA-")
    open_count = content.lower().count("**status:** open")
    return {"total": total, "open": open_count, "closed": total - open_count}


def render_dashboard(days: int = 7) -> str:
    """Render the full andon dashboard as a string."""
    from scripts.colors import bar, bold, dim, green, red, yellow

    metrics = _load_metrics_summary(days)
    calibration = _load_calibration_score()
    defects = _count_open_defects()
    rounds = _count_rounds()
    patterns = _count_patterns()
    fail_entries = _count_fail_entries()
    root_causes = _count_root_causes()

    lines = []
    w = 62

    lines.append("")
    lines.append(bold("=" * w))
    lines.append(bold(f"  RSI ANDON BOARD — last {days} days"))
    lines.append(bold(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}"))
    lines.append(bold("=" * w))

    # --- Health Summary ---
    lines.append("")
    lines.append(bold("  HEALTH SUMMARY"))
    lines.append("  " + "-" * (w - 4))

    tasks = metrics.get("tasks_completed", 0)
    avg_ct = metrics.get("avg_cycle_time_hours", 0)
    fpy = metrics.get("first_pass_yield", {})
    dr = metrics.get("defect_rate", {})
    signal = metrics.get("signal_ratio", {})

    lines.append(f"  Rounds completed:      {rounds}")
    lines.append(f"  Tasks completed:       {tasks}")

    if avg_ct:
        lines.append(f"  Avg cycle time:        {avg_ct}h")

    fpy_pct = fpy.get("yield_pct", 0)
    fpy_color = green if fpy_pct >= 80 else yellow if fpy_pct >= 60 else red
    if fpy.get("total"):
        lines.append(
            f"  First-pass yield:      {fpy_color(f'{fpy_pct}%')} ({fpy['passed']}/{fpy['total']})"
        )

    dr_val = dr.get("rate", 0)
    dr_color = green if dr_val < 0.3 else yellow if dr_val < 0.7 else red
    if dr.get("tasks_completed"):
        lines.append(f"  Defect rate:           {dr_color(str(dr_val))} per task")

    sig_pct = signal.get("ratio_pct", 0)
    sig_color = green if sig_pct >= 50 else yellow if sig_pct >= 25 else red
    if signal.get("total"):
        lines.append(
            f"  Signal ratio:          {sig_color(f'{sig_pct}%')} ({signal['actioned']}/{signal['total']} findings actioned)"
        )

    # --- Open Defects ---
    lines.append("")
    lines.append(bold("  OPEN ISSUES"))
    lines.append("  " + "-" * (w - 4))

    total_defects = sum(defects.values())
    if total_defects == 0:
        lines.append(f"  {green('No open issues')}")
    else:
        for prio in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            count = defects.get(prio, 0)
            if count:
                prio_color = {"CRITICAL": red, "HIGH": red, "MEDIUM": yellow, "LOW": dim}.get(
                    prio, str
                )
                lines.append(f"  {prio_color(f'{prio:<12}')} {bar(count, 10)} {count}")

    # --- Calibration ---
    if calibration:
        lines.append("")
        lines.append(bold("  PROOF-WRONG CALIBRATION"))
        lines.append("  " + "-" * (w - 4))

        total_h = calibration.get("total", 0)
        lines.append(f"  Total hypotheses:      {total_h}")
        lines.append(f"  Open:                  {calibration.get('open', 0)}")

        resolved = calibration.get("resolved", 0)
        if resolved:
            acc = calibration.get("accuracy_pct", 0)
            # For calibration: lower is better (means your code is usually right)
            acc_color = green if acc < 30 else yellow if acc < 60 else red
            lines.append(
                f"  Confirmed/Disproven:   {calibration.get('confirmed', 0)}/{calibration.get('disproven', 0)}"
            )
            lines.append(f"  Prediction accuracy:   {acc_color(f'{acc}%')}")

        avg_q = calibration.get("avg_quality_score", 0)
        q_color = green if avg_q >= 70 else yellow if avg_q >= 40 else red
        lines.append(f"  Avg hypothesis quality: {q_color(f'{avg_q}/100')}")

    # --- Root Causes ---
    if root_causes.get("total"):
        lines.append("")
        lines.append(bold("  ROOT CAUSE ANALYSES"))
        lines.append("  " + "-" * (w - 4))
        lines.append(f"  Total:   {root_causes['total']}")
        lines.append(
            f"  Open:    {red(str(root_causes['open'])) if root_causes['open'] else green('0')}"
        )
        lines.append(f"  Closed:  {root_causes['closed']}")

    # --- Knowledge Base ---
    lines.append("")
    lines.append(bold("  KNOWLEDGE BASE"))
    lines.append("  " + "-" * (w - 4))
    lines.append(f"  Patterns documented:   {patterns}")
    lines.append(f"  FAIL-index entries:    {fail_entries}")
    lines.append(f"  Root cause analyses:   {root_causes.get('total', 0)}")

    # --- Ceremony Stats ---
    ceremony = metrics.get("ceremony", {})
    if ceremony.get("count"):
        lines.append("")
        lines.append(bold("  CEREMONY COST"))
        lines.append("  " + "-" * (w - 4))
        lines.append(
            f"  Total time:   {ceremony['total_minutes']}min across {ceremony['count']} sessions"
        )
        lines.append(f"  Average:      {ceremony['avg_minutes']}min per session")
        for level, stats in ceremony.get("by_level", {}).items():
            lines.append(f"    {level:<12} {stats['count']}x, avg {stats['avg_min']}min")

    # --- Waste Indicators ---
    lines.append("")
    lines.append(bold("  WASTE INDICATORS (MUDA)"))
    lines.append("  " + "-" * (w - 4))

    waste_found = False
    if signal.get("total") and sig_pct < 25:
        lines.append(
            f"  {red('!')} Low signal ratio ({sig_pct}%) — most findings don't lead to action"
        )
        lines.append("    Consider: Are Module B prompts generating useful feedback?")
        waste_found = True

    if calibration.get("open", 0) > 5:
        lines.append(
            f"  {yellow('!')} {calibration['open']} unresolved hypotheses — test or close them"
        )
        waste_found = True

    if ceremony.get("avg_minutes", 0) > 30:
        lines.append(
            f"  {yellow('!')} High ceremony cost ({ceremony['avg_minutes']}min avg) — consider if proportional"
        )
        waste_found = True

    if not waste_found:
        lines.append(f"  {green('No waste indicators detected')}")

    lines.append("")
    lines.append(bold("=" * w))
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="RSI Andon Dashboard — visual management")
    parser.add_argument("--days", type=int, default=7, help="Period in days (default: 7)")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    args = parser.parse_args()

    if args.json:
        data = {
            "metrics": _load_metrics_summary(args.days),
            "calibration": _load_calibration_score(),
            "open_defects": _count_open_defects(),
            "rounds": _count_rounds(),
            "patterns": _count_patterns(),
            "fail_entries": _count_fail_entries(),
            "root_causes": _count_root_causes(),
        }
        print(json.dumps(data, indent=2))
    else:
        print(render_dashboard(args.days))


if __name__ == "__main__":
    main()
