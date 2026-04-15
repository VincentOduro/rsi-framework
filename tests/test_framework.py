# Framework self-validation tests.
# These tests verify the framework scripts work correctly against themselves.

import tempfile
from pathlib import Path


def test_preflight_check_imports():
    """Verify preflight_check.py can be imported."""
    import scripts.preflight_check
    assert hasattr(scripts.preflight_check, '_load_state')


def test_post_implementation_imports():
    """Verify post_implementation.py can be imported."""
    import scripts.post_implementation
    assert hasattr(scripts.post_implementation, 'update_round_log')


def test_self_feedback_imports():
    """Verify self_feedback.py can be imported."""
    import scripts.self_feedback
    assert hasattr(scripts.self_feedback, 'review_code')


def test_self_optimization_imports():
    """Verify self_optimization.py can be imported."""
    import scripts.self_optimization
    assert hasattr(scripts.self_optimization, 'prioritize_fixes')


def test_self_verify_imports():
    """Verify self_verify.py LanguageChecker plugin system loads."""
    import scripts.self_verify as sv
    assert hasattr(sv, 'LANG_CHECKERS')
    assert hasattr(sv, 'get_checker_for')
    assert hasattr(sv, 'PythonChecker')
    assert hasattr(sv, 'ShellChecker')
    assert hasattr(sv, 'GenericTextChecker')
    assert hasattr(sv, 'find_placeholder_code')


def test_python_checker_syntax():
    """PythonChecker detects valid and invalid Python syntax."""
    import scripts.self_verify as sv
    checker = sv.PythonChecker()

    # Valid Python
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("x = 1\n")
        f.flush()
        ok, err = checker.check_syntax(Path(f.name))
    assert ok, f"Valid Python should pass: {err}"

    # Invalid Python
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def broken(    \n")
        f.flush()
        ok, err = checker.check_syntax(Path(f.name))
    assert not ok, "Invalid Python should fail"


def test_shell_checker_syntax():
    """ShellChecker detects valid and invalid shell syntax."""
    import scripts.self_verify as sv
    checker = sv.ShellChecker()

    # Valid shell
    with tempfile.NamedTemporaryFile(suffix=".sh", mode="w", delete=False) as f:
        f.write("#!/bin/bash\necho hello\n")
        f.flush()
        ok, err = checker.check_syntax(Path(f.name))
    assert ok, f"Valid shell should pass: {err}"

    # Invalid shell (unclosed if)
    with tempfile.NamedTemporaryFile(suffix=".sh", mode="w", delete=False) as f:
        f.write("if true; then\necho")
        f.flush()
        ok, err = checker.check_syntax(Path(f.name))
    assert not ok, "Invalid shell should fail"


def test_placeholder_detection():
    """find_placeholder_code detects TODO, NotImplementedError, etc."""
    import scripts.self_verify as sv

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("# TODO: fix this later\n")
        f.write("def foo():\n")
        f.write("    pass  # TODO\n")
        f.flush()
        issues = sv.find_placeholder_code(Path(f.name))

    # Line 1 matches '# TODO'. Line 3 matches both '# TODO' and 'pass  #' -> 3 total.
    assert len(issues) == 3, f"Expected 3 placeholders, got {len(issues)}: {issues}"


def test_get_checker_for_file():
    """get_checker_for returns correct checker by extension."""
    import scripts.self_verify as sv

    assert isinstance(sv.get_checker_for(Path("foo.py")), sv.PythonChecker)
    assert isinstance(sv.get_checker_for(Path("foo.sh")), sv.ShellChecker)
    assert isinstance(sv.get_checker_for(Path("foo.js")), sv.GenericTextChecker)
    assert isinstance(sv.get_checker_for(Path("foo.txt")), sv.GenericTextChecker)


def test_session_check_functions_exist():
    """Verify --require-session and --start functions exist."""
    import scripts.preflight_check as pc

    assert hasattr(pc, 'cmd_require_session')
    assert hasattr(pc, 'cmd_start')
    assert hasattr(pc, '_is_session_expired')
    assert hasattr(pc, '_touch_session')


def test_backlog_imports():
    """Verify backlog.py can be imported."""
    import scripts.backlog as bl
    assert hasattr(bl, 'VALID_TYPES')
    assert hasattr(bl, 'VALID_STATUSES')
    assert hasattr(bl, 'cmd_add')
    assert hasattr(bl, 'cmd_list')
    assert hasattr(bl, 'cmd_show')
    assert hasattr(bl, 'cmd_update')
    assert hasattr(bl, 'cmd_stats')


def test_framework_sync_imports():
    """Verify framework_sync.py can be imported."""
    import scripts.framework_sync as fs
    assert hasattr(fs, 'cmd_status')
    assert hasattr(fs, 'cmd_check')
    assert hasattr(fs, 'cmd_pull')
    assert hasattr(fs, 'cmd_adopt')
    assert hasattr(fs, 'cmd_feedback')
    assert hasattr(fs, 'FRAMEWORK_MARKER')
    assert hasattr(fs, 'FEEDBACK_FILE')
