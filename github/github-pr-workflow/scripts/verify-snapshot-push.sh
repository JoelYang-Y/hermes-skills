#!/usr/bin/env bash
# Verify a snapshot push: remote HEAD must equal local HEAD, and the number of
# tracked local files must equal the number of blobs in the remote tree.
# A successful `git push` line is NOT proof; this reads the remote back.
#
# Usage: verify-snapshot-push.sh <owner/repo> [branch] [local_repo_path]
set -euo pipefail

REPO="${1:?usage: verify-snapshot-push.sh <owner/repo> [branch] [local_repo_path]}"
BRANCH="${2:-main}"
LOCAL="${3:-.}"

command -v gh >/dev/null || { echo "gh CLI required"; exit 2; }

LOCAL_SHA=$(git -C "$LOCAL" rev-parse HEAD)
REMOTE_SHA=$(gh api "repos/$REPO/commits/$BRANCH" --jq .sha)
TRACKED=$(git -C "$LOCAL" ls-files | wc -l | tr -d ' ')
BLOBS=$(gh api "repos/$REPO/git/trees/$BRANCH?recursive=1" \
  --jq '[.tree[]|select(.type=="blob")]|length')
SKILLS_LOCAL=$(git -C "$LOCAL" ls-files | grep -c 'SKILL\.md$' || true)
SKILLS_REMOTE=$(gh api "repos/$REPO/git/trees/$BRANCH?recursive=1" \
  --jq '[.tree[]|select(.type=="blob")|select(.path|endswith("SKILL.md"))]|length')

printf 'local HEAD  : %s\n' "$LOCAL_SHA"
printf 'remote HEAD : %s\n' "$REMOTE_SHA"
printf 'tracked     : %s\n' "$TRACKED"
printf 'remote blobs: %s\n' "$BLOBS"
printf 'SKILL.md    : local %s / remote %s\n' "$SKILLS_LOCAL" "$SKILLS_REMOTE"

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ] && [ "$TRACKED" = "$BLOBS" ]; then
  echo "OK: snapshot verified"
else
  echo "MISMATCH: remote does not match the local commit" >&2
  exit 1
fi
