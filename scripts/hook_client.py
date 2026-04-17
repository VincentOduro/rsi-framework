#!/usr/bin/env python3
"""
hook_client.py -- Thin client for the RSI hook daemon.

Connects to hookd.py over TCP, sends the tool input, prints the response,
exits with the daemon's exit code. This replaces `hooks.py` in
.claude/settings.json when daemon mode is active.

The ENTIRE purpose of this file is to be as fast as possible.
Minimal imports. No project imports. Just socket I/O.

Usage (called by Claude Code via .claude/settings.json):
    echo '{"tool_input": {...}}' | python3 scripts/hook_client.py pre-edit

If the daemon is not running, falls back to calling hooks.py directly.
"""

import json
import socket
import subprocess
import sys

# Hardcoded defaults — no project imports to keep startup fast
DEFAULT_PORT = 9751
PORT_FILE_RELATIVE = ".memory/.hookd.port"


def main():
    if len(sys.argv) < 2:
        print("Usage: hook_client.py <pre-edit|post-edit|pre-read|pre-bash>", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]

    # Read tool input from stdin
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            tool_input = data.get("tool_input", data)
        else:
            tool_input = {}
    except (json.JSONDecodeError, IOError):
        tool_input = {}

    # Try to read port from port file (fast — no imports needed)
    port = DEFAULT_PORT
    try:
        with open(PORT_FILE_RELATIVE) as f:
            port = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        pass

    # Connect to daemon
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect(("127.0.0.1", port))

        request = json.dumps({"action": action, "tool_input": tool_input}) + "\n"
        sock.sendall(request.encode("utf-8"))

        # Shutdown write side to signal end of request
        sock.shutdown(socket.SHUT_WR)

        # Read response
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk

        sock.close()

        response = json.loads(data.decode("utf-8").strip())
        stdout = response.get("stdout", "")
        if stdout:
            print(stdout, end="")
        sys.exit(response.get("exit_code", 0))

    except ConnectionRefusedError:
        # Daemon not running — fall back to direct hooks.py call
        # This is slow (~189ms) but ensures correctness
        result = subprocess.run(
            [sys.executable, "scripts/hooks.py", action],
            input=json.dumps({"tool_input": tool_input}),
            capture_output=True, text=True, timeout=30,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        sys.exit(result.returncode)

    except socket.timeout:
        # Daemon hung — fall back
        print("[RSI] Hook daemon timeout. Falling back to direct mode.", file=sys.stderr)
        result = subprocess.run(
            [sys.executable, "scripts/hooks.py", action],
            input=json.dumps({"tool_input": tool_input}),
            capture_output=True, text=True, timeout=30,
        )
        if result.stdout:
            print(result.stdout, end="")
        sys.exit(result.returncode)

    except Exception as e:
        print(f"[RSI] Hook client error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
