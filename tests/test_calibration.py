"""Tests for the calibration tracker — verifies hypothesis recording, validation, and scoring."""

import json
from pathlib import Path


def _setup_calibration(tmp_path):
    import scripts.calibration as c
    c.CALIBRATION_DIR = tmp_path
    c.HYPOTHESES_FILE = tmp_path / "hypotheses.jsonl"
    return c


def test_add_hypothesis(tmp_path):
    c = _setup_calibration(tmp_path)
    h = c.add_hypothesis("If cache TTL exceeds session, stale data served", task="TSK-001")
    assert h["id"] == "HYP-001"
    assert h["status"] == "open"
    assert h["task"] == "TSK-001"
    assert h["quality_score"] > 0


def test_sequential_ids(tmp_path):
    c = _setup_calibration(tmp_path)
    h1 = c.add_hypothesis("First hypothesis about cache invalidation")
    h2 = c.add_hypothesis("Second hypothesis about race conditions")
    assert h1["id"] == "HYP-001"
    assert h2["id"] == "HYP-002"


def test_resolve_hypothesis(tmp_path):
    c = _setup_calibration(tmp_path)
    c.add_hypothesis("Test hypothesis about error handling")
    result = c.resolve("HYP-001", "confirmed", "Reproduced in test")
    assert result is not None
    assert result["status"] == "confirmed"
    assert result["resolution_notes"] == "Reproduced in test"


def test_resolve_nonexistent(tmp_path):
    c = _setup_calibration(tmp_path)
    result = c.resolve("HYP-999", "confirmed")
    assert result is None


def test_list_open(tmp_path):
    c = _setup_calibration(tmp_path)
    c.add_hypothesis("Open one about memory leaks")
    c.add_hypothesis("Open two about connection pools")
    c.add_hypothesis("Will be closed — about timeout handling")
    c.resolve("HYP-003", "disproven")
    open_h = c.list_open()
    assert len(open_h) == 2


def test_calibration_score(tmp_path):
    c = _setup_calibration(tmp_path)
    c.add_hypothesis("Hypothesis A about buffer overflow")
    c.add_hypothesis("Hypothesis B about null pointer")
    c.add_hypothesis("Hypothesis C about thread safety")
    c.resolve("HYP-001", "confirmed")
    c.resolve("HYP-002", "disproven")
    score = c.calibration_score()
    assert score["total"] == 3
    assert score["open"] == 1
    assert score["confirmed"] == 1
    assert score["disproven"] == 1
    assert score["resolved"] == 2
    assert score["accuracy_pct"] == 50.0


def test_validate_good_hypothesis(tmp_path):
    c = _setup_calibration(tmp_path)
    result = c.validate_hypothesis(
        "If the database connection pool is exhausted, the upsert() call would timeout and raise ConnectionError"
    )
    assert result["valid"] is True
    assert result["score"] >= 60


def test_validate_vague_hypothesis(tmp_path):
    c = _setup_calibration(tmp_path)
    result = c.validate_hypothesis("it might break something")
    assert result["valid"] is False
    assert result["score"] < 40
    assert len(result["issues"]) > 0


def test_validate_empty_hypothesis(tmp_path):
    c = _setup_calibration(tmp_path)
    result = c.validate_hypothesis("")
    assert result["valid"] is False
    assert result["score"] == 0


def test_validate_short_hypothesis(tmp_path):
    c = _setup_calibration(tmp_path)
    result = c.validate_hypothesis("might fail")
    assert result["score"] < 60
