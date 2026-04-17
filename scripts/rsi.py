#!/usr/bin/env python3
"""
rsi — unified CLI for the Recursive Self-Improvement framework.

One command to rule them all. Replaces remembering 8 different script names.

Usage:
    python3 scripts/rsi.py init              # Start session
    python3 scripts/rsi.py capture            # Module A
    python3 scripts/rsi.py review             # Module B
    python3 scripts/rsi.py optimize           # Module C
    python3 scripts/rsi.py loop               # A->B->C chained
    python3 scripts/rsi.py verify             # Self-verify
    python3 scripts/rsi.py preflight          # Pre-flight check
    python3 scripts/rsi.py ceremony           # Check ceremony level
    python3 scripts/rsi.py dashboard          # Andon board
    python3 scripts/rsi.py backlog [cmd]      # Backlog management
    python3 scripts/rsi.py calibrate [cmd]    # Calibration tracker
    python3 scripts/rsi.py root-cause         # 5-Whys analysis
    python3 scripts/rsi.py metrics [cmd]      # Metrics engine
    python3 scripts/rsi.py ci                 # CI gate
    python3 scripts/rsi.py setup              # One-time setup
    python3 scripts/rsi.py sync               # Framework sync
    python3 scripts/rsi.py status             # Quick status
"""

import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _run(script: str, args: list[str] | None = None, allow_failure: bool = False) -> int:
    """Run a Python script. Exits on failure unless allow_failure=True.

    Streams child stdout/stderr directly so wrapped commands stay visible.
    """
    cmd = [sys.executable, str(SCRIPTS_DIR / script)] + (args or [])
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(PROJECT_ROOT) + (os.pathsep + existing if existing else "")
    # Force UTF-8 for all file I/O so Path.read_text/write_text, print(), and
    # json.dumps(..., ensure_ascii=False) all round-trip Unicode content (emoji,
    # em-dashes, non-ASCII worker output). Windows default is cp1252 which
    # raises UnicodeEncodeError on any char outside Latin-1.
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env)
    if result.returncode != 0 and not allow_failure:
        sys.exit(result.returncode)
    return result.returncode


def _run_bash(script: str, args: list[str] | None = None, allow_failure: bool = False) -> int:
    """Run a bash script. Exits on failure unless allow_failure=True.

    Streams child stdout/stderr directly so wrapped commands stay visible.
    """
    cmd = ["bash", str(SCRIPTS_DIR / script)] + (args or [])
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0 and not allow_failure:
        sys.exit(result.returncode)
    return result.returncode


def cmd_init(args: list[str]) -> None:
    """Start a new session."""
    _run_bash("init.sh", args, allow_failure=True)
    _run("preflight_check.py", ["--start"])
    # Record metrics
    try:
        from scripts.metrics import record

        record("session_start")
    except ImportError:
        pass
    # Session brief — compound learning from .memory/
    try:
        from scripts.session_brief import generate_brief

        print(generate_brief())
    except ImportError:
        pass


def cmd_capture(args: list[str]) -> None:
    """Module A: Post-implementation capture."""
    _run("post_implementation.py", args)


def cmd_review(args: list[str]) -> None:
    """Module B: Self-feedback."""
    _run("self_feedback.py", args)


def cmd_optimize(args: list[str]) -> None:
    """Module C: Self-optimization."""
    _run("self_optimization.py", args)


def cmd_loop(args: list[str]) -> None:
    """Run the full A->B->C loop."""
    # First classify ceremony level
    from scripts.ceremony import classify_change
    from scripts.colors import bold

    result = classify_change()
    level = result["level"]

    print(f"\n{bold(f'Ceremony level: {level.upper()}')} — {result['reason']}")
    for i, step in enumerate(result["required_steps"], 1):
        print(f"  {i}. {step}")
    print()

    _run("post_implementation.py", ["--interactive", "--run-feedback", "--run-optimization"] + args)


def cmd_verify(args: list[str]) -> None:
    """Self-verification."""
    _run("self_verify.py", args)


def cmd_preflight(args: list[str]) -> None:
    """Pre-flight check."""
    _run("preflight_check.py", args)


def cmd_ceremony(args: list[str]) -> None:
    """Check ceremony level for current changes."""
    _run("ceremony.py", args)


def cmd_dashboard(args: list[str]) -> None:
    """Show the andon dashboard."""
    _run("dashboard.py", args)


def cmd_backlog(args: list[str]) -> None:
    """Backlog management."""
    _run("backlog.py", args)


def cmd_calibrate(args: list[str]) -> None:
    """Calibration tracker."""
    _run("calibration.py", args)


def cmd_root_cause(args: list[str]) -> None:
    """5-Whys root cause analysis."""
    _run("root_cause.py", args)


def cmd_metrics(args: list[str]) -> None:
    """Metrics engine."""
    _run("metrics.py", args)


def cmd_ci(args: list[str]) -> None:
    """Run CI checks."""
    _run_bash("ci_check.sh", args)


def cmd_setup(args: list[str]) -> None:
    """One-time setup."""
    _run("setup.py", args)


def cmd_sync(args: list[str]) -> None:
    """Framework sync."""
    _run("framework_sync.py", args)


def cmd_status(args: list[str]) -> None:
    """Quick status overview."""
    from scripts.colors import green, header, red, yellow

    print(header("RSI STATUS"))

    # Session
    session_file = PROJECT_ROOT / ".memory" / ".session_timestamp"
    if session_file.exists():
        import json

        try:
            from scripts.hooks import _get_session_time_remaining, _is_session_expired

            data = json.loads(session_file.read_text())
            started = data.get("timestamp", "?")[:19]
            ttl_hours = int(data.get("ttl_hours", 24))

            if _is_session_expired():
                print(f"\n  Session: {red('EXPIRED')} (started {started}, TTL {ttl_hours}h)")
                print("  Run 'python3 scripts/rsi.py init' to start a new session")
            else:
                expiring_soon, minutes = _get_session_time_remaining()
                if expiring_soon:
                    print(
                        f"\n  Session: {yellow('active')} (started {started}, {minutes}m remaining)"
                    )
                    print("  Run 'python3 scripts/rsi.py init' to extend session")
                else:
                    print(f"\n  Session: {green('active')} (started {started}, TTL {ttl_hours}h)")
        except Exception:
            print(f"\n  Session: {yellow('unknown')}")
    else:
        print(f"\n  Session: {yellow('no active session')}")

    # Memory
    memory_dir = PROJECT_ROOT / ".memory"
    if memory_dir.exists():
        rounds = (
            len(list((memory_dir / "rounds").glob("round-*.md")))
            if (memory_dir / "rounds").exists()
            else 0
        )
        print(f"  Rounds:  {rounds}")
    else:
        print(f"  Memory:  {yellow('not initialized (run: rsi setup)')}")

    # Ceremony level
    try:
        from scripts.ceremony import classify_change

        result = classify_change()
        print(
            f"  Ceremony: {result['level']} ({result['files_changed']} files, {result['lines_changed']} lines)"
        )
    except Exception:
        pass

    # Calibration
    try:
        from scripts.calibration import calibration_score

        score = calibration_score()
        if score["total"]:
            print(f"  Hypotheses: {score['total']} ({score['open']} open)")
    except Exception:
        pass

    print()


def cmd_adapt(args: list[str]) -> None:
    """Generate platform-specific adapter files."""

    # Import all adapters to populate the registry
    from adapters.base import AVAILABLE_ADAPTERS
    from scripts.colors import bold, cyan, green, red, yellow

    if not args or args[0] in ("-h", "--help", "help"):
        print(bold("\nRSI Adapt — Generate platform-specific enforcement files\n"))
        print("Usage: python3 scripts/rsi.py adapt <platform|all|list>\n")
        print("Platforms:")
        for pid, cls in sorted(AVAILABLE_ADAPTERS.items()):
            a = cls()
            enforcement = (
                green("tool-layer") if a.supports_tool_enforcement else yellow("prompt-only")
            )
            print(f"  {cyan(pid.ljust(18))} {a.platform_name.ljust(28)} [{enforcement}]")
        print(f"\n  {cyan('all'.ljust(18))} Generate files for all platforms")
        print(f"  {cyan('list'.ljust(18))} List available platforms")
        return

    target = args[0]

    if target == "list":
        for pid, cls in sorted(AVAILABLE_ADAPTERS.items()):
            a = cls()
            print(f"  {pid}: {a.platform_name}")
        return

    if target == "all":
        platforms = list(AVAILABLE_ADAPTERS.keys())
    elif target in AVAILABLE_ADAPTERS:
        platforms = [target]
    else:
        print(f"{red('Unknown platform:')} {target}")
        print(f"Available: {', '.join(sorted(AVAILABLE_ADAPTERS.keys()))}")
        sys.exit(1)

    for pid in platforms:
        adapter = AVAILABLE_ADAPTERS[pid](PROJECT_ROOT)
        created = adapter.install()
        print(f"\n{green(adapter.platform_name)}:")
        for f in created:
            print(f"  {green('+')} {f}")

    print(f"\n{green('Done.')} Platform files generated.")


def cmd_delegate(args: list[str]) -> None:
    """Delegate a task to the worker model."""
    _run("delegate.py", args)


def cmd_auto(args: list[str]) -> None:
    """Auto-delegate: decompose task, route to MiniMax, review, apply."""
    _run("auto_delegate.py", args)


def cmd_review_queue(args: list[str]) -> None:
    """Manage the review queue."""
    _run("review_queue.py", args)


def cmd_trust(args: list[str]) -> None:
    """Worker trust scoring."""
    _run("trust.py", args)


def cmd_classify(args: list[str]) -> None:
    """Classify file sensitivity."""
    _run("classify_file.py", args)


def cmd_override(args: list[str]) -> None:
    """Create a temporary override allowing direct edit of a delegatable file."""
    from scripts.colors import green, red, yellow

    if not args or args[0] in ("-h", "--help"):
        print("Usage: python3 scripts/rsi.py override <filepath> --reason 'reason'")
        print("       python3 scripts/rsi.py override --list")
        print("       python3 scripts/rsi.py override --clear")
        print("\nCreates a 1-hour override. Emergency escape hatch only.")
        return

    if args[0] == "--list":
        override_dir = PROJECT_ROOT / ".rsi" / "overrides"
        if not override_dir.exists() or not list(override_dir.glob("*.json")):
            print("No active overrides.")
            return
        import json as _json

        for of in sorted(override_dir.glob("*.json")):
            data = _json.loads(of.read_text())
            print(
                f"  {data.get('filepath', '?')}  reason: {data.get('reason', '?')}  ttl: {data.get('ttl_minutes', 60)}m"
            )
        return

    if args[0] == "--clear":
        override_dir = PROJECT_ROOT / ".rsi" / "overrides"
        if override_dir.exists():
            import shutil

            shutil.rmtree(override_dir)
            override_dir.mkdir(parents=True, exist_ok=True)
        print(f"{green('Overrides cleared.')}")
        return

    filepath = args[0]
    reason = ""
    ttl = 60
    i = 1
    while i < len(args):
        if args[i] == "--reason" and i + 1 < len(args):
            reason = args[i + 1]
            i += 2
        elif args[i] == "--ttl" and i + 1 < len(args):
            ttl = int(args[i + 1])
            i += 2
        else:
            i += 1

    if not reason:
        print(f"{red('--reason is required.')} Why are you bypassing delegation?")
        return

    from scripts.hooks import create_override

    override_file = create_override(filepath, reason, ttl)
    print(f"{yellow('Override created:')} {filepath}")
    print(f"  Reason: {reason}")
    print(f"  Expires: {ttl} minutes")
    print(f"  File: {override_file}")
    print(f"\n{yellow('WARNING:')} This bypasses delegation enforcement. Use sparingly.")


COMMANDS = {
    "init": (cmd_init, "Start a new session"),
    "capture": (cmd_capture, "Module A: post-implementation capture"),
    "review": (cmd_review, "Module B: self-feedback"),
    "optimize": (cmd_optimize, "Module C: self-optimization"),
    "loop": (cmd_loop, "Full A->B->C loop (with ceremony classification)"),
    "verify": (cmd_verify, "Self-verification checks"),
    "preflight": (cmd_preflight, "Pre-flight check (read before edit)"),
    "ceremony": (cmd_ceremony, "Classify change scope / ceremony level"),
    "dashboard": (cmd_dashboard, "Andon board — visual management"),
    "backlog": (cmd_backlog, "Backlog management"),
    "calibrate": (cmd_calibrate, "Proof-wrong calibration tracker"),
    "root-cause": (cmd_root_cause, "5-Whys root cause analysis"),
    "metrics": (cmd_metrics, "Metrics engine"),
    "delegate": (cmd_delegate, "Send task to worker model (MiniMax-M2.7)"),
    "auto": (cmd_auto, "Auto-route: decompose -> delegate -> review -> apply"),
    "review-queue": (cmd_review_queue, "Manage review queue (Jidoka)"),
    "classify": (cmd_classify, "Check file sensitivity level"),
    "trust": (cmd_trust, "Worker trust scoring (per-task-type accept rate)"),
    "override": (cmd_override, "Emergency override for delegation gate (1hr TTL)"),
    "adapt": (cmd_adapt, "Generate platform-specific enforcement files"),
    "ci": (cmd_ci, "CI gate checks"),
    "setup": (cmd_setup, "One-time setup"),
    "sync": (cmd_sync, "Framework sync / update"),
    "status": (cmd_status, "Quick status overview"),
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        from scripts.colors import bold, cyan

        print(bold("\nRSI Framework — Unified CLI\n"))
        print("Usage: python3 scripts/rsi.py <command> [args...]\n")
        print("Commands:")
        for name, (_, desc) in sorted(COMMANDS.items()):
            print(f"  {cyan(f'{name:<14}')} {desc}")
        print("\nRun 'python3 scripts/rsi.py <command> --help' for command-specific help.")
        sys.exit(0)

    cmd_name = sys.argv[1]
    cmd_args = sys.argv[2:]

    if cmd_name in COMMANDS:
        handler, _ = COMMANDS[cmd_name]
        handler(cmd_args)
    else:
        print(f"Unknown command: {cmd_name}")
        print("Run 'python3 scripts/rsi.py help' for available commands.")
        sys.exit(1)


if __name__ == "__main__":
    main()
