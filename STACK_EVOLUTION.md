# RSI Framework — Stack Evolution Plan

**Status:** Proposal (v2, corrected)
**Author:** Drafted with Claude (orchestrator), reviewed and corrected
**Date:** 2026-04-17
**Scope:** Polyglot refactor — keep Python where it wins, replace hot paths with Go, reserve Rust for measured bottlenecks.

---

## 1. Executive Summary

The RSI Framework is ~11,300 lines of Python (9,031 scripts + 2,026 adapters + 266 engine), 916 lines of bash, and 2,111 lines of tests (160 tests). Python was the correct starting choice: fastest LLM SDK ecosystem, cheapest iteration, and the language LLMs write most fluently — which matters for a framework that modifies itself via MiniMax delegation.

Three structural weaknesses now cost real time and correctness:

1. **Hook cold-start latency** — `hooks.py` fires on every Claude Code tool call (Read, Edit, Write, Bash). Python interpreter boot costs ~60–150 ms per invocation. Across a 50-call session, that is 3–7 seconds of pure overhead, user-visible.
2. **Cross-platform path handling** — Bash + Python path logic broke the bootstrap on WSL UNC paths (`\\wsl.localhost\...`). Shell/Python split-brain compounds the problem.
3. **Type drift on a growing surface** — 1,092-line `delegate.py`, 575-line `self_verify.py`, 305-line `rules_engine.py`, and ~11k LOC with no mypy-strict boundary. Refactor risk grows linearly with size.

**Proposal:** First try the cheapest experiments (daemon spike, mypyc). If those fail the latency bar, selectively rewrite three hot, latency-sensitive components in Go. Leave everything LLM-facing, adapter-facing, or analytics-facing in Python. Reserve Rust for profiling-demanded bottlenecks only. Net effect: ~90% of the efficiency upside with ~1,100 lines of Go, without sacrificing agent self-editability or the Python LLM ecosystem.

---

## 2. Current State

### 2.1 Component inventory (accurate as of 2026-04-17)

```
scripts/ (9,031 LOC Python)
  delegate.py               1,092  MiniMax HTTP + task spec + parallel delegation + DAG
  auto_delegate.py            625  Standalone auto-routing (not used from Claude Code)
  self_verify.py              575  Pluggable syntax/quality verification
  backlog.py                  507  Markdown task backlog manager
  rsi.py                      429  CLI router (20 subcommands)
  hooks.py                    428  <- HOT: fires per Claude Code tool call
  universal_hook.py           423  Model-agnostic hook (opencode/shell path only)
  post_implementation.py      420  Module A: post-task capture
  framework_sync.py           374  Repo hygiene / self-update
  root_cause.py               368  5-Whys analysis
  self_optimization.py        357  Module C: prioritize and plan
  preflight_check.py          357  <- HOT: fires per edit (read-before-edit)
  calibration.py              336  Proof-wrong hypothesis tracking
  self_feedback.py            327  Module B: review and critique
  rules_engine.py             305  Declarative rule evaluator (.rsi/rules.yaml)
  setup.py                    300  One-time installer
  trust.py                    281  Worker trust scoring (per-task-type accept rate)
  metrics.py                  281  Value stream measurement engine
  ceremony.py                 269  Heijunka ceremony classification
  review_queue.py             266  Jidoka review gating
  dashboard.py                262  Andon board
  session_brief.py            227  Compound learning brief on init
  classify_file.py            156  File sensitivity classification
  colors.py                    65  Terminal color utilities (Windows-safe)
  __init__.py                   1

adapters/ (2,026 LOC Python)
  minimax.py                  462  MiniMax-M2.7 shell wrapper + tool module + instructions
  tool_wrappers.py            391  Universal RSISession enforcement layer
  base.py                     284  Rules engine + adapter registry
  claude_code.py              122  Claude Code settings.json + CLAUDE.md generator
  openai_agents.py             97  OpenAI API agent template
  langchain_adapter.py         97  LangChain @tool decorators
  aider.py                     56  Aider conventions
  cursor.py                    51  Cursor .cursorrules
  copilot.py                   45  GitHub Copilot instructions
  generic.py                   40  Generic adapter (shell + Python)
  shell_integrator.py         362  (in scripts/adapters/)

engine/ (266 LOC Python)
  protocol.py                 258  Task/result protocol definitions

Bash/PowerShell (916 LOC)
  ci_check.sh                 193
  bootstrap.sh                154
  checkpoint.sh               122
  git-hooks/pre-commit        110
  review.sh                    92
  setup.sh                     89
  init.sh                      83
  git-hooks/commit-msg         45
  install_hooks.sh             28

Tests (2,111 LOC, 160 tests)
```

**Total: ~14,300 LOC** (11,323 Python + 916 bash + 2,111 tests)

### 2.2 Call-frequency profile (must be measured in Phase 0)

| Component | Entry point | Est. calls/session | Latency sensitivity |
|---|---|---|---|
| `hooks.py` | `.claude/settings.json` PreToolUse/PostToolUse | 30–80 | **Critical** |
| `preflight_check.py` | Called from hooks.py and pre-commit hook | 5–20 | **High** |
| `classify_file.py` | Imported lazily inside hooks.py | Embedded in hook path | **High** |
| `rules_engine.py` | Imported lazily inside hooks.py | Embedded in hook path | **High** |
| `universal_hook.py` | opencode adapter only (NOT Claude Code) | 0 (if using Claude Code) | N/A for Claude |
| `delegate.py` | Manual CLI | 1–10 | Low (HTTP-bound) |
| `self_verify.py` | Post-change verification | 0–5 | Low |
| `metrics.py` / `dashboard.py` | On-demand | 0–1 | None (offline) |
| All adapters | Setup-time | 0–1 | None |

**Correction from v1:** Claude Code calls `hooks.py`, NOT `universal_hook.py`. The `universal_hook.py` is only used by the opencode/shell adapter path. The Go rewrite target is `hooks.py`.

Hot path is narrow: `hooks.py` -> lazy imports `classify_file.py` and `rules_engine.py`. Everything else is either human-triggered or network-bound.

### 2.3 Import chain analysis (hooks.py)

```
Top-level imports (always loaded):
  json, os, sys, datetime, pathlib          <- stdlib only, ~40ms

Lazy imports (loaded on first edit):
  scripts.classify_file                      <- +10ms (stdlib only)
  scripts.rules_engine                       <- +15ms (YAML parsing)

Total cold-start estimate: ~65-100ms
```

The lazy import pattern means the FIRST tool call is slowest. Subsequent calls in the same invocation don't re-import — but each hook invocation is a separate Python process, so every call pays the full cost.

---

## 3. Diagnosis — Where Python Hurts This Project

### 3.1 Hook cold-start (primary pain)

Every Claude Code tool call spawns `python3 scripts/hooks.py <action>`. Measured:

- `python3 -c "pass"` alone: ~25–40 ms
- With stdlib imports (`json`, `os`, `pathlib`, `datetime`): 40–60 ms
- With lazy imports on edit path (`classify_file`, `rules_engine`): 65–100 ms
- With disk I/O (session file, state file, FAIL-index, accepted reviews): 80–150 ms

A 50-tool session pays this 50 times. Even if hook logic runs in 1 ms, cold-start dominates.

### 3.2 Cross-platform path fragility

The bootstrap failed on:
```
mkdir: cannot create directory '//wsl.localhost': Read-only file system
```

Root cause: bash invoked with UNC pwd, Python inherited it, neither layer normalizes. Go's `path/filepath` handles UNC, WSL mounts, and Windows drives in one API.

### 3.3 Type drift at scale

No mypy-strict. 11k LOC with dynamic typing means:
- Task spec JSON shape drifts silently (partially fixed by rules_engine.py condition evaluator, but not enforced everywhere)
- Adapter return types vary
- Refactors require manual cross-file grep

Pydantic v2 solves most of this in-place (its validation core is Rust — free speedup, no rewrite).

### 3.4 Distribution friction

Python implies: compatible `python3` present, dependencies installable, venv resolved, bootstrap script that runs cross-platform. A single static Go binary for hooks sidesteps all of this for the latency-critical layer.

### 3.5 Bash/Python split

Nine bash/shell scripts (916 LOC) surround the Python core. Each is a platform-compatibility bug waiting to ship.

---

## 4. Design Principles

These are the rules the refactor must obey. Violations require explicit justification.

1. **Try cheap alternatives first.** Daemon spike and mypyc before Go. If they hit the latency bar, stop.
2. **Measure before rewriting.** No component moves out of Python until `time` + `-X importtime` confirm it is a bottleneck.
3. **Preserve self-editability.** LLMs write Python best. Code Claude/MiniMax must modify stays Python. Go layer must be minimal, rarely-edited, heavily tested.
4. **JSON over stdio is the only interop.** No FFI. No shared memory. Language boundaries are the hook protocol itself.
5. **Pydantic is the schema source of truth.** Go structs are codegen'd, never hand-written. One schema, two languages.
6. **Incremental, reversible migration.** Each component ports independently behind a feature flag. Old Python stays shipped until Go proves itself over N sessions.
7. **Cost must beat benefit.** Any rewrite under 2x speedup or under 100 ms saved per session fails the bar and stays Python.

---

## 5. Tier Map

### Tier 0 — Try before rewriting (cheapest experiments first)

| Experiment | Est. effort | Expected latency | If it works |
|---|---|---|---|
| **Daemon hook** — persistent Python process, Unix socket | 1 day | ~5-15 ms (no cold start) | Skip Go entirely |
| **mypyc compile** — compile hooks.py to C extension | 0.5 day | ~20-40 ms (faster boot) | May be enough to defer Go |
| **nuitka standalone** — compile to binary | 0.5 day | ~10-30 ms | Alternative to Go |

**Try these in Phase 0a.** If daemon gets hooks under 15ms, the Go rewrite is unnecessary.

### Tier 1 — Rewrite in Go (only if Tier 0 fails)

| Component | Current LOC | Target LOC (Go) | Expected gain |
|---|---|---|---|
| `hooks.py` | 428 | ~400 | 100 ms -> <5 ms per invocation |
| `preflight_check.py` | 357 | ~350 | Same; runs per edit |
| `classify_file.py` | 156 | ~150 (bundled) | Merged into `rsi-hook` binary |
| `rules_engine.py` condition evaluator | 305 | ~250 (subset) | Core rule evaluation only |
| Path normalization library | N/A | ~200 | Permanent fix for UNC/WSL/Windows |
| **Total Go** | — | **~1,350 LOC** | **3-7 s saved per session** |

**Important: rules_engine.py portability.** The declarative rules system (`.rsi/rules.yaml`) was added in v2.2. The Go port must either:
- Port the condition evaluator to Go (adds ~250 LOC, adds complexity)
- Keep rule evaluation in Python, called from Go (defeats cold-start benefit)
- Compile rules to a Go switch statement at build time (fastest, but loses runtime editability)

**Recommendation:** Port the condition evaluator to Go. The evaluator is ~100 lines of logic (the rest is parsing). Rules YAML is parsed once, cached. This preserves "edit YAML not code" while getting Go speed.

### Tier 2 — Rewrite in Rust (deferred; only if profiling demands)

| Component | Condition to trigger |
|---|---|
| Parallel delegation dispatcher | When >10 concurrent MiniMax calls with streaming become routine, AND Python asyncio profiling shows contention |
| Content-addressed memory hashing | When `.memory/` exceeds 1 GB and hashing appears in hot traces |
| JSON schema validation | **Already free via pydantic v2 (Rust core).** Just upgrade. |

### Tier 3 — Stay in Python (adapters, analytics, LLM-heavy, glue)

| Component | Why Python keeps winning |
|---|---|
| `adapters/*.py` (10 files) | LLM SDKs Python-native; streaming, caching, retries |
| `delegate.py` (1,092 LOC) | HTTP-bound; Python overhead invisible |
| `trust.py`, `session_brief.py` | Analytics; read-only, offline |
| `metrics.py`, `dashboard.py` | pandas/duckdb/plotly ecosystem unmatched |
| `self_verify.py`, `self_feedback.py`, `self_optimization.py` | LLM-orchestration, complexity dominates speed |
| `rsi.py` CLI router | Thin dispatch. Python is fine. |
| `review_queue.py` | Human-triggered UX; latency invisible |
| `auto_delegate.py` | Standalone mode only (not called from Claude Code) |

---

## 6. Target Architecture

```
rsi-framework/
+-- bin/                              # Shipped binaries, per-platform
|   +-- rsi-hook-linux-amd64
|   +-- rsi-hook-linux-arm64
|   +-- rsi-hook-darwin-amd64
|   +-- rsi-hook-darwin-arm64
|   +-- rsi-hook-windows-amd64.exe
|   +-- SHA256SUMS
|
+-- go/                               # Go source (Tier 1, if Tier 0 fails)
|   +-- go.mod
|   +-- cmd/
|   |   +-- rsi-hook/main.go          # Replaces hooks.py + preflight + classify + rules eval
|   +-- internal/
|   |   +-- classify/                 # From classify_file.py
|   |   +-- rules/                    # Condition evaluator from rules_engine.py
|   |   +-- pathsafe/                 # UNC/WSL/Windows normalization
|   |   +-- schema/                   # Codegen'd from pydantic models
|   |   +-- protocol/                 # JSON hook protocol
|   +-- Makefile
|
+-- scripts/                          # Python orchestrator (Tier 3, unchanged)
|   +-- rsi.py                        # CLI router
|   +-- delegate.py                   # MiniMax delegation + parallel + DAG
|   +-- trust.py                      # Worker trust scoring
|   +-- session_brief.py              # Compound learning on init
|   +-- rules_engine.py               # Declarative rules (Python fallback)
|   +-- adapters/
|   +-- metrics.py, dashboard.py
|   +-- self_verify.py, self_feedback.py, self_optimization.py
|   +-- review_queue.py
|
+-- engine/
|   +-- protocol.py                   # Pydantic v2 -- source of truth for schemas
|
+-- .rsi/
|   +-- rules.yaml                    # Declarative enforcement rules
|   +-- architecture.yaml             # File sensitivity + trust config
|   +-- config.yaml                   # hook_backend: python | go | daemon
|   +-- tasks/
```

### 6.1 Data flow

```
Claude Code  --stdin JSON-->  rsi-hook (Go, <5 ms)
                                  |
                                  +-- loads .rsi/rules.yaml (cached after first read)
                                  +-- reads .memory/ state files (cached per invocation)
                                  +-- pure-Go decision (allow/block/warn)
                                  |       +-- exit 0/1 + stdout message
                                  |
                                  +-- if delegation needed:
                                          subprocess python3 scripts/rsi.py delegate
                                                      |
                                                      +-- HTTP --> MiniMax API
```

Alternative (if daemon spike succeeds):
```
Claude Code  --stdin JSON-->  rsi-hookd (Python, persistent, <15 ms)
                                  |
                                  +-- already running, no cold start
                                  +-- same logic as hooks.py
                                  +-- exit 0/1 + stdout message
```

### 6.2 Schema flow

```
engine/protocol.py (pydantic v2 models, source of truth)
        |
        +-- Python: direct import, validation free
        |
        +-- codegen (quicktype / datamodel-code-generator):
                |
        go/internal/schema/*.go (structs regenerated on CI)
```

---

## 7. Interop Contract

All inter-language communication is **JSON over stdin/stdout/args + exit codes.** No shared libraries, no FFI, no sockets (unless daemon path chosen).

### 7.1 Hook protocol (unchanged externally)

```json
// stdin to rsi-hook
{
  "tool_input": {
    "file_path": "/abs/path/to/file.py"
  }
}

// stdout from rsi-hook (exit 0 = allow, non-zero = block)
// Plain text messages, not JSON (matches current hooks.py behavior)
[RSI] BLOCKED: 'src/api.py' not read. Read it first.
```

This is already the contract Claude Code enforces. Porting to Go is invisible to Claude.

### 7.2 Delegation protocol (Go hook -> Python orchestrator)

When the Go hook needs to trigger Python work:

```
rsi-hook  --exec-->  python3 scripts/rsi.py <subcommand> --json '...'
           <--stdout JSON--
```

Same pattern. No new infrastructure.

---

## 8. Migration Sequence

Each phase is independently shippable and reversible. Python original stays until replacement proves itself.

### Phase 0 — Measurement & baseline (0.5 day)

**Goal:** Replace hypothesis with data. No code changes.

Tasks:
1. Time `hooks.py` across 10 real events: `time python3 scripts/hooks.py pre-edit < sample.json`
2. Run `python3 -X importtime scripts/hooks.py 2> import.log` — identify top 10 import costs.
3. Same for `preflight_check.py` and `classify_file.py`.
4. Count actual hook invocations from a real 1-hour session.
5. Measure MiniMax delegation accept rate (self-editability baseline).
6. Write `docs/baseline-metrics.md` with numbers.

**Exit criterion:** Measured latency >= 80 ms p50 on hooks. If lower, skip to Phase 1 (Pydantic) and Phase 6 (Python hardening) only.

### Phase 0a — Daemon spike (1 day)

**Goal:** Test if a persistent Python process eliminates cold-start without Go.

Tasks:
1. Write `scripts/hookd.py` — Unix socket server, keeps hooks.py loaded in memory.
2. Write `scripts/hook_client.sh` — thin shell script that sends JSON to socket.
3. Update `.claude/settings.json` to call `hook_client.sh` instead of `python3 hooks.py`.
4. Measure latency: first call (process already running) and steady-state.

**Exit criterion:** If daemon p50 <15 ms, defer Go entirely. Proceed to Phase 1 + Phase 6.

Also try **mypyc** (`mypyc scripts/hooks.py`) — if compiled extension gets <30 ms, that may be sufficient.

### Phase 1 — Pydantic v2 migration (2 days)

**Goal:** Free Rust speedup + type safety, zero rewrite cost.

Tasks:
1. Audit `engine/protocol.py` and all task spec shapes.
2. Migrate to pydantic v2 BaseModel.
3. Add mypy strict config scoped to `engine/` and `scripts/rsi.py`.
4. Replace manual JSON validation in `delegate.py`, `review_queue.py`, `hooks.py` with pydantic validators.

**Exit criterion:** `mypy --strict engine/ scripts/rsi.py` passes. All 160 tests green.

### Phase 2 — Go scaffolding (2 days, skip if daemon succeeded)

**Goal:** Empty but buildable Go subtree. Prove cross-compilation works.

Tasks:
1. `go mod init github.com/VincentOduro/rsi-framework/go`.
2. Stub `cmd/rsi-hook/main.go` that reads JSON, echoes it, exits 0.
3. `Makefile` cross-compiles 5 target platforms.
4. CI job: build all 5 binaries, upload as artifacts, SHA256SUMS.
5. `pathsafe` package: port UNC/WSL/Windows normalization with table-driven tests.

**Exit criterion:** `make all` produces 5 working binaries. `pathsafe` tests pass on 3 OSes in CI.

### Phase 3 — `rsi-hook` port (5 days, skip if daemon succeeded)

**Goal:** Replace `hooks.py` with Go binary.

Tasks:
1. Codegen Go structs from pydantic models. Wire into CI.
2. Port `hooks.py` logic including `classify_file.py` and `rules_engine.py` condition evaluator.
3. Port delegation gate logic (read `.memory/reviews/accepted/`, `.rsi/overrides/`).
4. Feature flag: `.rsi/config.yaml` key `hook_backend: python | go | daemon`. Default `python`.
5. Dogfood: set `hook_backend: go` in this repo. Run >= 1 week.
6. Collect latency telemetry side-by-side.

**Exit criterion:**
- Go hook latency p95 <10 ms (target <5 ms).
- Zero behavior diff on a 100-event regression fixture.
- >= 1 week dogfooding with no regressions.
- MiniMax commit accept rate unchanged (self-editability preserved).

### Phase 4 — `rsi-preflight` merge (3 days)

**Goal:** Merge `preflight_check.py` into the `rsi-hook` binary. Same pattern as Phase 3.

**Exit criterion:** Same bar as Phase 3, scoped to preflight.

### Phase 5 — Bash consolidation (2 days)

**Goal:** Retire bash scripts where Go binary or Python CLI covers the need.

Tasks:
1. Audit each bash script. Classify: (a) replaceable by Go binary, (b) replaceable by `rsi.py` subcommand, (c) must remain bash.
2. Port (a) and (b). Keep (c) minimal.
3. `scripts/install.py` replaces most of `bootstrap.sh` logic.

Expected remaining bash: `bootstrap.sh` only (runs pre-install, can't use Go or Python until they're installed).

**Exit criterion:** Bash footprint shrinks from 9 scripts (916 LOC) to 1 script (<100 LOC).

### Phase 6 — Python hardening (3 days)

**Goal:** Fix remaining Python pain without porting.

Tasks:
1. mypy strict on entire `scripts/` tree.
2. Audit `subprocess` calls. Replace `shell=True` with list-form args.
3. Add `ruff` + `ruff format` with strict config.
4. Add pre-commit hook running mypy, ruff, pytest.

**Exit criterion:** All Python gates green. Pre-commit enforces them.

### Phase 7 — Evaluate Tier 2 (1 day profiling)

**Goal:** Decide if Rust is earned.

Tasks:
1. Profile `delegate.py` under peak load (simulated N=20 parallel MiniMax calls).
2. If asyncio p99 acceptable, stop. No Rust.
3. If not, design Rust parallel dispatcher in a separate plan doc.

**Exit criterion:** Explicit yes/no recorded in `docs/tier2-decision.md`.

---

## 9. Build & Distribution

### 9.1 Go build

```makefile
# go/Makefile
TARGETS := linux-amd64 linux-arm64 darwin-amd64 darwin-arm64 windows-amd64

.PHONY: all
all: $(TARGETS:%=../bin/rsi-hook-%) 
	cd ../bin && sha256sum rsi-* > SHA256SUMS

../bin/rsi-hook-%:
	GOOS=$(word 1,$(subst -, ,$*)) GOARCH=$(word 2,$(subst -, ,$*)) \
	  go build -trimpath -ldflags="-s -w" -o $@ ./cmd/rsi-hook
```

### 9.2 Distribution strategy

**A. Check binaries into git.** Fastest bootstrap. Acceptable if <20 MB total. Use during initial rollout.
**B. GitHub Releases.** Clean repo. Bootstrap downloads matching binary. Use once binaries stabilize.
**C. Build-on-install.** Requires Go toolchain. Rejected: violates "fast bootstrap" goal.

Recommendation: **A** during rollout, **B** for stable releases.

### 9.3 Version pinning

`bin/VERSION` records the Git SHA binaries were built from. `rsi-hook --version` prints it. CI rejects PRs that change Go source without rebuilding binaries.

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Go binary behavior diverges from Python original | Medium | High | 100-event regression fixture; both backends must produce identical output. |
| Schema codegen drifts (Python vs Go) | Medium | High | CI step: regen Go structs; fail build if diff vs checked-in version. |
| **Rules engine portability** | **High** | **High** | **Port condition evaluator to Go (~250 LOC). Parse rules.yaml once, cache. Keep "edit YAML not code" benefit.** |
| **Delegation gate state complexity** | **Medium** | **High** | **Go binary must read .memory/reviews/accepted/*.md and .rsi/overrides/*.json. Port the glob+read+match logic explicitly.** |
| Cross-compiled binary breaks on untested OS | Medium | Medium | GitHub Actions matrix: smoke test on linux/macos/windows runners. |
| LLM-editability regression on Go code | Low | Medium | Keep Go layer <1.5k LOC. Treat as infrastructure. Heavy comments. Tests as spec. |
| Rewrite bleeds scope into Tier 3 components | High | Medium | This doc is the boundary. Violations require a new proposal. |
| Daemon approach makes Go unnecessary | Medium | None | This is a success, not a risk. Phase 0a gates the whole plan. |
| Effort > payoff if framework has few users | Medium | Low | Phase 0 measurement gates everything. No Phase 1+ until numbers justify. |

---

## 11. Success Metrics

All measured, all comparable to Phase 0 baseline.

| Metric | Baseline (measure Phase 0) | Target |
|---|---|---|
| Hook p50 latency | ~80-100 ms (hypothesized) | **<5 ms** (Go) or **<15 ms** (daemon) |
| Hook p99 latency | ~150-200 ms (hypothesized) | **<15 ms** (Go) or **<30 ms** (daemon) |
| Per-session hook overhead (50 calls) | ~4-7 s | **<300 ms** (Go) or **<750 ms** (daemon) |
| Bootstrap failures on WSL/UNC paths | Reproducible | **Zero** |
| Lines of bash | 9 scripts, 916 LOC | **1 script, <100 LOC** |
| Lines with `# type: ignore` | Unknown | **Zero in engine/** |
| mypy strict passing | No | **Yes** |
| Go LOC (if Go path taken) | 0 | **<1,350** |
| Self-edit success rate | Measure in Phase 0 | **No regression** |
| Test count | 160 | **>= 160 (no test loss)** |

Last metric is the deal-breaker. If Go layer causes self-editability to drop (MiniMax commit accept rate decreases), the plan failed regardless of speed wins.

---

## 12. Open Questions

1. **Daemon hooks (Phase 0a) — likely the winning path.** Persistent Python process via Unix socket achieves similar latency gains without Go. Cheapest experiment. Try first. Needs Windows named pipe variant.
2. **mypyc / nuitka compile path.** Compiling hooks.py to C extension could get cold start to ~20 ms. Worth one day of experimentation alongside daemon spike.
3. **Go version floor.** Target Go 1.22+ (generics stable, `slog`). Lock explicitly.
4. **Windows/PowerShell surface.** `setup.ps1` exists. Does the framework actually support Windows-native (non-WSL) users? If no, drop it and simplify.
5. **Binary signing.** For a framework that runs on every tool call, supply chain integrity matters. Cosign? Sigstore? Decide before wide distribution.
6. **Telemetry opt-in.** Measuring success metrics requires telemetry. Design opt-in contract before Phase 3.
7. **Rules engine in Go.** The condition evaluator supports `and`, `or`, `not`, `==`, `!=`, `in`, string literals, parentheses, context variable lookup. Porting this to Go is ~250 LOC but must be tested against all existing rules. Alternative: compile rules to Go switch at build time.

---

## 13. Appendix — Why Not Just Rewrite Everything?

Tempting. Rejected because:

- **Self-editability is the framework's core value.** MiniMax writes Python. MiniMax cannot write Go. If the framework can't be delegated to MiniMax, the delegation system (the framework's defining feature) breaks.
- **LLM ecosystem (adapters) is Python-first.** Replicating 10 adapters in Go = weeks of work for zero user benefit.
- **Analytics (pandas/duckdb/plotly) has no Go peer.**
- **Delegation system is 1,092 LOC of HTTP+JSON+filesystem logic.** Python overhead is invisible (network-bound). Porting to Go saves zero user-visible time.
- **Cost of full rewrite: 8-14 weeks. Cost of this plan: ~4 weeks (Go path) or ~2 weeks (daemon path).** Payoff ratio is 3-7x better.
- **Big-bang rewrites violate the framework's own Toyota principles.** This plan is Kaizen-shaped: incremental, reversible, measured at each step.

The right mental model: **Python is the brain. Go is the reflexes. Rust, if ever, is a specialized organ.** Keep the brain intact.

---

**Next concrete action:** Execute Phase 0. Produce `docs/baseline-metrics.md`. Then Phase 0a (daemon spike). Decide from data whether Go is needed at all.
