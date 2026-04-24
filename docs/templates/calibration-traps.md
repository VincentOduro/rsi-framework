# Calibration-trap taxonomy + authoring guidance

Calibration traps are **deliberate ambiguities** in task specs that test
whether the producer preserves spec-unusual behavior under
semantic-smoothing pressure. Phase 1 planted two (A5 asymmetric 0.3
partial credit; Branch-4 weights override vs validate_composite_formula
hardcode); both fired correctly, and the engagement pattern was
visible in the producer's notes.

The framework ships this **taxonomy** — a vocabulary of trap categories
plus authoring guidance — but does **not** ship curated per-domain
instance libraries. Domain-specific traps (web APIs, trading math, data
pipelines, NLP) have too much variance to generalize usefully; the
expensive part is discovering traps in your own spec, not recognizing
generic patterns after the fact. Projects grow their own instance
collections and (optionally) contribute back to the taxonomy when a
genuinely cross-cutting category emerges.

---

## Why traps earn their cost

Writing traps is extra work at task-spec-authoring time. The cost buys:

1. **Verifiable fidelity signal.** Without traps, "did the producer
   preserve spec semantics?" is inferred from output shape. With traps,
   the answer is observable — the trap either fires correctly or it
   doesn't, and the reviewer checks at §5 of the task spec.

2. **Selection pressure on task-spec quality.** Authoring a trap forces
   the spec author to read the reference closely enough to find the
   ambiguity. Specs with thought-out traps tend to be tighter in every
   other dimension too.

3. **Calibration-drift leading indicator.** If the trap-firing rate
   drops across a sequence of dispatches, something upstream degraded
   (spec authoring, producer, or both). Traps are the framework's
   early-warning system for discipline erosion.

Rough budget: one trap per moderate-complexity task (≥100 lines of
output); two for high-stakes tasks; zero is acceptable for tasks where
no legitimate ambiguity exists (pure deletions, trivial refactors).
Forcing a trap into every spec dilutes the signal.

---

## Taxonomy (seven categories)

Each category comes with: a description of the failure mode, authoring
questions the spec author answers to surface candidate traps, the §10
language pattern that primes producer engagement, and a
fidelity-verification pointer at review time.

### 1. Type coercion traps

**Failure mode:** spec mixes Decimal, float, int, or untyped numerics
with implicit coercion. Producer "normalizes" to a single consistent
type and silently shifts semantics (rounding direction, precision,
overflow).

**Authoring questions:**

- Does the spec's pseudocode quantize before or after arithmetic?
- Are monetary values Decimal but ratios float? Does the producer need
  to know which side of a multiplication dominates?
- Is there an `int()` cast that truncates vs rounds? A `round()` that
  uses banker's rounding vs away-from-zero?

**§10 language pattern:**

```
The spec specifies Decimal quantization AFTER weighted-sum
computation (spec §4.2 line 12). Faithful reproduction must use
Decimal arithmetic for the sum, then quantize once at the end.
Normalizing to floats throughout — as would be tempting for
consistency with other dimensions — changes the quantization
behavior at the 0.005 boundary and breaks 3 of 14 fixture cases.
```

**Verification at review:** check the output's arithmetic path for the
specific coercion sequence. Test cases near quantization boundaries
should surface divergence.

---

### 2. Validator constraint traps

**Failure mode:** `@model_validator`, `@validator`, or equivalent
bodies contain constraints (hardcoded values, field-order dependencies,
cross-field rules) that reading field declarations alone misses.
Producer writes code that passes static inspection but fails at
runtime.

**Authoring questions:**

- Which `@model_validator(mode="after")` methods fire on this model,
  and what do they enforce?
- Is there a validator that expects specific field values (e.g.,
  `weights` summing to 1.0 within epsilon)?
- Does `.model_construct()` bypass validators — is the producer
  tempted to use it as an escape hatch?

**§10 language pattern:**

```
MatchScore has @model_validator(mode="after") named
validate_composite_formula (src/scoring/models.py:142-167).
This validator enforces weights[i] == HARDCODED_WEIGHTS[i]
for all i, with tolerance 1e-9. The producer must NOT bypass
the validator via .model_construct() even if Branch 4's
weights-override API suggests user-supplied weights are
possible — the validator will reject any divergence at
instantiation time.

In your notes, state whether you read validate_composite_formula
implementation and what decision you made about weight handling.
```

**Verification at review:** grep the output for `.model_construct(`
usage on the model; instantiate the model in a test fixture with
the specific edge inputs and assert validator behavior.

---

### 3. Enum ordering traps

**Failure mode:** dict insertion order or enum value ordering carries
semantics (iteration order, display order, first-match wins). Producer
"cleans up" by sorting or reordering and silently changes behavior.

**Authoring questions:**

- Does the spec iterate a dict and produce order-dependent output?
- Is enum value order used as a priority / fallback chain?
- Is there a dict literal where keys are added in the order of
  domain-specific priority (e.g., A/B/C dimensions)?

**§10 language pattern:**

```
The WEIGHT_DIMENSIONS dict in constants.py iterates in
insertion order (Python 3.7+). The order is
[deal_breakers, hard_match, skill_sim, trajectory, prefs] and
matches the spec's priority ordering in §2.1. Producer must
NOT sort by key, alphabetize, or "normalize" the order even
if the dict literal looks unusual — downstream renderers
rely on this order.
```

**Verification at review:** diff the output's dict literals against
HEAD; any reordering is a trap miss.

---

### 4. Boundary traps

**Failure mode:** inclusive vs exclusive thresholds (`<` vs `<=`),
floating-point tolerance, off-by-one in range boundaries.
Producer picks the "cleaner" comparator and shifts semantics at
exactly-at-threshold inputs.

**Authoring questions:**

- Where does the spec say "at least" vs "more than"? Is the threshold
  inclusive?
- Are there floating-point comparisons without explicit tolerance?
- Does the spec specify `>= 0` anywhere that should be `> 0` or
  vice versa?

**§10 language pattern:**

```
The min_years threshold in compute_hard_match uses `>=` not `>`
per spec §3.4: a candidate with exactly min_years of experience
MATCHES (returns True). Producer must preserve the inclusive
boundary even though it reads more naturally as "more than
min_years." Fixture test_boundary_min_years exercises this
exactly-at-threshold case.
```

**Verification at review:** boundary fixtures exercising the exact
threshold should pass; if they don't, the trap was missed.

---

### 5. Spec-bug traps

**Failure mode:** the reference pseudocode contains a defect —
incorrect pluralization, leading-separator artifact, off-by-one —
that faithful reproduction must reproduce (at least until the spec is
formally amended). Producer "fixes" the defect and breaks the
contract the rest of the system was built against.

**Authoring questions:**

- Are there known pseudocode defects (pluralization, formatting,
  array bounds)? Have they been logged in SPEC_AMENDMENTS.md?
- If reproducing the defect feels wrong, has the spec been amended?
  If yes, reference the amendment; if no, the producer still
  reproduces.

**§10 language pattern:**

```
Spec §5.2 contains a known defect: the explanation string for
compute_skill_sim emits a leading ", " when job_reqs is empty.
This has NOT been amended (see SPEC_AMENDMENTS.md I12 for the
tracking entry). Producer must reproduce the defect — downstream
consumers test against the current output shape.

In your notes, state that you noticed the leading comma and
chose to preserve it. Do NOT "fix" it inline.
```

**Verification at review:** the specific defect should appear in the
output. If the producer fixed it, the trap was missed — and the memo
needs to record the engagement decision explicitly.

---

### 6. Normalization traps (Session 2)

**Failure mode:** surgical-edit or pure-deletion task. Producer
silently normalizes encoding (em-dashes, replacement chars, quote
styles), collapses blank lines, reorders imports, or "cleans up"
unrelated sections. The core change lands correctly, but ~N-hundred
additional lines also change without the producer acknowledging it
in notes. Session 2 TASK-E8-008 was the canonical instance.

**Authoring questions:**

- Is this task surgical-edit or pure-deletion?
- Does the file contain characters the producer might "normalize"
  (em-dashes, non-ASCII quotes, mixed line endings)?
- Are there blank lines adjacent to the deletion target that the
  producer might decide to collapse?

**§10 language pattern:**

```
This task is surgical-edit (category). Byte-preservation is
mandatory (see §6). Additionally, note that the file contains
em-dashes and a mix of trailing-whitespace patterns that the
producer must preserve byte-exactly. Do NOT normalize encoding.
Do NOT collapse blank lines adjacent to the deletion target.

In your notes, state pre-edit byte count, post-edit byte count,
and the delta. The delta must equal the sum of lengths of the
three lines deleted in §4 (including trailing newlines).
```

**Verification at review:** this trap category is the primary driver
of review-memo §5 (memo-vs-diff reconciliation). Compare worker's
self-reported delta against actual diff byte count. If they diverge,
the trap fired (producer normalized despite instructions) and the
memo must record the discrepancy before accepting.

---

### 7. Self-report fidelity traps (Session 2)

**Failure mode:** producer's notes field contains claims that are
technically accurate to a narrow question but miss the operator's
scope question. Session 2 Kimi claimed "No other changes" about
TASK-E8-008 while having silently reformatted 174 lines — the claim
was true in the producer's interpretation of "no changes beyond the
deletion" but false in the operator's scope of "only the three
specified lines should differ."

**Authoring questions:**

- What exact claim do I want the producer to make, in their own words?
- What's the narrower interpretation they might give? How do I close
  the ambiguity?
- Is there a quantitative measure (byte count, line count, count of
  changed symbols) that forces specificity?

**§10 language pattern:**

```
Self-report fidelity — state EACH of the following in your notes
field explicitly:

1. Pre-edit byte count of {file}: {N} (measurable — not an estimate)
2. Post-edit byte count of your output: {M} (measurable)
3. Delta: {N - M}. This must equal {expected}. Confirm match or
   name the discrepancy.
4. A claim of "no other changes" is NOT accepted. Instead, affirm
   "only the three lines in §4 differ between pre-edit and post-
   edit, byte-for-byte, including line endings and whitespace."
```

**Verification at review:** cross-check producer's numerical claims
against measurable reality. A claim that "should" be true but isn't
fires the trap; a claim the producer declined to make fires the
trap differently (they recognized the ambiguity and surfaced it).

---

## Authoring guidance

Writing calibration traps is a skill that compounds. Field rules from
Phase 1 + Sessions 1-3:

### Find traps by adversarial reading of the spec

Read the reference (pseudocode, design doc, prior implementation) with
the question *"what's the polished version of this that would be
subtly wrong?"* The polish comes from natural producer behavior —
simpler code, consistent types, cleaner formatting. The wrongness
comes from spec-unusual constraints the polish would erase.

Two useful prompts for finding traps:

1. *"If the producer paraphrased this from memory a week later,
   what detail would they get wrong?"* — catches trap categories 1-5.
2. *"If this were a surgical-edit on a file that already has stylistic
   quirks, what would the producer normalize?"* — catches category 6.

### Trap one thing per trap

A trap is a single specific ambiguity. "The spec is subtle" is not a
trap; "the compute_hard_match min_years threshold is inclusive at
exactly-min-years-of-experience" is a trap. Workers handle specific
better than general.

### Make the verification mechanical

A good trap fires in a way the reviewer can check at a glance — a
fixture test, a grep pattern, a byte-count comparison. If verifying
requires re-reading the full output and reasoning about it, the trap
is too abstract — tighten it or drop it.

### Name the engagement

Every trap §10 block ends with *"state in your notes that you
encountered and how you handled this."* The self-report is not
optional — it converts trap-firing from an inference into direct
evidence.

### One trap per trap task section — don't bundle

If a task warrants two traps, write two separate §10 blocks. Bundling
traps into "here are three things that might go wrong" language
signals "vague warning" to the producer and they engage with none
specifically.

### Traps are not assertions

A trap is a test the producer *might miss*. Don't plant a trap on
something the producer trivially can't miss (e.g., "preserve the
function name compute_hard_match" — it's in the signature). Plant
traps on things the producer *would* miss if reading spec
declarations rather than implementation.

---

## Anti-patterns

### "Aggregate" traps

Do not write "this task contains several traps — preserve spec
behavior carefully." That's not a trap, it's a vague warning. Specific
traps in specific locations.

### Traps that duplicate §7 A6-standard-edges

A trap is stronger than an A6-edge: an A6-edge asks the producer to
*surface* an ambiguity; a trap expects the producer to *navigate* a
spec-unusual behavior correctly. If a §10 calibration trap duplicates
a §7 A6-edge, collapse into one of the two — don't list both.

### Traps without verification hooks

If the reviewer has no observable way to tell whether the trap fired,
the trap adds noise without adding signal. Every trap block must end
with a specific verification: "fixture X should pass," "grep the
output for Y," "byte-count should equal Z."

### Too many traps per task

>2 traps per task spreads producer attention and degrades all of
them. Pick the two highest-value (usually: one logic trap, one
discipline trap) and drop the rest.

---

## Growing project-specific trap collections

RSI ships the taxonomy; projects accumulate instances. A simple pattern:

1. **Capture from live dispatches.** When a task's calibration trap
   fires correctly, the task spec's §10 becomes a project-specific
   example. File it under `docs/project-traps/{category}.md`.
2. **Promote to cross-project.** When a trap instance matches a
   pattern another RSI-using project also faces, propose adding it
   to the canonical taxonomy here. Cross-project instances tend to
   be framework-level: language-level (Decimal coercion), library-
   level (Pydantic validators), or protocol-level (OpenAI SDK
   quirks).
3. **Retire instances that stop firing.** If a trap instance fires
   correctly on 10 consecutive dispatches, the producer has
   internalized the pattern and the trap no longer adds signal.
   Keep the instance archived but drop it from active use.

The framework does not automate any of this; it's retrospective
discipline. But shipping the taxonomy here means every project starts
from a coherent vocabulary rather than reinventing.

---

## Provenance

Seven categories, field-evidence attribution:

- 1 (Type coercion), 2 (Validator constraint), 4 (Boundary), 5
  (Spec-bug): Phase 1 job-platform retrospective §4.2 explicit
  examples.
- 3 (Enum ordering): generalized from Phase 1's dict-iteration
  patterns.
- 6 (Normalization): Session 2 TASK-E8-008 drift (174 lines changed
  while "No other changes" claimed).
- 7 (Self-report fidelity): Session 2 TASK-E8-008 memo-level drift
  (byte-count hallucinated; "No other changes" claim narrowly true
  but operator-scope false).

Authoring guidance drawn from five compounding task-spec generations
across Phase 1 (compute_deal_breakers → build_match_score).
