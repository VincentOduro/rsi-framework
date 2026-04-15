#!/bin/bash
# ci_check.sh — CI enforcement script (also usable locally)
# Runs in CI and locally to enforce self-improvement infrastructure.

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
RESET='\033[0m'

FAILED=0

echo "============================================================"
echo "CI CHECK — Self-Improvement Infrastructure"
echo "============================================================"
echo ""

# ---- 1. Syntax checks on all Python files ----
echo "[1] Checking Python syntax..."
PY_ERRORS=0
for f in $(find src scripts -name "*.py" -type f 2>/dev/null); do
    if ! python3 -B -m py_compile "$PROJECT_ROOT/$f" 2>/dev/null; then
        echo "  ${RED}✗ Syntax error: $f${RESET}"
        PY_ERRORS=$((PY_ERRORS + 1))
    fi
done
if [ $PY_ERRORS -eq 0 ]; then
    echo "  ${GREEN}✓ All Python files syntactically valid${RESET}"
else
    echo "  ${RED}$PY_ERRORS file(s) with syntax errors${RESET}"
    FAILED=1
fi

# ---- 2. Shell script syntax ----
echo ""
echo "[2] Checking shell script syntax..."
SH_ERRORS=0
for f in scripts/*.sh scripts/git-hooks/*; do
    if [ -f "$f" ] && [ -x "$f" ]; then
        if ! bash -n "$f" 2>/dev/null; then
            echo "  ${RED}✗ Shell syntax error: $f${RESET}"
            SH_ERRORS=$((SH_ERRORS + 1))
        fi
    fi
done
if [ $SH_ERRORS -eq 0 ]; then
    echo "  ${GREEN}✓ All shell scripts syntactically valid${RESET}"
else
    echo "  ${RED}$SH_ERRORS script(s) with syntax errors${RESET}"
    FAILED=1
fi

# ---- 2b. Pre-flight check (CI mode — blocks if files edited without reading) ----
echo ""
echo "[2b] Pre-flight: files read before editing..."
PREFLIGHT_OUTPUT=$(python3 -B scripts/preflight_check.py --ci 2>&1)
PREFLIGHT_EXIT=$?
if [ $PREFLIGHT_EXIT -eq 0 ]; then
    echo "  ${GREEN}✓ Pre-flight passed${RESET}"
else
    echo "  ${RED}✗ Pre-flight failed (files edited without being read)${RESET}"
    echo "$PREFLIGHT_OUTPUT" | grep -E "(EDITED|WARNING)" | head -10
    FAILED=1
fi

# ---- 3. Tests must pass ----
echo ""
echo "[3] Running test suite..."
TEST_OUTPUT=$(python3 -m pytest tests/ -v --tb=short -q 2>&1)
TEST_EXIT=$?
TEST_SUMMARY=$(echo "$TEST_OUTPUT" | grep -E "^=+.*passed" | tail -1)
if [ $TEST_EXIT -eq 0 ]; then
    echo "  ${GREEN}✓ $TEST_SUMMARY${RESET}"
else
    echo "  ${RED}✗ Tests failed${RESET}"
    echo "$TEST_OUTPUT" | tail -5
    FAILED=1
fi

# ---- 4. self_verify must pass on all source ----
echo ""
echo "[4] Running self_verify on all source files..."
SV_OUTPUT=$(python3 -B scripts/self_verify.py --skip-tests 2>&1)
SV_EXIT=$?
if [ $SV_EXIT -eq 0 ]; then
    echo "  ${GREEN}✓ self_verify passed${RESET}"
else
    echo "  ${RED}✗ self_verify failed${RESET}"
    echo "$SV_OUTPUT" | grep -A2 "CHECKS FAILED\|✗" | head -20
    FAILED=1
fi

# ---- 5. Memory infrastructure must be present ----
# Skip if running on the framework repo itself (MEMORY_TEMPLATE exists = source repo)
echo ""
echo "[5] Checking memory infrastructure..."
if [ -f "$PROJECT_ROOT/MEMORY_TEMPLATE/README.md" ]; then
    echo "  ${YELLOW}⚠ Framework source repo — skipping memory infra check${RESET}"
else
    MEMORY_OK=1
    check_file() {
        if [ ! -f "$PROJECT_ROOT/$1" ]; then
            echo "  ${RED}✗ Missing: $1${RESET}"
            MEMORY_OK=0
        fi
    }
    check_file "MEMORY.md"
    check_file ".memory/README.md"
    check_file ".memory/rounds/round-001.md"
    check_file ".memory/technical/decisions.md"
    check_file ".memory/technical/patterns.md"
    check_file ".memory/agents/current-task.md"
    check_file "scripts/post_implementation.py"
    check_file "scripts/self_feedback.py"
    check_file "scripts/self_optimization.py"
    check_file "scripts/init.sh"
    check_file "scripts/review.sh"
    check_file "scripts/checkpoint.sh"
    if [ $MEMORY_OK -eq 1 ]; then
        echo "  ${GREEN}✓ All memory infrastructure files present${RESET}"
    else
        echo "  ${RED}✗ Some memory infrastructure files missing${RESET}"
        FAILED=1
    fi
fi

# ---- 6. No placeholder code in source ----
echo ""
echo "[6] Scanning for placeholder code..."
PLACEHOLDER_FOUND=0
for f in src/**/*.py; do
    if [ -f "$PROJECT_ROOT/$f" ]; then
        for pat in "# TODO" "raise NotImplementedError" "pass  #" "...  # noqa"; do
            if grep -q "$pat" "$PROJECT_ROOT/$f" 2>/dev/null; then
                echo "  ${YELLOW}⚠ $f: contains '$pat'${RESET}"
                PLACEHOLDER_FOUND=1
            fi
        done
    fi
done
if [ $PLACEHOLDER_FOUND -eq 0 ]; then
    echo "  ${GREEN}✓ No placeholder code found${RESET}"
else
    echo "  ${RED}✗ Placeholder code detected — blocking${RESET}"
    FAILED=1
fi

# ---- 7. Scan for hardcoded secrets (memory files + scripts only) ----
# Principle 8: Use only reliable, tested technology
echo ""
echo "[7] Scanning for hardcoded secrets..."
SECRETS_FOUND=0
SECRET_RE="sk-[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{36,}|ghs_[a-zA-Z0-9]{36,}|AIza[a-zA-Z0-9_-]{35,}|-----BEGIN PRIVATE KEY-----"
SKIP_RE="dummy|example|placeholder|your-|test|fake"
for dir in .memory scripts; do
    [ -d "$PROJECT_ROOT/$dir" ] || continue
    while IFS= read -r f; do
        [ -f "$f" ] || continue
        # Skip ci_check.sh (contains regex patterns that look like secrets)
        echo "$f" | grep -q "ci_check.sh$" && continue
        file "$f" | grep -q "text\|ASCII\|UTF" || continue
        while IFS= read -r line; do
            linenum=$(echo "$line" | cut -d: -f1)
            content=$(echo "$line" | cut -d: -f2-)
            # Skip known safe patterns
            echo "$content" | grep -qiE "$SKIP_RE" && continue
            echo "  ${RED}✗ Secret-like pattern in $f:$linenum${RESET}"
            SECRETS_FOUND=1
        done < <(grep -nE "$SECRET_RE" "$f" 2>/dev/null || true)
    done < <(find "$PROJECT_ROOT/$dir" -type f 2>/dev/null)
done

if [ $SECRETS_FOUND -eq 0 ]; then
    echo "  ${GREEN}✓ No hardcoded secrets detected${RESET}"
else
    echo "  ${RED}✗ Hardcoded secrets detected — blocking${RESET}"
    FAILED=1
fi

# ---- Summary ----
echo ""
echo "============================================================"
if [ $FAILED -eq 0 ]; then
    echo "${GREEN}ALL CI CHECKS PASSED${RESET}"
    exit 0
else
    echo "${RED}SOME CI CHECKS FAILED${RESET}"
    exit 1
fi
