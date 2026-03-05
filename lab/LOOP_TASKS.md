# Loop Task Queue (lab/ mirror)
# Updated: 2026-03-05 23:00 CET (Session 15 closing — Claude Code)
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

## SESSION 15 CHANGES

**XGBoost TRAINED & WIRED.** Model at `/mnt/polysignal/data/models/xgboost_baseline.pkl`.
- 91.3% test accuracy, 85.5% CV ±10.6% (after pruning 9 dead features → 10 active)
- XGBoost gate live in prediction_node: suppresses predictions with P(correct) < 0.5
- Top features: `price_delta_24h` (0.29), `trend_strength` (0.22), `observation_density` (0.15)
- 4h time horizon KILLED (collapsed to 24h — was 0% accuracy on 17 evals)
- 260/260 tests passing

**Accuracy forensics revealed critical patterns:**
- Market 824952: 39% accuracy (91 evals) — **actively wrong, dragging system down**
- Market 556108: 89% accuracy (27 evals) — **star performer**
- 4h horizon: 0% accuracy (0W/17L) — **killed**
- Bearish: 67% vs Bullish: 38% — **directional bias**
- Second half: 59% vs First half: 43% — **improving over time**

**Research findings (see `lab/ecosystem_research.md`):**
- py-clob-client Level 0 methods can enhance perception NOW (orderbook depth, spread)
- PolyClaw (chainstacklabs) is an OpenClaw skill for Polymarket trading — needs vetting
- News retrieval is the #1 accuracy improvement per academic research (arxiv 2402.18563)
- High-probability bond detection (>95% markets near resolution) is free alpha

---

## Active Tasks

- [ ] **Task 5: Add `before` parameter to `get_market_history()` (20 min)**

  **Why:** You found in Task 1 that `get_market_history()` fetches 72h of observations regardless
  of `ref_time`. All downstream code filters correctly TODAY, but one careless future feature
  could silently cause data leakage. Add defense-in-depth.

  **What to do:**
  1. Read `lab/feature_engineering.py` — find `get_market_history()` function
  2. Add an optional `before: datetime = None` parameter
  3. If `before` is set, filter the SQL query to `timestamp <= before`
  4. Update `extract_features()` to pass `ref_time` as `before` when available
  5. Add test(s) to `tests/test_feature_engineering.py` verifying temporal correctness
  6. Run full test suite — must still be 260/260
  7. Report on Telegram

- [ ] **Task 6: Investigate XGBoost gate live impact (15 min)**

  **Why:** The gate has been live since Session 15. We need to know if it's helping.

  **What to do:**
  1. Query `prediction_outcomes.json` for predictions made AFTER the gate was wired
     (look for predictions with `xgb_p_correct` field — these passed through the gate)
  2. Compare accuracy of gated predictions vs pre-gate predictions
  3. Count: how many predictions were SUPPRESSED by the gate? (These won't appear in outcomes)
  4. Check scanner logs for "XGBoost gate" output messages
  5. Write findings to `lab/reviews/xgboost_gate_impact.md`
  6. Report on Telegram

- [ ] **Task 7: Market 824952 exclusion analysis (15 min)**

  **Why:** You found this market has 38.4% accuracy — worse than random. Excluding it
  would eliminate 53 of 55 losses. Before we exclude it, we need a clean analysis.

  **What to do:**
  1. Query the latest prediction_outcomes.json for market 824952 stats
  2. Has the XGBoost gate already started suppressing 824952 predictions?
  3. If yes, the gate may auto-fix the problem. If no, we need a manual exclusion.
  4. Check: what is 824952's `xgb_p_correct` score? Does the model know it's bad?
  5. Write recommendation to `lab/reviews/market_824952_decision.md`
  6. Recommend: exclude, invert, or let the gate handle it?

- [ ] **Task 8: Current prediction accuracy snapshot (10 min)**

  **Why:** Regular accuracy monitoring catches regressions early.

  **What to do:**
  1. Run the polysignal-data status report query
  2. Report total predictions, evaluated, accuracy, pending
  3. Per-horizon breakdown (should be no more 4h predictions)
  4. Report on Telegram

---

## Reminders

- **Do NOT run scanner commands. Do NOT run any `.sh` scripts.**
- **Do NOT try to access the network.** You have no network in your sandbox.
- **Do NOT hallucinate `./polymarket_scan.sh`** — it doesn't exist.
- Your job: write Python code, write tests, run pytest, report findings. Stay in your lane.
- After completing a task, mark it [x] in this file and move to the next one.

---

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
- [x] All Loop code review feedback addressed (Claude Code)
- [x] Docker bind mount fix: lab/LOOP_TASKS.md created, skills updated (Claude Code)

## Completed Tasks (Session 14)
- [x] Task 2: data_readiness.py built (Claude Code) — 14 tests
- [x] Task 4: Dead code audit (Claude Code) — no dead code found
- [x] Evaluation pipeline fix: moved evaluate_outcomes() after market fetch (Claude Code)
- [x] MasterLoop short-circuit: TRADING_ENABLED=false skips draft/review/risk_gate (Claude Code)

## Completed Tasks (Session 13 and earlier)
- [x] XGBoost baseline reviewed (Session 13 — Loop)
- [x] 241/241 tests verified from sandbox (Session 13 — Loop)
- [x] Overnight audit — 6 findings, cycle_number bug actionable (Session 13 — Loop)
- [x] Feature engineering self-review — 27/27 passing (Session 12 — Loop)
- [x] Signal detection review — approved with 3 minor findings (Session 12 — Loop)
- [x] Pytest access verified from sandbox (Session 12 — Loop)
