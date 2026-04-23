"""RSI Framework adapters — make enforcement work with any AI agent platform."""

from adapters.base import AVAILABLE_ADAPTERS, BaseAdapter, RSIRules

# Import all adapter modules so they self-register via @register_adapter
import adapters.aider  # noqa: F401
import adapters.claude_code  # noqa: F401
import adapters.copilot  # noqa: F401
import adapters.cursor  # noqa: F401
import adapters.generic  # noqa: F401
import adapters.kimi  # noqa: F401
import adapters.langchain_adapter  # noqa: F401
import adapters.minimax  # noqa: F401
import adapters.openai_agents  # noqa: F401

__all__ = ["AVAILABLE_ADAPTERS", "BaseAdapter", "RSIRules"]
