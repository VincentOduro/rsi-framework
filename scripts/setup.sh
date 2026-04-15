#!/bin/bash
# setup.sh — Install RSI framework hooks system-wide via git template
# ONE-TIME SETUP: Run once on a machine. Hooks then work automatically for every clone.
#
# Cross-platform: Linux, macOS, Windows Git Bash
# For PowerShell, use: python setup.py (this script IS the setup.py)
#
# What it does:
# - Installs hooks to ~/.git_template/hooks/ (git's template directory)
# - Every `git clone` or `git init` automatically gets these hooks
#
# To undo: rm -rf ~/.git_template/hooks/rsi-* ~/.memory/rsi/

set -e

# Resolve project root using Python (works on Linux, macOS, Windows Git Bash)
# Falls back to dirname-based resolution if Python not available
if [ -x "$(command -v python3)" ]; then
    RSIFW_SCRIPT_DIR="$(python3 -c "import os; print(os.path.dirname(os.path.realpath('$0')))")"
    RSIFW_PROJECT_ROOT="$(python3 -c "import os; print(os.path.dirname(os.path.realpath('$0')))" | xargs dirname)"
else
    RSIFW_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    RSIFW_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
fi

TEMPLATE_HOOKS="$HOME/.git_template/hooks"
RSI_HOOKS="$RSIFW_PROJECT_ROOT/scripts/git-hooks"

echo "RSI Framework — System-wide Setup"
echo ""

# Verify hooks exist
if [ ! -d "$RSI_HOOKS" ]; then
    echo "Error: hooks not found at $RSI_HOOKS"
    echo "Run from within the rsi-framework directory."
    exit 1
fi

# Create template directory if needed
if [ ! -d "$HOME/.git_template" ]; then
    mkdir -p "$HOME/.git_template"
    echo "  Created ~/.git_template/"
fi

# Install hooks
if [ -d "$TEMPLATE_HOOKS" ]; then
    echo "  Hooks already installed at $TEMPLATE_HOOKS"
    echo "  (Overwriting with latest version)"
fi

mkdir -p "$TEMPLATE_HOOKS"
cp "$RSI_HOOKS"/* "$TEMPLATE_HOOKS/"
chmod +x "$TEMPLATE_HOOKS"/*

echo "  ✓ Hooks installed to ~/.git_template/hooks/"
echo ""

# Show what was installed
echo "Installed hooks:"
for h in "$TEMPLATE_HOOKS"/*; do
    echo "  - $(basename "$h")"
done
echo ""

# Verify
echo "Verifying hooks are executable:"
TEST_HOOK="$TEMPLATE_HOOKS/pre-commit"
if [ -x "$TEST_HOOK" ]; then
    echo "  ✓ pre-commit is executable"
else
    echo "  ✗ pre-commit is NOT executable"
    exit 1
fi

echo ""
echo "✓ Setup complete."
echo ""
echo "After this, every new clone will automatically have these hooks:"
echo "  - pre-commit: runs pre-flight + self-verify before commit"
echo "  - commit-msg: blocks commit without memory update"
echo ""
echo "For existing repos, apply hooks manually:"
echo "  git config core.hooksPath ~/.git_template/hooks"
echo ""
echo "To create a new project with hooks:"
echo "  git clone --template=\$HOME/.git_template YOUR_REPO_URL"
echo ""
echo "Or clone normally, then in the new repo:"
echo "  git config core.hooksPath \$HOME/.git_template/hooks"
