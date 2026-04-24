#!/bin/bash
# Pre-commit hook: Run pytest before allowing commits to executor code
# Blocks commits if any executor Python files are changed AND tests fail.

EXECUTOR_DIR="forward_5/executor"

# Check if any executor files are in the commit
STAGED=$(git diff --cached --name-only | grep -c "$EXECUTOR_DIR" || true)

if [ "$STAGED" -eq 0 ]; then
    # No executor files changed — skip tests
    exit 0
fi

echo "🔍 Executor files changed — running test suite..."

# Run pytest from the executor directory
REPO_ROOT=$(git rev-parse --show-toplevel)
RESULT=$(cd "$REPO_ROOT/$EXECUTOR_DIR" && python3 -m pytest tests/ -q --tb=line 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Test suite FAILED! Fix before committing:"
    echo "$RESULT" | tail -20
    echo ""
    echo "💡 To skip (NOT recommended): git commit --no-verify"
    exit 1
fi

echo "✅ All tests passed — proceeding with commit"
exit 0