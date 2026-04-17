#!/usr/bin/env python3
"""
hookd.py -- RSI hook daemon. Persistent Python process on TCP socket.

Eliminates cold-start latency by keeping all hook logic loaded in memory.
Claude Code tool calls go through a thin client that connects to this daemon
instead of spawning a new Python process each time.

Architecture:
    rsi.py init  -->  starts hookd.py in background
    Claude Code  -->  hook_client connects to localhost:PORT
                      sends JSON, gets response, exits
    rsi.py checkpoint  -->  sends shutdown to daemon

Protocol:
    Client sends one line of JSON:
        {"action": "pre-edit", "tool_input": {"file_path": "/path/to/file"}}

    Daemon responds with one line:
        {"exit_code": 0, "stdout": "", "stderr": ""}
    or:
        {"exit_code": 1, "stdout": "[RSI] BLOCKED: ...", "stderr": ""}

    Then closes the connection.

Usage:
    python3 scripts/hookd.py start           # Start daemon (foreground)
    python3 scripts/hookd.py start --bg      # Start daemon (background)
    python3 scripts/hookd.py stop            # Stop daemon
    python3 scripts/hookd.py status          # Check if running
    python3 scripts/hookd.py --port 9751     # Custom port
"""

import argparse
import io
import json
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_PORT = 9751
PID_FILE = PROJECT_ROOT / ".memory" / ".hookd.pid"
PORT_FILE = PROJECT_ROOT / ".memory" / ".hookd.port"

# Pre-load ALL hook logic at startup — this is the whole point
# These imports happen ONCE, not per-call
from scripts.hooks import (
    _cache,
    handle_post_edit,
    handle_pre_bash,
    handle_pre_edit,
    handle_pre_read,
)


def _handle_request(action: str, tool_input: dict) -> tuple[int, str]:
    """Execute hook logic and capture stdout + exit code.

    Returns (exit_code, stdout_output).
    """
    # Clear per-invocation cache (simulates fresh process)
    _cache.clear()

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()

    exit_code = 0
    try:
        handlers = {
            "pre-read": handle_pre_read,
            "pre-edit": handle_pre_edit,
            "post-edit": handle_post_edit,
            "pre-bash": handle_pre_bash,
        }
        handler = handlers.get(action)
        if handler:
            handler(tool_input)
        else:
            print(f"Unknown action: {action}")
            exit_code = 1
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 1
    except Exception as e:
        print(f"[RSI] Hook error: {e}")
        exit_code = 1
    finally:
        sys.stdout = old_stdout

    return exit_code, captured.getvalue()


def _handle_client(conn: socket.socket, addr: tuple) -> None:
    """Handle one client connection."""
    try:
        # Read the full request (one line of JSON)
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break

        if not data:
            return

        # Parse request
        try:
            request = json.loads(data.decode("utf-8").strip())
        except (json.JSONDecodeError, UnicodeDecodeError):
            response = {"exit_code": 1, "stdout": "[RSI] Invalid JSON request\n"}
            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
            return

        action = request.get("action", "")
        tool_input = request.get("tool_input", request)

        # Execute hook logic
        exit_code, stdout = _handle_request(action, tool_input)

        # Send response
        response = {"exit_code": exit_code, "stdout": stdout}
        conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        conn.close()


def start_daemon(port: int = DEFAULT_PORT, foreground: bool = True) -> None:
    """Start the hook daemon on TCP localhost:port."""
    # Check if already running
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            # Check if process is alive (cross-platform)
            os.kill(pid, 0)
            print(f"Daemon already running (PID {pid}, port {_read_port()})")
            return
        except (OSError, ValueError):
            # Stale PID file
            PID_FILE.unlink(missing_ok=True)

    # Bind socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", port))
    except OSError as e:
        print(f"Cannot bind to port {port}: {e}")
        sys.exit(1)
    server.listen(5)
    server.settimeout(1.0)  # Allow periodic shutdown check

    # Write PID and port files
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    PORT_FILE.write_text(str(port))

    print(f"[RSI] Hook daemon started on localhost:{port} (PID {os.getpid()})")

    # Shutdown flag
    shutdown = threading.Event()

    def signal_handler(sig, frame):
        shutdown.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Accept loop
    try:
        while not shutdown.is_set():
            try:
                conn, addr = server.accept()
                # Handle each client in a thread (allows concurrent hooks)
                thread = threading.Thread(target=_handle_client, args=(conn, addr), daemon=True)
                thread.start()
            except TimeoutError:
                continue
            except OSError:
                break
    finally:
        server.close()
        PID_FILE.unlink(missing_ok=True)
        PORT_FILE.unlink(missing_ok=True)
        print("[RSI] Hook daemon stopped")


def stop_daemon() -> None:
    """Stop the running daemon."""
    if not PID_FILE.exists():
        print("No daemon running (no PID file)")
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"Daemon stopped (PID {pid})")
    except (OSError, ValueError) as e:
        print(f"Could not stop daemon: {e}")
    finally:
        PID_FILE.unlink(missing_ok=True)
        PORT_FILE.unlink(missing_ok=True)


def daemon_status() -> dict:
    """Check daemon status. Returns status dict."""
    if not PID_FILE.exists():
        return {"running": False, "reason": "no PID file"}

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # Check if alive
        port = _read_port()
        return {"running": True, "pid": pid, "port": port}
    except (OSError, ValueError):
        return {"running": False, "reason": "stale PID file"}


def _read_port() -> int:
    if PORT_FILE.exists():
        try:
            return int(PORT_FILE.read_text().strip())
        except ValueError:
            pass
    return DEFAULT_PORT


# ---------------------------------------------------------------------------
# Client function (used by hook_client.py and for testing)
# ---------------------------------------------------------------------------


def send_to_daemon(action: str, tool_input: dict, port: int | None = None) -> tuple[int, str]:
    """Send a request to the daemon and return (exit_code, stdout).

    This is the fast path — connect to running daemon, send JSON, get response.
    No Python boot, no imports. Just socket I/O.
    """
    if port is None:
        port = _read_port()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(("127.0.0.1", port))

        request = json.dumps({"action": action, "tool_input": tool_input}) + "\n"
        sock.sendall(request.encode("utf-8"))

        # Read response
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk

        sock.close()

        response = json.loads(data.decode("utf-8").strip())
        return response.get("exit_code", 0), response.get("stdout", "")

    except (TimeoutError, ConnectionRefusedError):
        return 1, "[RSI] Hook daemon not running. Start with: python3 scripts/hookd.py start\n"
    except Exception as e:
        return 1, f"[RSI] Daemon communication error: {e}\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="RSI Hook Daemon")
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["start", "stop", "status"],
        help="start|stop|status",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"TCP port (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--bg", action="store_true", help="Start in background (detach from terminal)"
    )

    args = parser.parse_args()

    if args.command == "start":
        if args.bg:
            # Fork to background (Unix) or use subprocess (Windows)
            import subprocess

            proc = subprocess.Popen(
                [sys.executable, __file__, "start", "--port", str(args.port)],
                cwd=PROJECT_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(0.5)  # Wait for daemon to bind
            status = daemon_status()
            if status["running"]:
                print(
                    f"[RSI] Hook daemon started in background (PID {status['pid']}, port {status['port']})"
                )
            else:
                print("[RSI] Failed to start daemon in background")
        else:
            start_daemon(args.port)

    elif args.command == "stop":
        stop_daemon()

    elif args.command == "status":
        status = daemon_status()
        if status["running"]:
            print(f"Daemon running (PID {status['pid']}, port {status['port']})")
        else:
            print(f"Daemon not running ({status.get('reason', 'unknown')})")


if __name__ == "__main__":
    main()
