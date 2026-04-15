# FAIL-index — Behavioral Failure Modes

Cite by ID before making risky claims. Format: `See FAIL-XXX`.

| ID | Short description | Rule to prevent it |
|---|---|---|
| FAIL-001 | Editing files without reading them | Always read file before editing. Use pre-flight check. |
| FAIL-002 | Claiming tests pass without running them | Run tests after every change. |
| FAIL-003 | Fixing symptoms instead of root causes | Ask "why why why" before implementing. |
| FAIL-004 | Not capturing what could go wrong | Mandatory "what could prove this wrong?" in Module A. |
| FAIL-005 | Assuming code works without verification | Use self_verify.py after every change. |
| FAIL-006 | Forgetting to update memory after changes | Commit must include memory update or warning. |
| FAIL-007 | Implementing without understanding the full context | Read the entire file before modifying it. |
| FAIL-008 | Fixing one thing and breaking another | Run full test suite after every change. |

---

## How to add an entry

When you discover a failure mode:

1. Add entry above with next sequential ID
2. Describe what happened (specific, not vague)
3. Describe why it was wrong
4. Describe what rule prevents it

Example:
```
| FAIL-009 | Not checking pre-commit hook output | Always read hook output before assuming commit succeeded |
```
