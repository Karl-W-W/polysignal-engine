"""
Tests for core/risk_integration.py — Risk gate node for MasterLoop.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from core.risk_integration import (
    risk_gate_node,
    route_after_risk_gate,
    observation_to_trade_proposal,
)
import core.risk as risk_module


def _make_state(direction="Bullish", confidence=0.85, has_signature=True, observations=None):
    """Build a realistic mock LoopState."""
    obs = observations if observations is not None else [{
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
    }]
    return {
        "thread_id": "test",
        "cycle_number": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "user_request": "test",
        "observations": obs,
        "predictions": [{"market_id": "0xtest", "confidence": confidence}],
        "draft_action": {"tool": "exec_cmd", "command": "echo trade", "reasoning": "test"},
        "draft_reasoning": "test",
        "audit_verdict": {"verdict": "APPROVE"},
        "signature": "fakesig123" if has_signature else None,
        "human_approval_needed": False,
        "human_approved": None,
        "execution_result": None,
        "execution_status": None,
        "errors": [],
        "stage_timings": {},
    }


@pytest.fixture(autouse=True)
def reset_risk_state():
    """Reset kill switch and tracker after each test."""
    original = risk_module.TRADING_ENABLED
    import core.risk_integration as ri
    ri._tracker = None
    yield
    risk_module.TRADING_ENABLED = original
    ri._tracker = None


# ============================================================================
# observation_to_trade_proposal
# ============================================================================

class TestObservationToTradeProposal:
    def test_bullish_signal(self):
        obs = {"market_id": "0x1", "title": "Test", "price": 0.6,
               "volume": 100, "direction": "Bullish", "confidence": 0.8}
        tp = observation_to_trade_proposal(obs, {"command": "test"})
        assert tp is not None
        assert tp.side == "BUY"
        assert tp.outcome == "Yes"
        assert tp.confidence == 0.8

    def test_bearish_signal(self):
        obs = {"market_id": "0x2", "title": "Test", "price": 0.4,
               "volume": 100, "direction": "Bearish", "confidence": 0.9}
        tp = observation_to_trade_proposal(obs, {"command": "test"})
        assert tp is not None
        assert tp.side == "SELL"
        assert tp.outcome == "No"

    def test_emoji_direction(self):
        obs = {"market_id": "0x3", "title": "Test", "price": 0.5,
               "volume": 100, "direction": "\U0001f4c8", "confidence": 0.7}
        tp = observation_to_trade_proposal(obs, {"command": "test"})
        assert tp is not None
        assert tp.side == "BUY"

    def test_no_direction_returns_none(self):
        obs = {"market_id": "0x4", "title": "Test", "price": 0.5,
               "volume": 100, "direction": ""}
        tp = observation_to_trade_proposal(obs, {"command": "test"})
        assert tp is None

    def test_missing_direction_returns_none(self):
        obs = {"market_id": "0x5", "title": "Test", "price": 0.5, "volume": 100}
        tp = observation_to_trade_proposal(obs, {"command": "test"})
        assert tp is None


# ============================================================================
# risk_gate_node
# ============================================================================

class TestRiskGateNode:
    def test_kill_switch_blocks(self):
        """Default TRADING_ENABLED=False blocks everything."""
        state = _make_state()
        result = risk_gate_node(state)
        assert result["execution_status"] == "RISK_BLOCKED"
        assert result["signature"] is None

    def test_low_confidence_blocked(self):
        risk_module.TRADING_ENABLED = True
        state = _make_state(confidence=0.60)
        result = risk_gate_node(state)
        assert result["execution_status"] == "RISK_BLOCKED"
        assert "confidence" in (result["execution_result"] or "").lower()

    def test_good_trade_approved(self):
        risk_module.TRADING_ENABLED = True
        import core.risk_integration as ri
        from core.risk import DailyPnLTracker

        class MockTracker(DailyPnLTracker):
            def __init__(self):
                self._state = {
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "total_trades": 10,
                    "daily_loss_usdc": 0.0,
                    "trades_today": 0,
                    "trade_log": [],
                }
            def save(self): pass

        ri._tracker = MockTracker()
        state = _make_state(confidence=0.85)
        result = risk_gate_node(state)
        assert result["execution_status"] != "RISK_BLOCKED"
        assert result["signature"] is not None
        assert result["draft_action"].get("risk_approved_size_usdc") is not None

    def test_no_draft_passthrough(self):
        state = _make_state()
        state["draft_action"] = None
        result = risk_gate_node(state)
        assert result.get("execution_status") != "RISK_BLOCKED"

    def test_no_signals_passthrough(self):
        """Non-trade action (no directional signals) passes through."""
        state = _make_state()
        state["observations"] = [{"market_id": "x", "title": "Test",
                                   "price": 0.5, "volume": 100,
                                   "direction": "", "source": "polymarket",
                                   "timestamp": datetime.now(timezone.utc).isoformat()}]
        result = risk_gate_node(state)
        assert result.get("execution_status") != "RISK_BLOCKED"
        assert result["signature"] == "fakesig123"

    def test_no_signature_skips(self):
        """Already blocked by supervisor — risk gate skips."""
        state = _make_state(has_signature=False)
        result = risk_gate_node(state)
        assert result.get("execution_status") != "RISK_BLOCKED"


# ============================================================================
# route_after_risk_gate
# ============================================================================

class TestRouteAfterRiskGate:
    def test_blocked_returns_end(self):
        from langgraph.graph import END
        state = {"execution_status": "RISK_BLOCKED", "human_approval_needed": False, "signature": None}
        assert route_after_risk_gate(state) == END

    def test_human_approval_routes_to_wait(self):
        state = {"execution_status": None, "human_approval_needed": True, "signature": "sig"}
        assert route_after_risk_gate(state) == "wait_approval"

    def test_approved_routes_to_commit(self):
        state = {"execution_status": None, "human_approval_needed": False, "signature": "sig"}
        assert route_after_risk_gate(state) == "commit"

    def test_no_signature_returns_end(self):
        from langgraph.graph import END
        state = {"execution_status": None, "human_approval_needed": False, "signature": None}
        assert route_after_risk_gate(state) == END
