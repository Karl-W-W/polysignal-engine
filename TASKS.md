# Loop Task Queue
# Updated: 2026-03-02 19:00 CET (Session 9 — Antigravity)
# Loop reads this on every heartbeat. Pick the first unchecked [ ] item.

---

## Active Tasks

- [ ] **Promote risk_integration.py from lab/ to core/**

  **Goal:** The risk gate bridge has been tested e2e (90/90 pass). It should move out of `lab/` and into the production path. The `from langgraph.graph import END` fix is already applied.

  **Where to write:** `core/risk_integration.py` (new file, copy from lab/)

  **What to do:**
  1. Read `lab/risk_integration.py` — this is the file to promote
  2. Copy it to `core/risk_integration.py`
  3. Update the import in `workflows/masterloop.py` from `from lab.risk_integration import ...` to `from core.risk_integration import ...`
  4. Update `tests/test_risk_integration.py` to import from `core.risk_integration`
  5. Report on Telegram when done
  6. **DO NOT delete the lab/ copy yet** — architect will verify and clean up

- [ ] **Add TradeProposal.from_signal() classmethod**

  **Goal:** Clean bridge from typed `Signal` objects directly to `TradeProposal`.

  **Context:** `observation_to_trade_proposal()` in risk_integration.py works on raw dicts. We also need a typed path from `Signal` (Pydantic) to `TradeProposal` (dataclass) for when the pipeline moves to fully-typed signals.

  **Where to write:** `lab/trade_proposal_bridge.py` (new file)

  **What to do:**
  1. Read `core/signal_model.py` — understand Signal class fields
  2. Read `core/risk.py` — understand TradeProposal fields
  3. Write `from_signal(signal: Signal) -> TradeProposal` that:
     - Maps `hypothesis` → `side` (Bullish→BUY, Bearish→SELL, Neutral→skip)
     - Uses `confidence` directly
     - Uses `outcome` directly
     - Defaults `proposed_size_usdc` to $5
     - Uses `signal_id` directly
  4. Write 5+ tests (with real Signal objects, not dicts)
  5. Report on Telegram when done

- [ ] **Audit and document dead fields: time_horizon**

  **Goal:** `time_horizon` defaults to "24h" in Signal and nothing sets it. Document whether to remove it or wire it.

  **Where to write:** `lab/reviews/dead_fields_audit.md`

  **What to do:**
  1. Search all files for `time_horizon` usage
  2. Determine: is it ever set to anything other than default?
  3. Recommend: keep (with wiring plan) or remove
  4. Report on Telegram

## Completed Tasks

- [x] Risk gate wired into MasterLoop (Session 8 — architect + Loop collab)
- [x] Schema unification — bitcoin_signal.py returns Signal objects (Session 6)
- [x] Architecture report — full codebase review (Session 6)
- [x] health_check.py — thermal, disk, DB freshness (Session 7)
- [x] test_risk_edge_cases.py — boundary tests for risk.py (Session 7)
- [x] schema_review.md — field usage audit (Session 7)
- [x] cycle_number fix — wired from LoopState into observations (Session 9 — Antigravity)
- [x] MasterLoop e2e smoke test — 4 tests, 90/90 pass (Session 9 — Antigravity)
- [x] route_after_risk_gate END bug — returned "END" string instead of langgraph END sentinel (Session 9 — Antigravity)
