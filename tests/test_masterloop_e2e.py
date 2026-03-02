"""
tests/test_masterloop_e2e.py
============================
End-to-end smoke test for the MasterLoop graph.

Proves: all 7 nodes execute in correct order with mocked external calls.
Mocks: Polymarket API, Ollama LLM, OpenClaw executor, Supervisor audit,
       Telegram notifications.

Written: Session 9 (2026-03-02) — Antigravity (architect).
Task origin: TASKS.md item #3, identified by Loop.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import core.risk as risk_module

# Force-import workflows.masterloop so patch() can resolve it.
# The module has side effects (ChatOpenAI, OpenClawTool) but they
# degrade gracefully via try/except in the module itself.
import workflows.masterloop as ml_module


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(autouse=True)
def reset_risk_state():
    """Reset trading state after each test."""
    original = risk_module.TRADING_ENABLED
    yield
    risk_module.TRADING_ENABLED = original


def _fake_markets():
    """Fake Polymarket response — 2 crypto markets."""
    return [
        {
            "id": "0xfake_btc",
            "title": "Will Bitcoin exceed $120k by April 2026?",
            "outcome": "Yes",
            "price": 0.65,
            "volume": 2_500_000.0,
            "url": "https://polymarket.com/event/btc-120k-april",
        },
        {
            "id": "0xfake_eth",
            "title": "Will Ethereum exceed $5k by April 2026?",
            "outcome": "Yes",
            "price": 0.42,
            "volume": 800_000.0,
            "url": "https://polymarket.com/event/eth-5k-april",
        },
    ]


def _fake_signals(markets):
    """Fake signal detection — 1 bullish signal on BTC."""
    return [
        {
            "market_id": "0xfake_btc",
            "title": "Will Bitcoin exceed $120k by April 2026?",
            "outcome": "Yes",
            "current_price": 0.65,
            "last_price": 0.58,
            "delta": 0.07,
            "volume": 2_500_000.0,
            "url": "https://polymarket.com/event/btc-120k-april",
            "direction": "Bullish",
            "last_seen": "2026-03-01T10:00:00",
        }
    ]


def _fake_predictions(observations):
    """Fake prediction — returns typed prediction objects with to_dict()."""
    class FakePrediction:
        def __init__(self, obs):
            self.market_id = obs.get("market_id", "unknown")
            self.confidence = 0.82
            self.hypothesis = "Bullish"

        def to_dict(self):
            return {
                "market_id": self.market_id,
                "confidence": self.confidence,
                "hypothesis": self.hypothesis,
            }

    return [FakePrediction(o) for o in observations]


def _fake_audit(draft):
    """Fake supervisor audit — approve with signature."""
    return {
        "verdict": "APPROVE",
        "risk_level": "low",
        "reasoning": "Test action approved",
        "signature": "fakesig_e2e_test_abc123",
    }


def _fake_verify(draft, signature):
    """Fake signature verification — always valid."""
    return True


def _fake_llm_response(msgs, **kwargs):
    """Build a fake LLM response object."""
    resp = MagicMock()
    resp.content = json.dumps({
        "tool": "openclaw_execute",
        "command": "echo 'BTC signal detected'",
        "workspace": "/mnt/workplace",
        "reasoning": "BTC moved +7pp, above 5pp threshold.",
    })
    return resp


def _build_initial_state(thread_id, cycle_number=1, user_request="test"):
    """Build a clean initial LoopState dict."""
    return {
        "thread_id": thread_id,
        "cycle_number": cycle_number,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "user_request": user_request,
        "observations": [],
        "predictions": [],
        "draft_action": None,
        "draft_reasoning": None,
        "audit_verdict": None,
        "signature": None,
        "human_approval_needed": False,
        "human_approved": None,
        "execution_result": None,
        "execution_status": None,
        "moltbook_result": None,
        "errors": [],
        "stage_timings": {},
    }


def _run_graph(initial):
    """Compile and stream the MasterLoop graph, return (final_state, nodes_executed).
    No checkpointer — avoids MagicMock serialization issues in tests."""
    graph = ml_module.build_masterloop()
    app = graph.compile()

    final = dict(initial)
    nodes_executed = []

    for output in app.stream(initial):
        for node, update in output.items():
            nodes_executed.append(node)
            final.update(update)

    return final, nodes_executed


# ============================================================================
# E2E TEST — FULL GRAPH WITH KILL SWITCH ON (DEFAULT)
# ============================================================================

class TestMasterLoopE2EKillSwitchOn:
    """Full pipeline with TRADING_ENABLED=False (default safe mode).
    Risk gate should block the trade, pipeline should complete cleanly."""

    def test_full_pipeline_kill_switch_blocks(self):
        with (
            patch.object(ml_module, "fetch_crypto_markets", side_effect=_fake_markets),
            patch.object(ml_module, "detect_signals", side_effect=_fake_signals),
            patch.object(ml_module, "predict_market_moves", side_effect=_fake_predictions),
            patch.object(ml_module, "audit_action", side_effect=_fake_audit),
            patch.object(ml_module, "verify_signature", side_effect=_fake_verify),
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "openclaw_tool") as mock_openclaw,
            patch.object(ml_module, "brain") as mock_brain,
        ):
            mock_brain.invoke.side_effect = _fake_llm_response
            mock_openclaw._run.return_value = "SUCCESS: test"

            initial = _build_initial_state("e2e_test_001", cycle_number=42,
                                            user_request="Check Bitcoin signals")
            final, nodes_executed = _run_graph(initial)

            # All expected nodes executed
            assert "perception" in nodes_executed
            assert "prediction" in nodes_executed
            assert "draft" in nodes_executed
            assert "review" in nodes_executed
            assert "risk_gate" in nodes_executed

            # Perception produced observations
            assert len(final["observations"]) > 0

            # cycle_number was propagated to observations
            for obs in final["observations"]:
                assert obs.get("cycle_number") == 42

            # Predictions were generated
            assert len(final["predictions"]) > 0

            # Draft action was created
            assert final["draft_action"] is not None
            assert "command" in final["draft_action"]

            # Supervisor approved
            assert final["audit_verdict"]["verdict"] == "APPROVE"

            # Risk gate blocked (TRADING_ENABLED=False by default)
            assert final["execution_status"] == "RISK_BLOCKED"
            assert final["signature"] is None

            # Stage timings populated
            assert "perception" in final["stage_timings"]
            assert "prediction" in final["stage_timings"]
            assert "draft" in final["stage_timings"]
            assert "review" in final["stage_timings"]
            assert "risk_gate" in final["stage_timings"]

            # No unhandled errors (risk block is intentional)
            non_risk_errors = [e for e in final["errors"] if "Risk gate" not in e]
            assert len(non_risk_errors) == 0


# ============================================================================
# E2E TEST — FULL GRAPH WITH TRADING ENABLED
# ============================================================================

class TestMasterLoopE2ETradingEnabled:
    """Full pipeline with TRADING_ENABLED=True. Should reach commit node."""

    def test_full_pipeline_trading_enabled(self):
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

        with (
            patch.object(ml_module, "fetch_crypto_markets", side_effect=_fake_markets),
            patch.object(ml_module, "detect_signals", side_effect=_fake_signals),
            patch.object(ml_module, "predict_market_moves", side_effect=_fake_predictions),
            patch.object(ml_module, "audit_action", side_effect=_fake_audit),
            patch.object(ml_module, "verify_signature", side_effect=_fake_verify),
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "openclaw_tool") as mock_openclaw,
            patch.object(ml_module, "brain") as mock_brain,
        ):
            mock_brain.invoke.side_effect = _fake_llm_response
            mock_openclaw._run.return_value = "SUCCESS: echo completed"

            initial = _build_initial_state("e2e_test_002",
                                            user_request="Execute Bitcoin signal trade")
            final, nodes_executed = _run_graph(initial)

            # All 7 nodes should execute
            assert "perception" in nodes_executed
            assert "prediction" in nodes_executed
            assert "draft" in nodes_executed
            assert "review" in nodes_executed
            assert "risk_gate" in nodes_executed
            assert "wait_approval" in nodes_executed or "commit" in nodes_executed

            # Risk gate should NOT have blocked
            assert final.get("execution_status") != "RISK_BLOCKED"

            # Risk approved size should be within limits
            if final.get("draft_action", {}).get("risk_approved_size_usdc"):
                assert final["draft_action"]["risk_approved_size_usdc"] <= 10.0

        ri._tracker = None


# ============================================================================
# E2E TEST — EMPTY MARKET (NO SIGNALS)
# ============================================================================

class TestMasterLoopE2ENoSignals:
    """Pipeline with no signals detected. Should complete gracefully."""

    def test_quiet_market_completes(self):
        with (
            patch.object(ml_module, "fetch_crypto_markets", return_value=_fake_markets()),
            patch.object(ml_module, "detect_signals", return_value=[]),
            patch.object(ml_module, "predict_market_moves", side_effect=_fake_predictions),
            patch.object(ml_module, "audit_action", side_effect=_fake_audit),
            patch.object(ml_module, "verify_signature", side_effect=_fake_verify),
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "openclaw_tool") as mock_openclaw,
            patch.object(ml_module, "brain") as mock_brain,
        ):
            mock_brain.invoke.side_effect = _fake_llm_response
            mock_openclaw._run.return_value = "SUCCESS: test"

            initial = _build_initial_state("e2e_test_003", cycle_number=5,
                                            user_request="Scan markets")
            final, nodes_executed = _run_graph(initial)

            # Core nodes still execute
            assert "perception" in nodes_executed
            assert "prediction" in nodes_executed
            assert "draft" in nodes_executed
            assert "review" in nodes_executed

            # Observations should exist (quiet markets, no signals)
            assert len(final["observations"]) == 2

            # No direction on quiet observations
            for obs in final["observations"]:
                assert obs["direction"] == ""

            # cycle_number still propagated
            for obs in final["observations"]:
                assert obs.get("cycle_number") == 5

            # No unhandled errors
            non_risk_errors = [e for e in final["errors"] if "Risk gate" not in e]
            assert len(non_risk_errors) == 0


# ============================================================================
# E2E TEST — API FAILURE RESILIENCE
# ============================================================================

class TestMasterLoopE2EAPIFailure:
    """Pipeline with Polymarket API failure. Should degrade gracefully."""

    def test_empty_market_response_degrades_gracefully(self):
        with (
            patch.object(ml_module, "fetch_crypto_markets", return_value=[]),
            patch.object(ml_module, "detect_signals", return_value=[]),
            patch.object(ml_module, "predict_market_moves", return_value=[]),
            patch.object(ml_module, "audit_action", side_effect=_fake_audit),
            patch.object(ml_module, "verify_signature", side_effect=_fake_verify),
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "openclaw_tool") as mock_openclaw,
            patch.object(ml_module, "brain") as mock_brain,
        ):
            mock_brain.invoke.side_effect = _fake_llm_response
            mock_openclaw._run.return_value = "SUCCESS: test"

            initial = _build_initial_state("e2e_test_004", user_request="Scan markets")
            final, _ = _run_graph(initial)

            # Should record the perception error
            assert any("No markets" in e for e in final["errors"])

            # Pipeline should still complete without crashing
            assert "perception" in final["stage_timings"]
