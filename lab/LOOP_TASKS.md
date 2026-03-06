# Loop Task Queue (lab/ mirror)
# Updated: 2026-03-06 18:30 CET (Session 16 — Claude Code)
#
# WHY THIS FILE EXISTS:
# TASKS.md and PROGRESS.md are mounted as individual file bind mounts in Docker.
# These capture the inode at container creation time and don't see host updates.
# This file lives in lab/ which is a DIRECTORY mount → always syncs correctly.
#
# Loop: READ THIS FILE instead of /mnt/polysignal/TASKS.md for current tasks.
# After completing a task, mark it [x] here AND report on Telegram.

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
/mnt/polysignal/data/          → /opt/loop/data/          (READ-ONLY)
/mnt/polysignal/brain/         → /opt/loop/brain/         (read/write)
```

**NOTE:** `/mnt/polysignal/TASKS.md` and `/mnt/polysignal/PROGRESS.md` are STALE
due to Docker inode caching. Use THIS file for tasks.

## Skills Available

- `/mnt/polysignal/lab/openclaw/skills/polysignal-pytest/SKILL.md` — pytest commands
- `/mnt/polysignal/lab/openclaw/skills/polysignal-data/SKILL.md` — DB and prediction queries
- `/mnt/polysignal/lab/openclaw/skills/polysignal-git/SKILL.md` — git read-only commands

## SESSION 16 CHANGES

**Scanner restarted with Session 15+16 code.** Previous scanner process ran since Mar 4 (pre-Session-15) — never loaded XGBoost gate or 4h kill.

**Fixes applied (Claude Code, Session 16):**
- XGBoost gate: inner `except Exception` now logs per-prediction failures (was silently swallowing)
- XGBoost gate: prints status line when active (`🔍 XGBoost gate: N passed, M suppressed`)
- Market 824952 EXCLUDED from signal detection via `EXCLUDED_MARKETS` in bitcoin_signal.py
- Observations for 824952 still recorded (data collection), but no signals/predictions generated
- Scanner restarted 18:25 CET — first cycle with new code confirmed working

**Current numbers (pre-fix baseline):**
- 330 predictions, 259 evaluated, 41% accuracy (58W/85L/116N)
- 0 predictions had xgb_p_correct (gate was never firing)
- Market 824952 was 34% accuracy, 0W/40L on Bullish
- Without 824952: ~89% accuracy on remaining markets

**What to expect going forward:**
- No more 824952 predictions (excluded)
- XGBoost gate now fires on every prediction — watch for `xgb_p_correct` in new predictions
- New predictions will be MegaETH (556062/556108) and any new crypto markets

---

## Active Tasks

- [ ] **Task 5: Add `before` parameter to `get_market_history()` (20 min)**

  **Why:** `get_market_history()` fetches 72h of observations regardless of `ref_time`.
  All downstream code filters correctly TODAY, but one careless future feature could
  silently cause data leakage. Add defense-in-depth.

  **What to do:**
  1. Read `lab/feature_engineering.py` — find `get_market_history()` function
  2. Add an optional `before: datetime = None` parameter
  3. If `before` is set, filter the SQL query to `timestamp <= before`
  4. Update `extract_features()` to pass `ref_time` as `before` when available
  5. Add test(s) to `tests/test_feature_engineering.py` verifying temporal correctness
  6. Run full test suite — must still be 260/260
  7. Report on Telegram

- [ ] **Task 9: Post-fix accuracy snapshot (10 min)**

  **Why:** We need a baseline after the Session 16 fixes (824952 exclusion + gate restart).

  **What to do:**
  1. Query `prediction_outcomes.json` — total predictions, evaluated, accuracy
  2. Check: are there any NEW predictions with `xgb_p_correct` field? (Gate firing confirmation)
  3. Per-market breakdown of remaining active markets
  4. Per-horizon breakdown (should be no 4h predictions in new data)
  5. Report on Telegram

- [ ] **Task 10: Review XGBoost gate logging changes (code review, 10 min)**

  **Why:** Session 16 added error logging to the XGBoost gate. Verify the changes are clean.

  **What to do:**
  1. Read `workflows/masterloop.py` lines 294-335 (XGBoost gate section)
  2. Verify: inner `except` now logs `market_id` + error message
  3. Verify: `gate_ran` flag correctly controls status line output
  4. Verify: when model is missing, gate skips gracefully (no crash)
  5. Run `pytest -k test_masterloop` to confirm 8/8 pass
  6. Report on Telegram

- [ ] **Task 11: Investigate bullish bias (research, 20 min)**

  **Why:** System is 67% on Bearish but only 38% on Bullish. Understanding why could
  improve the XGBoost model when we retrain.

  **What to do:**
  1. Query prediction_outcomes.json: per-hypothesis accuracy breakdown
  2. Is the bias market-specific (824952 drags Bullish) or systematic?
  3. With 824952 excluded, recalculate: what is Bullish accuracy on remaining markets?
  4. Check: does `price_delta_24h` feature encode direction? If so, the model sees this.
  5. Write findings to `lab/reviews/bullish_bias_analysis.md`
  6. Recommend: should we add a `hypothesis_direction` feature to XGBoost? Or a `distance_from_extreme` feature?

---

## Reminders

- **Do NOT run scanner commands. Do NOT run any `.sh` scripts.**
- **Do NOT try to access the network.** You have no network in your sandbox.
- **Do NOT hallucinate `./polymarket_scan.sh`** — it doesn't exist.
- Your job: write Python code, write tests, run pytest, report findings. Stay in your lane.
- After completing a task, mark it [x] in this file and move to the next one.

---

## Completed Tasks (Session 16)
- [x] XGBoost gate debug: inner except now logs errors (Claude Code)
- [x] Market 824952 excluded from signal detection (Claude Code)
- [x] Scanner restarted with new code (Claude Code)
- [x] KWW reviews: xgboost_gate_impact.md, market_824952_decision.md (KWW)

## Completed Tasks (Session 15)
- [x] Task 1: XGBoost training review — NO DATA LEAKAGE confirmed (Loop)
- [x] Task 2: Per-market accuracy analysis — 824952=38.4%, 556108=88.9% (Loop)
- [x] Task 3: Masterloop review — gate, short-circuit, imports all correct (Loop)
- [x] Task 4: PolyClaw assessment — verdict: SKIP (Loop)
- [x] XGBoost trained: 91.3% accuracy, model saved (Claude Code)
- [x] Accuracy forensics: per-market/horizon/hypothesis breakdown (Claude Code)
- [x] Ecosystem research: py-clob-client, PolyClaw, arxiv, strategies (Claude Code)
- [x] Feature pruning: 9 dead features removed, 10 active (Claude Code)
- [x] XGBoost gate wired into prediction_node, threshold 0.5 (Claude Code)
- [x] 4h horizon killed: time_horizon.py + bitcoin_signal.py WINDOWS (Claude Code)
- [x] 3 integration tests for XGBoost gate (suppress/pass/fallback) (Claude Code)
- [x] Docker bind mount fix: lab/LOOP_TASKS.md created, skills updated (Claude Code)

## Completed Tasks (Session 14 and earlier)
- [x] Task 2: data_readiness.py built (Claude Code) — 14 tests
- [x] Task 4: Dead code audit (Claude Code) — no dead code found
- [x] Evaluation pipeline fix: moved evaluate_outcomes() after market fetch (Claude Code)
- [x] MasterLoop short-circuit: TRADING_ENABLED=false skips draft/review/risk_gate (Claude Code)
- [x] XGBoost baseline reviewed (Session 13 — Loop)
- [x] 241/241 tests verified from sandbox (Session 13 — Loop)
- [x] Overnight audit — 6 findings, cycle_number bug actionable (Session 13 — Loop)
