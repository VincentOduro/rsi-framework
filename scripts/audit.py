#!/usr/bin/env python3
"""audit — Proactive infrastructure gap detection.

Runs the project's configured tooling (ruff, mypy, pytest collection,
pre-commit hook syntax, architecture.yaml field consumption) against
the full tree and reports gaps in one pass. Designed to surface
latent issues that would otherwise appear incrementally across the
first dozen commits of a project.

Usage:
    python3 scripts/audit.py                # Full audit, human output
    python3 scripts/audit.py --json         # Machine-readable
    python3 scripts/audit.py --strict       # Exit 1 if any gap found
    python3 scripts/audit.py --category lint   # Run one category only
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT_BOOTSTRAP = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
ARCHITECTURE_FILE = PROJECT_ROOT / ".rsi" / "architecture.yaml"
PYPROJECT_FILE = PROJECT_ROOT / "pyproject.toml"
GIT_HOOKS_DIR = PROJECT_ROOT / "scripts" / "git-hooks"
DELEGATE_PY = PROJECT_ROOT / "scripts" / "delegate.py"

# Optional colors import
try:
    from scripts.colors import green, red, yellow, bold
except Exception:
    def green(msg: str) -> str:  # noqa: D103
        return msg

    def red(msg: str) -> str:  # noqa: D103
        return msg

    def yellow(msg: str) -> str:  # noqa: D103
        return msg

    def bold(msg: str) -> str:  # noqa: D103
        return msg


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with standard audit settings."""
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        cwd=PROJECT_ROOT,
        timeout=120,
    )


def _tool_on_path(name: str) -> bool:
    """Check whether a CLI tool is available on PATH."""
    try:
        subprocess.run(
            [name, "--version"],
            capture_output=True,
            timeout=10,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _audit_lint() -> dict:
    """Run ruff check on the full tree."""
    if not _tool_on_path("ruff"):
        return {
            "category": "lint",
            "ok": True,
            "findings": [],
            "summary": "ruff: not installed",
            "skipped": True,
            "skip_reason": "ruff not installed",
        }

    result = _run(["ruff", "check", "."])
    if result.returncode == 0:
        return {
            "category": "lint",
            "ok": True,
            "findings": [],
            "summary": "ruff: clean",
            "skipped": False,
            "skip_reason": None,
        }

    lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip()]
    capped = lines[:20]
    # ruff output lines include "Found N errors." etc.; try to count files.
    files = set()
    for ln in lines:
        parts = ln.split(":", 1)
        if parts and parts[0] and not parts[0].startswith(" "):
            files.add(parts[0])
    file_count = len(files)
    summary = f"ruff: {len(lines)} findings across {file_count} file(s)"
    return {
        "category": "lint",
        "ok": False,
        "findings": capped,
        "summary": summary,
        "skipped": False,
        "skip_reason": None,
    }


def _audit_type() -> dict:
    """Run mypy on the paths listed in pyproject.toml."""
    if not PYPROJECT_FILE.exists():
        return {
            "category": "type",
            "ok": True,
            "findings": [],
            "summary": "mypy: pyproject.toml not found",
            "skipped": True,
            "skip_reason": "pyproject.toml not found",
        }

    try:
        import tomllib
    except ImportError:
        return {
            "category": "type",
            "ok": True,
            "findings": [],
            "summary": "mypy: tomllib unavailable (needs Python 3.11+)",
            "skipped": True,
            "skip_reason": "tomllib unavailable (needs Python 3.11+)",
        }

    with PYPROJECT_FILE.open("rb") as f:
        try:
            pyproject = tomllib.load(f)
        except Exception as exc:
            return {
                "category": "type",
                "ok": True,
                "findings": [],
                "summary": f"mypy: could not parse pyproject.toml ({exc})",
                "skipped": True,
                "skip_reason": f"could not parse pyproject.toml: {exc}",
            }

    mypy_config = pyproject.get("tool", {}).get("mypy")
    if not mypy_config:
        return {
            "category": "type",
            "ok": True,
            "findings": [],
            "summary": "mypy: no [tool.mypy] section in pyproject.toml",
            "skipped": True,
            "skip_reason": "no [tool.mypy] section in pyproject.toml",
        }

    paths = mypy_config.get("files", [])
    if not paths:
        return {
            "category": "type",
            "ok": True,
            "findings": [],
            "summary": "mypy: no files configured in [tool.mypy]",
            "skipped": True,
            "skip_reason": "no files configured in [tool.mypy]",
        }

    if not _tool_on_path("mypy"):
        return {
            "category": "type",
            "ok": True,
            "findings": [],
            "summary": "mypy: not installed",
            "skipped": True,
            "skip_reason": "mypy not installed",
        }

    result = _run(["mypy"] + paths)
    if result.returncode == 0:
        return {
            "category": "type",
            "ok": True,
            "findings": [],
            "summary": f"mypy: clean on {len(paths)} path(s)",
            "skipped": False,
            "skip_reason": None,
        }

    lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip()]
    capped = lines[:20]
    error_count = len(lines)
    return {
        "category": "type",
        "ok": False,
        "findings": capped,
        "summary": f"mypy: {error_count} error(s)",
        "skipped": False,
        "skip_reason": None,
    }


def _audit_test_discovery() -> dict:
    """Run pytest --collect-only to surface import/fixture errors."""
    if not _tool_on_path("pytest"):
        return {
            "category": "test_discovery",
            "ok": True,
            "findings": [],
            "summary": "pytest collection: pytest not installed",
            "skipped": True,
            "skip_reason": "pytest not installed",
        }

    result = _run(["pytest", "--collect-only", "-q"])
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    lines = stdout.splitlines()
    # Try to find test count
    test_count: int | None = None
    for ln in reversed(lines):
        if "tests collected" in ln:
            m = re.search(r"(\d+)\s+test", ln)
            if m:
                test_count = int(m.group(1))
            break

    if result.returncode == 0:
        summary = (
            f"pytest collection: clean ({test_count} tests)"
            if test_count is not None
            else "pytest collection: clean"
        )
        return {
            "category": "test_discovery",
            "ok": True,
            "findings": [],
            "summary": summary,
            "skipped": False,
            "skip_reason": None,
        }

    # Errors: capture stderr and last 20 stdout lines
    out_tail = lines[-20:] if len(lines) >= 20 else lines
    findings = [f"[stderr] {ln}" for ln in stderr.splitlines() if ln.strip()] + out_tail
    error_count = len(findings)
    summary = f"pytest collection: {error_count} error(s)"
    return {
        "category": "test_discovery",
        "ok": False,
        "findings": findings,
        "summary": summary,
        "skipped": False,
        "skip_reason": None,
    }


def _audit_hook() -> dict:
    """Syntax-check git hooks in scripts/git-hooks/."""
    if not GIT_HOOKS_DIR.exists():
        return {
            "category": "hook",
            "ok": True,
            "findings": [],
            "summary": "hooks: directory not found",
            "skipped": True,
            "skip_reason": "scripts/git-hooks/ does not exist",
        }

    hook_files = [f for f in GIT_HOOKS_DIR.iterdir() if f.is_file()]
    if not hook_files:
        return {
            "category": "hook",
            "ok": True,
            "findings": [],
            "summary": "hooks: none found",
            "skipped": False,
            "skip_reason": None,
        }

    findings: list[str] = []
    clean = 0
    total = 0
    for hf in sorted(hook_files):
        total += 1
        text = hf.read_text(encoding="utf-8")
        if text.startswith("#!/bin/bash") or hf.suffix == ".sh":
            res = _run(["bash", "-n", str(hf)])
            if res.returncode != 0:
                findings.append(f"{hf.name}: bash syntax error")
            else:
                clean += 1
        elif hf.suffix == ".py":
            res = _run([sys.executable, "-m", "py_compile", str(hf)])
            if res.returncode != 0:
                findings.append(f"{hf.name}: Python syntax error")
            else:
                clean += 1
        else:
            findings.append(f"{hf.name}: unrecognized hook type (skipped check)")

    if findings:
        summary = f"hooks: {len(findings)}/{total} have issues"
    else:
        summary = f"hooks: {clean}/{total} clean"
    return {
        "category": "hook",
        "ok": not findings,
        "findings": findings,
        "summary": summary,
        "skipped": False,
        "skip_reason": None,
    }


def _audit_config_consumption() -> dict:
    """Detect unconsumed architecture.yaml worker config keys in delegate.py."""
    if not ARCHITECTURE_FILE.exists():
        return {
            "category": "config_consumption",
            "ok": True,
            "findings": [],
            "summary": "config keys: architecture.yaml not found",
            "skipped": True,
            "skip_reason": "architecture.yaml not found",
        }

    if not DELEGATE_PY.exists():
        return {
            "category": "config_consumption",
            "ok": True,
            "findings": [],
            "summary": "config keys: delegate.py not found",
            "skipped": True,
            "skip_reason": "delegate.py not found",
        }

    content = ARCHITECTURE_FILE.read_text(encoding="utf-8")
    delegate_src = DELEGATE_PY.read_text(encoding="utf-8")

    # Collect keys at workers.<name>.* level
    keys: list[tuple[str, str, str]] = []  # (name, key, dotted)
    in_workers = False
    current_worker: str | None = None
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped == "workers:":
            in_workers = True
            continue
        if not in_workers:
            continue
        # End of workers section when indent drops
        if line and not line.startswith(" "):
            in_workers = False
            break
        # Named worker entry (2-space indent, ends with colon)
        if line.startswith("  ") and not line.startswith("   ") and stripped.endswith(":"):
            current_worker = stripped.rstrip(":")
            continue
        # Key under worker (4-space indent)
        if current_worker and line.startswith("    ") and ":" in stripped and not stripped.startswith("#"):
            key = stripped.split(":", 1)[0].strip()
            keys.append((current_worker, key, f"workers.{current_worker}.{key}"))

    # Excluded keys that don't need explicit consumption
    excluded = {"provider", "env_key"}
    unconsumed: list[str] = []
    for worker_name, key, dotted in keys:
        if key in excluded:
            continue
        patterns = [
            f'config.get("{key}"',
            f"config.get('{key}'",
            f"config[\"{key}\"]",
            f"config['{key}']",
            f"profile.{key}",
        ]
        if not any(p in delegate_src for p in patterns):
            unconsumed.append(f"{dotted}: not referenced in delegate.py")

    total = len(keys)
    if unconsumed:
        summary = f"config keys: {len(unconsumed)} unconsumed of {total} total"
    else:
        summary = f"config keys: all {total} referenced"
    return {
        "category": "config_consumption",
        "ok": not unconsumed,
        "findings": unconsumed,
        "summary": summary,
        "skipped": False,
        "skip_reason": None,
    }


def _render_human(results: list[dict]) -> None:
    """Print human-readable audit report."""
    for r in results:
        cat = r["category"]
        if r["skipped"]:
            prefix = yellow("~")
            line = f"{prefix} [{cat}] {r['summary']}"
        elif r["ok"]:
            prefix = green("✓")
            line = f"{prefix} [{cat}] {r['summary']}"
        else:
            prefix = red("✗")
            line = f"{prefix} [{cat}] {r['summary']}"
        print(line)
        for finding in r.get("findings", []):
            print(f"    {finding}")

    ok_count = sum(1 for r in results if r["ok"] and not r["skipped"])
    gap_count = sum(1 for r in results if not r["ok"] and not r["skipped"])
    skip_count = sum(1 for r in results if r["skipped"])
    gap_names = [r["category"] for r in results if not r["ok"] and not r["skipped"]]
    parts = []
    if ok_count:
        parts.append(f"{ok_count} ok")
    if gap_count:
        parts.append(f"{gap_count} gap")
    if skip_count:
        parts.append(f"{skip_count} skipped")
    summary = ", ".join(parts) if parts else "no categories"
    suffix = f" ({', '.join(gap_names)})" if gap_names else ""
    print(f"\nAudit: {summary}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description="RSI proactive infrastructure audit")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any gap found")
    parser.add_argument(
        "--category",
        choices=["lint", "type", "test_discovery", "hook", "config_consumption"],
        help="Run a single category instead of all",
    )
    args = parser.parse_args()

    audits = {
        "lint": _audit_lint,
        "type": _audit_type,
        "test_discovery": _audit_test_discovery,
        "hook": _audit_hook,
        "config_consumption": _audit_config_consumption,
    }
    if args.category:
        results = [audits[args.category]()]
    else:
        results = [fn() for fn in audits.values()]

    if args.json:
        print(json.dumps({"results": results}, indent=2, ensure_ascii=False))
    else:
        _render_human(results)

    if args.strict:
        any_gap = any(not r["ok"] and not r["skipped"] for r in results)
        return 1 if any_gap else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
