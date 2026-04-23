# Recursive Self-Improvement (RSI) Framework

A disciplined meta-process that turns every implementation into a learning opportunity — built on Toyota Production System principles. Drops into any AI-assisted project so the agent builds under measured quality discipline and keeps improving itself.

**Status:** v2.6 • **Runtime:** Python 3.11+ • **Deps:** pydantic, openai • **Tested on:** Windows 11, macOS, Linux, WSL2

---

## What This Is

Most AI agents ship code fast but learn nothing. The same mistakes repeat. Quality is assumed, not measured. This framework fixes that by enforcing Toyota's manufacturing discipline on software development — and by giving you a **multi-model workflow** where a senior "overlord" model (Claude) routes work to specialized worker models (MiniMax, Kimi) so you get scale without giving up judgment.

- **Measure** — cycle time, first-pass yield, defect rate, trust scores
- **Enforce** — read-before-edit, verification, delegation trails, quality gates
- **Reflect** — structured proof-wrong hypotheses, 5-Whys analyses, FAIL-index
- **Improve** — metrics track whether the framework itself is paying off
- **Delegate** — the overlord directs, the worker implements, every change is reviewed

## The Overlord-Worker Model

The core idea in v2.x: **one overlord, multiple workers, Claude decides who gets what.**

```
                                  ┌─────────────────────┐
                    ┌────────────▶│  Worker: MiniMax-M2.7│
                    │  task spec  │  - 1M ctx, bulk gen  │
┌─────────────────┐ │             │  - multi-file refactor│◀─┐
│  Overlord       │─┤             └─────────────────────┘   │
│  (Claude, you)  │ │                                        │ result
│                 │ │             ┌─────────────────────┐   │
│  - architect    │ └────────────▶│  Worker: Kimi        │◀─┘
│  - router       │  task spec   │  - precise reasoning │
│  - reviewer     │              │  - targeted edits    │
└─────────────────┘              └─────────────────────┘
         │                                ▲
         │   .memory/reviews/pending/     │
         └────────────────────────────────┘
```

The overlord writes the task spec (`.rsi/tasks/TASK-NNN.json`), picks the right worker by setting `"worker": "kimi"` or `"worker": "minimax"` (or omits it for round-robin), sends it via `scripts/delegate.py`, reviews the output in `.memory/reviews/pending/`, and either accepts (quality-ratchet auto-commit) or rejects/revises. The framework's pre-edit hook **blocks the overlord from editing guarded files without a delegation trail** — you physically can't cheat.

**Worker selection** — Claude decides per task:

| Use `minimax` when | Use `kimi` when |
|---|---|
| Task needs >128k context (whole-codebase scans) | Targeted single-file change |
| Bulk generation across many files | Strong reasoning required (algorithms, API use) |
| Multi-file refactor over large surface area | Test writing with precise symbol resolution |
| Throughput matters in a large parallel batch | Quality matters more than speed |

File sensitivity is declared in [`.rsi/architecture.yaml`](.rsi/architecture.yaml):

| Level | Who can modify | Examples |
|---|---|---|
| `constitution` | overlord only | `CLAUDE.md`, `.rsi/**`, `scripts/hooks.py`, `scripts/delegate.py` |
| `guarded` | worker via delegation + review | `scripts/*.py`, `adapters/**` |
| `open` | worker freely | `tests/**`, `docs/**`, `*.md` |

## Quick Start

### Prerequisites

```bash
python --version               # must be 3.11+
pip install -e .               # installs pydantic + openai from pyproject.toml
# or: pip install -e ".[dev]"  # also installs mypy, ruff, pre-commit, pip-audit, pytest

export MINIMAX_API_KEY=sk-...  # MiniMax worker (optional if KIMI_API_KEY is set)
export KIMI_API_KEY=sk-...     # Kimi worker    (optional if MINIMAX_API_KEY is set)
```

At least one worker API key must be set. Both can be set simultaneously — Claude routes tasks to whichever model fits best.

**Credential hygiene.** The framework reads API keys from the environment only — never put them in a committed file. `.env`, `*.pem`, `*.key`, `credentials.*`, and common cloud-SDK auth dirs are gitignored by default, but double-check with `git check-ignore -v <file>` before placing any secret in the project tree.

**GitHub auth.** Prefer `gh auth login` or a [credential helper](https://git-scm.com/book/en/v2/Git-Tools-Credential-Storage) over embedding a PAT in your remote URL (`https://x-access-token:TOKEN@github.com/...`). An inline PAT is visible in `git remote -v` output, shell history, and any CI log that dumps env state; rotate it if you suspect exposure and switch to a credential helper.

### Drop into a project

```bash
# 1. Copy the framework into your project
cp -r rsi-framework/* /path/to/your-project/
cd /path/to/your-project

# 2. One-time setup — installs agent hooks for your AI tool
python scripts/setup.py --model claude    # or opencode, shell, etc.

# 3. Initialize memory
cp -r MEMORY_TEMPLATE .memory

# 4. Start a session
python scripts/rsi.py init
```

### Everyday workflow

```bash
# Check what's happening
python scripts/rsi.py status
python scripts/rsi.py dashboard

# Write a task spec and delegate it to the worker
python scripts/rsi.py delegate .rsi/tasks/TASK-042.json

# Review the worker's output
python scripts/rsi.py review-queue list
python scripts/rsi.py review-queue show TASK-042
python scripts/rsi.py review-queue accept TASK-042 --apply

# After a code change (overlord-side edits)
python scripts/rsi.py loop          # full A→B→C capture, review, optimize
python scripts/rsi.py verify        # quick self-check

# Before pushing
python scripts/rsi.py ci
```

See [`.rsi/DELEGATION_GUIDE.md`](.rsi/DELEGATION_GUIDE.md) for the full task-spec schema and routing table.

## Architecture

### The pipeline

```
Change → Classify → Delegate → Review → Verify → Capture → Optimize → Measure
         (ceremony) (worker)   (gate)   (jidoka) (Mod A)   (Mod C)   (metrics)
```

### The enforcement stack

```
Layer 0: Delegation gate    (.rsi/architecture.yaml + scripts/hooks.py)
         ↓ Blocks overlord edits to guarded files without a delegation trail
         ↓ 1-hour override with reason if bypass is needed

Layer 1: Tool hooks          (.claude/settings.json → scripts/hooks.py)
         ↓ Blocks edit if file not read (Genchi Genbutsu)
         ↓ Blocks --no-verify bypasses (Jidoka)
         ↓ Records every read, edit, and session

Layer 2: Quality ratchet     (scripts/delegate.py apply_changes)
         ↓ After each accepted task: verify passes → checkpoint commit
         ↓ Verify fails → automatic revert; quality only goes up

Layer 3: Git hooks           (scripts/git-hooks/)
         ↓ Pre-commit: session check + preflight + self-verify
         ↓ Commit-msg: blocks if no memory update

Layer 4: Pre-commit          (.pre-commit-config.yaml)
         ↓ ruff + ruff-format + mypy --strict + pytest

Layer 5: CI gate             (scripts/ci_check.sh)
         ↓ Syntax, tests, preflight, placeholders, secrets

Layer 6: Measurement         (scripts/metrics.py + calibration.py + trust.py)
         ↓ Tracks whether the framework is working — no hidden problems
```

### Key components

| File | Role |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Agent standard work — the rules of engagement |
| [`.rsi/architecture.yaml`](.rsi/architecture.yaml) | File sensitivity + worker API config |
| [`.rsi/rules.yaml`](.rsi/rules.yaml) | Declarative enforcement rules |
| [`engine/protocol.py`](engine/protocol.py) | Pydantic v2 models: TaskSpec, WorkerResult, ReviewDecision, DelegationEvent |
| [`scripts/rsi.py`](scripts/rsi.py) | Unified CLI — single entry point |
| [`scripts/hooks.py`](scripts/hooks.py) | Tool-layer enforcement (poka-yoke) |
| [`scripts/delegate.py`](scripts/delegate.py) | Multi-worker delegation, per-task routing, parallel DAG executor, quality ratchet |
| [`scripts/review_queue.py`](scripts/review_queue.py) | Review queue with JSON validation |
| [`scripts/classify_file.py`](scripts/classify_file.py) | File sensitivity classifier |
| [`scripts/rules_engine.py`](scripts/rules_engine.py) | Declarative rule evaluator |
| [`scripts/trust.py`](scripts/trust.py) | Worker trust scoring — high-trust types auto-accept |
| [`scripts/metrics.py`](scripts/metrics.py) | Value stream measurement |
| [`scripts/dashboard.py`](scripts/dashboard.py) | Andon board |
| [`scripts/calibration.py`](scripts/calibration.py) | Proof-wrong hypothesis tracking |
| [`scripts/ceremony.py`](scripts/ceremony.py) | Heijunka — right-sized ceremony |
| [`scripts/root_cause.py`](scripts/root_cause.py) | 5-Whys |

### Toyota principles → framework mechanisms

| # | Principle | TPS term | Mechanism |
|---|---|---|---|
| 2 | Continuous process flow | Kaizen | A→B→C loop after every change |
| 4 | Level the workload | Heijunka | `ceremony.py` — minimal/standard/thorough/major |
| 5 | Stop and fix quality first | Jidoka | Hooks block edits, commits, pushes on failure |
| 6 | Standardized tasks | — | `CLAUDE.md` + scripts are the standard |
| 7 | Visual control | Andon | `dashboard.py` — one-command health |
| 12 | Go and see | Genchi Genbutsu | Pre-edit hook blocks editing unread files |
| 14 | Learning organization | Hansei + Kaizen | 5-Whys, FAIL-index, calibration, proof-wrong |

## CLI reference

```
python scripts/rsi.py <command>

Session             Development loop
  init                ceremony        Check required ceremony
  status              loop            Full A→B→C with auto-classify
  dashboard           verify          Self-verification
                      preflight       Read-before-edit compliance

Delegation          Tracking
  delegate <task>     metrics [cmd]   Value stream metrics
  review-queue list   calibrate       Proof-wrong calibration
  review-queue show   backlog         Task backlog
  review-queue accept root-cause      5-Whys analysis
  classify <path>     trust [cmd]     Worker trust scores
  override <path>

Operations
  ci                  sync            Framework sync
  setup               status          Quick status
```

## Metrics & measurement

The framework measures itself. If it's not improving quality, it's waste (muda).

| Metric | What it measures | Target |
|---|---|---|
| First-pass yield | % verifications passing first try | > 80% |
| Defect rate | Defects per completed task | < 0.3 |
| Signal ratio | % findings that led to action | > 50% |
| Cycle time | Hours from task start to complete | trending down |
| Ceremony cost | Minutes per framework session | proportional to risk |
| Hypothesis quality | Avg calibration score (0-100) | > 60 |
| Worker trust | Accept rate by task type per worker | > 80% → auto-accept |

```bash
python scripts/rsi.py dashboard         # everything at a glance
python scripts/rsi.py metrics summary
python scripts/rsi.py trust score
```

## Development

### Running tests

```bash
python -m pytest tests/ -q              # 185 tests, ~2s
python -m mypy                          # strict on engine/ + 6 scripts
python -m ruff check                    # lint
python -m ruff format                   # auto-format
```

### Pre-commit

```bash
pip install pre-commit
pre-commit install                      # registers git hook
pre-commit run --all-files              # one-shot full sweep
```

Hooks: ruff, ruff-format, mypy --strict, pytest.

### Editing framework internals

1. Classify the file: `python scripts/rsi.py classify <path>`
2. If `constitution` → overlord edits directly
3. If `guarded` → write a task spec, delegate, review
4. If `open` → anyone edits freely

When delegation is the wrong tool for a small mechanical change (e.g., adding a single type annotation), use `python scripts/rsi.py override <path> --reason "..."` — the override expires in 60 minutes and is auditable.

## Recent evolution

The framework has been through a measurement-gated evolution from v2.0 to v2.2, with every decision backed by numbers:

| Phase | Question | Outcome | Decision record |
|---|---|---|---|
| E0 | How slow is the Python hook stack? | 189ms p50 on WSL UNC; 62ms on native Win | [`docs/baseline-metrics.md`](docs/baseline-metrics.md) |
| E0a | Can a persistent daemon fix startup cost? | Daemon works but needs compiled client | [`docs/decisions/phase-E0a.md`](docs/decisions/phase-E0a.md) |
| E2-E3 | Does a Go hook binary help? | 10.4ms p50 on native Win (83% faster) | [`docs/decisions/phase-E2-E3.md`](docs/decisions/phase-E2-E3.md) |
| E1 | Migrate protocol to Pydantic v2? | Done — one source of truth | — |
| E6 | Python hardening sweep | ruff + mypy strict + pre-commit + encoding audit | — |
| E7 | Do we need a Rust parallel dispatcher? | **NO** — GIL is fine for I/O-bound worker API calls | [`docs/decisions/phase-E7.md`](docs/decisions/phase-E7.md) |

Full roadmap in [`.rsi/design/EVOLUTION_PLAN.md`](.rsi/design/EVOLUTION_PLAN.md). Stack rationale in [`STACK_EVOLUTION.md`](STACK_EVOLUTION.md).

## Version history

| Version | Change |
|---|---|
| v2.6 | Dual-worker support: Kimi (Moonshot AI) added alongside MiniMax. Claude routes tasks per-spec via `"worker"` field; unrouted tasks distribute round-robin across available workers. Delegation gate fires on either `MINIMAX_API_KEY` or `KIMI_API_KEY`. Worker strengths documented in `architecture.yaml` and `DELEGATION_GUIDE.md`. |
| v2.5 | Rules engine fail-closed (raises `RulesFileMissing` instead of silently returning empty rules → all gates passed). `framework_sync.py` now copies `.rsi/rules.yaml`, `.rsi/architecture.yaml`, `.rsi/DELEGATION_GUIDE.md` on `--pull` without touching project-specific `.rsi/tasks/` or `.rsi/overrides/`. |
| v2.4 | Version-drift guard in `framework_sync.py`: `--status`/`--check` print red `DRIFT:` warning when FRAMEWORK.md and README.md Status lines diverge |
| v2.3 | Memory hygiene (preflight cap + absolute-path filter), round rotation fix (checkpoint.sh marks COMPLETE), framework_sync.py recognizes `.rsi-source/` + actually copies files on `--pull`, FAIL-009 (MiniMax truncation pattern on guarded mid-file edits >100 lines) |
| v2.2 | Delegation gate, quality ratchet, parallel DAG, worker trust, declarative rules, Pydantic v2, mypy strict, ruff, pre-commit, Windows hardening, Go hook binary |
| v2.1 | Quality ratchet (toryo), session brief, parallel delegation, task DAG |
| v2.0 | Metrics engine, andon dashboard, calibration, 5-Whys, ceremony, unified CLI, Claude Code hooks, CLAUDE.md standard work. Consolidates all prior single-agent work (hooks, session TTL, proof-wrong guide, preflight, backlog, framework_sync, language checker, cross-platform installers). |

## Further reading

- [`CLAUDE.md`](CLAUDE.md) — agent standard work (mandatory for agents)
- [`FRAMEWORK.md`](FRAMEWORK.md) — complete reference documentation
- [`TOYOTA_PRINCIPLES.md`](TOYOTA_PRINCIPLES.md) — how each principle maps to code
- [`PROOF_WRONG_GUIDE.md`](PROOF_WRONG_GUIDE.md) — writing testable hypotheses
- [`.rsi/DELEGATION_GUIDE.md`](.rsi/DELEGATION_GUIDE.md) — task spec schema, routing, ceremony levels
- [`ATTRIBUTIONS.md`](ATTRIBUTIONS.md) — cited influences and prior art
