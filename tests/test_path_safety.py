"""Security regression: worker-supplied paths must not escape PROJECT_ROOT."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.delegate import UnsafePathError, _safe_project_path, validate_task


class TestSafeProjectPath:
    def test_relative_path_inside_root_ok(self) -> None:
        result = _safe_project_path("scripts/foo.py")
        assert result.is_absolute()
        assert str(result).startswith(str(PROJECT_ROOT.resolve()))

    def test_nested_path_ok(self) -> None:
        _safe_project_path("tests/subdir/deeper/file.py")

    @pytest.mark.parametrize(
        "bad",
        [
            "../etc/passwd",
            "../../outside.txt",
            "foo/../../../outside.txt",
        ],
    )
    def test_traversal_blocked(self, bad: str) -> None:
        with pytest.raises(UnsafePathError):
            _safe_project_path(bad)

    def test_benign_dotdot_inside_root_ok(self) -> None:
        # foo/.. resolves to PROJECT_ROOT itself — still inside bounds.
        _safe_project_path("foo/..")

    @pytest.mark.parametrize(
        "absolute",
        [
            "/etc/passwd",
            "/tmp/foo",
            "C:/Windows/System32/drivers/etc/hosts",
            "C:\\Windows\\foo",
            "D:/arbitrary/file",
        ],
    )
    def test_absolute_blocked(self, absolute: str) -> None:
        with pytest.raises(UnsafePathError):
            _safe_project_path(absolute)


class TestValidateTaskPathSafety:
    def _spec(self, **extra: object) -> dict:
        base = {
            "id": "T-SEC",
            "description": "d",
            "instruction": "i",
            "files_to_modify": ["scripts/ok.py"],
            "acceptance_criteria": ["c"],
            "proof_wrong": "p",
        }
        base.update(extra)
        return base

    def test_valid_spec_has_no_path_issues(self) -> None:
        issues = validate_task(self._spec())
        # Some issues may exist (e.g., file existence) but none should mention BLOCKED path.
        assert not any("escapes project root" in i for i in issues)
        assert not any("Absolute paths" in i for i in issues)

    def test_absolute_write_blocked(self) -> None:
        issues = validate_task(self._spec(files_to_modify=["/etc/passwd"]))
        assert any("Absolute paths" in i or "escapes project root" in i for i in issues)

    def test_traversal_write_blocked(self) -> None:
        issues = validate_task(self._spec(files_to_modify=["../../etc/passwd"]))
        assert any("escapes project root" in i for i in issues)

    def test_absolute_read_blocked(self) -> None:
        issues = validate_task(
            self._spec(files_to_modify=["scripts/ok.py"], files_to_read=["/etc/passwd"])
        )
        assert any("Absolute paths" in i or "escapes project root" in i for i in issues)

    def test_windows_drive_write_blocked(self) -> None:
        issues = validate_task(self._spec(files_to_modify=["C:/Windows/foo"]))
        assert any("Absolute paths" in i for i in issues)
