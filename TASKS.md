# Loop Task Queue
# Updated: 2026-03-01 18:00 CET
# Loop reads this on every heartbeat. Pick the first unchecked [ ] item.

---

## Active Tasks

- [ ] **Add TradeProposal.from_signal() classmethod to core/risk.py**

  **Goal:** Eliminate the manual Signal→TradeProposal conversion scattered across files.

  **Where to write:** `lab/trade_proposal_bridge.py` (new file)

  **What to do:**
  1. Read `core/signal_model.py` — understand the Signal class fields
  2. Read `core/risk.py` — understand TradeProposal fields
  3. Write a `from_signal(signal_dict: dict) -> TradeProposal` function that:
     - Maps Signal fields to TradeProposal fields cleanly
     - Derives `side` from `hypothesis` (Bullish→BUY, Bearish→SELL)
     - Uses Signal's `confidence` directly
     - Defaults `proposed_size_usdc` to $5 (conservative)
  4. Write 5+ tests in the same file
  5. Report on Telegram when done

- [ ] **Fix cycle_number (dead field)**

  **Goal:** `cycle_number` is always 0 in signals. Wire it from LoopState.

  **Where to write:** `workflows/masterloop.py` — in `perception_node()`

  **What to do:**
  1. In perception_node, after creating observations, set each observation's `cycle_number` from `state["cycle_number"]`
  2. This is a one-line fix. Report on Telegram.

- [ ] **Write MasterLoop end-to-end smoke test**

  **Goal:** A single test that runs the full graph with mocked external calls.

  **Where to write:** `lab/tests/test_masterloop_e2e.py`

  **What to do:**
  1. Mock: Polymarket API (return fake market), Ollama (return fake LLM response), OpenClaw (return "SUCCESS")
  2. Build initial LoopState, invoke `build_masterloop().compile()` with it
  3. Assert: pipeline completes, all 7 nodes execute, stage_timings populated
  4. This proves the graph wiring is correct end-to-end

## Completed Tasks

- [x] Risk gate wired into MasterLoop (Session 8 — architect + Loop collab)
- [x] Schema unification — bitcoin_signal.py returns Signal objects (Session 6)
- [x] Architecture report — full codebase review (Session 6)
- [x] health_check.py — thermal, disk, DB freshness (Session 7)
- [x] test_risk_edge_cases.py — boundary tests for risk.py (Session 7)
- [x] schema_review.md — field usage audit (Session 7)
