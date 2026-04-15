"""
Aider adapter — generates .aider.conf.yml and conventions file.

Aider supports conventions files for behavioral instructions.
Partial tool enforcement via the shell wrapper.
"""

from adapters.base import BaseAdapter, RSIRules, register_adapter


@register_adapter
class AiderAdapter(BaseAdapter):

    @property
    def platform_name(self) -> str:
        return "Aider"

    @property
    def platform_id(self) -> str:
        return "aider"

    def generate_files(self) -> dict[str, str]:
        return {
            "CONVENTIONS.md": self._generate_conventions(),
            ".aider.conf.yml": self._generate_config(),
        }

    def _generate_conventions(self) -> str:
        rules = RSIRules()
        lines = [
            "# RSI Framework Conventions for Aider",
            "",
            rules.IDENTITY,
            "",
        ]
        for rule in rules.RULES:
            lines.append(f"## {rule['name']}")
            lines.append(rule['rule'])
            lines.append("")

        lines.append("## After every code change")
        lines.append("Run: `python3 scripts/rsi.py loop`")
        lines.append("")
        lines.append("## Shell wrapper")
        lines.append("Source opencode_wrapper.sh for file operation enforcement:")
        lines.append("```bash")
        lines.append("source opencode_wrapper.sh")
        lines.append("```")

        return "\n".join(lines) + "\n"

    def _generate_config(self) -> str:
        return """# Aider configuration for RSI framework
conventions-file: CONVENTIONS.md
auto-commits: false
"""
