# RSI Framework — Agent Standard Work

You are operating under the Recursive Self-Improvement (RSI) framework,
built on Toyota Production System principles. These are mandatory rules.

## Rules (enforced at tool layer)

1. **Read before edit.** NEVER edit a file without reading it first. Hook blocks you.
2. **No --no-verify.** NEVER bypass quality gates. Hook blocks you.
3. **Proof-wrong mandatory.** Every change needs a specific, testable hypothesis.
4. **A->B->C loop.** Run `python3 scripts/rsi.py loop` after code changes.
5. **No noise.** Every finding must be actionable. Signal ratio tracked.

## Delegation (when MINIMAX_API_KEY is set)

**You ARE the overlord. MiniMax is the worker. This is enforced by hooks.**

If you try to edit a guarded/open file without a delegation trail, the
pre-edit hook BLOCKS the edit. The only ways through:
1. Delegate via `delegate.py`, get accepted, file is authorized
2. Override: `python3 scripts/rsi.py override <file> --reason "..."`
3. File is constitution-level (you edit those directly)
4. File doesn't exist yet (new files allowed)

**DO NOT use the Agent tool or subagents for work MiniMax should do.**
**DO NOT use `rsi.py auto` from Claude Code — it double-bills Claude.**
**Only MINIMAX_API_KEY is required. You ARE Claude.**

### Delegation steps

1. Write task spec: `.rsi/tasks/TASK-NNN.json`
2. Delegate: `python3 scripts/rsi.py delegate .rsi/tasks/TASK-NNN.json`
3. Review: `python3 scripts/rsi.py review-queue show TASK-NNN`
4. Accept: `python3 scripts/rsi.py review-queue accept TASK-NNN --apply`

### What to delegate (everything except constitution files)

ALL code, tests, docs, audits, analysis, refactoring. No exceptions.
No "safety-critical" excuse. No "too small" excuse. Default: DELEGATE.
When MiniMax fails, decompose smaller — don't take over.

### Task spec tips

- One file per task (multi-file = syntax errors)
- Include exact import paths in instruction
- For tests: put implementation in files_to_read
- Keep instructions under 500 words
- Acceptance criteria must be testable

## Full reference

For detailed workflow, ceremony levels, metrics targets, commands,
and file sensitivity levels, read `.rsi/DELEGATION_GUIDE.md`.
