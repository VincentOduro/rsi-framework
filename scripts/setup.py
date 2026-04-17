#!/usr/bin/env python3
# setup.py — Install RSI framework hooks system-wide
# ONE-TIME SETUP: Run once on a machine. Hooks then work automatically for every clone.
#
# Cross-platform: works on Linux, macOS, Windows (Git Bash, PowerShell, CMD)
#
# Usage:
#   python3 scripts/setup.py                      # Interactive model selection
#   python3 scripts/setup.py --model claude        # Claude Code
#   python3 scripts/setup.py --model opencode      # opencode / MiniMax-M2.7
#   python3 scripts/setup.py --model shell         # Generic shell integration
#   python3 scripts/setup.py --model all           # All supported models
#
# What it does:
#   - Installs git hooks to ~/.git_template/hooks/ (git's template directory)
#   - Installs AI model-specific hooks/adapters
#   - Initializes .memory/ from MEMORY_TEMPLATE if not present
#
# To undo: rm -rf ~/.git_template/hooks/rsi-* ~/.memory/rsi/

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path

SUPPORTED_MODELS = {
    "claude": "Claude Code (PreToolUse/PostToolUse hooks)",
    "opencode": "opencode / MiniMax-M2.7 (shell wrapper)",
    "shell": "Generic shell integration (any CLI AI tool)",
}


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables, resolve to absolute Path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str))).resolve()


def install_git_hooks(project_root: Path) -> bool:
    """Install git hooks to ~/.git_template/hooks/."""
    script_dir = project_root / "scripts"
    rsi_hooks_src = script_dir / "git-hooks"
    template_hooks = expand_path("~/.git_template/hooks")

    if not rsi_hooks_src.is_dir():
        print(f"Error: git hooks not found at {rsi_hooks_src}")
        return False

    template_hooks.mkdir(parents=True, exist_ok=True)

    installed = []
    for hook_file in rsi_hooks_src.iterdir():
        if hook_file.is_file():
            dest = template_hooks / hook_file.name
            shutil.copy2(hook_file, dest)
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            installed.append(hook_file.name)

    print(f"  + Git hooks installed to {template_hooks}")
    for name in sorted(installed):
        print(f"    - {name}")

    test_hook = template_hooks / "pre-commit"
    if not (test_hook.stat().st_mode & stat.S_IXUSR):
        print("  x pre-commit is NOT executable")
        return False

    return True


def install_claude_hooks(project_root: Path) -> None:
    """Install Claude Code hooks via the adapter system."""
    claude_settings = project_root / ".claude" / "settings.json"

    if not claude_settings.exists():
        sys.path.insert(0, str(project_root))
        try:
            from adapters.claude_code import ClaudeCodeAdapter

            adapter = ClaudeCodeAdapter(project_root)
            created = adapter.install()
            for f in created:
                print(f"  + {f}")
        except ImportError:
            # Fallback: write settings directly
            claude_settings.parent.mkdir(parents=True, exist_ok=True)
            import json

            settings = {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Read",
                            "hooks": [
                                {"type": "command", "command": "python3 scripts/hooks.py pre-read"}
                            ],
                        },
                        {
                            "matcher": "Edit|Write",
                            "hooks": [
                                {"type": "command", "command": "python3 scripts/hooks.py pre-edit"}
                            ],
                        },
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "python3 scripts/hooks.py pre-bash"}
                            ],
                        },
                    ],
                    "PostToolUse": [
                        {
                            "matcher": "Edit|Write",
                            "hooks": [
                                {"type": "command", "command": "python3 scripts/hooks.py post-edit"}
                            ],
                        },
                    ],
                }
            }
            claude_settings.write_text(json.dumps(settings, indent=2) + "\n")
            print(f"  + Claude Code hooks installed at {claude_settings}")
    else:
        print(f"  + Claude Code hooks already exist at {claude_settings}")
        print("    (To update, delete .claude/settings.json and re-run setup)")


def install_opencode_adapter(project_root: Path) -> None:
    """Install opencode/MiniMax-M2.7 adapter via the adapter system."""
    sys.path.insert(0, str(project_root))
    try:
        from adapters.minimax import MiniMaxAdapter

        adapter = MiniMaxAdapter(project_root)
        created = adapter.install()
        for f in created:
            print(f"  + {f}")
        wrapper = project_root / "opencode_wrapper.sh"
        if wrapper.exists():
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except ImportError:
        print("  x Adapter module not found. Ensure adapters/ directory exists.")


def install_shell_integrator(project_root: Path) -> None:
    """Install generic shell adapter via the adapter system."""
    sys.path.insert(0, str(project_root))
    try:
        from adapters.generic import GenericAdapter

        adapter = GenericAdapter(project_root)
        created = adapter.install()
        for f in created:
            print(f"  + {f}")
        wrapper = project_root / "opencode_wrapper.sh"
        if wrapper.exists():
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except ImportError:
        print("  x Adapter module not found. Ensure adapters/ directory exists.")


def init_memory(project_root: Path) -> None:
    """Initialize .memory/ from MEMORY_TEMPLATE."""
    memory_dir = project_root / ".memory"
    template_dir = project_root / "MEMORY_TEMPLATE"

    if memory_dir.exists():
        print("  + .memory/ already exists")
    elif template_dir.exists():
        print("  + Initializing .memory/ from MEMORY_TEMPLATE...")
        shutil.copytree(template_dir, memory_dir)
        print("    .memory/ created")
    else:
        print("  ! MEMORY_TEMPLATE not found, skipping .memory/ init")


def select_model_interactive() -> list:
    """Prompt user to select AI models interactively."""
    print("Select AI models to set up (space-separated, Enter for default):")
    print("")
    options = list(SUPPORTED_MODELS.items())
    for i, (name, desc) in enumerate(options, 1):
        print(f"  {i}. {name:12} — {desc}")
    print("  a.  all        — Install all models")
    print("  c.  continue  — Skip model setup, continue with git hooks")
    print("")

    selected = []
    while True:
        choice = input("Select (1 2 3 a c): ").strip().lower()

        if choice == "c" or choice == "":
            break

        if choice == "a":
            selected = list(SUPPORTED_MODELS.keys())
            break

        nums = choice.split()
        valid = True
        for n in nums:
            if n.isdigit():
                idx = int(n) - 1
                if 0 <= idx < len(options):
                    selected.append(options[idx][0])
                else:
                    valid = False
                    print(f"Invalid number: {n}")
            elif n in SUPPORTED_MODELS:
                selected.append(n)
            else:
                valid = False
                print(f"Invalid option: {n}")

        if valid and selected:
            break

    return selected


def main():
    parser = argparse.ArgumentParser(
        description="RSI Framework Setup — Install hooks for AI model(s)"
    )
    parser.add_argument(
        "--model",
        choices=["claude", "opencode", "shell", "all"],
        help="AI model to set up (default: all)",
    )
    parser.add_argument("--skip-memory", action="store_true", help="Skip .memory/ initialization")
    parser.add_argument(
        "--list-models", action="store_true", help="List supported AI models and exit"
    )

    args = parser.parse_args()

    if args.list_models:
        print("Supported AI models:")
        for name, desc in SUPPORTED_MODELS.items():
            print(f"  {name:12} — {desc}")
        return

    print("RSI Framework — Setup")
    print("=" * 40)
    print("")

    # Find project root
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent

    # Determine which models to install
    if args.model == "all":
        models_to_install = list(SUPPORTED_MODELS.keys())
    elif args.model:
        models_to_install = [args.model]
    else:
        models_to_install = select_model_interactive()

    print(
        f"Installing for models: {', '.join(models_to_install) if models_to_install else 'git hooks only'}"
    )
    print("")

    # Always install git hooks (required for commit enforcement)
    print("[Git Hooks]")
    if not install_git_hooks(project_root):
        print("Error: Failed to install git hooks")
        sys.exit(1)

    # Install model-specific adapters
    if "claude" in models_to_install:
        print("")
        print("[Claude Code]")
        install_claude_hooks(project_root)

    if "opencode" in models_to_install:
        print("")
        print("[opencode / MiniMax-M2.7]")
        install_opencode_adapter(project_root)

    if "shell" in models_to_install:
        print("")
        print("[Shell Integrator]")
        install_shell_integrator(project_root)

    # Initialize .memory/
    if not args.skip_memory:
        print("")
        print("[Memory]")
        init_memory(project_root)

    print("")
    print("=" * 40)
    print("+ Setup complete.")
    print("")

    if "claude" in models_to_install:
        print("Claude Code hooks: Active (via .claude/settings.json)")

    if "opencode" in models_to_install:
        print("opencode wrapper: Active (run 'alias opencode=/path/to/opencode_wrapper.sh')")

    if "shell" in models_to_install:
        print("Shell integrator: Available at ./shell_integrator.py")

    print("")
    print("Next steps:")
    print("  python3 scripts/rsi.py init              # Start a session")
    print("  python3 scripts/rsi.py dashboard         # View andon board")
    print("")
    print("For opencode/MiniMax-M2.7, add to shell profile:")
    print(f"  alias opencode='{project_root / 'opencode_wrapper.sh'}'")
    print("")
    print("For other AI models, see scripts/adapters/README.md")


if __name__ == "__main__":
    main()
