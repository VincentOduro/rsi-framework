#!/bin/bash
# install_hooks.sh — Install git hooks for Wandering Codex
# Run once after cloning: bash scripts/install_hooks.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

HOOKS_DIR="$PROJECT_ROOT/.git/hooks"

echo "Installing git hooks for Wandering Codex..."
echo ""

for hook in scripts/git-hooks/*; do
    name=$(basename "$hook")
    target="$HOOKS_DIR/$name"
    if [ -f "$target" ] && [ ! -L "$target" ]; then
        echo "  ✗ $name already exists (not a symlink). Backup or remove first."
    else
        ln -sf "../../$hook" "$target"
        echo "  ✓ Installed: $name"
    fi
done

echo ""
echo "Done. Hooks will run on every commit."
echo "To uninstall: rm .git/hooks/pre-commit .git/hooks/commit-msg"
