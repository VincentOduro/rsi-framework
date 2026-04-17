"""
Claude Code adapter — generates .claude/settings.json and CLAUDE.md.

Claude Code has native PreToolUse/PostToolUse hooks.
This is the strongest enforcement path — hooks intercept at the tool layer
before the operation happens. The model cannot bypass them.
"""

from adapters.base import BaseAdapter, RSIRules, register_adapter


@register_adapter
class ClaudeCodeAdapter(BaseAdapter):
    @property
    def platform_name(self) -> str:
        return "Claude Code"

    @property
    def platform_id(self) -> str:
        return "claude-code"

    @property
    def supports_tool_enforcement(self) -> bool:
        return True

    def generate_files(self) -> dict[str, str]:
        return {
            "CLAUDE.md": self._generate_claude_md(),
            ".claude/settings.json": self._generate_settings(),
        }

    def _generate_claude_md(self) -> str:
        rules = RSIRules()
        lines = [
            "# RSI Framework — Agent Standard Work",
            "",
            rules.IDENTITY,
            "",
            "## AI Model Compatibility",
            "",
            "This framework is **model-agnostic**. It works with any AI coding assistant:",
            "",
            "| Model | Setup Command | How It Works |",
            "|-------|--------------|--------------|",
            "| Claude Code | `python3 scripts/setup.py --model claude` | `.claude/settings.json` PreToolUse/PostToolUse hooks |",
            "| opencode / MiniMax-M2.7 | `python3 scripts/setup.py --model opencode` | Shell wrapper intercepts file ops |",
            "| Any CLI AI tool | `python3 scripts/setup.py --model shell` | Shell integrator wraps commands |",
            "",
            "If using opencode or another CLI tool, ensure the wrapper/alias is active in your shell.",
            "The core A->B->C loop, metrics, and calibration work identically regardless of which AI model you use.",
            "",
        ]

        lines.append("## The Non-Negotiable Rules\n")
        for rule in rules.RULES:
            lines.append(f"### {rule['id']}. {rule['name']} ({rule['principle']})\n")
            lines.append(f"**{rule['rule']}**\n")
            lines.append(f"{rule['why']}\n")

        lines.append("## Ceremony Levels\n")
        lines.append("| Level | When | Steps |")
        lines.append("|---|---|---|")
        for level, info in rules.CEREMONY_LEVELS.items():
            steps = " -> ".join(info["steps"][:3]) + ("..." if len(info["steps"]) > 3 else "")
            lines.append(f"| {level} | {info['when']} | {steps} |")
        lines.append("")

        lines.append("## Metrics Targets\n")
        lines.append("| Metric | Target | Command |")
        lines.append("|---|---|---|")
        for metric, info in rules.METRICS_TARGETS.items():
            lines.append(f"| {metric} | {info['target']} | `{info['command']}` |")
        lines.append("")

        lines.append("## Anti-Patterns\n")
        for ap in rules.ANTI_PATTERNS:
            lines.append(f"- {ap}")
        lines.append("")

        lines.append("## Quick Reference\n")
        lines.append("```bash")
        lines.append("python3 scripts/rsi.py init         # Start session")
        lines.append("python3 scripts/rsi.py dashboard    # Andon board")
        lines.append("python3 scripts/rsi.py loop         # Full A->B->C")
        lines.append("python3 scripts/rsi.py ceremony     # Check ceremony level")
        lines.append("python3 scripts/rsi.py verify       # Self-verify")
        lines.append("python3 scripts/rsi.py calibrate score  # Calibration")
        lines.append("python3 scripts/rsi.py root-cause interactive  # 5-Whys")
        lines.append("python3 scripts/rsi.py ci           # CI gate")
        lines.append("```")

        return "\n".join(lines) + "\n"

    def _generate_settings(self) -> str:
        import json

        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Read",
                        "hooks": [
                            {"type": "command", "command": "python3 scripts/hooks.py pre-read"}
                        ],
                    },
                    {
                        "matcher": "Edit|Write",
                        "hooks": [
                            {"type": "command", "command": "python3 scripts/hooks.py pre-edit"}
                        ],
                    },
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "python3 scripts/hooks.py pre-bash"}
                        ],
                    },
                ],
                "PostToolUse": [
                    {
                        "matcher": "Edit|Write",
                        "hooks": [
                            {"type": "command", "command": "python3 scripts/hooks.py post-edit"}
                        ],
                    },
                ],
            }
        }
        return json.dumps(settings, indent=2) + "\n"
