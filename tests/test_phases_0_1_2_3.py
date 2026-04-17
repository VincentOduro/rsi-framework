"""Tests for Phases 0-3: bug fixes, quality ratchet, session brief, parallel delegation."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Phase 0a: Result storage (no double API call)
# ---------------------------------------------------------------------------


def test_save_and_load_result(tmp_path):
    import scripts.delegate as d

    d.RESULTS_DIR = tmp_path / "results"
    d.RESULTS_DIR.mkdir()

    result = {"changes": {"test.py": "x = 1"}, "proof_wrong": "test", "tokens_used": 100}
    d.save_result("TASK-001", result)

    loaded = d.load_result("TASK-001")
    assert loaded is not None
    assert loaded["changes"]["test.py"] == "x = 1"
    assert loaded["proof_wrong"] == "test"


def test_load_result_nonexistent(tmp_path):
    import scripts.delegate as d

    d.RESULTS_DIR = tmp_path / "results"
    d.RESULTS_DIR.mkdir()

    assert d.load_result("TASK-999") is None


def test_write_review_stores_result(tmp_path):
    import scripts.delegate as d

    d.PENDING_DIR = tmp_path / "pending"
    d.RESULTS_DIR = tmp_path / "results"
    d.REVIEWS_DIR = tmp_path
    d.PENDING_DIR.mkdir(parents=True)
    d.RESULTS_DIR.mkdir(parents=True)

    task = {"id": "TASK-010", "description": "test"}
    result = {"changes": {"a.py": "code"}, "proof_wrong": "hyp", "notes": "ok", "tokens_used": 50}
    d.write_review(task, result)

    # Review file exists
    assert (d.PENDING_DIR / "TASK-010.md").exists()
    # Result JSON also stored
    stored = d.load_result("TASK-010")
    assert stored is not None
    assert stored["changes"]["a.py"] == "code"


# ---------------------------------------------------------------------------
# Phase 0b: File size validation
# ---------------------------------------------------------------------------


def test_validate_large_file_warning(tmp_path):
    import scripts.delegate as d

    old_root = d.PROJECT_ROOT
    d.PROJECT_ROOT = tmp_path

    # Create a large file
    large_file = tmp_path / "big.py"
    large_file.write_text("\n".join([f"line_{i} = {i}" for i in range(600)]))

    task = {
        "id": "TASK-BIG",
        "description": "modify big file",
        "instruction": "change it",
        "files_to_modify": ["big.py"],
        "acceptance_criteria": ["done"],
        "proof_wrong": "might truncate",
    }
    issues = d.validate_task(task)
    assert any("500" in i or "truncat" in i.lower() or "WARNING" in i for i in issues)

    d.PROJECT_ROOT = old_root


# ---------------------------------------------------------------------------
# Phase 0c: self_verify relative import handling
# ---------------------------------------------------------------------------


def test_python_checker_sanity_handles_import_error():
    """PythonChecker.check_sanity should not fail on relative import errors."""
    import tempfile

    from scripts.self_verify import PythonChecker

    checker = PythonChecker()

    # Create a file that uses a relative import (will fail to import standalone)
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, dir=str(PROJECT_ROOT)
    ) as f:
        f.write("from .nonexistent_sibling import something\nx = 1\n")
        f.flush()
        temp_path = Path(f.name)

    try:
        ok, err = checker.check_sanity(temp_path)
        # Should pass (relative import error is not a real bug)
        assert ok, f"Should pass on relative import error, got: {err}"
    finally:
        temp_path.unlink()


# ---------------------------------------------------------------------------
# Phase 2: Session brief
# ---------------------------------------------------------------------------


def test_session_brief_generates():
    from scripts.session_brief import generate_brief

    brief = generate_brief()
    assert "SESSION BRIEF" in brief
    assert "=" in brief


def test_session_brief_handles_empty_memory(tmp_path):
    import scripts.session_brief as sb

    old_root = sb.MEMORY_ROOT
    sb.MEMORY_ROOT = tmp_path / ".memory"
    sb.MEMORY_ROOT.mkdir()

    brief = sb.generate_brief()
    assert "SESSION BRIEF" in brief
    # Should not crash on missing directories
    assert "(none)" in brief or "No" in brief

    sb.MEMORY_ROOT = old_root


# ---------------------------------------------------------------------------
# Phase 3: Parallel delegation grouping
# ---------------------------------------------------------------------------


def test_group_by_file_overlap_independent():
    from scripts.delegate import _group_by_file_overlap

    tasks = [
        {"id": "T1", "files_to_modify": ["a.py"]},
        {"id": "T2", "files_to_modify": ["b.py"]},
        {"id": "T3", "files_to_modify": ["c.py"]},
    ]
    groups = _group_by_file_overlap(tasks)
    # All independent — 3 groups
    assert len(groups) == 3


def test_group_by_file_overlap_shared():
    from scripts.delegate import _group_by_file_overlap

    tasks = [
        {"id": "T1", "files_to_modify": ["a.py", "shared.py"]},
        {"id": "T2", "files_to_modify": ["shared.py", "b.py"]},
        {"id": "T3", "files_to_modify": ["c.py"]},
    ]
    groups = _group_by_file_overlap(tasks)
    # T1 and T2 overlap on shared.py — same group. T3 is independent.
    assert len(groups) == 2


def test_group_by_file_overlap_all_overlap():
    from scripts.delegate import _group_by_file_overlap

    tasks = [
        {"id": "T1", "files_to_modify": ["common.py"]},
        {"id": "T2", "files_to_modify": ["common.py"]},
        {"id": "T3", "files_to_modify": ["common.py"]},
    ]
    groups = _group_by_file_overlap(tasks)
    # All overlap — 1 group
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_group_by_file_overlap_empty():
    from scripts.delegate import _group_by_file_overlap

    assert _group_by_file_overlap([]) == []


def test_parse_file_spec_plain():
    from scripts.delegate import _parse_file_spec

    path, start, end = _parse_file_spec("src/main.py")
    assert path == "src/main.py"
    assert start is None
    assert end is None


def test_parse_file_spec_range():
    from scripts.delegate import _parse_file_spec

    path, start, end = _parse_file_spec("src/main.py:100-200")
    assert path == "src/main.py"
    assert start == 100
    assert end == 200


def test_parse_file_spec_start_only():
    from scripts.delegate import _parse_file_spec

    path, start, end = _parse_file_spec("src/main.py:50")
    assert path == "src/main.py"
    assert start == 50
    assert end is None
