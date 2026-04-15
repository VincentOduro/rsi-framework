#!/bin/bash
# checkpoint.sh — End-of-session checkpoint
# Run at the end of every session.

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================================"
echo "WANDERING CODEX — END-OF-SESSION CHECKPOINT"
echo "============================================================"
echo ""

# 1. Run tests to confirm state
echo "[1] Running test suite to confirm state..."
echo "------------------------------------------------------------"
TEST_RESULT=$(python3 -m pytest tests/ -v --tb=short -q 2>&1)
TEST_SUMMARY=$(echo "$TEST_RESULT" | grep -E "^=+.*passed" | tail -1)
echo "  $TEST_SUMMARY"
echo ""

# 2. Check git status
echo "[2] Git status:"
echo "------------------------------------------------------------"
git status --short 2>/dev/null | head -20 || echo "  Not a git repo"
echo ""

# 3. Prompt for session summary
echo "[3] Session summary (for round log):"
echo "------------------------------------------------------------"
echo "  What did we accomplish this session?"
read -r ACCOMPLISHED
echo ""
echo "  What didn't get done?"
read -r PENDING
echo ""
echo "  Key learnings or insights?"
read -r LEARNINGS
echo ""

# 4. Update current round log
if ls .memory/rounds/round-*.md 1> /dev/null 2>&1; then
    LATEST=$(ls -t .memory/rounds/round-*.md | head -1)
    if [ -n "$LATEST" ]; then
        echo "[4] Updating round log: $LATEST"
        echo ""

        # Append session summary to round log
        {
            echo ""
            echo "### Session Summary — $(date '+%Y-%m-%d')"
            echo "**Accomplished:** $ACCOMPLISHED"
            echo "**Pending:** $PENDING"
            echo "**Learnings:** $LEARNINGS"
            echo "**Test result:** $TEST_SUMMARY"
            echo ""
            echo "**Files changed:**"
            git diff --name-only HEAD 2>/dev/null | sed 's/^/  - /'
        } >> "$LATEST"
        echo "  Round log updated."
    fi
fi

# 5. Prompt for next session tasks
echo ""
echo "[5] Next session tasks (one per line, empty to finish):"
NEXT_TASKS=""
while true; do
    read -r TASK
    if [ -z "$TASK" ]; then
        break
    fi
    NEXT_TASKS="$NEXT_TASKS\n- [ ] $TASK"
done

if [ -n "$NEXT_TASKS" ]; then
    TASK_FILE=".memory/agents/current-task.md"
    if [ ! -f "$TASK_FILE" ]; then
        echo "# Current Task" > "$TASK_FILE"
        echo "" >> "$TASK_FILE"
        echo "## Active Tasks" >> "$TASK_FILE"
        echo "" >> "$TASK_FILE"
    fi
    echo -e "$NEXT_TASKS" >> "$TASK_FILE"
    echo "  Tasks saved to current-task.md"
fi

# 6. Self-verify on changed files
echo ""
echo "[6] Running self-verify on changed files..."
echo "------------------------------------------------------------"
CHANGED=$(git diff --name-only HEAD 2>/dev/null)
if [ -n "$CHANGED" ]; then
    python3 scripts/self_verify.py --changed-only 2>&1 | tail -5
else
    echo "  No files changed"
fi

# 7. Git commit prompt
echo ""
echo "[7] Git commit?"
echo "------------------------------------------------------------"
echo "  Changed files:"
git diff --name-only HEAD 2>/dev/null | sed 's/^/    /' || echo "    (none)"
echo ""
read -p "  Commit message (or 'skip'): " COMMIT_MSG
if [ "$COMMIT_MSG" != "skip" ] && [ -n "$COMMIT_MSG" ]; then
    git add -A 2>/dev/null
    git commit -m "$COMMIT_MSG" 2>/dev/null && echo "  Committed." || echo "  Commit failed."
elif [ "$COMMIT_MSG" = "skip" ]; then
    echo "  Skipped."
fi

echo ""
echo "============================================================"
echo "CHECKPOINT COMPLETE"
echo "============================================================"
echo "Memory files updated. Ready for next session."
echo ""
echo "To start next session:"
echo "  bash scripts/init.sh"
