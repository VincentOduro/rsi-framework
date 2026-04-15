"""
OpenAI Agents SDK adapter — tool wrappers for OpenAI function calling.

Full tool enforcement via RSISession wrapped tools.
Works with GPT-4, GPT-4o, o1, o3, or any model via the OpenAI API.
"""

from adapters.base import BaseAdapter, RSIRules, register_adapter


@register_adapter
class OpenAIAgentsAdapter(BaseAdapter):

    @property
    def platform_name(self) -> str:
        return "OpenAI Agents SDK"

    @property
    def platform_id(self) -> str:
        return "openai-agents"

    @property
    def supports_tool_enforcement(self) -> bool:
        return True

    def generate_files(self) -> dict[str, str]:
        return {"rsi_openai_agent.py": self._generate_agent_template()}

    def _generate_agent_template(self) -> str:
        return '''#!/usr/bin/env python3
"""
RSI-enforced agent template for OpenAI API.

Replace YOUR_API_KEY and customize the agent loop.
All file operations go through RSI enforcement.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.tool_wrappers import RSISession, make_function_call_handler
from adapters.base import RSIRules


def create_agent():
    """Create an RSI-enforced agent using OpenAI API."""
    # Requires: pip install openai
    from openai import OpenAI

    client = OpenAI()  # Uses OPENAI_API_KEY env var
    session = RSISession(PROJECT_ROOT)
    session.start()
    handler = make_function_call_handler(session)
    tools = [{"type": "function", "function": d} for d in RSIRules.generate_tool_definitions()]
    system_prompt = RSIRules.generate_system_prompt()

    messages = [{"role": "system", "content": system_prompt}]

    def chat(user_message: str) -> str:
        messages.append({"role": "user", "content": user_message})

        while True:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=tools,
            )
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls":
                messages.append(choice.message)
                for call in choice.message.tool_calls:
                    result = handler(call.function.name, json.loads(call.function.arguments))
                    messages.append({"role": "tool", "content": result, "tool_call_id": call.id})
            else:
                reply = choice.message.content or ""
                messages.append({"role": "assistant", "content": reply})
                return reply

    return chat


if __name__ == "__main__":
    chat = create_agent()
    print("RSI-enforced OpenAI agent ready.")
    print("Type messages (Ctrl+C to exit):")
    while True:
        try:
            msg = input("\\n> ")
            print(chat(msg))
        except (KeyboardInterrupt, EOFError):
            break
'''
