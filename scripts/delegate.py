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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is importable so `engine.protocol` resolves when this
# script is executed as `python scripts/delegate.py` rather than `-m`.
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))

from pydantic import ValidationError

from engine.protocol import TaskSpec, WorkerResult

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
TASKS_DIR = PROJECT_ROOT / ".rsi" / "tasks"
REVIEWS_DIR = PROJECT_ROOT / ".memory" / "reviews"
PENDING_DIR = REVIEWS_DIR / "pending"
RESULTS_DIR = REVIEWS_DIR / "results"
DELEGATIONS_LOG = PROJECT_ROOT / ".memory" / "metrics" / "delegations.jsonl"

# Architecture config
ARCHITECTURE_FILE = PROJECT_ROOT / ".rsi" / "architecture.yaml"


def _ensure_dirs():
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (REVIEWS_DIR / "accepted").mkdir(parents=True, exist_ok=True)
    (REVIEWS_DIR / "rejected").mkdir(parents=True, exist_ok=True)
    DELEGATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)


_worker_config_cache: dict[str, dict] | None = None
_active_worker: str | None = None  # Set by --worker flag in main()
_round_robin_index: int = 0  # Global counter for round-robin routing


@dataclass(frozen=True)
class WorkerProfile:
    """Typed view of a worker's architecture.yaml config.

    Session 3 consolidated eleven per-worker fields with varying fallback
    patterns into a single typed shape. `from_config` centralizes all casts
    and default resolution so call_worker / validate_task read attributes
    directly instead of re-deriving the same fallbacks at every call site.

    _load_worker_config is preserved as the raw-dict path for backward
    compatibility with existing tests and scripts; _load_worker_profile is
    the typed path the delegate itself uses.
    """

    name: str
    provider: str
    base_url: str
    model: str
    env_key: str
    max_tokens: int = 8192
    temperature: float = 0.3
    max_output_lines: int = 500
    client_timeout_seconds: int = 600
    max_retries: int = 2
    extra_body: dict | None = None
    output_format_preference: str = "either"

    @classmethod
    def from_config(cls, name: str, config: dict) -> "WorkerProfile":
        """Build a profile from a raw config dict (as returned by _load_worker_config).

        Handles:
        - int/float casts with safe fallback to defaults on non-numeric values
        - legacy extra_body_json string shim → extra_body dict
        - client_timeout_seconds fallback chain through legacy timeout_seconds
        - output_format_preference normalization to lowercase
        """
        def _int(key: str, default: int) -> int:
            try:
                val = config.get(key)
                return int(val) if val is not None else default
            except (TypeError, ValueError):
                return default

        def _float(key: str, default: float) -> float:
            try:
                val = config.get(key)
                return float(val) if val is not None else default
            except (TypeError, ValueError):
                return default

        # Client timeout — prefer client_timeout_seconds; fall back to the legacy
        # `timeout_seconds` field (projects that had it set before Session 3
        # intended it as the client budget even though nothing wired it through).
        client_timeout = _int("client_timeout_seconds", 0)
        if not client_timeout:
            client_timeout = _int("timeout_seconds", 600)

        # extra_body — prefer native nested dict; fall back to the legacy
        # extra_body_json string shim. Malformed shim raises ValueError so the
        # caller surfaces it rather than silently dropping the vendor params.
        extra_body: dict | None = None
        raw_eb = config.get("extra_body")
        if isinstance(raw_eb, dict):
            extra_body = raw_eb
        elif raw_eb is None:
            legacy = config.get("extra_body_json", "").strip()
            if legacy:
                try:
                    parsed = json.loads(legacy)
                    if isinstance(parsed, dict):
                        extra_body = parsed
                except json.JSONDecodeError:
                    # Defer the error to call_worker where it becomes a structured
                    # result — raising here would break validate_task callers
                    # that don't care about extra_body.
                    extra_body = None

        return cls(
            name=name,
            provider=str(config.get("provider", name)),
            base_url=str(config.get("base_url", "")),
            model=str(config.get("model", "")),
            env_key=str(config.get("env_key", "MINIMAX_API_KEY")),
            max_tokens=_int("max_tokens", 8192),
            temperature=_float("temperature", 0.3),
            max_output_lines=_int("max_output_lines", 500),
            client_timeout_seconds=client_timeout,
            max_retries=_int("max_retries", 2),
            extra_body=extra_body,
            output_format_preference=str(
                config.get("output_format_preference", "either")
            ).lower(),
        )


def _load_worker_profile(worker_name: str | None = None) -> WorkerProfile:
    """Load a worker's config and return it as a typed WorkerProfile."""
    raw = _load_worker_config(worker_name)
    return WorkerProfile.from_config(worker_name or "default", raw)


def _load_worker_config(worker_name: str | None = None) -> dict:
    """Load worker API config from architecture.yaml.

    If worker_name is given, looks up architecture.yaml `workers.<name>` section.
    Falls back to `worker_api` section for backward compat.
    Result is cached per worker_name.
    """
    global _worker_config_cache
    cache_key = worker_name or "__default__"
    if _worker_config_cache is not None and cache_key in _worker_config_cache:
        return _worker_config_cache[cache_key]

    _minimax_defaults = {
        "provider": "minimax",
        "base_url": "https://api.minimaxi.chat/v1",
        "model": "MiniMax-M2.7",
        "max_tokens": 8192,
        "timeout_seconds": 120,
        "env_key": "MINIMAX_API_KEY",
    }

    if not ARCHITECTURE_FILE.exists():
        config = dict(_minimax_defaults)
        config["base_url"] = os.environ.get("RSI_WORKER_BASE_URL", config["base_url"])
        config["model"] = os.environ.get("RSI_WORKER_MODEL", config["model"])
        if _worker_config_cache is None:
            _worker_config_cache = {}
        _worker_config_cache[cache_key] = config
        return config

    content = ARCHITECTURE_FILE.read_text(encoding="utf-8")

    if worker_name:
        config = _parse_named_worker(content, worker_name)
    else:
        config = _parse_worker_api_section(content)

    # Env vars override
    config["base_url"] = os.environ.get("RSI_WORKER_BASE_URL", config.get("base_url", "https://api.minimaxi.chat/v1"))
    config["model"] = os.environ.get("RSI_WORKER_MODEL", config.get("model", "MiniMax-M2.7"))
    config.setdefault("max_tokens", "8192")
    config.setdefault("timeout_seconds", "120")
    config.setdefault("env_key", "MINIMAX_API_KEY")
    # F5/F9 — per-worker defaults; preserve prior MiniMax-calibrated values.
    config.setdefault("temperature", "0.3")
    config.setdefault("max_output_lines", "500")

    if _worker_config_cache is None:
        _worker_config_cache = {}
    _worker_config_cache[cache_key] = config
    return config


def _parse_worker_api_section(content: str) -> dict:
    """Extract the flat `worker_api:` section from architecture.yaml."""
    config: dict = {}
    in_section = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped == "worker_api:":
            in_section = True
            continue
        if in_section and ":" in stripped and not stripped.startswith("#"):
            if not stripped.startswith("-") and line.startswith("  ") and not line.startswith("   "):
                key, _, val = stripped.partition(":")
                val = val.strip().strip('"').strip("'")
                if val:
                    config[key.strip()] = val
            elif not line.startswith("  "):
                in_section = False
    return config


def _parse_named_worker(content: str, name: str) -> dict:
    """Extract a named entry from the `workers:` section of architecture.yaml.

    Scalar values are stored as strings (callers cast to int/float as needed).
    Values starting with `{` or `[` are parsed as inline JSON (YAML flow-style)
    so nested structures like `extra_body: {"thinking": {"type": "disabled"}}`
    arrive as a real dict in the resulting config rather than a stringified
    JSON blob. Session 3 — replaces the earlier extra_body_json string shim.
    """
    config: dict = {}
    in_workers = False
    in_target = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped == "workers:":
            in_workers = True
            continue
        if in_workers:
            if line.startswith("  ") and not line.startswith("   ") and stripped.rstrip(":") == name:
                in_target = True
                continue
            if in_target:
                if line.startswith("    ") and ":" in stripped and not stripped.startswith("#"):
                    key, _, val = stripped.partition(":")
                    val = val.strip()
                    # YAML flow-style nested value (inline JSON)
                    if val.startswith(("{", "[")):
                        try:
                            config[key.strip()] = json.loads(val)
                            continue
                        except json.JSONDecodeError:
                            pass  # fall through to scalar string handling
                    # Scalar string fallback — strip surrounding quotes
                    val = val.strip('"').strip("'")
                    if val:
                        config[key.strip()] = val
                elif line.startswith("  ") and not line.startswith("    ") or (not line.startswith(" ") and line.strip()):
                    in_target = False
            if not line.startswith("  ") and line.strip() and not line.startswith(" "):
                in_workers = False
    if not config:
        raise ValueError(f"Worker '{name}' not found in architecture.yaml workers section.")
    return config


def _get_api_key(config: dict) -> str:
    env_key = config.get("env_key", "MINIMAX_API_KEY")
    key = os.environ.get(env_key, "")
    if not key:
        print(f"ERROR: {env_key} environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return key


# ---------------------------------------------------------------------------
# Worker routing
# ---------------------------------------------------------------------------


def _get_available_workers() -> list[str]:
    """Return names of configured workers whose API keys are present in env."""
    if not ARCHITECTURE_FILE.exists():
        return []
    content = ARCHITECTURE_FILE.read_text(encoding="utf-8")
    available = []
    in_workers = False
    current_name: str | None = None
    current_env_key: str | None = None

    for line in content.split("\n"):
        stripped = line.strip()
        if stripped == "workers:":
            in_workers = True
            continue
        if not in_workers:
            continue
        # Top-level workers section ends when indentation drops
        if line and not line.startswith(" "):
            in_workers = False
            if current_name and current_env_key and os.environ.get(current_env_key, ""):
                available.append(current_name)
            break
        # Named worker entry (2-space indent, ends with colon)
        if line.startswith("  ") and not line.startswith("   ") and stripped.endswith(":"):
            if current_name and current_env_key and os.environ.get(current_env_key, ""):
                available.append(current_name)
            current_name = stripped.rstrip(":")
            current_env_key = None
        # env_key field (4-space indent)
        if line.startswith("    ") and stripped.startswith("env_key:"):
            _, _, val = stripped.partition(":")
            current_env_key = val.strip().strip('"').strip("'")

    # Flush last entry
    if current_name and current_env_key and os.environ.get(current_env_key, ""):
        available.append(current_name)

    return available


def _resolve_worker(task: dict) -> str | None:
    """Pick the worker for a task.

    Priority:
    1. task["worker"] — explicit routing decision by Claude
    2. _active_worker  — --worker CLI flag (single-task override)
    3. Round-robin across available workers (auto-distribution)
    4. None — fall back to worker_api default
    """
    global _round_robin_index

    # Explicit per-task routing (Claude's decision)
    if task.get("worker"):
        return task["worker"]

    # CLI override
    if _active_worker:
        return _active_worker

    # Round-robin across available workers
    available = _get_available_workers()
    if not available:
        return None
    worker = available[_round_robin_index % len(available)]
    _round_robin_index += 1
    return worker


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


class UnsafePathError(ValueError):
    """Raised when a user- or worker-supplied path escapes PROJECT_ROOT."""


def _safe_project_path(filepath: str) -> Path:
    """Resolve `filepath` under PROJECT_ROOT and reject anything that escapes.

    Blocks:
      - absolute paths (/etc/passwd, C:\\Windows\\foo — pathlib's '/' operator
        discards the left side when the right is absolute)
      - traversal via .. that resolves outside PROJECT_ROOT
      - Windows drive letters embedded in a relative-looking path

    Returns the resolved absolute Path on success.
    """
    p = Path(filepath)
    if p.is_absolute() or (len(filepath) >= 2 and filepath[1] == ":"):
        raise UnsafePathError(f"Absolute paths are not allowed: {filepath!r}")
    candidate = (PROJECT_ROOT / p).resolve()
    root = PROJECT_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(f"Path escapes project root: {filepath!r}") from exc
    return candidate


# ---------------------------------------------------------------------------
# Task validation
# ---------------------------------------------------------------------------


def validate_task(task: dict) -> list[str]:
    """Validate task spec against architecture rules. Returns list of issues."""
    from scripts.classify_file import classify_file

    issues: list[str] = []

    # Schema validation via Pydantic TaskSpec — catches required fields,
    # non-empty strings, non-empty list[str] constraints in one pass.
    try:
        TaskSpec.model_validate(task)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            msg = err["msg"]
            # Preserve legacy error strings for missing top-level fields so
            # existing tests and downstream consumers still match on them.
            if err["type"] == "missing" and loc in {
                "id",
                "description",
                "instruction",
                "files_to_modify",
                "acceptance_criteria",
                "proof_wrong",
            }:
                issues.append(f"Missing required field: {loc}")
            elif loc == "acceptance_criteria":
                issues.append("acceptance_criteria must have at least one entry")
            elif loc == "proof_wrong":
                issues.append("proof_wrong is required")
            else:
                issues.append(f"Schema: {loc}: {msg}")

    # Path-safety + sensitivity on files_to_modify
    for filepath in task.get("files_to_modify", []):
        try:
            _safe_project_path(filepath)
        except UnsafePathError as exc:
            issues.append(f"BLOCKED: {exc}")
            continue
        sensitivity = classify_file(filepath)
        if sensitivity == "constitution":
            issues.append(f"BLOCKED: {filepath} is constitution-level. Worker cannot modify.")

    # Path-safety + existence on files_to_read
    for filepath in task.get("files_to_read", []):
        # Strip line-range suffix for existence check
        clean_path = (
            filepath.split(":")[0]
            if ":" in filepath and filepath.split(":")[-1][0:1].isdigit()
            else filepath
        )
        try:
            safe = _safe_project_path(clean_path)
        except UnsafePathError as exc:
            issues.append(f"BLOCKED: {exc}")
            continue
        if not safe.exists():
            issues.append(f"File to read does not exist: {clean_path}")

    # F9 — Output-size warning threshold read from WorkerProfile. Falls back
    # to 500 when no worker is declared on the task (legacy path).
    worker_name = task.get("worker")
    if worker_name:
        try:
            max_output_lines = _load_worker_profile(worker_name).max_output_lines
        except (ValueError, KeyError):
            max_output_lines = 500
    else:
        max_output_lines = 500
    for filepath in task.get("files_to_modify", []):
        try:
            full = _safe_project_path(filepath)
        except UnsafePathError:
            continue  # already reported above
        if full.exists():
            line_count = full.read_text(encoding="utf-8").count("\n") + 1
            if line_count > max_output_lines:
                worker_label = worker_name or "worker"
                issues.append(
                    f"WARNING: {filepath} has {line_count} lines (>{max_output_lines} "
                    f"for {worker_label}). Output may be truncated. Decompose into "
                    f"smaller tasks or raise workers.{worker_label}.max_output_lines."
                )

    # Unique task ID — skip if we're delegating the file that's already in .rsi/tasks/
    # (the overlord writes the spec there, then calls delegate.py with that same path)
    task_id = task.get("id", "UNKNOWN")
    task_file_in_dir = TASKS_DIR / f"{task_id}.json"
    if task_file_in_dir.exists():
        try:
            existing = json.loads(task_file_in_dir.read_text(encoding="utf-8"))
            # Only flag if existing task has a DIFFERENT description (true duplicate)
            if existing.get("description") != task.get("description"):
                issues.append(
                    f"Task ID {task_id} already exists with different description in .rsi/tasks/"
                )
        except (OSError, json.JSONDecodeError):
            pass

    return issues


# ---------------------------------------------------------------------------
# Worker system prompt
# ---------------------------------------------------------------------------

WORKER_SYSTEM_PROMPT = """You are a code worker. You receive a task and return JSON.

RESPONSE RULES (CRITICAL — violations cause rejection):
1. Respond with ONLY a JSON object. Nothing else.
2. Do NOT include <think> tags, commentary, markdown, or explanations.
3. Do NOT wrap JSON in code fences.
4. Do NOT use trailing commas.
5. For multi-line code: use actual newlines inside JSON strings, not \\n escapes.
6. Only modify files listed in files_to_modify.

IMPORT RULES:
- Check the provided file contents for EXACT import paths.
- If the task says files_to_read includes "src/scoring/scorer.py" and it
  contains "class BWBScorer", then import as "from src.scoring.scorer import BWBScorer".
- Do NOT guess import paths. Use what you see in the provided files.

TESTING RULES:
- If writing tests, import from the EXACT module path of the implementation.
- Mock external dependencies only. Do NOT mock the function being tested.
- Test actual behavior, not mock return values.

RESPONSE FORMAT:
{"changes": {"path/to/file.py": "full file contents"}, "proof_wrong": "specific hypothesis", "notes": "brief notes"}"""


def _parse_file_spec(spec: str) -> tuple[str, int | None, int | None]:
    """Parse a file spec with optional line range.

    "src/main.py"         -> ("src/main.py", None, None)
    "src/main.py:100-200" -> ("src/main.py", 100, 200)
    "src/main.py:50"      -> ("src/main.py", 50, None)
    """
    if ":" in spec:
        parts = spec.rsplit(":", 1)
        filepath = parts[0]
        range_str = parts[1]
        # Don't parse Windows drive letters (C:\...) as line ranges
        if len(range_str) > 0 and range_str[0].isdigit():
            if "-" in range_str:
                start, end = range_str.split("-", 1)
                return filepath, int(start), int(end)
            else:
                return filepath, int(range_str), None
    return spec, None, None


def build_worker_prompt(task: dict) -> str:
    """Build the full prompt for the worker model, including file contents.

    Supports line-range restriction to reduce token usage:
        files_to_read: ["src/big.py"]           -> full file
        files_to_read: ["src/big.py:100-200"]   -> lines 100-200 only
        files_to_read: ["src/big.py:50"]         -> from line 50 to end
    """
    # Build lean task spec -- only fields the worker needs
    lean_task = {
        "id": task.get("id"),
        "instruction": task.get("instruction", task.get("description", "")),
        "files_to_modify": task.get("files_to_modify", []),
        "acceptance_criteria": task.get("acceptance_criteria", []),
        "constraints": task.get("constraints", []),
    }
    parts = [f"TASK:\n{json.dumps(lean_task, indent=2)}\n"]

    # Inject file contents with optional line-range restriction
    parts.append("FILE CONTENTS:\n")
    for file_spec in task.get("files_to_read", []):
        filepath, start_line, end_line = _parse_file_spec(file_spec)
        # Reject any path that escapes PROJECT_ROOT before reading. A bad
        # task spec must NOT be able to exfiltrate arbitrary host files
        # (e.g., /etc/passwd, ~/.ssh/id_rsa) into the worker prompt.
        try:
            full_path = _safe_project_path(filepath)
        except UnsafePathError as exc:
            parts.append(f'<file path="{filepath}">\n(REFUSED: {exc})\n</file>\n')
            continue
        if full_path.exists():
            content = full_path.read_text(encoding="utf-8")
            if start_line or end_line:
                lines = content.split("\n")
                s = (start_line - 1) if start_line else 0
                e = end_line if end_line else len(lines)
                content = "\n".join(lines[s:e])
                parts.append(f'<file path="{filepath}" lines="{s + 1}-{e}">\n{content}\n</file>\n')
            else:
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

    # Pre-processing: strip <think>...</think> tags (MiniMax reasoning output)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Pre-processing: strip other common wrapper tags
    text = re.sub(r"<output>|</output>|<response>|</response>", "", text).strip()

    # Attempt 1: Direct parse (cleanest case)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: Extract from markdown code fences
    fence_patterns = [
        r"```(?:json)?\s*\n(.*?)\n\s*```",  # ```json ... ```
        r"```\s*\n?(.*?)\n?\s*```",  # ``` ... ```
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
        if text[i] == "{":
            depth = 0
            in_string = False
            escape = False
            j = i
            while j < len(text):
                c = text[j]
                if escape:
                    escape = False
                elif c == "\\" and in_string:
                    escape = True
                elif c == '"' and not escape:
                    in_string = not in_string
                elif not in_string:
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = text[i : j + 1]
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
    start = text.find("{")
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


_DELIMITER_FILE_RE = re.compile(
    r"<<<FILE:\s*(?P<path>[^\r\n>]+?)\s*>>>\r?\n(?P<body>.*?)\r?\n<<<END FILE>>>",
    re.DOTALL,
)


def _extract_delimiter_files(raw: str) -> dict | None:
    """Parse `<<<FILE: path>>> ... <<<END FILE>>>` blocks into a changes dict.

    Fallback for workers that emit delimiter-bounded file blocks instead of
    the expected JSON wrapper. Returns None when no delimiter blocks are found.
    """
    if not raw:
        return None
    matches = list(_DELIMITER_FILE_RE.finditer(raw))
    if not matches:
        return None
    changes: dict[str, str] = {}
    for m in matches:
        path = m.group("path").strip()
        if path:
            changes[path] = m.group("body")
    if not changes:
        return None
    return {"changes": changes, "proof_wrong": "", "notes": ""}


def _clean_json_string(text: str) -> dict | None:
    """Fix common JSON issues and attempt to parse."""
    s = text.strip()

    # Remove leading/trailing non-JSON content
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        s = s[start : end + 1]

    # Fix trailing commas before } or ]
    s = re.sub(r",\s*([}\]])", r"\1", s)

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
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
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
        if c == "\\" and in_string:
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth_brace += 1
        elif c == "}":
            depth_brace -= 1
        elif c == "[":
            depth_bracket += 1
        elif c == "]":
            depth_bracket -= 1

    # Close any unclosed strings
    if in_string:
        s += '"'

    # Remove trailing comma
    s = re.sub(r",\s*$", "", s)

    # Close brackets then braces
    s += "]" * max(0, depth_bracket)
    s += "}" * max(0, depth_brace)

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


def call_worker(task: dict, revision_instruction: str = "", worker_name: str | None = None) -> dict:
    """Call the worker model API and return parsed response.

    worker_name: explicit worker to use (overrides _active_worker and task["worker"]).
                 If None, _resolve_worker(task) is called to determine routing.

    Returns:
        {
            "changes": {"path": "content", ...},
            "proof_wrong": "...",
            "notes": "...",
            "raw_response": "...",
            "tokens_used": N,
            "latency_seconds": N.N,
            "worker": "name of worker used",
            "error": "..." (if failed)
        }
    """
    resolved = worker_name if worker_name is not None else _resolve_worker(task)
    profile = _load_worker_profile(resolved)
    api_key = _get_api_key({"env_key": profile.env_key})

    prompt = build_worker_prompt(task)
    if revision_instruction:
        prompt += f"\n\nREVISION INSTRUCTION:\n{revision_instruction}\n"

    try:
        from openai import OpenAI
    except ImportError:
        return {"error": "openai package required. Install: pip install openai"}

    # Per-worker client-side budgets come from WorkerProfile (built by
    # from_config with fallback chains for legacy field names).
    client = OpenAI(
        api_key=api_key,
        base_url=profile.base_url,
        timeout=profile.client_timeout_seconds,
        max_retries=profile.max_retries,
    )

    start = time.time()
    try:
        # extra_body is already the resolved dict (or None) from WorkerProfile.
        # Surface a structured error if the config had a malformed string shim.
        raw_eb = _load_worker_config(resolved).get("extra_body_json", "").strip()
        if profile.extra_body is None and raw_eb:
            # from_config silently dropped the malformed shim; re-surface here.
            try:
                json.loads(raw_eb)
            except json.JSONDecodeError as e:
                return {
                    "error": (
                        f"Worker '{resolved}' has invalid extra_body_json in "
                        f"architecture.yaml: {e}"
                    ),
                    "latency_seconds": round(time.time() - start, 1),
                    "worker": profile.provider,
                }
        create_kwargs: dict = {}
        if profile.extra_body:
            create_kwargs["extra_body"] = profile.extra_body
        response = client.chat.completions.create(
            model=profile.model,
            messages=[
                {"role": "system", "content": WORKER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=profile.max_tokens,
            temperature=profile.temperature,
            **create_kwargs,
        )

        latency = round(time.time() - start, 1)
        raw = response.choices[0].message.content or ""
        # F6 — persist full raw response to sidecar BEFORE any parsing.
        # Guarantees billed worker output is recoverable even when parse fails.
        try:
            _write_raw_sidecar(task.get("id", "UNKNOWN"), raw)
        except OSError:
            pass
        tokens = 0
        if hasattr(response, "usage") and response.usage:
            tokens = (response.usage.prompt_tokens or 0) + (response.usage.completion_tokens or 0)

        # Fail fast on truncation — if the model hit max_tokens, the JSON repair
        # path silently produces partial file contents. Surface this so the
        # caller can retry with a higher budget or decompose the task.
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        if finish_reason == "length":
            return {
                "error": (
                    f"Worker hit max_tokens limit ({profile.max_tokens}); response was truncated. "
                    f"Increase workers.{resolved}.max_tokens in .rsi/architecture.yaml or decompose the task."
                ),
                "raw_response": raw[:2000],
                "tokens_used": tokens,
                "latency_seconds": latency,
            }

        # Robust output extraction — parser chain order is driven by the
        # worker's output_format_preference (from WorkerProfile, lowercased):
        #   "json" / "either" / unset → JSON first, delimiter fallback (default)
        #   "delimiter"                → delimiter first, JSON fallback
        # The fallback in either direction preserves 9b behavior (no billed
        # output is lost to a parser mismatch).
        if profile.output_format_preference == "delimiter":
            parsed = _extract_delimiter_files(raw) or _extract_json(raw)
        else:
            parsed = _extract_json(raw) or _extract_delimiter_files(raw)
        if parsed is None:
            return {
                "error": f"Worker returned invalid JSON. Raw (first 500 chars): {raw[:500]}",
                "raw_response": raw[:2000],
                "latency_seconds": latency,
            }

        # Validate: only files_to_modify appear in changes, and every worker
        # path resolves inside PROJECT_ROOT. apply_changes re-checks, but
        # failing fast here keeps poisoned results out of save_result too.
        allowed = set(task.get("files_to_modify", []))
        actual = set(parsed.get("changes", {}).keys())
        violations = actual - allowed
        if violations:
            return {
                "error": f"Worker modified unauthorized files: {violations}",
                "raw_response": raw[:2000],
                "latency_seconds": latency,
            }
        for worker_path in actual:
            try:
                _safe_project_path(worker_path)
            except UnsafePathError as exc:
                return {
                    "error": f"Worker returned unsafe path: {exc}",
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
            "worker": profile.provider,
        }

    except Exception as e:
        return {
            "error": f"API call failed: {type(e).__name__}: {e}",
            "latency_seconds": round(time.time() - start, 1),
            "worker": profile.provider,
        }


# ---------------------------------------------------------------------------
# Result handling
# ---------------------------------------------------------------------------


def _write_raw_sidecar(task_id: str, raw: str) -> Path:
    """Persist the worker's full raw response to a sidecar file.

    Called before any parsing attempt so that parser mismatches never result
    in total loss of billed worker output. Sidecars live alongside the parsed
    result JSON in RESULTS_DIR and are keyed by task id. Writes are full
    content (no truncation); callers should bound their own in-memory use.
    """
    _ensure_dirs()
    sidecar = RESULTS_DIR / f"{task_id}.raw.txt"
    sidecar.write_text(raw, encoding="utf-8")
    return sidecar


def save_result(task_id: str, result: dict) -> Path:
    """Store worker result as JSON for later apply without re-calling API."""
    _ensure_dirs()
    result_path = RESULTS_DIR / f"{task_id}.json"
    # Don't store raw_response (large, not needed for apply — raw is on disk
    # via _write_raw_sidecar at {task_id}.raw.txt).
    stored = {k: v for k, v in result.items() if k != "raw_response"}
    result_path.write_text(json.dumps(stored, indent=2, ensure_ascii=False), encoding="utf-8")
    return result_path


def load_result(task_id: str) -> dict | None:
    """Load stored worker result, validated through WorkerResult. Returns None if not found."""
    result_path = RESULTS_DIR / f"{task_id}.json"
    if not result_path.exists():
        return None
    try:
        raw = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        # Parse through WorkerResult so downstream callers can rely on
        # typed fields (changes/tokens_used/etc.) having correct types.
        # extra='allow' keeps any unknown keys intact.
        return WorkerResult.model_validate(raw).model_dump()
    except ValidationError:
        # Fall back to raw dict so legacy result files still load.
        return raw


def write_review(task: dict, result: dict) -> Path:
    """Write worker result to .memory/reviews/pending/ for overlord review.

    Also stores the structured result JSON for later apply without re-calling API.
    """
    _ensure_dirs()
    task_id = task["id"]

    # Store structured result for apply_changes to use later
    save_result(task_id, result)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # List changed files with line counts, not full contents
    changes_summary = []
    for path, content in result.get("changes", {}).items():
        line_count = content.count("\n") + 1
        changes_summary.append(f"- {path} ({line_count} lines)")

    review_content = f"""# Review: {task_id}

**Date:** {timestamp}
**Status:** PENDING REVIEW
**Task spec:** .rsi/tasks/{task_id}.json

## Proof-Wrong
{result.get("proof_wrong", "(none)")}

## Changes
{chr(10).join(changes_summary)}

## Notes
{result.get("notes", "(none)")}

---
Tokens: {result.get("tokens_used", "?")} | Latency: {result.get("latency_seconds", "?")}s
"""

    review_path = PENDING_DIR / f"{task_id}.md"
    review_path.write_text(review_content, encoding="utf-8")
    return review_path


def apply_changes(task: dict, result: dict) -> list[str]:
    """Apply worker changes to disk with quality ratchet.

    Quality ratchet (inspired by toryo): after writing files, run self_verify.
    If verify passes -> checkpoint commit. If fails -> revert all changes.
    Quality only goes up, never down.

    Also handles MiniMax double-escaped newlines.
    """
    applied = []
    original_contents = {}

    for filepath, content in result.get("changes", {}).items():
        # Bound every write to PROJECT_ROOT. A malicious or confused worker
        # cannot write outside the project (e.g., ~/.ssh/authorized_keys,
        # /etc/*, C:\Windows\*) via absolute or traversal paths.
        try:
            full_path = _safe_project_path(filepath)
        except UnsafePathError as exc:
            print(f"[RSI] REFUSED unsafe worker path: {exc}", file=sys.stderr)
            continue
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Store original for revert
        if full_path.exists():
            original_contents[filepath] = full_path.read_text(encoding="utf-8")

        # Fix double-escaped newlines from MiniMax
        if "\\n" in content and "\n" not in content:
            content = content.replace("\\n", "\n")
        if "\\t" in content and "\t" not in content:
            content = content.replace("\\t", "\t")

        # Ensure file ends with newline
        if content and not content.endswith("\n"):
            content += "\n"

        full_path.write_text(content, encoding="utf-8")
        applied.append(filepath)

    if not applied:
        return []

    # Quality ratchet: verify then checkpoint or revert
    verify_ok = _run_verify(applied)

    if verify_ok:
        task_id = task.get("id", "unknown")
        _git_checkpoint(task_id, applied)
        return applied
    else:
        # Revert all changes
        _git_revert(applied, original_contents)
        return []


def _run_verify(files: list[str]) -> bool:
    """Run self_verify on changed files. Returns True if passed."""
    import subprocess as sp

    result = sp.run(
        [sys.executable, "scripts/self_verify.py", "--files"] + files + ["--skip-tests"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode == 0:
        print("[RSI] Quality ratchet: VERIFY PASSED")
        return True
    else:
        print("[RSI] Quality ratchet: VERIFY FAILED - reverting changes")
        # Show first few lines of error
        for line in result.stdout.split("\n")[-5:]:
            if line.strip():
                print(f"  {line.strip()}")
        return False


def _run_api_check(spec_path: Path, task: dict) -> tuple[bool, str]:
    """Pre-dispatch API verification. Skips research/audit task types.

    Shells out to scripts/api_check.py. Returns (ok, combined_output).
    """
    if task.get("task_type") in {"research", "audit"}:
        return True, f"api-check skipped (task_type={task.get('task_type')})"

    import subprocess as sp

    result = sp.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "api_check.py"), str(spec_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def _git_checkpoint(task_id: str, files: list[str]) -> None:
    """Create a checkpoint commit for accepted changes."""
    import subprocess as sp

    try:
        sp.run(["git", "add"] + files, cwd=PROJECT_ROOT, capture_output=True, timeout=10)
        sp.run(
            ["git", "commit", "-m", f"rsi-checkpoint: {task_id}", "--no-verify"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            timeout=10,
        )
        print(f"[RSI] Quality ratchet: checkpoint commit (rsi-checkpoint: {task_id})")
    except Exception:
        pass  # Non-critical — checkpoint is best-effort


def _git_revert(files: list[str], originals: dict[str, str]) -> None:
    """Revert changed files to their original content."""
    for filepath in files:
        try:
            full_path = _safe_project_path(filepath)
        except UnsafePathError:
            continue  # should not happen — apply_changes already filtered these
        if filepath in originals:
            full_path.write_text(originals[filepath], encoding="utf-8")
            print(f"[RSI] Reverted: {filepath}")
        elif full_path.exists():
            full_path.unlink()
            print(f"[RSI] Removed new file: {filepath}")


def log_delegation(task: dict, result: dict, verdict: str = "PENDING") -> None:
    """Log delegation event to metrics."""
    _ensure_dirs()
    config = _load_worker_config(_active_worker)
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "task_id": task.get("id"),
        "worker_model": config.get("model"),
        "verdict": verdict,
        "files_modified": len(result.get("changes", {})),
        "worker_tokens_used": result.get("tokens_used", 0),
        "worker_latency_seconds": result.get("latency_seconds", 0),
    }
    with open(DELEGATIONS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


# ---------------------------------------------------------------------------
# Parallel delegation (inspired by ccswarm)
# ---------------------------------------------------------------------------


def delegate_parallel(task_files: list[str], max_workers: int = 10) -> list[dict]:
    """Send tasks to MiniMax with DAG-aware parallel execution.

    Respects both explicit depends_on and implicit file overlap dependencies.
    Tasks are sorted into execution layers — each layer runs in parallel,
    layers execute sequentially.

    `max_workers` was raised from 3 to 10 after Phase E7 measured 99.96%
    thread-pool efficiency at 20 concurrent workers with zero GIL pressure
    (see docs/decisions/phase-E7.md). If MiniMax throttles concurrent
    requests from one API key, lower this with --workers.

    Inspired by ccswarm (parallelism) and OpenMultiAgent (task DAG).
    """
    import concurrent.futures

    # Load all task specs
    tasks = []
    for tf in task_files:
        path = Path(tf)
        if not path.exists():
            path = TASKS_DIR / tf
        if not path.exists():
            print(f"  Skip (not found): {tf}", file=sys.stderr)
            continue
        try:
            tasks.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            print(f"  Skip (invalid JSON): {tf}", file=sys.stderr)

    if not tasks:
        return []

    # Build DAG and sort into execution layers
    dag = _build_dag(tasks)
    cycle = _detect_cycle(dag)
    if cycle:
        print(f"[RSI] ERROR: Dependency cycle detected: {cycle}", file=sys.stderr)
        # Fall back to sequential
        layers = [[t["id"] for t in tasks]]
    else:
        layers = _topological_layers(dag)

    task_map = {t["id"]: t for t in tasks}
    print(f"[RSI] Parallel delegation: {len(tasks)} tasks, {len(layers)} layer(s)")
    for i, layer in enumerate(layers):
        print(f"  Layer {i}: {', '.join(layer)}")

    all_results = []

    # Execute layer by layer — within each layer, tasks run in parallel
    for layer_idx, layer_ids in enumerate(layers):
        layer_tasks = [task_map[tid] for tid in layer_ids if tid in task_map]
        if not layer_tasks:
            continue

        print(f"\n[RSI] Executing layer {layer_idx + 1}/{len(layers)} ({len(layer_tasks)} tasks)")

        if len(layer_tasks) == 1:
            # Single task — no need for thread pool
            results = _execute_group(layer_tasks, layer_idx + 1, len(layers))
            all_results.extend(results)
        else:
            # Multiple tasks — run in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {}
                for task in layer_tasks:
                    future = pool.submit(_execute_single, task)
                    futures[future] = task

                for future in concurrent.futures.as_completed(futures):
                    task = futures[future]
                    try:
                        result = future.result()
                        all_results.append(result)
                    except Exception as e:
                        all_results.append(
                            {
                                "task_id": task.get("id"),
                                "status": "error",
                                "error": str(e),
                            }
                        )

    return all_results


def _execute_single(task: dict) -> dict:
    """Execute a single task (for parallel dispatch)."""
    task_id = task.get("id", "?")
    routed_worker = _resolve_worker(task)
    route_reason = "explicit" if task.get("worker") else ("cli" if _active_worker else "round-robin")
    print(f"  [{task_id}] → {routed_worker or 'default'} ({route_reason})")

    if os.environ.get("RSI_SKIP_API_CHECK") != "1":
        spec_path = TASKS_DIR / f"{task_id}.json"
        if spec_path.exists():
            ok, api_output = _run_api_check(spec_path, task)
            if not ok:
                return {
                    "task_id": task_id,
                    "status": "failed",
                    "error": "api_check_failed",
                    "output": api_output,
                }

    result = call_worker(task, worker_name=routed_worker)
    if result.get("error"):
        return {"task_id": task_id, "status": "failed", "error": result["error"]}

    write_review(task, result)
    log_delegation(task, result, "PENDING")
    return {
        "task_id": task_id,
        "status": "pending",
        "worker": result.get("worker", routed_worker),
        "changes": list(result.get("changes", {}).keys()),
        "proof_wrong": result.get("proof_wrong", ""),
    }


def _build_dag(tasks: list[dict]) -> dict[str, set[str]]:
    """Build dependency graph from depends_on + implicit file overlap.

    Inspired by OpenMultiAgent's task DAG resolution.

    Returns: {task_id: set of dependency task_ids}
    """
    task_ids = {t["id"] for t in tasks}
    dag: dict[str, set[str]] = {t["id"]: set() for t in tasks}

    for task in tasks:
        tid = task["id"]

        # Explicit depends_on
        for dep in task.get("depends_on", []):
            if dep in task_ids:
                dag[tid].add(dep)

        # Implicit: file overlap with earlier tasks
        task_files = set(task.get("files_to_modify", []))
        for other in tasks:
            if other["id"] == tid:
                continue
            other_files = set(other.get("files_to_modify", []))
            if task_files & other_files:
                # Both modify same file — later one depends on earlier
                # Use task ID ordering as tiebreaker
                if other["id"] < tid:
                    dag[tid].add(other["id"])

    return dag


def _detect_cycle(dag: dict[str, set[str]]) -> list[str] | None:
    """Detect cycles in the DAG. Returns cycle path or None."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in dag}
    path: list[str] = []

    def dfs(node: str) -> bool:
        color[node] = GRAY
        path.append(node)
        for dep in dag.get(node, set()):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                cycle_start = path.index(dep)
                return True
            if color[dep] == WHITE and dfs(dep):
                return True
        path.pop()
        color[node] = BLACK
        return False

    for node in dag:
        if color[node] == WHITE:
            if dfs(node):
                return path
    return None


def _topological_layers(dag: dict[str, set[str]]) -> list[list[str]]:
    """Topological sort into execution layers.

    Layer 0: tasks with no dependencies (run first, in parallel)
    Layer 1: tasks depending only on layer 0 (run after layer 0, in parallel)
    etc.

    Returns: list of layers, each layer is a list of task IDs.
    """
    remaining = {k: set(v) for k, v in dag.items()}
    layers: list[list[str]] = []
    completed: set[str] = set()

    while remaining:
        # Find tasks whose dependencies are all completed
        layer = [tid for tid, deps in remaining.items() if deps <= completed]
        if not layer:
            # No progress — remaining tasks have unresolvable deps
            # Put them all in one final layer
            layers.append(list(remaining.keys()))
            break
        layers.append(sorted(layer))
        completed.update(layer)
        for tid in layer:
            del remaining[tid]

    return layers


def _group_by_file_overlap(tasks: list[dict]) -> list[list[dict]]:
    """Group tasks by file overlap. Non-overlapping tasks go in separate groups."""
    groups: list[list[dict]] = []
    used_files: list[set[str]] = []

    for task in tasks:
        files = set(task.get("files_to_modify", []))
        placed = False

        for i, group_files in enumerate(used_files):
            if files & group_files:  # Overlap — add to this group
                groups[i].append(task)
                used_files[i] |= files
                placed = True
                break

        if not placed:
            groups.append([task])
            used_files.append(files)

    return groups


def _execute_group(group: list[dict], group_num: int, total_groups: int) -> list[dict]:
    """Execute a group of tasks sequentially (they share files)."""
    results = []
    for task in group:
        task_id = task.get("id", "?")
        print(f"  [Group {group_num}/{total_groups}] {task_id}: {task.get('description', '')[:50]}")

        result = call_worker(task)
        if result.get("error"):
            results.append({"task_id": task_id, "status": "failed", "error": result["error"]})
            continue

        write_review(task, result)
        log_delegation(task, result, "PENDING")
        results.append(
            {
                "task_id": task_id,
                "status": "pending",
                "changes": list(result.get("changes", {}).keys()),
                "proof_wrong": result.get("proof_wrong", ""),
            }
        )

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_delegate(args):
    """Send a task to the worker model."""
    task_file = Path(args.task_file)
    if not task_file.exists():
        print(f"ERROR: Task file not found: {task_file}", file=sys.stderr)
        sys.exit(1)

    try:
        task = json.loads(task_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: Task file is not valid JSON ({task_file}): {exc}", file=sys.stderr)
        sys.exit(1)

    # Validate
    issues = validate_task(task)
    if issues:
        print("Task validation failed:", file=sys.stderr)
        for issue in issues:
            print(f"  ! {issue}", file=sys.stderr)
        sys.exit(1)

    print(f"Delegating: {task['id']} — {task['description']}")
    print(f"Files to modify: {', '.join(task.get('files_to_modify', []))}")

    # Pre-dispatch API verification
    if not getattr(args, "no_api_check", False):
        ok, api_output = _run_api_check(task_file, task)
        if not ok:
            print(api_output, file=sys.stderr)
            print(
                "Pre-dispatch API check failed — fix the spec or rerun with --no-api-check",
                file=sys.stderr,
            )
            sys.exit(1)

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
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
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
    with open(DELEGATIONS_LOG, encoding="utf-8") as f:
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
        print(
            f"  {ts}  {e.get('task_id', '?'):<12}  {e.get('verdict', '?'):<10}  "
            f"{e.get('files_modified', 0)} files  {e.get('worker_latency_seconds', 0)}s"
        )


def main():
    parser = argparse.ArgumentParser(
        description="RSI Delegation Engine -- send tasks to worker model"
    )
    parser.add_argument("task_file", nargs="?", help="Path to task spec JSON file")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--revise", help="Revision instruction for the worker")
    parser.add_argument("--history", action="store_true", help="Show delegation history")
    parser.add_argument("--parallel", nargs="*", help="Delegate multiple tasks in parallel")
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Max parallel workers (default: 10; lower if MiniMax rate-limits)",
    )
    parser.add_argument(
        "--no-api-check",
        action="store_true",
        help="Skip pre-dispatch API verification (emergency override)",
    )
    parser.add_argument(
        "--worker",
        default=None,
        help="Named worker to use (e.g. 'kimi', 'minimax'). Must match a key in architecture.yaml workers section.",
    )

    args = parser.parse_args()

    global _active_worker
    _active_worker = args.worker

    if args.history:
        cmd_history(args)
    elif args.parallel is not None:
        # --parallel with explicit files, or glob from .rsi/tasks/
        task_files = args.parallel
        if not task_files:
            task_files = [str(f) for f in sorted(TASKS_DIR.glob("*.json"))]
        if not task_files:
            print("No task files found.", file=sys.stderr)
            sys.exit(1)
        results = delegate_parallel(task_files, max_workers=args.workers)
        print(f"\nParallel delegation complete: {len(results)} tasks")
        for r in results:
            status = r.get("status", "?")
            print(f"  {r.get('task_id', '?')}: {status}")
    elif args.task_file:
        task_path = Path(args.task_file)
        if not task_path.exists() or not task_path.is_file():
            print(f"ERROR: Not a file: {args.task_file}", file=sys.stderr)
            sys.exit(1)
        cmd_delegate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
