#!/usr/bin/env python3
"""
lab/risk_integration.py
=======================
Risk gate node for MasterLoop commit path.

This module provides `risk_gate_node()` — a LangGraph-compatible node function
that sits between REVIEW and COMMIT in the MasterLoop. It converts observation
data into a TradeProposal and runs it through check_risk() before allowing
execution.

Lab Promotion Protocol:
  1. Built in /lab ✅
  2. Standalone test below
  3. Human authorization required before editing masterloop.py
  4. Integration: insert as node between review and commit in build_masterloop()

Usage (after promotion):
    wf.add_node("risk_gate", risk_gate_node)
    wf.add_edge("review", "risk_gate")
    wf.add_conditional_edges("risk_gate", route_after_risk_gate, {...})
"""

import os
import sys
import json
import uuid
from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime, timezone

# Ensure imports work from various locations
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.risk import (
    TradeProposal,
    DailyPnLTracker,
    RiskVerdict,
    check_risk,
    MAX_POSITION_USDC,
    MIN_CONFIDENCE,
    DAILY_LOSS_CAP_USDC,
)

# ============================================================================
# TYPE STUB — mirrors workflows/masterloop.py LoopState
# ============================================================================

class LoopState(TypedDict):
    thread_id:    str
    cycle_number: int
    started_at:   str
    user_request: str
    observations: List[Dict]
    predictions:  List[Dict]
    draft_action:    Optional[Dict[str, Any]]
    draft_reasoning: Optional[str]
    audit_verdict:        Optional[Dict[str, Any]]
    signature:            Optional[str]
    human_approval_needed: bool
    human_approved:       Optional[bool]
    execution_result: Optional[str]
    execution_status: Optional[str]
    errors:        List[str]
    stage_timings: Dict[str, float]


# ============================================================================
# SIGNAL → TRADE PROPOSAL BRIDGE
# ============================================================================

def observation_to_trade_proposal(obs: Dict, draft: Dict) -> Optional[TradeProposal]:
    """
    Convert a masterloop observation dict + draft action into a TradeProposal.

    The observation comes from perception_node (_signal_to_observation format):
      - market_id, title, price, volume, change_24h, direction, url, source

    The draft comes from draft_node:
      - command, reasoning, tool

    Returns None if the observation doesn't look like a tradeable signal
    (e.g. no direction / quiet market observation).
    """
    direction = obs.get("direction", "")
    if not direction:
        return None  # Quiet market observation, not a signal

    # Determine side from direction
    if direction in ("📈", "Bullish", "UP"):
        side = "BUY"
        outcome = "Yes"
    elif direction in ("📉", "Bearish", "DOWN"):
        side = "SELL"
        outcome = "No"
    else:
        side = "BUY"  # Default conservative
        outcome = "Yes"

    # Extract confidence — check observation, then predictions if available
    confidence = obs.get("confidence", 0.5)

    # Extract title — observation format is "Title — Outcome"
    title = obs.get("title", "Unknown Market")

    # Price as current implied probability
    price = obs.get("price", 0.5)

    # Position sizing: start at MAX_POSITION_USDC, let risk gate clamp if needed
    # In production this would come from a Kelly criterion or similar
    proposed_size = min(MAX_POSITION_USDC, 5.0)  # Conservative $5 default

    return TradeProposal(
        market_id=obs.get("market_id", "unknown"),
        title=title,
        outcome=outcome,
        side=side,
        confidence=confidence,
        proposed_size_usdc=proposed_size,
        current_price=price,
        signal_id=str(uuid.uuid4()),
    )


# ============================================================================
# RISK GATE NODE
# ============================================================================

# Module-level tracker — in production, this persists across cycles
_tracker: Optional[DailyPnLTracker] = None


def get_tracker(state_path: str = None) -> DailyPnLTracker:
    """Get or create the daily P&L tracker."""
    global _tracker
    if _tracker is None:
        path = state_path or os.getenv(
            "RISK_STATE_PATH", "/opt/loop/data/risk_state.json"
        )
        _tracker = DailyPnLTracker(state_path=path)
    return _tracker


def risk_gate_node(state: LoopState) -> LoopState:
    """
    LangGraph node: risk gate between REVIEW and COMMIT.

    Behavior:
      1. If no draft action or already blocked → pass through
      2. Extract strongest signal from observations
      3. Build TradeProposal from signal + draft
      4. Run check_risk()
      5. On rejection → set RISK_BLOCKED, clear signature, send alert
      6. On human approval needed → set flag (existing wait_approval handles it)
      7. On approved → pass through to commit
    """
    print("\n[RISK_GATE] Checking trade risk limits...")
    start = datetime.now(timezone.utc)

    draft = state.get("draft_action")
    if not draft:
        print("  ⚠ No draft action — skipping risk gate")
        state["stage_timings"]["risk_gate"] = 0.0
        return state

    # If already blocked by supervisor, don't bother
    if not state.get("signature") and not state.get("human_approval_needed"):
        print("  ⚠ No signature and no human approval pending — already blocked")
        state["stage_timings"]["risk_gate"] = 0.0
        return state

    # Find the strongest signal (observation with a direction)
    observations = state.get("observations", [])
    signal_obs = [o for o in observations if o.get("direction")]

    if not signal_obs:
        # No actionable signals — this might be a non-trade command (e.g. "ls")
        # Let it through; the risk gate only applies to trade-like actions
        print("  ✓ No trade signals in observations — passthrough (non-trade action)")
        state["stage_timings"]["risk_gate"] = (
            datetime.now(timezone.utc) - start
        ).total_seconds()
        return state

    # Use the first/strongest signal
    obs = signal_obs[0]
    trade = observation_to_trade_proposal(obs, draft)

    if trade is None:
        print("  ✓ Observation not tradeable — passthrough")
        state["stage_timings"]["risk_gate"] = (
            datetime.now(timezone.utc) - start
        ).total_seconds()
        return state

    # Enrich confidence from predictions if available
    predictions = state.get("predictions", [])
    if predictions:
        # Find matching prediction by market_id
        for pred in predictions:
            if pred.get("market_id") == trade.market_id:
                pred_confidence = pred.get("confidence", pred.get("probability"))
                if pred_confidence is not None:
                    trade.confidence = float(pred_confidence)
                    break

    # Run the risk gate
    tracker = get_tracker()
    verdict = check_risk(trade, tracker)

    print(f"  {'✅' if verdict.approved else '❌'} Risk verdict: "
          f"{'APPROVED' if verdict.approved else 'REJECTED'}")
    print(f"     Checks passed: {verdict.checks_passed}")
    if verdict.checks_failed:
        print(f"     Checks failed: {verdict.checks_failed}")

    if not verdict.approved:
        # BLOCKED — clear signature, set status, record in errors
        state["execution_status"] = "RISK_BLOCKED"
        state["execution_result"] = verdict.rejection_reason
        state["signature"] = None  # Prevent commit
        state["human_approval_needed"] = False
        state["errors"].append(f"Risk gate: {verdict.rejection_reason}")

        # Send Telegram alert
        alert_msg = verdict.to_telegram_message()
        try:
            from core.notifications import send_telegram_alert
            send_telegram_alert(alert_msg)
        except ImportError:
            print(f"  [ALERT] {alert_msg}")

        print(f"  🛑 Trade blocked: {verdict.rejection_reason}")

    elif verdict.requires_human_approval:
        # Need human YES — set the flag, existing wait_approval_node handles it
        state["human_approval_needed"] = True
        print(f"  ⚠ Human approval required (trade #{tracker.total_trades + 1})")

        try:
            from core.notifications import send_telegram_alert
            send_telegram_alert(verdict.to_telegram_message())
        except ImportError:
            print(f"  [ALERT] {verdict.to_telegram_message()}")

    else:
        # Approved — pass through, record the approved size for commit to use
        if state.get("draft_action"):
            state["draft_action"]["risk_approved_size_usdc"] = verdict.approved_size_usdc
        print(f"  ✅ Risk approved: ${verdict.approved_size_usdc:.2f} USDC")

    state["stage_timings"]["risk_gate"] = (
        datetime.now(timezone.utc) - start
    ).total_seconds()
    return state


# ============================================================================
# ROUTING (for integration into masterloop graph)
# ============================================================================

def route_after_risk_gate(state: LoopState) -> str:
    """
    Router for after the risk gate node.
    Returns the next node name or END.
    """
    if state.get("execution_status") == "RISK_BLOCKED":
        return "END"  # Skip commit entirely
    if state.get("human_approval_needed"):
        return "wait_approval"
    if state.get("signature"):
        return "commit"
    return "END"


# ============================================================================
# INTEGRATION INSTRUCTIONS (for masterloop.py — DO NOT APPLY YET)
# ============================================================================
"""
To wire into masterloop.py after human approval:

1. Add import:
   from lab.risk_integration import risk_gate_node, route_after_risk_gate

2. Add node:
   wf.add_node("risk_gate", risk_gate_node)

3. Replace the edge from review:
   OLD:
     wf.add_conditional_edges("review", route_after_review,
         {"wait_approval": "wait_approval", "commit": "commit", END: END})

   NEW:
     wf.add_conditional_edges("review", route_after_review_to_risk,
         {"risk_gate": "risk_gate", END: END})
     wf.add_conditional_edges("risk_gate", route_after_risk_gate,
         {"wait_approval": "wait_approval", "commit": "commit", END: END})

4. Update route_after_review to send approved/human_approval to risk_gate:
     def route_after_review_to_risk(state):
         if state.get("human_approval_needed") or state.get("signature"):
             return "risk_gate"
         return END  # Rejected by supervisor
"""


# ============================================================================
# STANDALONE TEST
# ============================================================================

def _run_tests():
    """Self-contained tests — no external deps needed."""
    import core.risk as risk_module

    print("=" * 60)
    print("Risk Integration — Standalone Tests")
    print("=" * 60)

    passed = 0
    failed = 0

    def assert_test(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  ✅ {name}")
            passed += 1
        else:
            print(f"  ❌ {name}: {detail}")
            failed += 1

    # --- Mock tracker (no disk I/O) ---
    class MockTracker(DailyPnLTracker):
        def __init__(self, total_trades=10, daily_loss=0.0):
            self._state = {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "total_trades": total_trades,
                "daily_loss_usdc": daily_loss,
                "trades_today": 0,
                "trade_log": [],
            }
        def save(self): pass

    # Monkey-patch the tracker
    global _tracker
    _tracker = MockTracker()

    # --- Build a realistic mock state ---
    def make_state(direction="📈", confidence=0.85, has_signature=True) -> LoopState:
        return {
            "thread_id": "test-risk-integration",
            "cycle_number": 1,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "user_request": "test",
            "observations": [{
                "market_id": "0xtest",
                "title": "BTC above $100k — Yes",
                "price": 0.71,
                "volume": 1_000_000,
                "change_24h": 0.05,
                "direction": direction,
                "url": "https://polymarket.com/event/btc-100k",
                "source": "polymarket",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "confidence": confidence,
            }],
            "predictions": [{
                "market_id": "0xtest",
                "confidence": confidence,
            }],
            "draft_action": {
                "tool": "openclaw_execute",
                "command": "echo 'execute trade'",
                "reasoning": "test trade",
            },
            "draft_reasoning": "test",
            "audit_verdict": {"verdict": "APPROVE", "risk_level": "medium"},
            "signature": "fakesig123" if has_signature else None,
            "human_approval_needed": False,
            "human_approved": None,
            "execution_result": None,
            "execution_status": None,
            "errors": [],
            "stage_timings": {},
        }

    # ---- TEST 1: Kill switch blocks (TRADING_ENABLED=False by default) ----
    print("\n[Test 1] Kill switch blocks trade through risk gate")
    state = make_state()
    result = risk_gate_node(state)
    assert_test("Status is RISK_BLOCKED", result["execution_status"] == "RISK_BLOCKED")
    assert_test("Signature cleared", result["signature"] is None)
    assert_test("Error recorded", any("Risk gate" in e for e in result["errors"]))

    # ---- TEST 2: Low confidence rejected ----
    print("\n[Test 2] Low confidence rejected")
    risk_module.TRADING_ENABLED = True
    state = make_state(confidence=0.60)
    result = risk_gate_node(state)
    assert_test("Status is RISK_BLOCKED", result["execution_status"] == "RISK_BLOCKED")
    assert_test("Mentions confidence", "confidence" in (result["execution_result"] or "").lower())
    risk_module.TRADING_ENABLED = False

    # ---- TEST 3: Good trade approved ----
    print("\n[Test 3] Good trade passes risk gate")
    risk_module.TRADING_ENABLED = True
    _tracker = MockTracker(total_trades=10)  # Past human approval gate
    state = make_state(confidence=0.85)
    result = risk_gate_node(state)
    assert_test("Not blocked", result["execution_status"] != "RISK_BLOCKED")
    assert_test("Signature preserved", result["signature"] is not None)
    assert_test("Risk approved size stored",
                result["draft_action"].get("risk_approved_size_usdc") is not None)
    risk_module.TRADING_ENABLED = False

    # ---- TEST 4: Human approval for first N trades ----
    print("\n[Test 4] Human approval required for early trades")
    risk_module.TRADING_ENABLED = True
    _tracker = MockTracker(total_trades=2)  # Under HUMAN_APPROVAL_FIRST_N=5
    state = make_state(confidence=0.85)
    result = risk_gate_node(state)
    assert_test("Human approval set", result["human_approval_needed"] is True)
    assert_test("Not blocked", result.get("execution_status") != "RISK_BLOCKED")
    risk_module.TRADING_ENABLED = False

    # ---- TEST 5: Non-trade action passes through ----
    print("\n[Test 5] Non-trade action (no signals) passes through")
    state = make_state()
    state["observations"] = [{"market_id": "x", "title": "BTC", "price": 0.5,
                               "volume": 100, "change_24h": 0.0, "direction": "",
                               "url": "", "source": "polymarket",
                               "timestamp": datetime.now(timezone.utc).isoformat()}]
    result = risk_gate_node(state)
    assert_test("Passthrough (no block)", result.get("execution_status") != "RISK_BLOCKED")
    assert_test("Signature untouched", result["signature"] == "fakesig123")

    # ---- TEST 6: Daily loss cap ----
    print("\n[Test 6] Daily loss cap blocks trade")
    risk_module.TRADING_ENABLED = True
    _tracker = MockTracker(total_trades=10, daily_loss=55.0)
    state = make_state(confidence=0.90)
    result = risk_gate_node(state)
    assert_test("Status is RISK_BLOCKED", result["execution_status"] == "RISK_BLOCKED")
    assert_test("Mentions daily loss", "daily loss" in (result["execution_result"] or "").lower())
    risk_module.TRADING_ENABLED = False

    # ---- TEST 7: observation_to_trade_proposal ----
    print("\n[Test 7] observation_to_trade_proposal conversion")
    obs_bull = {"market_id": "0x1", "title": "Test", "price": 0.6,
                "volume": 100, "direction": "📈", "confidence": 0.8}
    tp = observation_to_trade_proposal(obs_bull, {"command": "test"})
    assert_test("Bullish → BUY", tp.side == "BUY")
    assert_test("Bullish → Yes", tp.outcome == "Yes")

    obs_bear = {"market_id": "0x2", "title": "Test", "price": 0.4,
                "volume": 100, "direction": "📉", "confidence": 0.9}
    tp2 = observation_to_trade_proposal(obs_bear, {"command": "test"})
    assert_test("Bearish → SELL", tp2.side == "SELL")

    obs_quiet = {"market_id": "0x3", "title": "Test", "price": 0.5,
                 "volume": 100, "direction": ""}
    tp3 = observation_to_trade_proposal(obs_quiet, {"command": "test"})
    assert_test("No direction → None", tp3 is None)

    # ---- SUMMARY ----
    print("\n" + "=" * 60)
    total = passed + failed
    if failed == 0:
        print(f"✅ ALL {total} TESTS PASSED")
    else:
        print(f"❌ {failed}/{total} TESTS FAILED")
    print("=" * 60)

    # Reset
    _tracker = None
    return failed == 0


if __name__ == "__main__":
    success = _run_tests()
    exit(0 if success else 1)
