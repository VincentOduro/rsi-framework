# RSI Framework — AI Model Adapters

This directory contains integration adapters for different AI models. The RSI framework core (A→B→C loop, metrics, calibration) is model-agnostic. These adapters enforce the tool-layer rules (read-before-edit, session tracking) for specific AI tools.

## Quick Reference

| AI Model | Integration Method | Setup Command |
|----------|-------------------|---------------|
| Claude Code | `.claude/settings.json` | `python3 scripts/setup.py --model claude` |
| opencode / MiniMax-M2.7 | Shell wrapper | `python3 scripts/setup.py --model opencode` |
| Generic CLI tool | Shell wrapper | `python3 scripts/setup.py --model shell` |
| MCP-based tool | MCP hooks spec | See MCP section below |

## Per-Model Setup

### Claude Code (Default)

Claude Code has built-in hook support via `.claude/settings.json`.

```bash
# Install for Claude Code
python3 scripts/setup.py --model claude

# Or manually: hooks are already configured in .claude/settings.json
# Just run setup to ensure hooks are installed
```

The hooks are defined in `.claude/settings.json` and invoke:
- `universal_hook.py claude pre-read` — on file read
- `universal_hook.py claude pre-edit` — on file edit/write
- `universal_hook.py claude post-edit` — after file edit/write
- `universal_hook.py claude pre-bash` — on bash commands

### opencode / MiniMax-M2.7

opencode is a CLI-based AI coding tool. Integration is via shell wrapper.

```bash
# Install the opencode adapter
python3 scripts/setup.py --model opencode

# This copies the wrapper to your project root and creates an alias
```

Manual setup:
```bash
# Option 1: Direct wrapper (add to PATH)
alias opencode='./scripts/adapters/opencode_adapter.sh'

# Option 2: Wrapper script in project root
cp scripts/adapters/opencode_adapter.sh ./opencode_wrapper.sh
chmod +x ./opencode_wrapper.sh
alias opencode='./opencode_wrapper.sh'
```

How it works:
1. The wrapper intercepts `opencode read <file>` and records the read
2. Before `opencode edit <file>`, it checks if the file was read
3. After `opencode edit <file>`, it records the edit
4. For `opencode apply <patch>`, similar checks apply

### Generic CLI AI Tools

For any CLI-based AI tool (Aider, etc.), use the shell integrator:

```bash
# Install generic shell integration
python3 scripts/setup.py --model shell

# Wrap your AI tool:
./scripts/adapters/shell_integrator.py wrap -- <your-ai-tool> [args]
```

Or use as a Python module:
```python
from scripts.adapters.shell_integrator import ShellIntegrator

integrator = ShellIntegrator(project_root="/path/to/project")
integrator.record_read("src/main.py")
integrator.check_edit_allowed("src/main.py")
integrator.record_edit("src/main.py")
```

### MCP-Based Tools

If your AI tool uses the Model Context Protocol (MCP), you can define hooks in the MCP server config:

```json
{
  "hooks": {
    "tools/read": {
      "pre": ["python3 scripts/universal_hook.py generic pre-read --file ${path}"],
      "post": []
    },
    "tools/edit": {
      "pre": ["python3 scripts/universal_hook.py generic pre-edit --file ${path}"],
      "post": ["python3 scripts/universal_hook.py generic post-edit --file ${path}"]
    }
  }
}
```

## Universal Hook Interface

The `universal_hook.py` script provides a model-agnostic interface:

```bash
# Claude Code format
echo '{"tool_input": {"file_path": "foo.py"}}' | python3 scripts/universal_hook.py claude pre-read

# opencode format
python3 scripts/universal_hook.py opencode pre-read --file foo.py

# Shell wrapper format
python3 scripts/universal_hook.py shell record-read --file foo.py
python3 scripts/universal_hook.py shell check-edit --file foo.py
python3 scripts/universal_hook.py shell record-edit --file foo.py
python3 scripts/universal_hook.py shell check-bash --command "git commit -m 'msg'"

# Generic (environment variables)
export RSI_HOOK_MODE=pre-edit
export RSI_TOOL_INPUT='{"file_path":"foo.py"}'
python3 scripts/universal_hook.py generic
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `RSI_PROJECT_ROOT` | Project root directory | Auto-detected |
| `RSI_SESSION_TTL_HOURS` | Session TTL in hours | 24 |
| `RSI_HOOK_MODE` | Hook mode for generic integration | - |
| `RSI_TOOL_INPUT` | JSON tool input for generic integration | - |

## Adding Support for a New AI Model

1. Create an adapter in this directory (e.g., `newmodel_adapter.sh` or `newmodel_adapter.py`)
2. Your adapter should:
   - Intercept file read/edit/write operations
   - Call `universal_hook.py <model> <action>` with appropriate arguments
   - Handle the AI tool's specific command-line interface
3. Add setup logic to `setup.py` (see the `install_adapter` function)
4. Document the integration in this README

Example adapter template:

```bash
#!/bin/bash
# newmodel_adapter.sh — Integration for "NewModel AI"

# Pre-read
pre_read() {
    python3 scripts/universal_hook.py opencode pre-read --file "$1"
}

# Pre-edit (blocks if file not read)
pre_edit() {
    python3 scripts/universal_hook.py opencode pre-edit --file "$1"
}

# Post-edit
post_edit() {
    python3 scripts/universal_hook.py opencode post-edit --file "$1"
}

# Your adapter logic here, calling the above functions
```

## Troubleshooting

### "File not read before editing" even though I read it

1. Check that the wrapper is correctly intercepting read commands
2. Verify session is active: `python3 scripts/rsi.py status`
3. Check recorded reads: `python3 scripts/preflight_check.py --report`
4. If using a custom wrapper, ensure it calls `universal_hook.py` correctly

### Wrapper not being invoked

1. Verify alias is set: `alias opencode`
2. Check PATH priority: `which opencode`
3. Try running wrapper directly: `./opencode_wrapper.sh --version`

### Session expired errors

1. Start a new session: `python3 scripts/rsi.py init`
2. Or extend TTL: `export RSI_SESSION_TTL_HOURS=48`

## Architecture

```
AI Tool → [Adapter/Shell Wrapper] → universal_hook.py → hooks.py → [enforcement]
                                       ↓
                              Core RSI Framework
                              (A→B→C loop, metrics,
                               calibration, etc.)
```

The adapter translates the AI tool's specific interface into calls to `universal_hook.py`, which then invokes the core hook logic in `hooks.py`. This separation allows:
- Core logic to remain model-agnostic
- New adapters to be added without modifying core code
- Different adapters to be used for the same tool