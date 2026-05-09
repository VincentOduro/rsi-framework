# RSI Delegation Guide — Full Reference

Read this file on-demand, not on every message. CLAUDE.md has the core rules.

## Ceremony Levels

| Level | When | Required |
|---|---|---|
| minimal | Docs/config, <20 lines | Capture + proof-wrong |
| standard | Normal code, 1-5 files | Full A->B->C |
| thorough | 5+ files or risk factors | A->B->C + hypothesis review + FAIL-index |
| major | 10+ files or cross-module | A->B->C + 5-Whys + architecture review |

## Metrics Targets

| Metric | Target | Command |
|---|---|---|
| First-pass yield | >80% | `python3 scripts/metrics.py yield` |
| Defect rate | <0.3/task | `python3 scripts/metrics.py defects` |
| Signal ratio | >50% | `python3 scripts/metrics.py signal` |
| Hypothesis quality | >60/100 | `python3 scripts/calibration.py score` |

## Commands

```bash
python3 scripts/rsi.py init            # Start session
python3 scripts/rsi.py dashboard       # Andon board
python3 scripts/rsi.py ceremony        # Check ceremony level
python3 scripts/rsi.py loop            # A->B->C loop
python3 scripts/rsi.py verify          # Self-verify
python3 scripts/rsi.py delegate <f>    # Send to MiniMax
python3 scripts/rsi.py review-queue list/show/accept/reject/revise
python3 scripts/rsi.py classify <f>    # File sensitivity
python3 scripts/rsi.py override <f>    # Emergency bypass (1hr TTL)
python3 scripts/rsi.py calibrate score # Calibration accuracy
python3 scripts/rsi.py root-cause interactive  # 5-Whys
python3 scripts/rsi.py ci             # CI gate
```

## Routing Table

| Task | Route | Why |
|------|-------|-----|
| Any code change | **Delegate** | Worker implements, overlord reviews |
| Write tests | **Delegate** | Open files |
| Audit/analysis | **Delegate** | Worker scans, overlord synthesizes |
| Fix bugs | **Delegate** | Decompose into 1-fix-per-task |
| Update CLAUDE.md | Overlord | Constitution file |
| Pure question | Overlord | No files touched |

## Worker Selection

Active workers: MiniMax, Kimi, and DeepSeek (V4). Claude picks the worker per task by setting `"worker"` in the task spec. If omitted, tasks round-robin across available workers.

| Worker | Best for | Notes |
|---|---|---|
| `minimax` | >128k context scans, whole-codebase reads, large parallel batches | Highest throughput (max_concurrency 20) |
| `kimi` | Targeted single-file changes, algorithmic logic, API-sensitive code | Thinking mode on by default; reasoning sidecar written |
| `kimi-instant` | Surgical deletes/renames where thinking is wasteful overhead | Same quality cap, faster, no reasoning |
| `deepseek-flash` | Bulk refactors, doc gen, multi-file, latency-sensitive tasks | Cheap ($0.14/$0.28 per 1M), fast, 1M context |
| `deepseek-pro` | Precision edits, quality-sensitive, targeted logic without reasoning overhead | Higher capability; no chain-of-thought |
| `deepseek-pro-thinking` | Complex bugs, architectural reasoning, deep chain-of-thought needed | Slower; writes reasoning sidecar; omits temperature (vendor constraint) |

**Decision rule**: large context or bulk volume → `minimax` or `deepseek-flash`. Focused precision → `kimi` or `deepseek-pro`. Deep reasoning needed → `kimi` (thinking on) or `deepseek-pro-thinking`. When uncertain, omit `worker` and let round-robin decide.

DeepSeek workers all share `DEEPSEEK_API_KEY`. The concurrency semaphore is keyed per env_key, so their in-flight calls pool together.

## File Sensitivity

| Level | Who Modifies | Examples |
|---|---|---|
| constitution | Overlord only | CLAUDE.md, .rsi/**, scripts/hooks.py, scripts/delegate.py |
| guarded | Both (review required) | scripts/*.py, adapters/** |
| open | Both (freely) | tests/**, docs/** |

## Task Spec Format

```json
{
    "id": "TASK-NNN",
    "task_type": "code",
    "description": "Short description",
    "instruction": "Detailed instruction with exact import paths",
    "files_to_read": ["src/relevant.py"],
    "files_to_modify": ["src/target.py"],
    "acceptance_criteria": ["Testable criterion"],
    "proof_wrong": "Specific hypothesis",
    "constraints": [],
    "worker": "kimi"
}
```

`worker` is optional. Valid values: `"minimax"`, `"kimi"`, `"kimi-instant"`, `"deepseek-flash"`, `"deepseek-pro"`, `"deepseek-pro-thinking"`. Omit to let the dispatcher round-robin. See **Worker Selection** above for when to prefer each.

### Task types

| `task_type` | Purpose | API check | Output | Review tier |
|---|---|---|---|---|
| `code` (default) | Code/test/refactor work | enforced | edited files | per size, see below |
| `research` | Curate data, fact-find, judgment calls | skipped | report.md in `.rsi/research/` | single overlord pass; human-judgment criteria allowed |
| `audit` | Read-only analysis of existing code | skipped | findings.md in `.rsi/audits/` | single overlord pass |

If `task_type` is omitted, treat as `code`.

### Review tiers (code tasks)

| Code size | Review |
|---|---|
| < 50 lines, 1 file | Combined single-pass (overlord reviews implementation + spec compliance together) |
| 50-200 lines, ≤ 3 files | Two-stage (spec-compliance + code-quality) |
| > 200 lines or > 3 files | Two-stage + adversarial pass |

Rationale: feedback from prior sessions showed two-stage review on trivial
tasks is overkill. Match review depth to defect risk, not to ritual.

## API Verification (pre-dispatch)

Before delegating any `code` task, run:

```bash
python3 scripts/api_check.py .rsi/tasks/TASK-NNN.json
```

This walks `instruction` text, extracts referenced symbols (e.g.
`broker.max_position_risk_pct`), resolves them via `importlib` +
`inspect.signature()`, and fails if any are missing or have wrong kwargs.
Catches plan-time API hallucinations before MiniMax burns time on
non-existent calls.

Skip for `research` and `audit` task types.

## Anti-Patterns

- Don't edit from memory. Read the file.
- Don't skip ceremony. Run ceremony.py.
- Don't generate vague hypotheses.
- Don't ignore failing tests.
- Don't bypass hooks.
- Don't generate noise findings.
- Don't skip root cause analysis.
- Don't commit without memory update.
- Don't implement directly when MiniMax is available.
- Don't rationalize skipping delegation.
