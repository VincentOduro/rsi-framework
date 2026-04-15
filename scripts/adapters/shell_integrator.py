#!/usr/bin/env python3
"""
shell_integrator.py — Generic shell-based RSI integration for any AI tool.

This module provides shell integration functions that can wrap any AI CLI tool.
It works by:
1. Interposing on file operations (read/edit/write)
2. Enforcing the read-before-edit rule
3. Tracking session state
4. Blocking dangerous commands (--no-verify, etc.)

Usage as a module:
    from adapters.shell_integrator import ShellIntegrator

    integrator = ShellIntegrator(project_root="/path/to/project")
    integrator.record_read("src/main.py")
    integrator.check_edit_allowed("src/main.py")  # exits if not allowed
    integrator.record_edit("src/main.py")

Usage as a command-line tool:
    python3 scripts/adapters/shell_integrator.py record-read --file src/main.py
    python3 scripts/adapters/shell_integrator.py check-edit --file src/main.py
    python3 scripts/adapters/shell_integrator.py check-bash --command "git commit"

This is the foundation for integrating with:
  - opencode / MiniMax-M2.7
  - Other CLI-based AI coding tools
  - Shell-based AI assistants
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(os.environ.get("RSI_PROJECT_ROOT", Path(__file__).parent.parent.parent.resolve()))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from hooks import (
        _record_file_read,
        _record_file_edited,
        _load_read_files,
        _relative_path,
        _is_session_expired,
        _get_relevant_fail_entries,
    )
except ImportError:
    from scripts.hooks import (
        _record_file_read,
        _record_file_edited,
        _load_read_files,
        _relative_path,
        _is_session_expired,
        _get_relevant_fail_entries,
    )


class ShellIntegrator:
    """Python class for shell-based RSI integration.

    This class can be used by any AI tool that can invoke Python code
    or be wrapped with a shell alias.

    Example usage in a shell wrapper script:
        #!/bin/bash
        python3 -c "
        import sys
        sys.path.insert(0, 'scripts')
        from adapters.shell_integrator import ShellIntegrator
        integrator = ShellIntegrator()
        integrator.record_read('$1')
        " "$@"
    """

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize the shell integrator.

        Args:
            project_root: Path to the project root. Auto-detected if not provided.
        """
        self.project_root = project_root or PROJECT_ROOT

    def record_read(self, filepath: str) -> bool:
        """Record a file as having been read.

        Args:
            filepath: Path to the file that was read

        Returns:
            True if recorded successfully
        """
        if not filepath:
            return True

        try:
            rel = _relative_path(filepath)
            _record_file_read(rel)
            print(f"[RSI] Recorded read: {rel}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[RSI] Warning: Could not record read: {e}", file=sys.stderr)
            return False

    def check_edit_allowed(self, filepath: str) -> bool:
        """Check if editing a file is allowed.

        This will exit with code 1 if:
        - Session has expired
        - File exists but hasn't been read in this session

        Args:
            filepath: Path to the file to check

        Returns:
            True if editing is allowed

        Raises:
            SystemExit: If editing is not allowed
        """
        if not filepath:
            return True

        # Check session expiry
        if _is_session_expired():
            print("[RSI] Session expired. Run 'python3 scripts/rsi.py init' to start a new session.", file=sys.stderr)
            print("[RSI] Edits are blocked until session is active.", file=sys.stderr)
            sys.exit(1)

        rel = _relative_path(filepath)
        read_files = _load_read_files()

        # Check if file was read
        if rel not in read_files:
            if Path(filepath).exists():
                print(f"[RSI] File '{rel}' has not been read in this session.", file=sys.stderr)
                print(f"[RSI] Genchi Genbutsu: you must read a file before editing it.", file=sys.stderr)
                print(f"[RSI] Read the file first, then retry the edit.", file=sys.stderr)
                sys.exit(1)

        # Show FAIL-index entries
        fail_entries = _get_relevant_fail_entries(filepath)
        if fail_entries:
            print(f"[RSI] FAIL-index entries to consider while editing '{rel}':", file=sys.stderr)
            for entry in fail_entries[:5]:
                print(f"  {entry}", file=sys.stderr)

        return True

    def record_edit(self, filepath: str) -> bool:
        """Record a file as having been edited.

        Args:
            filepath: Path to the file that was edited

        Returns:
            True if recorded successfully
        """
        if not filepath:
            return True

        try:
            rel = _relative_path(filepath)
            _record_file_edited(rel)
            print(f"[RSI] Recorded edit: {rel}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[RSI] Warning: Could not record edit: {e}", file=sys.stderr)
            return False

    def check_bash_allowed(self, command: str) -> bool:
        """Check if a bash command is allowed.

        This will exit with code 1 if the command violates RSI rules.

        Args:
            command: The bash command to check

        Returns:
            True if the command is allowed

        Raises:
            SystemExit: If the command is not allowed
        """
        if not command:
            return True

        # Check for --no-verify bypass
        if "git commit" in command and "--no-verify" in command:
            print("[RSI] WARNING: --no-verify bypasses quality gates.", file=sys.stderr)
            print("[RSI] This violates Jidoka (Principle 5): stop and fix quality first.", file=sys.stderr)
            print("[RSI] Remove --no-verify and fix any failing checks.", file=sys.stderr)
            sys.exit(1)

        return True

    def check_session(self) -> bool:
        """Check if the RSI session is active.

        Returns:
            True if session is active, False if expired
        """
        if _is_session_expired():
            print("[RSI] Session: EXPIRED", file=sys.stderr)
            return False
        print("[RSI] Session: ACTIVE", file=sys.stderr)
        return True

    def show_fail_index(self, filepath: str) -> list[str]:
        """Get FAIL-index entries relevant to a file.

        Args:
            filepath: Path to the file

        Returns:
            List of FAIL-index entry strings
        """
        return _get_relevant_fail_entries(filepath)

    def interactive_wrap(self, original_cmd: list[str]) -> int:
        """Wrap a command with pre/post hooks.

        This is the main entry point for shell-based integration.
        It runs pre-checks, executes the command, and runs post-checks.

        Args:
            original_cmd: The original command to wrap, as a list

        Returns:
            Exit code of the original command
        """
        import subprocess

        if not original_cmd:
            return 0

        cmd_name = os.path.basename(original_cmd[0])
        subcmd = original_cmd[1] if len(original_cmd) > 1 else ""

        # Determine what file(s) the command operates on
        files = self._detect_files(cmd_name, subcmd, original_cmd[1:])

        # Pre-read for read operations
        if subcmd == "read" and files:
            for f in files:
                self.record_read(f)

        # Pre-edit check for edit/write operations
        if subcmd in ("edit", "write", "apply") and files:
            for f in files:
                self.check_edit_allowed(f)

        # Execute the original command
        try:
            result = subprocess.run(original_cmd, check=False)
            exit_code = result.returncode
        except Exception as e:
            print(f"[RSI] Error executing command: {e}", file=sys.stderr)
            return 1

        # Post-edit recording
        if subcmd in ("edit", "write", "apply") and files:
            for f in files:
                self.record_edit(f)

        return exit_code

    def _detect_files(self, cmd_name: str, subcmd: str, args: list) -> list[str]:
        """Detect file arguments from a command.

        This is a heuristic and may need to be customized per AI tool.

        Args:
            cmd_name: Name of the command
            subcmd: Subcommand (if any)
            args: Command arguments

        Returns:
            List of file paths detected
        """
        files = []

        for i, arg in enumerate(args):
            # Skip flags
            if arg.startswith("-"):
                continue

            # Check if it looks like a file path
            path = Path(arg)
            if path.exists() and path.is_file():
                files.append(str(path))
            elif i == 0 and subcmd in ("read", "edit", "write", "apply"):
                # First non-flag argument is often the file
                files.append(str(path))

        return files


def main():
    parser = argparse.ArgumentParser(
        description="RSI Shell Integrator — Generic shell-based RSI enforcement"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # record-read
    p_read = sub.add_parser("record-read", help="Record a file as read")
    p_read.add_argument("--file", required=True, help="File path")

    # check-edit
    p_edit = sub.add_parser("check-edit", help="Check if editing is allowed")
    p_edit.add_argument("--file", required=True, help="File path")

    # record-edit
    p_rec_edit = sub.add_parser("record-edit", help="Record a file as edited")
    p_rec_edit.add_argument("--file", required=True, help="File path")

    # check-bash
    p_bash = sub.add_parser("check-bash", help="Check if bash command is allowed")
    p_bash.add_argument("--command", required=True, help="Command to check")

    # session-status
    sub.add_parser("session-status", help="Check session status")

    # fail-index
    p_fail = sub.add_parser("fail-index", help="Show FAIL-index entries for a file")
    p_fail.add_argument("--file", required=True, help="File path")

    # wrap
    p_wrap = sub.add_parser("wrap", help="Wrap a command with RSI checks")
    p_wrap.add_argument("command", nargs=argparse.REMAINDER, help="Command to wrap")

    args = parser.parse_args()

    integrator = ShellIntegrator()

    if args.command == "record-read":
        integrator.record_read(args.file)
    elif args.command == "check-edit":
        integrator.check_edit_allowed(args.file)
        print(f"[RSI] Edit allowed: {args.file}")
    elif args.command == "record-edit":
        integrator.record_edit(args.file)
    elif args.command == "check-bash":
        integrator.check_bash_allowed(args.command)
        print(f"[RSI] Bash allowed: {args.command}")
    elif args.command == "session-status":
        if not integrator.check_session():
            sys.exit(1)
    elif args.command == "fail-index":
        entries = integrator.show_fail_index(args.file)
        if entries:
            print(f"[RSI] FAIL-index entries for {args.file}:")
            for e in entries[:5]:
                print(f"  {e}")
        else:
            print(f"[RSI] No FAIL-index entries for {args.file}")
    elif args.command == "wrap":
        sys.exit(integrator.interactive_wrap(args.command))


if __name__ == "__main__":
    main()