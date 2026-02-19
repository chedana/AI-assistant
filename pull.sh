#!/usr/bin/env bash
set -euo pipefail

REMOTE="${REMOTE_NAME:-origin}"
TARGET_BRANCH="${TARGET_BRANCH:-feature/rental}"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# Keep pull safe and predictable.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree is not clean. Commit or stash before pull."
  exit 1
fi

if [[ "$CURRENT_BRANCH" != "$TARGET_BRANCH" ]]; then
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

if git rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
  git pull --ff-only "$REMOTE" "$BRANCH"
else
  if git ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
    git branch --set-upstream-to="$REMOTE/$BRANCH" "$BRANCH"
    git pull --ff-only "$REMOTE" "$BRANCH"
  else
    echo "No remote branch found for $BRANCH on $REMOTE."
    echo "Push first with: ./push \"your commit message\""
    exit 1
  fi
fi

git status -sb
