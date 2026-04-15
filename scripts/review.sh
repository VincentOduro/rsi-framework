#!/bin/bash
# review.sh — Session review
# Run to review current state and identify what needs attention.

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================================"
echo "WANDERING CODEX — SESSION REVIEW"
echo "============================================================"
echo ""

# 1. Current round progress
echo "[1] Current round progress:"
echo "------------------------------------------------------------"
if ls .memory/rounds/round-*.md 1> /dev/null 2>&1; then
    LATEST=$(ls -t .memory/rounds/round-*.md | head -1)
    if [ -n "$LATEST" ]; then
        echo "  File: $LATEST"
        STATUS=$(grep "^Status:" "$LATEST" 2>/dev/null | head -1 || echo "Status: unknown")
        echo "  $STATUS"
        echo ""
        echo "  Last 5 implementation entries:"
        grep -B1 "## Results" "$LATEST" 2>/dev/null | tail -10 || echo "    (none)"
    fi
else
    echo "  No rounds found"
fi

# 2. Priority issues from self-optimization
echo ""
echo "[2] Priority issues (from current-task.md):"
echo "------------------------------------------------------------"
if [ -f ".memory/agents/current-task.md" ]; then
    grep -E "^\- \[ \]" .memory/agents/current-task.md 2>/dev/null | head -10 | sed 's/- \[ \]/  - /' || echo "  No pending tasks"
else
    echo "  No task tracker"
fi

# 3. Unconfirmed feedback
echo ""
echo "[3] Unconfirmed issues needing review:"
echo "------------------------------------------------------------"
if [ -f ".memory/technical/feedback-log.md" ]; then
    UNCONFIRMED=$(grep -B1 "UNCONFIRMED" .memory/technical/feedback-log.md 2>/dev/null | grep -v "^--$" | grep -v "UNCONFIRMED" | head -10)
    if [ -n "$UNCONFIRMED" ]; then
        echo "$UNCONFIRMED" | sed 's/^/  /'
    else
        echo "  No unconfirmed issues"
    fi
else
    echo "  No feedback log"
fi

# 4. CODE_REVIEW.md open findings
echo ""
echo "[4] Top open CODE_REVIEW.md findings:"
echo "------------------------------------------------------------"
if [ -f "docs/CODE_REVIEW.md" ]; then
    grep -E "^\| C-" docs/CODE_REVIEW.md 2>/dev/null | grep "OPEN" | head -5 | sed 's/| C-/  C-/g'
else
    echo "  CODE_REVIEW.md not found"
fi

# 5. What needs attention
echo ""
echo "[5] What needs attention today:"
echo "------------------------------------------------------------"
if [ -f ".memory/agents/current-task.md" ]; then
    # Show tasks that mention REVIEW (from unconfirmed feedback)
    REVIEW_TASKS=$(grep -E "^\- \[ \].*REVIEW" .memory/agents/current-task.md 2>/dev/null | sed 's/- \[ \]/  - /')
    if [ -n "$REVIEW_TASKS" ]; then
        echo "  Unconfirmed issues requiring verification:"
        echo "$REVIEW_TASKS"
    else
        echo "  No unconfirmed issues requiring immediate attention"
    fi
fi

# 6. Recent test results
echo ""
echo "[6] Last test run: $(python3 -m pytest tests/ --collect-only -q 2>/dev/null | tail -1 || echo 'unknown')"

echo ""
echo "============================================================"
echo "Suggested actions:"
echo "  1. python3 scripts/self_verify.py --changed-only"
echo "  2. python3 scripts/post_implementation.py --interactive"
echo "  3. python3 scripts/self_feedback.py"
echo "============================================================"
