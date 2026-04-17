"""Tests for the delegation engine — validates task specs, worker prompts, review writing."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _make_task(tmp_path, task_id="TASK-001"):
    """Create a minimal valid task for testing."""
    return {
        "id": task_id,
        "description": "Add retry logic to HTTP adapter",
        "instruction": "Implement exponential backoff retry",
        "files_to_read": [],
        "files_to_modify": ["tests/test_retry.py"],
        "acceptance_criteria": ["Retries on 500 status"],
        "proof_wrong": "If server returns 200 with error body, retries won't trigger",
        "constraints": [],
    }


def test_validate_valid_task(tmp_path):
    from scripts.delegate import validate_task

    task = _make_task(tmp_path)
    issues = validate_task(task)
    # Only issue should be that files_to_read don't exist on disk
    real_issues = [
        i for i in issues if "not found" not in i.lower() and "already exists" not in i.lower()
    ]
    assert len(real_issues) == 0


def test_validate_missing_fields():
    from scripts.delegate import validate_task

    task = {"id": "TASK-BAD"}
    issues = validate_task(task)
    assert any("description" in i for i in issues)
    assert any("instruction" in i for i in issues)
    assert any("files_to_modify" in i for i in issues)


def test_validate_missing_proof_wrong():
    from scripts.delegate import validate_task

    task = {
        "id": "TASK-002",
        "description": "Test",
        "instruction": "Do thing",
        "files_to_modify": ["tests/foo.py"],
        "acceptance_criteria": ["works"],
        "proof_wrong": "",
    }
    issues = validate_task(task)
    assert any("proof_wrong" in i for i in issues)


def test_validate_constitution_file_blocked():
    from scripts.delegate import validate_task

    task = {
        "id": "TASK-003",
        "description": "Modify hooks",
        "instruction": "Change hooks",
        "files_to_modify": ["scripts/hooks.py"],  # constitution-level
        "acceptance_criteria": ["Done"],
        "proof_wrong": "If hooks break, enforcement fails",
    }
    issues = validate_task(task)
    assert any("constitution" in i.lower() or "blocked" in i.lower() for i in issues)


def test_build_worker_prompt():
    from scripts.delegate import build_worker_prompt

    task = {
        "id": "TASK-004",
        "description": "Add feature",
        "instruction": "Implement retry",
        "files_to_read": [],
        "files_to_modify": ["src/http.py"],
        "acceptance_criteria": ["Works"],
        "proof_wrong": "Might not handle timeouts",
    }
    prompt = build_worker_prompt(task)
    assert "TASK-004" in prompt
    assert "retry" in prompt.lower()


def test_write_review(tmp_path):
    import scripts.delegate as d

    # Redirect output dirs to tmp
    d.PENDING_DIR = tmp_path / "pending"
    d.REVIEWS_DIR = tmp_path
    d.PENDING_DIR.mkdir(parents=True)

    task = {
        "id": "TASK-005",
        "description": "Test review",
        "instruction": "test",
        "acceptance_criteria": ["done"],
    }
    result = {
        "changes": {"test.py": "x = 1"},
        "proof_wrong": "might fail",
        "notes": "ok",
        "tokens_used": 100,
        "latency_seconds": 2.5,
    }

    path = d.write_review(task, result)
    assert path.exists()
    content = path.read_text()
    assert "TASK-005" in content
    assert "PENDING REVIEW" in content
    assert "might fail" in content
