#!/usr/bin/env python3
"""
universal_hook.py — Model-agnostic hook entry point for the RSI framework.

This script is the single entry point for ALL AI model hook integrations.
Different AI models invoke hooks differently:
  - Claude Code: Uses .claude/settings.json PreToolUse/PostToolUse hooks
  - opencode/MiniMax-M2.7: May use shell-based pre-command hooks
  - Generic CLI AI tools: Shell wrappers or environment variables
  - MCP-based tools: MCP hooks specification

This script bridges any of these mechanisms to the core RSI hook logic.

Usage (model-specific):
    # Claude Code: Invoked via .claude/settings.json
    echo '{"tool_input": {...}}' | python3 scripts/universal_hook.py claude pre-edit

    # opencode/MiniMax-M2.7: Via shell wrapper or config
    python3 scripts/universal_hook.py opencode pre-edit --file path/to/file.py

    # Generic: Via environment variables and shell wrapper
    export RSI_HOOK_MODE=pre-edit
    export RSI_TOOL_INPUT='{"command": "git commit"}'
    python3 scripts/universal_hook.py generic

Toyota Principle 5: Jidoka — build quality in, stop on defects.
Toyota Principle 12: Genchi Genbutsu — go and see for yourself.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(os.environ.get("RSI_PROJECT_ROOT", Path(__file__).parent.parent.resolve()))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from hooks import (
        handle_pre_read,
        handle_pre_edit,
        handle_post_edit,
        handle_pre_bash,
        _relative_path,
        _record_file_read,
        _record_file_edited,
        _load_read_files,
        _is_session_expired,
        _get_relevant_fail_entries,
    )
except ImportError:
    from scripts.hooks import (
        handle_pre_read,
        handle_pre_edit,
        handle_post_edit,
        handle_pre_bash,
        _relative_path,
        _record_file_read,
        _record_file_edited,
        _load_read_files,
        _is_session_expired,
        _get_relevant_fail_entries,
    )


SUPPORTED_MODELS = {
    "claude": "Claude Code (PreToolUse/PostToolUse via .claude/settings.json)",
    "opencode": "opencode / MiniMax-M2.7 (CLI-based tool)",
    "generic": "Generic AI tool (shell wrapper integration)",
    "shell": "Shell wrapper (direct CLI integration)",
}


def parse_tool_input_claude(raw_input: str) -> dict:
    """Parse Claude Code's JSON hook input format."""
    try:
        data = json.loads(raw_input)
        return data.get("tool_input", data)
    except json.JSONDecodeError:
        return {}


def parse_tool_input_opencode(raw_input: str) -> dict:
    """Parse opencode/MiniMax hook input format.

    opencode typically passes tool info via command-line arguments or env vars.
    Format: universal_hook.py opencode <action> --file <path>
    """
    return {}


def parse_tool_input_generic(raw_input: str) -> dict:
    """Parse generic AI tool input from environment variables."""
    tool_input_raw = os.environ.get("RSI_TOOL_INPUT", "")
    if tool_input_raw:
        try:
            return json.loads(tool_input_raw)
        except json.JSONDecodeError:
            pass
    return {}


def parse_args_opencode(args: list) -> tuple[str, dict]:
    """Parse opencode-specific arguments.

    Expected format: universal_hook.py opencode <action> [--file FILE] [--command COMMAND]

    Actions: pre-read, pre-edit, post-edit, pre-bash, session-check
    """
    if len(args) < 2:
        return "help", {}

    model_mode = args[0]
    action = args[1] if len(args) > 1 else "help"
    tool_input = {}

    i = 2
    while i < len(args):
        if args[i] == "--file" and i + 1 < len(args):
            tool_input["file_path"] = args[i + 1]
            i += 2
        elif args[i] == "--command" and i + 1 < len(args):
            tool_input["command"] = args[i + 1]
            i += 2
        else:
            i += 1

    return action, tool_input


def record_read(file_path: str) -> None:
    """Record a file as read. Works for all models."""
    if file_path:
        rel = _relative_path(file_path)
        _record_file_read(rel)
        print(f"[RSI] Recorded read: {rel}")


def check_edit_allowed(file_path: str) -> bool:
    """Check if editing is allowed (file was read, session active).

    Returns True if allowed, exits with sys.exit(1) if blocked.
    """
    if not file_path:
        return True

    if _is_session_expired():
        print("[RSI] Session expired. Run 'python3 scripts/rsi.py init' to start a new session.")
        print("[RSI] Edits are blocked until session is active.")
        sys.exit(1)

    rel = _relative_path(file_path)
    read_files = _load_read_files()

    if rel not in read_files:
        if Path(file_path).exists():
            print(f"[RSI] File '{rel}' has not been read in this session.")
            print(f"[RSI] Genchi Genbutsu: you must read a file before editing it.")
            print(f"[RSI] Read the file first, then retry the edit.")
            sys.exit(1)
        return True

    fail_entries = _get_relevant_fail_entries(file_path)
    if fail_entries:
        print(f"[RSI] FAIL-index entries to consider while editing '{rel}':")
        for entry in fail_entries[:5]:
            print(entry)

    return True


def record_edit(file_path: str) -> None:
    """Record a file as edited."""
    if file_path:
        rel = _relative_path(file_path)
        _record_file_edited(rel)


def check_bash_allowed(command: str) -> bool:
    """Check if a bash command is allowed.

    Returns True if allowed, exits with sys.exit(1) if blocked.
    """
    if "git commit" in command and "--no-verify" in command:
        print("[RSI] WARNING: --no-verify bypasses quality gates.")
        print("[RSI] This violates Jidoka (Principle 5): stop and fix quality first.")
        print("[RSI] Remove --no-verify and fix any failing checks.")
        sys.exit(1)
    return True


def cmd_claude(args: list) -> None:
    """Handle Claude Code hook invocation.

    Claude Code passes JSON on stdin with structure:
    {"tool_input": {"tool_name": "Read", "file_path": "/path/to/file"}}
    """
    raw = sys.stdin.read()
    tool_input = parse_tool_input_claude(raw)

    if not args:
        print("Usage: universal_hook.py claude <pre-read|pre-edit|post-edit|pre-bash>")
        sys.exit(1)

    action = args[0]

    handlers = {
        "pre-read": lambda: handle_pre_read(tool_input),
        "pre-edit": lambda: handle_pre_edit(tool_input),
        "post-edit": lambda: handle_post_edit(tool_input),
        "pre-bash": lambda: handle_pre_bash(tool_input),
    }

    handler = handlers.get(action)
    if handler:
        handler()
    else:
        print(f"Unknown Claude action: {action}", file=sys.stderr)
        sys.exit(1)


def cmd_opencode(args: list) -> None:
    """Handle opencode/MiniMax-M2.7 hook invocation.

    opencode is a CLI-based AI tool. It may invoke hooks via:
    1. Shell wrapper that intercepts commands
    2. Configuration file specifying hook commands
    3. Environment variables

    Expected invocation: universal_hook.py opencode <action> --file <path>
    """
    action, tool_input = parse_args_opencode(args)

    if action == "help":
        print("Usage: universal_hook.py opencode <pre-read|pre-edit|post-edit|pre-bash|session-check> [--file FILE] [--command COMMAND]")
        sys.exit(0)

    handlers = {
        "pre-read": lambda: handle_pre_read(tool_input),
        "pre-edit": lambda: handle_pre_edit(tool_input),
        "post-edit": lambda: handle_post_edit(tool_input),
        "pre-bash": lambda: handle_pre_bash(tool_input),
        "session-check": lambda: (_is_session_expired() and print("[RSI] Session expired") or print("[RSI] Session active")),
    }

    handler = handlers.get(action)
    if handler:
        handler()
    else:
        print(f"Unknown opencode action: {action}", file=sys.stderr)
        sys.exit(1)


def cmd_generic(args: list) -> None:
    """Handle generic AI tool hook invocation.

    Generic tools can integrate via:
    1. Environment variables (RSI_TOOL_INPUT, RSI_HOOK_MODE)
    2. Shell aliases/wrappers
    3. Direct function calls via Python import

    Environment variables:
        RSI_TOOL_INPUT: JSON-encoded tool input
        RSI_HOOK_MODE: pre-read|pre-edit|post-edit|pre-bash
    """
    mode = os.environ.get("RSI_HOOK_MODE", "")
    tool_input = parse_tool_input_generic("")

    handlers = {
        "pre-read": lambda: handle_pre_read(tool_input),
        "pre-edit": lambda: handle_pre_edit(tool_input),
        "post-edit": lambda: handle_post_edit(tool_input),
        "pre-bash": lambda: handle_pre_bash(tool_input),
    }

    handler = handlers.get(mode)
    if handler:
        handler()
    elif not mode:
        print("Usage for generic mode: Set RSI_HOOK_MODE env var and RSI_TOOL_INPUT env var")
        print("RSI_HOOK_MODE: pre-read|pre-edit|post-edit|pre-bash")
        sys.exit(1)
    else:
        print(f"Unknown generic mode: {mode}", file=sys.stderr)
        sys.exit(1)


def cmd_shell(args: list) -> None:
    """Handle shell wrapper integration.

    Shell wrapper mode allows wrapping any AI tool's file operations.

    Usage:
        # Record a file as read
        universal_hook.py shell record-read --file path/to/file.py

        # Check if edit is allowed
        universal_hook.py shell check-edit --file path/to/file.py

        # Record an edit
        universal_hook.py shell record-edit --file path/to/file.py

        # Check bash command
        universal_hook.py shell check-bash --command "git commit -m 'msg'"

        # Check session status
        universal_hook.py shell session-status
    """
    if len(args) < 1:
        print("""Usage: universal_hook.py shell <command> [options]

Commands:
    record-read --file <path>      Record a file as read
    check-edit --file <path>       Check if editing is allowed (blocks if not)
    record-edit --file <path>     Record a file as edited
    check-bash --command <cmd>     Check if bash command is allowed
    session-status                 Check if session is active
    fail-index --file <path>       Show FAIL-index entries for file
""")
        sys.exit(0)

    cmd = args[0]
    remaining = args[1:]

    file_path = ""
    command = ""

    i = 0
    while i < len(remaining):
        if remaining[i] == "--file" and i + 1 < len(remaining):
            file_path = remaining[i + 1]
            i += 2
        elif remaining[i] == "--command" and i + 1 < len(remaining):
            command = remaining[i + 1]
            i += 2
        else:
            i += 1

    if cmd == "record-read":
        record_read(file_path)
    elif cmd == "check-edit":
        check_edit_allowed(file_path)
        print(f"[RSI] Edit allowed: {file_path}")
    elif cmd == "record-edit":
        record_edit(file_path)
    elif cmd == "check-bash":
        check_bash_allowed(command)
        print(f"[RSI] Bash allowed: {command}")
    elif cmd == "session-status":
        if _is_session_expired():
            print("[RSI] Session: EXPIRED")
            sys.exit(1)
        else:
            print("[RSI] Session: ACTIVE")
    elif cmd == "fail-index":
        entries = _get_relevant_fail_entries(file_path)
        if entries:
            print(f"[RSI] FAIL-index entries for {file_path}:")
            for e in entries[:5]:
                print(e)
        else:
            print(f"[RSI] No FAIL-index entries for {file_path}")
    else:
        print(f"Unknown shell command: {cmd}", file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("""RSI Universal Hook — Model-Agnostic Tool-Layer Enforcement

Usage: universal_hook.py <model> <action> [options]

Models:
    claude     Claude Code (uses .claude/settings.json hooks)
    opencode   opencode / MiniMax-M2.7 CLI tool
    generic    Generic AI tool (via environment variables)
    shell      Direct shell integration (for wrappers/scripts)

Examples:
    # Claude Code (via .claude/settings.json):
    echo '{"tool_input": {"file_path": "foo.py"}}' | universal_hook.py claude pre-read

    # opencode/MiniMax (via config or wrapper):
    universal_hook.py opencode pre-read --file src/main.py

    # Shell wrapper:
    universal_hook.py shell record-read --file src/main.py
    universal_hook.py shell check-edit --file src/main.py

    # Generic (via environment):
    RSI_HOOK_MODE=pre-edit RSI_TOOL_INPUT='{"file_path":"foo.py"}' universal_hook.py generic

Environment variables:
    RSI_PROJECT_ROOT    Override project root (default: auto-detect)
    RSI_HOOK_MODE       Hook mode for generic integration
    RSI_TOOL_INPUT      JSON tool input for generic integration
""")
        sys.exit(0)

    model = sys.argv[1]
    args = sys.argv[2:]

    if model == "claude":
        cmd_claude(args)
    elif model == "opencode":
        cmd_opencode(args)
    elif model == "generic":
        cmd_generic(args)
    elif model == "shell":
        cmd_shell(args)
    elif model == "list-models":
        print("Supported models:")
        for name, desc in SUPPORTED_MODELS.items():
            print(f"    {name}: {desc}")
    else:
        print(f"Unknown model: {model}", file=sys.stderr)
        print("Run 'universal_hook.py help' for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()