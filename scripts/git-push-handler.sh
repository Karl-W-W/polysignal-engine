#!/bin/bash
# Git push handler for Loop agent
# Triggered by systemd path unit when /opt/loop/lab/.git-push-request appears
#
# Security:
#   - Branch must start with "loop/"
#   - Files restricted to lab/, workflows/, tests/, agents/
#   - Uses deploy key (repo-scoped, no access to other repos)
#   - Cannot push to main or modify core/
set -euo pipefail

REQUEST_FILE="/opt/loop/lab/.git-push-request"
RESULT_FILE="/opt/loop/lab/.git-push-result"
LOG_FILE="/opt/loop/lab/.git-push-log"
DEPLOY_KEY="/home/cube/.ssh/polysignal-deploy"
REPO_DIR="/opt/loop"

# Allowed path prefixes for commits
ALLOWED_PREFIXES=("lab/" "workflows/" "tests/" "agents/")

log() { echo "$(date +%Y-%m-%dT%H:%M:%S) $*" >> "$LOG_FILE"; echo "$*"; }

cleanup() {
    rm -f "$REQUEST_FILE"
    cd "$REPO_DIR" && git checkout main 2>/dev/null || true
}
trap cleanup EXIT

if [ ! -f "$REQUEST_FILE" ]; then
    log "ERROR: No request file found"
    exit 0  # Exit clean so systemd doesn't rate-limit
fi

# Parse request
branch=$(grep "^branch:" "$REQUEST_FILE" | sed "s/^branch: *//" || true)
message=$(grep "^message:" "$REQUEST_FILE" | sed "s/^message: *//" || true)
files_raw=$(grep "^files:" "$REQUEST_FILE" | sed "s/^files: *//" || true)

if [ -z "$branch" ] || [ -z "$message" ] || [ -z "$files_raw" ]; then
    log "ERROR: Missing required fields (branch, message, files)"
    echo "REJECTED: Missing required fields. Format: branch: loop/name, message: desc, files: path1, path2" > "$RESULT_FILE"
    exit 0
fi

# Validate branch name
if [[ ! "$branch" =~ ^loop/ ]]; then
    log "REJECTED: Branch '$branch' must start with loop/"
    echo "REJECTED: Branch must start with loop/" > "$RESULT_FILE"
    exit 0
fi

# Validate and collect files
IFS="," read -ra FILES <<< "$files_raw"
VALID_FILES=()
for f in "${FILES[@]}"; do
    f=$(echo "$f" | xargs)  # trim whitespace
    [ -z "$f" ] && continue

    valid=false
    for prefix in "${ALLOWED_PREFIXES[@]}"; do
        [[ "$f" == "$prefix"* ]] && valid=true && break
    done

    if [ "$valid" != "true" ]; then
        log "REJECTED: File '$f' not in allowed paths (${ALLOWED_PREFIXES[*]})"
        echo "REJECTED: File '$f' not in allowed paths. Allowed: lab/, workflows/, tests/, agents/" > "$RESULT_FILE"
        exit 0
    fi

    if [ ! -f "$REPO_DIR/$f" ]; then
        log "WARNING: File '$f' does not exist, skipping"
        continue
    fi

    VALID_FILES+=("$f")
done

if [ ${#VALID_FILES[@]} -eq 0 ]; then
    log "REJECTED: No valid files to commit"
    echo "REJECTED: No valid files to commit" > "$RESULT_FILE"
    exit 0
fi

cd "$REPO_DIR"

# Stash any uncommitted changes on main before switching
git stash --include-untracked 2>/dev/null || true

# Create/switch to the branch (based on latest main)
git fetch origin main 2>/dev/null || true
git checkout -B "$branch" origin/main 2>/dev/null || git checkout -B "$branch"

# Restore stashed files (includes Loop's new/modified files)
git stash pop 2>/dev/null || true

# Stage and commit
for f in "${VALID_FILES[@]}"; do
    git add "$f" || { log "ERROR: Cannot stage $f"; continue; }
    log "Staged: $f"
done

GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o StrictHostKeyChecking=no" \
    git -c user.name="Loop Agent" -c user.email="loop@polysignal.app" \
    commit -m "$message

Pushed by Loop agent via git-push-handler.sh" || {
    log "NOTICE: Nothing to commit (files unchanged)"
    echo "NOTICE: Nothing to commit (files unchanged)" > "$RESULT_FILE"
    exit 0
}

GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o StrictHostKeyChecking=no" \
    git push -u origin "$branch" --force-with-lease 2>&1 | tee -a "$LOG_FILE" || {
    log "ERROR: Push failed"
    echo "FAILED: Push failed, check .git-push-log" > "$RESULT_FILE"
    exit 0
}

log "SUCCESS: Pushed ${#VALID_FILES[@]} file(s) to $branch"
echo "SUCCESS: Pushed ${#VALID_FILES[@]} file(s) to $branch" > "$RESULT_FILE"
