# Recursive Self-Improvement Framework (RSI)

A lightweight meta-process for software projects that turns every implementation into a learning opportunity, and every learning opportunity into the next implementation's improvement.

**Status:** v2.3 | **Language:** Agnostic | **Stack:** Python + Bash + Git

---

## Core Philosophy

Most projects improve slowly because:
1. **Failures are forgotten.** The same mistake gets repeated months later.
2. **Success is assumed.** Code that "works" is never questioned.
3. **Refactors are one-time events.** Patterns aren't captured; the same problem gets solved differently each time.
4. **Memory is in the developer's head.** It leaves when the session ends.

The RSI framework addresses all four through a disciplined feedback loop with persistent memory.

### The Loop

```
Implement → Capture → Review → Optimize → Prioritize → Implement
```

Each cycle produces three things:
- **What actually happened** (not what was planned)
- **Real bugs found** (not theoretical ones)
- **Evidence-based priorities** (not guesses)

### What Makes It "Recursive"

The framework improves itself over time:
- Patterns captured in `patterns.md` make future work faster
- FAIL-index entries prevent repeated mistakes
- Decisions log prevents re-litigating settled questions
- The CI checks evolve as the framework matures

---

## Toyota Production System Foundations

The framework is built on 14 Toyota Production System principles. See `TOYOTA_PRINCIPLES.md` for the full table.

Key mappings:
- **Genchi Genbutsu (Go and see):** Pre-flight check — read files before editing
- **Hansei (Reflection):** "What could prove this wrong?" after every fix
- **Jidoka (Quality at source):** CI and commit-msg hook block commits when quality checks fail — no bypass, no continue anyway
- **Kaizen (Continuous improvement):** A→B→C loop runs after every change
- **Nemawashi (Slow consensus):** Mandatory reflection slows decisions, rapid implementation follows
- **Heijunka (Level workload):** Proportional ceremony — match ceremony to change size

---

## The Three-Module System

### Module A: Short-term Memory — `scripts/post_implementation.py`

**Purpose:** Capture what happened before it's forgotten.

**Trigger:** After every code change, before declaring success.

**Questions it asks:**
- What was attempted?
- What succeeded?
- What failed?
- **What could prove this WRONG?** (mandatory — empty answer is a red flag)
- What files changed?

**"What could prove this wrong?"** is the single most important question. It forces you to specify what evidence would invalidate the fix. If you can't answer it, the fix isn't ready. Examples:
- "If Supabase returns empty `data` on a successful INSERT, `safe_first_or_raise` would raise instead of returning the id"
- "If another process deletes the class row between the check and the upsert, the upsert would insert a duplicate"
- "If the cache has a stale entry for a merged entity, the wrong entity_id would be returned"

**Outputs:**
- `.memory/rounds/round-NNN.md` — implementation log updated (includes proof_wrong)
- `.memory/agents/current-task.md` — task marked complete or in-progress

**Key design decision:** Self-verify runs first. If checks fail, you fix before capturing. The capture records success, not a lie.

**Non-interactive mode requires `--proof-wrong`:**
```bash
python3 scripts/post_implementation.py --task "Fix auth bug" --succeeded "Added token validation" --failed "none" --proof-wrong "If clock skew exceeds token expiry window, valid tokens could be rejected"
```

**Can chain to B and C automatically:**
```bash
python3 scripts/post_implementation.py --run-feedback --run-optimization
```

---

### Module B: Self-Feedback — `scripts/self_feedback.py`

**Purpose:** Turn experience into actionable insight.

**Trigger:** After Module A.

**Questions it asks (per change):**
1. **Review:** What are 2+ potential bugs or edge cases in the code just written?
2. **Optimize:** What are 2 ways to improve efficiency?
3. **Improve:** What is 1 way to improve maintainability?

**Improvements prompt includes:** "Is this a reusable pattern? (y/N)" — explicit flag for Module C.

**Outputs:**
- `.memory/technical/feedback-log.md` — all findings, timestamped
- Follow-up tasks created for unconfirmed issues

**Key design decision:** Minimum counts enforced (2 reviews, 2 optimizations). The minimum prevents "nothing to say" from being acceptable. You can always say more.

**Automated assistance:** `review_code()` does keyword-based pattern matching (MagicMock subscript, unguarded data[0], await in comprehension, etc.). It finds obvious issues so you can focus on subtle ones.

---

### Module C: Self-Optimization — `scripts/self_optimization.py`

**Purpose:** Turn insight into action.

**Trigger:** After Module B, before ending the session.

**What it does:**
1. Reads all feedback from all rounds
2. Prioritizes by impact (CRITICAL → HIGH → MEDIUM → LOW)
3. Suggests specific next-round actions
4. Prompts to document patterns

**Outputs:**
- `.memory/agents/current-task.md` — prioritized task list with specific next actions
- `.memory/technical/patterns.md` — reusable patterns with code examples

**Key design decision:** Prioritization is automatic but visible. You see the full ranked list before it gets written. You can override before committing to disk.

---

## Directory Structure

```
rsi-framework/
├── README.md                     # Quick start + Toyota principle mappings
├── FRAMEWORK.md                  # This file — full documentation
├── TOYOTA_PRINCIPLES.md          # Toyota TPS principles reference
├── MEMORY_TEMPLATE/              # Copy to .memory/ in your project
│   ├── README.md                 # Memory system overview
│   ├── rounds/                   # Session logs
│   │   └── round-001.md         # Round template
│   ├── technical/                # Structured knowledge
│   │   ├── FAIL-index.md        # Behavioral failure modes (cite by ID)
│   │   ├── decisions.md          # Architecture decisions with rationale
│   │   └── patterns.md           # Reusable code patterns
│   └── agents/                   # Task state
│       ├── current-task.md      # Active tasks (legacy)
│       └── backlog.md           # Standard task backlog├── scripts/                      # Workflow automation (agnostic)
│   ├── __init__.py              # Package marker
│   ├── backlog.py               # Backlog manager (add/list/update/show/stats)
│   ├── framework_sync.py        # Framework self-update + feedback manager
│   ├── post_implementation.py    # Module A
│   ├── self_feedback.py         # Module B
│   ├── self_optimization.py     # Module C
│   ├── self_verify.py           # Pre-commit verification
│   ├── preflight_check.py       # Pre-flight: read before edit
│   ├── ci_check.sh              # CI gate
│   ├── setup.sh                  # System-wide hook setup (one-time per machine)
│   ├── init.sh                   # Start of session
│   ├── review.sh                 # Assess current state
│   ├── checkpoint.sh              # End of session
│   └── git-hooks/
│       ├── pre-commit           # Runs preflight + self_verify
│       └── commit-msg            # Warns if memory not updated
└── tests/
    └── test_framework.py        # Framework self-validation
```

---

## Workflow

### Minimal (one session)

```bash
# Start
bash scripts/init.sh

# After each code change
python3 scripts/post_implementation.py --interactive
python3 scripts/self_feedback.py
python3 scripts/self_optimization.py

# End
bash scripts/checkpoint.sh
```

### Fast (one command after each change)

```bash
python3 scripts/post_implementation.py --run-feedback --run-optimization
```

### Full CI gate (before push)

```bash
bash scripts/ci_check.sh   # Or: hooks run automatically on commit
```

---

## The Self-Verify Check (`scripts/self_verify.py`)

Pre-commit verification run automatically by the pre-commit hook and manually by you.

**What it checks:**
1. All modified Python files import cleanly
2. No placeholder code (TODO, pass, NotImplementedError)
3. File-specific sanity checks (override per-project)
4. Side-effect scan: what else imports from the changed module
5. Full test suite passes

**Important:** Use `python3 -B` to avoid bytecode caching false positives.

---

## Enforcement: Git Hooks + CI

Three enforcement layers:

### Layer 1: Pre-flight Check — `scripts/preflight_check.py`

**Purpose:** Prevents editing files without reading them first (Genchi Genbutsu).

**What it tracks:** Which files have been "read" (recorded) in the current session.

**States:**
- `--record FILE` — mark a file as read
- `--check-edited` — warn if edited files weren't read (non-blocking)
- `--ci` — blocking mode: fails if any edited file wasn't read
- `--report` — show read vs edited status

**Auto-seeding:** On first run, seeds state from `git ls-files` so CI only flags genuinely new files.

**In pre-commit hook:** Runs first, before self_verify. If any source file was edited without being read, commit is blocked.

### Layer 2: Git Hooks

Hooks are installed system-wide via `~/.git_template/hooks/`. Run once per machine: `bash scripts/setup.sh`

After setup, hooks work automatically for every `git clone`. For existing repos: `git config core.hooksPath ~/.git_template/hooks`

| Hook | What | Blocks? |
|---|---|---|
| `pre-commit` | Pre-flight check (files read before edit) | **Yes** |
| `pre-commit` | Runs `self_verify.py` on changed `.py` files | **Yes** |
| `pre-commit` | Checks shell script syntax | **Yes** |
| `pre-commit` | Auto-records files as read after verification | — |
| `commit-msg` | **BLOCKS** commit if code changed without a corresponding memory update (Module A entry) | **Yes** — no bypass, no continue anyway |

### Layer 3: CI

```bash
bash scripts/ci_check.sh
```

| Check | Blocks? |
|---|---|
| Pre-flight check (files read before edit) | **Yes** |
| Python syntax on all files | **Yes** |
| Shell script syntax | **Yes** |
| Test suite | **Yes** |
| self_verify.py | **Yes** |
| Memory infra files | **Yes** |
| No placeholder code | **Yes** |
| No hardcoded secrets (`.memory/` + `scripts/`) | **Yes** |

For GitHub Actions, add to workflow:
```yaml
- name: RSI framework checks
  run: bash scripts/ci_check.sh
```

**Why three layers?** Pre-flight catches the highest-failure-rate mistake (editing without reading). Hooks provide fast pre-commit feedback. CI catches hook bypasses.

---

## The "What Could Prove This Wrong?" Step

This is the most important discipline in the framework. Every implementation must answer (Hansei reflection):

> **"Name at least one specific thing that, if true, would mean this fix is incorrect, incomplete, or would break something else."**

**Why it's mandatory:** It forces you to think adversarially about your own code. If you can't name anything that would prove you wrong, you haven't thought hard enough about the fix.

**What makes a good answer:**
- Specific: names actual failure modes, not vague concerns
- Testable: there exists evidence that would confirm or deny it
- Non-trivial: if the answer is obvious or irrelevant, it's not useful

**Examples of good answers:**
- "If the network returns empty `data` on a successful INSERT, `safe_first_or_raise` would raise instead of returning the id" → suggests adding a test for this case
- "If another process deletes the class row between the check and the upsert, the upsert would insert a duplicate" → confirms the race was actually fixed
- "If the cache has a stale entry for a merged entity, the wrong entity_id would be returned" → suggests cache invalidation is needed

For a detailed rubric, anti-patterns, and examples by change type (bug fix, refactor, new feature, config, migration), see [`PROOF_WRONG_GUIDE.md`](PROOF_WRONG_GUIDE.md).

---

## Mandatory Discipline (Principle 5: Jidoka)

**Every change, no matter how small, goes through the complete A→B→C cycle.**

There is no "small fix" exemption. There is no "I know what I'm doing" exception. The moment you believe a change is too small for the framework is the moment the framework breaks.

> "Hotfix" is not a change type — it is a failure to follow the process.

| Change type | Required ceremony |
|---|---|
| Any code change | Module A → Module B → Module C |

All checks block. There is no "continue anyway" option. There is no `--skip-verify`. There is no `--skip-auto`. There are no advisory gates.

---

## Adapting to a New Project

### 1. Copy the structure

```bash
cp -r rsi-framework/ /path/to/your-project/
cd /path/to/your-project
cp -r MEMORY_TEMPLATE .memory
```

### 2. Configure project-specific parts

Edit these files for your project:
- `scripts/self_verify.py` — replace sanity checks with yours (see below)
- `scripts/preflight_check.py` — adjust `PROJECT_ROOT` if needed
- `.memory/README.md` — replace with your project name
- `.memory/technical/FAIL-index.md` — start with your own failure modes

### 3. Keep the generic parts

These work unchanged in any project:
- All scripts except `self_verify.py` and `preflight_check.py` (project root path)
- `scripts/init.sh`, `review.sh`, `checkpoint.sh`
- `scripts/post_implementation.py`, `self_feedback.py`, `self_optimization.py`
- `scripts/ci_check.sh`, `setup.sh`
- All `git-hooks/`

### 4. Add project-specific sanity checks

In `scripts/self_verify.py`, replace the `sanity_checks` dict:

```python
sanity_checks = {
    "my_file.py": my_file_sanity_check,
    # ...
}

def my_file_sanity_check(file_path: Path) -> bool:
    """Check something specific to your project."""
    content = file_path.read_text()
    # ...
    return True
```

### 5. Language/framework variants

The framework is language-agnostic. For a different stack:
- Replace `self_verify.py` checks with your language's linter/formatter
- Replace pytest with your test runner
- Replace Python AST with your language's parser (Tree-sitter, etc.)
- Keep the A→B→C loop identical

---

## Framework Evolution Log

See [README.md "Evolution Path"](README.md) for the authoritative version history.
This file tracks only the most recent release for quick reference.

| Date | Version | Change | What it fixed |
|---|---|---|---|
| 2026-04-21 | v2.3 | Memory hygiene (hooks.py + preflight_check.py reject absolute paths, cap `read_files` at 200). Round rotation (checkpoint.sh marks round COMPLETE via portable sed+mktemp+mv). FAIL-009 documents MiniMax truncation pattern for guarded mid-file edits >100 lines. framework_sync.py recognizes `.rsi-source/` convention; `cmd_pull` actually copies source→project; `--refresh` flag git-pulls source first. | `.preflight_state.json` grew unbounded with pytest temp paths; rounds never rotated; framework_sync `--pull` was a no-op in child-mode; FRAMEWORK.md Status tracked a parallel version scheme and caused "already current" false positives |

## Using FAIL-index

The FAIL-index is the shared vocabulary for behavioral failure modes. It lives in `.memory/technical/FAIL-index.md` and is the most underused part of the framework.

**The key insight:** Instead of writing "record matching on subset of key fields" in every code review, you write `FAIL-004`. One citation communicates the full failure mode, its root cause, and the preventive rule.

**When to cite:**
- During Module B (self-feedback review): "This code is vulnerable to FAIL-004"
- In commit messages: `fix: add missing unique constraint — prevents FAIL-004`
- In code comments: `# FAIL-007: Must read entire file before modifying`
- In task descriptions: `Review: Check if FAIL-008 applies to this change`

**How to cite in practice:**

```
## Review Comment

This upsert logic has a race condition — FAIL-004.
If process A reads the row between process B's check and insert,
we'd get a duplicate key violation.

[FAIL-004]: Record matching on subset of key fields.
  → Fix: Use SELECT FOR UPDATE or a unique constraint.
```

**When to add new entries:**

When a failure recurs but doesn't match an existing FAIL ID:
1. Add the ID: next sequential number
2. Short name: what went wrong (not the rule)
3. Preventive rule: what should have prevented it

Example new entry:
```
| FAIL-010 | Committing without reviewing hook output | Always read the full commit-msg hook output before the commit completes |
```

---

## Backlog System
The framework includes a lightweight, markdown-based backlog system for consistent task tracking across all projects.

### Core Files

- `.memory/backlog.md` — Standard task backlog (copy from `MEMORY_TEMPLATE/backlog.md`)
- `scripts/backlog.py` — Backlog manager CLI

### Task Format

Every task has:
| Field | Required | Values |
|-------|----------|--------|
| `id` | Yes (auto) | `TSK-001`, `TSK-002`, ... |
| `type` | Yes | `feature`, `bug`, `refactor`, `chore`, `spike`, `docs` |
| `title` | Yes | Free text |
| `status` | Yes | `todo`, `in-progress`, `blocked`, `done` |
| `priority` | Yes | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `estimate` | No | `xs`, `s`, `m`, `l`, `xl` |
| `assignee` | No | Free text |
| `related` | No | `TSK-XXX`, `FAIL-004`, `round-NNN` |
| `blocked-by` | No | `TSK-XXX` |

### Workflow

```bash
# Add a task
python3 scripts/backlog.py add --type bug --title "Fix auth token" --priority HIGH --estimate m

# List tasks (filter by status, priority, type)
python3 scripts/backlog.py list --status todo
python3 scripts/backlog.py list --priority CRITICAL

# Show task details
python3 scripts/backlog.py show TSK-001

# Update task (move to in-progress, mark done, etc.)
python3 scripts/backlog.py update TSK-001 --status done --completed 2026-04-15

# Stats
python3 scripts/backlog.py stats
```

### Relationship to current-task.md

- `backlog.md` is the **primary** task tracker
- `current-task.md` is the **legacy** per-session task tracker (Module C output)
- New projects should use `backlog.md`; existing projects can migrate tasks

---

### Known limitations

1. **Module B automated review is shallow.** Keyword matching only; misses logic bugs. Manual review is required and is the primary method.
2. **Module C pattern detection relies on user input.** Despite the explicit flag, you still have to recognize a pattern.
3. **Round files can grow stale.** If sessions are missed, the round log gets gaps.
4. **Cross-round deduplication is manual.** Module C prioritizes by weight, but duplicate feedback entries across rounds are possible.
5. **Pre-flight seeding doesn't enforce actual reading.** Seeding from `git ls-files` means CI can't distinguish "file was read" from "file is just tracked". Use `--fresh` flag for strict enforcement (skips auto-seeding).
6. **Priority assignment requires manual prefix.** Tasks without `[CRITICAL/HIGH/MEDIUM/LOW]` prefix default to MEDIUM.

### Improvements needed (backlog)

| Priority | Improvement | Why |
|---|---|---|
| MEDIUM | Module B: LLM-assisted code review | Replace keyword matching with actual analysis |
| MEDIUM | Cross-round deduplication in Module C | Prevent duplicate feedback entries |
| LOW | Pre-flight auto-record after read | Pre-flight detects reading via file access, not manual record |

---

## Further Reading

- [`TOYOTA_PRINCIPLES.md`](TOYOTA_PRINCIPLES.md) — Toyota Production System principles reference
- [`MEMORY_TEMPLATE/README.md`](MEMORY_TEMPLATE/README.md) — Memory system overview
