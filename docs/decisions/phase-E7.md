# Phase E7 Decision — Tier 2 Parallel Dispatcher Evaluation

**Date:** 2026-04-17
**Question:** Does `scripts/delegate.py`'s `delegate_parallel` (ThreadPoolExecutor over 20 concurrent MiniMax calls) need a Rust rewrite?

## Method

Mocked the OpenAI client in `delegate.call_worker` so each "API call" sleeps for a fixed 8.0s — the low end of observed real MiniMax latency (7.8s – 52.5s across the delegations this session). Benchmark is `.rsi/e7_benchmark.py`, 3 sweeps:

1. **Full parallelism:** N tasks with N workers, N ∈ {1, 2, 5, 10, 20}
2. **Bounded pool:** 20 tasks with pool size ∈ {1, 2, 5, 10, 20}
3. **Zero-latency:** 20 tasks with 0-duration fake to isolate dispatcher startup cost

All measurements on native Windows (Python 3.13.3).

## Measured

### Sweep 1 — full parallelism (N tasks, N workers)

| N | wall_s | ideal_s | efficiency | gil_ratio | dispatch_skew_ms |
|---|---|---|---|---|---|
| 1 | 8.00 | 8.00 | **99.98%** | 0.000 | 0.0 |
| 2 | 8.00 | 8.00 | 99.99% | 0.000 | 0.1 |
| 5 | 8.00 | 8.00 | 99.98% | 0.000 | 0.6 |
| 10 | 8.00 | 8.00 | 99.98% | 0.000 | 0.7 |
| 20 | 8.00 | 8.00 | **99.96%** | 0.000 | **2.3** |

### Sweep 2 — bounded pool (20 tasks, varying pool)

| pool | wall_s | ideal_s | efficiency |
|---|---|---|---|
| 1 | 160.01 | 160.00 | 99.99% |
| 2 | 80.01 | 80.00 | 99.99% |
| 5 | 32.00 | 32.00 | 99.99% |
| 10 | 16.00 | 16.00 | 99.98% |
| 20 | 8.00 | 8.00 | 99.96% |

### Sweep 3 — dispatcher-only overhead

20 tasks through a 20-worker pool with zero per-call latency:

| samples (ms) | median | per-task |
|---|---|---|
| [1.8, 1.7, 2.1, 1.5, 1.3] | **1.7ms** | **0.08ms** |

## Interpretation

- **Efficiency is at the measurement floor.** 99.96% at N=20 means the dispatcher adds at most 0.04% of wall time — ~3ms out of 8000ms per call. Below the noise threshold of the benchmark.

- **GIL pressure is zero.** `process_time / wall_time = 0.000` across every sweep. Every thread spends its time waiting on the (mocked) socket — the GIL is released inside `time.sleep`, and it would be released identically inside a real `socket.recv`. No thread ever contends for Python bytecode execution time, because there's no bytecode executing during the wait.

- **Dispatcher startup is 0.08ms per task.** Submitting 20 tasks and joining them takes 1.7ms total when the task is a no-op. At realistic MiniMax latencies (8000ms+), that's 0.002% of one call's runtime.

- **Scaling is linear up to 20 concurrent.** Sweep 2 confirms `wall ≈ ideal` at every pool size — no pathological slowdown as the pool grows. The scan stopped at 20 because the plan said so, not because any bottleneck appeared.

## Why Python threading wins here

The workload is **pure I/O wait**. MiniMax calls spend >99.9% of their time in a blocking socket read. During that read, CPython releases the GIL. Thirty waiting threads cost the same GIL-time as one. Rust's `tokio` or Go's goroutines would look identical in this regime — you can't beat "release the GIL and wait for the network."

The only scenario where Python loses to a compiled-language dispatcher:

| Scenario | What would change | Does it apply? |
|---|---|---|
| CPU-bound post-processing between calls | GIL becomes a ceiling | **No** — apply runs post-review, not inline |
| Thousands of concurrent tasks | Thread-per-task memory pressure | **No** — plan specifies 20, and the current default is 3 |
| Sub-millisecond call latency | Startup cost dominates | **No** — real call is 8000ms |
| Pinning to a specific CPU core per worker | Thread scheduling overhead | **No** — no such requirement |

None of those apply to RSI delegation as designed.

## Decision

**NO Rust dispatcher.** The Python `ThreadPoolExecutor` is not the bottleneck and cannot be meaningfully beaten for this workload. If any future scenario in the table above appears, re-run this benchmark and re-evaluate — but don't write a Rust dispatcher preemptively.

Separately: the `max_workers` default in `delegate_parallel` is 3 (`scripts/delegate.py:1158`). That's conservative and was chosen before measurement. Based on Sweep 2, a default of 5 or 10 would cut parallel delegation wall time by 40–66% with no observed downside. Worth a small follow-up, but still inside Python.

## Artifacts

- `.rsi/e7_benchmark.py` — reproducible benchmark (not tracked; one-shot tool)
- Raw output captured in this doc

## Follow-ups considered and rejected

- Real-API sweep (20 concurrent MiniMax calls): would cost $5–20 for no new information. The bottleneck question was answered by the mock.
- asyncio rewrite: would perform identically for pure-wait I/O. ThreadPoolExecutor already gives linear scaling.
- Process pool: only useful for CPU-bound work, which this isn't.
