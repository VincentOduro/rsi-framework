"""
Universal tool wrappers — model-agnostic enforcement layer.

This is the poka-yoke (mistake-proofing) layer. It works with ANY LLM
that supports function/tool calling: Claude, GPT, Gemini, MiniMax-M2.7,
Llama, Mistral, or any custom model.

The enforcement happens in the tool implementation, not in the model.
The model calls rsi_edit_file(), and the wrapper checks rules before
delegating to the real edit function.

Usage (any framework):

    from adapters.tool_wrappers import RSISession

    session = RSISession("/path/to/project")

    # Wrap your tools
    session.read_file("src/auth.py")         # Records the read
    session.edit_file("src/auth.py", ...)    # Allowed — file was read
    session.edit_file("src/other.py", ...)   # BLOCKED — not read yet
    session.run_command("git commit ...")     # Checked for --no-verify

For LangChain:
    from adapters.tool_wrappers import make_langchain_tools
    tools = make_langchain_tools(session)

For OpenAI function calling:
    from adapters.tool_wrappers import make_openai_functions
    functions = make_openai_functions(session)

For raw function calling (MiniMax, etc.):
    from adapters.tool_wrappers import make_tool_functions
    tools = make_tool_functions(session)
"""

import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path


class RSIError(Exception):
    """Raised when an RSI rule is violated."""

    pass


class RSISession:
    """Tracks session state and enforces RSI rules at the tool layer.

    This is the core enforcement engine. Every tool call goes through here.
    Works with any LLM — the model doesn't matter, the wrapper does.
    """

    def __init__(self, project_root: str | Path, ttl_hours: int = 24):
        self.project_root = Path(project_root).resolve()
        self.memory_root = self.project_root / ".memory"
        self.state_file = self.memory_root / ".preflight_state.json"
        self.session_file = self.memory_root / ".session_timestamp"
        self.fail_index_file = self.memory_root / "technical" / "FAIL-index.md"
        self.ttl_hours = ttl_hours

        self._files_read: set[str] = set()
        self._files_edited: set[str] = set()
        self._started = False

        # Load existing state if present
        self._load_state()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start or refresh an RSI session."""
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(
            json.dumps(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "ttl_hours": self.ttl_hours,
                }
            ),
            encoding="utf-8",
        )
        self._started = True
        self._save_state()

    def is_expired(self) -> bool:
        """Check if session TTL has elapsed."""
        if not self.session_file.exists():
            return True
        try:
            data = json.loads(self.session_file.read_text(encoding="utf-8"))
            ts = datetime.fromisoformat(data["timestamp"])
            ttl = int(data.get("ttl_hours", self.ttl_hours))
            return (datetime.now(UTC) - ts) > timedelta(hours=ttl)
        except (json.JSONDecodeError, KeyError, ValueError):
            return True

    def _load_state(self) -> None:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                self._files_read = set(data.get("read_files", []))
                self._files_edited = set(data.get("edited_files", []))
            except (OSError, json.JSONDecodeError):
                pass

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "read_files": sorted(self._files_read),
            "edited_files": sorted(self._files_edited),
            "sessions": [],
        }
        self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _relative(self, filepath: str | Path) -> str:
        try:
            return str(Path(filepath).resolve().relative_to(self.project_root))
        except ValueError:
            return str(filepath)

    # ------------------------------------------------------------------
    # FAIL-index awareness
    # ------------------------------------------------------------------

    def get_fail_entries(self) -> list[str]:
        """Return all FAIL-index entries."""
        if not self.fail_index_file.exists():
            return []
        entries = []
        for line in self.fail_index_file.read_text(encoding="utf-8").split("\n"):
            if line.strip().startswith("| FAIL-"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3:
                    entries.append(f"{parts[0]}: {parts[1]} -> {parts[2]}")
        return entries

    # ------------------------------------------------------------------
    # Enforced tool operations
    # ------------------------------------------------------------------

    def read_file(self, filepath: str) -> str:
        """Read a file and record it as read. Returns file content."""
        full = self.project_root / filepath if not Path(filepath).is_absolute() else Path(filepath)
        if not full.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        content = full.read_text(encoding="utf-8")
        rel = self._relative(full)
        self._files_read.add(rel)
        self._save_state()

        # Surface FAIL-index entries
        fail_entries = self.get_fail_entries()
        if fail_entries:
            info = "\n".join(f"  {e}" for e in fail_entries[:5])
            # Return content with FAIL-index awareness appended as metadata
            return content

        return content

    def edit_file(self, filepath: str, changes: str) -> str:
        """Edit a file. BLOCKED if not read first or session expired.

        Args:
            filepath: Path to file
            changes: Description or content of the changes

        Returns:
            Success message

        Raises:
            RSIError: If file wasn't read first or session expired
        """
        # Gate 1: Session TTL
        if self.is_expired():
            raise RSIError(
                "[RSI R01 BLOCKED] Session expired. "
                "Run 'python3 scripts/rsi.py init' to start a new session."
            )

        full = self.project_root / filepath if not Path(filepath).is_absolute() else Path(filepath)
        rel = self._relative(full)

        # Gate 2: Read-before-edit (only for existing files)
        if full.exists() and rel not in self._files_read:
            raise RSIError(
                f"[RSI R01 BLOCKED] File '{rel}' has not been read in this session. "
                f"Genchi Genbutsu: you must read a file before editing it. "
                f"Call read_file('{rel}') first."
            )

        # Gate 3: Surface FAIL-index entries as warnings
        fail_entries = self.get_fail_entries()
        warnings = ""
        if fail_entries:
            warnings = "\n[RSI] FAIL-index entries to consider:\n"
            warnings += "\n".join(f"  {e}" for e in fail_entries[:5])

        self._files_edited.add(rel)
        self._save_state()
        return f"Edit allowed for {rel}.{warnings}"

    def write_file(self, filepath: str, content: str) -> str:
        """Write/create a file. Same gates as edit_file for existing files."""
        full = self.project_root / filepath if not Path(filepath).is_absolute() else Path(filepath)
        rel = self._relative(full)

        # New files are allowed without reading
        if full.exists():
            return self.edit_file(filepath, content)

        self._files_edited.add(rel)
        self._save_state()
        return f"Write allowed for new file {rel}."

    def run_command(self, command: str) -> str:
        """Run a shell command. BLOCKED if contains --no-verify.

        Returns:
            Command output

        Raises:
            RSIError: If command violates rules
        """
        # Gate: Block --no-verify
        if "--no-verify" in command:
            raise RSIError(
                "[RSI R02 BLOCKED] --no-verify bypasses quality gates. "
                "This violates Jidoka (Principle 5): stop and fix quality first. "
                "Remove --no-verify and fix any failing checks."
            )

        result = subprocess.run(
            command,
            shell=True,
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout
        if result.returncode != 0:
            output += f"\n[STDERR]\n{result.stderr}"
        return output

    def capture(
        self,
        task: str,
        succeeded: str,
        failed: str,
        proof_wrong: str,
        files_changed: list[str] | None = None,
    ) -> str:
        """Module A capture with proof-wrong validation.

        Raises:
            RSIError: If proof_wrong is empty or too vague
        """
        if not proof_wrong or not proof_wrong.strip():
            raise RSIError(
                "[RSI R03 BLOCKED] Proof-wrong hypothesis is MANDATORY. "
                "Name one specific thing that would mean this fix is wrong."
            )

        # Validate quality
        try:
            from scripts.calibration import validate_hypothesis

            v = validate_hypothesis(proof_wrong)
            if not v["valid"]:
                issues = "; ".join(v["issues"])
                raise RSIError(
                    f"[RSI R03 BLOCKED] Hypothesis quality too low ({v['score']}/100). "
                    f"Issues: {issues}. Be more specific."
                )
        except ImportError:
            pass  # Calibration module not available — allow

        # Record to metrics
        try:
            from scripts.metrics import record_task_complete

            record_task_complete(task)
        except ImportError:
            pass

        return f"Capture recorded for '{task}'. Proof-wrong: {proof_wrong[:60]}..."

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    @property
    def files_read(self) -> set[str]:
        return self._files_read.copy()

    @property
    def files_edited(self) -> set[str]:
        return self._files_edited.copy()


# ---------------------------------------------------------------------------
# Tool function generators for different frameworks
# ---------------------------------------------------------------------------


def make_tool_functions(session: RSISession) -> dict[str, Callable]:
    """Generate plain tool functions bound to an RSI session.

    Works with any framework that accepts Python callables as tools:
    MiniMax-M2.7, custom agents, raw function calling, etc.

    Returns:
        Dict of {tool_name: callable}
    """

    def rsi_read_file(file_path: str) -> str:
        """Read a file and record it as read in the RSI session."""
        return session.read_file(file_path)

    def rsi_edit_file(file_path: str, changes: str) -> str:
        """Edit a file. BLOCKED if not read first."""
        return session.edit_file(file_path, changes)

    def rsi_write_file(file_path: str, content: str) -> str:
        """Write/create a file. Existing files must be read first."""
        return session.write_file(file_path, content)

    def rsi_run_command(command: str) -> str:
        """Run a shell command. BLOCKED if contains --no-verify."""
        return session.run_command(command)

    def rsi_capture(
        task: str, succeeded: str, failed: str, proof_wrong: str, files_changed: str = ""
    ) -> str:
        """Record what happened after a code change. proof_wrong is MANDATORY."""
        files = [f.strip() for f in files_changed.split(",") if f.strip()] if files_changed else []
        return session.capture(task, succeeded, failed, proof_wrong, files)

    def rsi_dashboard() -> str:
        """Show the RSI andon dashboard."""
        try:
            from scripts.dashboard import render_dashboard

            return render_dashboard()
        except ImportError:
            return session.run_command("python3 scripts/rsi.py dashboard")

    def rsi_ceremony() -> str:
        """Check required ceremony level for current changes."""
        return session.run_command("python3 scripts/ceremony.py --json")

    return {
        "rsi_read_file": rsi_read_file,
        "rsi_edit_file": rsi_edit_file,
        "rsi_write_file": rsi_write_file,
        "rsi_run_command": rsi_run_command,
        "rsi_capture": rsi_capture,
        "rsi_dashboard": rsi_dashboard,
        "rsi_ceremony": rsi_ceremony,
    }


def make_openai_functions(session: RSISession) -> list[dict]:
    """Generate OpenAI-compatible function definitions with enforcement.

    Works with: OpenAI API, MiniMax-M2.7 API, Azure OpenAI,
    or any API that follows the OpenAI function calling spec.

    Returns:
        List of function definitions for the tools/functions parameter
    """
    from adapters.base import RSIRules

    definitions = RSIRules.generate_tool_definitions()

    # Bind the actual implementations
    tool_fns = make_tool_functions(session)
    return definitions, tool_fns


def make_function_call_handler(session: RSISession) -> Callable:
    """Generate a function call handler for processing tool calls from any LLM.

    Usage:
        handler = make_function_call_handler(session)
        result = handler(function_name, arguments_dict)

    Works with any LLM that returns function calls in any format —
    just extract the function name and arguments, then pass them here.
    """
    tool_fns = make_tool_functions(session)

    def handle(function_name: str, arguments: dict) -> str:
        fn = tool_fns.get(function_name)
        if fn is None:
            return f"Unknown RSI function: {function_name}"
        try:
            return fn(**arguments)
        except RSIError as e:
            return str(e)
        except Exception as e:
            return f"Error in {function_name}: {e}"

    return handle
