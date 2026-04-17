"""Tests for the hook handlers — verifies tool-layer enforcement."""

import json
from pathlib import Path


def _setup_hooks(tmp_path):
    import scripts.hooks as h
    from datetime import datetime, timezone
    h.PROJECT_ROOT = tmp_path
    h.MEMORY_ROOT = tmp_path / ".memory"
    h.STATE_FILE = tmp_path / ".memory" / ".preflight_state.json"
    h.SESSION_FILE = tmp_path / ".memory" / ".session_timestamp"
    h.FAIL_INDEX_FILE = tmp_path / ".memory" / "technical" / "FAIL-index.md"
    h.ACCEPTED_DIR = tmp_path / ".memory" / "reviews" / "accepted"
    h.OVERRIDES_DIR = tmp_path / ".rsi" / "overrides"
    (tmp_path / ".memory").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".memory" / "technical").mkdir(parents=True, exist_ok=True)
    # Create valid session so TTL check passes
    h.SESSION_FILE.write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ttl_hours": 24,
    }))
    # Clear per-invocation cache
    h._cache.clear()
    return h


def test_record_file_read(tmp_path):
    h = _setup_hooks(tmp_path)
    h._record_file_read("src/main.py")
    read_files = h._load_read_files()
    assert "src/main.py" in read_files


def test_record_file_edited(tmp_path):
    h = _setup_hooks(tmp_path)
    h._record_file_edited("src/main.py")
    state = json.loads(h.STATE_FILE.read_text())
    assert "src/main.py" in state["edited_files"]


def test_pre_edit_blocks_unread_file(tmp_path):
    h = _setup_hooks(tmp_path)
    # Create a file that exists but hasn't been read
    src = tmp_path / "src" / "main.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x = 1")

    import sys
    try:
        h.handle_pre_edit({"file_path": str(src)})
        # If we get here on a file that exists and wasn't read, something's wrong
        # But handle_pre_edit calls sys.exit(1), so we catch SystemExit
        assert False, "Should have blocked"
    except SystemExit as e:
        assert e.code == 1


def test_pre_edit_allows_read_file(tmp_path, monkeypatch):
    h = _setup_hooks(tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    src = tmp_path / "src" / "main.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x = 1")

    # Record the file as read first
    rel = str(src.relative_to(tmp_path))
    h._record_file_read(rel)
    h._cache.clear()  # Re-read state after recording

    # Should not raise
    h.handle_pre_edit({"file_path": str(src)})


def test_pre_edit_allows_new_file(tmp_path):
    h = _setup_hooks(tmp_path)
    new_file = tmp_path / "src" / "new_module.py"
    # File doesn't exist — Write to new file should be allowed
    h.handle_pre_edit({"file_path": str(new_file)})


def test_fail_index_entries(tmp_path):
    h = _setup_hooks(tmp_path)
    fail_index = h.FAIL_INDEX_FILE
    fail_index.write_text("""# FAIL-index

| ID | Failure Mode | Preventive Rule | Times Cited | Last Cited |
|---|---|---|---|---|
| FAIL-001 | Editing from memory | Read file before editing | 3 | 2026-04-15 |
| FAIL-002 | Unguarded data access | Check .data before indexing | 1 | 2026-04-14 |
""")
    entries = h._get_relevant_fail_entries("src/main.py")
    # FAIL-001 matches (contains "edit"), FAIL-002 doesn't match any relevance keywords
    assert len(entries) >= 1
    assert "FAIL-001" in entries[0]


def test_pre_bash_blocks_no_verify(tmp_path):
    h = _setup_hooks(tmp_path)
    import sys
    try:
        h.handle_pre_bash({"command": "git commit --no-verify -m 'skip'"})
        assert False, "Should have blocked"
    except SystemExit as e:
        assert e.code == 1


def test_pre_bash_allows_normal_commit(tmp_path):
    h = _setup_hooks(tmp_path)
    # Should not raise
    h.handle_pre_bash({"command": "git commit -m 'normal commit'"})
