#!/usr/bin/env python3
"""
Claude Code hook handlers — poka-yoke (mistake-proofing) at the tool layer.

Toyota Principle 5: Jidoka — build quality in, stop on defects.
Toyota Principle 12: Genchi Genbutsu — go and see for yourself.

These hooks run BEFORE and AFTER Claude Code tool calls, enforcing:
  - Read before edit (Genchi Genbutsu)
  - FAIL-index awareness (learn from past failures)
  - Post-edit verification (Jidoka)
  - Session tracking (continuity)

Hook protocol:
  - Receives tool input as JSON on stdin
  - Outputs feedback text to stdout (shown to agent)
  - Exit 0 = allow, exit non-zero = block

Configured in .claude/settings.json
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("RSI_PROJECT_ROOT", Path(__file__).parent.parent.resolve()))
MEMORY_ROOT = PROJECT_ROOT / ".memory"
STATE_FILE = MEMORY_ROOT / ".preflight_state.json"
SESSION_FILE = MEMORY_ROOT / ".session_timestamp"
FAIL_INDEX_FILE = MEMORY_ROOT / "technical" / "FAIL-index.md"


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def _load_read_files() -> set[str]:
    """Load the set of files recorded as read in this session."""
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text())
        return set(data.get("read_files", []))
    except (json.JSONDecodeError, IOError):
        return set()


def _record_file_read(filepath: str) -> None:
    """Mark a file as read in the session state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            data = {"read_files": [], "edited_files": [], "sessions": []}
    else:
        data = {"read_files": [], "edited_files": [], "sessions": []}

    read_set = set(data.get("read_files", []))
    read_set.add(filepath)
    data["read_files"] = sorted(read_set)
    STATE_FILE.write_text(json.dumps(data, indent=2))


def _record_file_edited(filepath: str) -> None:
    """Mark a file as edited in the session state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            data = {"read_files": [], "edited_files": [], "sessions": []}
    else:
        data = {"read_files": [], "edited_files": [], "sessions": []}

    edited_set = set(data.get("edited_files", []))
    edited_set.add(filepath)
    data["edited_files"] = sorted(edited_set)
    STATE_FILE.write_text(json.dumps(data, indent=2))


def _relative_path(filepath: str) -> str:
    """Convert absolute path to project-relative."""
    try:
        return str(Path(filepath).resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return filepath


# ---------------------------------------------------------------------------
# FAIL-index integration
# ---------------------------------------------------------------------------

def _get_relevant_fail_entries(filepath: str) -> list[str]:
    """Check FAIL-index for entries relevant to the file being edited."""
    if not FAIL_INDEX_FILE.exists():
        return []

    content = FAIL_INDEX_FILE.read_text()
    filename = Path(filepath).name
    stem = Path(filepath).stem

    # Surface all FAIL entries — the agent should be aware of known failure modes
    entries = []
    for line in content.split("\n"):
        if line.strip().startswith("| FAIL-"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3:
                fail_id = parts[0]
                failure_mode = parts[1]
                rule = parts[2]
                entries.append(f"  {fail_id}: {failure_mode} -> {rule}")

    return entries


# ---------------------------------------------------------------------------
# Hook handlers
# ---------------------------------------------------------------------------

def handle_pre_read(tool_input: dict) -> None:
    """PreToolUse handler for Read tool — record that file was read."""
    filepath = tool_input.get("file_path", "")
    if filepath:
        rel = _relative_path(filepath)
        _record_file_read(rel)


def _is_session_expired() -> bool:
    """Check if the RSI session has expired (TTL-based)."""
    if not SESSION_FILE.exists():
        return True
    try:
        import json
        from datetime import datetime, timezone, timedelta
        data = json.loads(SESSION_FILE.read_text())
        last_session = datetime.fromisoformat(data["timestamp"])
        ttl_hours = int(data.get("ttl_hours", 24))
        now = datetime.now(timezone.utc)
        return (now - last_session) > timedelta(hours=ttl_hours)
    except (json.JSONDecodeError, IOError, KeyError, ValueError):
        return True


def _get_session_time_remaining() -> tuple[bool, int]:
    """Get session time remaining until expiry.

    Returns:
        (is_expiring_soon, minutes_remaining)
        is_expiring_soon: True if less than 1 hour remaining
        minutes_remaining: Minutes until expiry, or 0 if expired
    """
    if not SESSION_FILE.exists():
        return True, 0
    try:
        import json
        from datetime import datetime, timezone, timedelta
        data = json.loads(SESSION_FILE.read_text())
        last_session = datetime.fromisoformat(data["timestamp"])
        ttl_hours = int(data.get("ttl_hours", 24))
        now = datetime.now(timezone.utc)
        age = now - last_session
        remaining = timedelta(hours=ttl_hours) - age
        minutes_remaining = int(remaining.total_seconds() / 60)
        is_expiring_soon = minutes_remaining < 60 and minutes_remaining > 0
        return is_expiring_soon, max(0, minutes_remaining)
    except (json.JSONDecodeError, IOError, KeyError, ValueError):
        return True, 0


def handle_pre_edit(tool_input: dict) -> None:
    """PreToolUse handler for Edit/Write — enforce read-before-edit and session TTL."""
    filepath = tool_input.get("file_path", "")
    if not filepath:
        return

    # Check session TTL mid-session (not just at commit time)
    if _is_session_expired():
        print("[RSI] Session expired. Run 'python3 scripts/rsi.py init' to start a new session.")
        print("[RSI] Edits are blocked until session is active.")
        sys.exit(1)

    # Warn if session is expiring soon (within 1 hour)
    expiring_soon, minutes = _get_session_time_remaining()
    if expiring_soon:
        print(f"[RSI] Warning: Session expires in {minutes} minute(s). Run 'python3 scripts/rsi.py init' to extend.")

    rel = _relative_path(filepath)
    read_files = _load_read_files()

    # Check: was this file read in this session?
    if rel not in read_files:
        # Check if it's a new file (Write to non-existent path is OK)
        if Path(filepath).exists():
            print(f"[RSI] File '{rel}' has not been read in this session.")
            print(f"[RSI] Genchi Genbutsu: you must read a file before editing it.")
            print(f"[RSI] Read the file first, then retry the edit.")
            sys.exit(1)

    # Role-aware write permission check
    current_role = os.environ.get("RSI_ROLE", "overlord")
    if current_role == "worker":
        try:
            from scripts.classify_file import classify_file
            sensitivity = classify_file(rel)
            if sensitivity == "constitution":
                print(f"[RSI] BLOCKED: '{rel}' is constitution-level. Only overlord can modify.")
                sys.exit(1)
            if sensitivity == "guarded":
                print(f"[RSI] Note: '{rel}' is guarded. This change will require overlord review.")
        except ImportError:
            pass

    # Surface relevant FAIL-index entries
    fail_entries = _get_relevant_fail_entries(filepath)
    if fail_entries:
        print(f"[RSI] FAIL-index entries to consider while editing '{rel}':")
        for entry in fail_entries[:5]:
            print(entry)

    # Review queue gate — warn if pending reviews exist
    try:
        pending_dir = MEMORY_ROOT / "reviews" / "pending"
        if pending_dir.exists():
            pending_count = len(list(pending_dir.glob("*.md")))
            if pending_count > 0:
                print(f"[RSI] JIDOKA: {pending_count} pending review(s). Consider draining the queue.")
    except Exception:
        pass


def handle_post_edit(tool_input: dict) -> None:
    """PostToolUse handler for Edit/Write — record the edit and remind."""
    filepath = tool_input.get("file_path", "")
    if filepath:
        rel = _relative_path(filepath)
        _record_file_edited(rel)


def handle_pre_bash(tool_input: dict) -> None:
    """PreToolUse handler for Bash — track git commits."""
    command = tool_input.get("command", "")
    if "git commit" in command and "--no-verify" in command:
        print("[RSI] WARNING: --no-verify bypasses quality gates.")
        print("[RSI] This violates Jidoka (Principle 5): stop and fix quality first.")
        print("[RSI] Remove --no-verify and fix any failing checks.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def main():
    """Dispatch hook based on command-line argument.

    Usage:
        echo '{"tool_input": {...}}' | python3 scripts/hooks.py pre-edit
        echo '{"tool_input": {...}}' | python3 scripts/hooks.py post-edit
        echo '{"tool_input": {...}}' | python3 scripts/hooks.py pre-read
        echo '{"tool_input": {...}}' | python3 scripts/hooks.py pre-bash
    """
    if len(sys.argv) < 2:
        print("Usage: hooks.py <pre-edit|post-edit|pre-read|pre-bash>", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]

    # Read tool input from stdin
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            tool_input = data.get("tool_input", data)
        else:
            tool_input = {}
    except (json.JSONDecodeError, IOError):
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
        print(f"Unknown hook action: {action}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
