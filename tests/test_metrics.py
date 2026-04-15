"""Tests for the metrics engine — verifies event recording, querying, and computations."""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch


def _setup_metrics(tmp_path):
    """Set up metrics module with a temp directory."""
    import scripts.metrics as m
    m.METRICS_DIR = tmp_path
    m.EVENTS_FILE = tmp_path / "events.jsonl"
    return m


def test_record_event(tmp_path):
    m = _setup_metrics(tmp_path)
    event = m.record("test_event", key="value")
    assert event["type"] == "test_event"
    assert event["key"] == "value"
    assert "ts" in event
    assert m.EVENTS_FILE.exists()


def test_record_task_lifecycle(tmp_path):
    m = _setup_metrics(tmp_path)
    m.record_task_start("TSK-001", "round-001")
    m.record_task_complete("TSK-001", "round-001", first_pass=True)
    events = m.load_events()
    assert len(events) == 2
    assert events[0]["type"] == "task_start"
    assert events[1]["type"] == "task_complete"
    assert events[1]["first_pass"] is True


def test_load_events_filtered(tmp_path):
    m = _setup_metrics(tmp_path)
    m.record("task_start", task="a")
    m.record("verify_result", passed=True)
    m.record("task_start", task="b")
    starts = m.load_events("task_start")
    assert len(starts) == 2
    verifies = m.load_events("verify_result")
    assert len(verifies) == 1


def test_first_pass_yield(tmp_path):
    m = _setup_metrics(tmp_path)
    m.record_verify_result(passed=True, attempt=1)
    m.record_verify_result(passed=True, attempt=1)
    m.record_verify_result(passed=False, attempt=1)
    m.record_verify_result(passed=True, attempt=2)  # retry, not first attempt
    result = m.first_pass_yield(days=30)
    assert result["total"] == 3  # only attempt=1
    assert result["passed"] == 2
    assert result["yield_pct"] == 66.7


def test_defect_rate(tmp_path):
    m = _setup_metrics(tmp_path)
    m.record_task_complete("t1")
    m.record_task_complete("t2")
    m.record_defect("t1", "HIGH")
    result = m.defect_rate(days=30)
    assert result["tasks_completed"] == 2
    assert result["defects"] == 1
    assert result["rate"] == 0.5


def test_ceremony_stats(tmp_path):
    m = _setup_metrics(tmp_path)
    m.record_ceremony("standard", 15.0)
    m.record_ceremony("minimal", 5.0)
    m.record_ceremony("standard", 20.0)
    result = m.ceremony_stats(days=30)
    assert result["count"] == 3
    assert result["total_minutes"] == 40.0
    assert "standard" in result["by_level"]
    assert result["by_level"]["standard"]["count"] == 2


def test_signal_ratio(tmp_path):
    m = _setup_metrics(tmp_path)
    m.record_finding_outcome("f1", True)
    m.record_finding_outcome("f2", False)
    m.record_finding_outcome("f3", True)
    m.record_finding_outcome("f4", False)
    result = m.signal_ratio(days=30)
    assert result["total"] == 4
    assert result["actioned"] == 2
    assert result["ratio_pct"] == 50.0


def test_summary(tmp_path):
    m = _setup_metrics(tmp_path)
    m.record_task_complete("t1", first_pass=True)
    result = m.summary(days=7)
    assert "tasks_completed" in result
    assert "first_pass_yield" in result
    assert "defect_rate" in result


def test_empty_metrics(tmp_path):
    m = _setup_metrics(tmp_path)
    assert m.load_events() == []
    assert m.first_pass_yield()["total"] == 0
    assert m.defect_rate()["rate"] == 0.0
    assert m.ceremony_stats()["count"] == 0
