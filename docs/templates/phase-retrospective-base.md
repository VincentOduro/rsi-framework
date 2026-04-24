# Phase retrospective — base template

**Canonical path for instances:** `docs/retrospectives/{phase}.md`
(project-owned; the RSI project itself uses this path for the
job-platform-phase-1 retrospective).

Phase boundaries are the operator's chosen points — end-of-quarter,
completion of a multi-algorithm arc, pre-major-release, or wherever
else operator context says "worth pausing to audit." The framework
does not prescribe cadence (Q4 resolution: operator owns cadence;
RSI ships template + guidance + self-audit checklist).

---

## §0 Phase boundary framing

```
**Phase:** {short name — e.g., "Phase 1 algorithm implementation"}
**Period:** {start date → end date}
**Dispatches covered:** {count, or enumerate TASK IDs}
**External reviewer invoked:** {yes / no, and who}
```

The "external reviewer invoked" field matters for calibration: Phase 1
had Opus-in-chat as a structural layer. Sessions 1-3 ran without
Opus-in-chat. Which regime you're in changes what the retrospective is
*for* — diagnostic vs confirmatory.

---

## §1 What the phase delivered

Factual summary: tasks completed, features shipped, framework commits
landed. No evaluation yet.

```
- {deliverable 1 — commit SHA or TASK ID, brief description}
- {deliverable 2}
- ...
```

Two to ten bullets. If the list stretches past ten, phase scope was
too broad for a single retrospective — decompose.

---

## §2 Calibration signals (quantitative where available)

Observable signals that accumulated across the phase. Calibration data
is the evidence base the rest of the retrospective reasons from.

### 2.1 Finding distribution across dispatches

```
Dispatches reviewed:   {N}
Critical findings:     {M_c} ({M_c/N:.1%})
Medium findings:       {M_m} ({M_m/N:.1%})
Low findings:          {M_l} ({M_l/N:.1%})
Compliments logged:    {M_p}
```

Trend across the phase: finding count decreasing → producer / spec /
self-review is tightening. Flat or increasing → something's drifting;
name what.

### 2.2 Calibration-trap outcomes

```
Traps planted:         {T}
Traps fired as intended: {T_correct}
Traps misfired:        {T_miss}  (enumerate below)
```

For each misfire: the task, the trap category, the producer's actual
behavior, the spec-author's intent, and the disposition (escalated /
self-reconciled / logged for next phase).

### 2.3 Escalation rate

```
Dispatches:            {N}
Escalations:           {E}
Escalation-to-dispatch ratio: {E/N:.2f}
```

Phase 1 / Session 1-3 calibration: 0-1 escalations per session
(~0.1-0.3 per dispatch). Rates above 0.5 signal either spec-
authoring churn or self-review uncertainty; rates at 0 across >10
dispatches signal self-review possibly auto-applying past escalation
points (see `docs/templates/escalation-criteria.md` §3).

### 2.4 Decision distribution

```
apply-with-edits:      {A}
re-dispatch:           {R}
surface-to-operator:   {S}
```

Healthy mix: mostly apply-with-edits with occasional re-dispatch and
rare surface-to-operator. A phase dominated by re-dispatch suggests
task-spec quality gaps; a phase dominated by surface-to-operator
suggests the producer / worker configuration isn't matched to the
task category (re-check Signal C suitability in review-memo-base.md).

### 2.5 Memo-vs-diff reconciliation outcomes

For surgical-edit / pure-deletion tasks specifically:

```
Surgical tasks in phase:        {N_s}
Byte-count self-report accurate: {N_s_correct}
Byte-count self-report drift:    {N_s_drift}  (enumerate)
```

Drift rate trend informs worker-suitability annotations for the next
phase.

---

## §3 What worked

Not just feel-good content — calibration data worth reinforcing.
Specific behaviors, specific framings, specific templates that paid
out. Each entry describes the pattern concretely enough that it can
be applied to the next phase's task specs.

```
- {Specific producer behavior and the §10 language that primed it}
- {Specific review-memo pattern that caught a class of issue}
- {Specific task-spec framing that cut finding count}
```

---

## §4 What didn't work

Honest catalog. Not blame — failure analysis for the framework's
discipline loop.

For each item: the pattern, the incident count, the proposed fix (if
any), and who owns the fix.

```
### 4.1 {Pattern name}

**Description:** {what happened, specifically}
**Incidents:** {TASK IDs or session references}
**Root cause hypothesis:** {best current understanding}
**Proposed fix:** {specific change — task-spec template edit,
                    calibration-trap addition, escalation criterion
                    update, etc.}
**Owner:** {operator / framework / project / deferred}
```

---

## §5 Self-review self-audit

The calibration plan (Q4 resolution, retrospective §2.8) specified
scheduled self-audits on self-review quality itself. At a phase
boundary, the operator (or external reviewer, if invoked) reads the
last N review memos and asks:

### 5.1 Were there findings self-review missed?

Read a sample of accepted-as-applied dispatches. Would an external
reviewer have flagged anything the memo didn't? If yes, the missed
category becomes a candidate §6 self-audit question for the next
phase's review-memo template extension.

### 5.2 Severity-tier inflation or deflation patterns?

Look for: Critical findings that landed as apply-with-edits without
re-dispatch (possible deflation — "it's critical but I wanted to
ship"). Medium findings that blocked for a week (possible inflation —
"I marked it Medium to justify pausing").

Either direction signals momentum bias the self-review §3 decision-
bias question is supposed to catch. If it's not catching, strengthen
the prompt.

### 5.3 Decision patterns diverging from what external review would have chosen?

Compare self-review's decisions on a sample against what the operator
(or a newly-invoked external reviewer) would have decided. Divergence
is either (a) legitimate — self-review has context the operator
doesn't — or (b) drift — self-review is optimizing for something
other than the operator's goals. Name which.

### 5.4 Drift from established template conventions?

Check recent task specs and review memos against the canonical
templates. Has drift accumulated? If yes, either (a) the drift
reflects a legitimate evolution — propagate back to the templates,
or (b) it's discipline erosion — restore from canonical.

---

## §6 Decisions carried forward

The retrospective's actionable output: what the next phase does
differently. Each decision becomes a docs update, a template change,
or a calibration-trap addition.

```
- {Decision}. Changes: {specific file or template section}. Rationale:
  {which calibration signal or incident motivated it}.
- ...
```

If §6 is empty, the retrospective produced no new framework evolution.
That's a signal — either the phase was a steady-state hum (possible,
especially after a framework-churn arc) or the retrospective didn't
dig deep enough.

---

## §7 Provenance and revision history

```
**Written by:** {operator / claude-code / opus-in-chat / collaborative}
**First draft:** {date}
**Revisions:** {list revision dates + what changed + who drove}
**Sources:** {specific memos, commit ranges, memory artifacts}
```

---

## Calibration plan — cadence guidance (Q4)

**RSI ships this template; operator owns the cadence.** Frameworks
that prescribe phase boundaries land in awkward places (quarter ends
that don't match work phases, automated gates on rates that fire
during legitimate ramp-up). Human judgment on "when is a phase
worth retrospecting" is the durable answer.

That said, three cadence anchors are useful:

1. **Feature-arc boundary.** End of a multi-task sequence that
   produced a coherent deliverable. Phase 1 job-platform used this
   anchor — five algorithms from compute_deal_breakers through
   build_match_score.
2. **Operator-initiated pause.** "I'm going to sit with this for a
   day before starting the next arc." Treat that pause as a phase
   boundary opportunity.
3. **Escalation-rate spike.** If escalations exceed 0.5 per dispatch
   across several sessions, something's drifting — a retrospective
   may diagnose.

**Do NOT** trigger retrospectives on schedule alone (every N weeks,
every M dispatches) unless the operator explicitly wants that
cadence. The signal-to-noise ratio of scheduled retrospectives on
flat periods is poor.

---

## Provenance

Template structure derived from the
`rsi-retrospective-from-job-platform-phase-1.md` document delivered
to the RSI project in Session 1. That document's §0-§7 organization
(framing → deliverables → problems → gaps → calibration → lessons →
prioritization → meta) is the implicit template; this file makes the
shape explicit and portable.

Calibration plan sub-sections (§2, §5) derive from retrospective
§2.8's "Calibration plan" proposal (Q4 scope). Operator-owns-cadence
boundary from Q4 resolution during RSI decomposition session 4.
