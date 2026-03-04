# Loop Task Queue
# Updated: 2026-03-04 (Session 14 — Claude Code)
# Loop reads this on every heartbeat. Pick the first unchecked [ ] item.
# IMPORTANT: You are a CODE AGENT. Write code in lab/ and workflows/. Do NOT run scanner commands.

---

## YOUR ENVIRONMENT — READ THIS FIRST

You have more capability than you think. Here's what's actually mounted in your sandbox:

```
/mnt/polysignal/lab/           → /opt/loop/lab/           (read/write)
/mnt/polysignal/workflows/     → /opt/loop/workflows/     (read/write)
/mnt/polysignal/tests/         → /opt/loop/tests/         (read/write)
/mnt/polysignal/core/          → /opt/loop/core/          (READ-ONLY)
/mnt/polysignal/agents/        → /opt/loop/agents/        (read/write)
/mnt/polysignal/.venv/         → /opt/loop/.venv/         (READ-ONLY)
/mnt/polysignal/TASKS.md       → /opt/loop/TASKS.md       (read/write)
/mnt/polysignal/PROGRESS.md    → /opt/loop/PROGRESS.md    (read/write)
/mnt/polysignal/data/          → /opt/loop/data/          (READ-ONLY)
/mnt/polysignal/brain/         → /opt/loop/brain/         (read/write)
```

## NEW: Skills Available

Three skills have been deployed to help you work faster. Read them at:
- `/mnt/polysignal/lab/openclaw/skills/polysignal-pytest/SKILL.md` — pytest commands
- `/mnt/polysignal/lab/openclaw/skills/polysignal-data/SKILL.md` — DB and prediction queries
- `/mnt/polysignal/lab/openclaw/skills/polysignal-git/SKILL.md` — git read-only commands

## SESSION 14 CHANGES

**MasterLoop short-circuit**: When `TRADING_ENABLED=false`, the graph now exits after
prediction_node. Draft/review/risk_gate are skipped entirely. This saves 2 LLM calls per
cycle and eliminates all Telegram spam. Perception + prediction still run for data collection.

---

## Active Tasks

- [ ] **Task 1: Data status report (5 min — quick win)**

  Use the polysignal-data skill to check current system state. Report on Telegram:
  1. How many total observations in the DB?
  2. How many predictions in prediction_outcomes.json? How many evaluated?
  3. What time horizons are the pending predictions using?
  4. When will the oldest pending prediction be evaluable?
  5. How many distinct markets are being tracked?

  **Commands**: See `polysignal-data/SKILL.md` for exact queries.

- [ ] **Task 2: Build `lab/data_readiness.py` — Phase 2 data monitor**

  **Goal:** We need to know when we have enough labeled predictions to train XGBoost.

  **What to do:**
  1. Create `lab/data_readiness.py` with a `check_readiness()` function
  2. Read `prediction_outcomes.json` (at `/mnt/polysignal/data/prediction_outcomes.json`)
  3. Report: total predictions, evaluated predictions, correct/incorrect/neutral counts, accuracy
  4. Report: estimated time to 50 labeled samples based on current accumulation rate
  5. Return a dict with all stats + `ready: bool` (True when >=50 evaluated predictions)
  6. Add a CLI `__main__` block that prints a formatted report
  7. Write tests in `tests/test_data_readiness.py` — at least 8 tests
  8. Run pytest to verify (use polysignal-pytest skill)

  **Context:**
  - `lab/outcome_tracker.py` already has the PredictionRecord format — read it for the JSON schema
  - `lab/feature_engineering.py` has `dataset_summary()` which does similar reporting
  - The prediction_outcomes.json lives in `/mnt/polysignal/data/`

- [ ] **Task 3: Review masterloop short-circuit (code review)**

  **Goal:** Review the Session 14 changes to `workflows/masterloop.py`.

  **What to review:**
  1. Read the new `route_after_prediction()` function (~line 574)
  2. Read the updated `build_masterloop()` graph assembly (~line 608)
  3. Verify: does the conditional edge correctly route to `draft` when `TRADING_ENABLED=true`?
  4. Verify: does perception_node's `evaluate_outcomes()` still fire? (It should — it's before the short-circuit)
  5. Verify: does prediction_node's `record_predictions()` still fire? (Same — before short-circuit)
  6. Read the updated tests in `tests/test_masterloop_e2e.py`
  7. Run pytest: use polysignal-pytest skill, filter with `-k 'test_masterloop'`
  8. Report findings on Telegram

- [ ] **Task 4: Dead code audit (lab/ and workflows/)**

  **Goal:** Find unused imports, unreachable code, or files that should be deleted.

  **What to do:**
  1. Check each file in `lab/` — are there functions never called anywhere?
  2. Check `workflows/scanner.py` — any dead code from before the short-circuit?
  3. Check `workflows/masterloop.py` — any now-unreachable code paths?
  4. Check for unused imports across all non-core files
  5. Write findings in `lab/dead_code_audit.md`
  6. Do NOT delete anything — just report

---

## Reminders

- **Do NOT run scanner commands. Do NOT run any `.sh` scripts.**
- **Do NOT try to access the network.** You have no network in your sandbox.
- **Do NOT hallucinate `./polymarket_scan.sh`** — it doesn't exist.
- Your job: write Python code, write tests, run pytest, report findings. Stay in your lane.
- After completing a task, mark it [x] in this file and move to the next one.

---

## Completed Tasks (Session 14)
(none yet — you're up!)

## Completed Tasks (Session 13 and earlier)
- [x] XGBoost baseline reviewed (Session 13 — Loop)
- [x] 241/241 tests verified from sandbox (Session 13 — Loop)
- [x] Overnight audit — 6 findings, cycle_number bug actionable (Session 13 — Loop)
- [x] Feature engineering self-review — 27/27 passing (Session 12 — Loop)
- [x] Signal detection review — approved with 3 minor findings (Session 12 — Loop)
- [x] Pytest access verified from sandbox (Session 12 — Loop)
