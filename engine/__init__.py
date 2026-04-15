"""
RSI Engine — orchestrator-worker architecture for AI-assisted development.

Claude (Opus/Sonnet) orchestrates. MiniMax-M2.7 executes.
RSI enforcement lives in the bus between them.

Neither model touches files directly. The bus enforces all rules.
"""
