# RSI Framework Retrospective — Field Evidence from Job-Platform Phase 1

**Source project:** Agentic Job Application Platform, Phase 1 algorithm implementation
**Period:** Multi-session arc covering scaffold through build_match_score landing
**Author context:** Retrospective written from the perspective of RSI as a dependency, not RSI as the primary project
**Purpose:** Hand off field evidence to the RSI project's next development session so framework improvements are informed by real-world usage rather than abstract estimates

---

## 0. Framing

This document captures what the RSI framework should do better, learned from using it as the discipline layer for an Opus↔Kimi-via-Claude-Code code-generation workflow across five algorithm implementations. The usage pattern was:

- **Opus** (reviewer layer) — authors task specs, produces review memos, oversights the reviewer
- **Claude Code** (producer layer, under RSI) — dispatches tasks to Kimi via `scripts/delegate.py`, reviews Kimi's output, applies edits, commits through RSI ceremony
- **Kimi K2.6** (implementation worker) — generates code against task specs, returns via delegate adapter

RSI's job was to enforce discipline around commits, capture learning signals (Modules A/B/C), preflight-check work, and provide the infrastructure for multi-worker delegation.

Over five algorithm implementations (compute_deal_breakers, compute_hard_match, compute_skill_sim, compute_trajectory, compute_prefs, build_match_score), plus supporting scaffold work, plus multiple framework patches, a pattern of recurring friction emerged. This document organizes that friction into actionable improvements.

The framing is **field evidence, not abstract critique.** Every finding below has specific commit SHAs, token counts, time-to-resolution, or other concrete evidence from the job-platform project.

---

## 1. Bugs that need fixing

These are clear defects in RSI as currently shipped. They have reproducible symptoms and known fixes. Most already have local patches on the job-platform fork that should be ported.

### 1.1 U5 — `classify_file.py` YAML parser doesn't strip inline comments

**Symptom:** `SPEC_AMENDMENTS.md` and `pyproject.toml` are listed under `constitution` tier in `architecture.yaml`, but `classify` returns `open` and `guarded` respectively.

**Root cause:** `scripts/classify_file.py` YAML-subset parser preserves inline comments as part of the fnmatch pattern. Entry like `"SPEC_AMENDMENTS.md" # amendments to spec` becomes pattern `SPEC_AMENDMENTS.md" # amendments to spec` (with embedded whitespace and quote) that never matches anything.

**Severity:** Highest of the bug set. **Silent misclassification of constitution-tier files to lower tiers.** Files the operator most wants protected receive less ceremony and less protection than intended. No loud failure surfaces the bug — every commit that should have triggered constitution ceremony passes through with guarded ceremony instead.

**Evidence:** Reproduced during Phase 1 on both `SPEC_AMENDMENTS.md` (expected constitution, returns open) and `pyproject.toml` (expected constitution, returns guarded). Discovered while running ceremony check on the S commit (SPEC_AMENDMENTS entry add).

**Fix:** Three-line patch — strip inline comments from each pattern line before fnmatch compilation. Specifically: `pattern = line.split('#', 1)[0].strip().strip('"').strip("'")`.

**Priority for RSI session:** Ship first. Trivial fix, highest severity, no design questions.

**Tests to add:** Regression test — `architecture.yaml` with inline comments on path patterns should correctly classify files according to the pre-comment path, not the raw line.

---

### 1.2 U3 — Module C `argv.parse_args()` crash at startup

**Symptom:** Module C (`scripts/self_feedback.py` or similar — prioritization/next-round/task-tracker/pattern-library module) calls `argparse.ArgumentParser().parse_args()` at the very start of `main()`, apparently redundantly. The call crashes under the pipeline invocation context because argv has already been consumed by the upstream orchestrator.

**Root cause:** Unknown without maintainer input. Either (a) vestigial argparse call that should be removed, (b) missing `[sys.argv[1:]]` arg on parse_args that should have been defaulted, or (c) intentional argv reparse that assumes a context we're not providing.

**Severity:** Elevated. Every cycle loses four learning signals:
- Prioritization (which findings matter most for next round)
- Next-round suggestions (what to do differently)
- Task tracker update (tracking which tasks succeeded)
- Pattern library growth (accumulating reusable patterns)

The "lossy-to-raw" framing we adopted during Phase 1 — memory content is captured by Module A, but Module C's aggregation never runs, so the dashboard is permanently stale — is a workaround, not a fix.

**Evidence:** Reproduced on every single commit during Phase 1 (14+ commits). Dashboard counters remain at `Rounds: 1, Tasks: 0` despite `.memory/rounds/round-001.md` growing from 790 bytes to 13,068 bytes across three-algorithm equivalent of real work. Memory content is populated by Module A; Module C crash blocks the aggregator.

**Fix:** Needs framework-maintainer decision on Module C's intended invocation contract. Possibilities:
- Remove the argv.parse_args() call entirely if vestigial
- Pass `[]` or `sys.argv[1:]` explicitly depending on context
- Restructure Module C to be fully callable from pipeline context without argv dependencies

**Priority for RSI session:** Second — this is the most impactful framework bug in terms of cumulative capability loss. Every RSI-using project loses learning signals every commit until this is fixed.

**Tests to add:** End-to-end Module C invocation from pipeline context, without manipulating sys.argv. Verify counters update correctly in the dashboard.

---

### 1.3 U1 — `self_verify` whole-file placeholder scan

**Symptom:** `scripts/self_verify.py` scans the entire file for placeholder patterns (TODO, FIXME, NotImplementedError, etc.), not just the diff vs HEAD. This means any pre-existing TODO or stub in an untouched file blocks commits that didn't introduce the placeholder.

**Root cause:** `self_verify` reads full file contents, applies regex pattern matching to find placeholders, and errors on any match — without filtering by whether the match is in changed lines.

**Severity:** Medium. Creates false-positive blocks that force operators to either work around the check or clean up pre-existing placeholders unrelated to the current commit.

**Evidence:** Hit during Phase 1 scaffold work — commits to files with pre-existing `NotImplementedError` stubs (compute_skill_sim etc. during the compute_hard_match commit) triggered false positives. Local patch F1 landed at `480d317` restricts scanning to diff-vs-HEAD.

**Fix:** F1 patch — implement diff-scoped scanning. Read `git diff HEAD -- <file>` for each changed file, apply placeholder pattern matching only to added lines.

**Priority for RSI session:** Third — port F1 with tests.

**Tests to add:**
- Changed file with new placeholder in added lines — should block commit
- Unchanged file with pre-existing placeholder — should not block commit
- Changed file with pre-existing placeholder on unchanged lines + new code on changed lines — should not block commit

---

### 1.4 U6 — `delegate.py` hardcoded temperature

**Symptom:** `scripts/delegate.py` passes `temperature=0.3` hardcoded to all workers. Kimi K2.6 in thinking mode rejects non-1.0 temperature; Kimi K2.6 in non-thinking mode rejects non-0.6 temperature. Both return HTTP 400.

**Root cause:** Temperature was a MiniMax-oriented default with no per-worker override.

**Severity:** Medium. Blocks all reasoning-model workers from working at all until locally patched.

**Evidence:** First Kimi dispatch attempt failed with 400 error. Local patch F5 landed at `f5d2494` reads temperature from worker config. Configured Kimi worker with `temperature: 0.6` (non-thinking mode, Path 1 config).

**Fix:** F5 patch — add `temperature` to worker config in `architecture.yaml`, read per-worker in `delegate.py`, default to 0.3 if unset (preserves current MiniMax behavior).

**Priority for RSI session:** Fourth — port F5 with tests.

**Tests to add:**
- Worker with explicit `temperature: 0.6` in config → passes 0.6
- Worker without `temperature` in config → passes default 0.3
- Worker with invalid temperature type → config validation error

---

### 1.5 F9 — `delegate.py` hardcoded MAX_OUTPUT_LINES

**Symptom:** `delegate.py:354` hardcodes `MAX_OUTPUT_LINES = 500`. Pre-flight validator rejects task files exceeding this line count. Our task files for Kimi (especially test files) are routinely 600+ lines because Kimi handles larger output budgets cleanly.

**Root cause:** 500-line limit was a MiniMax 16K-token-budget safety heuristic. Kimi K2.6 has 65K max_tokens; the limit doesn't apply.

**Severity:** Medium. Blocks legitimate dispatches to reasoning-model workers.

**Evidence:** Blocked the compute_skill_sim dispatch at pre-flight on a 665-line `tests/unit/test_matching.py`. No tokens burned (task never left delegate). Local patch F9 landed at `f2ed90c` reads `max_output_lines` from worker config.

**Fix:** F9 patch — add `max_output_lines` per-worker config, default to 500 (preserves MiniMax safety floor), set Kimi workers to 2000+.

**Priority for RSI session:** Fifth — port F9 with tests. Can be bundled with F5 (same file, same shape).

**Tests to add:**
- Worker with explicit `max_output_lines: 2000` → accepts task files up to 2000 lines
- Worker without `max_output_lines` → default 500 applies
- Task file exceeding worker's limit → clear error message with worker name and limit

---

### 1.6 F6 — `save_result` strips raw_response, catastrophic data loss on parse failure

**Symptom:** First Kimi dispatch for `compute_hard_match` emitted 43,263 tokens in 19 minutes, then the adapter's JSON parser found no JSON block (Kimi had complied with our `<<<FILE>>>` delimiter instruction instead), returned empty `{"changes": {}}`, and `save_result` stripped the raw response before write. Zero recoverable output from a successful dispatch.

**Root cause:** `delegate.py:837` explicitly strips `raw_response` from the saved result dict, saving only the parsed outcome. When parsing fails, there's nothing to recover.

**Severity:** Highest. A defense-in-depth failure that converts any parser mismatch into total billed-work loss.

**Evidence:** 43k tokens + 19 minutes lost on the first Kimi dispatch. Local patch F6 bundled with 9b persists raw response unconditionally to `.memory/reviews/results/TASK-{ID}.raw.txt` sidecar.

**Fix:** F6 — `save_result` writes raw response to sidecar file unconditionally before any parsing attempt. Sidecar write is the first operation; parsing is second. Parse failures don't affect sidecar.

**Priority for RSI session:** First (tied with U5). Non-negotiable framework improvement. Raw response persistence is a fundamental safety property of any LLM delegation adapter.

**Tests to add:**
- Successful parse → both sidecar and parsed result written
- Failed parse (malformed JSON, missing delimiters) → sidecar written, parsed result empty, no exception propagates out
- Concurrent dispatches → sidecars don't collide
- Very large raw response → sidecar writes complete without truncation

---

### 1.7 9b — `_extract_json` only parses JSON, no delimiter fallback

**Symptom:** Kimi's system prompt (prepended by delegate) appears to override task-level format instructions. Task spec specified `<<<FILE: path>>>...<<<END FILE>>>` delimiter format; Kimi emitted JSON wrapper instead. Parser chokes on mismatch.

**Root cause:** `_extract_json` is JSON-only. Delimiter format is valid code-delivery shape but not recognized.

**Severity:** Medium — with F6 in place, data isn't lost, but parse failures require manual recovery.

**Evidence:** Three of five Phase 1 Kimi dispatches emitted JSON despite delimiter instruction; two emitted delimiters. The adapter needs to handle both. Local patch 9b adds delimiter parsing as fallback when JSON parsing fails.

**Fix:** 9b — after JSON parse attempt returns empty or fails, attempt delimiter parse (`<<<FILE: path>>>...<<<END FILE>>>` blocks). Return unified `{"changes": {path: content}}` dict for downstream compatibility.

**Priority for RSI session:** First (bundled with F6). Together, F6 + 9b convert catastrophic parse failures into recoverable ones.

**Tests to add:**
- JSON-only input → parses via JSON path
- Delimiter-only input → parses via delimiter path
- Malformed JSON → falls through to delimiter parser
- Both formats present → JSON takes precedence
- Neither format present → empty changes dict with raw preserved via F6

---

### 1.8 F3 — Ceremony classifier over-scopes non-code changes

**Symptom:** Ceremony classifier uses line count as the dominant signal, ignoring content type. Pure docs changes trigger thorough or major ceremony when they should trigger minimal.

**Root cause:** `scripts/ceremony.py` classifier scales linearly with line count across all file types.

**Severity:** Low-to-medium. Friction cost on every docs/config commit. Not blocking, but accumulates into real session-overhead inflation.

**Evidence:** Four calibration data points from Phase 1:
- 14 lines docstring change → classified `standard` (expected `minimal`, off by 1 tier)
- 93 lines amendment log entry → classified `standard` (expected `minimal`, off by 1 tier)
- 179 lines new docs file → classified `thorough` (expected `minimal`, off by 2 tiers)
- 255 lines test-fixture rewrite → classified `major` (expected `standard`, off by 1 tier — or `minimal` if treated as pure-data/no-logic)

Pattern confirmed: line count drives classification, content-type is unused.

**Fix:** Add content-type discrimination. Proposed heuristic:
- File extensions `.md`, `.rst`, `.txt`, `.yaml`, `.toml`, `.json` with >50% of line delta in non-code regions → minimal regardless of line count
- `.py`, `.ts`, `.rs` etc. (code) → existing line-count logic applies
- Mixed changes (docs edits to code files, e.g., docstring rewrites) → case-by-case

Alternative approach: let the classifier be more semantic — detect whether changes introduce logic or just text. More robust but more complex.

**Priority for RSI session:** After the bug batch, because this is a calibration improvement not a bug. The line-count-only classifier isn't wrong, it's just miscalibrated.

**Tests to add:**
- 500-line docs change → minimal
- 15-line code change with new logic → standard
- 100-line mixed (code + docs) change → standard
- 1000-line config change (pure YAML) → minimal

---

## 2. Framework gaps that need filling

These aren't bugs in existing code — they're things the framework should do but doesn't.

### 2.1 Worker-genericization

**Pattern:** RSI's defaults (temperature 0.3, MAX_OUTPUT_LINES 500, adapter parsing assumptions, timeout heuristics) are calibrated for one worker class (MiniMax). Real use involves multiple worker classes. Each new worker exposes another hardcoded MiniMax-ism.

**Evidence accumulated:**
- F5 (temperature per worker) — hardcoded 0.3 was MiniMax default
- F9 (max_output_lines per worker) — hardcoded 500 was MiniMax 16K-token safety
- Path 1 config (Kimi K2.6 thinking-disabled + temp 0.6) — needed `extra_body` injection for Moonshot-specific parameters
- Kimi K2.6 reasoning_content field — delegate reads `message.content` only, ignoring `reasoning_content` that Kimi emits in thinking mode; tokens burn invisibly against max_tokens budget (observed during pre-Path-1 smoke test when max_tokens=10 came back with empty content and full reasoning_content)
- OpenAI SDK client timeout — default 10 minutes with 2 retries, far below Kimi's 2h server budget

**Gap:** No first-class concept of "worker capability profile" in RSI. Each worker's characteristics (token budget, temperature constraints, timeout tolerance, reasoning_content handling, output-format preferences) should be first-class configuration, not hardcoded defaults with opt-out mechanisms.

**Proposed framework change:** Define a `WorkerProfile` dataclass or YAML schema in `architecture.yaml` that captures:
- `api_base_url` (Moonshot vs Anthropic vs OpenAI vs MiniMax etc.)
- `model_name`
- `temperature` (with validator — Kimi K2.6 accepts {0.6, 1.0} only)
- `max_tokens` / `max_output_tokens` (server-side)
- `max_output_lines` (client-side pre-flight safety)
- `client_timeout_seconds` (SDK-level, should match server-side budget)
- `thinking_mode` (for Moonshot reasoning models)
- `extra_body` (arbitrary API-specific parameters)
- `reasoning_content_handling` (`ignore` / `capture` / `stream`)
- `output_format_preference` (`json` / `delimiter` / `either`)
- `retry_policy` (max retries, backoff)

Delegate reads worker profile once, applies all constraints uniformly.

**Priority:** Medium. Not blocking current work (our local patches handle each dimension), but the RSI framework can't cleanly support a second worker class without this refactor.

---

### 2.2 Raw-response retention as framework guarantee

**Pattern:** Losing billed work to parser mismatches should not be possible. F6 solved this for our fork but should be a framework-level guarantee, not a per-project fix.

**Proposed framework change:** Delegate adapter contract states: raw response is persisted to disk before any parsing attempts. Parsing is a separate step that reads from disk. This makes parse retries cheap (no API re-call needed) and makes data loss impossible.

Formalize as part of the delegate adapter interface: every worker's raw response goes to a well-known sidecar location (e.g., `.memory/reviews/results/TASK-{ID}.raw.{extension}`), with extension chosen by worker (e.g., `.raw.txt` for text-based workers, `.raw.jsonl` for streaming workers).

**Priority:** First-tier. Ship alongside F6 port.

---

### 2.3 Format-flexibility in adapters

**Pattern:** Workers emit different output formats (JSON wrapping, delimiter blocks, raw code, SSE-streamed chunks). Adapters should be format-agnostic, converging on a unified internal representation (`{"changes": {path: content}, "notes": str, "metadata": dict}`) regardless of input format.

**Proposed framework change:** Define an adapter pipeline with pluggable parsers:
1. Try `worker.output_format_preference` first
2. Fall through to alternative formats
3. Pass raw content to parser chain: JSON → delimiter → structured-code → freeform
4. First parser to return non-empty `changes` wins
5. Log which parser succeeded for calibration

Per-worker config determines parser priority. F9 and F6 together are the prototype; this generalizes it.

**Priority:** Bundle with F6 + 9b port.

---

### 2.4 Review-memo template (revised — template-only, not tool-gated)

> **Note on revision:** This section originally proposed tool-gating — `rsi apply` refusing to proceed without a review memo. The RSI decomposition session pushed back that tool-gating would turn RSI into a policy engine it isn't designed to be, and that template-only support is sufficient. Accepting the correction; revised below.

**Pattern:** The original RSI design assumes Claude Code plays a reviewer role between Kimi (producer) and operator. In practice, without explicit protocol enforcement, Claude Code defaulted to "paste raw Kimi response back to operator and wait" — effectively demoting itself to transport layer.

**Evidence:** During Phase 1 compute_hard_match cycle, Claude Code pasted Kimi's 25k-token response to Opus (operator's reviewer) without producing a review memo first. Operator noticed the drift and explicitly reinstated the review-memo protocol via a saved `.memory/feedback_kimi_delegate_review.md` file. After that fix, all subsequent dispatches (compute_skill_sim through build_match_score) produced review memos correctly.

**Gap:** The framework provides no template or convention for review memos. Every project using RSI for LLM delegation invents its own memo format, and drift back to "paste raw and wait" is easy without an established pattern to fall back to.

**Proposed framework change:** Ship a review-memo template as a first-class framework asset at `rsi/templates/review-memo-base.md`. Template prescribes:

- Severity-tiered findings format (Critical / Medium / Low / Compliments)
- Decision field with fixed vocabulary: `apply-with-edits` / `re-dispatch` / `surface-to-operator`
- Proposed-edits section for apply-with-edits decisions
- Revised-task-instructions section for re-dispatch decisions
- Standard artifact path: `.memory/reviews/TASK-{ID}-review.md`

Ceremony output surfaces memo presence/absence — if a delegation-capture round doesn't have a corresponding review memo, the ceremony flags it as missing-artifact (warning level, not blocking). This catches drift through visibility rather than enforcement.

**Priority:** Medium. Part of the template library (§2.5).

---

### 2.5 Task-spec template library

**Pattern:** Phase 1's task specs evolved across five algorithms. Each iteration earned specific improvements:
- Update A — Pydantic runtime validator prompt in §10 Context (motivated by 48-char summary bug)
- Update B — A6-standard-edges (a)-(d) in §7 (motivated by L1 empty-skills guard + L2 min_years=0)
- Update C — Accept-with-edits framing in §8 (motivated by unclear review-outcome expectations)
- Update D — Enumerate @model_validator methods in §10 (motivated by second `validate_expert_needs_evidence` bug)
- Update E — Monkeypatch source-module convention in `docs/testing-conventions.md` (motivated by compute_skill_sim C2)
- Update F — Explanation template rendering decisions as A6-standard-edges (e) (motivated by compute_trajectory M1 align_desc)

By the time build_match_score's task spec was written, the template was substantially better than compute_hard_match's.

**Gap:** Each RSI-using project rediscovers these template improvements from scratch. Field evidence from the job-platform should become first-class RSI infrastructure.

**Proposed framework change:** Ship a `rsi/templates/` directory with:
- `task-spec-base.md` — canonical template with §0-§10 structure, all six Updates A-F baked in
- `review-memo-base.md` — canonical template with severity tiering
- `ambiguity-prompts.md` — library of A6-standard-edges categories and hint-lists per domain

Projects start from these templates, extend them per-project, and optionally contribute back field evidence as new templates or new ambiguity categories.

**Priority:** Medium. This is framework-evolution work that compounds across future projects.

---

### 2.6 Testing conventions corpus

**Pattern:** `docs/testing-conventions.md` in the job-platform accumulated three sections during Phase 1:
1. **Monkeypatching functions with local imports** (from compute_skill_sim review — local imports resolve in source module, not consumer module, so `monkeypatch.setattr` must target the source)
2. **Pytest fixture discovery** (from compute_trajectory review — fixtures in sibling test modules aren't auto-discoverable; must live in `conftest.py` or same module)
3. **Latent defects behind xfail — seen-twice pattern** (from build_match_score review, citing I14 Evidence validator + KNOWN_VECTORS compound-string gap — xfail masks fixture-setup errors and dependency bugs)

Each was earned from a specific review cycle. Each is a generalizable testing-discipline insight.

**Gap:** Every RSI-using project rediscovers these from scratch. The testing-conventions file is generalizable IP.

**Proposed framework change:** Ship `rsi/docs/testing-conventions.md` as a canonical base. Projects extend with project-specific conventions, and RSI absorbs project-extensions back into the canonical base over time (when they're evidence-backed and generally applicable).

**Priority:** Low-to-medium. Documentation work, but high long-term value per unit effort.

---

### 2.7 Upstream spec-amendment tracking

**Pattern:** Phase 1 accumulated four spec-amendment entries (I11-I14) tracking divergences between the spec and the implementation:
- I11 — `ApplicationStatus.ghosted` enum completeness
- I12 — `JobProfile.location` field addition
- I13 — `DimensionScore.raw_features` value type widening
- I14 — Evidence validator field-order bug (spec defect, fixed via @model_validator rewrite)

Each entry captures: spec location, issue description, scaffold resolution (with commit SHA), proposed upstream fix, blocking phase.

**Gap:** `SPEC_AMENDMENTS.md` is a project-local convention. RSI doesn't provide a structured way to track "we deviated from the design spec here, and here's why." Future projects invent their own conventions or (worse) don't track divergences at all.

**Proposed framework change:** RSI could provide a structured amendment-log format with:
- Machine-readable schema (YAML or JSON front-matter per entry)
- Integration with classify_file (amendments file is constitution-tier automatically)
- Ceremony hook that surfaces pending amendments on spec-file commits ("you touched the spec file, are any pending amendments now resolved?")
- Visible in dashboard alongside other health indicators

**Priority:** Elevated per RSI decomposition session pushback — bundle with U5 in Session 1 bug batch. Both involve `classify_file.py` semantics (U5 fixes the YAML parser; amendment-tracking adds structure to what classify_file treats as constitution-tier). Single coherent commit rather than two touches on the same file.

---

### 2.8 Automated self-review framework capabilities

> **Note on scope:** This section was added in a retrospective revision after the operator clarified that the goal isn't just to fix RSI's current friction — it's to evolve RSI toward supporting autonomous self-review loops where an external reviewer (Opus in chat) isn't structurally required for routine work. This is different from §2.4 (review-memo template) because that section addresses "does Claude Code write review memos" while this section addresses "can Claude Code's review memos be quality-assured without an external reviewer."

**Current architecture.** Phase 1 ran with three active review layers:
- **Operator** as decision-maker and strategic reviewer
- **Opus in chat** as reviewer-of-reviewer — checking Claude Code's review memos for tier accuracy, decision soundness, missed findings, calibration drift
- **Claude Code** as producer-reviewer — authoring task specs, dispatching Kimi, reviewing output, producing review memos, applying edits

The Opus-in-chat layer caught real things: review-loop architecture drift (operator-surfaced first but reinforced by chat), template-update motivation across five algorithms, specific quality checks on specific review memos, calibration-signal naming (A5 preservation, validate_composite_formula fidelity).

**Target architecture.** Two active layers:
- **Operator** as decision-maker and escalation endpoint
- **Claude Code** running an autonomous producer-reviewer loop with framework-supported self-review discipline

The Opus-in-chat layer either disappears entirely or becomes invocable on-demand for strategic work (retrospectives, framework design, calibration reviews at project-phase boundaries) rather than routine per-dispatch review.

**What parts of Opus's current review role are automatable.**

Much of routine review memo oversight is pattern-matchable and doesn't require external position:

*Severity-tier audits.* Most severity mistakes are detectable by checking against explicit criteria. Is a "Critical" finding actually going to fail at runtime, or is it an edge case that passes today but is fragile? Is a "Medium" finding actually something that could slip past review and cause problems, or is it really a Low? Self-audit prompts enforce explicit reasoning rather than gut-feel tiering.

*Decision soundness.* `apply-with-edits` / `re-dispatch` / `surface-to-operator` decisions have recognizable patterns. If findings are all specific code changes → apply-with-edits. If findings are design-level (wrong signature, wrong algorithm approach, missing abstraction) → re-dispatch. If findings introduce novel ambiguity requiring operator judgment → surface. A decision matrix in the memo template makes this mechanical.

*Completeness checks.* Did the memo address all standard finding categories? Pydantic validators, test-side bugs, ambiguity surfacing, template rendering decisions, style consistency, spec fidelity — these are checkable as a list. Self-audit prompts require explicit presence of each category even if the finding is "no issue in this category."

*Proposed-edit specificity.* Edits framed as "improve X" are insufficient; edits framed as "change line Y from A to B because C" are actionable. Self-audit prompt forces the actionable framing.

*Calibration signal naming.* When a task spec includes calibration traps (like the A5 partial-credit preservation or the validate_composite_formula constraint), the review memo should explicitly report on whether the traps fired correctly. Self-audit prompt surfaces this automatically rather than requiring external reviewer to notice.

**What parts are harder to automate.**

Specific things the external-reviewer position caught during Phase 1 that don't automate cleanly:

*Cross-session drift detection.* "You said you'd do X last session; this session you did Y instead — which is right?" requires comparing current state to prior commitments. Memory-backed, but requires discipline to actually consult rather than ignore. Automatable with enforcement, which has its own costs.

*Scope-expansion resistance.* "You're about to bundle this unrelated fix into this commit; don't." Easier when the reviewer isn't emotionally invested in getting the session to forward-progress. Self-review can do this, but has a structural bias toward expanding scope ("while I'm here, I might as well fix this too...") that's hard to counter without external friction.

*Self-contradiction acknowledgment.* Calling out when an earlier recommendation was wrong. (Phase 1 example: I admitted the delimiter format assertion was my error, not Kimi's, after the 43k-token loss.) Requires willingness to contradict prior self, which is harder for single-agent loops because the prior self and current self share context. External position provides the gap.

*Systematic blind-spot detection.* Self-review can't catch its own systematic blind spots by definition. If Claude Code systematically misses a category of finding (xfail-masking-latent-defects being the canonical Phase 1 example), only an external reviewer with different context catches it. This is the structural limit of automation.

**Framework capabilities required for the target architecture.**

*Self-review protocol as first-class memo content.* Beyond the review-memo template (§2.4), the memo must include a self-audit section. Required questions:

1. Reconsidering each finding: is this severity tier correct, or am I inflating/deflating for momentum reasons?
2. Are there categories of finding I typically miss (test-side bugs, runtime validator violations, explanation-template decisions, xfail-masking latent defects)? Have I checked for each?
3. Does my apply/re-dispatch decision follow from the findings, or am I biasing toward apply because re-dispatch is expensive?
4. What's the steelman for the opposite decision? If I can't construct a steelman, the decision isn't considered.
5. If an external reviewer (Opus in chat) were reading this memo, what would they push back on?
6. Are calibration signals from this dispatch worth naming explicitly? What did the producer do well? What did the producer do that matches or diverges from prior patterns?

The questions are in the template; answering them is in the memo; refusing to answer is the memo being incomplete.

*Calibration-trap libraries.* In an automated loop, Claude Code authoring the task spec can't plant calibration traps for itself — knowing where the trap is eliminates its function. But Claude Code can consume pre-built trap libraries the framework provides for common domains:

- **Type coercion traps.** Pseudocode that mixes Decimal/float/int and is easy to normalize in a way that drifts from spec semantics.
- **Validator constraint traps.** Model validators with unusual constraints (hardcoded expected values, field-order dependencies, cross-field rules) that are easy to miss when reading Field declarations only.
- **Enum ordering traps.** Dict or enum insertion-order dependencies where mechanical reproduction preserves spec behavior and "cleanup" silently changes it.
- **Boundary traps.** Floating-point tolerances, Decimal quantization order, inclusive-vs-exclusive thresholds.
- **Spec-bug traps.** Known pseudocode defects that faithful reproduction would reproduce (like compute_skill_sim's leading `, ` when job_reqs is empty, or compute_prefs' "1 preference dimensions match" pluralization).

Framework ships the library; task-spec authoring selects relevant traps per task; producer's response reveals fidelity. Self-review checks whether traps fired correctly.

*Memory-driven consistency enforcement.* RSI's Module A captures memory per cycle. What's missing is active consultation. Framework requirement: before task-spec authoring, Claude Code must read:

- Prior review memos for similar tasks in this project
- Prior calibration data (which traps the producer engaged with, which were silently missed)
- Prior template decisions (what updates were applied, which decisions were made about signature conventions, test organization, etc.)
- Cross-session commitments that affect the current work

The output of this reading is an explicit consistency-note in the task spec: "this task aligns with prior commitments on X, Y; diverges on Z because [reason]." Refusing to produce the consistency-note is task-spec incomplete.

*Self-audit prompts at decision points.* Before committing a change, the commit author runs through explicit checks:

- Am I bundling unrelated work? (If yes, split the commit.)
- Am I committing something the memo didn't explicitly approve? (If yes, add to memo first or drop from commit.)
- Am I rushing past a Medium finding because it felt like it could be handled later? (If yes, justify why later is acceptable and commit the deferral to memory.)
- Is there a reason external oversight (if invoked) would block this commit? Stating the reason is sufficient; if no reason can be stated, proceed.

Answers committed to memory alongside the commit. Reviewable by operator or external reviewer if later invoked.

*Explicit human-escalation criteria.* The framework defines when Claude Code must pause for operator input rather than self-deciding. Proposed criteria:

- Severity-Critical findings that aren't addressable as specific code changes (re-dispatch or scope change needed)
- Any decision that would change the task-spec template, review protocol, or self-review protocol itself (meta-change to the framework requires operator approval)
- Re-dispatches (not applies) — Kimi-token cost is real and the operator funds it
- Novel failure patterns not matching prior calibration data (something new, might be pattern vs one-off)
- Disagreements between self-review and a re-read of prior session's conclusions (possible cross-session drift)
- Calibration traps that fire in unexpected ways — whether the producer bypassed a trap unexpectedly, or engaged with a trap that was actually a real constraint to honor

With explicit criteria, self-review runs autonomously except at these checkpoints. Operator-in-loop is invoked only when criteria fire.

**Calibration plan — how do we know self-review is working?**

The structural problem: self-review can't catch its own systematic blind spots. How does the project know whether the automation is producing quality comparable to the human-reviewer-augmented pattern Phase 1 ran with?

Proposed calibration approach:

*Scheduled external-reviewer sessions.* Every N dispatches (N calibrated based on confidence in self-review quality; start N=3, extend as trust grows), an operator-triggered external-review session reads the last N review memos and their outcomes. External reviewer (could be operator directly, or Opus-in-chat if invoked for this purpose) looks for:

- Findings self-review missed that external-review catches
- Severity-tier inflation or deflation patterns
- Decision patterns that diverge from what external review would have chosen
- Drift from established template or protocol conventions

Findings from external-review sessions feed back into self-review protocol improvements — if a class of finding is missed repeatedly, add a self-audit prompt for that class.

*Retrospective self-audit gates.* At project-phase boundaries (like Phase 1 → Phase 2), a mandatory retrospective that examines self-review quality over the phase. Operator-driven, can use external reviewer if available. This is the moment to catch systematic blind spots and update the framework.

*Calibration-trap outcomes as leading indicator.* If calibration traps from the framework's library fire correctly at expected rates, self-review is engaging with discipline. If trap-firing rate drops, something in the self-review protocol has degraded. Traps are the framework's built-in quality signal.

*Producer-side consistency.* If Kimi's output quality stays steady over time (finding distribution, implementation correctness rate, ambiguity surfacing quality), the upstream self-review isn't regressing. Producer quality is downstream of task-spec quality which is downstream of self-review.

**Priority for RSI session.** High — this is architectural direction, not incremental fixes. But substantial work: the self-review protocol, calibration-trap library, memory-driven consistency, human-escalation criteria, and calibration plan are each their own design problem. Not a single session's work; probably multiple sessions across Tier 3 of the prioritization roadmap.

**Sequencing note.** The self-review protocol (first sub-capability) is most valuable first because it structures the quality-assurance that the rest of the capabilities feed into. Calibration-trap library second because it provides the test-bed for whether self-review is working. Memory-driven consistency third. Human-escalation criteria fourth. Calibration plan throughout — the infrastructure is in place from Tier 1, but the scheduled-external-reviewer cadence starts whenever operator is ready to test it.

**What the job-platform project gets from this.** If the automation succeeds, the job-platform's future algorithm implementation work (Phase 2, Phase 3, ...) runs without Opus-in-chat as a structural dependency. Operator interacts with Claude Code directly; Claude Code runs the full producer-reviewer loop against Kimi with framework-supported discipline; operator funds the escalations and makes strategic decisions. Opus-in-chat becomes invocable for retrospectives, framework design, and phase-boundary reviews rather than per-dispatch.

**What the RSI ecosystem gets from this.** Every project using RSI for LLM delegation inherits the self-review infrastructure. The pattern that took Phase 1 to discover (reviewer-of-reviewer catches specific things, most review work is pattern-matchable) becomes framework-level default rather than per-project rediscovery.

**Honest caveat.** Whether this target architecture is achievable depends on whether Claude Code with framework support can actually produce review quality comparable to external human/AI review. The proposal assumes yes based on Phase 1 evidence that most review work was pattern-matchable. But the 10% that required external position was real, and whether framework-supported self-audit captures that 10% is an empirical question that gets answered by running the architecture and seeing whether systematic blind spots emerge.

The calibration plan (scheduled external-reviewer sessions) exists precisely to answer this question empirically rather than hope.

---

## 3. Calibration problems

These aren't bugs and aren't gaps — they're places where RSI's defaults are miscalibrated for the real usage pattern.

### 3.1 Per-commit ceremony overhead vs single-operator project reality

**Pattern:** RSI was designed around per-commit learning signal (Module A/B/C after each commit produces round-by-round calibration data). For single-operator projects with related small commits (three commits in sequence for related scaffold work), per-commit ceremony costs pile up:
- 60 minutes of pipeline friction across 3 commits in one session during Phase 1 scaffold close-out
- 2 retry cycles on pre-commit blockers (ruff ANN401, mypy test-file exclusion)
- Module B's 12-input stdin interaction per commit via piped printf

Per-commit ceremony has real value — it catches issues (lint, type, discipline gaps) and captures memory. But the overhead-to-value ratio is different for single-operator projects vs multi-contributor projects.

**Gap:** No first-class concept of "related commit sequence" or "batch-ceremony mode" in RSI. Every commit pays full ceremony cost regardless of its relationship to the surrounding sequence.

**Two competing design directions:**

*Direction A — Batch-ceremony:* Allow operators to declare "these three commits are related; run ceremony once after the third lands." Memory artifacts reference the batch, not individual commits. Module B reflection happens once over the batch. Pro: massive friction reduction for related-commit sequences. Con: loses per-commit learning granularity, may violate RSI's design philosophy.

*Direction B — Ceremony proportionality:* Keep per-commit ceremony but make it scale more cleanly with change size. F3 (content-type classifier) is one instance of this. More broadly: minimal commits (docs, config) get ultra-minimal ceremony (preflight only, no Module B); larger commits get full ceremony. Pro: preserves design philosophy, targeted improvement. Con: still pays ceremony cost on every commit, even when commits are atomic-but-small.

**Recommendation for RSI session:** This is a genuine design question, not a bug. Consider Direction B as the near-term path (F3 content-type heuristic + minimal-ceremony mode for low-risk change classes) and defer Direction A unless Direction B proves insufficient.

**Priority:** Design-work priority. Worth an explicit design document in the RSI project before implementation.

---

### 3.2 Tier 1 reference-binding spec — reconsider given Phase 1 evidence

**Context:** During pre-Phase-1 work, we authored `rsi_tier1_reference_binding_spec_v0_1.md` — a ~550-line spec extending read-before-edit to require reference reads for constitution/guarded tier edits. The motivating failure mode was "paraphrase-from-memory defects" surfaced during the A0/A0b scaffold audit (eight MatchScore model divergences because the scaffold paraphrased spec §2.5.3 from memory).

**Phase 1 evidence that reshapes the calibration:**

Across five algorithm implementations with the Opus↔Kimi-via-Claude-Code pattern:
- Implementation bodies: correct 5/5 (zero algorithm defects)
- Findings clustered on: tests, discipline gaps, template-rendering decisions
- Calibration traps: both fired correctly (0.3 asymmetric partial credit preserved, validate_composite_formula constraint honored)
- Reviewer catches: tests-side bugs, fixture-construction issues, edge-case guards, explanation-template decisions
- Spec-violation defects: essentially zero

The paraphrase-from-memory failure mode that motivated Tier 1 was *not* the primary problem during Phase 1 implementation. When the task spec was precise and the ambiguity-surfacing prompts covered the edge cases, Kimi produced spec-faithful code.

**Reconsidered position:**

Tier 1's motivation (prevent paraphrase-from-memory defects on spec-bound edits) may have been over-weighted based on a single high-stakes failure (A0b audit) rather than a steady-state pattern. The actual steady-state failures are in test-side discipline and template-rendering gaps — which Tier 1 doesn't address.

**Options for RSI session:**

- **Option 1: Build Tier 1 as specified.** The spec is written; implementation is straightforward; reference-binding discipline is genuinely valuable for spec-heavy edits even if not the top-priority failure mode.
- **Option 2: Rescope Tier 1.** Narrow the scope to apply only to constitution-tier edits (not guarded-tier), which was where the paraphrase failure originated. Reduces implementation effort; matches actual field-evidence better.
- **Option 3: Redirect Tier 1's budget elsewhere.** Use the 2-3 developer-days originally earmarked for Tier 1 to implement higher-leverage items from this retrospective (worker-genericization, review-loop guardrails, template library).

**Recommendation (revised per RSI decomposition session):** **Option 2** — rescope Tier 1 to constitution-tier edits only. The RSI session's pushback, which I accept, is that Phase 1's zero spec-violations was enabled by task specs that were themselves the product of Opus↔operator pre-filter — two humans catching paraphrase-prone phrasings before Kimi saw them. Other projects using RSI won't have that pre-filter. The paraphrase-from-memory failure mode is still the one that shows up *without* a pre-filtered spec, which Tier 1 directly addresses.

Constitution-only scope keeps Tier 1's implementation effort bounded while preserving its value for the class of projects that need it most. Guarded-tier expansion can be considered later based on field evidence, not preemptively.

Option 3 (redirect budget) is rejected: the retrospective underweighted the fact that Phase 1's fidelity depended on specs that most projects won't have. Tier 1's value is real but was obscured by our specific setup.

---

### 3.3 Module B interactivity vs automation

**Pattern:** Module B (reflection capture) is designed around interactive stdin — operator answers 12 prompts about the commit. Claude Code tool harness has no TTY, so answers are piped via printf feeding hardcoded responses from `docs/rsi-ceremony-answers.md` templates.

**Gap:** The printf-feed workaround is functional but awkward:
- Requires a per-commit-type template in a docs file
- Template responses are generic, not specific to the commit
- "Reflection" loses its intended meaning when it's printf-fed from a template
- No clear way to inject a single override answer without editing the template

**Design question:** Should Module B be:
- Interactive-only (current design, requires TTY and human attention per commit)
- Programmatic with structured input (e.g., `--findings-file path/to/findings.json`)
- Hybrid (interactive when TTY available, programmatic when not)

**Recommendation for RSI session:** Hybrid with clean programmatic interface. `--findings-file` flag accepting structured YAML/JSON with the 12 required answers. Interactive mode remains default when TTY is available. Documentation clarifies that programmatic mode sacrifices reflection quality for automation-feasibility.

**Priority:** Medium. Unblocks the automated pipeline case.

---

### 3.4 Pre-commit hook uses `preflight` not `verify`

**Pattern:** The git pre-commit hook installed by `rsi init` runs `preflight` (basic lint + self_verify) but not `verify` (full ceremony check). Commits can land even while Module A/B/C are blocked or crashing.

**Evidence:** Throughout Phase 1, every commit landed despite Module C crashing on every invocation (U3). If the pre-commit hook had run `verify`, commits would have been blocked until U3 was fixed.

**Design question:** Should pre-commit block on ceremony module failures? Arguments both ways:

- Pro blocking: Forces fixing ceremony bugs, prevents silent learning-signal loss
- Anti blocking: Ceremony is a learning layer, not a correctness layer; blocking commits on ceremony failures means a ceremony bug can halt all project work

**Recommendation for RSI session:** Configurable. Add `pre_commit_strictness` to `architecture.yaml` with options:
- `preflight_only` — current behavior, lint + basic checks
- `verify_warn` — run full verify, warn on failures but don't block
- `verify_strict` — run full verify, block on any failure

Default to `verify_warn` — surfaces ceremony bugs without halting work. Projects can opt into `verify_strict` when ceremony stability is mature.

**Priority:** Medium. Addresses U4 in a configurable way.

---

## 4. Systemic lessons from Phase 1

These are meta-observations about the Opus↔Kimi-via-Claude-Code pattern that inform framework design beyond specific bug fixes.

### 4.1 Review-memo quality is load-bearing for multi-layer review

**Observation:** The three-layer review architecture (Opus as reviewer-of-reviewer, Claude Code as producer-reviewer, Kimi as producer) works when Claude Code's review memos are substantive. When memos are thin, the whole pattern degrades to "Opus re-reads Kimi's raw output" — which doesn't scale.

**Concrete data:** After the review-loop architecture correction, Claude Code's memos on compute_skill_sim, compute_trajectory, compute_prefs, and build_match_score were of sufficient quality that Opus approved apply-with-edits directly without reading Kimi's raw output. That's the pattern working at scale. Before the correction, Opus was doing the reviewer work directly.

**Implication for RSI:** Review-memo quality should be explicitly supported by framework tooling. Not just "please write a review memo" — RSI should provide:
- Memo template with required sections (findings by severity, decision, proposed edits)
- Memo quality checks (all severity tiers addressed, decision stated, edits specific)
- Memo-history integration (past memos for similar tasks inform future memos)

---

### 4.2 Calibration traps as a discipline-verification technique

**Observation:** Two places in Phase 1 task specs planted deliberate ambiguities to test whether Kimi would preserve spec fidelity under semantic-smoothing pressure:
- compute_prefs A5 (role_level asymmetric 0.3 partial credit — easy to normalize to 0.0 for consistency with other binary dimensions)
- build_match_score Branch 4 (weights override that would collide with `validate_composite_formula`'s hardcoded constants — easy to bypass with `.model_construct()`)

Both traps fired correctly. Kimi preserved the spec-unusual behavior in both cases and surfaced engagement in the ambiguity-resolution output.

**Implication for RSI:** This is a generalizable task-spec pattern worth codifying. Task-spec templates could include a `## Calibration traps` section where task authors explicitly name "here are spec details that are easy to semantically-smooth; we're testing whether the producer preserves them." Makes the discipline-verification explicit rather than emergent.

---

### 4.3 Self-report directives convert behavior into verifiable evidence

**Observation:** The build_match_score task spec's §10 included an explicit instruction for Kimi to self-report in the `notes` field: "state whether you read validate_composite_formula's implementation, what you found, what you chose to do."

Kimi's response was substantively genuine — not just acknowledging the validator exists, but describing its exact behavior and stating the implementation decision. That produced verifiable evidence of the discipline rather than inferred evidence from output alone.

**Implication for RSI:** Self-report prompts are a cheap, reusable pattern for converting "did the producer do X" from inference to direct verification. Task-spec templates could include a `## Self-report directives` section listing "explicitly state in your notes whether and how you..." for the specific disciplines the task requires.

---

### 4.4 Template engineering compounds

**Observation:** Each Phase 1 task spec inherited improvements from the prior. By the time build_match_score's spec was written (5th in sequence), it preempted multiple classes of error that earlier specs hadn't. The compounding was visible: finding counts decreased across the sequence despite increasing algorithm complexity.

**Implication for RSI:** The task-spec template is an asset that accumulates value. Treating it as first-class framework infrastructure (per §2.5 above) means future projects start from a tighter baseline and continue adding to it.

---

### 4.5 Infrastructure-gap findings surface in predictable patterns

**Observation:** Throughout Phase 1, pre-commit hooks surfaced latent issues each time they ran against a previously-unexercised file set:
- C1 (mypy on `tests/` revealed missing test-file exclude)
- C2 (pre-commit hook ordering)
- F7 (mypy couldn't resolve `src/job_platform.*` package paths)
- F8 (83 latent ruff errors in committed code that pre-commit-on-commit caught but pre-commit-on-backfill missed)

Pattern: each gap surfaces exactly once, when the relevant file type first lands in a commit. After fix, doesn't recur.

**Implication for RSI:** `rsi init` or `rsi audit` could proactively run every configured tool against every file type before the first real commit, surfacing all latent gaps at once rather than incrementally across early commits. Reduces early-project friction by a lot.

---

### 4.6 Reviewer-of-reviewer pattern — deferred as separate product question

> **Note on deferral:** The RSI decomposition session's pushback, which I accept: this is a separate product question bigger than RSI's scope. General-purpose vertical-review architecture is its own design problem and grafting it onto RSI would distort the framework. Kept as section for historical record and to make the deferral explicit; not a work item for the RSI project roadmap.

**Observation:** Opus (operator's reviewer) oversaw Claude Code's reviews of Kimi's output. This "reviewer-of-reviewer" relationship caught:
- Review-loop architecture drift (operator-surfaced, not me-surfaced, but reinforced by framework clarification)
- Review memo quality issues early in the sequence
- Task-spec template improvements that Claude Code hadn't yet internalized

**Implication for RSI:** Most multi-agent frameworks assume horizontal agent relationships (peers pass tasks between them). The reviewer-of-reviewer relationship is vertical — each layer reviews the one below and is reviewed by the one above. Standard frameworks don't support this shape well — but making RSI the place to solve this would expand the framework's scope beyond self-improving single-agent workflows.

Deferred. If it matters later, it belongs in its own project, not grafted onto RSI.

---

## 5. Proposed prioritization for the RSI project roadmap (revised)

> **Note on revision:** The RSI decomposition session proposed "four sessions, not four tiers" — closer to a concrete sequence than abstract tiers. Accepting that framing. Also integrating §2.8 (automated self-review) and the accepted pushback on §3.2 (Option 2) and §2.4 (template-only).

### Session 1 — Bug batch

*Session estimate: one session*

- **U5** (YAML inline-comment strip) bundled with **§2.7** (spec-amendment tracking structure) — both touch `classify_file.py` semantics; coherent single commit per RSI session's pushback
- **F6 + 9b** — Raw sidecar + delimiter parser (port local patches with tests)
- **U1** — self_verify diff-scope (port F1 with tests)
- **U6 + F9** — delegate temperature and max_output_lines per-worker (port F5 + F9 together, both touch `delegate.py` config loading)

Deliverable: framework fork has parity with our local patches, all tested. No design questions in this session — everything here is port-with-tests or trivial fix.

### Session 2 — Calibration

*Session estimate: one-to-two sessions*

- **U3** — Module C argv crash (needs Q1 from operator: what was the intended argv contract?)
- **F3** — Ceremony classifier content-type heuristic
- **U4** — Pre-commit strictness configuration (preflight-only / verify-warn / verify-strict)
- **U2** — Module B programmatic mode (`--findings-file` flag)

Deliverable: steady-state friction reduced; calibration matches real usage patterns. U3 blocks on operator input; other items proceed in parallel.

### Session 3 — Worker-genericization

*Session estimate: one-to-two sessions*

- **§2.1** — Thread per-worker config (temperature, max_output_lines, extra_body, timeout, format preference) through `delegate.py` without committing to a formal `WorkerProfile` dataclass yet. Incremental: convert hardcoded defaults to config-driven on a dimension-by-dimension basis. Dataclass formalization can follow after incremental work proves the shape.

Deliverable: delegate is worker-agnostic. Second worker class (hypothetical future) can be added via config change, not code change.

### Session 4 — Framework assets (pick one)

*Session estimate: one-to-two sessions per asset*

Three candidates; RSI session and operator pick one to start:
- **§2.5** — Task-spec template library (seeds from job-platform's Phase 1 templates)
- **§2.6** — Testing conventions corpus (seeds from job-platform's `docs/testing-conventions.md`)
- **§4.5** — `rsi audit` command (proactive infrastructure gap detection at `rsi init` or on-demand)
- **§2.4** — Review-memo template shipped as framework asset (per revised §2.4 — template-only, not tool-gated)

Deliverable: one framework-level asset in place. Others queued for later sessions.

### Session 5+ — Automated self-review (§2.8)

*Session estimate: multiple sessions, substantial work*

The target architecture in §2.8 is substantial and gets sequenced after the simpler improvements are in place. Proposed sub-sequence:

- **Session 5a:** Self-review protocol as memo-template expansion (self-audit questions, decision matrix, calibration-signal prompts). Single session.
- **Session 5b:** Calibration-trap library (initial release covering type coercion, validator constraints, enum ordering, boundary conditions, spec bugs). Multiple sessions to build up library; one session to wire trap-selection into task-spec authoring.
- **Session 5c:** Memory-driven consistency enforcement (active consultation of prior memos, calibration data, template decisions, cross-session commitments). Single session for implementation, plus ongoing discipline for use.
- **Session 5d:** Human-escalation criteria and calibration plan (scheduled external-reviewer sessions, retrospective self-audit gates, calibration-trap outcome monitoring). Mostly documentation plus minor tooling.

Deliverable: the job-platform project (and other RSI-using projects) can run producer-reviewer loops autonomously for routine work, with operator-in-loop only at explicit escalation points.

### Tier 4 — Reconsider or defer (unchanged from prior)

*Session estimate: TBD*

- **§3.2 Tier 1 reference-binding spec — Option 2 confirmed** (constitution-tier only). Implementation session TBD; spec already written.
- **§3.1 Batch-ceremony** (design work before implementation; Direction B — proportionality — likely preferred per prior analysis, but genuine design question)
- **§4.6 Reviewer-of-reviewer** — **explicitly deferred** as separate product question per RSI decomposition session.

Deliverable: intentional decisions on remaining items based on evidence from Sessions 1-5.

---

## 6. What to carry into the RSI project session

If I were the RSI project's next Claude Code session, here's what I'd want from this retrospective:

**Required context:**
- The eight bugs in §1 with their local patches, evidence, and tests-to-add
- The eight gaps in §2 with proposed framework changes, including §2.8 (automated self-review) as the most substantial architectural direction
- The four calibration problems in §3 with design questions named
- The six systemic lessons in §4 as design principles (§4.6 explicitly deferred)

**Optional context:**
- The revised prioritization in §5 as a starting roadmap (subject to RSI project's broader goals)
- The specific commit SHAs referenced throughout (available in the job-platform git history if deeper investigation is needed)

**What not to do:**
- Don't implement anything before reading the full retrospective
- Don't copy local patches from the job-platform fork verbatim — port them with proper tests and documentation
- Don't assume all findings are equal priority; the prioritization in §5 is informed by Phase 1 evidence but the RSI project has its own context

**First-session deliverable (suggested):**
- A decomposition/prioritization document that responds to the retrospective
- No code yet — decomposition and prioritization exercise first
- After that, Session 1 (bug batch) starts with actual implementation

---

## 7. Meta: on the retrospective itself

This document is opinionated. It represents the operator's (and Opus's) view of what Phase 1 revealed about RSI. The RSI project's maintainer may read the evidence differently and reach different conclusions about priorities.

That's fine. The document's purpose is to hand off field evidence, not to prescribe solutions. Every finding has specific evidence attached, so the RSI project can reach its own conclusions while having the same data to work from.

**Revision history:**

This document was revised once after the initial draft, in response to:
1. RSI decomposition session pushback on §2.4 (tool-gated → template-only), §3.2 (Option 3 → Option 2), §2.7 (priority elevation), §4.6 (defer entirely)
2. Operator clarification that the retrospective's scope should include automated self-review architecture (§2.8 added)

The revisions are flagged inline with "Note on revision" or "Note on deferral" annotations where substantive changes were made.

**Things to push back on if they don't match RSI's design intent:**

- §2.8 Automated self-review assumes framework-supported self-audit can approximate external review quality. That's an empirical question, not a proven claim. The calibration plan (scheduled external-reviewer sessions) exists to test it.
- §3.1 Batch-ceremony Direction A vs B is a genuine design question; Direction B (proportionality) leans preferred per analysis but neither is confirmed.
- §2.1 Worker-genericization as `WorkerProfile` dataclass may be premature formalization; the RSI session's alternative — incremental thread-through without formal dataclass — is defensible and may be better.
- §4.6 Reviewer-of-reviewer is deferred; if RSI's broader roadmap includes vertical-review architecture, this decision is revisitable.

The retrospective is input, not conclusion.
