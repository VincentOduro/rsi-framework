#!/usr/bin/env python3
"""
delegate.py — Cross-model delegation engine.

Sends tasks to the worker model (MiniMax-M2.7), captures results,
writes them to .memory/reviews/pending/ for overlord review.

The filesystem is the message bus. Models never talk directly.

Usage:
    python3 scripts/delegate.py .rsi/tasks/TASK-047.json              # Dry-run
    python3 scripts/delegate.py .rsi/tasks/TASK-047.json --apply      # Apply changes
    python3 scripts/delegate.py .rsi/tasks/TASK-047.json --revise "Add jitter"
    python3 scripts/delegate.py --history                              # Show history
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
TASKS_DIR = PROJECT_ROOT / ".rsi" / "tasks"
REVIEWS_DIR = PROJECT_ROOT / ".memory" / "reviews"
PENDING_DIR = REVIEWS_DIR / "pending"
DELEGATIONS_LOG = PROJECT_ROOT / ".memory" / "metrics" / "delegations.jsonl"

# Architecture config
ARCHITECTURE_FILE = PROJECT_ROOT / ".rsi" / "architecture.yaml"


def _ensure_dirs():
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    (REVIEWS_DIR / "accepted").mkdir(parents=True, exist_ok=True)
    (REVIEWS_DIR / "rejected").mkdir(parents=True, exist_ok=True)
    DELEGATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)


def _load_worker_config() -> dict:
    """Load worker API config from architecture.yaml."""
    if not ARCHITECTURE_FILE.exists():
        return {
            "provider": "minimax",
            "base_url": os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.chat/v1"),
            "model": os.environ.get("RSI_WORKER_MODEL", "MiniMax-M2.7"),
            "max_tokens": 8192,
            "timeout_seconds": 120,
            "env_key": "MINIMAX_API_KEY",
        }

    # Simple extraction from YAML
    content = ARCHITECTURE_FILE.read_text()
    config = {}
    in_worker_api = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped == "worker_api:":
            in_worker_api = True
            continue
        if in_worker_api and ":" in stripped and not stripped.startswith("#"):
            if not stripped.startswith("-") and line.startswith("  "):
                key, _, val = stripped.partition(":")
                val = val.strip().strip('"').strip("'")
                if val:
                    config[key.strip()] = val
            elif not line.startswith("  "):
                in_worker_api = False

    # Env vars override
    config["base_url"] = os.environ.get("MINIMAX_BASE_URL", config.get("base_url", "https://api.minimaxi.chat/v1"))
    config["model"] = os.environ.get("RSI_WORKER_MODEL", config.get("model", "MiniMax-M2.7"))
    config.setdefault("max_tokens", "8192")
    config.setdefault("timeout_seconds", "120")
    config.setdefault("env_key", "MINIMAX_API_KEY")
    return config


def _get_api_key(config: dict) -> str:
    env_key = config.get("env_key", "MINIMAX_API_KEY")
    key = os.environ.get(env_key, "")
    if not key:
        print(f"ERROR: {env_key} environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return key


# ---------------------------------------------------------------------------
# Task validation
# ---------------------------------------------------------------------------

def validate_task(task: dict) -> list[str]:
    """Validate task spec against architecture rules. Returns list of issues."""
    from scripts.classify_file import classify_file

    issues = []

    # Required fields
    for field in ["id", "description", "instruction", "files_to_modify"]:
        if not task.get(field):
            issues.append(f"Missing required field: {field}")

    # Acceptance criteria
    if not task.get("acceptance_criteria"):
        issues.append("acceptance_criteria must have at least one entry")

    # Proof-wrong
    if not task.get("proof_wrong"):
        issues.append("proof_wrong is required")

    # File sensitivity check
    for filepath in task.get("files_to_modify", []):
        sensitivity = classify_file(filepath)
        if sensitivity == "constitution":
            issues.append(f"BLOCKED: {filepath} is constitution-level. Worker cannot modify.")

    # Files to read must exist
    for filepath in task.get("files_to_read", []):
        if not (PROJECT_ROOT / filepath).exists():
            issues.append(f"File to read does not exist: {filepath}")

    # Unique task ID
    task_file = TASKS_DIR / f"{task.get('id', 'UNKNOWN')}.json"
    if task_file.exists():
        issues.append(f"Task ID {task.get('id')} already exists in .rsi/tasks/")

    return issues


# ---------------------------------------------------------------------------
# Worker system prompt
# ---------------------------------------------------------------------------

WORKER_SYSTEM_PROMPT = """You are a worker agent in the RSI framework.

ROLE: Implement code changes according to exact specifications.

CRITICAL OUTPUT RULES:
- Your ENTIRE response must be a single valid JSON object.
- Do NOT include any text before or after the JSON.
- Do NOT wrap the JSON in markdown code fences.
- Do NOT include comments in the JSON.
- Do NOT use trailing commas.
- Escape all special characters in string values properly.
- For multi-line code in "changes" values, use \\n for newlines.

RULES:
1. Study the provided file contents before writing.
2. Only modify files listed in files_to_modify.
3. Follow acceptance criteria exactly. No unrequested features.
4. Include a proof_wrong hypothesis.

RESPONSE FORMAT (respond with ONLY this JSON, nothing else):
{"changes": {"path/to/file.py": "full file contents"}, "proof_wrong": "hypothesis", "notes": "brief notes"}"""


def build_worker_prompt(task: dict) -> str:
    """Build the full prompt for the worker model, including file contents."""
    parts = [f"TASK SPECIFICATION:\n{json.dumps(task, indent=2)}\n"]

    # Inject file contents (Genchi Genbutsu for the worker)
    parts.append("FILE CONTENTS (read these before implementing):\n")
    for filepath in task.get("files_to_read", []):
        full_path = PROJECT_ROOT / filepath
        if full_path.exists():
            content = full_path.read_text()
            parts.append(f'<file path="{filepath}">\n{content}\n</file>\n')
        else:
            parts.append(f'<file path="{filepath}">\n(file not found)\n</file>\n')

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Robust JSON extraction from LLM output
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> dict | None:
    """Extract a JSON object from messy LLM output.

    Handles:
    - Clean JSON
    - JSON wrapped in ```json ... ``` fences
    - JSON with commentary before/after
    - JSON with trailing commas
    - JSON inside <json> tags or similar markup
    - Multiple JSON blocks (takes the largest)
    - Truncated JSON (attempts brace repair)
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Attempt 1: Direct parse (cleanest case)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: Extract from markdown code fences
    fence_patterns = [
        r"```(?:json)?\s*\n(.*?)\n\s*```",   # ```json ... ```
        r"```\s*\n?(.*?)\n?\s*```",            # ``` ... ```
    ]
    for pattern in fence_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                # Try cleaning the extracted content
                cleaned = _clean_json_string(match.group(1).strip())
                if cleaned:
                    return cleaned

    # Attempt 3: Extract from XML-like tags
    tag_patterns = [
        r"<json>(.*?)</json>",
        r"<response>(.*?)</response>",
        r"<output>(.*?)</output>",
    ]
    for pattern in tag_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

    # Attempt 4: Find the largest {...} block by brace matching
    result = _find_json_object(text)
    if result is not None:
        return result

    # Attempt 5: Try cleaning common issues and re-parsing
    cleaned = _clean_json_string(text)
    if cleaned is not None:
        return cleaned

    return None


def _find_json_object(text: str) -> dict | None:
    """Find the largest valid JSON object in text using brace matching."""
    candidates = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            depth = 0
            in_string = False
            escape = False
            j = i
            while j < len(text):
                c = text[j]
                if escape:
                    escape = False
                elif c == '\\' and in_string:
                    escape = True
                elif c == '"' and not escape:
                    in_string = not in_string
                elif not in_string:
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            candidate = text[i:j+1]
                            try:
                                parsed = json.loads(candidate)
                                if isinstance(parsed, dict):
                                    candidates.append(parsed)
                            except json.JSONDecodeError:
                                # Try cleaning
                                cleaned = _clean_json_string(candidate)
                                if cleaned is not None:
                                    candidates.append(cleaned)
                            break
                j += 1
        i += 1

    # Always try brace repair on the full text first — catches truncated outer objects
    # that _find_json_object misses because inner objects match first
    start = text.find('{')
    if start >= 0:
        fragment = text[start:]
        repaired = _repair_truncated_json(fragment)
        if repaired is not None and ("changes" in repaired or "proof_wrong" in repaired):
            return repaired

    if not candidates:
        return None

    # Return the candidate with "changes" key, or the largest one
    for c in candidates:
        if "changes" in c:
            return c
    return max(candidates, key=lambda x: len(str(x)))


def _clean_json_string(text: str) -> dict | None:
    """Fix common JSON issues and attempt to parse."""
    s = text.strip()

    # Remove leading/trailing non-JSON content
    start = s.find('{')
    end = s.rfind('}')
    if start >= 0 and end > start:
        s = s[start:end+1]

    # Fix trailing commas before } or ]
    s = re.sub(r',\s*([}\]])', r'\1', s)

    # Fix single quotes used instead of double quotes (risky but common)
    # Only do this if double-quote parse fails first
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Try replacing single quotes with double quotes
    # (only outside of already-double-quoted strings)
    try:
        # Simple heuristic: if no double quotes exist, swap singles
        if '"' not in s:
            s2 = s.replace("'", '"')
            return json.loads(s2)
    except json.JSONDecodeError:
        pass

    # Remove control characters that break JSON
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    return None


def _repair_truncated_json(fragment: str) -> dict | None:
    """Attempt to repair truncated JSON by closing braces/brackets."""
    s = fragment.rstrip()

    # Count unmatched braces
    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape = False

    for c in s:
        if escape:
            escape = False
            continue
        if c == '\\' and in_string:
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{': depth_brace += 1
        elif c == '}': depth_brace -= 1
        elif c == '[': depth_bracket += 1
        elif c == ']': depth_bracket -= 1

    # Close any unclosed strings
    if in_string:
        s += '"'

    # Remove trailing comma
    s = re.sub(r',\s*$', '', s)

    # Close brackets then braces
    s += ']' * max(0, depth_bracket)
    s += '}' * max(0, depth_brace)

    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    return None


# ---------------------------------------------------------------------------
# Worker API call
# ---------------------------------------------------------------------------

def call_worker(task: dict, revision_instruction: str = "") -> dict:
    """Call the worker model API and return parsed response.

    Returns:
        {
            "changes": {"path": "content", ...},
            "proof_wrong": "...",
            "notes": "...",
            "raw_response": "...",
            "tokens_used": N,
            "latency_seconds": N.N,
            "error": "..." (if failed)
        }
    """
    config = _load_worker_config()
    api_key = _get_api_key(config)

    prompt = build_worker_prompt(task)
    if revision_instruction:
        prompt += f"\n\nREVISION INSTRUCTION:\n{revision_instruction}\n"

    try:
        from openai import OpenAI
    except ImportError:
        return {"error": "openai package required. Install: pip install openai"}

    client = OpenAI(api_key=api_key, base_url=config["base_url"])

    start = time.time()
    try:
        response = client.chat.completions.create(
            model=config["model"],
            messages=[
                {"role": "system", "content": WORKER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=int(config.get("max_tokens", 8192)),
            temperature=0.3,
        )

        latency = round(time.time() - start, 1)
        raw = response.choices[0].message.content or ""
        tokens = 0
        if hasattr(response, "usage") and response.usage:
            tokens = (response.usage.prompt_tokens or 0) + (response.usage.completion_tokens or 0)

        # Robust JSON extraction — handles all common LLM output quirks
        parsed = _extract_json(raw)
        if parsed is None:
            return {"error": f"Worker returned invalid JSON. Raw (first 500 chars): {raw[:500]}", "raw_response": raw[:2000], "latency_seconds": latency}

        # Validate: only files_to_modify appear in changes
        allowed = set(task.get("files_to_modify", []))
        actual = set(parsed.get("changes", {}).keys())
        violations = actual - allowed
        if violations:
            return {
                "error": f"Worker modified unauthorized files: {violations}",
                "raw_response": raw[:2000],
                "latency_seconds": latency,
            }

        return {
            "changes": parsed.get("changes", {}),
            "proof_wrong": parsed.get("proof_wrong", ""),
            "notes": parsed.get("notes", ""),
            "raw_response": raw[:2000],
            "tokens_used": tokens,
            "latency_seconds": latency,
        }

    except Exception as e:
        return {"error": f"API call failed: {type(e).__name__}: {e}", "latency_seconds": round(time.time() - start, 1)}


# ---------------------------------------------------------------------------
# Result handling
# ---------------------------------------------------------------------------

def write_review(task: dict, result: dict) -> Path:
    """Write worker result to .memory/reviews/pending/ for overlord review."""
    _ensure_dirs()
    task_id = task["id"]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    review_content = f"""# Review: {task_id}

**Task:** {task['description']}
**Worker model:** {_load_worker_config().get('model', 'unknown')}
**Date:** {timestamp}
**Status:** PENDING REVIEW

## Instruction
{task.get('instruction', '')}

## Acceptance Criteria
{chr(10).join(f'- [ ] {c}' for c in task.get('acceptance_criteria', []))}

## Worker Proof-Wrong
{result.get('proof_wrong', '(none provided)')}

## Worker Notes
{result.get('notes', '(none)')}

## Proposed Changes
"""
    for path, content in result.get("changes", {}).items():
        review_content += f"\n### {path}\n```\n{content[:3000]}\n```\n"

    review_content += f"""
---
**Tokens used:** {result.get('tokens_used', 'unknown')}
**Latency:** {result.get('latency_seconds', 'unknown')}s
"""

    review_path = PENDING_DIR / f"{task_id}.md"
    review_path.write_text(review_content)
    return review_path


def apply_changes(task: dict, result: dict) -> list[str]:
    """Apply worker changes to disk. Returns list of applied files."""
    applied = []
    for filepath, content in result.get("changes", {}).items():
        full_path = PROJECT_ROOT / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        applied.append(filepath)
    return applied


def log_delegation(task: dict, result: dict, verdict: str = "PENDING") -> None:
    """Log delegation event to metrics."""
    _ensure_dirs()
    config = _load_worker_config()
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task.get("id"),
        "worker_model": config.get("model"),
        "verdict": verdict,
        "files_modified": len(result.get("changes", {})),
        "worker_tokens_used": result.get("tokens_used", 0),
        "worker_latency_seconds": result.get("latency_seconds", 0),
    }
    with open(DELEGATIONS_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_delegate(args):
    """Send a task to the worker model."""
    task_file = Path(args.task_file)
    if not task_file.exists():
        print(f"ERROR: Task file not found: {task_file}", file=sys.stderr)
        sys.exit(1)

    task = json.loads(task_file.read_text())

    # Validate
    issues = validate_task(task)
    if issues:
        print("Task validation failed:", file=sys.stderr)
        for issue in issues:
            print(f"  ! {issue}", file=sys.stderr)
        sys.exit(1)

    print(f"Delegating: {task['id']} — {task['description']}")
    print(f"Files to modify: {', '.join(task.get('files_to_modify', []))}")

    # Call worker
    revision = args.revise if hasattr(args, "revise") and args.revise else ""
    result = call_worker(task, revision)

    if result.get("error"):
        print(f"Worker error: {result['error']}", file=sys.stderr)
        log_delegation(task, result, "FAILED")
        sys.exit(1)

    # Write review
    review_path = write_review(task, result)
    log_delegation(task, result, "PENDING")
    print(f"Review written: {review_path.relative_to(PROJECT_ROOT)}")
    print(f"Worker proof-wrong: {result.get('proof_wrong', '(none)')[:80]}")

    # Apply if requested
    if args.apply:
        applied = apply_changes(task, result)
        print(f"Applied changes: {', '.join(applied)}")

        # Run self-verify
        import subprocess
        verify = subprocess.run(
            [sys.executable, "scripts/self_verify.py", "--files"] + applied + ["--skip-tests"],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
        )
        if verify.returncode == 0:
            print("Self-verify: PASSED")
        else:
            print("Self-verify: FAILED")
            print(verify.stdout[-500:] if verify.stdout else verify.stderr[-500:])
    else:
        print("Dry-run mode. Use --apply to write changes to disk.")


def cmd_history(args):
    """Show delegation history."""
    if not DELEGATIONS_LOG.exists():
        print("No delegation history.")
        return

    events = []
    with open(DELEGATIONS_LOG) as f:
        for line in f:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not events:
        print("No delegation history.")
        return

    print(f"\n{'=' * 60}")
    print(f"DELEGATION HISTORY — {len(events)} event(s)")
    print(f"{'=' * 60}\n")
    for e in events[-20:]:
        ts = e.get("timestamp", "?")[:19]
        print(f"  {ts}  {e.get('task_id', '?'):<12}  {e.get('verdict', '?'):<10}  "
              f"{e.get('files_modified', 0)} files  {e.get('worker_latency_seconds', 0)}s")


def main():
    parser = argparse.ArgumentParser(description="RSI Delegation Engine — send tasks to worker model")
    sub = parser.add_subparsers(dest="command")

    # Default: delegate a task file
    parser.add_argument("task_file", nargs="?", help="Path to task spec JSON file")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--revise", help="Revision instruction for the worker")
    parser.add_argument("--history", action="store_true", help="Show delegation history")

    args = parser.parse_args()

    if args.history:
        cmd_history(args)
    elif args.task_file:
        cmd_delegate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
