# Phase E0a Decision — Daemon Spike

**Date:** 2026-04-17

## Measured

| Approach | p50 Latency | vs Direct hooks.py (189ms) |
|---|---|---|
| Direct hooks.py (baseline) | **189ms** | — |
| Python daemon + Python client | **250ms** | Worse (+61ms) |
| Python daemon + PowerShell client | **394ms** | Much worse (+205ms) |
| Python daemon + bash hook_client.sh | **291ms** | Worse (+102ms) |
| Python daemon + raw bash /dev/tcp (no parsing) | **59ms** | Better (-130ms) |
| Bash boot alone | **72ms** | — |

## Analysis

The daemon itself works. It responds in ~5ms. The problem is the **client**.

Every client option available on this machine requires booting an interpreter:
- Python client: 180ms boot + 70ms socket = 250ms
- Bash client: 72ms boot + 220ms (script overhead: cat, grep, sed) = 291ms
- PowerShell client: 350ms boot + 44ms = 394ms
- Raw bash /dev/tcp (no parsing): 72ms boot + socket = 59ms — but can't parse JSON responses

The raw /dev/tcp test proves the daemon is fast (59ms total including bash boot).
But a **usable** client that parses JSON responses and sets exit codes correctly
pushes the latency above the direct Python approach.

## The fundamental problem

On this machine (Windows + WSL), every process spawn costs 60-180ms regardless
of language. The daemon eliminates Python boot on the SERVER side but not on
the CLIENT side. You need a client that:
1. Boots in <5ms (compiled binary, not interpreted)
2. Connects to TCP socket
3. Sends JSON
4. Parses JSON response
5. Exits with correct code

That's a compiled binary. Go or Rust. ~50 lines of code.

## Decision

**DAEMON CONCEPT VALIDATED but NEEDS COMPILED CLIENT.**

The daemon is the right architecture — it reduces server-side latency from 189ms
to 5ms. But the client must be a compiled binary to capture that benefit.

Options:
1. **Write a 50-line Go client** → daemon + Go client = ~5ms + 3ms = ~8ms total
2. **Write the full Go hook binary** → ~3ms total, no daemon needed, simpler
3. **Try mypyc on hook_client.py** → might get client to ~30ms

Option 2 (full Go binary) is simpler. One binary, no daemon lifecycle, no socket,
no process coordination. The daemon adds complexity (start/stop/crash recovery)
for marginal benefit over a standalone Go binary.

**Recommendation: Go binary (Track B).** The daemon was the right experiment to run.
It proved the daemon architecture works, but the compiled-client requirement makes
a standalone Go binary the cleaner solution.

## Next phase

Phase E1 (Pydantic v2 migration) — do this regardless of Go decision.
Then Phase E2 (Go scaffolding).

## Preserved artifacts

- `scripts/hookd.py` — working daemon, kept for future use or non-Windows platforms
- `scripts/hook_client.py` — Python client (fallback when daemon + compiled client unavailable)
- `scripts/hook_client.sh` — bash client (fallback)
