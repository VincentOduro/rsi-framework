# Diagnostic conventions

Short reference for debugging workflow inside RSI projects. Grows over time
as specific diagnostic failures produce generalizable patterns.

---

## Config drift before dependency breakage

**Convention:** When a dependency reports a failure and you have reason to
believe the dependency works elsewhere — another session, another user, a
recent green CI run — the *first* hypothesis is configuration drift on
your side (wrong endpoint, stale model ID, parameter shape change),
**not** breakage of the dependency.

**Why this matters:** Misdiagnosing config drift as dependency breakage
costs 2× — first the time spent working around the imagined breakage
(override, skip, fall back to a weaker tool), then the time spent actually
fixing the config once the true cause surfaces. The cost compounds if the
workaround leaks into committed code as scope creep.

**How to apply:** Before concluding a dependency is broken, run a narrow
probe against it with varied parameters. Two to five API calls covering
the plausible dimensions (endpoint, model name, auth shape, temperature,
extra parameters) resolves most cases in under a minute. If all probes
fail with the same signature, then it's plausibly real breakage. If any
probe succeeds, the winning configuration is your answer.

**Typical signatures and what they point at:**

| Signature                                          | First hypothesis                                   |
|----------------------------------------------------|----------------------------------------------------|
| 401 on one endpoint, 200 on a sibling endpoint     | Wrong region / tenant / base URL                   |
| 404 "model not found" on a vendor's active API     | Stale model ID; call `models.list()` to discover   |
| 400 "invalid parameter X" after a known-good call  | Vendor constraint changed; re-read API reference    |
| 5xx on a single endpoint across multiple calls     | Vendor-side incident; probe `/health` if available  |
| Timeout + partial response                         | Client timeout < server budget, or streaming edge   |
| 200 OK with empty content and usage=N              | Vendor added a new output channel (reasoning, audio) |

---

## Case study: Kimi K2.6 authentication (2026-04-24)

**What happened:** Session 1 attempted to delegate a task to Kimi via
`delegate.py`. The OpenAI SDK returned `AuthenticationError: Error code:
401 - Invalid Authentication`. The conclusion was "Kimi key is broken,
fall back to MiniMax." Three dispatches later, an override was used to
unblock U1's guarded-tier edit.

**What was actually wrong:** The worker configuration in
`.rsi/architecture.yaml` pointed `kimi.base_url` at
`https://api.moonshot.cn/v1` (the China region). The API key in use was
provisioned for `https://api.moonshot.ai/v1` (the international region).
The `.cn` endpoint rejected the key as "Invalid Authentication." The
`.ai` endpoint accepted the same key immediately.

The model ID was also stale (`moonshot-v1-128k` had been the default a
generation earlier; `kimi-k2.6` was what the operator actually used in
other sessions). And the worker needed
`extra_body={"thinking": {"type": "disabled"}}` with `temperature=0.6`
to produce deterministic non-thinking output rather than burning budget
on `reasoning_content`.

**Empirical resolution:** The entire diagnosis took two probes:

```python
client = OpenAI(api_key=os.environ["KIMI_API_KEY"], base_url="https://api.moonshot.ai/v1")
models = client.models.list()  # 200 OK → key works, endpoint was wrong
# output includes kimi-k2.5, kimi-k2.6 — discover the real model ID

resp = client.chat.completions.create(
    model="kimi-k2.6", messages=[...], temperature=0.6,
    extra_body={"thinking": {"type": "disabled"}},
)
# 200 OK, clean content → full config resolved
```

Two minutes of probe work. The cost of the misdiagnosis was larger: one
override (U1), one task retry cycle, and a commit message explicitly
flagging the override as contingent on Kimi being unavailable when it
wasn't.

**Discipline lesson captured:** Before concluding "X is broken," run a
narrow probe. `models.list()` is almost always safe and answers "does
this key work against this endpoint" in one call. Endpoint-and-model
variations cost seconds to try. The convention above is the
generalization of this specific incident.

---

## When this convention does not apply

- **Probing is destructive.** Don't blindly call `POST /delete_account`
  just because auth is returning 401. If the probe itself has side
  effects beyond a normal read, fall back to vendor docs or support.
- **The dependency is your own code and you can read its source.** In
  that case, reading the code is faster than probing its behavior.
- **You have high confidence in a recent success.** If you made the same
  call successfully five minutes ago with identical config, the problem
  is more likely transient (network, rate limit, vendor-side hiccup)
  than config drift.

---

## Adding to this document

New convention entries should include:

1. The convention itself, stated as a short rule.
2. **Why** — what breaks when the convention is violated.
3. **How to apply** — concrete procedure or decision rule.
4. A case study (optional but strongly preferred) with specific
   signatures, the misdiagnosis, and the fix.

Keep entries narrow and evidence-backed. One convention per section.
