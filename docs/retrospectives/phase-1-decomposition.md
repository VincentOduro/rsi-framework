# Phase 1 Retrospective — Decomposition & Prioritization (v2)

**Source:** [docs/retrospectives/job-platform-phase-1.md](docs/retrospectives/job-platform-phase-1.md) — revised v2 (635→920 lines).
**This document:** v2, rewritten after the retrospective's own v2 integrated this decomposition's v1 pushback and introduced §2.8 (automated self-review).
**Context:** The retrospective and this decomposition are in active dialogue. v1 recommendations on §2.4 (template-only), §3.2 (Option 2), §2.7 (bundle with U5), and §4.6 (defer) were accepted and are no longer open. §2.8 is a new, substantial architectural addition that needs its own analysis.
**Scope:** Analysis only. No code. No commits to `scripts/`. First-session implementation scope proposed at the end; work starts only after operator signs off on the design questions below.

---

## 1. Evidence reading — still grounded

The bug-level evidence in §1 was verified in-tree during v1 and hasn't changed. Short recap:

| Tag | Status | Location |
|---|---|---|
| U5 | Confirmed latent | [scripts/classify_file.py:74](scripts/classify_file.py:74) |
| U1 | Confirmed | [scripts/self_verify.py:351](scripts/self_verify.py:351) |
| U6/F5 | Confirmed | [scripts/delegate.py:741](scripts/delegate.py:741) |
| F9 | Confirmed | [scripts/delegate.py:340](scripts/delegate.py:340) |
| F6 | Confirmed | [scripts/delegate.py:823](scripts/delegate.py:823) |
| U3 | Confirmed shape | [scripts/self_optimization.py:324](scripts/self_optimization.py:324) |
| F3 | Confirmed | [scripts/ceremony.py:113](scripts/ceremony.py:113) |
| 9b | Trusted (verify at impl time) | `scripts/delegate.py` |

What changed in v2: retrospective §2.4 revised to template-only, §2.7 elevated and bundled with U5, §3.2 revised to Option 2, §4.6 marked explicitly deferred. All four align with v1 pushback and are no longer contested.

---

## 2. Analysis of §2.8 — automated self-review

§2.8 is the substantive new content in v2. The retrospective frames it as a "target architecture" shift: current three-layer (operator + Opus-in-chat + Claude Code) reduces to two-layer (operator + Claude Code with framework-supported self-review). Six sub-capabilities proposed:

1. Self-review protocol as first-class memo content (six self-audit questions)
2. Calibration-trap libraries (five trap categories, per-domain instances)
3. Memory-driven consistency enforcement (active consultation of prior artifacts)
4. Self-audit prompts at decision points (pre-commit checks)
5. Explicit human-escalation criteria
6. Calibration plan (scheduled external-reviewer sessions)

The retrospective is honest about the limits: "self-review can't catch its own systematic blind spots by definition" and "whether framework-supported self-audit captures that 10% is an empirical question that gets answered by running the architecture."

### Where I agree with §2.8

- **Direction is right.** Single-agent discipline-supported loops are RSI's natural aim. The framework exists to enforce discipline on the overlord's work; self-review is discipline applied to the review itself. Coherent extension of scope.
- **Sub-capabilities 1, 4, 5 (self-audit questions, pre-commit checks, escalation criteria) are template and documentation work.** They're valuable and small. A session each, at most.
- **Sub-capability 2 (trap library) is the right frame at the taxonomy level.** Type coercion / validator constraint / enum order / boundary / spec-bug is a real typology. Framework can ship the taxonomy plus authoring guidance without shipping domain-complete instance libraries.
- **Sub-capability 3 (memory-driven consistency) is a template convention that RSI already has the plumbing for.** Module A memory exists; the missing discipline is mandated consultation before task-spec authoring.
- **The honest caveat at the end of §2.8 is the right epistemic posture.** "We don't know if this will work; the calibration plan exists to find out." Don't build the whole architecture in advance of evidence.

### Where I push back on §2.8

**1. The monolithic framing overstates the scope.** The retrospective proposes Session 5a through 5d as a multi-session arc. In the sub-capability-level decomposition above, I count roughly 3 sessions of framework work, not 5+:

- Session 5a (self-review protocol in memo template) — real, 1 session
- Session 5b (trap library) — taxonomy + authoring doc is 1 session; instance libraries are per-project work the framework doesn't ship
- Session 5c (memory-driven consistency) — template convention + one delegate-layer read hook, 1 session
- Session 5d (escalation criteria + calibration plan) — escalation criteria is a doc (small); calibration plan is *operator discipline*, not framework capability (see point 2)

Net framework work: ~3 sessions, partially bundleable with Session 4 (since most of it lives in `rsi/templates/`). The retrospective's framing inflates the perceived cost.

**2. The calibration plan is not framework work — it's operator discipline.** "Scheduled external-reviewer sessions every N dispatches" is a project-operations decision, not a framework capability. RSI can ship a *retrospective template* (a doc, ~1 session). Setting the external-review cadence, actually running external reviews, and feeding their output back into self-review protocol — those are operator actions that no tool can enforce usefully. If RSI tried to enforce them (e.g., `rsi dispatch` refusing to proceed after N dispatches without an external-review sidecar), it would be imposing a workflow on projects that may or may not have Opus-in-chat available. Scope creep.

**3. The "trap instance library" has a sinkhole risk.** Every domain has different traps. Web/systems/data pipelines/trading/NLP all have distinct semantic-smoothing pressure points. If RSI tries to ship domain-complete libraries, it becomes a curation problem the framework can't win. Ship the **taxonomy** and **authoring guidance** ("here's how to identify a calibration trap in your domain; here's the prompt shape for planting one"); let per-project trap collections grow organically from real review cycles. RSI absorbs traps back into the canonical library when they've generalized (proven useful across multiple projects).

**4. "Opus-in-chat disappears entirely" is probably too strong, even as an aspiration.** The retrospective uses both framings: "disappears entirely or becomes invocable on-demand." The second framing is realistic; the first is not. Self-review will have blind spots by definition (the retrospective says so). External review needs to remain an available-and-sometimes-mandatory checkpoint, not a removed layer. Framing matters for scope: building toward "external review is optional for routine work, required at phase boundaries" is achievable; building toward "external review is never needed" commits to a target that the calibration plan itself admits is empirically uncertain.

**5. Sub-capability 3 (memory-driven consistency) has an enforcement-cost question that §2.8 glosses over.** The proposal: "before task-spec authoring, Claude Code must read [prior memos, calibration data, template decisions, cross-session commitments]." How is "must" enforced? Three options, each with costs:
- Hard-enforced (delegate refuses to dispatch without a consistency-note in the task spec): forces discipline but adds friction that's unevenly valuable across task types.
- Template-prompted (task-spec template has a "## Consistency note" section Claude Code fills in, but no tool check): same as the rest of the template — discipline by visibility.
- Audit-after-the-fact (ceremony output flags missing consistency-notes): catches drift without blocking.
  
  Template-prompted with audit-after seems right. Hard enforcement is premature given how variable the value is across task types.

### What §2.8 looks like after decomposition

Same sub-capabilities, re-sequenced and re-scoped:

| Sub-capability | Work shape | Session estimate | Bundled with |
|---|---|---|---|
| Self-review protocol (six self-audit questions in memo template) | Template expansion | ~1 session | Session 4 Track A (`rsi/templates/review-memo-base.md`) |
| Trap library taxonomy + authoring guidance | Documentation | ~1 session | Session 4 Track A or separate |
| Memory-driven consistency (task-spec template addition + optional audit hook) | Template + small tooling | ~1 session | Session 4 Track A or separate |
| Self-audit prompts at decision points | Documentation | ~0.5 session | Can fold into memo template |
| Human-escalation criteria | Documentation | ~0.5 session | Can fold into memo template |
| Calibration plan | Retrospective template (doc) | ~0.5 session | Becomes a retrospective-template artifact |

Total net-new framework work for §2.8: ~3 sessions if decomposed this way, much of it naturally falling into Session 4's scope (which already ships `rsi/templates/`). The "Session 5a-d" framing in the retrospective is a valid alternative if operator wants §2.8 treated as a dedicated architectural initiative with its own session arc; but it's not required by the work itself.

---

## 3. Revised prioritization sequence

### Session 1 — Bug batch (unchanged)

- U5 + §2.7 (classify_file.py fix + amendment-log structure, single commit)
- F6 + 9b (raw sidecar + delimiter parser)
- U1 (self_verify diff-scope)
- U6/F5 + F9 (per-worker temperature + max_output_lines)

**Estimated effort:** 1 session, maybe 1.5 if F6+9b sidecar layout takes design thought.
**Blocks on:** nothing new. All design questions for this session are resolved.
**Exit condition:** framework at parity with job-platform fork, tests green, architecture.yaml documents new per-worker fields.

### Session 2 — Calibration

- U3 (Module C argv contract — operator resolution: treat `parse_args()` as vestigial (option a), delete it, run RSI test suite, observe what breaks. If nothing breaks, it was dead code. If something breaks, the breakage reveals whether defensive-default (option b) or intentional-broken-contract (option c) is the right fix. Empirical in minutes; no abstract reasoning.)
- F3 (ceremony content-type heuristic)
- U4 (pre-commit strictness config)
- U2 (Module B programmatic mode)

**Estimated effort:** 1-2 sessions.
**Blocks on:** nothing. Q1 resolved empirically during session.

### Session 3 — Worker-genericization thread-through

- §2.1 incremental: thread temperature + max_output_lines + timeout + extra_body + output_format_preference through `delegate.py` without WorkerProfile dataclass.
- §2.3 format-flexibility parser chain (parser priority per worker config).

**Estimated effort:** 1-2 sessions.
**Blocks on:** nothing (builds on Session 1's per-worker config shape).

### Session 4 — Framework asset corpus (operator-accepted scope)

Per operator resolution on Q2: §2.8 collapses into Session 4 rather than Session 5+. Single framework-assets arc. Per Q5: memo templates first, task-spec library center, supporting docs last. Split at task-spec-library boundary (4a / 4b) if scope demands during the session.

**Track 4a — Memo discipline foundation (first):**
- §2.4 review-memo template (`rsi/templates/review-memo-base.md`): severity-tiered findings, decision vocabulary (`apply-with-edits` / `re-dispatch` / `surface-to-operator`), proposed-edits section, standard artifact path
- §2.8 self-review protocol: six self-audit questions baked into memo template (severity reconsideration, category-completeness check, decision bias check, steelman requirement, external-reviewer pushback imagination, calibration-signal naming)
- §2.8 self-audit prompts at decision points (pre-commit checklist appendix to memo template)
- §2.8 escalation criteria (appendix to memo template: when Claude Code must pause for operator input)

**Track 4b — Task-spec corpus (center):**
- §2.5 task-spec template (`rsi/templates/task-spec-base.md`): §0-§10 structure, Updates A-F baked in
- §2.8 consistency-check section (per Q3 resolution: template-prompted + audit-after, not hard-enforced. Task-spec template has `## Consistency check` section requiring explicit statements about prior memos consulted, template decisions acknowledged, calibration data considered. Blank or "not applicable" accepted — prompt forces consideration, not specific answer. Retrospectives audit for drift patterns.)
- §2.8 calibration-trap authoring guidance + trap taxonomy reference (`rsi/templates/calibration-traps.md`): five trap categories (type coercion, validator constraint, enum order, boundary, spec-bug) with authoring pattern per category

**Track 4c — Supporting corpus (last):**
- §2.6 testing conventions (`rsi/docs/testing-conventions.md`): three sections from job-platform (monkeypatch source-module, pytest fixture discovery, xfail seen-twice)
- §2.8 calibration-plan template (per Q4 resolution: operator owns cadence; RSI ships template + guidance + self-audit checklist. `rsi/templates/phase-retrospective-base.md` includes the self-audit checklist. RSI makes discipline cheap to execute; operator executes. RSI does not track dispatch count or enforce review cadence.)

**Estimated effort:** 2-3 sessions as one arc, or split 4a / 4b / 4c into two or three sessions depending on natural commit-size breaks.
**Blocks on:** nothing.

### Session 5 — `rsi audit` command (standalone per Q2)

- §4.5 proactive infrastructure-gap check at `rsi init` or on-demand.

**Estimated effort:** 1 session.
**Blocks on:** nothing.

### Session 6 — Memory-driven consistency consult — CLOSED, NOT NEEDED (2026-04-27)

**Status:** explicitly closed as not-needed.

**Resolution:** Q3's template-prompted + audit-after shape (task-spec-base.md §1 Consistency-check section) is the operating mechanism. Building dedicated tooling without evidence of drift would be speculative work that consumes Anthropic tokens against a hypothetical future need. Per CLAUDE.md ("Don't add features, refactor, or introduce abstractions beyond what the task requires") and the operator's cost model (Anthropic-constrained, workers cheap), defer-without-evidence is the disciplined call.

**Trigger criteria for reopening:** Session 6 fires if a phase retrospective surfaces a §1-related drift pattern that the template prompt failed to catch. Specifically: if the phase-retrospective-base.md §5.4 self-audit ("Drift from established template conventions?") finds that consistency-check sections are routinely empty, copy-pasted, or inaccurate across multiple task specs, that's the trigger to add tooling. Until then, the template prompt + retrospective audit is the operating mechanism.

**No work item carried forward.** This decomposition entry is the durable record that the deferral was a deliberate decision, not an oversight.

### Deferred-but-not-forgotten

- §3.2 Tier 1 reference-binding (Option 2 confirmed; constitution-tier scope; 1 session, TBD)
- §3.1 batch-ceremony Direction A (Direction B is delivered via F3 in Session 2; reopen A only if B proves insufficient)
- WorkerProfile dataclass refactor (formalization after Session 3's incremental thread-through proves the shape)
- §2.8 as a standalone Session 5a-d arc (operator's call — see Q2 below)

### Explicitly out of scope

- §4.6 reviewer-of-reviewer architecture (retrospective v2 defers explicitly; remains out)

---

## 4. Design questions for operator — all resolved

All five open questions answered by operator. Captured below for Session-1+ context; no longer blocking.

### Resolved by retrospective v2

- Q (Tier 1 scope) → Option 2 (constitution-tier only)
- Q (review-memo enforcement) → template-only, no tool gating
- Q (retrospective commit) → committed to [docs/retrospectives/job-platform-phase-1.md](docs/retrospectives/job-platform-phase-1.md)

### Resolved by operator in follow-up

### Q1 — Module C invocation contract

**Context:** [scripts/self_optimization.py:324-326](scripts/self_optimization.py:324) has bare `parser.parse_args()` with no defined arguments. Crashes when upstream orchestrator leaves residual argv.

**Options:**
1. Remove the `parse_args()` call entirely.
2. Call `parser.parse_args([])` explicitly.
3. Refactor Module C to a `run()` function called by `rsi.py loop`; keep argparse only in `__main__` block.

**Recommendation:** Option 3. Cleanest separation, enables Session 2 U2 (programmatic mode) without further refactoring.

**Operator resolution:** Option 1 with empirical posture — delete `parse_args()` as vestigial, run RSI test suite, observe breakage. Empirical result drives next step: no breakage → option a was correct; breakage reveals whether option b (defensive default) or option c (intentional-broken-contract) applies. Resolve in minutes during Session 2; don't reason it out abstractly.

### Q2 — §2.8 integration into Session 4 vs standalone Session 5a-d

**Context:** §2.8 proposes Session 5a-d as a multi-session arc for automated self-review. My decomposition (§2 above) argues §2.8's sub-capabilities naturally live in `rsi/templates/` and `rsi/docs/`, bundling cleanly with Session 4. Net framework work ~3 sessions, not 4+.

**Options:**
1. **Bundle into Session 4.** Session 4 scope expands to include §2.4 + §2.5 + §2.6 + §2.8 template work; runs as 2-3 sessions internally.
2. **Keep §2.8 as standalone Session 5a-d.** Session 4 ships §2.4 + §2.5 + §2.6 only; §2.8 gets its own dedicated arc. Treats automated self-review as a first-class architectural direction warranting its own roadmap slot.
3. **Hybrid.** Sub-capabilities 1, 4, 5 (self-audit questions, pre-commit checks, escalation criteria) bundle into Session 4 memo template. Sub-capability 2 (trap taxonomy) ships in Session 4 as a task-spec addendum. Sub-capability 3 (memory-driven consistency) and sub-capability 6 (calibration plan template) get standalone sessions because they involve new discipline patterns, not just template text.

**Recommendation:** Option 3 (hybrid). Ships the cheap valuable items fast (Session 4 memo template + trap taxonomy); reserves dedicated attention for memory-driven consistency and calibration-plan templates where the design work is real. Avoids both the "Session 5a-d as monolith" framing (inflates perceived cost) and "stuff it all into Session 4" (glosses over real design in sub-caps 3 and 6).

**Operator resolution:** Full collapse into Session 4 (goes further than Option 3 hybrid). Decomposition pushback accepted entirely. `rsi audit` moves to standalone Session 5. Memory-driven consistency (sub-cap 3) folds into Session 4 if it fits the templates theme; otherwise becomes Session 6 — decide during Session 4 execution based on observed scope. Final sequence:

- Session 1: Bug batch
- Session 2: Calibration
- Session 3: Worker-genericization
- Session 4: Framework asset corpus (all templates + self-review protocol + trap taxonomy + testing conventions + escalation + calibration-plan template). Split 4a/4b possible at task-spec-library boundary.
- Session 5: `rsi audit` command
- Session 6 (tentative): Memory-driven consistency consult if not folded into Session 4

### Q3 — Memory-driven consistency enforcement strength

**Context:** §2.8 sub-capability 3 requires task-spec authors to consult prior memos, calibration data, and commitments before new task spec. Three enforcement levels are possible:

1. **Template-prompted only** (task-spec template has a `## Consistency note` section; no tool check).
2. **Audit-after-the-fact** (ceremony flags missing consistency-notes as warnings).
3. **Hard-enforced** (delegate refuses to dispatch without consistency-note).

**Recommendation:** Option 2 (template-prompted + audit-after). Hard enforcement is premature given uneven per-task value. Pure template-prompting (Option 1) is probably what §2.4 template ships with initially; audit-layer can be added later if drift re-emerges.

**Operator resolution:** Option 2 confirmed. Task-spec template ships with a `## Consistency check` section requiring explicit statements about prior memos consulted, template decisions acknowledged, calibration data considered. Blank or "not applicable" accepted — the prompt forces consideration, not a specific answer. Retrospectives audit the sections for drift patterns.

### Q4 — Calibration plan: framework capability or operator discipline?

**Context:** §2.8 sub-capability 6 proposes "scheduled external-reviewer sessions every N dispatches." The retrospective positions this as a framework capability. I argue it's operator discipline with a framework-provided template.

**Options:**
1. **Framework capability.** RSI ships tooling that tracks dispatch count, prompts for external review at threshold, enforces the review before subsequent dispatches.
2. **Operator discipline with framework template.** RSI ships a retrospective template (`rsi/templates/phase-retrospective-base.md`); operator chooses when and how often to invoke external review.
3. **Hybrid.** RSI tracks dispatch count and surfaces "N dispatches since last external review" in dashboard output; does not enforce or prompt.

**Recommendation:** Option 2. External review is an operations discipline that depends on availability of an external reviewer — not every RSI-using project has Opus-in-chat on tap. Ship the template and discipline guidance; let projects choose cadence. Option 3 is defensible as a low-friction awareness mechanism; it's not wrong but it's not strictly necessary for the discipline to work.

**Operator resolution:** Option 2 confirmed with explicit boundary statement: "RSI makes discipline cheap to execute; operator executes." RSI ships template + guidance + self-audit checklist; operator owns cadence. Boundary chosen because RSI can't know project phase or operator bandwidth.

### Q5 — Session 4 track selection (given operator's Q2 full-collapse resolution)

**Context:** If Q2 is Option 3 hybrid, Session 4's scope expands. Three tracks within Session 4; operator picks ordering:

**Options:**
1. **Templates first (§2.4 memo + §2.5 task-spec + §2.8 self-audit + trap taxonomy).** Highest compound value; 1-2 sessions.
2. **`rsi audit` first (§4.5).** Narrow scope; 1 session; immediately useful at project init.
3. **Testing conventions first (§2.6).** Pure doc port; <1 session.

**Recommendation:** Track 1 (templates) first because it feeds the discipline pattern that downstream sub-capabilities rely on. Track 2 (`rsi audit`) second as a fast, independent win. Track 3 (testing conventions) bundleable with Track 1 since both are doc-shaped.

**Operator resolution:** Memo templates first (review-memo + self-review protocol), task-spec library center, supporting docs (conventions + escalation + calibration-plan) last. Natural narrative: build memo discipline, then the supporting corpus. Split at task-spec-library boundary (4a / 4b) if session scope grows. This supersedes the prior Track 1/2/3 numbering — see revised Session 4 structure in §3.

---

## 5. First-session scope (unchanged from v1)

**Target: Session 1 — Bug batch.**

Concrete deliverable: branch `rsi/phase-1-bugfix-batch` with commits for:

1. U5 + §2.7 amendment-log structure + regression tests ([scripts/classify_file.py](scripts/classify_file.py) + new amendment-log convention)
2. U1 + three regression tests ([scripts/self_verify.py](scripts/self_verify.py))
3. F6 + 9b + sidecar-write-order test + delimiter-parser tests ([scripts/delegate.py](scripts/delegate.py))
4. U6/F5 + F9 schema addition + threading + tests ([.rsi/architecture.yaml](.rsi/architecture.yaml) + [scripts/delegate.py](scripts/delegate.py))

Each commit isolated. Ceremony level `standard` (per-commit A→B→C). `scripts/*.py` is guarded, so each goes through `delegate.py` to a worker with review.

**Not in scope for Session 1:**
- No U3, F3, U4, U2 (Session 2).
- No worker-genericization beyond the two fields in U6/F5/F9 (Session 3).
- No templates, audit, or §2.8 work (Session 4).
- No Tier 1 reference-binding (deferred, Option 2 confirmed).

**Pre-session 1 checklist — complete:**
- Decomposition reviewed.
- Q1-Q5 all resolved (see §4).
- Retrospective v2 committed.
- Session 1 unblocked. Awaiting operator signal to start.

---

## 6. What this decomposition is not

- **Not a design proposal.** Per-session design lands in that session.
- **Not a commitment to retrospective v2's framing on §2.8.** I've argued for decomposing §2.8 into smaller pieces that ship incrementally. Operator may prefer the monolithic Session 5a-d framing for roadmap-visibility reasons.
- **Not a roadmap.** Five+ sessions sketched here, but RSI has context I don't (cost telemetry plans per [COST_TELEMETRY_PLAN.md](COST_TELEMETRY_PLAN.md), stack evolution per [STACK_EVOLUTION.md](STACK_EVOLUTION.md), proof-wrong guide maturity, etc.). If other initiatives need to interleave, the sequence adjusts.

---

## 7. Dialogue state with retrospective

The retrospective and this decomposition are in active dialogue. State of the dialogue:

**Agreements reached:**
- §2.4 tool-gating → template-only (decomp v1 pushback accepted in retrospective v2)
- §2.7 priority elevation and bundle with U5 (decomp v1 pushback accepted in retrospective v2)
- §3.2 Option 3 → Option 2 (decomp v1 pushback accepted in retrospective v2)
- §4.6 deferred entirely (decomp v1 pushback accepted in retrospective v2)

**Open dialogue items:**
- §2.8 decomposition (retrospective v2 proposes Session 5a-d monolithic; decomp v2 counter-proposes hybrid integration with Session 4 for cheaper sub-capabilities). Resolution: Q2 above.
- Calibration plan scope (retrospective v2 frames as framework capability; decomp v2 counter-proposes as operator discipline with framework-provided template). Resolution: Q4 above.
- Memory-driven consistency enforcement strength (retrospective v2 says "must read"; decomp v2 asks what "must" means in tooling terms). Resolution: Q3 above.

**Empirical questions neither side can resolve in advance:**
- Whether framework-supported self-audit captures the 10% of review work that required external position in Phase 1 (retrospective v2 §2.8 honest caveat).
- Whether N=3 dispatches between external-review sessions is the right cadence (retrospective v2 §2.8 calibration plan).
- Whether Direction B (ceremony proportionality) is sufficient without Direction A (batch ceremony) (retrospective v2 §3.1).

These three are answerable only by running the architecture and observing. Don't resolve them upfront; resolve them via the calibration plan (scheduled external-reviewer sessions) once §2.8 is partially deployed.

---

All design questions resolved. Session 1 can start on operator signal. Sessions 2-6 follow the sequence in §3; Session 2 resolves Module C empirically during its first minutes rather than pre-session; Session 6 is tentative pending Session 4 execution.
