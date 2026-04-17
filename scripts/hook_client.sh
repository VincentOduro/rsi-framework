#!/bin/bash
# hook_client.sh -- Fast thin client for RSI hook daemon.
#
# Uses bash's built-in /dev/tcp for zero-dependency socket I/O.
# Falls back to direct hooks.py if daemon is not running.
#
# Called by .claude/settings.json:
#   "command": "bash scripts/hook_client.sh pre-edit"

ACTION="${1:-pre-read}"
PORT=$(cat .memory/.hookd.port 2>/dev/null || echo 9751)

# Read stdin (tool input from Claude Code)
INPUT=$(cat)
if [ -z "$INPUT" ]; then
    INPUT='{}'
fi

# Build request JSON
REQUEST="{\"action\":\"$ACTION\",\"tool_input\":$INPUT}"

# Try daemon via /dev/tcp
exec 3<>/dev/tcp/127.0.0.1/$PORT 2>/dev/null

if [ $? -eq 0 ]; then
    # Daemon available — send request
    echo "$REQUEST" >&3

    # Read response (one line of JSON)
    RESPONSE=""
    while IFS= read -r -t 5 line <&3; do
        RESPONSE="$line"
        break
    done
    exec 3<&- 2>/dev/null

    # Parse response with pure bash — extract exit_code and stdout
    # Response format: {"exit_code": N, "stdout": "..."}
    # Extract exit_code (number after "exit_code":)
    EXIT_CODE=$(echo "$RESPONSE" | grep -o '"exit_code": *[0-9]*' | grep -o '[0-9]*')
    EXIT_CODE=${EXIT_CODE:-0}

    # Extract stdout (string between "stdout": " and next ")
    # Handle escaped quotes in stdout by extracting everything after "stdout": "
    STDOUT=$(echo "$RESPONSE" | sed -n 's/.*"stdout": *"\(.*\)".*/\1/p')

    # Unescape \n in stdout
    if [ -n "$STDOUT" ]; then
        echo -ne "$STDOUT"
    fi

    exit $EXIT_CODE
else
    # Daemon not running — fall back to direct hooks.py
    echo "$INPUT" | python3 scripts/hooks.py "$ACTION"
    exit $?
fi
