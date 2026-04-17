"""Tests for the review queue — verifies Jidoka gating and review lifecycle."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _setup_queue(tmp_path):
    """Set up review queue with tmp directories."""
    import scripts.review_queue as rq

    rq.REVIEWS_DIR = tmp_path / "reviews"
    rq.PENDING_DIR = rq.REVIEWS_DIR / "pending"
    rq.ACCEPTED_DIR = rq.REVIEWS_DIR / "accepted"
    rq.REJECTED_DIR = rq.REVIEWS_DIR / "rejected"
    rq.DELEGATIONS_LOG = tmp_path / "metrics" / "delegations.jsonl"
    rq._ensure_dirs()
    return rq


def _add_pending(rq, task_id: str, content: str = ""):
    """Add a pending review file."""
    review = rq.PENDING_DIR / f"{task_id}.md"
    if not content:
        content = f"# Review: {task_id}\n**Task:** Test task\n**Status:** PENDING REVIEW\n"
    review.write_text(content, encoding="utf-8")
    return review


def test_empty_queue(tmp_path):
    rq = _setup_queue(tmp_path)
    assert len(rq._pending_reviews()) == 0


def test_pending_reviews(tmp_path):
    rq = _setup_queue(tmp_path)
    _add_pending(rq, "TASK-001")
    _add_pending(rq, "TASK-002")
    assert len(rq._pending_reviews()) == 2


def test_gate_blocks_on_pending(tmp_path):
    rq = _setup_queue(tmp_path)
    _add_pending(rq, "TASK-001")
    try:
        rq.cmd_gate(None)
        assert False, "Gate should exit with code 1"
    except SystemExit as e:
        assert e.code == 1


def test_gate_clear_when_empty(tmp_path):
    rq = _setup_queue(tmp_path)
    try:
        rq.cmd_gate(None)
        assert False, "Gate should exit with code 0"
    except SystemExit as e:
        assert e.code == 0


def test_accept_moves_file(tmp_path):
    rq = _setup_queue(tmp_path)
    _add_pending(
        rq, "TASK-010", "# Review: TASK-010\n**Task:** Stuff\n**Status:** PENDING REVIEW\n"
    )

    class FakeArgs:
        task_id = "TASK-010"
        apply = False

    rq.cmd_accept(FakeArgs())

    assert not (rq.PENDING_DIR / "TASK-010.md").exists()
    assert (rq.ACCEPTED_DIR / "TASK-010.md").exists()
    content = (rq.ACCEPTED_DIR / "TASK-010.md").read_text(encoding="utf-8")
    assert "ACCEPTED" in content


def test_reject_moves_file(tmp_path):
    rq = _setup_queue(tmp_path)
    _add_pending(rq, "TASK-020")

    class FakeArgs:
        task_id = "TASK-020"
        reason = "Missing edge case"

    rq.cmd_reject(FakeArgs())

    assert not (rq.PENDING_DIR / "TASK-020.md").exists()
    assert (rq.REJECTED_DIR / "TASK-020.md").exists()
    content = (rq.REJECTED_DIR / "TASK-020.md").read_text(encoding="utf-8")
    assert "REJECTED" in content
    assert "Missing edge case" in content


def test_accept_nonexistent_fails(tmp_path):
    rq = _setup_queue(tmp_path)

    class FakeArgs:
        task_id = "TASK-999"
        apply = False

    try:
        rq.cmd_accept(FakeArgs())
        assert False, "Should fail"
    except SystemExit as e:
        assert e.code == 1
