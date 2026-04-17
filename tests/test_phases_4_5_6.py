"""Tests for Phases 4-6: task DAG, worker trust, declarative rules engine."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Phase 4: Task DAG
# ---------------------------------------------------------------------------


def test_build_dag_no_deps():
    from scripts.delegate import _build_dag

    tasks = [
        {"id": "T1", "files_to_modify": ["a.py"]},
        {"id": "T2", "files_to_modify": ["b.py"]},
    ]
    dag = _build_dag(tasks)
    assert dag["T1"] == set()
    assert dag["T2"] == set()


def test_build_dag_explicit_depends_on():
    from scripts.delegate import _build_dag

    tasks = [
        {"id": "T1", "files_to_modify": ["a.py"]},
        {"id": "T2", "files_to_modify": ["b.py"], "depends_on": ["T1"]},
    ]
    dag = _build_dag(tasks)
    assert "T1" in dag["T2"]
    assert dag["T1"] == set()


def test_build_dag_implicit_file_overlap():
    from scripts.delegate import _build_dag

    tasks = [
        {"id": "T1", "files_to_modify": ["shared.py"]},
        {"id": "T2", "files_to_modify": ["shared.py"]},
    ]
    dag = _build_dag(tasks)
    # T2 should depend on T1 (earlier ID)
    assert "T1" in dag["T2"]


def test_topological_layers_independent():
    from scripts.delegate import _topological_layers

    dag = {"T1": set(), "T2": set(), "T3": set()}
    layers = _topological_layers(dag)
    # All independent — one layer
    assert len(layers) == 1
    assert len(layers[0]) == 3


def test_topological_layers_chain():
    from scripts.delegate import _topological_layers

    dag = {"T1": set(), "T2": {"T1"}, "T3": {"T2"}}
    layers = _topological_layers(dag)
    assert len(layers) == 3
    assert layers[0] == ["T1"]
    assert layers[1] == ["T2"]
    assert layers[2] == ["T3"]


def test_topological_layers_diamond():
    from scripts.delegate import _topological_layers

    dag = {"T1": set(), "T2": {"T1"}, "T3": {"T1"}, "T4": {"T2", "T3"}}
    layers = _topological_layers(dag)
    assert len(layers) == 3
    assert layers[0] == ["T1"]
    assert set(layers[1]) == {"T2", "T3"}
    assert layers[2] == ["T4"]


def test_detect_cycle_none():
    from scripts.delegate import _detect_cycle

    dag = {"T1": set(), "T2": {"T1"}}
    assert _detect_cycle(dag) is None


def test_detect_cycle_found():
    from scripts.delegate import _detect_cycle

    dag = {"T1": {"T2"}, "T2": {"T1"}}
    result = _detect_cycle(dag)
    assert result is not None


# ---------------------------------------------------------------------------
# Phase 5: Worker trust
# ---------------------------------------------------------------------------


def test_compute_trust_empty(tmp_path):
    import scripts.trust as t

    t.DELEGATIONS_LOG = tmp_path / "empty.jsonl"
    result = t.compute_trust()
    assert result["overall"]["total"] == 0
    assert result["overall"]["score"] == 0.0


def test_compute_trust_with_data(tmp_path):
    import scripts.trust as t

    log = tmp_path / "delegations.jsonl"
    events = [
        {"task_id": "TEST-001", "verdict": "ACCEPTED"},
        {"task_id": "TEST-002", "verdict": "ACCEPTED"},
        {"task_id": "TEST-003", "verdict": "REJECTED"},
        {"task_id": "IMPL-001", "verdict": "ACCEPTED"},
        {"task_id": "IMPL-002", "verdict": "REJECTED"},
    ]
    log.write_text("\n".join(json.dumps(e) for e in events))
    t.DELEGATIONS_LOG = log

    result = t.compute_trust()
    assert result["overall"]["total"] == 5
    assert result["overall"]["accepted"] == 3
    assert result["overall"]["score"] == 0.6


def test_should_auto_accept_insufficient_samples(tmp_path):
    import scripts.trust as t

    log = tmp_path / "delegations.jsonl"
    log.write_text(json.dumps({"task_id": "TEST-001", "verdict": "ACCEPTED"}))
    t.DELEGATIONS_LOG = log
    t.ARCHITECTURE_FILE = tmp_path / "nonexistent.yaml"

    ok, reason = t.should_auto_accept("test")
    assert not ok
    assert "Insufficient" in reason


def test_should_auto_accept_below_threshold(tmp_path):
    import scripts.trust as t

    log = tmp_path / "delegations.jsonl"
    events = [
        {"task_id": f"TEST-{i:03d}", "verdict": "ACCEPTED" if i < 4 else "REJECTED"}
        for i in range(10)
    ]
    log.write_text("\n".join(json.dumps(e) for e in events))
    t.DELEGATIONS_LOG = log
    t.ARCHITECTURE_FILE = tmp_path / "nonexistent.yaml"

    ok, reason = t.should_auto_accept("test")
    assert not ok  # 4/10 = 40%, below 85% threshold


# ---------------------------------------------------------------------------
# Phase 6: Rules engine
# ---------------------------------------------------------------------------


def test_rules_engine_loads():
    from scripts.rules_engine import RuleEngine

    engine = RuleEngine()
    assert engine is not None


def test_rules_engine_blocks_session_expired():
    from scripts.rules_engine import RuleEngine

    engine = RuleEngine()
    context = {
        "file": "test.py",
        "file_exists": True,
        "file_was_read": True,
        "session_expired": True,
        "role": "overlord",
        "sensitivity": "guarded",
        "minimax_key_set": False,
        "has_delegation": False,
        "has_override": False,
    }
    allowed, messages = engine.evaluate("pre_edit", context)
    assert not allowed
    assert any("Session expired" in m or "R01" in m for m in messages)


def test_rules_engine_blocks_unread_file():
    from scripts.rules_engine import RuleEngine

    engine = RuleEngine()
    context = {
        "file": "test.py",
        "file_exists": True,
        "file_was_read": False,
        "session_expired": False,
        "role": "overlord",
        "sensitivity": "guarded",
        "minimax_key_set": False,
        "has_delegation": False,
        "has_override": False,
    }
    allowed, messages = engine.evaluate("pre_edit", context)
    assert not allowed
    assert any("not read" in m.lower() or "R02" in m for m in messages)


def test_rules_engine_allows_clean_edit():
    from scripts.rules_engine import RuleEngine

    engine = RuleEngine()
    context = {
        "file": "test.py",
        "file_exists": True,
        "file_was_read": True,
        "session_expired": False,
        "role": "overlord",
        "sensitivity": "constitution",
        "minimax_key_set": False,
        "has_delegation": False,
        "has_override": False,
    }
    allowed, messages = engine.evaluate("pre_edit", context)
    assert allowed


def test_rules_engine_blocks_no_verify():
    from scripts.rules_engine import RuleEngine

    engine = RuleEngine()
    context = {"command": "git commit --no-verify -m 'skip'"}
    allowed, messages = engine.evaluate("pre_bash", context)
    assert not allowed
    assert any("no-verify" in m.lower() or "R05" in m for m in messages)


def test_rules_engine_allows_normal_bash():
    from scripts.rules_engine import RuleEngine

    engine = RuleEngine()
    context = {"command": "git status"}
    allowed, messages = engine.evaluate("pre_bash", context)
    assert allowed


def test_rules_engine_delegation_gate():
    from scripts.rules_engine import RuleEngine

    engine = RuleEngine()
    context = {
        "file": "src/api.py",
        "file_exists": True,
        "file_was_read": True,
        "session_expired": False,
        "role": "overlord",
        "sensitivity": "guarded",
        "minimax_key_set": True,
        "has_delegation": False,
        "has_override": False,
    }
    allowed, messages = engine.evaluate("pre_edit", context)
    assert not allowed
    assert any("Delegate" in m or "R04" in m for m in messages)


def test_rules_engine_delegation_gate_with_delegation():
    from scripts.rules_engine import RuleEngine

    engine = RuleEngine()
    context = {
        "file": "src/api.py",
        "file_exists": True,
        "file_was_read": True,
        "session_expired": False,
        "role": "overlord",
        "sensitivity": "guarded",
        "minimax_key_set": True,
        "has_delegation": True,
        "has_override": False,
    }
    allowed, messages = engine.evaluate("pre_edit", context)
    assert allowed


def test_condition_eval_in_operator():
    from scripts.rules_engine import _eval_condition

    ctx = {"sensitivity": "guarded"}
    assert _eval_condition("sensitivity in ('guarded', 'open')", ctx) is True
    ctx = {"sensitivity": "constitution"}
    assert _eval_condition("sensitivity in ('guarded', 'open')", ctx) is False
