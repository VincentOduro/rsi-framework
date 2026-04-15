# Proof-Wrong Guide

> "What could prove this WRONG?" is the most important question in the RSI framework.

Every implementation must answer this question before capturing success. This guide will help you write answers that are actually useful.

---

## The One-Line Test

Ask yourself:
> **"If I ran one specific test or check, would the result tell me if this fix is broken?"**

If you can't answer that, the fix isn't ready.

---

## Rubric

| | **Good** | **Bad** |
|---|---|---|
| **Specificity** | Names a concrete failure mode | Says "there might be a bug" |
| **Testability** | You can construct evidence (pass/fail) | Requires re-reading the code to check |
| **Significance** | Would actually break production | Technically true but harmless |
| **Ownership** | Lives inside the fix's scope | Blames caller, not the fix |

---

## Examples by Change Type

### Bug Fix

**Fix:** Add null guard to `data["id"]` access

**Bad:** "What if the data is None?" ← Too vague, doesn't describe the failure mode

**Good:** "If `data` is a list containing only `[None, None]`, the null guard would pass but downstream code expecting a dict would fail on attribute access." ← Names the exact shape of bad input

**Better:** "If `safe_first_or_raise` receives a row with NULL id column, it returns a dict with `None` id, and the upsert would insert a null-keyed record." ← Names the actual race/input that breaks the fix

---

### Refactor

**Fix:** Extract `validate()` into a standalone function

**Bad:** "What if the new function has bugs?" ← Self-referential, proves nothing

**Good:** "If the original `validate()` had implicit dependencies on closure variables, moving it to a function with explicit args would silently change behavior." ← Names the specific implicit assumption being violated

---

### New Feature

**Fix:** Add pagination to the entity list API endpoint

**Bad:** "What if someone requests page 0?" ← Trivially handled by standard bounds checking

**Good:** "If a client requests `limit=1000`, and Supabase returns 1000 rows, the response embedding vector(1024) × 1000 = 1M tokens could hit the API timeout before the final row is written to the response stream." ← Names a real resource exhaustion scenario

---

### Config / Infrastructure

**Fix:** Increase connection pool size from 10 to 50

**Bad:** "What if 50 is too many?" ← Vague, no actionable test

**Good:** "If the database's `max_connections` is 100 and 3 services each run 50 connections, we'd exceed the limit under normal load and get 'too many connections' errors." ← Names the specific resource limit that would be violated

---

### Data Migration

**Fix:** Backfill `entity_aliases.mentioned_name` from `entities.name`

**Bad:** "What if some entities don't have aliases?" ← The fix handles nulls

**Good:** "If an entity's `name` contains a unicode homograph (e.g., Cyrillic 'о' vs Latin 'o'), naive string matching would fail silently when resolving aliases." ← Names a real data quality issue that bypasses the naive backfill

---

## Warning Signs

### "This is too vague"
- "There might be a race condition"
- "Something could go wrong"
- "Edge cases exist"

### "This is obvious"
- "If the code doesn't run, it won't work"
- "If the input is wrong, the output is wrong"
- "If there's no database connection, the query fails"

### "This wouldn't prove the fix wrong"
- "If someone changes the code later" ← Not the fix's fault
- "If the requirements change" ← Out of scope
- "If the server is down" ← Infrastructure, not the fix

---

## How to Improve a Weak Answer

Start with the failure mode, not the concern:

```
concern: "What if the null check isn't enough?"
     ↓
failure mode: "If data is a list of dicts instead of a single dict,
               isinstance check passes but 'id' key doesn't exist"
     ↓
proof-wrong: "If a caller passes [{'id': 1}, {'id': 2}] instead of
             {'id': 1}, the isinstance guard passes but KeyError
             happens on data['class']"
```

---

## Non-Interactive Mode

When running Module A non-interactively (CI, scripts), provide `--proof-wrong`:

```bash
python3 scripts/post_implementation.py \
  --task "Fix auth token expiry" \
  --succeeded "Token now refreshes automatically" \
  --failed "Edge case where clock skew > 5min not handled" \
  --proof-wrong "If server clock is 6 minutes ahead of client, the
  refresh window misfires and user gets logged out"
```

**Minimum bar for non-interactive:** The proof-wrong must describe:
1. What specific input/state breaks the fix
2. What specific observable failure occurs
3. Why the fix doesn't handle it (root cause)

If you can't write that in one or two sentences, the fix needs more work before non-interactive capture is appropriate.
