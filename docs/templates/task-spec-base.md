# Task spec — base template

**Canonical path for instances:** `.rsi/tasks/TASK-{ID}.json` (JSON shape
required by `scripts/delegate.py`; this markdown template is the human-
oriented source-of-truth that gets serialized into the JSON fields).

The task spec is what the worker reads. Every hour of task-spec care pays
out across the worker's dispatch quality — Phase 1's evidence showed
finding counts decreased across five algorithms as the spec template
tightened. This template bakes in the Phase 1 Updates A-F plus the
Session 1-3 calibration signals.

---

## §0 Identification

```json
{
  "id": "TASK-{project}-{number}",
  "task_type": "code",
  "worker": "{kimi | minimax | unset for round-robin}",
  "task_category": "{algorithm | logic | surgical-edit | pure-deletion | test | docs}",
  "description": "One-line imperative summary of what this task accomplishes."
}
```

### Task categories (Signal C — dispatch-planning framing)

The `task_category` tag drives the framing language the rest of the spec
uses. Pick carefully — the wrong framing is often the difference between
a clean dispatch and a re-dispatch cycle.

Default Kimi routing per category is shown in parentheses; override by
setting `"worker"` explicitly in §0.

- **algorithm** (default worker: `kimi`, thinking mode) — implement a
  function/class per a spec. Standard template. Thinking mode benefits
  from chain-of-thought before emitting output; MiniMax is also suited
  for bulk/multi-file refactors. Token cost: higher than instant mode.
  Worth it for non-trivial logic.
- **logic** (default worker: `kimi`, thinking mode) — change or extend
  existing logic; surrounding style drift is tolerable. Section §6
  omits byte-preservation language.
- **surgical-edit** (default worker: `kimi-instant`) — change specific
  lines only, preserve surrounding bytes exactly. Session 1 U3 and U5
  evidence: workers silently normalize encoding, collapse blank lines,
  reorder imports, or "clean up" unrelated sections. Signal A language
  in §6 is mandatory. Route to `kimi-instant` rather than thinking-mode
  Kimi — reasoning tokens don't help with byte-preservation discipline,
  they just inflate cost.
- **pure-deletion** (default worker: `kimi-instant` or direct edit) —
  remove specific lines without adding anything. Highest normalization-
  drift risk. Consider direct edit (rsi.py override) over delegation
  entirely. If delegating, route to `kimi-instant`; Signal A language
  in §6 is mandatory AND self-report byte counts required in §10.
- **test** (default worker: `kimi`, thinking mode) — author pytest cases
  for existing code. Thinking mode helps reason about edge-case
  coverage. Include the source module in files_to_read so monkeypatch
  paths resolve correctly (see testing-conventions.md §1).
- **docs** (default routing depends on content type) —
  - **Pattern-following prose** (README boilerplate, docstrings,
    reference documentation, prose that templates well): default
    worker `kimi-instant` (no reasoning burn needed for templated
    content; cheap worker tokens substitute for expensive overlord
    tokens).
  - **Analysis / synthesis docs** (retrospectives, audits, scope
    decisions, framework design memos): default operator direct-edit —
    the content requires operator-specific judgment that doesn't
    delegate cleanly, and the overlord's context is load-bearing.
  - When in doubt between the two, delegate first and override if the
    result doesn't match. Worker tokens are cheap; overlord tokens are
    the constrained resource. Prose drift is expected when delegated —
    no byte-preservation framing.

### Kimi thinking-mode reasoning capture

For tasks dispatched to `kimi` (thinking mode), the framework captures
the model's `reasoning_content` to a sidecar at
`.memory/reviews/results/TASK-{ID}.reasoning.txt` alongside the raw
content sidecar. Review-time inspection can audit whether the producer's
chain-of-thought engaged with calibration traps (§10) and self-report
directives rather than inferring engagement from output shape alone.
This is calibration infrastructure, not a required review input — empty
or skimmed reasoning isn't itself a review failure, just a data point
for the retrospective.

---

## §1 Consistency check

Before authoring a new task spec, consult prior memos / calibration data
/ template decisions for this project so each dispatch is informed by
field evidence rather than starting cold.

```
**Prior memos consulted:**
- {TASK-ID or "none — first dispatch for this area"}

**Template decisions acknowledged:**
- {relevant decisions from past tasks, or "none carry over"}

**Calibration data reviewed:**
- {trap-firing rate from recent dispatches, or "n/a"}

**Cross-session commitments affecting this task:**
- {relevant commitments, or "none"}

**Divergence from prior patterns (if any):**
- {what this spec does differently and why, or "follows established pattern"}
```

Per Q3 resolution, blank or "not applicable" entries are accepted —
the prompt forces consideration, not a specific answer. The
retrospectives-layer audit (at phase boundaries) looks for drift
patterns across many tasks, not individual sparse answers.

---

## §2 Motivation / context

One paragraph answering: *what specific thing does this enable, and why
can't the rest of the system function as intended without it?* Keep to
3-6 sentences. If motivation spans more than a paragraph, the task is
probably too big — decompose.

```
**Why this task exists:**
{paragraph}

**Files to read:**
- {path:line-range for excerpts, or full paths}

**Files to modify:**
- {path — list only what actually changes; extra entries inflate dispatch risk}
```

The files_to_read list is load-bearing: Phase 1 evidence consistently
showed that omitting a referenced file from files_to_read led to either
pseudocode defects being reproduced faithfully (spec-bug trap) or
paraphrase-from-memory drift. Err on the side of inclusion.

---

## §3 Current state → target state

Two compact snapshots.

```
**Current state:**
{what exists now, specific enough that the worker can orient}

**Target state:**
{what should exist after the task lands — observable, not aspirational}
```

For surgical-edit / pure-deletion tasks, include the exact before/after
shape at the byte / character level where relevant:

```
BEFORE:
    parser = argparse.ArgumentParser(description="Module C: Self-optimization")
    args = parser.parse_args()

AFTER:
    (these two lines removed; blank line between them preserved; no other changes)
```

---

## §4 Concrete changes

The actual delta. For `algorithm` and `logic` categories, describe the
intended behavior and let the worker produce the specific lines. For
`surgical-edit` and `pure-deletion`, give exact line-level instructions.

Phase 1 Update F: if the changes involve rendering / template / string-
formatting decisions, surface them here explicitly — don't bury them in
§7 ambiguity. Explicit decisions at §4 cut findings in half by
pre-empting trap-category-6 (normalization) pressures.

---

## §5 Acceptance criteria

Testable, observable, specific. Each entry is a checkbox the overlord
can verify at review time.

```
- [ ] {criterion 1, with the specific command or observation that proves it}
- [ ] {criterion 2}
- [ ] All tests in `tests/{relevant_module}` pass.
- [ ] Full suite passes: `python -m pytest tests/ -q`.
```

For surgical-edit / pure-deletion:

```
- [ ] Only the specified lines changed. Diff against HEAD shows nothing else.
- [ ] Worker's self-reported byte count matches the actual diff delta.
      (If not, the discrepancy is investigated before acceptance per
      review-memo §5.)
```

---

## §6 Constraints / framing

Category-dependent. Pick ONE of the framings below based on §0
`task_category`, or write a custom block that covers the same ground.

### `algorithm` / `logic` framing

```
- Single file modification: {path} only (or list all files explicitly).
- No new external dependencies. Existing imports are what's available.
- Match the project's lint/format conventions; ruff and mypy configs
  in pyproject.toml are authoritative.
- Proof-wrong in §9 must identify a specific, testable failure mode —
  not a vague worry.
```

### `surgical-edit` framing (Signal A — Session 2 U3 byte-preservation)

```
**Byte-preservation discipline — mandatory:**

This task requires byte-exact precision. ONLY the lines specified in §4
may change. The worker must NOT:
- Reformat surrounding code (line endings, whitespace, import order)
- Normalize encoding (em-dashes, replacement characters, quote styles)
- Collapse blank lines not specifically called out
- "Clean up" adjacent code that was already there
- Reorder imports, sort definitions, or rewrite docstrings
- Fix typos, comments, or style issues outside the specified delta

If the worker would normally make stylistic improvements alongside the
core change, DEFER them. This task is scope-bounded. Style improvements
are welcome in a SEPARATE follow-up task, not bundled with this one.

Self-report requirement in §10: state pre-edit and post-edit byte counts
and confirm the delta matches the specified change set exactly.
```

### `pure-deletion` framing (highest normalization risk)

```
**Byte-preservation discipline — mandatory (see surgical-edit framing).**

Additionally, for pure deletions:
- Every deleted line is listed explicitly in §4. The worker may not
  delete anything else, even if it appears "obviously unused."
- Blank-line handling: if a blank line sits between the deleted lines
  and neighboring code, preserve it unless §4 explicitly lists it as
  deleted.
- Self-report byte counts are NOT optional. The worker must state
  pre-edit bytes, post-edit bytes, and confirm the delta equals the
  sum of the deleted lines' byte lengths (including trailing newlines).

If the worker cannot confidently produce a byte-exact deletion (common
when the tool chain normalizes on read/write), it must return an empty
changes dict with a note explaining why — the overlord will apply the
deletion directly rather than receive subtly-incorrect output.
```

### `test` framing

```
- Source module for monkeypatching: include in files_to_read. (Pytest
  monkeypatch.setattr patches the source module, not the consumer —
  see docs/templates/testing-conventions.md §1.)
- Fixtures: place in conftest.py or same test module; sibling-module
  fixtures aren't auto-discovered.
- No xfail without a concrete linked issue or TASK reference; xfail
  masks latent defects in a seen-twice pattern (testing-conventions.md §3).
```

### `docs` framing

```
- Prose may drift stylistically from the overlord's written voice;
  this is acceptable for docs tasks.
- Do NOT fabricate references to files, functions, or APIs that don't
  exist in the project. Grep the tree before citing specifics.
- Markdown: GFM, no HTML unless the existing document already uses it.
```

---

## §7 Ambiguity surfacing — A6-standard-edges

The A6 standard edges are places where the spec is intentionally or
accidentally silent, and the worker must either engage or surface the
ambiguity. Originated in Phase 1 Update B (empty-skills guard,
min_years=0, etc.); generalized here.

**(a) Empty-input edges** — what does this function do with `None`,
empty list, empty string, zero? Pseudocode typically specifies the
happy path; the worker must either engage with edges or surface them.

**(b) Zero / boundary values** — what about `0`, `-1`, exactly-at-
threshold? If the spec uses `<` vs `<=` inconsistently, that's an edge
to surface.

**(c) Type coercion edges** — if the spec mixes Decimal, float, int:
what's the coercion order? Does quantization happen pre- or
post-arithmetic? (Trap category 1 — type coercion.)

**(d) Validator constraint edges** — if the spec declares
`@model_validator` methods, enumerate them. Worker reads the method
bodies, not just the field declarations (Phase 1 Update D, trap
category 2).

**(e) Rendering / template edges** — explanation strings, pluralization,
formatting. State explicit decisions for "1 preference dimensions match"
vs "1 preference dimension matches", leading commas when lists are
empty, number-of-decimals in currency renderings (Phase 1 Update F,
trap category 6 normalization impulses).

**(f) Spec-bug edges** — pseudocode in the reference doc may contain
defects that faithful reproduction would reproduce. List them here so
the worker engages rather than silently "fixes." (Trap category 5.)

### Task-specific A6 edges

```
a) {specific empty-input edge in THIS task, or "n/a"}
b) {specific boundary edge, or "n/a"}
c) {specific coercion edge, or "n/a"}
d) @model_validator methods in scope:
   - validate_X: {what it does, what constraint it enforces}
   - validate_Y: {...}
e) Rendering decisions:
   - {specific decision, or "no rendering in this task"}
f) Known spec bugs to preserve / engage:
   - {specific bug and expected engagement, or "none known"}
```

---

## §8 Review outcome expectations (Phase 1 Update C)

```
This task is expected to land via **apply-with-edits** unless the worker
surfaces design-level ambiguity the overlord can't resolve from findings
alone. Re-dispatch should only fire on:

- A structural misread of the task (wrong signature, wrong algorithm
  approach, missing abstraction)
- A scope violation (surgical-edit task that normalizes unrelated lines
  per Session 2 U3 pattern)
- A self-report inaccuracy that the memo-vs-diff reconciliation in
  review-memo §5 can't attribute to benign drift

Small issues — a single missed edge in §7, a test-side mistake, a
borderline severity-tier call — are apply-with-edits territory.
```

Phase 1 evidence: absent explicit outcome-framing, workers sometimes
produced outputs too polished to accept-with-edits (over-engineering) or
too rough to avoid re-dispatch. Naming the expected outcome in §8 aligns
expectations.

---

## §9 Proof-wrong

A specific, testable hypothesis about how this task could fail to
deliver what's actually needed. Not "this might have bugs"; rather,
"if X assumption is wrong, the specific observable failure is Y."

```
If {specific assumption}, then {specific observable failure mode}. The
fix ideally surfaces in {acceptance criterion N} — verify that criterion
is exercising the assumption.
```

The proof-wrong field is what converts a task from "hope it works" to
"we've named the specific way it would go wrong." Phase 1 evidence:
tasks with vague proof-wrong ("might not handle edge cases") consistently
produced thinner output than tasks with specific proof-wrong ("if the
spec allows negative weights, the normalize function will divide by
zero").

---

## §10 Context — validators, calibration traps, self-report directives

This is the place for the pattern-adherence prompts that make producer
engagement verifiable rather than inferred.

### Pydantic / runtime validators (Phase 1 Update A)

```
Validators the worker must read (not just reference by name):
- {module.ValidatorClass.validate_method}: enforces {constraint}. Impact:
  if the worker's output violates this, the runtime raises {specific
  ValidationError}, and tests in {test_file} will fail with {message}.
```

### Calibration traps (Phase 1 Update F + retrospective §2.8)

```
This task contains the following planted ambiguities to test spec-
fidelity-under-semantic-smoothing-pressure. The task spec is accurate;
these are NOT defects to fix. Producer should preserve behavior as
written:

- Trap category: {type-coercion | validator-constraint | enum-ordering |
                  boundary | spec-bug | normalization | self-report-fidelity}
  Location: {file:line or section}
  Trap: {what's easy to "smooth" that would silently break spec fidelity}
  Expected producer behavior: {preserve the unusual-looking behavior and
                               name the engagement in notes}
```

Calibration-trap library reference: see
`docs/templates/calibration-traps.md` for the taxonomy.

### Self-report directives (retrospective §4.3)

```
In your notes field, explicitly state:
- Whether you read {key method or module} implementation, and what you
  found.
- What you chose to do when you encountered {specific ambiguity the spec
  deliberately leaves open}.
- For surgical-edit / pure-deletion tasks: pre-edit byte count,
  post-edit byte count, delta confirmation.
```

Phase 1 evidence (build_match_score): self-report directives converted
discipline from inferred to directly verifiable. Worker's compliance
surfaces as concrete memo content the reviewer can check at review time.

---

## §11 Acceptance criteria — repeated here for worker convenience

Workers sometimes scan §5 and §11 separately; keeping the acceptance
criteria in both places reduces the chance of a missed criterion.

*(This section is a duplicate of §5 for worker convenience. Keep them
in sync or omit one.)*

---

## Provenance

This template bakes in:

- Phase 1 Update A (validator prompts in §10) — 48-char summary bug
- Phase 1 Update B (A6-standard-edges in §7) — empty-skills, min_years=0
- Phase 1 Update C (accept-with-edits framing in §8) — unclear outcome
  expectations
- Phase 1 Update D (@model_validator enumeration in §10) — second
  validate_expert_needs_evidence bug
- Phase 1 Update E (monkeypatch source-module in testing-conventions) —
  compute_skill_sim C2
- Phase 1 Update F (rendering decisions in §4 / A6-standard-edges (e)) —
  compute_trajectory M1 align_desc
- Session 1-3 signals A / B / C — byte-preservation discipline,
  memo-vs-diff reconciliation, suitability annotations
- Retrospective §2.8 calibration traps — seven trap categories
- Retrospective §4.3 self-report directives — verifiable producer
  behavior

Projects copy this template into their own docs/ or .rsi/tasks/
authoring workflow, extend with project-specific A6 edges in §7 and
project-specific validators / traps in §10.
