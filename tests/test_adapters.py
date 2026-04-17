"""Tests for the adapter system — verifies rules engine, tool wrappers, and platform adapters."""

import json
import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Rules engine tests
# ---------------------------------------------------------------------------


def test_rules_have_required_fields():
    from adapters.base import RSIRules

    for rule in RSIRules.RULES:
        assert "id" in rule
        assert "name" in rule
        assert "rule" in rule
        assert "enforcement" in rule


def test_system_prompt_generation():
    from adapters.base import RSIRules

    prompt = RSIRules.generate_system_prompt()
    assert len(prompt) > 100
    assert "Genchi Genbutsu" in prompt
    assert "Jidoka" in prompt
    assert "Kaizen" in prompt


def test_tool_definitions_generation():
    from adapters.base import RSIRules

    defs = RSIRules.generate_tool_definitions()
    assert len(defs) >= 4
    names = [d["name"] for d in defs]
    assert "rsi_read_file" in names
    assert "rsi_edit_file" in names
    assert "rsi_capture" in names


def test_ceremony_levels_defined():
    from adapters.base import RSIRules

    assert "minimal" in RSIRules.CEREMONY_LEVELS
    assert "standard" in RSIRules.CEREMONY_LEVELS
    assert "thorough" in RSIRules.CEREMONY_LEVELS
    assert "major" in RSIRules.CEREMONY_LEVELS


# ---------------------------------------------------------------------------
# Tool wrapper tests
# ---------------------------------------------------------------------------


def test_session_creation(tmp_path):
    from adapters.tool_wrappers import RSISession

    session = RSISession(tmp_path)
    session.start()
    assert not session.is_expired()
    assert (tmp_path / ".memory" / ".session_timestamp").exists()


def test_read_records_file(tmp_path):
    from adapters.tool_wrappers import RSISession

    session = RSISession(tmp_path)
    session.start()

    # Create a file to read
    test_file = tmp_path / "src" / "main.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("x = 1\n", encoding="utf-8")

    session.read_file(str(test_file))
    rel = str(test_file.relative_to(tmp_path))
    assert rel in session.files_read


def test_edit_blocked_without_read(tmp_path):
    from adapters.tool_wrappers import RSIError, RSISession

    session = RSISession(tmp_path)
    session.start()

    test_file = tmp_path / "src" / "main.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("x = 1\n", encoding="utf-8")

    try:
        session.edit_file(str(test_file), "x = 2")
        assert False, "Should have raised RSIError"
    except RSIError as e:
        assert "BLOCKED" in str(e)
        assert "read" in str(e).lower()


def test_edit_allowed_after_read(tmp_path):
    from adapters.tool_wrappers import RSISession

    session = RSISession(tmp_path)
    session.start()

    test_file = tmp_path / "src" / "main.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("x = 1\n", encoding="utf-8")

    session.read_file(str(test_file))
    result = session.edit_file(str(test_file), "x = 2")
    assert "allowed" in result.lower()


def test_write_new_file_allowed(tmp_path):
    from adapters.tool_wrappers import RSISession

    session = RSISession(tmp_path)
    session.start()

    new_file = tmp_path / "src" / "new_module.py"
    result = session.write_file(str(new_file), "y = 1")
    assert "allowed" in result.lower()


def test_run_command_blocks_no_verify(tmp_path):
    from adapters.tool_wrappers import RSIError, RSISession

    session = RSISession(tmp_path)
    session.start()

    try:
        session.run_command("git commit --no-verify -m 'skip'")
        assert False, "Should have raised RSIError"
    except RSIError as e:
        assert "BLOCKED" in str(e)
        assert "no-verify" in str(e).lower()


def test_capture_requires_proof_wrong(tmp_path):
    from adapters.tool_wrappers import RSIError, RSISession

    session = RSISession(tmp_path)
    session.start()

    try:
        session.capture("test task", "it worked", "nothing", "")
        assert False, "Should have raised RSIError"
    except RSIError as e:
        assert "MANDATORY" in str(e)


def test_make_tool_functions(tmp_path):
    from adapters.tool_wrappers import RSISession, make_tool_functions

    session = RSISession(tmp_path)
    session.start()

    tools = make_tool_functions(session)
    assert "rsi_read_file" in tools
    assert "rsi_edit_file" in tools
    assert "rsi_run_command" in tools
    assert "rsi_capture" in tools
    assert "rsi_dashboard" in tools
    assert callable(tools["rsi_read_file"])


def test_function_call_handler(tmp_path):
    from adapters.tool_wrappers import RSISession, make_function_call_handler

    session = RSISession(tmp_path)
    session.start()

    # Create a test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello", encoding="utf-8")

    handler = make_function_call_handler(session)

    # Read should work
    result = handler("rsi_read_file", {"file_path": str(test_file)})
    assert "hello" in result

    # Edit after read should work
    result = handler("rsi_edit_file", {"file_path": str(test_file), "changes": "world"})
    assert "allowed" in result.lower()

    # Unknown function
    result = handler("nonexistent_tool", {})
    assert "Unknown" in result


# ---------------------------------------------------------------------------
# Platform adapter tests
# ---------------------------------------------------------------------------


def test_adapter_registry():
    # Side-effect imports — each module's @register_adapter decorator runs on
    # import and populates AVAILABLE_ADAPTERS. Keep the noqa markers so ruff
    # F401 does not strip them again.
    import adapters.aider
    import adapters.claude_code
    import adapters.copilot
    import adapters.cursor
    import adapters.generic
    import adapters.langchain_adapter
    import adapters.minimax
    import adapters.openai_agents  # noqa: F401
    from adapters.base import AVAILABLE_ADAPTERS

    assert "claude-code" in AVAILABLE_ADAPTERS
    assert "minimax" in AVAILABLE_ADAPTERS
    assert "cursor" in AVAILABLE_ADAPTERS
    assert "copilot" in AVAILABLE_ADAPTERS
    assert "aider" in AVAILABLE_ADAPTERS
    assert "openai-agents" in AVAILABLE_ADAPTERS
    assert "langchain" in AVAILABLE_ADAPTERS
    assert "generic" in AVAILABLE_ADAPTERS


def test_claude_adapter_generates_files(tmp_path):
    from adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter(tmp_path)
    files = adapter.generate_files()
    assert "CLAUDE.md" in files
    assert ".claude/settings.json" in files
    # Verify settings.json is valid JSON
    settings = json.loads(files[".claude/settings.json"])
    assert "hooks" in settings
    assert "PreToolUse" in settings["hooks"]


def test_minimax_adapter_generates_files(tmp_path):
    from adapters.minimax import MiniMaxAdapter

    adapter = MiniMaxAdapter(tmp_path)
    files = adapter.generate_files()
    assert "opencode_wrapper.sh" in files
    assert "rsi_tools.py" in files
    assert ".opencode/instructions.md" in files
    # Verify shell wrapper has key enforcement functions
    wrapper = files["opencode_wrapper.sh"]
    assert "rsi_cat" in wrapper
    assert "rsi_vim" in wrapper
    assert "_rsi_check_read" in wrapper
    assert "_rsi_record_read" in wrapper
    assert "RSI BLOCKED" in wrapper


def test_minimax_adapter_supports_tool_enforcement():
    from adapters.minimax import MiniMaxAdapter

    adapter = MiniMaxAdapter()
    assert adapter.supports_tool_enforcement is True


def test_cursor_adapter_no_tool_enforcement():
    from adapters.cursor import CursorAdapter

    adapter = CursorAdapter()
    assert adapter.supports_tool_enforcement is False


def test_adapter_install(tmp_path):
    from adapters.cursor import CursorAdapter

    adapter = CursorAdapter(tmp_path)
    created = adapter.install()
    assert ".cursorrules" in created
    assert (tmp_path / ".cursorrules").exists()
    content = (tmp_path / ".cursorrules").read_text(encoding="utf-8")
    assert "Genchi Genbutsu" in content


def test_all_adapters_generate_nonempty_files(tmp_path):
    # Side-effect imports — see note in test_adapter_registry.
    import adapters.aider
    import adapters.claude_code
    import adapters.copilot
    import adapters.cursor
    import adapters.generic
    import adapters.langchain_adapter
    import adapters.minimax
    import adapters.openai_agents  # noqa: F401
    from adapters.base import AVAILABLE_ADAPTERS

    for pid, cls in AVAILABLE_ADAPTERS.items():
        adapter = cls(tmp_path)
        files = adapter.generate_files()
        assert len(files) > 0, f"{pid} generates no files"
        for path, content in files.items():
            assert len(content) > 0, f"{pid} generates empty {path}"
