"""Tests for the ceremony classifier — verifies Heijunka change classification."""


def test_classify_docs_only():
    from scripts.ceremony import classify_change
    result = classify_change(
        files_changed=["README.md", "CHANGELOG.md"],
        lines_added=10,
        lines_removed=5,
    )
    assert result["level"] == "minimal"
    assert result["code_files"] == 0
    assert result["doc_files"] == 2


def test_classify_small_code_change():
    from scripts.ceremony import classify_change
    result = classify_change(
        files_changed=["src/auth.py"],
        lines_added=15,
        lines_removed=5,
    )
    assert result["level"] == "standard"
    assert result["code_files"] == 1


def test_classify_large_change():
    from scripts.ceremony import classify_change
    files = [f"src/module_{i}.py" for i in range(8)]
    result = classify_change(
        files_changed=files,
        lines_added=300,
        lines_removed=100,
    )
    assert result["level"] == "major"


def test_classify_mixed_change():
    from scripts.ceremony import classify_change
    result = classify_change(
        files_changed=["src/api.py", "README.md", "config.yaml"],
        lines_added=50,
        lines_removed=20,
    )
    assert result["level"] == "standard"
    assert result["code_files"] == 1
    assert result["doc_files"] == 1
    assert result["config_files"] == 1


def test_required_steps_exist():
    from scripts.ceremony import CEREMONY_STEPS
    assert "minimal" in CEREMONY_STEPS
    assert "standard" in CEREMONY_STEPS
    assert "thorough" in CEREMONY_STEPS
    assert "major" in CEREMONY_STEPS
    # Major should have more steps than minimal
    assert len(CEREMONY_STEPS["major"]) > len(CEREMONY_STEPS["minimal"])


def test_classify_returns_required_steps():
    from scripts.ceremony import classify_change
    result = classify_change(files_changed=["src/main.py"], lines_added=10, lines_removed=2)
    assert "required_steps" in result
    assert len(result["required_steps"]) > 0


def test_test_files_classified():
    from scripts.ceremony import classify_change
    result = classify_change(
        files_changed=["tests/test_auth.py", "src/auth.py"],
        lines_added=30,
        lines_removed=10,
    )
    assert result["test_files"] == 1
    assert result["code_files"] == 1
