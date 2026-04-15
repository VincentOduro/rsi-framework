#!/bin/bash
# bootstrap.sh — One-command RSI framework installation for any project.
#
# Run from within your project directory (or let Claude Code run it):
#
#   curl -sL https://raw.githubusercontent.com/VincentOduro/rsi-framework/main/bootstrap.sh | bash
#
# Or if you already cloned the framework:
#
#   bash /path/to/rsi-framework/bootstrap.sh
#
# What it does:
#   1. Clones rsi-framework into .rsi-source/ (or uses existing clone)
#   2. Copies scripts/, adapters/, engine/, MEMORY_TEMPLATE/, CLAUDE.md into your project
#   3. Runs setup.py --model claude (installs git hooks + Claude Code hooks)
#   4. Initializes .memory/ from MEMORY_TEMPLATE
#   5. Creates .rsi/architecture.yaml for overlord-worker delegation
#   6. Starts an RSI session
#
# After this, Claude Code enforces TPS discipline automatically.
# Zero manual steps.

set -e

GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[91m'
BOLD='\033[1m'
RESET='\033[0m'

PROJECT_ROOT="$(pwd)"
RSI_SOURCE="$PROJECT_ROOT/.rsi-source"
RSI_REPO="https://github.com/VincentOduro/rsi-framework.git"

echo ""
echo "${BOLD}========================================${RESET}"
echo "${BOLD}RSI Framework — Bootstrap${RESET}"
echo "${BOLD}========================================${RESET}"
echo ""
echo "Project: $PROJECT_ROOT"
echo ""

# ---- Step 1: Get the framework source ----
echo "${YELLOW}[1/6] Getting framework source...${RESET}"

# Check if this script is being run FROM the rsi-framework repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
if [ -f "$SCRIPT_DIR/FRAMEWORK.md" ] && [ -d "$SCRIPT_DIR/scripts" ]; then
    RSI_SOURCE="$SCRIPT_DIR"
    echo "  Using local source: $RSI_SOURCE"
elif [ -d "$RSI_SOURCE" ] && [ -f "$RSI_SOURCE/FRAMEWORK.md" ]; then
    echo "  Using existing clone: $RSI_SOURCE"
else
    echo "  Cloning from $RSI_REPO..."
    git clone --depth 1 "$RSI_REPO" "$RSI_SOURCE" 2>/dev/null
    echo "  Cloned to $RSI_SOURCE"
fi

# ---- Step 2: Copy framework files ----
echo ""
echo "${YELLOW}[2/6] Installing framework files...${RESET}"

# Copy directories (preserve existing if present)
for dir in scripts adapters engine; do
    if [ -d "$RSI_SOURCE/$dir" ]; then
        if [ -d "$PROJECT_ROOT/$dir" ]; then
            # Merge — don't overwrite existing project scripts
            cp -rn "$RSI_SOURCE/$dir/"* "$PROJECT_ROOT/$dir/" 2>/dev/null || \
            cp -r "$RSI_SOURCE/$dir/"* "$PROJECT_ROOT/$dir/" 2>/dev/null || true
        else
            cp -r "$RSI_SOURCE/$dir" "$PROJECT_ROOT/$dir"
        fi
        echo "  ✓ $dir/"
    fi
done

# Copy standalone files
for file in CLAUDE.md conftest.py PROOF_WRONG_GUIDE.md; do
    if [ -f "$RSI_SOURCE/$file" ] && [ ! -f "$PROJECT_ROOT/$file" ]; then
        cp "$RSI_SOURCE/$file" "$PROJECT_ROOT/$file"
        echo "  ✓ $file"
    elif [ -f "$PROJECT_ROOT/$file" ]; then
        echo "  ✓ $file (already exists, kept)"
    fi
done

# Copy MEMORY_TEMPLATE if not present
if [ ! -d "$PROJECT_ROOT/MEMORY_TEMPLATE" ] && [ -d "$RSI_SOURCE/MEMORY_TEMPLATE" ]; then
    cp -r "$RSI_SOURCE/MEMORY_TEMPLATE" "$PROJECT_ROOT/MEMORY_TEMPLATE"
    echo "  ✓ MEMORY_TEMPLATE/"
fi

# ---- Step 3: Initialize .memory ----
echo ""
echo "${YELLOW}[3/6] Initializing memory system...${RESET}"

if [ -d "$PROJECT_ROOT/.memory" ]; then
    echo "  ✓ .memory/ already exists"
else
    cp -r "$PROJECT_ROOT/MEMORY_TEMPLATE" "$PROJECT_ROOT/.memory"
    echo "  ✓ .memory/ created from template"
fi

# ---- Step 4: Set up .rsi directory ----
echo ""
echo "${YELLOW}[4/6] Setting up delegation config...${RESET}"

mkdir -p "$PROJECT_ROOT/.rsi/tasks"
mkdir -p "$PROJECT_ROOT/.memory/reviews/pending"
mkdir -p "$PROJECT_ROOT/.memory/reviews/accepted"
mkdir -p "$PROJECT_ROOT/.memory/reviews/rejected"
mkdir -p "$PROJECT_ROOT/.memory/metrics"
mkdir -p "$PROJECT_ROOT/.memory/calibration"

if [ ! -f "$PROJECT_ROOT/.rsi/architecture.yaml" ] && [ -f "$RSI_SOURCE/.rsi/architecture.yaml" ]; then
    cp "$RSI_SOURCE/.rsi/architecture.yaml" "$PROJECT_ROOT/.rsi/architecture.yaml"
    echo "  ✓ .rsi/architecture.yaml"
else
    echo "  ✓ .rsi/architecture.yaml (already exists)"
fi

# ---- Step 5: Run setup for Claude Code ----
echo ""
echo "${YELLOW}[5/6] Installing hooks...${RESET}"

python3 "$PROJECT_ROOT/scripts/setup.py" --model claude --skip-memory 2>&1 | sed 's/^/  /'

# ---- Step 6: Start session ----
echo ""
echo "${YELLOW}[6/6] Starting RSI session...${RESET}"

python3 "$PROJECT_ROOT/scripts/preflight_check.py" --start 2>&1 | sed 's/^/  /'

# ---- Done ----
echo ""
echo "${BOLD}========================================${RESET}"
echo "${GREEN}✓ RSI Framework installed and active${RESET}"
echo "${BOLD}========================================${RESET}"
echo ""
echo "What's enforced now:"
echo "  • Read-before-edit (Claude Code hook blocks edits to unread files)"
echo "  • --no-verify blocked (git commit safety)"
echo "  • Session tracking (24h TTL)"
echo "  • FAIL-index surfaced on every edit"
echo ""
echo "Commands:"
echo "  python3 scripts/rsi.py dashboard       # Andon board"
echo "  python3 scripts/rsi.py ceremony         # Check ceremony level"
echo "  python3 scripts/rsi.py loop             # Full A→B→C loop"
echo "  python3 scripts/rsi.py delegate <task>  # Send to MiniMax worker"
echo "  python3 scripts/rsi.py status           # Quick check"
echo ""
echo "CLAUDE.md is loaded. Hooks are active. Go build."
echo ""
