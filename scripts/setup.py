#!/usr/bin/env python3
# setup.py — Install RSI framework hooks system-wide
# ONE-TIME SETUP: Run once on a machine. Hooks then work automatically for every clone.
#
# Cross-platform: works on Linux, macOS, Windows (Git Bash, PowerShell, CMD)
#
# What it does:
# - Installs hooks to ~/.git_template/hooks/ (git's template directory)
# - Every `git clone` or `git init` automatically gets these hooks
#
# To undo: rm -rf ~/.git_template/hooks/rsi-* ~/.memory/rsi/

import os
import sys
import shutil
import stat
from pathlib import Path


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables, resolve to absolute Path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str))).resolve()


def main():
    print("RSI Framework — System-wide Setup")
    print("")

    # Find the rsi-framework directory (parent of scripts/)
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent
    rsi_hooks_src = project_root / "scripts" / "git-hooks"
    template_hooks = expand_path("~/.git_template/hooks")

    # Verify hooks exist
    if not rsi_hooks_src.is_dir():
        print(f"Error: hooks not found at {rsi_hooks_src}")
        print("Run from within the rsi-framework directory.")
        sys.exit(1)

    # Create template directory if needed
    template_hooks.mkdir(parents=True, exist_ok=True)

    # Install hooks
    installed = []
    for hook_file in rsi_hooks_src.iterdir():
        if hook_file.is_file():
            dest = template_hooks / hook_file.name
            shutil.copy2(hook_file, dest)
            # Ensure executable
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            installed.append(hook_file.name)

    print(f"  ✓ Hooks installed to {template_hooks}")
    print("")
    print("Installed hooks:")
    for name in sorted(installed):
        print(f"  - {name}")
    print("")

    # Verify pre-commit is executable
    test_hook = template_hooks / "pre-commit"
    if test_hook.stat().st_mode & stat.S_IXUSR:
        print("  ✓ pre-commit is executable")
    else:
        print("  ✗ pre-commit is NOT executable")
        sys.exit(1)

    print("")
    print("✓ Setup complete.")
    print("")
    print("After this, every new clone will automatically have these hooks:")
    print("  - pre-commit: runs pre-flight + self-verify before commit")
    print("  - commit-msg: blocks commit without memory update")
    print("")
    print("For existing repos, apply hooks manually:")
    print(f"  git config core.hooksPath \"{template_hooks}\"")
    print("")
    print("To create a new project with hooks:")
    print(f"  git clone --template={template_hooks} YOUR_REPO_URL")
    print("")
    print("Or clone normally, then in the new repo:")
    print(f"  git config core.hooksPath \"{template_hooks}\"")


if __name__ == "__main__":
    main()
