# Loop Task Queue
# Updated: 2026-03-03 18:30 CET (Session 12 — Claude Code)
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

**You CAN run pytest.** The `.venv` is mounted. Use this exact command:

```bash
cd /mnt/polysignal && /mnt/polysignal/.venv/bin/python3 -m pytest tests/ --tb=short -k 'not test_api'
```

If this works, you can validate your own code. If it fails, report the exact error on Telegram.

---

## Active Tasks

- [ ] **TEST: Verify you can run pytest from sandbox**

  **Goal:** Confirm pytest access. This is your most important capability unlock.

  **What to do:**
  1. Run: `cd /mnt/polysignal && /mnt/polysignal/.venv/bin/python3 -m pytest tests/ --tb=short -k 'not test_api'`
  2. If it works: report "217/217 passing" (or whatever the count is) on Telegram
  3. If it fails: report the EXACT error message on Telegram
  4. Either way, write a brief note in `/mnt/polysignal/lab/reviews/pytest_access_test.md`

- [ ] **Review Session 12 signal detection fix in bitcoin_signal.py**

  **Goal:** Session 12 fixed a critical bug: `detect_signals()` was comparing to the previous 5-minute scan (always 0pp delta for prediction markets). Now uses rolling time windows (15m/1h/4h). Review for correctness and edge cases.

  **What to do:**
  1. Read `lab/experiments/bitcoin_signal.py` — find `detect_signals()` (around line 116)
  2. Review the WINDOWS config and the rolling window query logic
  3. Check edge cases:
     - What if no observations exist in any window? (new market, first hour)
     - What if multiple windows return the same delta? (monotonic trend)
     - Is `datetime('now')` correct for UTC comparison?
  4. Read `workflows/masterloop.py` lines 48-85 — we moved `load_dotenv()` BEFORE core imports (Session 12 fix). Verify this ordering is correct.
  5. Write your review in `/mnt/polysignal/lab/reviews/session12_signal_detection_review.md`
  6. Report findings on Telegram

  **Context:**
  - Production DB has 1,700+ observations across 14 markets
  - First real predictions: Bearish conf=0.60 and Bullish conf=0.60 for market 556108
  - The scanner is now producing real directional predictions via rolling windows
  - Previous bug: `load_dotenv()` ran AFTER core imports, so `predict.py` got wrong DB_PATH

- [ ] **Code review: feature_engineering.py quality check**

  **Goal:** You wrote `lab/feature_engineering.py` in Session 11 (481 lines, 18 features). It has 27 tests passing. Do a self-review now that you can potentially run tests yourself.

  **What to do:**
  1. Re-read your own `lab/feature_engineering.py`
  2. If pytest works: run `cd /mnt/polysignal && /mnt/polysignal/.venv/bin/python3 -m pytest tests/test_feature_engineering.py -v`
  3. Look for:
     - Edge cases in `_safe_std()` and `_prices_in_window()`
     - Are the 18 features actually useful for XGBoost? Any redundant?
     - Is `build_labeled_dataset()` correctly joining features to outcomes?
  4. Write review + any suggested improvements in `/mnt/polysignal/lab/reviews/feature_eng_self_review.md`

---

## Roadmap (for awareness — not active tasks)

**Phase 2: Real Prediction** — Replace rule-based `predict_market_moves()` with ML.
- Scanner is now producing real labeled predictions (Bullish/Bearish, not Neutral)
- Need 50+ labeled predictions for XGBoost baseline (~24-48h of scanner data)
- Feature engineering pipeline ready (`lab/feature_engineering.py`)
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
