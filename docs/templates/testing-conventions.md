# Testing conventions corpus

Canonical test-discipline conventions seeded from Phase 1 field evidence
and Session 1-3 RSI-project work. Each convention is earned from a
specific failure mode; the "why" line is non-negotiable context because
the rules look arbitrary without the incident behind them.

Projects extend this corpus with their own conventions. When a
project-specific convention generalizes (appears in ≥2 RSI-using
projects), it's a candidate for promotion back to this canonical base.

---

## §1 Monkeypatching functions with local imports

**Rule:** `monkeypatch.setattr` must target the **source module where the
function is defined**, not the module that imports it — unless the
import happens at module-load time at the consumer (classic `from X
import Y` at the top).

For **local imports** (inside a function body), the name resolves in the
source module at call time, so patches on the consumer module don't
take effect. This is a Phase 1 compute_skill_sim-era discovery.

**Why:** Phase 1 C2 surfaced this: a test patched `consumer.embed`
expecting to intercept `consumer`'s `embed` calls, but the consumer
imported `embed` locally inside the function body. Python resolved
`embed` in the source module on each call, so the patch fired zero
times and the test silently exercised real behavior. Caused a review
cycle that looked like a worker bug but was a test-discipline bug.

**How to apply:**

```python
# consumer.py
def compute_skill_sim(...):
    from embeddings import embed    # local import
    return embed(...)

# tests/test_consumer.py — WRONG
def test_compute_skill_sim(monkeypatch):
    monkeypatch.setattr("consumer.embed", fake_embed)   # ineffective
    ...

# tests/test_consumer.py — RIGHT
def test_compute_skill_sim(monkeypatch):
    monkeypatch.setattr("embeddings.embed", fake_embed)  # patches source
    ...
```

**Diagnostic when this fires:** test passes when it should fail, or
vice versa. The symptom: fixture prep looks correct; assertion should
exercise the patched behavior; it doesn't. Check which module defines
the function vs which module imports it. If the import is local, patch
the source.

---

## §2 Pytest fixture discovery

**Rule:** fixtures live in **`conftest.py`** at the appropriate scope or
in the **same test module** that uses them. Fixtures defined in a
sibling test module (e.g., `tests/test_a.py` → `tests/test_b.py`) are
**not auto-discovered** — the test referencing them fails with
"fixture not found" even though the name is lexically present in the
test tree.

**Why:** Phase 1 compute_trajectory surfaced this: a well-intentioned
fixture in `test_compute_hard_match.py` was referenced from
`test_compute_trajectory.py`. Test collection failed; the fix was
either duplicating the fixture or moving it to `conftest.py` at the
shared directory level.

**How to apply:**

```
# Shared across many tests → conftest.py at project root
tests/conftest.py:
    @pytest.fixture
    def sample_match_score(): ...

# Shared across tests in one directory → conftest.py at directory level
tests/unit/conftest.py:
    @pytest.fixture
    def unit_fixture(): ...

# Used in exactly one test module → same module
tests/test_compute_trajectory.py:
    @pytest.fixture
    def trajectory_fixture(): ...
    def test_something(trajectory_fixture): ...
```

**Diagnostic when this fires:** pytest error `fixture '<name>' not
found`. `pytest --fixtures` lists the fixtures available at collection;
if the expected fixture isn't there, check whether it's in a sibling
module (wrong) rather than conftest or same-module (right).

---

## §3 Latent defects behind xfail — seen-twice pattern

**Rule:** `@pytest.mark.xfail` without a concrete linked issue or TASK
reference is a code smell. Xfail **masks** failures; a legitimate xfail
points at a tracked defect that will be fixed, and the xfail comes off
when the fix lands. An xfail with no link points at a **latent defect**
someone gave up on.

The "seen-twice pattern": when you see the same xfail annotation twice
(in code review, in a different module, or on a related test),
investigate rather than accept — the duplication suggests an
undocumented shared root cause the xfails are collectively masking.

**Why:** Phase 1 build_match_score surfaced two instances of this:

- I14 Evidence validator — an xfail masked a field-order bug in the
  @model_validator. The xfail made the failure silent; fixing required
  the model's validator to be rewritten (spec amendment I14).
- KNOWN_VECTORS compound-string gap — an xfail masked a fixture-setup
  error. The fix was a fixture correction; the xfail had been obscuring
  a real discipline gap.

Both were caught because the reviewer noticed the xfail pattern twice in
close succession and stopped to investigate rather than accept.

**How to apply:**

```python
# ACCEPTABLE — concrete reference, will be removed on fix
@pytest.mark.xfail(reason="TASK-E8-014: fix pending, see SPEC_AMENDMENTS.md I14")
def test_evidence_validator_field_order(): ...

# CODE SMELL — no reference
@pytest.mark.xfail(reason="flaky, sometimes passes")
def test_something(): ...

# CODE SMELL — philosophical
@pytest.mark.xfail(reason="edge case we'll get to later")
def test_rare_path(): ...
```

**Diagnostic when this fires:** reviewing a diff, grep for `xfail`. If
the reason is vague or missing, flag it. If you see the same vague
reason twice across separate changes, stop and investigate the
underlying pattern rather than adding a third.

---

## §4 Diagnostic conventions (reference)

Debugging workflow — config-drift-before-dependency-breakage — lives in
its own document at `docs/diagnostic-conventions.md`. That document
includes the Kimi K2.6 endpoint case study (Session 1) as the canonical
worked example.

The convention in one sentence: *when a dependency reports failure and
you have reason to believe it works elsewhere, the first hypothesis is
config drift on your side (endpoint, model ID, parameter shape), not
dependency breakage.*

See the full document for: the signature → hypothesis lookup table,
the case study, and when the convention does NOT apply.

---

## §5 Config-value-not-consumed

**Rule:** every config key read by the framework (architecture.yaml,
rules.yaml, similar) is either **actively consumed** by current code or
**explicitly flagged** as deprecated / pending. Unused config keys are
landmines — a future consumer wires them up and inherits the stale
value without realizing.

**Why:** Session 3 WorkerProfile migration caught this: MiniMax's
`timeout_seconds: 120` field had been parsed into the config dict
since before the framework shipped dual-worker support, but nothing
read it. When Session 3's refactor added a
`client_timeout_seconds → timeout_seconds → 600` fallback chain, the
stale 120 silently became MiniMax's effective client timeout —
shrinking dispatches from the SDK's default 600s to 120s without any
code-visible change. Caught by manual review during the dataclass
migration, not by tests.

The failure mode is subtle: the config key *looked* correct because it
had been there "for a long time," and the fallback wiring *looked*
correct because it referenced a real config field. Neither alone was
wrong; the combination was a regression.

**How to apply:**

1. At config authoring time: for every key, either ensure it's
   actively consumed OR add a comment marking it as deprecated /
   pending-wiring. Deprecated keys get a deletion ETA.
2. At code-review time for fallback chains: when a new default-
   resolution chain is added, audit every field referenced. If any
   field is not currently consumed elsewhere, either wire it or drop
   it from the chain.
3. When wiring a previously-unused field: check git blame for the
   introduction, search for tests that depend on the stale value,
   consider pinning the field to a sensible current value rather
   than inheriting the legacy.

**Diagnostic when this fires:** a config change that *should* be
behavior-neutral produces behavior drift in a specific worker / module
/ subsystem. If the drift tracks to a config value, check when that
value was last consumed. If it's the first consumption after a
multi-release gap, the "new" consumer inherited stale data.

---

## §6 Test name vs test behavior divergence

**Rule:** a test's name must describe what it actually verifies. When
the name promises X and the logic tests Y, fix the divergence — either
rename to match behavior, or fix behavior to match the name.
Workarounds (deselects, expected-failure markers, "for now" comments)
are acceptable only with a concrete follow-up commit to converge.

**Why:** Session 2's
`tests/test_delegation_gate.py::test_gate_inactive_without_minimax_key`
and `tests/test_hooks.py::test_pre_edit_allows_read_file` both promised
"gate inactive without MiniMax key" behavior but actually required
*both* MINIMAX_API_KEY and KIMI_API_KEY to be absent (post-dual-worker
R04 update). The test names were written when single-worker was the
only mode; dual-worker support shipped later and the tests quietly
started failing in environments where KIMI_API_KEY was set.

The workaround that accumulated: `--deselect` these tests in every CI
run. That kept the suite green but masked the name-behavior divergence.
Every session's full-suite run prefixed with two `--deselect` lines
until Session 2 housekeeping fixed both at the root.

**How to apply:**

```
# WRONG — name promises X, body tests Y
def test_gate_inactive_without_minimax_key(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    # KIMI_API_KEY stays set in dev env, so R04 stays active
    # → test fails despite name promising inactive gate

# ONE FIX — rename to match behavior
def test_gate_inactive_without_any_worker_keys(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    ...

# THE OTHER FIX — change behavior to match name
# (not applicable here — R04's dual-worker check is the intended behavior)
```

**Diagnostic when this fires:** a test fails intermittently or only in
specific environments. Reading the test name suggests one thing; reading
the test body shows another. Don't add deselects or xfails to paper
over; converge the name and behavior.

**Corollary — deselects accumulate into technical debt.** When you add
`--deselect` to a test run, the timer starts. Either fix the underlying
divergence or accept that the deselect is permanent and mark the test
with `@pytest.mark.skip(reason=...)` so its status is visible. Silent
deselects at CI layer hide failing tests from everyone except whoever
edits the CI config.

---

## §7 (Reserved for project-specific additions)

Append here when a convention emerges that's specific to this project
but doesn't yet generalize. Keep the same structure as the canonical
sections: Rule / Why / How to apply / Diagnostic when this fires.

Convention candidates are promoted back to §1-§6 (or a new numbered
section) when they appear in another RSI-using project — the
promotion threshold is "seen twice" from different contexts.

---

## Provenance

- §1 Monkeypatch source-module (Phase 1 Update E, compute_skill_sim C2)
- §2 Pytest fixture discovery (Phase 1 compute_trajectory review)
- §3 xfail seen-twice pattern (Phase 1 build_match_score, I14 Evidence
  validator + KNOWN_VECTORS)
- §4 Diagnostic conventions reference (Session 1 Kimi endpoint case
  study → docs/diagnostic-conventions.md)
- §5 Config-value-not-consumed (Session 3 MiniMax timeout_seconds
  latent regression, caught during WorkerProfile migration)
- §6 Test name vs test behavior divergence (Session 2 housekeeping fix
  for test_gate_inactive_without_minimax_key and
  test_pre_edit_allows_read_file)

Each convention is load-bearing: it came from a specific failure that
cost specific time. The rule is cheap to follow once you know the
incident; the lesson isn't teachable in the abstract.
