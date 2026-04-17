"""
Generic adapter — for any custom agent or CLI tool.

Generates:
1. Shell wrapper (same as MiniMax adapter — works with any CLI)
2. Python tool module (for any Python-based agent)
3. System prompt text file (for any LLM that accepts system prompts)
"""

from adapters.base import BaseAdapter, RSIRules, register_adapter
from adapters.minimax import MiniMaxAdapter


@register_adapter
class GenericAdapter(BaseAdapter):
    @property
    def platform_name(self) -> str:
        return "Generic / Custom Agent"

    @property
    def platform_id(self) -> str:
        return "generic"

    @property
    def supports_tool_enforcement(self) -> bool:
        return True

    def generate_files(self) -> dict[str, str]:
        # Reuse the MiniMax shell wrapper since it's the universal CLI interceptor
        minimax = MiniMaxAdapter(self.project_root)
        minimax_files = minimax.generate_files()

        files = {
            "opencode_wrapper.sh": minimax_files["opencode_wrapper.sh"],
            "rsi_system_prompt.txt": RSIRules.generate_system_prompt(),
            "rsi_tools.py": minimax_files["rsi_tools.py"],
        }
        return files
