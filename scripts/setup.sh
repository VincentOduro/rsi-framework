#!/bin/bash
# setup.sh — Install RSI framework hooks system-wide via git template
# ONE-TIME SETUP: Run once on a machine. Hooks then work automatically for every clone.
# 
# What it does:
# - Installs hooks to ~/.git_template/hooks/ (git's template directory)
# - Every `git clone` or `git init` automatically gets these hooks
# - Creates ~/.memory/rsi/ as the framework home (optional shared memory)
# - Adds rsi-framework alias for quick access
#
# To undo: rm -rf ~/.git_template/hooks/rsi-* ~/.memory/rsi/

set -e

TEMPLATE_HOOKS="$HOME/.git_template/hooks"
RSI_HOOKS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/git-hooks"
MEMORY_HOME="$HOME/.memory/rsi"

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
