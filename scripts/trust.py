#!/usr/bin/env python3
"""
trust.py -- Worker trust scoring system.

Inspired by Orchestrator-Agent Trust (Applied-AI-Research-Lab).
Tracks MiniMax accept rate by task type. High-trust task types get
lighter review. Low-trust get extra scrutiny.

Trust score = accepted / (accepted + rejected) per task type.
Auto-accept threshold configurable in .rsi/architecture.yaml.

Usage:
    python3 scripts/trust.py score                # Overall trust score
    python3 scripts/trust.py score --type test     # Trust for "test" tasks
    python3 scripts/trust.py should-auto-accept test  # Check if auto-accept
    python3 scripts/trust.py history               # Delegation history by type
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DELEGATIONS_LOG = PROJECT_ROOT / ".memory" / "metrics" / "delegations.jsonl"
ARCHITECTURE_FILE = PROJECT_ROOT / ".rsi" / "architecture.yaml"

# Defaults — overridden by architecture.yaml
DEFAULT_AUTO_ACCEPT_THRESHOLD = 0.85
DEFAULT_MIN_SAMPLES = 5
DEFAULT_SPOT_CHECK_RATE = 0.2


def _load_events() -> list[dict[str, Any]]:
    if not DELEGATIONS_LOG.exists():
        return []
    events: list[dict[str, Any]] = []
    with open(DELEGATIONS_LOG) as f:
        for line in f:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def _load_trust_config() -> dict[str, Any]:
    """Load trust thresholds from architecture.yaml."""
    if not ARCHITECTURE_FILE.exists():
        return {
            "auto_accept_threshold": DEFAULT_AUTO_ACCEPT_THRESHOLD,
            "min_samples": DEFAULT_MIN_SAMPLES,
            "spot_check_rate": DEFAULT_SPOT_CHECK_RATE,
        }

    content = ARCHITECTURE_FILE.read_text(encoding="utf-8")
    config: dict[str, Any] = {}
    in_trust = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped == "worker_trust:":
            in_trust = True
            continue
        if in_trust and ":" in stripped and not stripped.startswith("#"):
            if line.startswith("  ") and not line.startswith("    "):
                key, _, val = stripped.partition(":")
                val = val.strip()
                if val:
                    try:
                        config[key.strip()] = float(val)
                    except ValueError:
                        config[key.strip()] = val
            elif not line.startswith(" "):
                in_trust = False

    return {
        "auto_accept_threshold": config.get("auto_accept_threshold", DEFAULT_AUTO_ACCEPT_THRESHOLD),
        "min_samples": int(config.get("min_samples", DEFAULT_MIN_SAMPLES)),
        "spot_check_rate": config.get("spot_check_rate", DEFAULT_SPOT_CHECK_RATE),
    }


def _infer_task_type(event: dict[str, Any]) -> str:
    """Infer task type from delegation event. Uses task_id prefix or file patterns."""
    task_id = event.get("task_id", "")

    # Check common prefixes
    prefixes = {
        "TEST": "test",
        "AUDIT": "audit",
        "FIX": "fix",
        "IMPL": "implement",
        "REFACTOR": "refactor",
        "DOC": "docs",
    }
    for prefix, task_type in prefixes.items():
        if task_id.upper().startswith(prefix):
            return task_type

    # Check task file for type field
    task_file = PROJECT_ROOT / ".rsi" / "tasks" / f"{task_id}.json"
    if task_file.exists():
        try:
            spec = json.loads(task_file.read_text(encoding="utf-8"))
            return str(spec.get("type", "unknown"))
        except (OSError, json.JSONDecodeError):
            pass

    return "unknown"


# ---------------------------------------------------------------------------
# Trust computation
# ---------------------------------------------------------------------------


def compute_trust(task_type: str | None = None) -> dict[str, Any]:
    """Compute worker trust score from delegation history.

    Inspired by Orchestrator-Agent Trust confidence calibration metrics.

    Returns:
        {
            "overall": {"accepted": N, "rejected": N, "score": 0.XX},
            "by_type": {
                "test": {"accepted": N, "rejected": N, "score": 0.XX},
                ...
            }
        }
    """
    events = _load_events()

    by_type: dict[str, dict[str, int]] = {}
    total_accepted = 0
    total_rejected = 0

    for event in events:
        verdict = event.get("verdict", "").upper()
        if verdict not in ("ACCEPTED", "REJECTED"):
            continue

        t = _infer_task_type(event)

        if t not in by_type:
            by_type[t] = {"accepted": 0, "rejected": 0}

        if verdict == "ACCEPTED":
            by_type[t]["accepted"] += 1
            total_accepted += 1
        else:
            by_type[t]["rejected"] += 1
            total_rejected += 1

    total = total_accepted + total_rejected
    overall_score = round(total_accepted / total, 3) if total else 0.0

    type_scores = {}
    for t, counts in by_type.items():
        t_total = counts["accepted"] + counts["rejected"]
        type_scores[t] = {
            **counts,
            "total": t_total,
            "score": round(counts["accepted"] / t_total, 3) if t_total else 0.0,
        }

    result = {
        "overall": {
            "accepted": total_accepted,
            "rejected": total_rejected,
            "total": total,
            "score": overall_score,
        },
        "by_type": type_scores,
    }

    if task_type:
        result["queried_type"] = task_type
        result["queried_score"] = type_scores.get(task_type, {"score": 0.0, "total": 0})

    return result


def should_auto_accept(task_type: str) -> tuple[bool, str]:
    """Check if a task type qualifies for auto-accept.

    Returns (should_auto_accept, reason).

    Auto-accept requires:
    1. Trust score >= threshold (default 0.85)
    2. At least min_samples completed (default 5)
    3. Random spot-check may override (default 20% rate)
    """
    config = _load_trust_config()
    trust = compute_trust(task_type)
    type_data = trust["by_type"].get(task_type, {})

    score = type_data.get("score", 0.0)
    total = type_data.get("total", 0)
    threshold = float(config["auto_accept_threshold"])
    min_samples = int(config["min_samples"])
    spot_rate = float(config["spot_check_rate"])

    if total < min_samples:
        return False, f"Insufficient samples ({total}/{min_samples})"

    if score < threshold:
        return False, f"Trust score {score:.1%} below threshold {threshold:.1%}"

    # Spot check — random review even for trusted task types
    import random

    if random.random() < spot_rate:
        return False, f"Spot check (random {spot_rate:.0%} review rate)"

    return True, f"Auto-accept: trust {score:.1%} >= {threshold:.1%} ({total} samples)"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="RSI Worker Trust Scoring")
    sub = parser.add_subparsers(dest="cmd")

    score_p = sub.add_parser("score", help="Show trust scores")
    score_p.add_argument("--type", help="Filter by task type")
    score_p.add_argument("--json", action="store_true", help="JSON output")

    auto_p = sub.add_parser("should-auto-accept", help="Check auto-accept eligibility")
    auto_p.add_argument("task_type", help="Task type to check")

    sub.add_parser("history", help="Delegation history by type")
    sub.add_parser("config", help="Show trust configuration")

    args = parser.parse_args()

    if args.cmd == "score":
        trust = compute_trust(args.type if hasattr(args, "type") else None)
        if hasattr(args, "json") and args.json:
            print(json.dumps(trust, indent=2))
        else:
            overall = trust["overall"]
            print("\nWorker Trust Score")
            print(f"{'=' * 40}")
            print(f"  Overall: {overall['score']:.1%} ({overall['accepted']}/{overall['total']})")
            print("\n  By Type:")
            for t, data in sorted(trust["by_type"].items()):
                print(f"    {t:<15} {data['score']:.1%} ({data['accepted']}/{data['total']})")

    elif args.cmd == "should-auto-accept":
        ok, reason = should_auto_accept(args.task_type)
        if ok:
            print(f"AUTO-ACCEPT: {reason}")
        else:
            print(f"REVIEW REQUIRED: {reason}")
        sys.exit(0 if ok else 1)

    elif args.cmd == "config":
        config = _load_trust_config()
        print("\nTrust Configuration")
        print(f"{'=' * 40}")
        for k, v in config.items():
            print(f"  {k}: {v}")

    elif args.cmd == "history":
        events = _load_events()
        resolved = [e for e in events if e.get("verdict") in ("ACCEPTED", "REJECTED")]
        if not resolved:
            print("No resolved delegations yet.")
            return
        print(f"\nDelegation History ({len(resolved)} resolved)")
        print(f"{'=' * 50}")
        for e in resolved[-20:]:
            ts = e.get("timestamp", "?")[:19]
            tid = e.get("task_id", "?")
            verdict = e.get("verdict", "?")
            t = _infer_task_type(e)
            print(f"  {ts}  {tid:<14}  {verdict:<10}  {t}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
