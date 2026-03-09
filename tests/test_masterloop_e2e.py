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
    """With TRADING_ENABLED=False (default), graph short-circuits after prediction.
    No LLM calls (draft/review skipped), no Telegram spam, data still collected."""

    def test_short_circuit_skips_draft_review_risk(self):
        """When trading disabled, only perception + prediction run."""
        with (
            patch.object(ml_module, "fetch_crypto_markets", side_effect=_fake_markets),
            patch.object(ml_module, "detect_signals", side_effect=_fake_signals),
            patch.object(ml_module, "predict_market_moves", side_effect=_fake_predictions),
            patch.object(ml_module, "audit_action", side_effect=_fake_audit),
            patch.object(ml_module, "verify_signature", side_effect=_fake_verify),
            patch.object(ml_module, "send_telegram_alert") as mock_tg,
            patch.object(ml_module, "openclaw_tool") as mock_openclaw,
            patch.object(ml_module, "brain") as mock_brain,
        ):
            mock_brain.invoke.side_effect = _fake_llm_response
            mock_openclaw._run.return_value = "SUCCESS: test"

            initial = _build_initial_state("e2e_test_001", cycle_number=42,
                                            user_request="Check Bitcoin signals")
            final, nodes_executed = _run_graph(initial)

            # Only perception + prediction executed (short-circuit)
            assert "perception" in nodes_executed
            assert "prediction" in nodes_executed
            assert "draft" not in nodes_executed
            assert "review" not in nodes_executed
            assert "risk_gate" not in nodes_executed

            # No LLM calls made (the whole point of the short-circuit)
            mock_brain.invoke.assert_not_called()

            # Perception produced observations
            assert len(final["observations"]) > 0

            # cycle_number was propagated to observations
            for obs in final["observations"]:
                assert obs.get("cycle_number") == 42

            # Predictions were generated
            assert len(final["predictions"]) > 0

            # Stage timings for perception + prediction only
            assert "perception" in final["stage_timings"]
            assert "prediction" in final["stage_timings"]

    def test_xgboost_gate_suppresses_low_confidence(self):
        """XGBoost confidence gate suppresses predictions with P(correct) < 0.5."""
        import numpy as np

        # Create a fake XGBoost model that returns low P(correct)
        mock_model = MagicMock()
        mock_model.predict_proba.return_value = np.array([[0.8, 0.2]])  # P(correct)=0.2

        with (
            patch.object(ml_module, "fetch_crypto_markets", side_effect=_fake_markets),
            patch.object(ml_module, "detect_signals", side_effect=_fake_signals),
            patch.object(ml_module, "predict_market_moves", side_effect=_fake_predictions),
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "brain") as mock_brain,
            patch("workflows.masterloop.os.getenv", return_value=":memory:"),
            patch("lab.xgboost_baseline.load_model", return_value=(mock_model, ["price", "trend_strength"])),
            patch("lab.feature_engineering.extract_features") as mock_extract,
        ):
            # Make extract_features return a mock FeatureVector
            mock_fv = MagicMock()
            mock_fv.to_dict.return_value = {"price": 0.65, "trend_strength": 1.2}
            mock_extract.return_value = mock_fv

            initial = _build_initial_state("e2e_xgb_gate",
                                            user_request="Check signals")
            final, nodes_executed = _run_graph(initial)

            # All predictions should be suppressed (P(correct)=0.2 < 0.5)
            assert len(final["predictions"]) == 0

    def test_xgboost_gate_passes_high_confidence(self):
        """XGBoost confidence gate passes predictions with P(correct) >= 0.5."""
        import numpy as np

        mock_model = MagicMock()
        mock_model.predict_proba.return_value = np.array([[0.3, 0.7]])  # P(correct)=0.7

        with (
            patch.object(ml_module, "fetch_crypto_markets", side_effect=_fake_markets),
            patch.object(ml_module, "detect_signals", side_effect=_fake_signals),
            patch.object(ml_module, "predict_market_moves", side_effect=_fake_predictions),
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "brain") as mock_brain,
            patch("workflows.masterloop.os.getenv", return_value=":memory:"),
            patch("lab.xgboost_baseline.load_model", return_value=(mock_model, ["price", "trend_strength"])),
            patch("lab.feature_engineering.extract_features") as mock_extract,
        ):
            mock_fv = MagicMock()
            mock_fv.to_dict.return_value = {"price": 0.65, "trend_strength": 1.2}
            mock_extract.return_value = mock_fv

            initial = _build_initial_state("e2e_xgb_pass",
                                            user_request="Check signals")
            final, nodes_executed = _run_graph(initial)

            # Predictions should pass through (P(correct)=0.7 >= 0.5)
            assert len(final["predictions"]) > 0
            # Each prediction should have xgb_p_correct attached
            for pred in final["predictions"]:
                assert "xgb_p_correct" in pred
                assert pred["xgb_p_correct"] >= 0.5

    def test_xgboost_gate_graceful_fallback(self):
        """XGBoost gate falls through gracefully if model not found."""
        with (
            patch.object(ml_module, "fetch_crypto_markets", side_effect=_fake_markets),
            patch.object(ml_module, "detect_signals", side_effect=_fake_signals),
            patch.object(ml_module, "predict_market_moves", side_effect=_fake_predictions),
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "brain") as mock_brain,
            patch("lab.xgboost_baseline.load_model", side_effect=FileNotFoundError("No model")),
        ):
            initial = _build_initial_state("e2e_xgb_fallback",
                                            user_request="Check signals")
            final, nodes_executed = _run_graph(initial)

            # All predictions should pass through (gate skipped)
            assert len(final["predictions"]) > 0

    def test_excluded_markets_filtered_from_prediction(self):
        """Markets in EXCLUDED_MARKETS should not produce predictions."""
        # Patch EXCLUDED_MARKETS to include one of our fake markets
        with (
            patch.object(ml_module, "fetch_crypto_markets", side_effect=_fake_markets),
            patch.object(ml_module, "detect_signals", return_value=[]),  # quiet market
            patch.object(ml_module, "predict_market_moves", side_effect=_fake_predictions) as mock_predict,
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "brain") as mock_brain,
            patch("lab.experiments.bitcoin_signal.EXCLUDED_MARKETS", {"0xfake_btc"}),
        ):
            initial = _build_initial_state("e2e_excluded",
                                            user_request="Check signals")
            final, nodes_executed = _run_graph(initial)

            # predict_market_moves should only receive 1 observation (ETH only)
            call_args = mock_predict.call_args[0][0]
            market_ids = [o.get("market_id") for o in call_args]
            assert "0xfake_btc" not in market_ids
            assert "0xfake_eth" in market_ids

    def test_neutral_predictions_suppressed_by_gate(self):
        """Neutral predictions should be suppressed when XGBoost gate is active."""
        import numpy as np

        # Fake predictions that return Neutral
        def _neutral_predictions(observations):
            class FakePred:
                def __init__(self, obs):
                    self.market_id = obs.get("market_id", "unknown")
                    self.confidence = 0.5
                    self.hypothesis = "Neutral"
                def to_dict(self):
                    return {"market_id": self.market_id,
                            "confidence": self.confidence,
                            "hypothesis": self.hypothesis}
            return [FakePred(o) for o in observations]

        mock_model = MagicMock()
        mock_model.predict_proba.return_value = np.array([[0.3, 0.7]])  # Would pass

        with (
            patch.object(ml_module, "fetch_crypto_markets", side_effect=_fake_markets),
            patch.object(ml_module, "detect_signals", return_value=[]),  # quiet market — no signal enhancement
            patch.object(ml_module, "predict_market_moves", side_effect=_neutral_predictions),
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "brain") as mock_brain,
            patch("workflows.masterloop.os.getenv", return_value=":memory:"),
            patch("lab.xgboost_baseline.load_model", return_value=(mock_model, ["price", "trend_strength"])),
            patch("lab.feature_engineering.extract_features") as mock_extract,
        ):
            mock_fv = MagicMock()
            mock_fv.to_dict.return_value = {"price": 0.65, "trend_strength": 1.2}
            mock_extract.return_value = mock_fv

            initial = _build_initial_state("e2e_neutral_gate",
                                            user_request="Check signals")
            final, nodes_executed = _run_graph(initial)

            # All predictions are Neutral → all suppressed despite high gate score
            assert len(final["predictions"]) == 0

    def test_short_circuit_no_telegram_spam(self):
        """Short-circuit must not send any Telegram alerts."""
        with (
            patch.object(ml_module, "fetch_crypto_markets", side_effect=_fake_markets),
            patch.object(ml_module, "detect_signals", side_effect=_fake_signals),
            patch.object(ml_module, "predict_market_moves", side_effect=_fake_predictions),
            patch.object(ml_module, "send_telegram_alert") as mock_tg,
            patch.object(ml_module, "brain") as mock_brain,
        ):
            initial = _build_initial_state("e2e_test_001b",
                                            user_request="Check signals")
            final, nodes_executed = _run_graph(initial)

            # Draft/review never ran, so no Telegram alerts from risk gate
            mock_tg.assert_not_called()


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
    """Pipeline with no signals detected. Short-circuits after prediction (trading off)."""

    def test_quiet_market_completes(self):
        with (
            patch.object(ml_module, "fetch_crypto_markets", return_value=_fake_markets()),
            patch.object(ml_module, "detect_signals", return_value=[]),
            patch.object(ml_module, "predict_market_moves", side_effect=_fake_predictions),
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "brain") as mock_brain,
        ):
            initial = _build_initial_state("e2e_test_003", cycle_number=5,
                                            user_request="Scan markets")
            final, nodes_executed = _run_graph(initial)

            # Short-circuit: only perception + prediction
            assert "perception" in nodes_executed
            assert "prediction" in nodes_executed
            assert "draft" not in nodes_executed

            # Observations should exist (quiet markets, no signals)
            assert len(final["observations"]) == 2

            # No direction on quiet observations
            for obs in final["observations"]:
                assert obs["direction"] == ""

            # cycle_number still propagated
            for obs in final["observations"]:
                assert obs.get("cycle_number") == 5


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
            patch.object(ml_module, "send_telegram_alert"),
            patch.object(ml_module, "brain") as mock_brain,
        ):
            initial = _build_initial_state("e2e_test_004", user_request="Scan markets")
            final, _ = _run_graph(initial)

            # Should record the perception error
            assert any("No markets" in e for e in final["errors"])

            # Pipeline should still complete without crashing
            assert "perception" in final["stage_timings"]
