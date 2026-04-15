# FAIL-index — Behavioral Failure Modes

Cite by ID in commit messages, code comments, and review findings.
Format: `FAIL-XXX` or `See FAIL-XXX`.

| ID | Failure Mode | Preventive Rule | Times Cited | Last Cited |
|---|---|---|---|---|
| FAIL-001 | Editing files without reading them | Always read file before editing. Enforced by pre-edit hook. | 0 | — |
| FAIL-002 | Claiming tests pass without running them | Run tests after every change. Enforced by self_verify. | 0 | — |
| FAIL-003 | Fixing symptoms instead of root causes | Use 5-Whys (root_cause.py) for post-commit defects. | 0 | — |
| FAIL-004 | Vague "what could prove this wrong" answers | Use calibration.py validate to check hypothesis quality. Score must be >=40. | 0 | — |
| FAIL-005 | Assuming code works without verification | Use self_verify.py after every change. Enforced by pre-commit hook. | 0 | — |
| FAIL-006 | Forgetting to update memory after changes | commit-msg hook blocks commits without memory update. | 0 | — |
| FAIL-007 | Implementing without understanding full context | Read the entire file, not just the function. Enforced by pre-edit hook. | 0 | — |
| FAIL-008 | Fixing one thing and breaking another | Run full test suite. Use side-effect scan in self_verify. | 0 | — |
| FAIL-009 | Generating noise findings that don't lead to action | Track signal ratio via metrics.py. Target >50%. | 0 | — |
| FAIL-010 | Skipping ceremony because "it's small" | Run ceremony.py to classify. Even minimal requires proof-wrong. | 0 | — |
| FAIL-011 | Not resolving proof-wrong hypotheses | Review calibration.py open list. Resolve or close hypotheses. | 0 | — |
| FAIL-012 | Bypassing quality gates with --no-verify | pre-bash hook blocks --no-verify. No exceptions. | 0 | — |

---

## How to add an entry

When a defect recurs but doesn't match an existing FAIL entry:

1. Run `python3 scripts/rsi.py root-cause create --add-to-fail-index`
2. Or manually add with next sequential ID

**When to cite:**
- Commit messages: `fix: add null check — prevents FAIL-004`
- Code comments: `# FAIL-007: must read entire file before modifying`
- Review findings: "This code is vulnerable to FAIL-003"
- Task descriptions: `Review: Check if FAIL-008 applies`

**When to add:**
Run 5-Whys analysis and check "Add to FAIL-index?" when the root cause
is a behavioral failure mode (not a code bug, but a process failure).
