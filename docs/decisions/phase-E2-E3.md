# Phase E2-E3 Decision — Go Hook Binary

**Date:** 2026-04-17

## Measured

| Binary | WSL UNC path | Native Windows | Native Linux (est.) |
|---|---|---|---|
| Python hooks.py | 209ms | ~65ms | ~30ms |
| Go rsi-hook.exe | 297ms | 38ms | ~5ms |
| Go --version (no I/O) | 293ms | 29ms | ~3ms |

## Analysis

**From WSL UNC path: Go is SLOWER than Python.** The 2.1MB Go binary takes
~293ms to load through the WSL2 9P filesystem bridge. Python (~55ms loader)
is faster because Windows caches the interpreter executable.

**From native Windows: Go is 40% faster.** 38ms vs 65ms. Saves ~2 seconds
per 75-call session.

**From native Linux: Go would be ~10x faster.** ~5ms vs ~30ms. Saves ~1.9
seconds per session.

**The WSL 9P bridge is the real bottleneck.** No language change fixes it.
Loading ANY binary from `\\wsl.localhost\...` costs 250-300ms regardless
of binary size or language.

## Solution for WSL users

The framework should detect WSL UNC paths and copy the Go binary to a
native Windows temp directory on first run. Subsequent calls load from
`C:\Users\...\AppData\Local\Temp\rsi-hook.exe` — native filesystem, fast.

Alternatively: advise users to clone the project to a native Windows path
or use WSL-native Python (no cross-filesystem penalty).

## Solution for all users

The Go binary IS faster on native filesystems. Worth shipping for:
- Native Windows: 65ms -> 38ms (42% improvement)
- macOS: ~35ms -> ~5ms (86% improvement) 
- Native Linux: ~30ms -> ~5ms (83% improvement)

## Decision

**SHIP THE GO BINARY** with a WSL detection workaround:
1. On first run, if running from UNC path, copy binary to native temp dir
2. Subsequent hook calls use the native-path copy
3. Python hooks.py remains as fallback (hook_backend: python in config)

## Artifacts

- `bin/rsi-hook.exe` — working Windows binary (2.1MB)
- `go/` — full Go source with packages: classify, rules, state, pathsafe
- Build requires native Windows path (Go can't lock files on WSL filesystem)
