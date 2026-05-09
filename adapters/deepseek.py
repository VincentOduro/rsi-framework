"""
DeepSeek V4 adapter — enforcement for opencode + DeepSeek models.

DeepSeek exposes an OpenAI-compatible API at https://api.deepseek.com.
Enforcement works through the same two layers as MiniMax:

1. **Shell wrapper** (deepseek_wrapper.sh): Intercepts file operations at the OS
   level for CLI agents that don't have native tool hook APIs.

2. **Python tool wrappers** (tool_wrappers.py): For custom agents built on
   DeepSeek's API directly, use RSISession to wrap tool implementations.

3. **System prompt**: Injected into the model's context to reinforce
   behavioral rules that can't be enforced at the tool layer.

Requires: DEEPSEEK_API_KEY environment variable.
"""

from adapters.base import BaseAdapter, RSIRules, register_adapter


@register_adapter
class DeepSeekAdapter(BaseAdapter):
    @property
    def platform_name(self) -> str:
        return "DeepSeek V4 / deepseek-v4-flash"

    @property
    def platform_id(self) -> str:
        return "deepseek"

    @property
    def supports_tool_enforcement(self) -> bool:
        return True

    def generate_files(self) -> dict[str, str]:
        return {
            "deepseek_wrapper.sh": self._generate_shell_wrapper(),
            "rsi_tools.py": self._generate_tool_module(),
            ".opencode/instructions.md": self._generate_instructions(),
        }

    def _generate_shell_wrapper(self) -> str:
        return r"""#!/bin/bash
# RSI Framework — Shell wrapper for DeepSeek V4
#
# Source this file to activate enforcement in your shell:
#   source kimi_wrapper.sh
#
# Intercepts file operations so the RSI framework can enforce
# read-before-edit discipline regardless of which AI model is driving.

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
}

# Wrap read commands
cat() { command cat "$@" && _rsi_record_read "$1"; }
less() { command less "$@" && _rsi_record_read "$1"; }
head() { command head "$@" && _rsi_record_read "$1"; }
tail() { command tail "$@" && _rsi_record_read "$1"; }
bat() { command bat "$@" 2>/dev/null && _rsi_record_read "$1"; }

# Wrap edit commands
vim() {
    _rsi_check_read "$1" || return 1
    command vim "$@"
}
nano() {
    _rsi_check_read "$1" || return 1
    command nano "$@"
}
sed() {
    if echo "$*" | grep -q '\-i'; then
        local f="${@: -1}"
        _rsi_check_read "$f" || return 1
    fi
    command sed "$@"
}

# Block --no-verify
git() {
    if echo "$*" | grep -q '\-\-no-verify'; then
        echo '[RSI BLOCKED] --no-verify bypasses quality gates.'
        return 1
    fi
    command git "$@"
}

export -f cat less head tail bat vim nano sed git
echo '[RSI] DeepSeek shell wrapper active.'
"""

    def _generate_tool_module(self) -> str:
        return '''"""
RSI tool wrappers for DeepSeek V4 function-calling agents.

Usage:
    from rsi_tools import RSISession
    session = RSISession()
    content = session.read_file("src/foo.py")
    session.edit_file("src/foo.py", new_content)
"""

from adapters.tool_wrappers import RSISession

__all__ = ["RSISession"]
'''

    def _generate_instructions(self) -> str:
        rules = RSIRules()
        lines = [
            "# RSI Framework — Standard Work for DeepSeek V4",
            "",
            rules.IDENTITY,
            "",
            "## Enforcement",
            "",
            "This project uses the RSI framework. The shell wrapper (`deepseek_wrapper.sh`)",
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
        lines += [
            "## API",
            "- Base URL: https://api.deepseek.com",
            "- Default model: deepseek-v4-flash",
            "- Auth: Bearer $DEEPSEEK_API_KEY",
            "",
            "## Response format",
            "Return ONLY valid JSON matching the WorkerResult schema.",
            "No prose outside the JSON block.",
        ]
        return "\n".join(lines) + "\n"
