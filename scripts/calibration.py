#!/usr/bin/env python3
"""
Calibration tracker — measures proof-wrong prediction accuracy.

Toyota Principle 14: Become a learning organization through relentless
reflection and continuous improvement.

Every "what could prove this wrong?" answer is a hypothesis. This module
tracks whether those hypotheses are later confirmed, disproven, or never
tested — then computes calibration scores over time.

An AI that generates hypotheses but never checks them isn't learning.
An AI that checks them and adjusts is Kaizen.

Storage: .memory/calibration/hypotheses.jsonl
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CALIBRATION_DIR = PROJECT_ROOT / ".memory" / "calibration"
HYPOTHESES_FILE = CALIBRATION_DIR / "hypotheses.jsonl"


def _ensure_dir() -> None:
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_all() -> list[dict]:
    if not HYPOTHESES_FILE.exists():
        return []
    results = []
    with open(HYPOTHESES_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return results


def _save_all(hypotheses: list[dict]) -> None:
    _ensure_dir()
    with open(HYPOTHESES_FILE, "w") as f:
        for h in hypotheses:
            f.write(json.dumps(h) + "\n")


def _next_id(hypotheses: list[dict]) -> str:
    max_num = 0
    for h in hypotheses:
        m = re.search(r"HYP-(\d+)", h.get("id", ""))
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"HYP-{max_num + 1:03d}"


# ---------------------------------------------------------------------------
# Hypothesis quality validation
# ---------------------------------------------------------------------------

VAGUE_PATTERNS = [
    r"^it might break",
    r"^something could go wrong",
    r"^there might be issues",
    r"^it could fail",
    r"^not sure",
    r"^maybe",
    r"^possibly",
    r"^if something goes wrong",
    r"^edge cases",
]


def validate_hypothesis(text: str) -> dict:
    """Validate a proof-wrong hypothesis for quality.
    Returns {valid, issues, score}.
    Score: 0-100 where 100 = perfect hypothesis."""
    issues = []
    score = 100

    if not text or not text.strip():
        return {"valid": False, "issues": ["Empty hypothesis"], "score": 0}

    # Check for vague patterns
    lower = text.lower().strip()
    for pattern in VAGUE_PATTERNS:
        if re.match(pattern, lower):
            issues.append(f"Vague: matches pattern '{pattern}'")
            score -= 40
            break

    # Check minimum length (specific hypotheses need detail)
    if len(text) < 20:
        issues.append("Too short — specific hypotheses need detail")
        score -= 30

    # Check for specificity markers (good signs)
    specificity_markers = [
        "if ",
        "when ",
        "because ",
        "would ",
        "could cause ",
        "returns ",
        "throws ",
    ]
    has_conditional = any(marker in lower for marker in specificity_markers)
    if not has_conditional:
        issues.append("No conditional — good hypotheses use 'if X then Y' structure")
        score -= 20

    # Check for testability markers
    testability_markers = [
        "test",
        "verify",
        "check",
        "assert",
        "returns",
        "raises",
        "throws",
        "output",
        "result",
    ]
    has_testable = any(marker in lower for marker in testability_markers)
    if not has_testable:
        issues.append("May not be testable — consider how you'd verify this")
        score -= 10

    # Check for file/function references (very specific = good)
    has_reference = bool(re.search(r"[a-zA-Z_]+\.(py|js|ts|go|rs|java|rb)", text)) or bool(
        re.search(r"[a-zA-Z_]+\(\)", text)
    )
    if has_reference:
        score = min(100, score + 10)

    score = max(0, score)
    return {"valid": score >= 40, "issues": issues, "score": score}


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def add_hypothesis(
    hypothesis: str,
    task: str = "",
    severity_if_true: str = "MEDIUM",
    test_method: str = "",
    files: list[str] | None = None,
) -> dict:
    """Record a new proof-wrong hypothesis. Returns the hypothesis dict."""
    all_h = _load_all()
    hyp_id = _next_id(all_h)

    validation = validate_hypothesis(hypothesis)

    entry = {
        "id": hyp_id,
        "created": _now(),
        "task": task,
        "hypothesis": hypothesis,
        "severity_if_true": severity_if_true,
        "test_method": test_method,
        "files": files or [],
        "status": "open",
        "quality_score": validation["score"],
        "quality_issues": validation["issues"],
        "resolution_date": "",
        "resolution_notes": "",
    }
    all_h.append(entry)
    _save_all(all_h)
    return entry


def resolve(hyp_id: str, status: str, notes: str = "") -> dict | None:
    """Mark a hypothesis as confirmed, disproven, or untestable.
    status: confirmed | disproven | untestable"""
    if status not in ("confirmed", "disproven", "untestable"):
        raise ValueError(f"Invalid status: {status}. Use: confirmed, disproven, untestable")

    all_h = _load_all()
    for h in all_h:
        if h["id"] == hyp_id:
            h["status"] = status
            h["resolution_date"] = _now()
            h["resolution_notes"] = notes
            _save_all(all_h)
            return h
    return None


def list_open() -> list[dict]:
    return [h for h in _load_all() if h.get("status") == "open"]


def list_all() -> list[dict]:
    return _load_all()


# ---------------------------------------------------------------------------
# Calibration score
# ---------------------------------------------------------------------------


def calibration_score() -> dict:
    """Compute overall calibration metrics.
    Returns {total, open, confirmed, disproven, untestable, accuracy_pct,
             avg_quality_score, hypotheses_by_severity}."""
    all_h = _load_all()
    total = len(all_h)
    by_status = {"open": 0, "confirmed": 0, "disproven": 0, "untestable": 0}
    by_severity: dict[str, int] = {}
    quality_scores = []

    for h in all_h:
        s = h.get("status", "open")
        by_status[s] = by_status.get(s, 0) + 1
        sev = h.get("severity_if_true", "UNKNOWN")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        quality_scores.append(h.get("quality_score", 50))

    resolved = by_status["confirmed"] + by_status["disproven"]
    accuracy = round(by_status["confirmed"] / resolved * 100, 1) if resolved else 0
    avg_quality = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else 0

    return {
        "total": total,
        **by_status,
        "resolved": resolved,
        "accuracy_pct": accuracy,
        "avg_quality_score": avg_quality,
        "by_severity": by_severity,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    from scripts.colors import cyan, green, red, yellow

    parser = argparse.ArgumentParser(
        description="RSI Calibration Tracker — proof-wrong hypothesis accuracy"
    )
    sub = parser.add_subparsers(dest="cmd")

    add_p = sub.add_parser("add", help="Add a hypothesis")
    add_p.add_argument("hypothesis", help="The proof-wrong hypothesis text")
    add_p.add_argument("--task", default="")
    add_p.add_argument(
        "--severity", default="MEDIUM", choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    )
    add_p.add_argument("--test-method", default="")
    add_p.add_argument("--files", nargs="*")

    res_p = sub.add_parser("resolve", help="Resolve a hypothesis")
    res_p.add_argument("hyp_id", help="Hypothesis ID (e.g., HYP-001)")
    res_p.add_argument("status", choices=["confirmed", "disproven", "untestable"])
    res_p.add_argument("--notes", default="")

    sub.add_parser("open", help="List open hypotheses")
    sub.add_parser("all", help="List all hypotheses")
    sub.add_parser("score", help="Show calibration score")

    val_p = sub.add_parser("validate", help="Validate a hypothesis for quality")
    val_p.add_argument("hypothesis", help="Hypothesis text to validate")

    args = parser.parse_args()

    if args.cmd == "add":
        h = add_hypothesis(args.hypothesis, args.task, args.severity, args.test_method, args.files)
        quality = h["quality_score"]
        color = green if quality >= 70 else yellow if quality >= 40 else red
        print(f"{green('Added')} {h['id']}: {h['hypothesis'][:60]}")
        print(f"  Quality: {color(f'{quality}/100')}")
        if h["quality_issues"]:
            for issue in h["quality_issues"]:
                print(f"  {yellow('!')} {issue}")

    elif args.cmd == "resolve":
        h = resolve(args.hyp_id.upper(), args.status, args.notes)
        if h:
            status_color = {"confirmed": red, "disproven": green, "untestable": yellow}[args.status]
            print(f"{status_color(args.status.upper())} {h['id']}: {h['hypothesis'][:60]}")
        else:
            print(f"{red('ERROR:')} Hypothesis {args.hyp_id} not found")
            sys.exit(1)

    elif args.cmd == "open":
        hyps = list_open()
        if not hyps:
            print("No open hypotheses.")
            return
        print(f"\n{len(hyps)} open hypothesis(es):\n")
        for h in hyps:
            print(f"  {h['id']}  [{h.get('severity_if_true', '?')}]  {h['hypothesis'][:60]}")
            if h.get("task"):
                print(f"         Task: {h['task']}")

    elif args.cmd == "all":
        hyps = list_all()
        if not hyps:
            print("No hypotheses recorded.")
            return
        print(f"\n{len(hyps)} hypothesis(es):\n")
        for h in hyps:
            status = h.get("status", "open")
            color = {"open": cyan, "confirmed": red, "disproven": green, "untestable": yellow}.get(
                status, str
            )
            status_str = status.upper().ljust(12)
            print(f"  {h['id']}  {color(status_str)}  {h['hypothesis'][:50]}")

    elif args.cmd == "score":
        s = calibration_score()
        print(f"\n{'=' * 50}")
        print("CALIBRATION SCORE")
        print(f"{'=' * 50}\n")
        print(f"  Total hypotheses:  {s['total']}")
        print(f"  Open:              {s['open']}")
        print(f"  Confirmed:         {s['confirmed']}")
        print(f"  Disproven:         {s['disproven']}")
        print(f"  Untestable:        {s['untestable']}")
        print(f"  Resolved:          {s['resolved']}")
        if s["resolved"]:
            acc_color = red if s["accuracy_pct"] > 50 else green
            acc_str = str(s["accuracy_pct"]) + "%"
            print(f"\n  Prediction accuracy: {acc_color(acc_str)}")
            print("  (Lower is better — it means your code is usually right)")
        print(f"  Avg quality score:   {s['avg_quality_score']}/100")

    elif args.cmd == "validate":
        v = validate_hypothesis(args.hypothesis)
        color = green if v["score"] >= 70 else yellow if v["score"] >= 40 else red
        score_str = str(v["score"]) + "/100"
        print(f"Quality: {color(score_str)}")
        if v["issues"]:
            for issue in v["issues"]:
                print(f"  {yellow('!')} {issue}")
        else:
            print(f"  {green('No issues detected')}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
