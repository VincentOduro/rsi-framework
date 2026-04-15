# Backlog — [Project Name]

> Standard task format for RSI Framework projects. All fields are optional except `id`, `type`, `title`, `status`, `priority`.

---

## Stats

| Metric | Count |
|---|---|
| Total | 0 |
| Todo | 0 |
| In Progress | 0 |
| Blocked | 0 |
| Done | 0 |

---

## In Progress

| id | type | title | priority | estimate | assignee |
|---|---|---|---|---|---|
| | | | | | |

## Blocked

| id | type | title | priority | estimate | assignee | blocked-by |
|---|---|---|---|---|---|---|
| | | | | | | |

## Todo

| id | type | title | priority | estimate | assignee |
|---|---|---|---|---|---|
| | | | | | |

## Done

| id | type | title | priority | estimate | completed |
|---|---|---|---|---|---|
| | | | | | |

---

## Task Entry Format

```
### TSK-XXX: [title]

**type:** feature | bug | refactor | chore | spike | docs
**status:** todo | in-progress | blocked | done
**priority:** CRITICAL | HIGH | MEDIUM | LOW
**estimate:** xs | s | m | l | xl
**assignee:** (optional)
**created:** YYYY-MM-DD
**updated:** YYYY-MM-DD
**related:** TSK-YYY, FAIL-004, round-NNN (optional)
**notes:** (optional free text)
```

---

## Task Definitions

| Type | When to use |
|---|---|
| `feature` | New functionality or user-facing change |
| `bug` | Defect fix — should reference FAIL-ID if applicable |
| `refactor` | Code improvement without behavior change |
| `chore` | Maintenance, tooling, dependency updates |
| `spike` | Time-boxed investigation or proof-of-concept |
| `docs` | Documentation-only changes |

| Priority | When to use |
|---|---|
| `CRITICAL` | Blocks release, data loss risk, security issue |
| `HIGH` | Important but not blocking; should ship in current cycle |
| `MEDIUM` | Should fix eventually; no rush |
| `LOW` | Nice to have; address when nothing else matters |

| Estimate | Meaning |
|---|---|
| `xs` | Under 1 hour |
| `s` | Half a day |
| `m` | 1-2 days |
| `l` | 3-5 days |
| `xl` | Over a week — consider splitting |

---

## Quick Reference

```bash
# Add a task
python3 scripts/backlog.py add --type bug --title "Fix auth token expiry" --priority HIGH --estimate m

# List tasks
python3 scripts/backlog.py list
python3 scripts/backlog.py list --status todo
python3 scripts/backlog.py list --priority CRITICAL

# Update task
python3 scripts/backlog.py update TSK-001 --status done --completed 2026-04-15

# Show stats
python3 scripts/backlog.py stats

# Show task detail
python3 scripts/backlog.py show TSK-001
```