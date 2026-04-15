# Metrics

This directory stores RSI framework metrics data.

## Files

- `events.jsonl` — Append-only event log (created automatically by the metrics engine)

## Event Types

| Type | Description |
|---|---|
| `session_start` | New session started |
| `task_start` | Work started on a task |
| `task_complete` | Task finished (includes first_pass flag) |
| `verify_result` | Self-verify outcome (passed, attempt number) |
| `ceremony_complete` | A->B->C loop finished (level, duration) |
| `defect_found` | Bug found (severity, found_by) |
| `finding_outcome` | Whether a Module B finding led to action |

## Viewing Metrics

```bash
python3 scripts/rsi.py dashboard       # Full visual dashboard
python3 scripts/rsi.py metrics summary  # JSON summary
python3 scripts/rsi.py metrics yield    # First-pass yield
python3 scripts/rsi.py metrics defects  # Defect rate
```
