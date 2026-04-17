# Tests for universal_hook.py — model-agnostic hook entry point

from pathlib import Path


def test_universal_hook_imports():
    """Verify universal_hook.py can be imported."""
    import scripts.universal_hook as uh

    assert hasattr(uh, "SUPPORTED_MODELS")
    assert "claude" in uh.SUPPORTED_MODELS
    assert "opencode" in uh.SUPPORTED_MODELS
    assert "generic" in uh.SUPPORTED_MODELS
    assert "shell" in uh.SUPPORTED_MODELS


def test_parse_tool_input_claude():
    """Claude format: JSON with tool_input key."""
    import scripts.universal_hook as uh

    raw = '{"tool_input": {"file_path": "/tmp/test.py"}}'
    result = uh.parse_tool_input_claude(raw)
    assert result == {"file_path": "/tmp/test.py"}


def test_parse_tool_input_claude_empty():
    """Claude format: empty input returns empty dict."""
    import scripts.universal_hook as uh

    result = uh.parse_tool_input_claude("")
    assert result == {}


def test_parse_tool_input_claude_invalid():
    """Claude format: invalid JSON returns empty dict."""
    import scripts.universal_hook as uh

    result = uh.parse_tool_input_claude("not json")
    assert result == {}


def test_parse_args_opencode():
    """opencode format: command-line arguments."""
    import scripts.universal_hook as uh

    action, tool_input = uh.parse_args_opencode(["opencode", "pre-read", "--file", "src/main.py"])
    assert action == "pre-read"
    assert tool_input == {"file_path": "src/main.py"}


def test_parse_args_opencode_with_command():
    """opencode format: bash command."""
    import scripts.universal_hook as uh

    action, tool_input = uh.parse_args_opencode(
        ["opencode", "pre-bash", "--command", "git commit -m 'fix'"]
    )
    assert action == "pre-bash"
    assert tool_input == {"command": "git commit -m 'fix'"}


def test_parse_args_opencode_help():
    """opencode format: help returns 'help' action."""
    import scripts.universal_hook as uh

    action, tool_input = uh.parse_args_opencode(["opencode"])
    assert action == "help"


def test_shell_integrator_imports():
    """Verify ShellIntegrator can be imported."""
    from scripts.adapters.shell_integrator import ShellIntegrator

    assert ShellIntegrator is not None


def test_shell_integrator_init():
    """ShellIntegrator initializes with optional project_root."""
    from scripts.adapters.shell_integrator import ShellIntegrator

    integrator = ShellIntegrator()
    assert integrator.project_root is not None

    custom_root = Path("/custom/path")
    integrator2 = ShellIntegrator(project_root=custom_root)
    assert integrator2.project_root == custom_root


def test_shell_integrator_record_read(tmp_path):
    """ShellIntegrator.record_read() executes without error."""
    from scripts.adapters.shell_integrator import ShellIntegrator

    # Create a test file
    test_file = tmp_path / "test.py"
    test_file.write_text("x = 1", encoding="utf-8")

    # Create memory directory (needed by _record_file_read)
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()

    # Set environment to use temp path
    import os

    original_root = os.environ.get("RSI_PROJECT_ROOT")
    os.environ["RSI_PROJECT_ROOT"] = str(tmp_path)

    try:
        integrator = ShellIntegrator(project_root=tmp_path)
        # Should not raise - just verify it runs
        result = integrator.record_read(str(test_file))
        assert result == True
    finally:
        if original_root:
            os.environ["RSI_PROJECT_ROOT"] = original_root
        else:
            os.environ.pop("RSI_PROJECT_ROOT", None)


def test_shell_integrator_check_edit_allowed_new_file(tmp_path):
    """ShellIntegrator allows editing new files."""
    from unittest.mock import patch

    import scripts.hooks as hooks
    from scripts.adapters.shell_integrator import ShellIntegrator

    # Create a temp state
    state_file = tmp_path / ".preflight_state.json"
    state_file.write_text(
        '{"read_files": [], "edited_files": [], "sessions": []}', encoding="utf-8"
    )

    original_state = hooks.STATE_FILE
    hooks.STATE_FILE = state_file
    hooks._cache.clear()

    try:
        # Mock session check — shell_integrator imports _is_session_expired directly
        import scripts.adapters.shell_integrator as si

        with patch.object(si, "_is_session_expired", return_value=False):
            integrator = ShellIntegrator(project_root=tmp_path)
            new_file = tmp_path / "new.py"
            result = integrator.check_edit_allowed(str(new_file))
            assert result == True
    finally:
        hooks.STATE_FILE = original_state


def test_shell_integrator_check_bash_allowed():
    """ShellIntegrator blocks --no-verify."""
    from scripts.adapters.shell_integrator import ShellIntegrator

    integrator = ShellIntegrator()

    # Normal command should be allowed
    result = integrator.check_bash_allowed("git status")
    assert result == True

    # --no-verify should be blocked (exits)
    try:
        integrator.check_bash_allowed("git commit --no-verify -m 'fix'")
        assert False, "Should have exited"
    except SystemExit:
        pass


def test_record_functions_exist():
    """Verify all record/check functions exist in universal_hook."""
    import scripts.universal_hook as uh

    assert hasattr(uh, "record_read")
    assert hasattr(uh, "check_edit_allowed")
    assert hasattr(uh, "record_edit")
    assert hasattr(uh, "check_bash_allowed")
    assert callable(uh.record_read)
    assert callable(uh.check_edit_allowed)
    assert callable(uh.record_edit)
    assert callable(uh.check_bash_allowed)
