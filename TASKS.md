# Loop Task Queue
# Updated: 2026-03-04 01:45 CET (Session 13 closing — Claude Code)
# Loop reads this on every heartbeat. Pick the first unchecked [ ] item.
# IMPORTANT: You are a CODE AGENT. Write code in lab/ and workflows/. Do NOT run scanner commands.
# The scanner is already running as a systemd service — you don't need to scan markets yourself.

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
/mnt/polysignal/ARCHITECTURE.md → /opt/loop/ARCHITECTURE.md (read-only)
/mnt/polysignal/polysignal.db  → /opt/loop/polysignal.db  (read-only)
```

**You CAN run pytest.** Python 3.12 is installed in your sandbox image. Use this exact command:

```bash
cd /mnt/polysignal && PYTHONPATH=/mnt/polysignal:/mnt/polysignal/.venv/lib/python3.12/site-packages /usr/local/bin/python3 -m pytest tests/ --tb=short -k 'not test_api' -q
```

**Why this command?** The `.venv/bin/python3` symlink points to `/usr/bin/python3` which doesn't exist
in your sandbox. Python 3.12 was compiled from source into `/usr/local/bin/python3` in your sandbox
image. The `PYTHONPATH` tells it where to find all installed packages (pydantic, pytest, etc.).

If this works, you can validate your own code. If it fails, report the exact error on Telegram.

---

## Active Tasks

- [ ] **Build `lab/data_readiness.py` — Phase 2 data monitor**

  **Goal:** We need to know when we have enough labeled predictions to train XGBoost.
  The scanner is accumulating data. Build a script that checks readiness.

  **What to do:**
  1. Create `lab/data_readiness.py` with a `check_readiness()` function
  2. It should read `prediction_outcomes.json` (at `/mnt/polysignal/data/prediction_outcomes.json`)
  3. Report: total predictions, evaluated predictions, correct/incorrect/neutral counts, accuracy
  4. Report: estimated time to 50 labeled samples based on current accumulation rate
  5. Return a dict with all stats + `ready: bool` (True when >=50 evaluated predictions)
  6. Add a CLI `__main__` block that prints a formatted report
  7. Write tests in `tests/test_data_readiness.py` — at least 8 tests
  8. Run pytest to verify: `cd /mnt/polysignal && PYTHONPATH=/mnt/polysignal:/mnt/polysignal/.venv/lib/python3.12/site-packages /usr/local/bin/python3 -m pytest tests/test_data_readiness.py -v`

  **Context:**
  - `lab/outcome_tracker.py` already has the PredictionRecord format — read it for the JSON schema
  - `lab/feature_engineering.py` has `dataset_summary()` which does similar reporting — reuse patterns
  - The prediction_outcomes.json lives in `/opt/loop/data/` (mounted at `/mnt/polysignal/data/`)
  - Claude Code is building `lab/xgboost_baseline.py` in parallel — your data_readiness.py will tell us when to trigger training

- [ ] **Apply your Session 12 review findings to bitcoin_signal.py**

  **Goal:** You found 3 minor issues in your review. Apply the fixes.

  **What to do:**
  1. Add a UTC comment to the `datetime('now')` usage in `detect_signals()` (line ~156-159)
     — Clarify that SQLite `datetime('now')` returns UTC, which matches our UTC-stored timestamps
  2. Do NOT change any logic — the review confirmed correctness
  3. Run pytest after: `cd /mnt/polysignal && PYTHONPATH=/mnt/polysignal:/mnt/polysignal/.venv/lib/python3.12/site-packages /usr/local/bin/python3 -m pytest tests/ --tb=short -k 'not test_api' -q`

- [ ] **Build a `polysignal-pytest` custom skill**

  **Goal:** Make pytest a first-class skill so you don't have to remember the long command.

  **What to do:**
  1. Create `/workspace/skills/polysignal-pytest/SKILL.md` (or wherever your skills live)
  2. The skill should wrap: `PYTHONPATH=/mnt/polysignal:/mnt/polysignal/.venv/lib/python3.12/site-packages /usr/local/bin/python3 -m pytest`
  3. Support optional arguments: specific test file, verbose flag, keyword filter
  4. Include instructions on how to interpret results

  **⚠️ IMPORTANT REMINDERS:**
  - Do NOT run scanner commands. Do NOT run any `.sh` scripts. The scanner is a systemd service.
  - Do NOT try to access the network. You have no network in your sandbox.
  - If a command doesn't exist in the codebase, don't run it.
  - Your job: write Python code, write tests, run pytest. Stay in your lane.

---

## Roadmap (for awareness — not active tasks)

**Phase 2: Real Prediction** — Replace rule-based `predict_market_moves()` with ML.
- Scanner is now producing real labeled predictions (Bullish/Bearish, not Neutral)
- Need 50+ labeled predictions for XGBoost baseline (~24-48h of scanner data)
- Feature engineering pipeline ready (`lab/feature_engineering.py`)
- XGBoost training pipeline being built by Claude Code (`lab/xgboost_baseline.py`)
- GPU available (Blackwell on DGX)

**Phase 4: Real HITL** — Telegram YES/NO buttons instead of auto-approve.

**⛔ MoltBook Read Pipeline** — DO NOT BUILD. Write-only until double-layer isolation exists.
See PROGRESS.md "MoltBook Threat Model" for details.

## Completed Tasks

- [x] Risk gate wired into MasterLoop (Session 8 — architect + Loop collab)
- [x] Schema unification — bitcoin_signal.py returns Signal objects (Session 6)
- [x] Architecture report — full codebase review (Session 6)
- [x] health_check.py — thermal, disk, DB freshness (Session 7)
- [x] test_risk_edge_cases.py — boundary tests for risk.py (Session 7)
- [x] schema_review.md — field usage audit (Session 7)
- [x] trade_proposal_bridge.py — typed Signal→TradeProposal bridge (Session 9 — Loop)
- [x] time_horizon.py — derives time_horizon from volatility (Session 9 — Loop)
- [x] time_horizon_audit.md — dead field audit (Session 9 — Loop)
- [x] cycle_number fix — wired from LoopState into observations (Session 9 — Claude Code)
- [x] MasterLoop e2e smoke test — 4 tests (Session 9 — Claude Code)
- [x] route_after_risk_gate END bug fix (Session 9 — Claude Code + Loop independently)
- [x] telegram service removed from docker-compose.yml (Session 9 — Claude Code)
- [x] time_horizon wired into perception pipeline (Session 9 — Claude Code)
- [x] MoltBook publisher built with 17 tests (Session 9 — Claude Code)
- [x] risk_integration.py promoted from lab/ to core/ — 140/140 tests (Session 9 — Claude Code)
- [x] test_trade_proposal_bridge.py — 14 pytest tests ported (Session 9 — Loop)
- [x] test_time_horizon.py — 16 pytest tests ported (Session 9 — Loop)
- [x] MoltBook publisher verified on DGX (Session 9 — Loop)
- [x] MoltBook publisher wired into commit_node (Session 9 — Claude Code)
- [x] Dead files deleted: -1,230 lines (Session 9 — Claude Code)
- [x] MoltBook implementations reconciled (Session 9 — Claude Code)
- [x] dgx_config.md marked SUPERSEDED (Session 9 — Claude Code)
- [x] write_memory() wired into commit_node — learning loop closed (Session 9 — Claude Code)
- [x] Scanner deployed as systemd service on DGX (Session 10 — Antigravity)
- [x] 10 scanner tests added (Session 10 — Antigravity)
- [x] Git auto-sync cron on DGX (Session 10 — Antigravity)
- [x] Outcome tracker built — lab/outcome_tracker.py, 17 tests (Session 10 — Claude Code)
- [x] Outcome tracking wired into MasterLoop (Session 10 — Claude Code)
- [x] Sanitize tests ported — 23 tests (Session 10 — Claude Code)
- [x] 190/190 tests passing (Session 10 — Claude Code)
- [x] Verify full pipeline on DGX — REASSIGNED to Antigravity (Session 11)
- [x] Monitor DGX thermals — REASSIGNED to Antigravity (Session 11)
- [x] Feature engineering pipeline — 18 features, 27 tests (Session 11 — Loop)
- [x] Signal-enhanced predictions — override Neutral with perception direction (Session 11 — Claude Code)
- [x] Supervisor JSON fix — strict=False for Ollama (Session 11 — Claude Code, Vault auth)
- [x] Rolling window signal detection — 15m/1h/4h windows (Session 12 — Claude Code)
- [x] load_dotenv() import order fix — before core imports (Session 12 — Claude Code)
- [x] 217/217 tests passing (Session 12 — Claude Code)
- [x] Sandbox image rebuilt with Python 3.12.3 — Loop can run pytest (Session 12 — Claude Code)
- [x] data/ and brain/ bind mounts added to openclaw.json (Session 12 — Claude Code)
- [x] Loop pytest verified — 217/217 passing from sandbox (Session 12 — Loop)
- [x] Session 12 signal detection reviewed — approved with 3 minor findings (Session 12 — Loop)
- [x] feature_engineering.py self-review — 27/27 passing, no bugs (Session 12 — Loop)
- [x] XGBoost baseline built — `lab/xgboost_baseline.py`, 24 tests (Session 13 — Claude Code)
- [x] XGBoost baseline reviewed — positive review, 2 minor findings (Session 13 — Loop)
- [x] Loop verified 241/241 tests from sandbox incl. XGBoost tests (Session 13 — Loop)
- [x] Overnight audit — 6 findings, cycle_number bug was actionable (Session 13 — Loop)
- [x] Telegram notification dedup — 1hr cooldown, `core/notifications.py` (Session 13 — Claude Code, Vault auth)
- [x] cycle_number wired from scanner into masterloop (Session 13 — Claude Code, bug found by Loop)
- [x] ML deps (xgboost, scikit-learn) installed on DGX (Session 13 — Claude Code)
- [x] 241/241 tests passing on Mac + DGX (Session 13 — Claude Code)
