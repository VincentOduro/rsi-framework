"""
GitHub Copilot adapter — generates .github/copilot-instructions.md.

Copilot reads this file for repo-level custom instructions.
No tool enforcement — prompt + git hooks + CI only.
"""

from adapters.base import BaseAdapter, RSIRules, register_adapter


@register_adapter
class CopilotAdapter(BaseAdapter):

    @property
    def platform_name(self) -> str:
        return "GitHub Copilot"

    @property
    def platform_id(self) -> str:
        return "copilot"

    def generate_files(self) -> dict[str, str]:
        return {".github/copilot-instructions.md": self._generate_instructions()}

    def _generate_instructions(self) -> str:
        rules = RSIRules()
        lines = [
            "# RSI Framework — Instructions for GitHub Copilot",
            "",
            rules.IDENTITY,
            "",
        ]
        for rule in rules.RULES:
            lines.append(f"## {rule['name']}")
            lines.append(rule['rule'])
            lines.append("")

        lines.append("## Required workflow after code changes")
        lines.append("Run `python3 scripts/rsi.py loop` to execute the A->B->C improvement loop.")
        lines.append("")
        lines.append("## Commands")
        for name, cmd in rules.COMMANDS.items():
            lines.append(f"- `{cmd}`")

        return "\n".join(lines) + "\n"
