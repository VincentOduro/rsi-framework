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
    "description": "Short description",
    "instruction": "Detailed instruction with exact import paths",
    "files_to_read": ["src/relevant.py"],
    "files_to_modify": ["src/target.py"],
    "acceptance_criteria": ["Testable criterion"],
    "proof_wrong": "Specific hypothesis",
    "constraints": []
}
```

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
