"""
Base adapter and rules engine — single source of truth for all platforms.

Every adapter generates platform-specific files from this shared rule set.
The rules never change between platforms. The enforcement mechanism does.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


# ---------------------------------------------------------------------------
# RSI Rules — the single source of truth
# ---------------------------------------------------------------------------

class RSIRules:
    """All framework rules as structured data. Every adapter reads from here."""

    IDENTITY = (
        "You are operating under the Recursive Self-Improvement (RSI) framework, "
        "built on Toyota Production System principles. These rules are mandatory."
    )

    RULES = [
        {
            "id": "R01",
            "name": "Genchi Genbutsu — Read Before Edit",
            "principle": "Toyota Principle 12",
            "rule": "NEVER edit a file without reading it first in this session.",
            "why": "The most common source of bugs is editing code you only partially understand.",
            "enforcement": "tool_block",
        },
        {
            "id": "R02",
            "name": "Jidoka — Stop and Fix Quality First",
            "principle": "Toyota Principle 5",
            "rule": "NEVER skip verification. NEVER bypass quality gates.",
            "why": "Quality problems caught early cost 10x less than those found later.",
            "enforcement": "tool_block",
        },
        {
            "id": "R03",
            "name": "Hansei — Reflect After Every Change",
            "principle": "Toyota Principle 14",
            "rule": "ALWAYS answer 'What could prove this WRONG?' with a specific, testable hypothesis.",
            "why": "Forces adversarial thinking about your own code.",
            "enforcement": "structured_output",
        },
        {
            "id": "R04",
            "name": "Kaizen — Every Change Goes Through the Loop",
            "principle": "Toyota Principle 2",
            "rule": "ALWAYS run the A->B->C loop (capture, review, optimize) after code changes.",
            "why": "Skipping the loop means failures are forgotten and patterns aren't captured.",
            "enforcement": "git_hook",
        },
        {
            "id": "R05",
            "name": "Muda — Eliminate Waste",
            "principle": "Toyota Principle 3",
            "rule": "Every finding must be actionable. Track signal-to-noise ratio.",
            "why": "Generating noise findings wastes time and erodes trust in the framework.",
            "enforcement": "metrics",
        },
        {
            "id": "R06",
            "name": "Heijunka — Right-Sized Ceremony",
            "principle": "Toyota Principle 4",
            "rule": "Match ceremony to change scope. Run ceremony.py to classify.",
            "why": "Over-ceremony on small changes is waste. Under-ceremony on large changes is risk.",
            "enforcement": "prompt",
        },
        {
            "id": "R07",
            "name": "Andon — Visual Management",
            "principle": "Toyota Principle 7",
            "rule": "Check the dashboard regularly. Act on waste indicators.",
            "why": "Hidden problems compound. Visible problems get fixed.",
            "enforcement": "prompt",
        },
    ]

    CEREMONY_LEVELS = {
        "minimal": {
            "when": "Docs/config only, <20 lines",
            "steps": ["Capture what changed", "Proof-wrong hypothesis", "Commit with memory update"],
        },
        "standard": {
            "when": "Normal code changes, 1-5 files",
            "steps": ["Self-verify", "Module A: capture", "Module B: review (2 bugs, 2 opts, 1 maint)", "Module C: optimize", "Commit"],
        },
        "thorough": {
            "when": "5+ files or risk factors present",
            "steps": ["Self-verify", "Module A", "Module B", "Review open hypotheses", "Check FAIL-index", "Module C", "Commit"],
        },
        "major": {
            "when": "10+ files or cross-module changes",
            "steps": ["Self-verify", "Module A", "Module B (3+ each)", "All open hypotheses", "All FAIL entries", "5-Whys if defect", "Architecture review", "Module C", "Commit"],
        },
    }

    METRICS_TARGETS = {
        "first_pass_yield": {"target": ">80%", "command": "python3 scripts/metrics.py yield"},
        "defect_rate": {"target": "<0.3 per task", "command": "python3 scripts/metrics.py defects"},
        "signal_ratio": {"target": ">50%", "command": "python3 scripts/metrics.py signal"},
        "hypothesis_quality": {"target": ">60/100 avg", "command": "python3 scripts/calibration.py score"},
    }

    ANTI_PATTERNS = [
        "Don't edit from memory. Read the file. Every time.",
        "Don't skip ceremony because 'it's small.' Run ceremony.py.",
        "Don't generate vague hypotheses. 'It might break' is not a hypothesis.",
        "Don't ignore failing tests. Fix the test or fix the code.",
        "Don't bypass hooks or use --no-verify.",
        "Don't generate noise. Every finding should be actionable.",
        "Don't skip root cause analysis when a bug is found post-commit.",
        "Don't commit without a memory update.",
    ]

    COMMANDS = {
        "init": "python3 scripts/rsi.py init",
        "dashboard": "python3 scripts/rsi.py dashboard",
        "loop": "python3 scripts/rsi.py loop",
        "verify": "python3 scripts/rsi.py verify",
        "ceremony": "python3 scripts/rsi.py ceremony",
        "calibrate_score": "python3 scripts/calibration.py score",
        "calibrate_open": "python3 scripts/calibration.py open",
        "root_cause": "python3 scripts/rsi.py root-cause interactive",
        "metrics_summary": "python3 scripts/rsi.py metrics summary",
        "ci": "python3 scripts/rsi.py ci",
    }

    @classmethod
    def generate_system_prompt(cls) -> str:
        """Generate a complete system prompt from all rules."""
        lines = [cls.IDENTITY, ""]

        lines.append("## Mandatory Rules\n")
        for rule in cls.RULES:
            lines.append(f"### {rule['name']} ({rule['principle']})")
            lines.append(f"**Rule:** {rule['rule']}")
            lines.append(f"**Why:** {rule['why']}")
            lines.append("")

        lines.append("## Ceremony Levels\n")
        for level, info in cls.CEREMONY_LEVELS.items():
            lines.append(f"### {level.upper()}: {info['when']}")
            for i, step in enumerate(info["steps"], 1):
                lines.append(f"  {i}. {step}")
            lines.append("")

        lines.append("## Metrics Targets\n")
        for metric, info in cls.METRICS_TARGETS.items():
            lines.append(f"- **{metric}**: {info['target']} — check with `{info['command']}`")
        lines.append("")

        lines.append("## Anti-Patterns (NEVER do these)\n")
        for ap in cls.ANTI_PATTERNS:
            lines.append(f"- {ap}")
        lines.append("")

        lines.append("## Commands\n")
        for name, cmd in cls.COMMANDS.items():
            lines.append(f"- `{cmd}`")

        return "\n".join(lines)

    @classmethod
    def generate_tool_definitions(cls) -> list[dict]:
        """Generate tool/function definitions for LLMs that support function calling."""
        return [
            {
                "name": "rsi_read_file",
                "description": "Read a file and record it as read in the RSI session. You MUST use this instead of raw file reading to satisfy the read-before-edit requirement.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the file to read"},
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "rsi_edit_file",
                "description": "Edit a file. BLOCKED if the file hasn't been read with rsi_read_file first. BLOCKED if session is expired.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the file to edit"},
                        "changes": {"type": "string", "description": "The changes to make"},
                    },
                    "required": ["file_path", "changes"],
                },
            },
            {
                "name": "rsi_run_command",
                "description": "Run a shell command. BLOCKED if command contains --no-verify.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"},
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "rsi_capture",
                "description": "Record what happened after a code change (Module A). Requires proof-wrong hypothesis.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "succeeded": {"type": "string"},
                        "failed": {"type": "string"},
                        "proof_wrong": {"type": "string", "description": "MANDATORY: Specific, testable hypothesis about what could make this change wrong"},
                        "files_changed": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["task", "succeeded", "failed", "proof_wrong"],
                },
            },
        ]


# ---------------------------------------------------------------------------
# Base Adapter
# ---------------------------------------------------------------------------

class BaseAdapter(ABC):
    """Abstract base for platform-specific adapters."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or PROJECT_ROOT
        self.rules = RSIRules()

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform name."""
        pass

    @property
    @abstractmethod
    def platform_id(self) -> str:
        """Short identifier (e.g., 'claude-code', 'cursor', 'minimax')."""
        pass

    @abstractmethod
    def generate_files(self) -> dict[str, str]:
        """Generate platform-specific files.
        Returns {relative_path: content} dict."""
        pass

    @property
    def supports_tool_enforcement(self) -> bool:
        """Whether this platform supports tool-layer enforcement."""
        return False

    def install(self) -> list[str]:
        """Write generated files to disk. Returns list of created file paths."""
        files = self.generate_files()
        created = []
        for rel_path, content in files.items():
            full_path = self.project_root / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            created.append(rel_path)
        return created


# ---------------------------------------------------------------------------
# Adapter Registry
# ---------------------------------------------------------------------------

AVAILABLE_ADAPTERS: dict[str, type] = {}


def register_adapter(cls: type) -> type:
    """Decorator to register an adapter in the global registry."""
    adapter = cls()
    AVAILABLE_ADAPTERS[adapter.platform_id] = cls
    return cls
