---
name: github-pr-workflow
description: "GitHub PR lifecycle: branch, commit, open, CI, merge."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Pull-Requests, CI/CD, Git, Automation, Merge]
    related_skills: [github-auth, github-code-review]
---

# GitHub Pull Request Workflow

Complete guide for managing the PR lifecycle. Each section shows the `gh` way first, then the `git` + `curl` fallback for machines without `gh`.

## Prerequisites

- Authenticated with GitHub (see `github-auth` skill)
- Inside a git repository with a GitHub remote

### Quick Auth Detection

```bash
# Determine which method to use throughout this workflow
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  AUTH="gh"
else
  AUTH="git"
  # Ensure we have a token for API calls
  if [ -z "$GITHUB_TOKEN" ]; then
    if [ -f ~/.hermes/.env ] && grep -q "^GITHUB_TOKEN=" ~/.hermes/.env; then
      GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" ~/.hermes/.env | head -1 | cut -d= -f2 | tr -d '\n\r')
    elif grep -q "github.com" ~/.git-credentials 2>/dev/null; then
      GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials 2>/dev/null | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
    fi
  fi
fi
echo "Using: $AUTH"
```

### Extracting Owner/Repo from the Git Remote

Many `curl` commands need `owner/repo`. Extract it from the git remote:

```bash
# Works for both HTTPS and SSH remote URLs
REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
OWNER=$(echo "$OWNER_REPO" | cut -d/ -f1)
REPO=$(echo "$OWNER_REPO" | cut -d/ -f2)
echo "Owner: $OWNER, Repo: $REPO"
```

---

## 1. Branch Creation

This part is pure `git` — identical either way:

```bash
# Make sure you're up to date
git fetch origin
git checkout main && git pull origin main

# Create and switch to a new branch
git checkout -b feat/add-user-authentication
```

Branch naming conventions:
- `feat/description` — new features
- `fix/description` — bug fixes
- `refactor/description` — code restructuring
- `docs/description` — documentation
- `ci/description` — CI/CD changes

## 2. Making Commits

Use the agent's file tools (`write_file`, `patch`) to make changes, then commit:

```bash
# Stage specific files
git add src/auth.py src/models/user.py tests/test_auth.py

# Commit with a conventional commit message
git commit -m "feat: add JWT-based user authentication

- Add login/register endpoints
- Add User model with password hashing
- Add auth middleware for protected routes
- Add unit tests for auth flow"
```

Commit message format (Conventional Commits):
```
type(scope): short description

Longer explanation if needed. Wrap at 72 characters.
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `ci`, `chore`, `perf`

## 3. Pushing and Creating a PR

### Push the Branch (same either way)

```bash
git push -u origin HEAD
```

### Create the PR

**With gh:**

```bash
gh pr create \
  --title "feat: add JWT-based user authentication" \
  --body "## Summary
- Adds login and register API endpoints
- JWT token generation and validation

## Test Plan
- [ ] Unit tests pass

Closes #42"
```

Options: `--draft`, `--reviewer user1,user2`, `--label "enhancement"`, `--base develop`

**With git + curl:**

```bash
BRANCH=$(git branch --show-current)

curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/$OWNER/$REPO/pulls \
  -d "{
    \"title\": \"feat: add JWT-based user authentication\",
    \"body\": \"## Summary\nAdds login and register API endpoints.\n\nCloses #42\",
    \"head\": \"$BRANCH\",
    \"base\": \"main\"
  }"
```

The response JSON includes the PR `number` — save it for later commands.

To create as a draft, add `"draft": true` to the JSON body.

## 4. Monitoring CI Status

### Check CI Status

**With gh:**

```bash
# One-shot check
gh pr checks

# Watch until all checks finish (polls every 10s)
gh pr checks --watch
```

**With git + curl:**

```bash
# Get the latest commit SHA on the current branch
SHA=$(git rev-parse HEAD)

# Query the combined status
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/status \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Overall: {data['state']}\")
for s in data.get('statuses', []):
    print(f\"  {s['context']}: {s['state']} - {s.get('description', '')}\")"

# Also check GitHub Actions check runs (separate endpoint)
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/check-runs \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cr in data.get('check_runs', []):
    print(f\"  {cr['name']}: {cr['status']} / {cr['conclusion'] or 'pending'}\")"
```

### Poll Until Complete (git + curl)

```bash
# Simple polling loop — check every 30 seconds, up to 10 minutes
SHA=$(git rev-parse HEAD)
for i in $(seq 1 20); do
  STATUS=$(curl -s \
    -H "Authorization: token $GITHUB_TOKEN" \
    https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/status \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])")
  echo "Check $i: $STATUS"
  if [ "$STATUS" = "success" ] || [ "$STATUS" = "failure" ] || [ "$STATUS" = "error" ]; then
    break
  fi
  sleep 30
done
```

## 5. Auto-Fixing CI Failures

When CI fails, diagnose and fix. This loop works with either auth method.

### Step 1: Get Failure Details

**With gh:**

```bash
# List recent workflow runs on this branch
gh run list --branch $(git branch --show-current) --limit 5

# View failed logs
gh run view <RUN_ID> --log-failed
```

**With git + curl:**

```bash
BRANCH=$(git branch --show-current)

# List workflow runs on this branch
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/actions/runs?branch=$BRANCH&per_page=5" \
  | python3 -c "
import sys, json
runs = json.load(sys.stdin)['workflow_runs']
for r in runs:
    print(f\"Run {r['id']}: {r['name']} - {r['conclusion'] or r['status']}\")"

# Get failed job logs (download as zip, extract, read)
RUN_ID=<run_id>
curl -s -L \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/actions/runs/$RUN_ID/logs \
  -o /tmp/ci-logs.zip
cd /tmp && unzip -o ci-logs.zip -d ci-logs && cat ci-logs/*.txt
```

### Step 2: Fix and Push

After identifying the issue, use file tools (`patch`, `write_file`) to fix it:

```bash
git add <fixed_files>
git commit -m "fix: resolve CI failure in <check_name>"
git push
```

### Step 3: Verify

Re-check CI status using the commands from Section 4 above.

### Auto-Fix Loop Pattern

When asked to auto-fix CI, follow this loop:

1. Check CI status → identify failures
2. Read failure logs → understand the error
3. Use `read_file` + `patch`/`write_file` → fix the code
4. `git add . && git commit -m "fix: ..." && git push`
5. Wait for CI → re-check status
6. Repeat if still failing (up to 3 attempts, then ask the user)

## 6. Merging

**With gh:**

```bash
# Squash merge + delete branch (cleanest for feature branches)
gh pr merge --squash --delete-branch

# Enable auto-merge (merges when all checks pass)
gh pr merge --auto --squash --delete-branch
```

**With git + curl:**

```bash
PR_NUMBER=<number>

# Merge the PR via API (squash)
curl -s -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER/merge \
  -d "{
    \"merge_method\": \"squash\",
    \"commit_title\": \"feat: add user authentication (#$PR_NUMBER)\"
  }"

# Delete the remote branch after merge
BRANCH=$(git branch --show-current)
git push origin --delete $BRANCH

# Switch back to main locally
git checkout main && git pull origin main
git branch -d $BRANCH
```

Merge methods: `"merge"` (merge commit), `"squash"`, `"rebase"`

### Enable Auto-Merge (curl)

```bash
# Auto-merge requires the repo to have it enabled in settings.
# This uses the GraphQL API since REST doesn't support auto-merge.
PR_NODE_ID=$(curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['node_id'])")

curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/graphql \
  -d "{\"query\": \"mutation { enablePullRequestAutoMerge(input: {pullRequestId: \\\"$PR_NODE_ID\\\", mergeMethod: SQUASH}) { clientMutationId } }\"}"
```

## 7. Complete Workflow Example

```bash
# 1. Start from clean main
git checkout main && git pull origin main

# 2. Branch
git checkout -b fix/login-redirect-bug

# 3. (Agent makes code changes with file tools)

# 4. Commit
git add src/auth/login.py tests/test_login.py
git commit -m "fix: correct redirect URL after login

Preserves the ?next= parameter instead of always redirecting to /dashboard."

# 5. Push
git push -u origin HEAD

# 6. Create PR (picks gh or curl based on what's available)
# ... (see Section 3)

# 7. Monitor CI (see Section 4)

# 8. Merge when green (see Section 6)
```

## 8. Publishing a Local Directory Tree as a New Repository (Snapshot Push)

Use when the user wants a local tree (skills library, dotfiles, docs, scripts) mirrored into a
**brand-new** GitHub repo. Different from the PR flow: no branch, no review, the deliverable is a
verified remote snapshot.

1. Confirm the external write once before doing it (creating a public repo is irreversible in
   practice): new repo vs subdirectory of an existing repo, and public vs private. One combined
   question round, then execute without further prompting.
2. Stage the tree in a throwaway dir — **never `git init` inside the live source tree**. Runtime
   caches and DBs sitting next to real content leak into `git add -A`.
3. Stage with an explicit exclusion list instead of copying wholesale. Hermes skill/library dirs
   carry `.hub/`, `.curator_backups/` (tar.gz snapshots), `.locks/`, `.curator_*`, `.bundled_manifest`,
   `.usage.json*` — a few MB of real content becomes tens of MB of noise without the excludes.
4. Kill orphan skeletons before committing: `git` does not track empty dirs, but a "category" dir
   holding only metadata (e.g. `DESCRIPTION.md`) DOES land in the repo as a stray empty category.
   Cheap check: every top-level dir must contain at least one real payload file.
5. Generate the index (`README.md`) with a script, not by hand — one row per item with links built
   from the item's own relative path, so links stay valid.
6. Create and push in one shot, then verify from the remote API, not from push output:

```bash
STAGE=$(mktemp -d)
rsync -a --exclude='.archive/' --exclude='.curator_backups/' --exclude='.hub/' \
  --exclude='.locks/' --exclude='.curator_*' --exclude='.bundled_manifest' \
  --exclude='.usage.json*' --exclude='.DS_Store' --exclude='.git/' \
  "$SRC/" "$STAGE/"
find "$STAGE" -name '.DS_Store' -delete
cd "$STAGE" && git init -b main -q && git add -A \
  && git commit -q -m "chore: initial snapshot"
gh repo create "$OWNER/$NAME" --public --source . --remote origin --push

# verification (see scripts/verify-snapshot-push.sh)
gh api "repos/$OWNER/$NAME/commits/main" --jq .sha          # must equal local HEAD
git rev-parse HEAD
gh api "repos/$OWNER/$NAME/git/trees/main?recursive=1" \
  --jq '[.tree[]|select(.type=="blob")]|length'             # must equal git ls-files | wc -l
```

7. Leave the persistent working copy at a durable path (`~/<repo-name>`), not in a temp/scratch
   dir — Hermes prunes idle scratch entries after 24h, so a staging-dir clone silently disappears
   and the next incremental sync has no history to build on. `--delete` is safe to pair with
   `--exclude='.git/'`: rsync does not delete excluded paths, so the clone keeps its `.git`.
8. State the sync contract honestly. An rsync + `git commit` + `git push` one-liner does **not**
   regenerate the generated README index, and the mirror is one-way unless a pull step exists.
   Either say so, or ship the index generator as `scripts/` inside the repo so "sync" means
   "sync + rebuild index".

Verification tool: `scripts/verify-snapshot-push.sh <owner/repo> [branch] [local_path]` compares
local HEAD vs remote HEAD and tracked-file count vs remote blob count in one shot.

### Local installation (mirror + index rebuild in one command)

On this machine the skills mirror is already wired up: `~/hermes-skills` is a clone of
`JoelYang-Y/hermes-skills`, and its own `scripts/` does mirror → index rebuild → commit → push.

```bash
bash ~/hermes-skills/scripts/sync.sh             # sync + rebuild README + commit + push
bash ~/hermes-skills/scripts/sync.sh --dry-run   # preview only (rsync -n -v + cleanup preview)
bash ~/hermes-skills/scripts/sync.sh --no-push   # local commit, no remote write
bash ~/hermes-skills/scripts/sync.sh --src D --dst D2   # ad-hoc (used for testing)
```

Invariants the script enforces, each from a real failure:

- **Anchor every root-protection exclude to the transfer root.** The repo keeps its own
  `README.md`, `.gitignore` and `scripts/` at the top level; a source tree that lacks them plus
  `rsync -a --delete` **wipes them** on the next run. Use `--exclude='/scripts/'`,
  `'/README.md'`, `'/.gitignore'`. A bare `--exclude='scripts/'` would instead kill the legitimate
  per-skill `scripts/` subdirectories (e.g. `adguardhome-doh-deploy/scripts/`).
- **Re-derive counts for the commit message from the index generator**, not from top-level dirs:
  top-level dirs include unclassified root-level skills, so `find . -maxdepth 1 -type d` overstates
  the category count (25 vs the true 19).
- **Clean orphan category skeletons after rsync, not before**: a category holding only
  `DESCRIPTION.md` is re-created by every sync, so the removal pass must run on the destination
  each time; skip the repo's own `scripts/` dir explicitly.
- **Idempotence is the acceptance test**: run twice — the second run must print `无变更，跳过提交`
  and add no commit. Test create/delete/exclude paths against a throwaway `--src`/`--dst` pair, never
  against the live `~/.hermes/skills` or the remote.

## Related Skills (absorbed into this umbrella)

This skill now serves as the unified GitHub workflow skill. The following skills are absorbed:

- `github-auth` — Authentication setup: HTTPS tokens, SSH keys, gh CLI login
- `github-issues` — Create, triage, label, assign GitHub issues via gh or REST
- `github-repo-management` — Clone/create/fork repos; manage remotes, releases, secrets, workflows
- `github-code-review` — Review PRs: diffs, inline comments via gh or REST

### Section: github-auth — Authentication Setup

The github-auth skill covered two methods:

**Method 1: Git-Only (no gh, no sudo)**

Option A — HTTPS with Personal Access Token:
```bash
# Create token at https://github.com/settings/tokens
# Scopes: repo, workflow, read:org
git config --global credential.helper store
# Then git will prompt for username + token as password
```

Option B — SSH Key:
```bash
ssh-keygen -t ed25519 -C "email@example.com" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub  # Add to GitHub Settings → SSH Keys
ssh -T git@github.com     # Verify
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

**Method 2: gh CLI**
```bash
echo "<TOKEN>" | gh auth login --with-token
gh auth setup-git
```

Token extraction for scripts:
```bash
# From ~/.hermes/.env
export GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" ~/.hermes/.env | cut -d= -f2)

# From ~/.git-credentials
export GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
```

Auth detection helper:
```bash
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  echo "AUTH_METHOD=gh"
elif [ -n "$GITHUB_TOKEN" ]; then
  echo "AUTH_METHOD=curl"
else
  echo "AUTH_METHOD=none"
fi
```

### Section: github-issues — Issues Management

**Create Issues:**
```bash
gh issue create \
  --title "Login redirect ignores ?next= parameter" \
  --body "## Description\n..." \
  --label "bug,backend" \
  --assignee "username"
```

With curl:
```bash
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/issues \
  -d '{"title": "...", "body": "...", "labels": ["bug"], "assignees": ["username"]}'
```

**Triage Workflow:**
```bash
# List untriaged
gh issue list --label "needs-triage" --state open

# Add labels/assign
gh issue edit 42 --add-label "priority:high" --add-assignee username

# Close with reason
gh issue close 42 --reason "not planned"
```

**Link to PR:** Use keywords in PR body: `Closes #42`, `Fixes #42`, `Resolves #42`

### Section: github-repo-management — Repository Management

**Clone/Create/Fork:**
```bash
gh repo clone owner/repo-name
gh repo create my-project --public --clone
gh repo fork owner/repo-name --clone
```

With curl:
```bash
# Create
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/user/repos \
  -d '{"name": "my-project", "private": false}'

# Fork
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/owner/repo-name/forks
```

**Sync fork:**
```bash
git fetch upstream
git checkout main && git merge upstream/main && git push origin main
```

**Releases:**
```bash
gh release create v1.0.0 --title "v1.0.0" --generate-notes
gh release list
```

**Branch protection:**
```bash
curl -s -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/branches/main/protection \
  -d '{"required_status_checks": {"strict": true, "contexts": ["ci/test"]}, "required_pull_request_reviews": {"required_approving_review_count": 1}}'
```

**Actions:**
```bash
gh run list --limit 10
gh run view <RUN_ID> --log-failed
gh run rerun <RUN_ID>
gh workflow run ci.yml --ref main -f environment=staging
```

### Section: github-code-review — Code Review

**Review local changes (pre-push):**
```bash
git diff main...HEAD --stat
git diff main...HEAD

# Check for issues
git diff main...HEAD | grep -in "password\|secret\|api_key\|TODO\|FIXME"
```

Structured review output:
```
## Code Review Summary

### Critical
- **src/auth.py:45** — SQL injection: user input passed directly to query.

### Warnings
- **src/models/user.py:23** — Password stored in plaintext.

### Suggestions
- **src/utils/helpers.py:8** — Duplicates logic in src/core/utils.py:34.

### Looks Good
- Clean separation of concerns
```

**Review PR on GitHub:**
```bash
gh pr checkout 123
git diff main...HEAD

# Post review
gh pr review 123 --approve --body "LGTM!"
gh pr review 123 --request-changes --body "See inline comments."
```

Atomic multi-comment review (curl):
```bash
HEAD_SHA=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['head']['sha'])")

curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews \
  -d "{
    \"commit_id\": \"$HEAD_SHA\",
    \"event\": \"REQUEST_CHANGES\",
    \"body\": \"## Hermes Agent Review\n\nFound issues — see inline.\",
    \"comments\": [
      {\"path\": \"src/auth.py\", \"line\": 45, \"body\": \"🔴 SQL injection — use parameterized queries.\"},
      {\"path\": \"src/models.py\", \"line\": 23, \"body\": \"⚠️ Plaintext password storage.\"}
    ]
  }"
```

**PR Review Checklist:**
- Correctness: edge cases, error paths
- Security: no hardcoded secrets, input validation, SQL/XSS injection
- Code quality: naming, complexity, DRY
- Testing: new paths covered, happy + error cases
- Performance: no N+1 queries, appropriate caching
- Documentation: public APIs documented, README updated

---

## Useful PR Commands Reference

| Action | gh | git + curl |
|--------|-----|-----------|
| List my PRs | `gh pr list --author @me` | `curl .../pulls?state=open` |
| View PR diff | `gh pr diff` | `git diff main...HEAD` |
| Add comment | `gh pr comment N --body "..."` | `curl .../issues/N/comments -d '{"body":"..."}'` |
| Request review | `gh pr edit N --add-reviewer user` | `curl .../pulls/N/requested_reviewers -d '{"reviewers":["user"]}'` |
| Close PR | `gh pr close N` | `curl -X PATCH .../pulls/N -d '{"state":"closed"}'` |
| Check out PR | `gh pr checkout N` | `git fetch origin pull/N/head:pr-N && git checkout pr-N` |
