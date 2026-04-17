# Phase E0 — Baseline Metrics

**Date:** 2026-04-17
**Machine:** Windows 11 + WSL2 Ubuntu, Python 3.13.3
**Repo:** rsi-framework (the framework itself, not a target project)
**Working directory:** `\\wsl.localhost\Ubuntu\home\ajeem\rsi-framework` (WSL UNC path)

---

## 1. Hook Latency (hooks.py)

Measured: `time python3 scripts/hooks.py <action> < sample_event.json` x10

### From WSL UNC path (actual Claude Code working directory)

| Action | p50 | p95 | p99 | Min | Max |
|---|---|---|---|---|---|
| pre-read | **185ms** | 216ms | 217ms | 181ms | 217ms |
| pre-edit | **188ms** | 212ms | 212ms | 180ms | 212ms |
| pre-bash | **191ms** | 221ms | 221ms | 182ms | 221ms |
| post-edit | **191ms** | 223ms | 223ms | 184ms | 223ms |

**Median across all actions: ~189ms**

### From native Windows path (C:\)

| Action | p50 | Notes |
|---|---|---|
| pre-read | **153ms** | Script still on WSL path |

### Python bare startup comparison

| Context | Time |
|---|---|
| `python -c "pass"` from native Windows | **53ms** |
| `python3 -c "pass"` from WSL UNC path | **180ms** |
| `python3 -c "import json,os,sys,datetime,pathlib"` from WSL UNC | **190ms** |
| `hooks.py pre-read` from WSL UNC | **185ms** |

**Key finding:** Python interpreter boot from WSL UNC path = 180ms.
hooks.py logic adds ~5-10ms. The ENTIRE cost is interpreter startup +
WSL-to-Windows file bridge overhead (~130ms penalty vs native Windows).

---

## 2. Import Chain Analysis

Profiled: `python -X importtime -c "import scripts.hooks"`

| Module | Cumulative (us) | Self (us) | Notes |
|---|---|---|---|
| scripts.hooks (total) | **62,808** | 10,555 | 63ms total import chain |
| json | 26,252 | 2,083 | json.decoder -> re = 21ms |
| pathlib | 19,317 | 1,805 | pathlib._abc + _local |
| re | 21,479 | 1,994 | Used by json.decoder |
| enum | 15,149 | 2,456 | Used by pathlib |
| scripts (package) | 4,876 | 4,876 | Package __init__ |
| site | 12,169 | 2,840 | Python startup |

**Key finding:** Import chain = 63ms. But `python -c "pass"` already
costs 53-180ms depending on path context. The import chain is ~35% of
the from-native cost and ~33% of the from-WSL cost.

---

## 3. Component Latencies

| Component | Median | Notes |
|---|---|---|
| preflight_check.py --report | **195ms** | Reads state file + git |
| classify_file.py <file> | **185ms** | Parses architecture.yaml |
| rules_engine.py (import + init) | **181ms** | Parses rules.yaml |

All components within 180-200ms — dominated by Python startup, not logic.

---

## 4. Session Call Count

Estimated from production sessions (Nyquist project):
- Read calls per session: ~30-50
- Edit calls per session: ~15-30
- Bash calls per session: ~10-20
- **Total hook invocations: ~55-100 per session**

Each edit triggers BOTH pre-edit AND post-edit hooks = 2 Python processes.

**Estimated per-session hook overhead:** 55-100 calls x 189ms = **10.4-18.9 seconds**

This is worse than STACK_EVOLUTION.md hypothesized (5-7s). The WSL UNC
path penalty was not accounted for.

---

## 5. MiniMax Accept Rate

No delegation history in this repo (the framework itself). From Nyquist
production session:
- 16 delegations total
- Accepted: ~12 (75%)
- Rejected: ~2
- Failed (syntax/JSON): ~2
- Revision needed: ~3 of the accepted

**Self-editability baseline: ~75% first-pass accept rate on real project.**

---

## 6. Cost Breakdown

Where time goes in a 75-call session:

| Component | Per-call | x Calls | Total |
|---|---|---|---|
| Python interpreter boot | 53ms | 75 | 4.0s |
| WSL UNC path penalty | 130ms | 75 | **9.8s** |
| Import chain (json, pathlib, re) | 63ms | - | (included in boot) |
| Hook logic (state reads, classify, rules) | 5-10ms | 75 | 0.5s |
| **Total** | ~189ms | 75 | **14.2s** |

**The WSL path penalty alone = 9.8 seconds per session.**
**Hook logic = 0.5 seconds per session.**

---

## 7. Decision Gate

| Criterion | Threshold | Measured | Result |
|---|---|---|---|
| Hook p50 >= 80ms | Proceed to E0a | **189ms** | **PROCEED** |
| WSL path penalty significant | Investigate | **130ms/call** | **Major factor** |

### Observations

1. **The problem is NOT hook logic.** Hook code runs in 5-10ms. The problem
   is spawning a Python process per tool call from a WSL UNC path.

2. **A Go binary would fix the WSL penalty too** — Go binary boot is <5ms
   regardless of working directory.

3. **A Python daemon would fix the spawn cost** — process already running,
   no boot or import. But the daemon still lives on the WSL filesystem, so
   socket I/O may still have UNC overhead.

4. **The cheapest fix might be: move the project to a native Windows path.**
   But that's a workflow constraint, not a framework fix.

### Recommendation

**Proceed to Phase E0a (daemon spike).** The daemon eliminates process
startup entirely. If socket I/O over WSL is fast (<5ms), daemon wins.
If not, the Go binary is the correct solution because it fixes both
startup AND cross-platform path handling.

---

**Next action:** Phase E0a — build hookd.py daemon, measure socket latency over WSL.
