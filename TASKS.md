# Loop Task Queue
# Updated: 2026-03-03 02:00 CET (Session 10 — Claude Code)
# Loop reads this on every heartbeat. Pick the first unchecked [ ] item.

---

## Active Tasks

- [ ] **Verify full pipeline on DGX (git pull + tests + dry-run)**

  **Goal:** DGX auto-syncs via cron. Verify 190/190 tests pass after sync.

  **What to do:**
  1. `cd /opt/loop && git pull origin main`
  2. `python3 -m pytest tests/ --tb=short -k 'not test_api'` — expect 190/190
  3. Verify `write_memory()` works: check if `/opt/loop/brain/memory.md` gets entries
  4. Verify outcome tracker writes to `/opt/loop/data/prediction_outcomes.json`
  5. Report results on Telegram

- [ ] **Let scanner accumulate data (48-72h)**

  **Goal:** Scanner running as systemd service. Let it accumulate observations before Phase 2 ML.

  **What to do:**
  1. Monitor `/opt/loop/data/prediction_outcomes.json` grows
  2. Check accuracy summary via `get_accuracy_summary()`
  3. After 48h, evaluate if enough labeled data for XGBoost baseline

## Roadmap (Phase 2+, for planning — not active tasks yet)

**Phase 2: Real Prediction** — Replace rule-based `predict_market_moves()` with ML.
- Feature engineering from outcome_tracker labeled data
- XGBoost baseline → backtest → A/B vs rule-based
- GPU utilization on DGX Blackwell
- Requires: 48-72h of scanner data from outcome tracker

**Phase 3: Continuous Scanning** — COMPLETE (Antigravity, Session 10)
- Scanner deployed as `polysignal-scanner.service` on DGX
- 5-minute interval, active hours 07:00-01:00 CET
- Git auto-sync cron installed

**Phase 4: Real HITL** — Telegram YES/NO buttons instead of auto-approve.

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
- [x] Outcome tracking wired into MasterLoop — perception evaluates, prediction records, memory includes accuracy (Session 10 — Claude Code)
- [x] Sanitize tests ported — tests/test_sanitize.py, 23 tests (Session 10 — Claude Code)
- [x] 190/190 tests passing (Session 10 — Claude Code)
