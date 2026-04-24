#!/bin/bash
# install-hooks.sh — Install pre-commit hook from tracked source
# Run this after: git clone https://github.com/dpxyz/pecz.git
#
# The pre-commit hook blocks commits if executor tests fail.
# .git/hooks/ is NOT tracked by git, so this must be run manually.

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_SRC="$REPO_ROOT/forward_5/executor/scripts/pre-commit.sh"
HOOK_DST="$REPO_ROOT/.git/hooks/pre-commit"

if [ ! -f "$HOOK_SRC" ]; then
    echo "❌ Hook source not found: $HOOK_SRC"
    echo "   Are you in the pecz repo?"
    exit 1
fi

cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"

echo "✅ Pre-commit hook installed: .git/hooks/pre-commit"
echo "   This will run 'pytest tests/' before any commit touching executor files."
echo ""
echo "To verify: make a deliberate test break and try to commit."