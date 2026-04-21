"""End-to-end tests for scripts/api_check.py via subprocess CLI."""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
API_CHECK = PROJECT_ROOT / "scripts" / "api_check.py"


def _run(spec_path, *extra_args):
    return subprocess.run(
        [sys.executable, str(API_CHECK), str(spec_path), *extra_args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _write_spec(tmp_path, spec):
    path = tmp_path / (spec.get("id", "TEST") + ".json")
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_clean_docs_spec_passes(tmp_path):
    """"A minimal code task with empty files should pass API check."""
    spec = {
        "id": "TASK-CLEAN",
        "task_type": "code",
        "instruction": "Update the README with new metrics.",
        "files_to_read": [],
        "files_to_modify": [],
    }
    path = _write_spec(tmp_path, spec)
    result = _run(path)
    assert result.returncode == 0, result.stderr
    assert "all 0 reference" in result.stdout


def test_hallucinated_method_fails(tmp_path):
    """A reference to a non-existent method should fail with returncode 1."""
    spec = {
        "id": "TASK-HALLUC",
        "task_type": "code",
        "files_to_read": ["scripts/shape.py"],
        "files_to_modify": ["scripts/shape.py"],
        "instruction": "Call shape_file.totally_fake_method(arg) here.",
    }
    path = _write_spec(tmp_path, spec)
    result = _run(path)
    assert result.returncode == 1, result.stderr
    assert "totally_fake_method" in result.stdout


def test_research_type_skips(tmp_path):
    """A research task type should skip API check and return 0."""
    spec = {
        "id": "TASK-RESEARCH",
        "task_type": "research",
        "instruction": "Investigate foo.bar() behavior.",
        "files_to_read": [],
        "files_to_modify": [],
    }
    path = _write_spec(tmp_path, spec)
    result = _run(path)
    assert result.returncode == 0, result.stderr
    assert "skipped" in result.stdout


def test_audit_type_skips(tmp_path):
    """An audit task type should skip API check and return 0."""
    spec = {
        "id": "TASK-AUDIT",
        "task_type": "audit",
        "instruction": "Review the code for foo.bar() calls.",
        "files_to_read": [],
        "files_to_modify": [],
    }
    path = _write_spec(tmp_path, spec)
    result = _run(path)
    assert result.returncode == 0, result.stderr
    assert "skipped" in result.stdout


def test_builtin_attrs_suppressed(tmp_path):
    """Builtin attrs like get/keys/append should be suppressed and not flag errors."""
    spec = {
        "id": "TASK-BUILTIN",
        "task_type": "code",
        "files_to_read": ["scripts/shape.py"],
        "instruction": 'task.get("x") and environ.get("Y") and data.keys() and items.append(z)',
        "files_to_modify": [],
    }
    path = _write_spec(tmp_path, spec)
    result = _run(path)
    assert result.returncode == 0, result.stderr


def test_stdlib_prefixes_suppressed(tmp_path):
    """Stdlib calls like os.path.join and json.loads should be suppressed."""
    spec = {
        "id": "TASK-STDLIB",
        "task_type": "code",
        "files_to_read": ["scripts/shape.py"],
        "instruction": "os.path.join(a, b) and json.loads(s) and sys.exit(1)",
        "files_to_modify": [],
    }
    path = _write_spec(tmp_path, spec)
    result = _run(path)
    assert result.returncode == 0, result.stderr


def test_malformed_spec_fails(tmp_path):
    """Malformed JSON should cause returncode 2."""
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not valid json", encoding="utf-8")
    result = _run(bad_path)
    assert result.returncode == 2, result.stderr



def test_missing_spec_fails(tmp_path):
    """A nonexistent spec path should cause returncode 2."""
    missing = tmp_path / "does_not_exist.json"
    result = _run(missing)
    assert result.returncode == 2, result.stderr


def test_line_range_file_spec_handled(tmp_path):
    """Line range syntax should be stripped and API check still works."""
    spec = {
        "id": "TASK-RANGE",
        "task_type": "code",
        "files_to_read": ["scripts/shape.py:1-50"],
        "instruction": "shape_file.other_thing()",
        "files_to_modify": [],
    }
    path = _write_spec(tmp_path, spec)
    result = _run(path)
    assert result.returncode == 1, result.stderr



def test_json_output_mode(tmp_path):
    """The --json flag should produce machine-readable output with expected keys."""
    spec = {
        "id": "TASK-JSON",
        "task_type": "code",
        "instruction": "Update the README with new metrics.",
        "files_to_read": [],
        "files_to_modify": [],
    }
    path = _write_spec(tmp_path, spec)
    result = _run(path, "--json")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "refs_checked" in data
    assert "problems" in data
