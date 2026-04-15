#!/bin/bash
# init.sh — Start of session initialization
# Run at the start of every session.

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================================"
echo "WANDERING CODEX — SESSION INITIALIZATION"
echo "============================================================"
echo ""

# 1. Create necessary directories
echo "[1] Ensuring .memory directory structure exists..."
mkdir -p .memory/rounds .memory/technical .memory/agents scripts
echo "     Done."

# 2. Show current task status
echo ""
echo "[2] Current task status:"
echo "------------------------------------------------------------"
if [ -f "MEMORY.md" ]; then
    # Extract quick reference section
    grep -A 10 "Quick Reference" MEMORY.md 2>/dev/null || echo "  (no Quick Reference section found)"
else
    echo "  MEMORY.md not found"
fi

# 3. Show pending tasks
echo ""
echo "[3] Pending tasks:"
echo "------------------------------------------------------------"
if [ -f ".memory/agents/current-task.md" ]; then
    grep -E "^\- \[ \]" .memory/agents/current-task.md 2>/dev/null | sed 's/- \[ \]/  - /' || echo "  No pending tasks"
else
    echo "  No task tracker found"
fi

# 4. Show recent learnings
echo ""
echo "[4] Recent learnings from last session:"
echo "------------------------------------------------------------"
if ls .memory/rounds/round-*.md 1> /dev/null 2>&1; then
    LATEST=$(ls -t .memory/rounds/round-*.md | head -1)
    if [ -n "$LATEST" ]; then
        echo "  File: $LATEST"
        echo ""
        grep -A 10 "## Learnings" "$LATEST" 2>/dev/null | head -15 || echo "  (no learnings section)"
    fi
else
    echo "  No round files found"
fi

# 5. Show FAIL index
echo ""
echo "[5] FAIL index (cite by ID before making risky claims):"
echo "------------------------------------------------------------"
if [ -f ".memory/technical/FAIL-index.md" ]; then
    grep "^| FAIL-" .memory/technical/FAIL-index.md 2>/dev/null || echo "  (empty)"
else
    echo "  FAIL-index.md not found"
fi

# 6. Show pending follow-ups
echo ""
echo "[6] Pending follow-ups from feedback log:"
echo "------------------------------------------------------------"
if [ -f ".memory/technical/feedback-log.md" ]; then
    UNCONFIRMED=$(grep -c "UNCONFIRMED" .memory/technical/feedback-log.md 2>/dev/null || echo "0")
    echo "  Unconfirmed issues: $UNCONFIRMED"
    grep "UNCONFIRMED" .memory/technical/feedback-log.md 2>/dev/null | head -5 | sed 's/^/    /'
else
    echo "  No feedback log found"
fi

echo ""
echo "============================================================"
echo "Ready. Suggested next step:"
echo "  python3 scripts/post_implementation.py --interactive"
echo "  or"
echo "  python3 scripts/review.sh"
echo "============================================================"
