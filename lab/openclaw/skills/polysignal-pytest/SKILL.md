---
name: polysignal-pytest
version: 1.0.0
description: Run the PolySignal test suite from the sandbox
---

# PolySignal Pytest Skill

Run pytest without memorizing the long command. Works from your sandbox.

## Quick Run (all tests)
```bash
cd /mnt/polysignal && PYTHONPATH=/mnt/polysignal:/mnt/polysignal/.venv/lib/python3.12/site-packages /usr/local/bin/python3 -m pytest tests/ --tb=short -k 'not test_api' -q
```

## Run Specific Test File
```bash
cd /mnt/polysignal && PYTHONPATH=/mnt/polysignal:/mnt/polysignal/.venv/lib/python3.12/site-packages /usr/local/bin/python3 -m pytest tests/test_risk.py -v
```

## Run With Keyword Filter
```bash
cd /mnt/polysignal && PYTHONPATH=/mnt/polysignal:/mnt/polysignal/.venv/lib/python3.12/site-packages /usr/local/bin/python3 -m pytest tests/ -k 'test_short_circuit' -v
```

## Stop at First Failure
```bash
cd /mnt/polysignal && PYTHONPATH=/mnt/polysignal:/mnt/polysignal/.venv/lib/python3.12/site-packages /usr/local/bin/python3 -m pytest tests/ --maxfail=1 --tb=long -k 'not test_api'
```

## Interpreting Results
- **260 passed** = current baseline (Session 15)
- Any **FAILED** = report exact failure on Telegram immediately
- **ERRORS** = usually import errors — check PYTHONPATH includes both paths
- `.pytest_cache` write warnings are harmless (read-only filesystem)

## IMPORTANT: Task File Location
**`/mnt/polysignal/TASKS.md` is STALE** due to Docker inode caching on individual file bind mounts.
Read your tasks from: **`/mnt/polysignal/lab/LOOP_TASKS.md`** (syncs through directory mount).

## Why This Command?
- `.venv/bin/python3` symlink points to `/usr/bin/python3` which doesn't exist in sandbox
- Python 3.12.3 was compiled into `/usr/local/bin/python3` in the sandbox image
- `PYTHONPATH` tells it where to find installed packages (pydantic, pytest, xgboost, etc.)
