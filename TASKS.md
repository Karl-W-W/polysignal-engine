# Loop Task Queue
# Updated: 2026-03-01 15:00 CET
# Loop reads this on every heartbeat. Pick the first unchecked [ ] item.

---

## Active Tasks

- [ ] **Wire risk.py into MasterLoop commit path**

  **Goal:** Before any trade action is committed, run it through the risk gate.

  **Where to write:** `lab/risk_integration.py` (new file, standalone test first)

  **What to do:**
  1. Read `core/risk.py` — understand `check_risk(trade: TradeProposal, tracker)` and `RiskVerdict`
  2. Read `workflows/masterloop.py` lines 388–444 — understand the `wait_approval_node` → `commit_node` flow
  3. Write a new function `risk_gate_node(state: LoopState) -> LoopState` that:
     - Extracts the signal from state (observations list)
     - Constructs a `TradeProposal` from the signal data
     - Calls `check_risk()`
     - If `verdict.approved == False`: set `state["execution_status"] = "RISK_BLOCKED"`, send Telegram alert, skip commit
     - If `verdict.requires_human_approval`: set `state["human_approval_needed"] = True`
     - If approved: pass through to commit
  4. Write a standalone test in `lab/risk_integration.py` that creates a mock state and verifies the gate works
  5. Report on Telegram when done — do NOT modify `workflows/masterloop.py` directly. Just write the function and test.

  **Acceptance criteria:** The function exists, the test passes when run manually, and the approach is documented in a Telegram message.

## Completed Tasks

- [x] Schema unification — `bitcoin_signal.py` returns Signal objects (Session 6)
- [x] Architecture report — full codebase review (Session 6)
