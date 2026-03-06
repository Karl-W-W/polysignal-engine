---
name: polysignal-scanner
version: 1.0.0
description: Request a scanner restart after code changes
---

# Scanner Restart Skill

The PolySignal scanner (`polysignal-scanner.service`) runs on the DGX host as a user-level systemd service. It caches Python modules at startup, so code changes in `lab/` or `workflows/` require a restart to take effect.

**You cannot run systemctl from the sandbox.** Instead, use the trigger-file mechanism below.

## When to Restart

Restart the scanner after:
- Modifying `workflows/masterloop.py` or `workflows/scanner.py`
- Modifying `lab/experiments/bitcoin_signal.py` or `lab/time_horizon.py`
- Modifying `lab/feature_engineering.py` or `lab/xgboost_baseline.py`
- Modifying `lab/outcome_tracker.py`
- Any change that affects the perception/prediction/evaluation pipeline

**Always run tests first.** Only restart if tests pass.

## Trigger a Restart

```bash
echo "restart requested $(date)" > /mnt/polysignal/lab/.restart-scanner
```

A systemd path unit on the host watches for this file. When created:
1. The scanner service restarts automatically
2. The trigger file is removed
3. A log entry is written to `/mnt/polysignal/lab/.restart-scanner-log`

## Verify the Restart

Wait ~10 seconds, then check:

```bash
# Check if trigger was consumed (file should be gone)
ls /mnt/polysignal/lab/.restart-scanner 2>/dev/null && echo "PENDING" || echo "DONE (trigger consumed)"

# Check restart log
tail -3 /mnt/polysignal/lab/.restart-scanner-log
```

## Important

- The restart is **asynchronous**. The trigger file is consumed by the host, not by your sandbox.
- Do NOT attempt to run `systemctl` commands. They won't work from the sandbox.
- Only restart after code changes **AND** passing tests (`python3 -m pytest tests/ --tb=short -k 'not test_api'`).
- The scanner takes ~2 seconds to start. First scan cycle begins immediately after startup.
