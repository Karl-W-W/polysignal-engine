# Loop Task Queue (lab/ mirror)
# Updated: 2026-03-05 (Session 15 — Claude Code)
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

- [ ] **Task 1: Review XGBoost training results (15 min)**

  The XGBoost model was trained on 112 samples (89 train, 23 test).
  Training metrics are at `/mnt/polysignal/data/models/training_metrics.json`.

  **Review checklist:**
  1. Read the training metrics JSON and report accuracy, precision, recall, F1
  2. Check feature importance — do the top features make intuitive sense?
  3. Check: is `price_delta_24h` causing data leakage? (Should only use observations BEFORE prediction time)
  4. Read `lab/feature_engineering.py` lines 340-380 (`build_labeled_dataset`) — verify temporal correctness
  5. Run `tests/test_xgboost_baseline.py` to confirm tests pass
  6. Report findings + recommendation (wire into masterloop or wait for more data?) on Telegram

- [ ] **Task 2: Per-market accuracy analysis (20 min)**

  Using the polysignal-data skill, analyze which markets are predictable.

  **Analysis:**
  1. Query prediction_outcomes.json for per-market win/loss rates
  2. Market 824952 has 39% accuracy on 91 evals — investigate why. What is this market about?
  3. Market 556108 has 89% accuracy — what makes it predictable?
  4. The 4h time horizon was 0% accuracy (0W/17L). Verify these are now gone (collapsed to 24h).
  5. Write findings to `lab/market_analysis.md`
  6. Recommend: which markets should we keep tracking, which should we drop?

- [ ] **Task 3: Review masterloop short-circuit + XGBoost gate (code review)**

  **Goal:** Review the Session 14-15 changes to `workflows/masterloop.py`.

  **What to review:**
  1. Read the `route_after_prediction()` function (~line 574)
  2. Read the XGBoost confidence gate in `prediction_node` (~line 295-330)
  3. Verify: does the conditional edge correctly route to `draft` when `TRADING_ENABLED=true`?
  4. Verify: gate threshold is 0.5 (not 0.3)
  5. Verify: `select_features` is imported correctly (public, not private)
  6. Run pytest: `-k 'test_masterloop'`
  7. Report findings on Telegram

- [ ] **Task 4: Evaluate PolyClaw skill for integration (research)**

  PolyClaw (github.com/chainstacklabs/polyclaw) is an OpenClaw skill for Polymarket trading.
  It has 166 GitHub stars, MIT license, last updated Jan 2026.

  **What to do:**
  1. Read `lab/ecosystem_research.md` for details
  2. Assess: does PolyClaw's architecture fit our OpenClaw sandbox?
  3. What dependencies does it need? (py-clob-client, web3.py, OpenRouter API)
  4. Security: does it fetch remote instructions? Does it have exec permissions?
  5. Write a risk assessment to `lab/polyclaw_assessment.md`
  6. Recommend: install as skill, fork and strip, or skip?

---

## Reminders

- **Do NOT run scanner commands. Do NOT run any `.sh` scripts.**
- **Do NOT try to access the network.** You have no network in your sandbox.
- **Do NOT hallucinate `./polymarket_scan.sh`** — it doesn't exist.
- Your job: write Python code, write tests, run pytest, report findings. Stay in your lane.
- After completing a task, mark it [x] in this file and move to the next one.

---

## Completed Tasks (Session 15)
- [x] XGBoost trained: 91.3% accuracy, model saved (Claude Code)
- [x] Accuracy forensics: per-market/horizon/hypothesis breakdown (Claude Code)
- [x] Ecosystem research: py-clob-client, PolyClaw, arxiv, strategies (Claude Code)
- [x] Feature pruning: 9 dead features removed, 10 active (Claude Code)
- [x] XGBoost gate wired into prediction_node, threshold 0.5 (Claude Code)
- [x] 4h horizon killed: time_horizon.py + bitcoin_signal.py WINDOWS (Claude Code)
- [x] 3 integration tests for XGBoost gate (suppress/pass/fallback) (Claude Code)
- [x] All Loop code review feedback addressed (Claude Code)

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
