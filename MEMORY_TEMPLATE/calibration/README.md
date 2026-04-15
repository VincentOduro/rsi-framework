# Calibration

This directory stores proof-wrong hypothesis tracking data.

## Files

- `hypotheses.jsonl` — All recorded hypotheses with status and quality scores

## How It Works

Every "what could prove this wrong?" answer is recorded as a hypothesis.
Over time, hypotheses are resolved as:
- **confirmed** — the thing you were worried about actually happened
- **disproven** — tested and the concern was unfounded
- **untestable** — cannot be verified (try to avoid these)

The calibration score measures prediction accuracy. For code quality,
**lower accuracy is better** — it means your code is usually right and
your concerns are precautionary, not real bugs.

## Usage

```bash
python3 scripts/rsi.py calibrate add "hypothesis text" --task "task name"
python3 scripts/rsi.py calibrate open        # List unresolved
python3 scripts/rsi.py calibrate score       # Accuracy metrics
python3 scripts/rsi.py calibrate resolve HYP-001 confirmed --notes "details"
```
