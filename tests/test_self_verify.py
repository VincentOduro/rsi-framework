"""Tests for U1 — find_placeholder_code must scan only lines added vs HEAD.

Pre-existing placeholders in unchanged regions must not block commits that
didn't introduce them. If git diff is unavailable or returns empty, the
whole-file fallback preserves the prior strict behavior rather than
silently skipping the check.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _git(repo, *args):
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def test_pre_existing_placeholder_in_unchanged_region_is_ignored(tmp_path, monkeypatch):
    import scripts.self_verify as sv

    repo = tmp_path / "repo"
    _init_repo(repo)
    target = repo / "module.py"
    target.write_text(
        "def legacy():\n"
        "    # TODO: later\n"
        "    return 1\n",
        encoding="utf-8",
    )
    _git(repo, "add", "module.py")
    _git(repo, "commit", "-q", "-m", "initial")

    # Edit adds a NEW function without a placeholder. The pre-existing TODO
    # in `legacy` is unchanged and must not be reported.
    target.write_text(
        "def legacy():\n"
        "    # TODO: later\n"
        "    return 1\n"
        "\n"
        "def added():\n"
        "    return 2\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sv, "PROJECT_ROOT", repo)
    issues = sv.find_placeholder_code(target)
    assert issues == [], f"Should not report pre-existing TODO; got: {issues}"


def test_new_placeholder_in_added_line_is_reported(tmp_path, monkeypatch):
    import scripts.self_verify as sv

    repo = tmp_path / "repo"
    _init_repo(repo)
    target = repo / "module.py"
    target.write_text("def existing():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", "module.py")
    _git(repo, "commit", "-q", "-m", "initial")

    # Edit introduces a new TODO on an added line.
    target.write_text(
        "def existing():\n    return 1\n\ndef new():\n    # TODO: fix me\n    pass\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sv, "PROJECT_ROOT", repo)
    issues = sv.find_placeholder_code(target)
    assert issues, "Should report newly-added # TODO"
    assert any("TODO" in issue for issue in issues)


def test_placeholder_on_unchanged_line_plus_new_code_not_reported(tmp_path, monkeypatch):
    """Appending clean code below a pre-existing TODO must not surface the TODO."""
    import scripts.self_verify as sv

    repo = tmp_path / "repo"
    _init_repo(repo)
    target = repo / "module.py"
    target.write_text(
        "# TODO: keep for now\n"
        "def older():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    _git(repo, "add", "module.py")
    _git(repo, "commit", "-q", "-m", "initial")

    target.write_text(
        "# TODO: keep for now\n"
        "def older():\n"
        "    return 1\n"
        "\n"
        "def clean_new():\n"
        "    return 2\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sv, "PROJECT_ROOT", repo)
    issues = sv.find_placeholder_code(target)
    assert issues == []


def test_untracked_new_file_falls_back_to_whole_file_scan(tmp_path, monkeypatch):
    """New file (not in HEAD) has empty `git diff HEAD -- path` → whole-file scan."""
    import scripts.self_verify as sv

    repo = tmp_path / "repo"
    _init_repo(repo)
    # Create a HEAD so `HEAD` resolves
    seed = repo / "seed.py"
    seed.write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "seed.py")
    _git(repo, "commit", "-q", "-m", "seed")

    new_file = repo / "fresh.py"
    new_file.write_text(
        "def fresh():\n"
        "    # TODO: placeholder in untracked file\n"
        "    raise NotImplementedError\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sv, "PROJECT_ROOT", repo)
    issues = sv.find_placeholder_code(new_file)
    assert any("TODO" in i for i in issues)
    assert any("NotImplementedError" in i for i in issues)


def test_non_repo_path_falls_back_to_whole_file(tmp_path, monkeypatch):
    """When the file lives outside the project root, fall back to whole-file."""
    import scripts.self_verify as sv

    outside = tmp_path / "somewhere_else.py"
    outside.write_text(
        "def demo():\n    # TODO: hi\n    return 0\n",
        encoding="utf-8",
    )
    # PROJECT_ROOT unchanged — outside is outside.
    issues = sv.find_placeholder_code(outside)
    assert any("TODO" in i for i in issues)
