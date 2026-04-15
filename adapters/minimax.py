"""
MiniMax-M2.7 adapter — enforcement for opencode + MiniMax models.

MiniMax-M2.7 supports OpenAI-compatible function calling. Enforcement
works through two complementary layers:

1. **Shell wrapper** (opencode_wrapper.sh): Intercepts file operations
   at the OS level. Works with opencode or any CLI tool that reads/writes
   files through shell commands. This is the primary enforcement for CLI
   agents that don't have native tool hook APIs.

2. **Python tool wrappers** (tool_wrappers.py): For custom agents built
   on MiniMax's API directly, use RSISession to wrap tool implementations.

3. **System prompt**: Injected into the model's context to reinforce
   behavioral rules that can't be enforced at the tool layer.

opencode is the primary CLI interface for MiniMax-M2.7. The shell wrapper
intercepts cat/less/vim/nano/sed/ed commands to track reads and edits.
"""

import json
from pathlib import Path
from adapters.base import BaseAdapter, RSIRules, register_adapter


@register_adapter
class MiniMaxAdapter(BaseAdapter):

    @property
    def platform_name(self) -> str:
        return "opencode / MiniMax-M2.7"

    @property
    def platform_id(self) -> str:
        return "minimax"

    @property
    def supports_tool_enforcement(self) -> bool:
        return True  # Via shell wrapper + Python tool wrappers

    def generate_files(self) -> dict[str, str]:
        return {
            "opencode_wrapper.sh": self._generate_shell_wrapper(),
            "rsi_tools.py": self._generate_tool_module(),
            ".opencode/instructions.md": self._generate_instructions(),
        }

    def _generate_shell_wrapper(self) -> str:
        """Generate shell wrapper that intercepts file ops for opencode / MiniMax-M2.7.

        This wrapper:
        - Wraps common file-reading commands (cat, less, head, tail, bat)
          to record files as read in the RSI session state.
        - Wraps common file-editing commands (vim, nano, sed, ed, tee)
          to check read-before-edit and record edits.
        - Wraps git commit to block --no-verify.
        - Sources into the user's shell so opencode's commands hit the wrappers.

        Usage:
            source opencode_wrapper.sh   # Activate in current shell
            # Now opencode's file operations go through RSI enforcement
        """
        return r'''#!/bin/bash
# RSI Framework — Shell wrapper for opencode / MiniMax-M2.7
#
# Source this file to activate enforcement in your shell:
#   source opencode_wrapper.sh
#
# This intercepts file operations so the RSI framework can enforce
# read-before-edit discipline regardless of which AI model is driving.
#
# Works with: opencode, aider, any CLI tool that uses shell commands.

RSI_PROJECT_ROOT="${RSI_PROJECT_ROOT:-$(pwd)}"
RSI_STATE_FILE="$RSI_PROJECT_ROOT/.memory/.preflight_state.json"
RSI_SESSION_FILE="$RSI_PROJECT_ROOT/.memory/.session_timestamp"

_rsi_ensure_state() {
    mkdir -p "$RSI_PROJECT_ROOT/.memory"
    if [ ! -f "$RSI_STATE_FILE" ]; then
        echo '{"read_files":[],"edited_files":[],"sessions":[]}' > "$RSI_STATE_FILE"
    fi
}

_rsi_relative() {
    # Convert absolute path to project-relative
    local abs
    abs="$(cd "$(dirname "$1")" 2>/dev/null && pwd)/$(basename "$1")"
    echo "${abs#$RSI_PROJECT_ROOT/}"
}

_rsi_record_read() {
    _rsi_ensure_state
    local rel
    rel="$(_rsi_relative "$1")"
    python3 -c "
import json, sys
f = '$RSI_STATE_FILE'
try:
    d = json.loads(open(f).read())
except: d = {'read_files':[],'edited_files':[],'sessions':[]}
s = set(d.get('read_files',[]))
s.add('$rel')
d['read_files'] = sorted(s)
open(f,'w').write(json.dumps(d, indent=2))
" 2>/dev/null
}

_rsi_check_read() {
    _rsi_ensure_state
    local rel
    rel="$(_rsi_relative "$1")"
    python3 -c "
import json, sys
f = '$RSI_STATE_FILE'
try:
    d = json.loads(open(f).read())
except: sys.exit(1)
if '$rel' not in d.get('read_files',[]):
    print('[RSI BLOCKED] File \"$rel\" not read yet. Read it first.')
    sys.exit(1)
" 2>/dev/null
    return $?
}

_rsi_record_edit() {
    _rsi_ensure_state
    local rel
    rel="$(_rsi_relative "$1")"
    python3 -c "
import json
f = '$RSI_STATE_FILE'
try:
    d = json.loads(open(f).read())
except: d = {'read_files':[],'edited_files':[],'sessions':[]}
s = set(d.get('edited_files',[]))
s.add('$rel')
d['edited_files'] = sorted(s)
open(f,'w').write(json.dumps(d, indent=2))
" 2>/dev/null
}

_rsi_check_session() {
    if [ ! -f "$RSI_SESSION_FILE" ]; then
        echo "[RSI] No active session. Run: python3 scripts/rsi.py init"
        return 1
    fi
    python3 -c "
import json, sys
from datetime import datetime, timezone, timedelta
f = '$RSI_SESSION_FILE'
try:
    d = json.loads(open(f).read())
    ts = datetime.fromisoformat(d['timestamp'])
    ttl = int(d.get('ttl_hours', 24))
    if (datetime.now(timezone.utc) - ts) > timedelta(hours=ttl):
        print('[RSI] Session expired. Run: python3 scripts/rsi.py init')
        sys.exit(1)
except: sys.exit(1)
" 2>/dev/null
    return $?
}

# --- Wrapped read commands ---

rsi_cat() {
    for f in "$@"; do
        if [ -f "$f" ]; then
            _rsi_record_read "$f"
        fi
    done
    command cat "$@"
}

rsi_less() {
    for f in "$@"; do
        if [ -f "$f" ] && [[ "$f" != -* ]]; then
            _rsi_record_read "$f"
        fi
    done
    command less "$@"
}

rsi_head() {
    for f in "$@"; do
        if [ -f "$f" ] && [[ "$f" != -* ]]; then
            _rsi_record_read "$f"
        fi
    done
    command head "$@"
}

rsi_tail() {
    for f in "$@"; do
        if [ -f "$f" ] && [[ "$f" != -* ]]; then
            _rsi_record_read "$f"
        fi
    done
    command tail "$@"
}

rsi_bat() {
    for f in "$@"; do
        if [ -f "$f" ] && [[ "$f" != -* ]]; then
            _rsi_record_read "$f"
        fi
    done
    command bat "$@" 2>/dev/null || command cat "$@"
}

# --- Wrapped edit commands ---

rsi_vim() {
    local target="$1"
    if [ -f "$target" ]; then
        _rsi_check_session || return 1
        _rsi_check_read "$target" || return 1
        _rsi_record_edit "$target"
    fi
    command vim "$@"
}

rsi_nano() {
    local target="$1"
    if [ -f "$target" ]; then
        _rsi_check_session || return 1
        _rsi_check_read "$target" || return 1
        _rsi_record_edit "$target"
    fi
    command nano "$@"
}

rsi_sed() {
    # sed -i modifies files in-place — check the last arg
    local last="${!#}"
    if [[ "$*" == *"-i"* ]] && [ -f "$last" ]; then
        _rsi_check_session || return 1
        _rsi_check_read "$last" || return 1
        _rsi_record_edit "$last"
    fi
    command sed "$@"
}

rsi_tee() {
    # tee writes to files — check all file args
    for f in "$@"; do
        if [[ "$f" != -* ]] && [ -f "$f" ]; then
            _rsi_check_session || return 1
            _rsi_check_read "$f" || return 1
            _rsi_record_edit "$f"
        fi
    done
    command tee "$@"
}

# --- Wrapped git commit ---

rsi_git() {
    if [[ "$1" == "commit" ]] && [[ "$*" == *"--no-verify"* ]]; then
        echo "[RSI BLOCKED] --no-verify bypasses quality gates."
        echo "Jidoka (Principle 5): stop and fix quality first."
        return 1
    fi
    command git "$@"
}

# --- Activate aliases ---

alias cat='rsi_cat'
alias less='rsi_less'
alias head='rsi_head'
alias tail='rsi_tail'
alias bat='rsi_bat'
alias vim='rsi_vim'
alias nano='rsi_nano'
alias sed='rsi_sed'
alias tee='rsi_tee'
alias git='rsi_git'

echo "[RSI] Shell wrapper active. File operations are now enforced."
echo "[RSI] Read commands (cat/less/head/tail) record reads."
echo "[RSI] Edit commands (vim/nano/sed/tee) require prior read."
echo "[RSI] git commit --no-verify is blocked."
'''

    def _generate_tool_module(self) -> str:
        """Generate a standalone Python module for MiniMax API integration.

        This module can be imported directly by custom agents using the
        MiniMax-M2.7 API. It provides enforced tool functions that work
        with MiniMax's OpenAI-compatible function calling.
        """
        return '''#!/usr/bin/env python3
"""
RSI Tools for MiniMax-M2.7 — enforced tool functions for custom agents.

Usage with MiniMax API (OpenAI-compatible):

    import rsi_tools

    # Initialize session
    session = rsi_tools.create_session()

    # Get tool definitions for MiniMax function calling
    tool_defs = rsi_tools.get_tool_definitions()

    # Handle function calls from MiniMax
    result = rsi_tools.handle_function_call("rsi_read_file", {"file_path": "src/main.py"})

Usage with opencode:
    # Just source the shell wrapper:
    #   source opencode_wrapper.sh
    # opencode's commands then go through RSI enforcement automatically.

Usage in a custom agent loop:

    from openai import OpenAI  # MiniMax uses OpenAI-compatible API
    import rsi_tools

    client = OpenAI(
        api_key="your-minimax-key",
        base_url="https://api.minimaxi.chat/v1",
    )

    session = rsi_tools.create_session()
    tools = rsi_tools.get_tool_definitions()
    system_prompt = rsi_tools.get_system_prompt()

    messages = [{"role": "system", "content": system_prompt}]

    while True:
        response = client.chat.completions.create(
            model="MiniMax-M2.7",
            messages=messages,
            tools=tools,
        )

        choice = response.choices[0]
        if choice.finish_reason == "tool_calls":
            for call in choice.message.tool_calls:
                result = rsi_tools.handle_function_call(
                    call.function.name,
                    json.loads(call.function.arguments),
                )
                messages.append({"role": "tool", "content": result, "tool_call_id": call.id})
        else:
            break
"""

import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.tool_wrappers import RSISession, make_tool_functions, make_function_call_handler
from adapters.base import RSIRules

_session = None


def create_session(project_root: str | None = None) -> RSISession:
    """Create and start an RSI session."""
    global _session
    root = Path(project_root) if project_root else PROJECT_ROOT
    _session = RSISession(root)
    _session.start()
    return _session


def get_session() -> RSISession:
    """Get or create the current session."""
    global _session
    if _session is None:
        _session = create_session()
    return _session


def get_system_prompt() -> str:
    """Get the RSI system prompt for MiniMax-M2.7."""
    return RSIRules.generate_system_prompt()


def get_tool_definitions() -> list[dict]:
    """Get OpenAI-compatible tool definitions for MiniMax function calling."""
    raw = RSIRules.generate_tool_definitions()
    return [{"type": "function", "function": d} for d in raw]


def handle_function_call(function_name: str, arguments: dict) -> str:
    """Handle a function call from MiniMax-M2.7.

    Args:
        function_name: Name of the RSI function (e.g., "rsi_read_file")
        arguments: Function arguments as a dict

    Returns:
        Result string (success or error message)
    """
    session = get_session()
    handler = make_function_call_handler(session)
    return handler(function_name, arguments)


if __name__ == "__main__":
    # Quick test / demo
    session = create_session()
    print("RSI Session started for MiniMax-M2.7")
    print(f"Project root: {session.project_root}")
    print(f"Tool definitions: {len(get_tool_definitions())} tools")
    print(f"System prompt: {len(get_system_prompt())} chars")
    print("\\nAvailable tools:")
    for t in get_tool_definitions():
        print(f"  - {t['function']['name']}: {t['function']['description'][:60]}...")
'''

    def _generate_instructions(self) -> str:
        """Generate instructions.md for opencode (MiniMax-M2.7 CLI).

        opencode reads .opencode/instructions.md as the system prompt,
        similar to how Claude Code reads CLAUDE.md.
        """
        rules = RSIRules()
        lines = [
            "# RSI Framework — Standard Work for opencode / MiniMax-M2.7",
            "",
            rules.IDENTITY,
            "",
            "## Enforcement",
            "",
            "This project uses the RSI framework. The shell wrapper (`opencode_wrapper.sh`)",
            "intercepts file operations to enforce read-before-edit discipline.",
            "",
            "If you see `[RSI BLOCKED]` messages, it means you violated a rule.",
            "Read the file first, then edit it.",
            "",
            "## Rules",
            "",
        ]
        for rule in rules.RULES:
            lines.append(f"### {rule['name']}")
            lines.append(f"**{rule['rule']}**")
            lines.append(f"{rule['why']}")
            lines.append("")

        lines.append("## Workflow")
        lines.append("")
        lines.append("After every code change:")
        lines.append("1. `python3 scripts/rsi.py verify`")
        lines.append("2. `python3 scripts/rsi.py loop`")
        lines.append("3. `python3 scripts/rsi.py dashboard`")
        lines.append("")
        lines.append("## Commands")
        lines.append("")
        for name, cmd in rules.COMMANDS.items():
            lines.append(f"- `{cmd}`")

        return "\n".join(lines) + "\n"
