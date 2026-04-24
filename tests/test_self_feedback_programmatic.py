"""Tests for U2 — Module B --findings-file programmatic mode.

Verifies that _load_findings_file:
- accepts both JSON and YAML by extension
- applies auto_findings.keep and auto_findings.confirm_all correctly
- shapes manual findings / optimizations / improvements for log_feedback_to_file
- raises a clear RuntimeError when PyYAML is absent but the file is YAML
- tolerates missing optional keys
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_load_json_findings_file(tmp_path, monkeypatch):
    import scripts.self_feedback as sf

    # Stub review_code so the test doesn't need files_to_review on disk
    monkeypatch.setattr(sf, "review_code", lambda files: [])

    payload = {
        "task": "Fix something",
        "manual_findings": [
            {"description": "edge case not covered"},
            {"description": "potential race condition"},
        ],
        "optimizations": [
            {"description": "cache the lookup", "impact": "avoid n+1"},
        ],
        "improvements": [
            {
                "description": "extract helper",
                "is_pattern_candidate": True,
                "applies_to": "src/foo.py",
            }
        ],
    }
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    findings, opts, imps, task = sf._load_findings_file(str(path), [])
    assert task == "Fix something"
    assert len(findings) == 2
    assert findings[0]["description"] == "edge case not covered"
    assert findings[0]["confirmed"] is False
    assert len(opts) == 1
    assert opts[0]["impact"] == "avoid n+1"
    assert len(imps) == 1
    assert imps[0]["is_pattern_candidate"] is True
    assert imps[0]["applies_to"] == "src/foo.py"


def test_load_findings_auto_keep_false_drops_auto_findings(tmp_path, monkeypatch):
    import scripts.self_feedback as sf

    # review_code returns something; keep=false should discard
    monkeypatch.setattr(
        sf, "review_code",
        lambda files: [{"description": "auto-found", "confirmed": False, "file": "x.py", "line": 1}],
    )
    payload = {
        "auto_findings": {"keep": False},
        "manual_findings": [{"description": "manual only"}],
    }
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    findings, _, _, _ = sf._load_findings_file(str(path), [])
    assert len(findings) == 1
    assert findings[0]["description"] == "manual only"


def test_load_findings_confirm_all_flips_auto_confirmed(tmp_path, monkeypatch):
    import scripts.self_feedback as sf

    monkeypatch.setattr(
        sf, "review_code",
        lambda files: [
            {"description": "a1", "confirmed": False, "file": "x.py", "line": 1},
            {"description": "a2", "confirmed": False, "file": "y.py", "line": 2},
        ],
    )
    payload = {"auto_findings": {"confirm_all": True}, "manual_findings": []}
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    findings, _, _, _ = sf._load_findings_file(str(path), [])
    assert len(findings) == 2
    assert all(f["confirmed"] for f in findings)


def test_load_findings_empty_file_handled(tmp_path, monkeypatch):
    """An empty-ish file (only `{}`) loads with safe defaults — no KeyError."""
    import scripts.self_feedback as sf

    monkeypatch.setattr(sf, "review_code", lambda files: [])
    path = tmp_path / "findings.json"
    path.write_text("{}", encoding="utf-8")

    findings, opts, imps, task = sf._load_findings_file(str(path), [])
    assert findings == []
    assert opts == []
    assert imps == []
    assert task is None


def test_yaml_file_raises_clear_error_when_pyyaml_missing(tmp_path, monkeypatch):
    """If PyYAML isn't importable, a YAML findings file raises a clear hint."""
    import builtins

    import scripts.self_feedback as sf

    monkeypatch.setattr(sf, "review_code", lambda files: [])
    original_import = builtins.__import__

    def _no_yaml(name, *a, **kw):
        if name == "yaml":
            raise ImportError("mocked missing yaml")
        return original_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _no_yaml)

    path = tmp_path / "findings.yaml"
    path.write_text("task: x\nmanual_findings: []\n", encoding="utf-8")

    import pytest

    with pytest.raises(RuntimeError, match="PyYAML"):
        sf._load_findings_file(str(path), [])


def test_missing_improvement_keys_default_safely(tmp_path, monkeypatch):
    import scripts.self_feedback as sf

    monkeypatch.setattr(sf, "review_code", lambda files: [])
    payload = {
        "manual_findings": [],
        "improvements": [
            {"description": "sparse entry"},  # no is_pattern_candidate, no applies_to
        ],
    }
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    _, _, imps, _ = sf._load_findings_file(str(path), [])
    assert len(imps) == 1
    assert imps[0]["is_pattern_candidate"] is False
    assert imps[0]["applies_to"] == ""
