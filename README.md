# Recursive Self-Improvement (RSI) Framework

A lightweight meta-process that turns every implementation into a learning opportunity, and every learning opportunity into the next implementation's improvement. Built on Toyota Production System principles.

**Status:** v1.11 | **Language:** Agnostic | **Stack:** Python + Bash + Git

---

## Toyota Principles → RSI Framework

Each TPS principle maps to a concrete RSI mechanism:

| # | Toyota Principle | TPS Term | RSI Implementation |
|---|---|---|---|
| 1 | Long-term philosophy over short-term goals | — | The framework IS the long-term investment. "Just fix it" creates regressions. The cost is always paid. |
| 2 | Continuous process flow | Kaizen | The A→B→C loop (Implement → Capture → Review → Optimize) runs after every change, no matter how small. |
| 3 | Pull systems (avoid overproduction) | — | Checks run only when changes exist (git-diff detected). No scheduled noise. |
| 4 | Level the workload | Heijunka | Every change runs the full A→B→C loop. No "small fix" exemption. |
| 5 | Stop and fix quality first time | Jidoka | CI blocks commits when checks fail. Quality gates are **blocking**, not advisory. |
| 6 | Standardized tasks as foundation | — | The framework scripts ARE the standard. Everyone uses identical capture/feedback/optimization. |
| 7 | Visual control (no hidden problems) | 5S | Task tracker, round logs, CI output, self_verify reports — all visible, all in git. |
| 8 | Reliable, tested technology | — | Python + Bash + Git. No novel tools. No dependencies beyond standard tooling. |
| 9 | Grow leaders who understand the work | — | **"What could prove this wrong?"** trains adversarial thinking. Managers and peers ask it. |
| 10 | Develop exceptional people and teams | — | Module B (self_feedback) develops code review discipline. Module C develops prioritization. |
| 11 | Respect extended network | — | Open framework repo. Sharing findings benefits all projects using it. |
| 12 | Go and see for yourself | Genchi Genbutsu | **Pre-flight check**: you must read a file before editing it. No editing from memory. |
| 13 | Slow consensus, fast implementation | Nemawashi | Module A mandatory reflection slows decisions. Once decided, implementation is rapid. |
| 14 | Learning organization | Hansei + Kaizen | Round logs + retrospectives + "what could prove this wrong" = explicit organizational learning. |

---

## Quick Start

```bash
# 1. ONE-TIME SETUP (per machine):
python3 scripts/setup.py        # Cross-platform (Linux/macOS/Windows)
# Or: bash scripts/setup.sh     # Bash only
# Or: powershell -File scripts/setup.ps1  # Windows PowerShell

# 2. Initialize memory structure (one-time per project):
cp -r MEMORY_TEMPLATE .memory

# 3. After every code change, run the A→B→C loop:
python3 scripts/post_implementation.py --interactive --run-feedback --run-optimization

# 4. Before pushing:
bash scripts/ci_check.sh
```

---

## The Three-Module System

### Module A: Post-Implementation Capture (`post_implementation.py`)
After every code change. Captures what happened before it's forgotten.

**Key question (mandatory):** "What could prove this WRONG?"

### Module B: Self-Feedback (`self_feedback.py`)
After Module A. Identifies bugs, edge cases, efficiency gains, maintainability improvements.

### Module C: Self-Optimization (`self_optimization.py`)
After Module B. Prioritizes findings, plans next round, documents reusable patterns.

---

## Key Files

| File | Purpose |
|---|---|
| `FRAMEWORK.md` | Full framework documentation |
| `PROOF_WRONG_GUIDE.md` | Examples of good/bad "what could prove this wrong?" answers |
| `scripts/self_verify.py` | Pre-commit verification with pluggable language checkers |
| `scripts/preflight_check.py` | Enforce "read before edit" discipline, session expiry |
| `scripts/post_implementation.py` | Module A: capture what happened |
| `scripts/self_feedback.py` | Module B: review, optimize, improve |
| `scripts/self_optimization.py` | Module C: prioritize and plan |
| `scripts/ci_check.sh` | Full CI gate |
| `setup.py` / `setup.ps1` | Cross-platform one-time installer (Python/PowerShell) |
| `MEMORY_TEMPLATE/` | Copy to `.memory/` in your project |

---

## Toyota Genchi Genbutsu in Practice

**Rule:** You must read a file before editing it.

The most common failure mode in code review is critiquing code you haven't read — or editing code you only partially understand. The pre-flight check enforces reading:

```bash
# Record that you've read a file
python3 scripts/preflight_check.py --record src/main.py

# Now edit it
# (Pre-commit hook will verify this)
```

---

## Toyota Hansei in Practice

**Rule:** After every fix, answer "What could prove this WRONG?"

This is not optimism vs pessimism. It is **adversarial hypothesis generation**. You are required to name at least one specific thing that, if true, would mean your fix is wrong.

Examples:
- "If the network returns empty data on a successful INSERT, `safe_first_or_raise` would raise instead of returning the id"
- "If another process deletes the row between the check and the upsert, a duplicate would be inserted"
- "If the cache has a stale entry, the wrong entity_id would be returned"

---

## Framework Evolution

| Version | Change |
|---|---|
| v0.1 | Initial implementation (Wandering Codex) |
| v1.0 | Added enforcement (git hooks + CI), A→B→C chaining |
| v1.1 | Pre-flight check, mandatory "what could prove this wrong?" |
| v1.2 | GitHub Actions, fixed PROJECT_ROOT bugs, updated sanity checks, task tracker format |
| v1.5 | Cross-platform installers: `setup.py` (Python), `setup.ps1` (PowerShell), `os.path.realpath()` in hooks |
| v1.7 | 24h session expiry, `--fresh` flag to skip auto-seeding, PROOF_WRONG_GUIDE.md |
| v1.8 | Pluggable LanguageChecker architecture in self_verify.py, FAIL-index usage guide, expanded self-tests |
| v1.9 | Pre-commit Stage 0 session check (`--require-session`), `--start` flag, Module B documented as interactive-only |
| v1.10 | Markdown-based backlog system with standard task format (`backlog.md` + `scripts/backlog.py`) |

See [`FRAMEWORK.md`](FRAMEWORK.md) for full documentation.
