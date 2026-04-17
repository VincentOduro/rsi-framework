#!/usr/bin/env python3
"""
Claude Code hook handlers -- poka-yoke (mistake-proofing) at the tool layer.

Enforces: read-before-edit, delegation gate, session TTL, FAIL-index awareness.

Hook protocol: receives JSON on stdin, outputs text to stdout.
Exit 0 = allow, exit non-zero = block.

Performance: each hook invocation is a fresh Python process, so module-level
caches only live for one call. Disk reads are minimized by reading each file
at most once per invocation and reusing the result.
"""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("RSI_PROJECT_ROOT", Path(__file__).parent.parent.resolve()))
MEMORY_ROOT = PROJECT_ROOT / ".memory"
STATE_FILE = MEMORY_ROOT / ".preflight_state.json"
SESSION_FILE = MEMORY_ROOT / ".session_timestamp"
FAIL_INDEX_FILE = MEMORY_ROOT / "technical" / "FAIL-index.md"
ACCEPTED_DIR = MEMORY_ROOT / "reviews" / "accepted"
OVERRIDES_DIR = PROJECT_ROOT / ".rsi" / "overrides"


# ---------------------------------------------------------------------------
# Per-invocation cache -- each hook is a separate process, so this cache
# lives for exactly one tool call. Eliminates redundant reads within a
# single hook invocation (session file read twice, state file read twice, etc).
# ---------------------------------------------------------------------------

_cache: dict = {}


def _read_cached(path: Path) -> str | None:
    """Read a file, caching the result for this invocation."""
    key = str(path)
    if key not in _cache:
        if path.exists():
            try:
                _cache[key] = path.read_text()
            except OSError:
                _cache[key] = None
        else:
            _cache[key] = None
    return _cache[key]


def _invalidate_cache(path: Path) -> None:
    """Invalidate cache after writing to a file."""
    _cache.pop(str(path), None)


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def _load_read_files() -> set[str]:
    content = _read_cached(STATE_FILE)
    if not content:
        return set()
    try:
        return set(json.loads(content).get("read_files", []))
    except (json.JSONDecodeError, ValueError):
        return set()


def _load_state_data() -> dict:
    content = _read_cached(STATE_FILE)
    if not content:
        return {"read_files": [], "edited_files": [], "sessions": []}
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return {"read_files": [], "edited_files": [], "sessions": []}


def _save_state(data: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2))
    _invalidate_cache(STATE_FILE)


def _record_file_read(filepath: str) -> None:
    data = _load_state_data()
    read_set = set(data.get("read_files", []))
    read_set.add(filepath)
    data["read_files"] = sorted(read_set)
    _save_state(data)


def _record_file_edited(filepath: str) -> None:
    data = _load_state_data()
    edited_set = set(data.get("edited_files", []))
    edited_set.add(filepath)
    data["edited_files"] = sorted(edited_set)
    _save_state(data)


def _relative_path(filepath: str) -> str:
    try:
        return str(Path(filepath).resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return filepath


# ---------------------------------------------------------------------------
# Session management -- single read, multiple uses
# ---------------------------------------------------------------------------


def _load_session_data() -> dict | None:
    """Load session data once, return parsed dict or None."""
    content = _read_cached(SESSION_FILE)
    if not content:
        return None
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return None


def _is_session_expired() -> bool:
    data = _load_session_data()
    if not data:
        return True
    try:
        ts = datetime.fromisoformat(data["timestamp"])
        ttl = int(data.get("ttl_hours", 24))
        return (datetime.now(UTC) - ts) > timedelta(hours=ttl)
    except (KeyError, ValueError):
        return True


def _get_session_time_remaining() -> tuple[bool, int]:
    """Returns (is_expiring_soon, minutes_remaining). Uses cached session data."""
    data = _load_session_data()
    if not data:
        return True, 0
    try:
        ts = datetime.fromisoformat(data["timestamp"])
        ttl = int(data.get("ttl_hours", 24))
        remaining = timedelta(hours=ttl) - (datetime.now(UTC) - ts)
        minutes = int(remaining.total_seconds() / 60)
        return (0 < minutes < 60), max(0, minutes)
    except (KeyError, ValueError):
        return True, 0


# ---------------------------------------------------------------------------
# FAIL-index -- cached read, actual relevance filtering
# ---------------------------------------------------------------------------


def _get_relevant_fail_entries(filepath: str) -> list[str]:
    """Return FAIL-index entries relevant to this file.

    Relevance heuristic: entries whose failure mode or rule text mentions
    keywords related to the file's type (test, import, edit, commit, etc).
    Falls back to returning the 3 most universal entries if no keyword match.
    """
    content = _read_cached(FAIL_INDEX_FILE)
    if not content:
        return []

    filename = Path(filepath).name
    stem = Path(filepath).stem
    suffix = Path(filepath).suffix

    all_entries = []
    for line in content.split("\n"):
        if line.strip().startswith("| FAIL-"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3:
                all_entries.append(
                    {
                        "id": parts[0],
                        "mode": parts[1],
                        "rule": parts[2],
                        "text": f"  {parts[0]}: {parts[1]} -> {parts[2]}",
                    }
                )

    if not all_entries:
        return []

    # Keyword relevance matching
    relevant = []
    filepath_lower = filepath.lower()

    for entry in all_entries:
        mode_lower = entry["mode"].lower()
        rule_lower = entry["rule"].lower()

        # Always-relevant entries (editing, reading, verification)
        if any(kw in mode_lower for kw in ["edit", "read", "verif", "commit", "memory"]):
            relevant.append(entry["text"])
            continue

        # File-type-specific matching
        if (suffix == ".py" and any(kw in mode_lower for kw in ["import", "syntax", "test"])) or (
            "test" in filepath_lower and "test" in mode_lower
        ):
            relevant.append(entry["text"])

    # Return relevant entries, or top 3 universal ones if no matches
    if relevant:
        return relevant[:5]
    return [e["text"] for e in all_entries[:3]]


# ---------------------------------------------------------------------------
# Delegation trail -- cached reads
# ---------------------------------------------------------------------------


def _has_delegation_trail(filepath: str) -> bool:
    """Check if accepted reviews authorize this file."""
    if not ACCEPTED_DIR.exists():
        return False

    normalized = filepath.replace("\\", "/")
    for review_file in ACCEPTED_DIR.glob("*.md"):
        content = _read_cached(review_file)
        if content and normalized in content.replace("\\", "/"):
            return True
    return False


def _has_override(filepath: str) -> bool:
    """Check if a non-expired override exists for this file."""
    if not OVERRIDES_DIR.exists():
        return False

    filepath = filepath.replace("\\", "/")
    now = datetime.now(UTC)

    for of in OVERRIDES_DIR.glob("*.json"):
        content = _read_cached(of)
        if not content:
            continue
        try:
            data = json.loads(content)
            pattern = data.get("filepath", "").replace("\\", "/")
            if not pattern:
                continue
            # Match exact or wildcard
            if pattern != filepath and not (
                pattern.endswith("*") and filepath.startswith(pattern[:-1])
            ):
                continue
            # Check expiry
            created = datetime.fromisoformat(data.get("created", "2000-01-01"))
            ttl = int(data.get("ttl_minutes", 60))
            if (now - created) < timedelta(minutes=ttl):
                return True
        except (json.JSONDecodeError, ValueError):
            continue

    return False


def create_override(filepath: str, reason: str, ttl_minutes: int = 60) -> Path:
    """Create a temporary override allowing direct edit of a delegatable file."""
    OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = filepath.replace("/", "_").replace("\\", "_")
    override_file = OVERRIDES_DIR / f"{safe_name}.json"
    data = {
        "filepath": filepath,
        "reason": reason,
        "created": datetime.now(UTC).isoformat(),
        "ttl_minutes": ttl_minutes,
    }
    override_file.write_text(json.dumps(data, indent=2))
    return override_file


# ---------------------------------------------------------------------------
# Hook handlers
# ---------------------------------------------------------------------------


def handle_pre_read(tool_input: dict) -> None:
    filepath = tool_input.get("file_path", "")
    if filepath:
        _record_file_read(_relative_path(filepath))


def _build_edit_context(filepath: str) -> dict:
    """Build context dict for rule evaluation on pre_edit trigger."""
    rel = _relative_path(filepath)
    rel_normalized = rel.replace("\\", "/")

    # Classify file sensitivity
    sensitivity = "guarded"  # safe default
    try:
        from scripts.classify_file import classify_file

        sensitivity = classify_file(rel)
    except ImportError:
        pass

    return {
        "file": rel,
        "file_exists": Path(filepath).exists(),
        "file_was_read": rel in _load_read_files(),
        "session_expired": _is_session_expired(),
        "role": os.environ.get("RSI_ROLE", "overlord"),
        "sensitivity": sensitivity,
        "minimax_key_set": bool(os.environ.get("MINIMAX_API_KEY", "")),
        "has_delegation": _has_delegation_trail(rel_normalized),
        "has_override": _has_override(rel_normalized),
    }


def handle_pre_edit(tool_input: dict) -> None:
    filepath = tool_input.get("file_path", "")
    if not filepath:
        return

    # Build context once, evaluate rules against it
    context = _build_edit_context(filepath)
    rel = context["file"]

    # Try declarative rules engine first
    try:
        from scripts.rules_engine import get_engine

        engine = get_engine()
        allowed, messages = engine.evaluate("pre_edit", context)
        for msg in messages:
            print(msg)
        if not allowed:
            sys.exit(1)
    except ImportError:
        # Fallback: hardcoded rules (backward compatibility)
        if context["session_expired"]:
            print("[RSI] Session expired. Run 'python3 scripts/rsi.py init'.")
            sys.exit(1)
        if context["file_exists"] and not context["file_was_read"]:
            print(f"[RSI] BLOCKED: '{rel}' not read. Read it first.")
            sys.exit(1)
        if context["role"] == "worker" and context["sensitivity"] == "constitution":
            print(f"[RSI] BLOCKED: '{rel}' is constitution-level.")
            sys.exit(1)
        if (
            context["minimax_key_set"]
            and context["role"] != "worker"
            and context["sensitivity"] in ("guarded", "open")
            and context["file_exists"]
            and not context["has_delegation"]
            and not context["has_override"]
        ):
            print(f"[RSI] DELEGATION GATE BLOCKED: '{rel}'.")
            sys.exit(1)

    # Session expiry warning (non-blocking)
    expiring_soon, minutes = _get_session_time_remaining()
    if expiring_soon:
        print(f"[RSI] Session expires in {minutes}m.")

    # FAIL-index -- relevant entries only
    fail_entries = _get_relevant_fail_entries(filepath)
    if fail_entries:
        print(f"[RSI] FAIL-index for '{rel}':")
        for entry in fail_entries:
            print(entry)

    # Review queue warning
    pending_dir = MEMORY_ROOT / "reviews" / "pending"
    if pending_dir.exists():
        pending = list(pending_dir.glob("*.md"))
        if pending:
            print(f"[RSI] JIDOKA: {len(pending)} pending review(s).")


def handle_post_edit(tool_input: dict) -> None:
    filepath = tool_input.get("file_path", "")
    if filepath:
        _record_file_edited(_relative_path(filepath))


def handle_pre_bash(tool_input: dict) -> None:
    command = tool_input.get("command", "")
    context = {"command": command}

    try:
        from scripts.rules_engine import get_engine

        engine = get_engine()
        allowed, messages = engine.evaluate("pre_bash", context)
        for msg in messages:
            print(msg)
        if not allowed:
            sys.exit(1)
    except ImportError:
        # Fallback
        if "git commit" in command and "--no-verify" in command:
            print("[RSI] BLOCKED: --no-verify bypasses quality gates.")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print("Usage: hooks.py <pre-edit|post-edit|pre-read|pre-bash>", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]

    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            tool_input = data.get("tool_input", data)
        else:
            tool_input = {}
    except (OSError, json.JSONDecodeError):
        tool_input = {}

    handlers = {
        "pre-edit": handle_pre_edit,
        "post-edit": handle_post_edit,
        "pre-read": handle_pre_read,
        "pre-bash": handle_pre_bash,
    }

    handler = handlers.get(action)
    if handler:
        handler(tool_input)
    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
