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
        assert len(state.predictions) == 2
        assert state.stats["total_predictions"] == 2

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
        assert len(state.predictions) == 4
        assert state.stats["total_predictions"] == 4


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
        obs = [
            {"market_id": "0xbtc", "current_price": 0.605},  # +0.005, below 1pp threshold
            {"market_id": "0xeth", "current_price": 0.495},  # -0.005, below 1pp threshold
        ]
        result = evaluate_outcomes(obs, state_path=state_file)
        assert result["neutral"] == 2
        assert result["correct"] == 0

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

    def test_predictions_capped_at_500(self, state_file):
        state = OutcomeState()
        state.predictions = [{"i": i} for i in range(600)]
        state.save(state_file)
        loaded = OutcomeState.load(state_file)
        assert len(loaded.predictions) == 500


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
