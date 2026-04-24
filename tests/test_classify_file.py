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


# U5 regression — inline comments on pattern lines must be stripped before
# fnmatch compilation. Without the fix, a pattern like
#   - "SPEC_AMENDMENTS.md"  # amendments tracking
# becomes `SPEC_AMENDMENTS.md"  # amendments tracking`, never matches, and
# the file silently falls through to DEFAULT_SENSITIVITY.


def test_inline_comments_stripped_from_patterns(tmp_path, monkeypatch):
    import scripts.classify_file as cf

    arch = tmp_path / "architecture.yaml"
    arch.write_text(
        'file_sensitivity:\n'
        '  constitution:\n'
        '    description: "test tier"\n'
        '    patterns:\n'
        '      - "SPEC_AMENDMENTS.md"  # amendments tracking\n'
        '      - "docs/design/**"   # spec documents\n'
        '  guarded:\n'
        '    description: "guarded tier"\n'
        '    patterns:\n'
        '      - "scripts/*.py"\n'
        '  open:\n'
        '    description: "open"\n'
        '    patterns:\n'
        '      - "tests/**"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cf, "ARCHITECTURE_FILE", arch)
    monkeypatch.setattr(cf, "_architecture_cache", None)

    assert cf.classify_file("SPEC_AMENDMENTS.md") == "constitution"
    assert cf.classify_file("docs/design/match_score.md") == "constitution"
    # Guarded and open still work alongside the fix
    assert cf.classify_file("scripts/metrics.py") == "guarded"
    assert cf.classify_file("tests/test_foo.py") == "open"


def test_patterns_without_comments_unaffected(tmp_path, monkeypatch):
    import scripts.classify_file as cf

    arch = tmp_path / "architecture.yaml"
    arch.write_text(
        'file_sensitivity:\n'
        '  constitution:\n'
        '    description: "c"\n'
        '    patterns:\n'
        '      - "CLAUDE.md"\n'
        '  guarded:\n'
        '    description: "g"\n'
        '    patterns:\n'
        '      - "scripts/*.py"\n'
        '  open:\n'
        '    description: "o"\n'
        '    patterns:\n'
        '      - "*.md"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cf, "ARCHITECTURE_FILE", arch)
    monkeypatch.setattr(cf, "_architecture_cache", None)

    assert cf.classify_file("CLAUDE.md") == "constitution"
    assert cf.classify_file("scripts/foo.py") == "guarded"
    assert cf.classify_file("README.md") == "open"
