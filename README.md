# Recursive Self-Improvement (RSI) Framework

A disciplined meta-process that turns every implementation into a learning opportunity — built on Toyota Production System principles. Designed to be wired into any AI-assisted project so the agent builds according to quality principles, forever improving itself.

**Status:** v2.0 | **Language:** Agnostic | **Stack:** Python + Bash + Git | **Zero dependencies**

---

## What This Is

Most AI agents ship code fast but learn nothing. The same mistakes repeat. Quality is assumed, not measured. This framework fixes that by enforcing Toyota's manufacturing discipline on software development:

- **Measure** cycle time, first-pass yield, defect rate
- **Enforce** read-before-edit, verification, memory updates
- **Reflect** with structured proof-wrong hypotheses and 5-Whys
- **Improve** by tracking what works and eliminating what doesn't

## Quick Start

```bash
# 1. ONE-TIME SETUP (select your AI model when prompted):
python3 scripts/setup.py
# Or specify model directly:
#   python3 scripts/setup.py --model claude    # Claude Code
#   python3 scripts/setup.py --model opencode   # opencode / MiniMax-M2.7
#   python3 scripts/setup.py --model shell      # Any CLI AI tool

# 2. Initialize memory (one-time per project):
cp -r MEMORY_TEMPLATE .memory

# 3. Start a session:
python3 scripts/rsi.py init

# 4. See the dashboard:
python3 scripts/rsi.py dashboard

# 5. After every code change:
python3 scripts/rsi.py loop

# 6. Before pushing:
python3 scripts/rsi.py ci
```

## For AI Agents

Drop this framework into any project. The agent reads `CLAUDE.md` on session start and follows the standard work. Tool-layer enforcement depends on your AI model:

| Model | Enforcement |
|-------|------------|
| Claude Code | `.claude/settings.json` PreToolUse/PostToolUse hooks |
| opencode / MiniMax-M2.7 | Shell wrapper (`opencode_wrapper.sh`) |
| Other CLI tools | Shell integrator (`shell_integrator.py`) |

```bash
# Copy into your project
cp -r rsi-framework/ /path/to/your-project/
cd /path/to/your-project
python3 scripts/setup.py --model <your-model>  # Install for your AI tool
```

The agent is now operating under TPS discipline.

---

## Toyota Principles → Framework Mechanisms

| # | Toyota Principle | TPS Term | Framework Mechanism |
|---|---|---|---|
| 1 | Long-term philosophy | — | The framework IS the investment. Measured by metrics over time. |
| 2 | Continuous process flow | Kaizen | A→B→C loop after every change. Ceremony level auto-classified. |
| 3 | Pull systems / avoid waste | Muda | Signal ratio tracking. Waste indicators on dashboard. |
| 4 | Level the workload | Heijunka | `ceremony.py` classifies changes: minimal/standard/thorough/major. |
| 5 | Stop and fix quality first | Jidoka | Hooks block edits, commits, and pushes on failure. No bypass. |
| 6 | Standardized tasks | — | `CLAUDE.md` defines standard work. Scripts ARE the standard. |
| 7 | Visual control | Andon | `dashboard.py` — one command, complete health picture. |
| 8 | Reliable technology | — | Python + Bash + Git. Zero external dependencies. |
| 9-10 | Develop people | — | Calibration tracking develops judgment over time. |
| 11 | Respect network | — | Open framework. `framework_sync.py` for feedback. |
| 12 | Go and see | Genchi Genbutsu | Pre-edit hook blocks editing unread files. |
| 13 | Slow consensus, fast implementation | Nemawashi | Ceremony classification slows big changes, speeds small ones. |
| 14 | Learning organization | Hansei + Kaizen | 5-Whys, FAIL-index, calibration, proof-wrong tracking. |

---

## Architecture

### The Pipeline

```
Change → Classify → Verify → Capture → Review → Optimize → Measure
         (ceremony)  (jidoka)  (Module A) (Module B) (Module C) (metrics)
```

### The Enforcement Stack

```
Layer 1: Tool hooks     (.claude/settings.json → hooks.py)
         ↓ Blocks edit if file not read
         ↓ Blocks --no-verify
         ↓ Records all reads and edits

Layer 2: Git hooks      (scripts/git-hooks/)
         ↓ Pre-commit: session check + preflight + self-verify
         ↓ Commit-msg: blocks if no memory update

Layer 3: CI gate        (scripts/ci_check.sh)
         ↓ Syntax, tests, preflight, placeholders, secrets

Layer 4: Measurement    (metrics.py + calibration.py + dashboard.py)
         ↓ Tracks whether the framework is working
```

### Key Files

| File | Purpose |
|---|---|
| `CLAUDE.md` | Agent standard work — the rules of engagement |
| `.claude/settings.json` | Tool-layer hook configuration |
| `scripts/rsi.py` | Unified CLI — single entry point for everything |
| `scripts/hooks.py` | Tool-layer enforcement (poka-yoke) |
| `scripts/metrics.py` | Value stream measurement engine |
| `scripts/dashboard.py` | Andon board — visual management |
| `scripts/calibration.py` | Proof-wrong hypothesis tracking |
| `scripts/ceremony.py` | Heijunka — right-sized ceremony |
| `scripts/root_cause.py` | 5-Whys root cause analysis |
| `scripts/post_implementation.py` | Module A: capture what happened |
| `scripts/self_feedback.py` | Module B: review and identify issues |
| `scripts/self_optimization.py` | Module C: prioritize and plan |
| `scripts/self_verify.py` | Pluggable syntax/quality verification |
| `scripts/preflight_check.py` | Read-before-edit enforcement |
| `scripts/backlog.py` | Markdown-based task backlog |

---

## Unified CLI

```bash
python3 scripts/rsi.py <command>

# Session
  init              Start a new session
  status            Quick status check
  dashboard         Full andon board

# Development loop
  ceremony          Check required ceremony level
  loop              Full A→B→C with auto-classification
  verify            Self-verification checks
  preflight         Read-before-edit compliance

# Tracking
  metrics [cmd]     Value stream metrics
  calibrate [cmd]   Proof-wrong calibration
  backlog [cmd]     Task backlog management
  root-cause        5-Whys analysis

# Operations
  ci                CI gate checks
  setup             One-time setup
  sync              Framework sync/update
```

---

## Metrics & Measurement

The framework measures itself. If it's not improving quality, it's waste.

| Metric | What It Measures | Target |
|---|---|---|
| First-pass yield | % of verifications passing first try | >80% |
| Defect rate | Bugs per completed task | <0.3 |
| Signal ratio | % of findings that led to action | >50% |
| Cycle time | Hours from task start to complete | Trending down |
| Ceremony cost | Minutes per framework session | Proportional to risk |
| Hypothesis quality | Avg calibration score (0-100) | >60 |

```bash
python3 scripts/rsi.py dashboard    # See everything at a glance
python3 scripts/rsi.py metrics summary
```

---

## Version History

| Version | Change |
|---|---|
| v2.0 | Major: Added metrics engine, andon dashboard, calibration tracker, 5-Whys root cause analysis, Heijunka ceremony classification, unified CLI, Claude Code tool-layer hooks, CLAUDE.md agent standard work, comprehensive test suite |
| v1.11 | Added framework_sync.py |
| v1.10 | Markdown backlog system |
| v1.9 | Pre-commit session check |
| v1.8 | Pluggable LanguageChecker |
| v1.7 | 24h session expiry, PROOF_WRONG_GUIDE.md |
| v1.5 | Cross-platform installers |
| v1.0 | Git hooks + CI enforcement |
| v0.1 | Initial implementation |

See [`FRAMEWORK.md`](FRAMEWORK.md) for full documentation.
