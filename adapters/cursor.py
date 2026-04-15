"""
Cursor adapter — generates .cursorrules.

Cursor has no tool interception API. Enforcement is prompt-only,
backed by git hooks and CI which ARE enforceable.
"""

from adapters.base import BaseAdapter, RSIRules, register_adapter


@register_adapter
class CursorAdapter(BaseAdapter):

    @property
    def platform_name(self) -> str:
        return "Cursor"

    @property
    def platform_id(self) -> str:
        return "cursor"

    @property
    def supports_tool_enforcement(self) -> bool:
        return False  # Cursor has no tool hook API

    def generate_files(self) -> dict[str, str]:
        return {".cursorrules": self._generate_cursorrules()}

    def _generate_cursorrules(self) -> str:
        rules = RSIRules()
        lines = [
            "# RSI Framework Rules for Cursor",
            "",
            rules.IDENTITY,
            "",
        ]
        for rule in rules.RULES:
            lines.append(f"## {rule['name']}")
            lines.append(rule['rule'])
            lines.append("")

        lines.append("## After every code change, run:")
        lines.append("```")
        lines.append("python3 scripts/rsi.py loop")
        lines.append("```")
        lines.append("")
        lines.append("## Anti-patterns")
        for ap in rules.ANTI_PATTERNS:
            lines.append(f"- {ap}")

        return "\n".join(lines) + "\n"
