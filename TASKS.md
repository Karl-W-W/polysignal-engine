# Loop Task Queue
# Updated: 2026-03-02 21:00 CET (Session 9 — Claude Code)
# Loop reads this on every heartbeat. Pick the first unchecked [ ] item.

---

## Active Tasks

- [ ] **Promote risk_integration.py from lab/ to core/**

  **Goal:** The risk gate bridge has been tested e2e (107/107 pass). It should move out of `lab/` and into the production path. The `from langgraph.graph import END` fix is already applied.

  **Where to write:** `core/risk_integration.py` (new file, copy from lab/)

  **What to do:**
  1. Read `lab/risk_integration.py` — this is the file to promote
  2. Copy it to `core/risk_integration.py`
  3. Update the import in `workflows/masterloop.py` from `from lab.risk_integration import ...` to `from core.risk_integration import ...`
  4. Update `tests/test_risk_integration.py` to import from `core.risk_integration`
  5. Report on Telegram when done
  6. **DO NOT delete the lab/ copy yet** — architect will verify and clean up

- [ ] **Write pytest suite for trade_proposal_bridge.py**

  **Goal:** Your `lab/trade_proposal_bridge.py` works (8 self-tests). But those are inline `_run_tests()` not pytest. Port to `tests/test_trade_proposal_bridge.py` so CI catches regressions.

  **Where to write:** `tests/test_trade_proposal_bridge.py` (new file)

  **What to do:**
  1. Read `lab/trade_proposal_bridge.py` — understand the 8 existing self-tests
  2. Convert each to a pytest test using proper fixtures and assertions
  3. Use real `Signal` objects (from core/signal_model.py) not dicts for the typed path tests
  4. Report on Telegram when done

- [ ] **Write pytest suite for time_horizon.py**

  **Goal:** Same as above — `lab/time_horizon.py` has 12 inline tests. Port to `tests/test_time_horizon.py` for CI.

  **Where to write:** `tests/test_time_horizon.py` (new file)

  **What to do:**
  1. Read `lab/time_horizon.py` — understand the 12 existing self-tests
  2. Convert each to a pytest test
  3. Include boundary tests (exact thresholds, zero values)
  4. Report on Telegram when done

- [ ] **MoltBook publisher dry-run test on DGX**

  **Goal:** Verify `lab/moltbook_publisher.py` runs correctly on DGX (just built by Claude Code, 17 tests passing). Do NOT call live API.

  **Where to write:** Nothing new — just run the tests

  **What to do:**
  1. Run `python3 -m pytest tests/test_moltbook_publisher.py -v` on DGX
  2. If any failures, report the error on Telegram with traceback
  3. If all pass, report "MoltBook publisher verified on DGX"

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
