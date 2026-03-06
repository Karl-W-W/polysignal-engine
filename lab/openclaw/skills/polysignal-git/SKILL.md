---
name: polysignal-git
version: 2.0.0
description: Git operations for PolySignal codebase (read + push to loop/* branches)
---

# PolySignal Git Skill

View git history, diffs, and push code changes to `loop/*` branches.

## Read Operations

### Recent Commits
```bash
cd /mnt/polysignal && git log --oneline -20
```

### What Changed in a Specific File
```bash
cd /mnt/polysignal && git diff HEAD~1 -- lab/outcome_tracker.py
```

### Changes Since Last Session
```bash
cd /mnt/polysignal && git log --oneline --since="24 hours ago"
```

### Current Branch State
```bash
cd /mnt/polysignal && git status --short
```

### Show a Specific Commit
```bash
cd /mnt/polysignal && git show --stat HEAD
```

### File Change History
```bash
cd /mnt/polysignal && git log --oneline -10 -- workflows/masterloop.py
```

---

## Push Operations (via trigger file)

You can push code changes to `loop/*` branches. A host-side handler validates and executes the push.

### How to Push

1. Write your code changes to `lab/`, `workflows/`, `tests/`, or `agents/`.
2. Run tests: `python3 -m pytest /mnt/polysignal/tests/ --tb=short -k 'not test_api'`
3. Create a push request:

```bash
cat > /mnt/polysignal/lab/.git-push-request << EOF
branch: loop/your-feature-name
message: Brief description of changes
files: lab/your_file.py, lab/another_file.py
EOF
```

4. Wait ~10 seconds, then check the result:

```bash
cat /mnt/polysignal/lab/.git-push-result
```

### Push Request Format

```
branch: loop/<feature-name>     (REQUIRED — must start with "loop/")
message: <commit message>       (REQUIRED — brief description)
files: <path1>, <path2>, ...    (REQUIRED — comma-separated, relative to repo root)
```

### Rules

- **Branch must start with `loop/`** — you cannot push to `main` or other branches.
- **Files must be in allowed paths:** `lab/`, `workflows/`, `tests/`, `agents/`
- **Cannot push files in:** `core/` (Vault), `.env`, `*.key`, `.git/`
- **Always run tests before pushing.** Push requests with failing tests waste reviewer time.
- The push creates a branch from `origin/main`. Claude Code or Karl will review and merge.

### Check Push Result

```bash
# Result of last push
cat /mnt/polysignal/lab/.git-push-result

# Push history
tail -10 /mnt/polysignal/lab/.git-push-log
```

---

## Important Notes

- The DGX cron runs `git reset --hard origin/main` every 10 minutes — your uncommitted changes in git-tracked files will be wiped. Push promptly or write to `lab/` (safe via directory mount).
- `.git/` is not directly mounted in the sandbox. Push operations go through the trigger-file mechanism.
- Read operations work because git data is accessible through the bind-mounted directories.

## IMPORTANT: Task File Location
**`/mnt/polysignal/TASKS.md` is STALE** due to Docker inode caching on individual file bind mounts.
Read your tasks from: **`/mnt/polysignal/lab/LOOP_TASKS.md`** (syncs through directory mount).
