#!/bin/bash
# opencode_adapter.sh — Shell wrapper for opencode/MiniMax-M2.7 integration
#
# This wrapper intercepts opencode's file operations and enforces RSI framework rules.
# It works by wrapping the opencode command and monitoring its inputs.
#
# Usage:
#   # Option 1: Direct wrapper (add to PATH)
#   alias opencode='./scripts/adapters/opencode_adapter.sh'
#
#   # Option 2: Wrapper script in project root
#   cp scripts/adapters/opencode_adapter.sh ./opencode_wrapper.sh
#   chmod +x ./opencode_wrapper.sh
#   alias opencode='./opencode_wrapper.sh'
#
#   # Option 3: Via environment variable (if opencode supports it)
#   export OPENCODE_HOOK_COMMAND="./scripts/adapters/opencode_adapter.sh"
#
# Requirements:
#   - bash >= 4.0
#   - python3 with RSI framework installed
#   - RSI_PROJECT_ROOT set or auto-detected

set -e

# Resolve script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RSI_FRAMEWORK_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Auto-detect PROJECT_ROOT if not set
if [ -z "$RSI_PROJECT_ROOT" ]; then
    RSI_PROJECT_ROOT="$RSI_FRAMEWORK_DIR"
fi

# Colors
RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
RESET='\033[0m'

# ============================================================================
# Helper Functions
# ============================================================================

rsi_hook() {
    local action="$1"
    local file="$2"
    python3 -B "$RSI_FRAMEWORK_DIR/scripts/universal_hook.py" opencode "$action" --file "$file" 2>&1
}

check_session() {
    python3 -B "$RSI_FRAMEWORK_DIR/scripts/universal_hook.py" opencode session-check 2>&1
    return $?
}

# ============================================================================
# Pre-operation Checks
# ============================================================================

pre_read() {
    local file="$1"
    if [ -z "$file" ]; then
        return 0
    fi
    rsi_hook pre-read "$file" || true
}

pre_edit() {
    local file="$1"
    if [ -z "$file" ]; then
        return 0
    fi

    # Run the pre-edit check - will exit 1 if blocked
    if ! rsi_hook pre-edit "$file"; then
        echo "${RED}[RSI] Edit blocked: file not read before editing${RESET}"
        return 1
    fi
    echo "${GREEN}[RSI] Edit allowed${RESET}"
    return 0
}

pre_bash() {
    local command="$1"
    if [ -z "$command" ]; then
        return 0
    fi
    python3 -B "$RSI_FRAMEWORK_DIR/scripts/universal_hook.py" opencode pre-bash --command "$command" 2>&1
    return $?
}

# ============================================================================
# Post-operation Recording
# ============================================================================

post_edit() {
    local file="$1"
    if [ -z "$file" ]; then
        return 0
    fi
    rsi_hook post-edit "$file" || true
}

# ============================================================================
# Command Parsing for opencode
# ============================================================================
# opencode is a CLI tool. We need to intercept commands that read or write files.
# Common opencode commands that affect files:
#   opencode read <file>           - Read a file
#   opencode edit <file> ...       - Edit a file
#   opencode write <file> ...      - Write a file
#   opencode apply <patch>         - Apply a patch
#   opencode --help                - Help (no file ops)

parse_and_intercept() {
    local cmd="$1"
    shift

    local subcmd=""
    local file=""

    # Parse common opencode command patterns
    while [ $# -gt 0 ]; do
        case "$1" in
            read|edit|write|apply)
                subcmd="$1"
                file="$2"
                shift 2
                ;;
            -f|--file)
                file="$2"
                shift 2
                ;;
            -*)
                shift
                ;;
            *)
                if [ -z "$subcmd" ] && [ -f "$1" ]; then
                    file="$1"
                fi
                shift
                ;;
        esac
    done

    # Handle by subcommand
    case "$subcmd" in
        read)
            pre_read "$file"
            ;;
        edit|write|apply)
            # Pre-edit check
            if ! pre_edit "$file"; then
                return 1
            fi
            # Run the actual opencode command
            opencode_orig "$@"
            local result=$?
            # Post-edit recording
            post_edit "$file"
            return $result
            ;;
        *)
            # Unknown command, just pass through
            opencode_orig "$@"
            return $?
            ;;
    esac
}

# ============================================================================
# Main Wrapper Logic
# ============================================================================

# Find the real opencode command
find_opencode() {
    # Check if opencode is available
    if command -v opencode &> /dev/null; then
        echo "opencode"
    elif [ -x "/usr/local/bin/opencode" ]; then
        echo "/usr/local/bin/opencode"
    elif [ -x "$HOME/.local/bin/opencode" ]; then
        echo "$HOME/.local/bin/opencode"
    else
        echo ""
    fi
}

# Main entry point when this script IS the wrapper
if [ -z "$OPENCODE_WRAPPER_ACTIVE" ]; then
    export OPENCODE_WRAPPER_ACTIVE=1

    OPENCODE_REAL="$(find_opencode)"

    if [ -z "$OPENCODE_REAL" ]; then
        echo "Error: opencode command not found. Install opencode first."
        echo "Or set the path to opencode manually:"
        echo "  export OPENCODE_PATH=/path/to/opencode"
        exit 1
    fi

    # Check session first
    if ! check_session; then
        echo "${YELLOW}[RSI] Warning: No active RSI session. Run 'python3 scripts/rsi.py init' first.${RESET}"
        echo "${YELLOW}[RSI] Continuing anyway (hook enforcement may be incomplete)...${RESET}"
    fi

    # For read commands, just record and pass through
    if [ "$1" = "read" ] && [ -n "$2" ]; then
        pre_read "$2"
    fi

    # For edit/write commands, check then execute
    if [ "$1" = "edit" ] || [ "$1" = "write" ] || [ "$1" = "apply" ]; then
        file=""
        if [ "$1" = "apply" ]; then
            file="$2"
        else
            file="$2"
        fi

        if [ -n "$file" ]; then
            if ! pre_edit "$file"; then
                echo "${RED}[RSI] Blocked: Read file before editing${RESET}"
                exit 1
            fi
        fi
    fi

    # Execute the real opencode
    "$OPENCODE_REAL" "$@"
    result=$?

    # Post-edit recording
    if [ "$1" = "edit" ] || [ "$1" = "write" ] || [ "$1" = "apply" ]; then
        file=""
        if [ "$1" = "apply" ]; then
            file="$2"
        else
            file="$2"
        fi
        if [ -n "$file" ]; then
            post_edit "$file" 2>/dev/null || true
        fi
    fi

    exit $result
fi