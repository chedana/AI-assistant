#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: ./push \"commit message\""
  echo "   or: ./push.sh \"commit message\""
  exit 1
fi

MSG="$1"
REMOTE="${REMOTE_NAME:-origin}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
ALLOW_MAIN_PUSH="${ALLOW_MAIN_PUSH:-0}"

if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
  if [[ "$ALLOW_MAIN_PUSH" != "1" ]]; then
    echo "Refusing to commit/push on $BRANCH."
    echo "Switch to a feature branch (e.g. feature/rental), then run ./push."
    echo "If you really need this, run with: ALLOW_MAIN_PUSH=1 ./push \"message\""
    exit 1
  fi
fi

# 1) stage everything (including new files)
git add -A

# 2) commit if there is anything staged
if ! git diff --cached --quiet; then
  git commit -m "$MSG"
fi

# 3) push if we have commits ahead
if git rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
  AHEAD="$(git rev-list --count @{u}..HEAD)"
  if [[ "$AHEAD" != "0" ]]; then
    git push "$REMOTE" "$BRANCH"
  else
    echo "Nothing to push."
  fi
else
  # First push for this branch: set upstream.
  git push -u "$REMOTE" "$BRANCH"
fi

git status -sb
