"""
LangChain / LangGraph adapter — tool wrappers as LangChain tools.

Full tool enforcement via RSISession.
Works with any LLM backend LangChain supports.
"""

from adapters.base import BaseAdapter, register_adapter


@register_adapter
class LangChainAdapter(BaseAdapter):
    @property
    def platform_name(self) -> str:
        return "LangChain / LangGraph"

    @property
    def platform_id(self) -> str:
        return "langchain"

    @property
    def supports_tool_enforcement(self) -> bool:
        return True

    def generate_files(self) -> dict[str, str]:
        return {"rsi_langchain_tools.py": self._generate_tools()}

    def _generate_tools(self) -> str:
        return '''#!/usr/bin/env python3
"""
RSI-enforced tools for LangChain / LangGraph.

Usage:
    from rsi_langchain_tools import get_rsi_tools

    tools = get_rsi_tools()
    agent = create_react_agent(llm, tools)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.tool_wrappers import RSISession, RSIError


def get_rsi_tools(project_root: str | None = None):
    """Create LangChain-compatible RSI tools.

    Requires: pip install langchain-core
    """
    from langchain_core.tools import tool

    root = Path(project_root) if project_root else PROJECT_ROOT
    session = RSISession(root)
    session.start()

    @tool
    def rsi_read_file(file_path: str) -> str:
        """Read a file and record it as read in the RSI session.
        You MUST use this to read files — it satisfies the read-before-edit requirement."""
        return session.read_file(file_path)

    @tool
    def rsi_edit_file(file_path: str, changes: str) -> str:
        """Edit a file. BLOCKED if the file has not been read with rsi_read_file first."""
        return session.edit_file(file_path, changes)

    @tool
    def rsi_write_file(file_path: str, content: str) -> str:
        """Write or create a file. Existing files must be read first."""
        return session.write_file(file_path, content)

    @tool
    def rsi_run_command(command: str) -> str:
        """Run a shell command. BLOCKED if it contains --no-verify."""
        return session.run_command(command)

    @tool
    def rsi_capture(task: str, succeeded: str, failed: str,
                    proof_wrong: str) -> str:
        """Record what happened after a code change.
        proof_wrong is MANDATORY: name one specific thing that could prove this change wrong."""
        return session.capture(task, succeeded, failed, proof_wrong)

    return [rsi_read_file, rsi_edit_file, rsi_write_file, rsi_run_command, rsi_capture]


if __name__ == "__main__":
    tools = get_rsi_tools()
    print(f"Created {len(tools)} RSI-enforced LangChain tools:")
    for t in tools:
        print(f"  - {t.name}: {t.description[:60]}...")
'''
