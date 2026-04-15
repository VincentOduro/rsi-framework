#!/usr/bin/env python3
"""
auto_delegate.py — Automatic task routing between overlord and worker.

Claude (overlord) decomposes a high-level task, classifies each subtask
as overlord-only or delegatable, routes delegatable work to MiniMax-M2.7,
reviews the output, and consolidates results.

This is the automated orchestrator loop. No manual task spec writing.
No manual review queue management. Claude describes, MiniMax implements,
Claude reviews — all in one command.

Usage:
    python3 scripts/auto_delegate.py "Audit the project for security issues"
    python3 scripts/auto_delegate.py "Add input validation to all API endpoints"
    python3 scripts/auto_delegate.py "Write tests for the auth module"
    python3 scripts/auto_delegate.py --dry-run "Refactor the database layer"

Environment:
    ANTHROPIC_API_KEY    Required. For Claude (overlord).
    MINIMAX_API_KEY      Required. For MiniMax-M2.7 (worker).
    RSI_WORKER_MODEL     Optional. Default: MiniMax-M2.7
    RSI_OVERLORD_MODEL   Optional. Default: claude-sonnet-4-20250514
    RSI_MAX_RETRIES      Optional. Default: 3
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

TASKS_DIR = PROJECT_ROOT / ".rsi" / "tasks"
DELEGATIONS_LOG = PROJECT_ROOT / ".memory" / "metrics" / "delegations.jsonl"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OVERLORD_MODEL = os.environ.get("RSI_OVERLORD_MODEL", "claude-sonnet-4-20250514")
MAX_RETRIES = int(os.environ.get("RSI_MAX_RETRIES", "3"))


def _get_anthropic_client():
    try:
        import anthropic
    except ImportError:
        print("ERROR: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    return anthropic.Anthropic(api_key=key)


# ---------------------------------------------------------------------------
# Project context gathering
# ---------------------------------------------------------------------------

def _gather_project_context() -> str:
    """Gather project structure and known failure modes for the overlord."""
    parts = []

    # File tree (first 2 levels, no .git)
    import subprocess
    tree = subprocess.run(
        ["git", "ls-files"], cwd=PROJECT_ROOT,
        capture_output=True, text=True,
    )
    if tree.returncode == 0:
        files = tree.stdout.strip().split("\n")
        parts.append(f"PROJECT FILES ({len(files)} tracked):")
        for f in files[:100]:
            parts.append(f"  {f}")
        if len(files) > 100:
            parts.append(f"  ... and {len(files) - 100} more")

    # FAIL-index
    fail_file = PROJECT_ROOT / ".memory" / "technical" / "FAIL-index.md"
    if fail_file.exists():
        content = fail_file.read_text()
        fail_lines = [l for l in content.split("\n") if l.strip().startswith("| FAIL-")]
        if fail_lines:
            parts.append("\nKNOWN FAILURE MODES:")
            for l in fail_lines:
                parts.append(f"  {l.strip()}")

    # File sensitivity rules
    arch_file = PROJECT_ROOT / ".rsi" / "architecture.yaml"
    if arch_file.exists():
        parts.append("\nFILE SENSITIVITY (from .rsi/architecture.yaml):")
        parts.append("  constitution: CLAUDE.md, FRAMEWORK.md, .rsi/**, scripts/hooks.py, scripts/delegate.py")
        parts.append("  guarded: scripts/*.py, adapters/**")
        parts.append("  open: tests/**, docs/**, *.md (non-constitution)")
        parts.append("  Worker CANNOT modify constitution files.")
        parts.append("  Worker CAN modify guarded (needs review) and open (freely).")

    return "\n".join(parts)


def _gather_file_contents(filepaths: list[str]) -> dict[str, str]:
    """Read file contents, recording reads for RSI compliance."""
    contents = {}
    for fp in filepaths:
        full = PROJECT_ROOT / fp
        if full.exists():
            try:
                contents[fp] = full.read_text()
            except Exception:
                pass
    return contents


# ---------------------------------------------------------------------------
# Overlord: decompose task into subtasks
# ---------------------------------------------------------------------------

DECOMPOSE_PROMPT = """You are the overlord in an RSI framework overlord-worker architecture.

TASK: {task_description}

PROJECT CONTEXT:
{project_context}

DECOMPOSE this task into ordered subtasks. For each subtask, decide:
- **overlord_only**: Architecture decisions, reviewing results, planning, modifying constitution files
- **delegatable**: Writing code, writing tests, writing docs, bulk generation, anything touching open/guarded files

Respond with JSON only:
```json
{{
    "plan": "Brief description of your overall approach",
    "subtasks": [
        {{
            "id": "ST-001",
            "routing": "delegatable|overlord_only",
            "type": "implement|fix|refactor|review|test|docs|audit",
            "description": "Specific action",
            "instruction": "Detailed instruction for the worker (if delegatable)",
            "files_to_read": ["path/to/file.py"],
            "files_to_modify": ["path/to/file.py"],
            "acceptance_criteria": ["Criterion 1"],
            "proof_wrong": "What could prove this subtask's output wrong"
        }}
    ]
}}
```

RULES:
- Each subtask must be specific and independently completable
- Worker cannot modify constitution files (CLAUDE.md, .rsi/**, scripts/hooks.py, scripts/delegate.py)
- Worker CAN modify tests/**, docs/**, and scripts/*.py (guarded — you'll review)
- Maximum 10 subtasks
- Be specific about files_to_read and files_to_modify
- acceptance_criteria must be verifiable, not vague
- If the entire task is overlord-only (e.g. "review the architecture"), return all subtasks as overlord_only
"""


def decompose_task(task_description: str, project_context: str) -> dict:
    """Call Claude to decompose a high-level task into routed subtasks."""
    client = _get_anthropic_client()

    response = client.messages.create(
        model=OVERLORD_MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": DECOMPOSE_PROMPT.format(
                task_description=task_description,
                project_context=project_context,
            ),
        }],
    )

    raw = response.content[0].text

    # Robust JSON extraction
    from scripts.delegate import _extract_json
    parsed = _extract_json(raw)
    if parsed is not None and "subtasks" in parsed:
        return parsed

    # Fallback: single overlord-only task
    if True:
        return {
            "plan": "Could not decompose — treating as single overlord task",
            "subtasks": [{
                "id": "ST-001",
                "routing": "overlord_only",
                "type": "review",
                "description": task_description,
                "instruction": task_description,
                "files_to_read": [],
                "files_to_modify": [],
                "acceptance_criteria": ["Task completed"],
                "proof_wrong": "Unable to decompose automatically",
            }],
        }


# ---------------------------------------------------------------------------
# Overlord: review worker output
# ---------------------------------------------------------------------------

REVIEW_PROMPT = """You are the overlord reviewing worker output.

ORIGINAL TASK: {description}

ACCEPTANCE CRITERIA:
{criteria}

WORKER OUTPUT:
{worker_output}

WORKER PROOF-WRONG:
{proof_wrong}

Review this output. Respond with JSON only:
```json
{{
    "decision": "accept|reject|revise",
    "feedback": "Specific feedback",
    "issues": ["Issue 1"],
    "proof_wrong_quality": 75
}}
```

RULES:
- "accept" only if ALL acceptance criteria are met
- "reject" if fundamentally wrong or missing key requirements
- "revise" if close but needs specific improvements (provide feedback)
- Score proof-wrong 0-100 (specific + testable = high, vague = low)
"""


def review_worker_output(subtask: dict, result: dict) -> dict:
    """Call Claude to review worker output against acceptance criteria."""
    client = _get_anthropic_client()

    criteria = "\n".join(f"- {c}" for c in subtask.get("acceptance_criteria", []))
    worker_output = json.dumps(result.get("changes", {}), indent=2)[:4000]

    response = client.messages.create(
        model=OVERLORD_MODEL,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": REVIEW_PROMPT.format(
                description=subtask["description"],
                criteria=criteria,
                worker_output=worker_output,
                proof_wrong=result.get("proof_wrong", "(none)"),
            ),
        }],
    )

    raw = response.content[0].text
    from scripts.delegate import _extract_json
    parsed = _extract_json(raw)
    if parsed is not None and "decision" in parsed:
        return parsed
    return {"decision": "accept", "feedback": raw[:500], "issues": [], "proof_wrong_quality": 50}


# ---------------------------------------------------------------------------
# Overlord: handle overlord-only subtasks
# ---------------------------------------------------------------------------

OVERLORD_EXECUTE_PROMPT = """You are the overlord executing a task that cannot be delegated.

TASK: {description}

INSTRUCTION: {instruction}

FILE CONTENTS:
{file_contents}

Execute this task. Respond with JSON:
```json
{{
    "analysis": "Your analysis or findings",
    "changes": {{"path/to/file.py": "full content"}},
    "recommendations": ["Recommendation 1"],
    "proof_wrong": "What could prove your analysis wrong"
}}
```

If this is a review/audit task with no file changes, set "changes" to {{}}.
"""


def execute_overlord_task(subtask: dict) -> dict:
    """Claude handles overlord-only subtasks directly."""
    client = _get_anthropic_client()

    file_contents = _gather_file_contents(subtask.get("files_to_read", []))
    fc_text = ""
    for path, content in file_contents.items():
        fc_text += f"\n--- {path} ---\n{content[:3000]}\n"

    response = client.messages.create(
        model=OVERLORD_MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": OVERLORD_EXECUTE_PROMPT.format(
                description=subtask["description"],
                instruction=subtask.get("instruction", subtask["description"]),
                file_contents=fc_text or "(no files requested)",
            ),
        }],
    )

    raw = response.content[0].text
    from scripts.delegate import _extract_json
    parsed = _extract_json(raw)
    if parsed is not None:
        return parsed
    return {"analysis": raw[:2000], "changes": {}, "recommendations": [], "proof_wrong": ""}


# ---------------------------------------------------------------------------
# Core loop: decompose -> route -> execute -> review -> consolidate
# ---------------------------------------------------------------------------

def run_auto_delegation(task_description: str, dry_run: bool = False, verbose: bool = True) -> dict:
    """Full automated orchestrator-worker loop.

    1. Claude decomposes the task
    2. For each subtask:
       - overlord_only -> Claude handles directly
       - delegatable -> MiniMax implements -> Claude reviews -> accept/reject/revise
    3. Apply accepted changes (unless dry_run)
    4. Record metrics
    5. Return consolidated results
    """
    from scripts.delegate import call_worker, validate_task, apply_changes, write_review, log_delegation
    from scripts.classify_file import classify_file

    start_time = time.time()

    def log(msg):
        if verbose:
            print(msg)

    log(f"\n{'=' * 60}")
    log(f"AUTO-DELEGATION: {task_description}")
    log(f"{'=' * 60}")

    # Step 1: Gather context
    log(f"\n[1] Gathering project context...")
    context = _gather_project_context()

    # Step 2: Decompose
    log(f"[2] Overlord decomposing task...")
    plan = decompose_task(task_description, context)
    subtasks = plan.get("subtasks", [])
    log(f"    Plan: {plan.get('plan', '(none)')}")
    log(f"    Subtasks: {len(subtasks)}")

    delegatable = [s for s in subtasks if s.get("routing") == "delegatable"]
    overlord_only = [s for s in subtasks if s.get("routing") != "delegatable"]
    log(f"    Delegatable: {len(delegatable)} | Overlord-only: {len(overlord_only)}")

    results = []
    all_changes = {}
    all_recommendations = []

    # Step 3: Execute overlord-only subtasks
    for i, subtask in enumerate(overlord_only, 1):
        log(f"\n[Overlord {i}/{len(overlord_only)}] {subtask['description'][:60]}")
        result = execute_overlord_task(subtask)
        results.append({
            "subtask": subtask,
            "routing": "overlord",
            "status": "completed",
            "result": result,
        })
        if result.get("changes"):
            all_changes.update(result["changes"])
        if result.get("recommendations"):
            all_recommendations.extend(result["recommendations"])
        log(f"    -> Completed")
        if result.get("analysis"):
            # Print first 200 chars of analysis
            log(f"    Analysis: {result['analysis'][:200]}...")

    # Step 4: Execute delegatable subtasks
    for i, subtask in enumerate(delegatable, 1):
        log(f"\n[Worker {i}/{len(delegatable)}] {subtask['description'][:60]}")

        # Validate files aren't constitution
        blocked = [f for f in subtask.get("files_to_modify", []) if classify_file(f) == "constitution"]
        if blocked:
            log(f"    BLOCKED: {blocked} are constitution-level. Skipping.")
            results.append({
                "subtask": subtask,
                "routing": "worker",
                "status": "blocked",
                "error": f"Constitution files: {blocked}",
            })
            continue

        # Build task spec for delegate.py
        task_id = f"AUTO-{datetime.now(timezone.utc).strftime('%H%M%S')}-{i:02d}"
        task_spec = {
            "id": task_id,
            "description": subtask["description"],
            "instruction": subtask.get("instruction", subtask["description"]),
            "files_to_read": subtask.get("files_to_read", []),
            "files_to_modify": subtask.get("files_to_modify", []),
            "acceptance_criteria": subtask.get("acceptance_criteria", ["Task completed"]),
            "proof_wrong": subtask.get("proof_wrong", "Unknown"),
            "constraints": [],
        }

        # Save task spec
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        task_file = TASKS_DIR / f"{task_id}.json"
        task_file.write_text(json.dumps(task_spec, indent=2))

        # Retry loop: worker implements -> overlord reviews
        accepted = False
        revision_feedback = ""
        for attempt in range(1, MAX_RETRIES + 1):
            log(f"    Attempt {attempt}/{MAX_RETRIES}")

            # Call worker
            log(f"    -> Sending to MiniMax...")
            worker_result = call_worker(task_spec, revision_feedback)

            if worker_result.get("error"):
                log(f"    -> Worker error: {worker_result['error']}")
                if attempt < MAX_RETRIES:
                    revision_feedback = f"Error: {worker_result['error']}. Try again."
                    continue
                results.append({
                    "subtask": subtask,
                    "routing": "worker",
                    "status": "failed",
                    "error": worker_result["error"],
                    "attempts": attempt,
                })
                break

            # Write review
            write_review(task_spec, worker_result)
            log_delegation(task_spec, worker_result, "PENDING")

            # Overlord reviews
            log(f"    -> Overlord reviewing...")
            review = review_worker_output(subtask, worker_result)
            decision = review.get("decision", "accept")
            log(f"    -> Decision: {decision.upper()} (proof-wrong quality: {review.get('proof_wrong_quality', '?')}/100)")

            if decision == "accept":
                accepted = True
                all_changes.update(worker_result.get("changes", {}))
                log_delegation(task_spec, worker_result, "ACCEPTED")
                results.append({
                    "subtask": subtask,
                    "routing": "worker",
                    "status": "accepted",
                    "attempts": attempt,
                    "changes": list(worker_result.get("changes", {}).keys()),
                    "proof_wrong": worker_result.get("proof_wrong", ""),
                    "review_feedback": review.get("feedback", ""),
                })
                break

            elif decision == "reject":
                log(f"    -> Rejected: {review.get('feedback', '')[:100]}")
                log_delegation(task_spec, worker_result, "REJECTED")
                if attempt < MAX_RETRIES:
                    revision_feedback = review.get("feedback", "Rejected. Try again.")
                    if review.get("issues"):
                        revision_feedback += "\nIssues:\n" + "\n".join(f"- {i}" for i in review["issues"])
                else:
                    results.append({
                        "subtask": subtask,
                        "routing": "worker",
                        "status": "rejected",
                        "attempts": attempt,
                        "feedback": review.get("feedback", ""),
                    })

            elif decision == "revise":
                log(f"    -> Revision: {review.get('feedback', '')[:100]}")
                if attempt < MAX_RETRIES:
                    revision_feedback = review.get("feedback", "Needs revision.")
                else:
                    # Out of retries — accept if quality was decent
                    pq = review.get("proof_wrong_quality", 0)
                    if pq >= 60:
                        all_changes.update(worker_result.get("changes", {}))
                        log(f"    -> Accepting after max revisions (quality {pq}/100)")
                        results.append({
                            "subtask": subtask,
                            "routing": "worker",
                            "status": "accepted",
                            "attempts": attempt,
                            "changes": list(worker_result.get("changes", {}).keys()),
                            "note": "Accepted after max revisions",
                        })
                    else:
                        results.append({
                            "subtask": subtask,
                            "routing": "worker",
                            "status": "failed",
                            "attempts": attempt,
                            "feedback": review.get("feedback", ""),
                        })

    # Step 5: Apply changes
    applied_files = []
    if all_changes and not dry_run:
        log(f"\n[Apply] Writing {len(all_changes)} file(s)...")
        for filepath, content in all_changes.items():
            full_path = PROJECT_ROOT / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            applied_files.append(filepath)
            log(f"    + {filepath}")
    elif all_changes and dry_run:
        log(f"\n[Dry-run] Would write {len(all_changes)} file(s):")
        for filepath in all_changes:
            log(f"    {filepath}")

    # Step 6: Summary
    elapsed = round(time.time() - start_time, 1)
    accepted_count = sum(1 for r in results if r.get("status") == "accepted" or r.get("status") == "completed")
    failed_count = sum(1 for r in results if r.get("status") in ("failed", "rejected", "blocked"))

    # Record overall metrics
    try:
        from scripts.metrics import record
        record("auto_delegation", task=task_description,
               subtasks=len(subtasks), delegated=len(delegatable),
               accepted=accepted_count, failed=failed_count,
               elapsed_seconds=elapsed)
    except (ImportError, Exception):
        pass

    summary = {
        "task": task_description,
        "plan": plan.get("plan", ""),
        "total_subtasks": len(subtasks),
        "overlord_only": len(overlord_only),
        "delegated": len(delegatable),
        "accepted": accepted_count,
        "failed": failed_count,
        "files_changed": applied_files,
        "recommendations": all_recommendations,
        "elapsed_seconds": elapsed,
        "dry_run": dry_run,
        "results": results,
    }

    log(f"\n{'=' * 60}")
    log(f"RESULT: {accepted_count}/{len(subtasks)} subtasks completed")
    log(f"Delegated: {len(delegatable)} to MiniMax | Overlord: {len(overlord_only)} handled directly")
    log(f"Files changed: {len(applied_files)} | Time: {elapsed}s")
    if failed_count:
        log(f"Failed: {failed_count}")
    if all_recommendations:
        log(f"\nRecommendations:")
        for rec in all_recommendations[:10]:
            log(f"  • {rec}")
    log(f"{'=' * 60}\n")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="RSI Auto-Delegation — automatic task routing between Claude and MiniMax"
    )
    parser.add_argument("task", nargs="*", help="Task description")
    parser.add_argument("--dry-run", action="store_true", help="Decompose and delegate but don't write files")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--json", action="store_true", help="JSON output only")

    args = parser.parse_args()

    task_description = " ".join(args.task) if args.task else ""
    if not task_description:
        print("Usage: python3 scripts/auto_delegate.py 'Your task description'")
        sys.exit(1)

    summary = run_auto_delegation(
        task_description,
        dry_run=args.dry_run,
        verbose=not args.quiet and not args.json,
    )

    if args.json:
        print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
