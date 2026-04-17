"""Tests for the delegation enforcement gate — verifies that Claude cannot
edit guarded/open files directly when MINIMAX_API_KEY is set."""

import json
import sys
from datetime import UTC
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _setup_hooks(tmp_path):
    """Configure hooks module to use tmp directories."""
    import scripts.hooks as h

    h.PROJECT_ROOT = tmp_path
    h.MEMORY_ROOT = tmp_path / ".memory"
    h.STATE_FILE = tmp_path / ".memory" / ".preflight_state.json"
    h.SESSION_FILE = tmp_path / ".memory" / ".session_timestamp"
    h.FAIL_INDEX_FILE = tmp_path / ".memory" / "technical" / "FAIL-index.md"
    h.ACCEPTED_DIR = tmp_path / ".memory" / "reviews" / "accepted"
    h.OVERRIDES_DIR = tmp_path / ".rsi" / "overrides"

    # Create directories
    (tmp_path / ".memory" / "technical").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".memory" / "reviews" / "accepted").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".memory" / "reviews" / "pending").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".rsi" / "overrides").mkdir(parents=True, exist_ok=True)

    # Start a valid session
    h.SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    h.SESSION_FILE.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "ttl_hours": 24,
            }
        ),
        encoding="utf-8",
    )

    return h


def _record_read(h, tmp_path, filepath: str):
    """Record a file as read, using the same path format as _relative_path."""
    full = tmp_path / filepath
    rel = h._relative_path(str(full))
    h._record_file_read(rel)


def _create_test_file(tmp_path, filepath: str, content: str = "x = 1"):
    """Create a file on disk."""
    full = tmp_path / filepath
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


def _add_accepted_review(h, task_id: str, filepath: str):
    """Create an accepted review record that authorizes a file."""
    review_file = h.ACCEPTED_DIR / f"{task_id}.md"
    review_file.write_text(
        f"""# Review: {task_id}
**Status:** ACCEPTED

## Proposed Changes

### {filepath}
```
authorized content
```
""",
        encoding="utf-8",
    )


def test_gate_blocks_when_minimax_key_set(tmp_path, monkeypatch):
    """Editing guarded file without delegation trail = BLOCKED."""
    h = _setup_hooks(tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key-123")
    monkeypatch.setenv("RSI_ROLE", "overlord")

    # Create a guarded file (scripts/*.py matches guarded pattern)
    _create_test_file(tmp_path, "scripts/metrics.py")
    _record_read(h, tmp_path, "scripts/metrics.py")

    try:
        h.handle_pre_edit({"file_path": str(tmp_path / "scripts/metrics.py")})
        assert False, "Should have blocked"
    except SystemExit as e:
        assert e.code == 1


def test_gate_allows_with_delegation_trail(tmp_path, monkeypatch):
    """Editing guarded file WITH delegation trail = allowed."""
    h = _setup_hooks(tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key-123")
    monkeypatch.setenv("RSI_ROLE", "overlord")

    _create_test_file(tmp_path, "scripts/metrics.py")
    _record_read(h, tmp_path, "scripts/metrics.py")
    _add_accepted_review(h, "TASK-001", "scripts/metrics.py")

    # Should not raise
    h.handle_pre_edit({"file_path": str(tmp_path / "scripts/metrics.py")})


def test_gate_allows_constitution_files(tmp_path, monkeypatch):
    """Constitution files bypass delegation gate — overlord edits directly."""
    h = _setup_hooks(tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key-123")
    monkeypatch.setenv("RSI_ROLE", "overlord")

    _create_test_file(tmp_path, "CLAUDE.md")
    _record_read(h, tmp_path, "CLAUDE.md")

    # Should not raise — constitution files are overlord-only
    h.handle_pre_edit({"file_path": str(tmp_path / "CLAUDE.md")})


def test_gate_inactive_without_minimax_key(tmp_path, monkeypatch):
    """No MINIMAX_API_KEY = single-model mode, gate inactive."""
    h = _setup_hooks(tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setenv("RSI_ROLE", "overlord")

    _create_test_file(tmp_path, "scripts/metrics.py")
    _record_read(h, tmp_path, "scripts/metrics.py")

    # Should not raise — gate only active when MINIMAX_API_KEY set
    h.handle_pre_edit({"file_path": str(tmp_path / "scripts/metrics.py")})


def test_gate_allows_with_override(tmp_path, monkeypatch):
    """Override file bypasses delegation gate."""
    h = _setup_hooks(tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key-123")
    monkeypatch.setenv("RSI_ROLE", "overlord")

    _create_test_file(tmp_path, "scripts/metrics.py")
    _record_read(h, tmp_path, "scripts/metrics.py")

    # Create override
    h.create_override("scripts/metrics.py", "emergency hotfix", ttl_minutes=60)

    # Should not raise — override exists
    h.handle_pre_edit({"file_path": str(tmp_path / "scripts/metrics.py")})


def test_override_expires(tmp_path, monkeypatch):
    """Expired overrides don't bypass gate."""
    h = _setup_hooks(tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key-123")
    monkeypatch.setenv("RSI_ROLE", "overlord")

    _create_test_file(tmp_path, "scripts/metrics.py")
    _record_read(h, tmp_path, "scripts/metrics.py")

    # Create an expired override (TTL = 0 minutes)
    h.create_override("scripts/metrics.py", "already expired", ttl_minutes=0)

    try:
        h.handle_pre_edit({"file_path": str(tmp_path / "scripts/metrics.py")})
        assert False, "Should have blocked — override expired"
    except SystemExit as e:
        assert e.code == 1


def test_gate_blocks_open_files_too(tmp_path, monkeypatch):
    """Even open files require delegation trail when MINIMAX_API_KEY set."""
    h = _setup_hooks(tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key-123")
    monkeypatch.setenv("RSI_ROLE", "overlord")

    _create_test_file(tmp_path, "tests/test_something.py")
    _record_read(h, tmp_path, "tests/test_something.py")

    try:
        h.handle_pre_edit({"file_path": str(tmp_path / "tests/test_something.py")})
        assert False, "Should have blocked"
    except SystemExit as e:
        assert e.code == 1


def test_new_files_allowed(tmp_path, monkeypatch):
    """Writing new files (that don't exist yet) is allowed — no delegation needed."""
    h = _setup_hooks(tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key-123")
    monkeypatch.setenv("RSI_ROLE", "overlord")

    # File doesn't exist on disk — Write to create is allowed
    h.handle_pre_edit({"file_path": str(tmp_path / "scripts/new_module.py")})
