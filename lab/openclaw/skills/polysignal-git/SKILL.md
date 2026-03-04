---
name: polysignal-git
version: 1.0.0
description: Read-only git operations for PolySignal codebase
---

# PolySignal Git Skill

View git history and diffs. You have read-only access to .git/.

## Recent Commits
```bash
cd /mnt/polysignal && git log --oneline -20
```

## What Changed in a Specific File
```bash
cd /mnt/polysignal && git diff HEAD~1 -- lab/outcome_tracker.py
```

## Changes Since Last Session
```bash
cd /mnt/polysignal && git log --oneline --since="24 hours ago"
```

## Current Branch State
```bash
cd /mnt/polysignal && git status --short
```

## Show a Specific Commit
```bash
cd /mnt/polysignal && git show --stat HEAD
```

## File Change History
```bash
cd /mnt/polysignal && git log --oneline -10 -- workflows/masterloop.py
```

## Important Notes
- `.git/` is read-only. You **cannot** commit, push, or modify git state.
- To contribute code: write files in `lab/` or `workflows/`, then report on Telegram.
- Claude Code or Karl will commit your changes.
- The DGX cron runs `git reset --hard origin/main` every 10 minutes — your uncommitted changes in git-tracked files will be wiped. Write to `lab/` (safe) or report immediately.
