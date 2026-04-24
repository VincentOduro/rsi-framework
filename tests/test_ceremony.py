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


# F3 regression — pure-docs/pure-config changes classify as minimal regardless
# of line count. Data points from the job-platform Phase 1 retrospective:
# 14/93/179/255 lines, all previously over-scoped to standard/thorough/major.


def test_classify_large_docs_only_is_minimal():
    from scripts.ceremony import classify_change

    # 93-line amendment-log entry previously landed as `standard`
    result = classify_change(
        files_changed=["SPEC_AMENDMENTS.md"],
        lines_added=90,
        lines_removed=3,
    )
    assert result["level"] == "minimal"
    assert result["code_files"] == 0
    assert result["doc_files"] == 1


def test_classify_very_large_docs_only_is_minimal():
    from scripts.ceremony import classify_change

    # 179-line new docs file previously landed as `thorough`
    result = classify_change(
        files_changed=["docs/new-feature.md"],
        lines_added=179,
        lines_removed=0,
    )
    assert result["level"] == "minimal"


def test_classify_pure_yaml_is_minimal():
    from scripts.ceremony import classify_change

    # 255-line pure-YAML change previously landed as `major`
    result = classify_change(
        files_changed=["tests/fixtures/data.yaml"],
        lines_added=200,
        lines_removed=55,
    )
    assert result["level"] == "minimal"
    assert result["config_files"] == 1


def test_classify_huge_config_is_minimal():
    from scripts.ceremony import classify_change

    # 1000-line config change: the cap is now content-type, not line count
    result = classify_change(
        files_changed=["config/prod.yaml"],
        lines_added=800,
        lines_removed=200,
    )
    assert result["level"] == "minimal"


def test_classify_small_code_change_still_standard():
    """F3 regression guard — 20-line .py change must not collapse to minimal."""
    from scripts.ceremony import classify_change

    result = classify_change(
        files_changed=["src/auth.py"],
        lines_added=15,
        lines_removed=5,
    )
    assert result["level"] == "standard"
    assert result["code_files"] == 1


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
