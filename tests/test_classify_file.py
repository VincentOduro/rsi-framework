"""Tests for file classification — verifies sensitivity levels from architecture.yaml."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_classify_constitution_files():
    from scripts.classify_file import classify_file

    assert classify_file("CLAUDE.md") == "constitution"
    assert classify_file("FRAMEWORK.md") == "constitution"
    assert classify_file("TOYOTA_PRINCIPLES.md") == "constitution"
    assert classify_file("scripts/hooks.py") == "constitution"
    assert classify_file("scripts/delegate.py") == "constitution"


def test_classify_guarded_files():
    from scripts.classify_file import classify_file

    assert classify_file("scripts/metrics.py") == "guarded"
    assert classify_file("scripts/ceremony.py") == "guarded"
    assert classify_file("scripts/self_verify.py") == "guarded"


def test_classify_open_files():
    from scripts.classify_file import classify_file

    assert classify_file("tests/test_framework.py") == "open"
    assert classify_file("tests/test_metrics.py") == "open"
    assert classify_file("docs/guide.md") == "open"


def test_classify_unknown_defaults_guarded():
    from scripts.classify_file import classify_file

    # Unknown paths default to guarded (safe default)
    assert classify_file("src/core/api.py") == "guarded"
    assert classify_file("some/random/file.py") == "guarded"


def test_worker_allowed():
    from scripts.classify_file import is_worker_allowed

    assert is_worker_allowed("tests/test_foo.py") is True
    assert is_worker_allowed("scripts/metrics.py") is True  # guarded = allowed but needs review
    assert is_worker_allowed("CLAUDE.md") is False  # constitution = blocked


def test_classify_multiple():
    from scripts.classify_file import classify_files

    result = classify_files(["CLAUDE.md", "tests/test_foo.py", "src/api.py"])
    assert result["CLAUDE.md"] == "constitution"
    assert result["tests/test_foo.py"] == "open"
    assert result["src/api.py"] == "guarded"


def test_rsi_directory_is_constitution():
    from scripts.classify_file import classify_file

    assert classify_file(".rsi/architecture.yaml") == "constitution"
    assert classify_file(".rsi/tasks/TASK-001.json") == "constitution"
