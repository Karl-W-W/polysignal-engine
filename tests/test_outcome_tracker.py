"""
tests/test_outcome_tracker.py
=============================
Tests for lab/outcome_tracker.py — prediction outcome tracking.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from lab.outcome_tracker import (
    record_predictions,
    evaluate_outcomes,
    get_accuracy_summary,
    get_gated_accuracy,
    get_per_market_accuracy,
    get_accuracy_by_horizon,
    OutcomeState,
    PredictionRecord,
    MIN_MOVE_THRESHOLD,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "outcomes.json"


@pytest.fixture
def sample_predictions():
    return [
        {"market_id": "0xbtc", "hypothesis": "Bullish", "confidence": 0.82,
         "time_horizon": "4h"},
        {"market_id": "0xeth", "hypothesis": "Bearish", "confidence": 0.75,
         "time_horizon": "1h"},
    ]


@pytest.fixture
def sample_observations():
    return [
        {"market_id": "0xbtc", "current_price": 0.65, "title": "BTC"},
        {"market_id": "0xeth", "current_price": 0.40, "title": "ETH"},
    ]


# ============================================================================
# RECORD PREDICTIONS
# ============================================================================

class TestRecordPredictions:
    def test_records_directional_predictions(self, sample_predictions,
                                              sample_observations, state_file):
        count = record_predictions(sample_predictions, sample_observations,
                                   cycle_number=1, state_path=state_file)
        assert count == 2

        state = OutcomeState.load(state_file)
        # Session 39: 4h predictions also create a 24h copy (BTC is 4h, ETH is 1h)
        assert len(state.predictions) == 3  # 2 primary + 1 dual-horizon (BTC 24h)
        assert state.stats["total_predictions"] == 3

    def test_skips_neutral_predictions(self, sample_observations, state_file):
        preds = [{"market_id": "0xbtc", "hypothesis": "Neutral", "confidence": 0.5}]
        count = record_predictions(preds, sample_observations,
                                   state_path=state_file)
        assert count == 0

    def test_skips_missing_market_price(self, state_file):
        preds = [{"market_id": "0xmissing", "hypothesis": "Bullish", "confidence": 0.8}]
        obs = [{"market_id": "0xother", "current_price": 0.5}]
        count = record_predictions(preds, obs, state_path=state_file)
        assert count == 0

    def test_records_cycle_number(self, sample_predictions,
                                   sample_observations, state_file):
        record_predictions(sample_predictions, sample_observations,
                          cycle_number=42, state_path=state_file)
        state = OutcomeState.load(state_file)
        assert state.predictions[0]["cycle_number"] == 42

    def test_records_price_at_prediction(self, sample_predictions,
                                          sample_observations, state_file):
        record_predictions(sample_predictions, sample_observations,
                          state_path=state_file)
        state = OutcomeState.load(state_file)
        btc = [p for p in state.predictions if p["market_id"] == "0xbtc"][0]
        assert btc["price_at_prediction"] == 0.65

    def test_records_xgb_p_correct(self, sample_observations, state_file):
        preds = [
            {"market_id": "0xbtc", "hypothesis": "Bullish", "confidence": 0.82,
             "time_horizon": "4h", "xgb_p_correct": 0.73},
            {"market_id": "0xeth", "hypothesis": "Bearish", "confidence": 0.75,
             "time_horizon": "1h"},  # no xgb_p_correct — pre-gate
        ]
        record_predictions(preds, sample_observations,
                          cycle_number=1, state_path=state_file)
        state = OutcomeState.load(state_file)
        btc = [p for p in state.predictions if p["market_id"] == "0xbtc"][0]
        eth = [p for p in state.predictions if p["market_id"] == "0xeth"][0]
        assert btc["xgb_p_correct"] == 0.73
        assert eth["xgb_p_correct"] is None

    def test_accumulates_across_cycles(self, sample_predictions,
                                        sample_observations, state_file):
        record_predictions(sample_predictions, sample_observations,
                          cycle_number=1, state_path=state_file)
        record_predictions(sample_predictions, sample_observations,
                          cycle_number=2, state_path=state_file)
        state = OutcomeState.load(state_file)
        # Session 39: each cycle has 2 primary + 1 dual-horizon = 3 records
        assert len(state.predictions) == 6
        assert state.stats["total_predictions"] == 6


# ============================================================================
# EVALUATE OUTCOMES
# ============================================================================

class TestEvaluateOutcomes:
    def _seed_predictions(self, state_file, hours_ago=5):
        """Seed state with predictions from N hours ago."""
        state = OutcomeState()
        ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
        state.predictions = [
            {
                "market_id": "0xbtc",
                "hypothesis": "Bullish",
                "confidence": 0.82,
                "price_at_prediction": 0.60,
                "timestamp": ts,
                "time_horizon": "4h",
                "cycle_number": 1,
                "evaluated": False,
                "outcome": None,
                "price_at_evaluation": None,
                "evaluated_at": None,
                "actual_delta": None,
            },
            {
                "market_id": "0xeth",
                "hypothesis": "Bearish",
                "confidence": 0.75,
                "price_at_prediction": 0.50,
                "timestamp": ts,
                "time_horizon": "4h",
                "cycle_number": 1,
                "evaluated": False,
                "outcome": None,
                "price_at_evaluation": None,
                "evaluated_at": None,
                "actual_delta": None,
            },
        ]
        state.stats["total_predictions"] = 2
        state.save(state_file)

    def test_correct_bullish(self, state_file):
        self._seed_predictions(state_file)
        obs = [
            {"market_id": "0xbtc", "current_price": 0.70},  # +0.10, bullish correct
            {"market_id": "0xeth", "current_price": 0.40},  # -0.10, bearish correct
        ]
        result = evaluate_outcomes(obs, state_path=state_file)
        assert result["correct"] == 2
        assert result["incorrect"] == 0

    def test_incorrect_prediction(self, state_file):
        self._seed_predictions(state_file)
        obs = [
            {"market_id": "0xbtc", "current_price": 0.50},  # -0.10, bullish WRONG
            {"market_id": "0xeth", "current_price": 0.60},  # +0.10, bearish WRONG
        ]
        result = evaluate_outcomes(obs, state_path=state_file)
        assert result["incorrect"] == 2
        assert result["correct"] == 0

    def test_neutral_if_small_move(self, state_file):
        self._seed_predictions(state_file)
        # Session 39: threshold lowered to 0.0005 (0.05pp)
        obs = [
            {"market_id": "0xbtc", "current_price": 0.60025},  # +0.00025, below 0.05pp
            {"market_id": "0xeth", "current_price": 0.49975},  # -0.00025, below 0.05pp
        ]
        result = evaluate_outcomes(obs, state_path=state_file)
        assert result["neutral"] == 2
        assert result["correct"] == 0

    def test_directional_at_new_threshold(self, state_file):
        """Session 39: 0.05pp (0.0005) moves should now be directional, not NEUTRAL."""
        self._seed_predictions(state_file)
        obs = [
            {"market_id": "0xbtc", "current_price": 0.601},   # +0.001 (0.1pp), bullish correct
            {"market_id": "0xeth", "current_price": 0.499},   # -0.001 (0.1pp), bearish correct
        ]
        result = evaluate_outcomes(obs, state_path=state_file)
        assert result["correct"] == 2
        assert result["neutral"] == 0

    def test_skips_if_horizon_not_reached(self, state_file):
        self._seed_predictions(state_file, hours_ago=1)  # Only 1h ago, need 4h
        obs = [{"market_id": "0xbtc", "current_price": 0.90}]
        result = evaluate_outcomes(obs, state_path=state_file)
        assert result["evaluated"] == 0

    def test_accuracy_calculation(self, state_file):
        self._seed_predictions(state_file)
        obs = [
            {"market_id": "0xbtc", "current_price": 0.70},  # correct
            {"market_id": "0xeth", "current_price": 0.60},  # incorrect (predicted bearish)
        ]
        result = evaluate_outcomes(obs, state_path=state_file)
        assert result["accuracy"] == 0.5  # 1 right / 2 directional

    def test_does_not_re_evaluate(self, state_file):
        self._seed_predictions(state_file)
        obs = [
            {"market_id": "0xbtc", "current_price": 0.70},
            {"market_id": "0xeth", "current_price": 0.40},
        ]
        evaluate_outcomes(obs, state_path=state_file)
        result2 = evaluate_outcomes(obs, state_path=state_file)
        assert result2["evaluated"] == 0  # Already evaluated


# ============================================================================
# STATE PERSISTENCE
# ============================================================================

class TestOutcomeState:
    def test_save_and_load(self, state_file):
        state = OutcomeState()
        state.predictions = [{"market_id": "0x1", "evaluated": False}]
        state.stats["total_predictions"] = 1
        state.save(state_file)

        loaded = OutcomeState.load(state_file)
        assert len(loaded.predictions) == 1
        assert loaded.stats["total_predictions"] == 1

    def test_load_missing_file(self, tmp_path):
        state = OutcomeState.load(tmp_path / "nonexistent.json")
        assert len(state.predictions) == 0
        assert state.stats["total_predictions"] == 0

    def test_predictions_capped_at_5000(self, state_file):
        state = OutcomeState()
        state.predictions = [{"i": i} for i in range(6000)]
        state.save(state_file)
        loaded = OutcomeState.load(state_file)
        assert len(loaded.predictions) == 5000

    def test_unevaluated_protected_from_rotation(self, state_file):
        """Unevaluated predictions survive rotation even when cap is exceeded."""
        state = OutcomeState()
        # 4000 evaluated + 2000 unevaluated = 6000 total
        evaluated = [{"i": i, "evaluated": True} for i in range(4000)]
        unevaluated = [{"i": i + 4000} for i in range(2000)]
        state.predictions = evaluated + unevaluated
        state.save(state_file)
        loaded = OutcomeState.load(state_file)
        # All 2000 unevaluated must survive; 3000 evaluated kept (5000 total)
        assert len(loaded.predictions) == 5000
        unevaluated_loaded = [p for p in loaded.predictions if not p.get("evaluated")]
        assert len(unevaluated_loaded) == 2000


# ============================================================================
# ACCURACY SUMMARY
# ============================================================================

class TestAccuracySummary:
    def test_no_evaluations_yet(self, state_file):
        summary = get_accuracy_summary(state_file)
        assert "No predictions evaluated yet" in summary

    def test_with_evaluations(self, state_file):
        state = OutcomeState()
        state.stats = {
            "total_predictions": 10,
            "total_evaluated": 8,
            "correct": 5,
            "incorrect": 2,
            "neutral": 1,
            "accuracy": 0.714,
        }
        state.save(state_file)
        summary = get_accuracy_summary(state_file)
        assert "71%" in summary
        assert "5/7" in summary


# ============================================================================
# GATED ACCURACY SPLIT
# ============================================================================

class TestGatedAccuracy:
    def test_splits_pre_and_post_gate(self, state_file):
        state = OutcomeState()
        state.predictions = [
            # Pre-gate (no xgb_p_correct)
            {"market_id": "0x1", "hypothesis": "Bullish", "evaluated": True,
             "outcome": "CORRECT"},
            {"market_id": "0x2", "hypothesis": "Bearish", "evaluated": True,
             "outcome": "INCORRECT"},
            # Post-gate (has xgb_p_correct)
            {"market_id": "0x3", "hypothesis": "Bullish", "evaluated": True,
             "outcome": "CORRECT", "xgb_p_correct": 0.72},
            {"market_id": "0x4", "hypothesis": "Bearish", "evaluated": True,
             "outcome": "CORRECT", "xgb_p_correct": 0.65},
        ]
        state.save(state_file)

        result = get_gated_accuracy(state_file)
        assert result["pre_gate"]["correct"] == 1
        assert result["pre_gate"]["incorrect"] == 1
        assert result["pre_gate"]["accuracy"] == 0.5
        assert result["post_gate"]["correct"] == 2
        assert result["post_gate"]["incorrect"] == 0
        assert result["post_gate"]["accuracy"] == 1.0

    def test_empty_state(self, state_file):
        result = get_gated_accuracy(state_file)
        assert result["pre_gate"]["total"] == 0
        assert result["post_gate"]["total"] == 0

    def test_skips_unevaluated(self, state_file):
        state = OutcomeState()
        state.predictions = [
            {"market_id": "0x1", "evaluated": False, "xgb_p_correct": 0.8},
            {"market_id": "0x2", "evaluated": True, "outcome": "CORRECT",
             "xgb_p_correct": 0.7},
        ]
        state.save(state_file)

        result = get_gated_accuracy(state_file)
        assert result["post_gate"]["total"] == 1


# ============================================================================
# PER-MARKET ACCURACY
# ============================================================================

class TestPerMarketAccuracy:
    def test_splits_by_market(self, state_file):
        state = OutcomeState()
        state.predictions = [
            {"market_id": "btc", "evaluated": True, "outcome": "CORRECT"},
            {"market_id": "btc", "evaluated": True, "outcome": "INCORRECT"},
            {"market_id": "eth", "evaluated": True, "outcome": "CORRECT"},
            {"market_id": "eth", "evaluated": True, "outcome": "CORRECT"},
        ]
        state.save(state_file)

        result = get_per_market_accuracy(state_file)
        assert result["btc"]["accuracy"] == 0.5
        assert result["eth"]["accuracy"] == 1.0

    def test_empty(self, state_file):
        result = get_per_market_accuracy(state_file)
        assert result == {}

    def test_skips_unevaluated(self, state_file):
        state = OutcomeState()
        state.predictions = [
            {"market_id": "btc", "evaluated": False, "outcome": None},
            {"market_id": "btc", "evaluated": True, "outcome": "CORRECT"},
        ]
        state.save(state_file)

        result = get_per_market_accuracy(state_file)
        assert result["btc"]["total"] == 1


# ============================================================================
# DUAL-HORIZON (Session 39)
# ============================================================================

class TestDualHorizon:
    def test_4h_prediction_creates_24h_copy(self, state_file):
        """Recording a 4h prediction should also create a 24h evaluation copy."""
        preds = [{"market_id": "0xbtc", "hypothesis": "Bullish",
                  "confidence": 0.82, "time_horizon": "4h"}]
        obs = [{"market_id": "0xbtc", "current_price": 0.65}]
        count = record_predictions(preds, obs, state_path=state_file)
        assert count == 1  # Only the primary counts as "recorded"

        state = OutcomeState.load(state_file)
        assert len(state.predictions) == 2  # 4h + 24h
        horizons = [p["time_horizon"] for p in state.predictions]
        assert "4h" in horizons
        assert "24h" in horizons
        # Both should have same prediction data
        assert state.predictions[0]["market_id"] == state.predictions[1]["market_id"]
        assert state.predictions[0]["hypothesis"] == state.predictions[1]["hypothesis"]

    def test_non_4h_prediction_no_duplicate(self, state_file):
        """1h predictions should NOT get a 24h copy."""
        preds = [{"market_id": "0xeth", "hypothesis": "Bearish",
                  "confidence": 0.75, "time_horizon": "1h"}]
        obs = [{"market_id": "0xeth", "current_price": 0.40}]
        record_predictions(preds, obs, state_path=state_file)

        state = OutcomeState.load(state_file)
        assert len(state.predictions) == 1
        assert state.predictions[0]["time_horizon"] == "1h"

    def test_dual_horizon_evaluated_independently(self, state_file):
        """4h copy should evaluate at 4h, 24h copy should wait until 24h."""
        state = OutcomeState()
        ts_5h_ago = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        base = {
            "market_id": "0xbtc", "hypothesis": "Bullish", "confidence": 0.8,
            "price_at_prediction": 0.60, "timestamp": ts_5h_ago,
            "cycle_number": 1, "evaluated": False, "outcome": None,
            "price_at_evaluation": None, "evaluated_at": None, "actual_delta": None,
            "xgb_p_correct": None,
        }
        state.predictions = [
            {**base, "time_horizon": "4h"},   # 5h ago, past 4h horizon
            {**base, "time_horizon": "24h"},  # 5h ago, NOT past 24h horizon
        ]
        state.stats["total_predictions"] = 2
        state.save(state_file)

        obs = [{"market_id": "0xbtc", "current_price": 0.70}]
        result = evaluate_outcomes(obs, state_path=state_file)
        assert result["evaluated"] == 1  # Only the 4h one
        assert result["correct"] == 1

        state = OutcomeState.load(state_file)
        p4h = [p for p in state.predictions if p["time_horizon"] == "4h"][0]
        p24h = [p for p in state.predictions if p["time_horizon"] == "24h"][0]
        assert p4h["evaluated"] is True
        assert p24h["evaluated"] is False


# ============================================================================
# ACCURACY BY HORIZON (Session 39)
# ============================================================================

class TestAccuracyByHorizon:
    def test_splits_by_horizon(self, state_file):
        state = OutcomeState()
        state.predictions = [
            {"time_horizon": "4h", "evaluated": True, "outcome": "CORRECT"},
            {"time_horizon": "4h", "evaluated": True, "outcome": "INCORRECT"},
            {"time_horizon": "24h", "evaluated": True, "outcome": "CORRECT"},
            {"time_horizon": "24h", "evaluated": True, "outcome": "CORRECT"},
        ]
        state.save(state_file)

        result = get_accuracy_by_horizon(state_file)
        assert result["4h"]["accuracy"] == 0.5
        assert result["24h"]["accuracy"] == 1.0
        assert result["4h"]["total"] == 2
        assert result["24h"]["total"] == 2

    def test_empty(self, state_file):
        result = get_accuracy_by_horizon(state_file)
        assert result == {}

    def test_skips_unevaluated(self, state_file):
        state = OutcomeState()
        state.predictions = [
            {"time_horizon": "4h", "evaluated": False, "outcome": None},
            {"time_horizon": "4h", "evaluated": True, "outcome": "CORRECT"},
        ]
        state.save(state_file)

        result = get_accuracy_by_horizon(state_file)
        assert result["4h"]["total"] == 1
