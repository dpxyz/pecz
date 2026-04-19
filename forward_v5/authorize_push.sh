#!/bin/bash
# OpenClaw Push Authorization Script
# Creates the authorization token required by pre-push hook

REPO_ROOT="$(cd "$(dirname "$0")" && git rev-parse --show-toplevel 2>/dev/null || pwd)"
AUTH_FILE="$REPO_ROOT/.git/.push_authorized"

echo "=========================================="
echo "  OpenClaw Push Authorization"
echo "=========================================="
echo ""

# Create authorization file with timestamp
date +%s > "$AUTH_FILE"
echo "user: node" >> "$AUTH_FILE"
echo "branch: main" >> "$AUTH_FILE"
echo "repo: dpxyz/pecz" >> "$AUTH_FILE"

echo "✅ Authorization CREATED: $AUTH_FILE"
echo "   Time: $(date)"
echo "   Expires: In 10 minutes"
echo ""
echo "Push authorized. Proceed with: git push origin main"
echo "=========================================="
