# Loop Task Queue
# Updated: 2026-03-02 23:30 CET (Session 9 — Claude Code)
# Loop reads this on every heartbeat. Pick the first unchecked [ ] item.

---

## Active Tasks

- [ ] **Wire MoltBook publisher into masterloop commit_node**

  **Goal:** The MoltBook publisher (`lab/moltbook_publisher.py`) is built and tested (17 tests) but never called from the pipeline. Wire it as a non-blocking post-commit step so signals get published to MoltBook after successful execution.

  **Where to write:** `workflows/masterloop.py` (edit commit_node function)

  **What to do:**
  1. Read `lab/moltbook_publisher.py` — understand `publish_signal()` and `MoltBookConfig`
  2. In commit_node (after successful execution), call `publish_signal()` in dry-run mode
  3. Add result to state (e.g. `state["moltbook_result"]`)
  4. Wrap in try/except so publish failure never blocks the trade pipeline
  5. Run `python3 -m pytest tests/ --tb=short -k 'not test_api'` — all must pass
  6. Report on Telegram when done

- [ ] **Clean up lab/ copies of promoted modules**

  **Goal:** `risk_integration.py` is now live in `core/`. The `lab/` copy is stale. Remove it to prevent import confusion.

  **Where to write:** Delete `lab/risk_integration.py`

  **What to do:**
  1. Verify `core/risk_integration.py` exists and imports work: `python3 -c "from core.risk_integration import risk_gate_node; print('OK')"`
  2. Delete `lab/risk_integration.py`
  3. Run full test suite to confirm nothing imports from lab path
  4. Report on Telegram when done

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
