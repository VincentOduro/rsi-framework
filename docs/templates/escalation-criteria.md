# Escalation criteria template

When Claude Code (operating as overlord / reviewer / dispatcher) should
**pause and escalate to the operator** rather than proceeding
autonomously. These are hard checkpoints in the self-review protocol —
when any fire, the decision moves from `apply-with-edits` or
`re-dispatch` to `surface-to-operator` per review-memo §2.

Per Q4 resolution: RSI ships these criteria as a template; the
**operator** decides which apply in their context. Projects override or
extend the list in their own `docs/escalation-criteria.md` — this file
is a canonical baseline, not a mandate.

The criteria come out of retrospective §2.8: Claude Code's self-review
has structural limits (can't catch its own systematic blind spots, has
momentum bias toward apply, lacks gap for self-contradiction). The
escalation criteria are where those limits become visible — if you're
about to self-decide past one, stop and invite operator judgment
instead.

---

## §1 The six canonical criteria

Any ONE firing is sufficient cause to escalate. Most dispatches fire
zero; high-stakes work may fire one or two.

### 1. Severity-Critical finding not addressable as a specific code change

If §1 of the review memo names a **Critical** finding and §3's proposed
edits can't contain it (requires re-dispatch, scope change, or design
revisit), that's a decision larger than self-review carries authority
for. The pattern from Phase 1: Critical findings that are "fix the
approach" rather than "fix this line" belong in surface-to-operator.

**Apply when:** the Critical finding's remedy spans more than the
overlord's local edit budget (typically: structural algorithm change,
schema migration, cross-module refactor).

**Do not apply when:** the Critical is a single file's worth of changes
the overlord can make during review time.

### 2. Meta-change to task-spec, review, or self-review protocol

Changes to the templates themselves, the self-audit questions, the
escalation criteria (this file), or the calibration plan are
**framework-level** decisions. Self-review cannot modify the rules
it's evaluated against without the operator's sign-off.

**Apply when:** the decision involves editing `docs/templates/*.md`,
`docs/escalation-criteria.md`, or equivalent framework assets. Even a
"small wording change" on these warrants operator awareness because
they propagate across every future dispatch.

**Do not apply when:** extending a project-specific appendix (e.g.,
adding a §7 project-specific convention to `testing-conventions.md`).

### 3. Re-dispatch (not apply-with-edits)

Kimi / MiniMax token spend is real operator cost. A re-dispatch means
another full API call, more latency, more memory / dashboard churn,
and the prior dispatch's billed output gets superseded. Operator may
prefer to accept the prior output with overlord edits rather than
re-dispatching — the calculus is theirs, not self-review's.

**Apply when:** the review memo's decision is `re-dispatch`. Surface
the proposed revised task spec (§4 of review memo) and let operator
confirm before dispatching.

**Do not apply when:** decision is `apply-with-edits`, even if the
edit set is large — edit-cost is overlord time, not token spend.

**Exception:** if the operator has explicitly delegated re-dispatch
authority for a specific task category (common during bulk refactor
sessions), honor that. Record the exception context in review memo §2.

### 4. Novel failure pattern not matching prior calibration data

Something happened that no prior review memo or memory artifact
captures. New error category, new discipline gap, new worker
behavior. Self-review can't tell whether it's a one-off or the start
of a pattern; only operator time-series awareness can.

**Apply when:** the failure observed doesn't match anything in
`.memory/reviews/accepted/` or `.memory/rounds/` for this project
/ worker combination.

**Do not apply when:** the failure matches a known pattern (even if
the specific trigger is new) — precedent exists for the disposition.

**Examples of novelty worth escalating:** worker emits a format no
prior dispatch emitted; a trap fires in an unexpected direction (see
§6); a known-green test fails after an unrelated commit.

### 5. Self-review vs prior-session conclusion disagreement

If this session's self-review is about to reach a decision that
contradicts an explicit decision from a prior session's review or a
documented memory artifact, that's **cross-session drift**. Self-review
can't tell whether prior-self or current-self is right; external
perspective is the only way to resolve.

**Apply when:** this review's decision would overturn or substantially
revise a prior review memo's decision, a prior retrospective's
conclusion, or a documented framework decision (`docs/*.md`,
`.rsi/*.yaml`).

**Do not apply when:** this review extends or refines a prior decision
without overturning it — extension is normal discipline.

### 6. Calibration trap firing in unexpected direction

Two sub-cases, both warrant escalation:

- **Producer bypasses a trap unexpectedly.** Spec says preserve the
  spec-unusual behavior; producer preserves it correctly; reviewer
  discovers that the spec was actually the wrong call and the
  producer's "mistake" was right. Could mean the trap itself was
  miscalibrated, or the spec has an undiagnosed defect.
- **Producer engages with a trap that was actually a real constraint.**
  Spec planted an ambiguity as a trap; producer treats it as a real
  spec-unusual behavior and preserves it; reviewer discovers the trap
  was meant to fire in the opposite direction and the "correct"
  behavior was actually "fix it." Spec-author error on trap
  placement.

**Apply when:** trap outcome doesn't match trap-authoring intent, in
either direction. Trap design is a framework-level discipline; getting
it wrong enough to warrant escalation is a useful signal.

**Do not apply when:** trap fires as intended (producer preserves
spec-unusual behavior, reviewer verifies). That's the happy path —
record in review-memo §6 (calibration signal naming).

---

## §2 Escalation mechanics

When a criterion fires:

1. **Set review-memo §2 decision to `surface-to-operator`.** Don't
   attempt to self-decide.
2. **In §2 decision reasoning, name which criterion fired** (e.g.,
   "escalation-criteria §1.3 re-dispatch cost"). Makes it easy for
   operator to jump to the relevant context.
3. **Include the findings verbatim plus any preliminary self-review
   analysis.** Operator may accept self-review's implicit preference
   or override.
4. **Do not proceed to apply, re-dispatch, or commit.** The review
   memo sits in `.memory/reviews/pending/` awaiting operator response.
5. **Record the operator's resolution in the memo's §2 once received.**
   Include the operator's reasoning — future self-review on similar
   tasks needs the precedent.

---

## §3 Escalation is a feature, not a failure

Each criterion above exists because an incident happened. Avoiding
escalations via self-override is the wrong optimization. The right
optimization is **earning trust** — a track record where escalations
surface real decisions worth operator time and routine work proceeds
autonomously.

Phase 1 / Session 1-3 calibration: escalations averaged 0-1 per
session. Above that rate suggests the producer, the task specs, or
the self-review protocol need tightening. Below that rate suggests
self-review may be auto-applying past legitimate escalation points —
worth operator review at phase boundaries.

---

## §4 Project-specific extensions

Projects add criteria to their own `docs/escalation-criteria.md` that
reflect their domain. Examples (illustrative — these are for
reference, not canonical):

- **Security / financial:** any code change touching auth, payment, or
  PII flows escalates regardless of other criteria.
- **Public API:** any change to exported types / HTTP endpoints
  escalates.
- **Migration / schema:** anything touching a live database schema or
  data migration escalates.

Project extensions are **additive only** — don't remove a canonical
criterion; extending with stricter domain rules is fine.

---

## Provenance

Six criteria from retrospective §2.8's "Explicit human-escalation
criteria" section:

1. Severity-Critical not local-fixable
2. Meta-change to framework assets
3. Re-dispatch token cost
4. Novel failure patterns
5. Cross-session self-review / prior-session disagreement
6. Unexpected trap outcomes (bidirectional)

Escalation mechanics (§2) and the "escalation is a feature" framing
(§3) are Session 4 additions — the retrospective stated the criteria
but didn't codify the procedural and attitude guidance that keeps
criteria from calcifying into busywork.
