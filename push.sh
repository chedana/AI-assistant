#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: ./push \"commit message\""
  echo "   or: ./push.sh \"commit message\""
  exit 1
fi

MSG="$1"
REMOTE="${REMOTE_NAME:-origin}"
TARGET_BRANCH="${TARGET_BRANCH:-feature/rental}"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [[ "$CURRENT_BRANCH" != "$TARGET_BRANCH" ]]; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Cannot switch from $CURRENT_BRANCH to $TARGET_BRANCH: working tree is not clean."
    echo "Commit or stash first, then run ./push again."
    exit 1
  fi

  echo "Switching branch: $CURRENT_BRANCH -> $TARGET_BRANCH"
  if git show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
    git checkout "$TARGET_BRANCH"
  elif git ls-remote --exit-code --heads "$REMOTE" "$TARGET_BRANCH" >/dev/null 2>&1; then
    git checkout -b "$TARGET_BRANCH" --track "$REMOTE/$TARGET_BRANCH"
  else
    echo "Target branch $TARGET_BRANCH does not exist locally or on $REMOTE."
    exit 1
  fi
fi

BRANCH="$TARGET_BRANCH"

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
