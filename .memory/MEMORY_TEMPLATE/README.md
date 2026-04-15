# Memory System

The `.memory/` directory is your project's organizational memory. It survives sessions and is git-tracked.

## Structure

```
.memory/
├── README.md              # This file
├── rounds/                # Session logs (one per working session)
│   └── round-001.md      # Copy from MEMORY_TEMPLATE/rounds/
├── technical/             # Structured, searchable knowledge
│   ├── FAIL-index.md     # Behavioral failure modes
│   ├── decisions.md      # Architecture decisions
│   └── patterns.md       # Reusable code patterns
└── agents/               # Task state
    └── current-task.md   # Active tasks
```

## Usage

After installing the RSI framework (`cp -r MEMORY_TEMPLATE/.memory .` from project root):

```bash
# Start session
bash scripts/init.sh

# After changes
python3 scripts/post_implementation.py --interactive

# End session
bash scripts/checkpoint.sh
```

## What Goes Where

| File | What | When |
|---|---|---|
| `rounds/round-NNN.md` | What happened this session | Every session |
| `technical/FAIL-index.md` | What went wrong and how to prevent it | After failures |
| `technical/decisions.md` | Architecture choices and rationale | After design decisions |
| `technical/patterns.md` | Reusable code patterns | After finding good solutions |
| `agents/current-task.md` | What needs doing | Continuously updated |
