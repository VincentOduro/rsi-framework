# Review memo — base template

**Canonical path for instances:** `.memory/reviews/pending/TASK-{ID}.md`
(framework-generated; edit in place during review, then accept/reject moves
it to `.memory/reviews/accepted/` or `.memory/reviews/rejected/`).

This template is copied / instantiated for every worker dispatch that lands
in review queue. The review memo is the overlord's durable record of why a
worker's output was accepted, rejected, or revised — and the primary
artifact that supports self-review discipline (see §6 below).

The framework provides this template but does not enforce it by tool gate.
Per the RSI decomposition's Q3 resolution, tool-gating review memos turns
the framework into a policy engine it isn't designed to be. Template-only
support is sufficient: the ceremony layer surfaces memo presence/absence
as a warning, and review-memo quality is an operator discipline concern.

---

## §0 Identification

```
**Task:** TASK-{ID}
**Dispatched:** {ISO-8601 UTC timestamp}
**Worker:** {kimi | minimax | ...}
**Model:** {actual model ID that produced the output}
**Task category:** {algorithm | logic | surgical-edit | pure-deletion | other}
**Status:** {PENDING REVIEW | ACCEPTED | REJECTED | REVISED}
```

The **task category** field matters for calibration: surgical-edit and
pure-deletion categories carry different suitability assumptions than
algorithm implementation. See `docs/templates/task-spec-base.md` §0 for the
category vocabulary.

---

## §1 Findings (severity-tiered)

Findings are what the review *found*, not a restatement of what the worker
did. Every finding must be actionable — either the worker's output is fine
as-is, or specific changes are proposed.

**Tier definitions — use these criteria, not gut-feel tiering:**

- **Critical** — the output would fail at runtime, violate a spec
  constraint, corrupt data, or introduce a security vulnerability. Not
  "could be better"; "will break something."
- **Medium** — a real issue that would slip past and cause pain later:
  test gaps, latent edge-case bugs, fragile patterns, incorrect
  assumptions that happen to work today.
- **Low** — style / minor / nice-to-have. Things a future reader might
  notice but that don't affect correctness.
- **Compliments** — what the producer did *well*. This is not flattery —
  it's calibration data for the next dispatch. Compliments name specific
  behaviors (e.g., "preserved the validate_composite_formula trap by
  reading the validator's implementation explicitly") so patterns of
  good behavior can be reinforced in future task specs.

### Critical

- [ ] *{none identified / finding description}*

### Medium

- [ ] *{none identified / finding description}*

### Low

- [ ] *{none identified / finding description}*

### Compliments

- *{specific behavior worth naming}*

---

## §2 Decision

**Decision:** `{apply-with-edits | re-dispatch | surface-to-operator}`

### Decision vocabulary

- **apply-with-edits** — output is substantially correct; overlord applies
  with listed small edits in §3. Use when findings are all specific code
  changes the overlord can make without re-consulting the producer.
- **re-dispatch** — output has a design-level problem (wrong signature,
  wrong algorithm approach, missing abstraction, scope violation,
  byte-preservation failure). Use when fixing requires the producer to
  regenerate with a revised task spec in §4.
- **surface-to-operator** — output introduces novel ambiguity requiring
  operator judgment. Use sparingly — this is the escalation path when
  self-review can't produce a confident decision.

### Decision reasoning

{1-3 sentences on why this decision follows from the findings. Not
optional — the reasoning is what makes the decision auditable later.}

---

## §3 Proposed edits — for `apply-with-edits`

Specific, concrete changes the overlord will make before applying. Edits
framed as "improve X" are insufficient; edits framed as "change line Y
from A to B because C" are actionable.

- [ ] *{file}: line {N} — change from `{before}` to `{after}`. Reason: {why}.*

(Remove this section or leave blank if decision is not `apply-with-edits`.)

---

## §4 Revised task instructions — for `re-dispatch`

The revised task spec for the next dispatch. May be a full replacement
task spec or a delta on top of the prior one. Either way, spell out what
changed from the original and why.

```
Changes vs prior dispatch:
- {change 1}
- {change 2}

Revised task spec body follows:

{paste or reference the revised spec}
```

(Remove this section or leave blank if decision is not `re-dispatch`.)

---

## §5 Memo-vs-diff reconciliation (Signal B — from Session 2 U3)

If the worker self-reported counts, scope, or "no other changes" claims,
reconcile against the actual diff before accepting. Kimi's Session 2
self-reports for TASK-E8-008 claimed "pure deletion of three lines" while
the diff showed 174 changed lines (mostly blank-line removal and
line-ending normalization). Catching that discrepancy required an
explicit diff comparison; the memo language alone was misleading.

```
Producer claimed:   {paste exact claim from worker's notes, or "no explicit claim"}
Actual diff shows:  {files changed, lines added, lines removed, notable categories of change}
Discrepancy:        {none | {specific} — investigate before accepting}
Resolution:         {accepted as-is | rejected / re-dispatched | surgical accept of partial}
```

For surgical-edit and pure-deletion tasks, running a concrete byte or
line-count comparison is part of the acceptance criterion — not optional.

---

## §6 Self-review protocol

The six self-audit questions below are the framework's substitute for an
external reviewer-of-reviewer layer. They force the reviewer to reconsider
each finding, catch momentum bias, and name the calibration signals that
would otherwise stay implicit. An empty or "none applicable" answer is
*accepted* — the prompt forces consideration, not a specific answer.

These questions complement the six escalation criteria in `docs/templates/
escalation-criteria.md`. If answering honestly points at an escalation
criterion, set the decision to `surface-to-operator` rather than continuing.

### 1. Severity reconsideration

*For each Critical / Medium / Low finding above: is the tier right, or am
I inflating/deflating for momentum reasons? Specifically — did I mark
something Critical that's actually Low because I want the producer to
re-dispatch, or mark something Medium as Low because I don't want to
block apply?*

*Answer: {explicit reconsideration, or "all tiers stand"}*

### 2. Category-completeness

*Did I address every standard finding category? Check each:*

- *Pydantic / runtime validator violations: {addressed / n/a}*
- *Test-side bugs (fixture setup, assertion shape, monkeypatch target): {addressed / n/a}*
- *Ambiguity surfacing (did producer engage with A6 edges in the task spec?): {addressed / n/a}*
- *Template rendering decisions (explanation strings, pluralization, formatting): {addressed / n/a}*
- *Style consistency with surrounding code: {addressed / n/a}*
- *Spec fidelity (did producer paraphrase vs read?): {addressed / n/a}*

### 3. Decision bias check

*Does my apply/re-dispatch decision follow from the findings, or am I
biasing toward apply because re-dispatch is expensive (token cost,
operator time, rework)?*

*Answer: {explicit acknowledgment — if bias is present, name it, then
decide whether it's a legitimate trade-off or a discipline failure}*

### 4. Steelman requirement

*What's the strongest case for the OPPOSITE decision? If I chose
apply-with-edits, what would justify re-dispatch? If I chose re-dispatch,
what would justify apply?*

*If I can't construct a steelman in 1-2 sentences, the decision isn't
considered enough — revisit findings or escalate.*

*Answer: {steelman for the opposite decision}*

### 5. External-reviewer simulation

*If a fresh reviewer-of-reviewer (Opus-in-chat or equivalent) read this
memo cold, what would they push back on? Are any findings vague,
decisions under-justified, or reconciliation fields skipped?*

*Answer: {anticipated pushbacks, or "nothing stands out"}*

### 6. Calibration signal naming

*What did the producer do well that's worth naming as a pattern to
reinforce in future task specs? What did they do that matches or diverges
from prior dispatches for this project / worker? Specifically — did any
calibration traps from the task spec fire correctly, and did the producer
surface the engagement in their notes?*

*Answer: {specific behaviors worth naming; trap-firing report}*

---

## §7 Metadata

```
Tokens used:        {N}
Latency:            {N.N seconds}
Raw sidecar path:   .memory/reviews/results/TASK-{ID}.raw.txt (F6)
Review length:      {approximate word count of this memo}
```

---

## Suitability annotations (Signal C — task-category → producer-fit)

For reference at dispatch-planning time, not review time. These are
*priors*, not rules. Real task nature overrides the default.

| Category            | Kimi fit   | MiniMax fit | Key framing requirement                     |
|---------------------|------------|-------------|---------------------------------------------|
| Algorithm           | Well-suited| Well-suited | Standard task-spec template                 |
| Logic change        | Well-suited| Well-suited | Style-neutral framing                       |
| Surgical edit       | Mixed      | Mixed       | Explicit byte-preservation instruction      |
| Pure deletion       | Risky      | Mixed       | Highest normalization-drift risk — consider direct edit |
| Test authoring      | Well-suited| Well-suited | Include source module for monkeypatch paths |
| Docs / prose        | Variable   | Variable    | Often faster direct — delegate only when operator capacity constrained |

See `docs/templates/task-spec-base.md` §0 for task-category framing
language. Kimi's "mixed" / "risky" annotations are calibrated from
Session 1-3 evidence: Kimi silently normalizes encoding / collapses
blank lines / hallucinates byte-count self-reports on surgical tasks.
MiniMax is similar on encoding but less prone to self-report drift.

---

## Provenance

This template is the framework's canonical starting point. Projects copy
into `.memory/reviews/pending/` at dispatch time, fill during review.
Field evidence driving the template shape:

- Phase 1 compute_hard_match drift (memo-less dispatch degraded multi-layer
  review to "paste raw and wait") — established memo as a first-class
  artifact (retrospective §2.4).
- Session 2 TASK-E8-008 (Kimi "no other changes" claim vs 174-line diff) —
  established Signal B memo-vs-diff reconciliation as required, not
  optional (retrospective §2.8 revision, Session 2 calibration signal B).
- Session 2 task-suitability observations — established Signal C category
  annotations.
- Retrospective §2.8 — six self-audit questions (§6 above).

Projects extending this template should keep the §0-§7 structure stable;
project-specific additions belong in appendices below §7.
