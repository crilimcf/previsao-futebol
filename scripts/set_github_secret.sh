#!/usr/bin/env bash
# scripts/set_github_secret.sh
# Helper: set repository secret using `gh` (GitHub CLI).
# Usage: ./scripts/set_github_secret.sh SECRET_NAME SECRET_VALUE
# Requires `gh auth login` and repo permissions.
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: $0 SECRET_NAME SECRET_VALUE" >&2
  exit 2
fi
name=$1
value=$2
repo=$(git config --get remote.origin.url || echo "")
if [ -z "$repo" ]; then
  echo "No git remote origin found. Run this from repo root." >&2
  exit 3
fi
# Use gh to set secret for current repo
gh secret set "$name" --body "$value"
