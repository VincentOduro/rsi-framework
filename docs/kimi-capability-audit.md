# Kimi K2.6 capability audit — RSI framework support

**Audit date:** 2026-04-24 (end of Session 4, before pause)
**Audit scope:** every capability in the official Kimi K2.6 capability matrix,
classified against RSI's dispatch model.
**Purpose:** identify what the framework already supports, what's in-scope
and could be added with small work, and what's out-of-scope for RSI's
single-worker-dispatch architecture. Does not include implementation —
operator chooses which gaps (if any) warrant work.

---

## Classification key

- **✓ Supported** — already works today. No action needed.
- **△ In-scope gap** — fits RSI's dispatch model, not yet wired; small
  session of work to close.
- **✗ Out of scope** — doesn't fit RSI's dispatch model (single-worker,
  dispatch-on-demand, structured-output). Wiring these would expand the
  framework's scope beyond its intent; belongs in a different product.
- **?** — genuinely ambiguous. Depends on operator goals for what RSI
  should become.

---

## 1. Architecture & core specs

No RSI action required — these are model-intrinsic properties, not API
surface.

| Capability | Status | Notes |
|---|---|---|
| 256K context window | ✓ | We don't artificially limit input prompts. Task specs + files_to_read typically well under this. |
| 98K max output tokens | ✓ | Our `max_tokens: 32768` is conservative; can raise if needed. |
| MoE / MLA / 1T params | n/a | Implementation detail, no API-level action. |
| Vision encoder (MoonViT) | see §3 | Multimodal input section. |
| Open weights | n/a | Operator deployment choice, not framework. |

---

## 2. API access & compatibility

| Capability | Status | Notes |
|---|---|---|
| Base URL `api.moonshot.ai/v1` | ✓ | Pinned in `.rsi/architecture.yaml` workers.kimi.base_url (Session 1 correction). |
| OpenAI-compatible `ChatCompletion` | ✓ | We use the `openai` SDK throughout. |
| Bearer auth via env var | ✓ | `KIMI_API_KEY` per worker config. |
| Model ID `kimi-k2.6` | ✓ | Pinned in config. |
| Model ID `kimi-k2.6-thinking` | n/a | Probed the live `models.list()` endpoint 2026-04-24: no separate `-thinking` model ID. Thinking mode is controlled via `extra_body`, not a distinct model. The capability matrix's mention of a separate ID is either aspirational or docs-drift. |
| Third-party inference providers | ? | If operator wants to route through Together / Fireworks / OpenRouter, the `base_url` field already supports it. Not currently wired for failover. |

---

## 3. Multimodal input (text / image / video)

RSI's dispatch model delivers structured text tasks that produce
structured text output. No current use case for image or video input.

| Capability | Status | Notes |
|---|---|---|
| Text input | ✓ | Standard dispatch path. |
| Image input (base64 / URL) | ✗ | Would require prompt-building in `build_worker_prompt` to accept `{"type": "image_url"}` messages. No RSI task today involves image input. |
| Video input (base64 MP4) | ✗ | Same as image; experimental on vendor side per matrix; no RSI use case. |

**Expanding this** would turn RSI into a general multimodal-dispatch
framework — different product.

---

## 4. Dual operating modes (thinking / instant)

| Capability | Status | Notes |
|---|---|---|
| Instant mode | ✓ | Current Kimi worker config: `temperature: 0.6`, `extra_body: {"thinking": {"type": "disabled"}}`. |
| Thinking mode | △ | Requires a separate worker config (temperature 1.0, `extra_body: {"thinking": {"type": "enabled"}}`). Could add `kimi-thinking` as a second named worker in `.rsi/architecture.yaml`. Operator routes per-task via `task["worker"]`. |
| Recommended top-p 0.95 | △ | We don't currently set `top_p`. Adding per-worker `top_p` field is ~5 lines. |
| Temperature-constraint enforcement | ✓ | Session 3 WorkerProfile handles the float cast. Session 1 architecture.yaml documents the constraint (0.6 instant, 1.0 thinking). |

**Recommended implementation (if operator wants thinking mode):**

- Add `kimi-thinking` worker entry in `.rsi/architecture.yaml` with the
  thinking-mode parameter set.
- Optionally add `top_p` to WorkerProfile with default 0.95.
- Operator selects `"worker": "kimi-thinking"` on task specs that need
  deep reasoning (complex algorithm, math-heavy, multi-step).

Effort: ~1 small commit, no code changes in delegate.py (existing
`extra_body` + temperature plumbing covers it).

---

## 5. Reasoning / chain-of-thought features

| Capability | Status | Notes |
|---|---|---|
| `reasoning_content` exposure | △ | Verified 2026-04-24 with live API: thinking-mode response includes `reasoning_content` field (171 chars for a trivial probe). Our delegate reads `.content` only and discards `reasoning_content`. |
| Preserve thinking (`keep: all`) across turns | ✗ | Requires multi-turn conversation state. RSI dispatches single-shot. |
| Reasoning-content sidecar | △ | If we capture `reasoning_content`, saving to `.memory/reviews/results/TASK-{ID}.reasoning.txt` alongside the raw sidecar would give review-time visibility into the producer's chain-of-thought. Useful calibration data for Session 4's trap-outcome audits. |

**Recommended implementation (if operator wants reasoning capture):**

- In `call_worker`, after `raw = response.choices[0].message.content`,
  also capture `getattr(response.choices[0].message, 'reasoning_content', None)`.
- Write to `.memory/reviews/results/TASK-{ID}.reasoning.txt` alongside
  the existing `.raw.txt` sidecar. F6-style unconditional write.
- Review-memo template §7 metadata section can gain a pointer to the
  reasoning sidecar path.

Effort: ~1 small commit, additive to F6 sidecar infrastructure.

---

## 6. Agent swarm & agentic execution

| Capability | Status | Notes |
|---|---|---|
| 300 sub-agents, 4000 coordinated steps | ✗ | RSI's model is single-worker dispatch per task. Agent swarm is a different orchestration pattern — workers spawn sub-workers, coordinate results, synthesize. Not a bolt-on; a different product. |
| Parallel subtask decomposition | ✗ | Same concern. |

**Expanding this** would require RSI to become an agent-orchestration
framework. Retrospective §4.6 explicitly deferred the
reviewer-of-reviewer vertical-review architecture as out of scope; agent
swarm is the horizontal version of the same scope question. Same
disposition: separate product.

---

## 7. Tool calling & multi-step execution

| Capability | Status | Notes |
|---|---|---|
| Interleaved thinking + tool calls | ✗ | Our worker returns files via structured JSON or delimiter blocks (9b). Tool calling would be a different output protocol and a different orchestration pattern (execute tool → feed result back). |
| 200-300 sequential tool calls | ✗ | Same concern. |
| Built-in `$web_search` tool | ✗ | Not our task model. |
| Custom function schemas | ✗ | Same. |

**Expanding this** has genuine merit — a tool-calling worker could
read files dynamically at dispatch time rather than requiring them in
`files_to_read`. But that's a structural architecture change, not a
configuration change. Would warrant its own session arc.

---

## 8. Long-horizon coding

| Capability | Status | Notes |
|---|---|---|
| SWE-Bench / LiveCodeBench scores | ✓ | We benefit from these via the underlying model. Nothing to wire. |
| Rust / Go / Python / frontend | ✓ | Language-agnostic; our tasks pass through verbatim. |
| Vision-to-code | ✗ | Requires multimodal input (§3). |

---

## 9. Proactive autonomous execution

| Capability | Status | Notes |
|---|---|---|
| Persistent background agents | ✗ | RSI is dispatch-on-demand. Persistent agents are a different execution model (long-running, scheduled, self-directing). Not a scope fit. |
| 24/7 operation | ✗ | Same. |

---

## 10. Context & memory

| Capability | Status | Notes |
|---|---|---|
| 256K input context | ✓ | We don't limit. Typical dispatches use well under 32K. |
| Long-document analysis | ✓ | Operator could send large `files_to_read` lists; framework handles it. |
| Low hallucination rate | ✓ | Model property. Session 1-3 dispatches showed good fidelity; Session 2 TASK-E8-008 normalization drift was discipline-layer (trap category 6), not hallucination. |

---

## 11. Pricing

Operational, not framework-level. Operator monitors via token-usage
metrics that `delegate.py` already logs to `.memory/metrics/delegations.jsonl`.

---

## 12. Self-hosting & deployment

| Capability | Status | Notes |
|---|---|---|
| Open weights / vLLM / SGLang | ? | Operator deployment choice. If self-hosted, `base_url` points at the local inference server — no framework change needed. |

---

## 13. Key API gotchas — how RSI handles them

| Gotcha | RSI coverage |
|---|---|
| Web search + thinking conflict | ✓ trivially — we don't use web search. |
| `tool_choice` constraint when thinking enabled | ✓ trivially — we don't use tools. |
| `reasoning_content` must be preserved in multi-turn tool conversations | ✓ trivially — we don't do multi-turn. (Would become relevant if §7 tool calling were added.) |
| Video input experimental | ✓ trivially — we don't send video. |
| Temperature-management rules | ✓ — Session 1 architecture.yaml documents and enforces constraints. |

---

## Recommended action summary

### Work that closes meaningful gaps (△)

These would add material capability to RSI for tasks already in-scope:

1. **Thinking-mode worker variant** — add `kimi-thinking` to
   `.rsi/architecture.yaml` with `temperature: 1.0` and
   `extra_body: {"thinking": {"type": "enabled"}}`. Operator routes
   via `task["worker"]`. Enables reasoning-heavy task dispatches. No
   code change.
2. **Reasoning-content sidecar** — capture `response.choices[0].message.reasoning_content`
   and write alongside the raw sidecar. Additive to F6 infrastructure.
   Enables review-time inspection of the producer's chain-of-thought,
   which is useful calibration data for Session 4's trap-outcome
   audits. ~20 lines of `call_worker` change + a test.
3. **Optional: `top_p` per-worker field** — add to WorkerProfile with
   default 0.95. Matches vendor recommendation for both modes. ~5 lines
   of code + config.

Rough effort: 1 session, ~3 commits.

### Work explicitly out of scope (✗)

These belong in a different product:

- Multimodal input (§3)
- Agent swarm (§6)
- Tool calling with interleaved thinking (§7)
- Persistent background agents (§9)

Wiring these would change RSI from a dispatch framework into a general
agent-orchestration framework. Retrospective §4.6 precedent (reviewer-
of-reviewer deferred as separate product) covers the disposition.

### Genuinely ambiguous (?)

- Third-party provider failover (§2). Current `base_url` already
  accepts alternative endpoints; no framework work needed. If operator
  wants automatic failover between Moonshot and OpenRouter on rate
  limits, that's retry-policy work — separate conversation.
- Self-hosting integration (§12). Same: `base_url` handles it today.
  Framework-level self-hosting support isn't needed unless operator
  wants discovery / health-check behavior.

---

## Decision point for operator

Three options, each respects the pause in its own way:

**Option A — do nothing now.** Audit stands as the authoritative record
of what RSI supports vs doesn't. Gaps remain open. Session 5's
`rsi audit` or later sessions revisit when a specific gap becomes
blocking. This is the default-respect-the-pause option.

**Option B — close the two △ gaps now as a Session 4 tail.** Thinking-mode
worker variant + reasoning-content sidecar. ~1 hour of work, 2-3
commits, ends the RSI arc at a cleaner capability boundary. If
job-platform Phase 1 exit validation benefits from thinking-mode
dispatches (complex reasoning on edge cases), this is an investment in
that. If not, delay has no cost.

**Option C — close only the reasoning-content sidecar (△2).** This is
the item most clearly useful regardless of job-platform needs — it's
calibration infrastructure that Session 4's trap-outcome audits would
use. Thinking-mode variant defers until a specific task surfaces the
need. ~1 small commit.

**My recommendation: Option A unless you have a concrete job-platform
Phase 1 exit validation use case.** The capabilities in § matter when a
task surfaces the need. Right now, job-platform returns to 10-JD
validation, which doesn't need thinking-mode (spec-bound algorithm
validation, not open reasoning). Leaving the gaps open for a later
session where they have concrete motivation is cheaper than
implementing preemptively.

**If your "ensure Kimi can perform all its functions" request was
closer to "audit coverage so I can see what's there," this document is
the answer.** If it was "wire everything that fits," Option B is the
minimal useful delta.

Operator picks.
