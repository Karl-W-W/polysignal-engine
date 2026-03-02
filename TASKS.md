# Loop Task Queue
# Updated: 2026-03-03 00:30 CET (Session 9 — Claude Code)
# Loop reads this on every heartbeat. Pick the first unchecked [ ] item.

---

## Active Tasks

- [ ] **Port sanitize.py self-tests to pytest**

  **Goal:** `lab/openclaw/moltbook_polysignal_skill/sanitize.py` has 7 inline self-tests. Port to `tests/test_sanitize.py` for CI.

  **Where to write:** `tests/test_sanitize.py` (new file)

  **What to do:**
  1. Read `lab/openclaw/moltbook_polysignal_skill/sanitize.py`
  2. Convert each self-test to a pytest test with proper assertions
  3. Add edge cases: empty post, missing fields, very long content (>500 chars)
  4. Run `python3 -m pytest tests/test_sanitize.py -v`
  5. Report on Telegram when done

- [ ] **Verify full pipeline on DGX (git pull + tests + dry-run)**

  **Goal:** DGX is behind — needs git pull of commits `2fd7d5f` through latest.

  **What to do:**
  1. `cd /opt/loop && git pull origin main`
  2. `python3 -m pytest tests/ --tb=short -k 'not test_api'` — expect 140/140
  3. Run dry-run from `lab/reviews/moltbook_verification.md` §4
  4. Verify `write_memory()` works: check if `/opt/loop/brain/memory.md` gets entries
  5. Report results on Telegram

## Roadmap (Phase 2+, for planning — not active tasks yet)

**Phase 2: Real Prediction** — Replace rule-based `predict_market_moves()` with ML.
- Feature engineering from observations table
- XGBoost baseline → backtest → A/B vs rule-based
- GPU utilization on DGX Blackwell

**Phase 3: Continuous Scanning** — Kill manual invocation, scan every 5 minutes.
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
