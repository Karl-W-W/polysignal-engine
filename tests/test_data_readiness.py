"""
tests/test_data_readiness.py
============================
Tests for lab/data_readiness.py — Phase 2 data monitor.
"""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from lab.data_readiness import check_readiness, format_report, _avg_horizon_hours


@pytest.fixture
def tmp_outcomes(tmp_path):
    """Create a temporary prediction outcomes file."""
    path = tmp_path / "prediction_outcomes.json"
    return path


def _write_outcomes(path, predictions, stats=None):
    """Write predictions to the outcomes file."""
    if stats is None:
        stats = {
            "total_predictions": len(predictions),
            "total_evaluated": sum(1 for p in predictions if p.get("evaluated")),
            "correct": 0, "incorrect": 0, "neutral": 0, "accuracy": 0.0,
        }
    with open(path, "w") as f:
        json.dump({"predictions": predictions, "stats": stats}, f)


def _make_pred(market_id="556108", hypothesis="Bullish", confidence=0.6,
               price=0.65, horizon="4h", evaluated=False, outcome=None,
               hours_ago=0, cycle=1):
    """Create a prediction record."""
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return {
        "market_id": market_id,
        "hypothesis": hypothesis,
        "confidence": confidence,
        "price_at_prediction": price,
        "timestamp": ts,
        "time_horizon": horizon,
        "cycle_number": cycle,
        "evaluated": evaluated,
        "outcome": outcome,
        "price_at_evaluation": None,
        "evaluated_at": None,
        "actual_delta": None,
    }


class TestCheckReadiness:

    def test_no_file(self, tmp_path):
        result = check_readiness(tmp_path / "nonexistent.json")
        assert result["ready"] is False
        assert result["total_predictions"] == 0
        assert result["error"] == "No predictions file found"

    def test_empty_predictions(self, tmp_outcomes):
        _write_outcomes(tmp_outcomes, [])
        result = check_readiness(tmp_outcomes)
        assert result["ready"] is False
        assert result["evaluated"] == 0
        assert result["pending"] == 0

    def test_all_pending(self, tmp_outcomes):
        preds = [_make_pred(hours_ago=i) for i in range(20)]
        _write_outcomes(tmp_outcomes, preds)
        result = check_readiness(tmp_outcomes)
        assert result["ready"] is False
        assert result["real_predictions"] == 20
        assert result["evaluated"] == 0
        assert result["pending"] == 20
        assert result["needed"] == 50

    def test_ready_with_50_evaluated(self, tmp_outcomes):
        preds = [_make_pred(evaluated=True, outcome="CORRECT", hours_ago=i)
                 for i in range(50)]
        _write_outcomes(tmp_outcomes, preds)
        result = check_readiness(tmp_outcomes)
        assert result["ready"] is True
        assert result["evaluated"] == 50
        assert result["needed"] == 0

    def test_accuracy_calculation(self, tmp_outcomes):
        preds = (
            [_make_pred(evaluated=True, outcome="CORRECT") for _ in range(7)] +
            [_make_pred(evaluated=True, outcome="INCORRECT") for _ in range(3)] +
            [_make_pred(evaluated=True, outcome="NEUTRAL") for _ in range(2)]
        )
        _write_outcomes(tmp_outcomes, preds)
        result = check_readiness(tmp_outcomes)
        assert result["correct"] == 7
        assert result["incorrect"] == 3
        assert result["neutral"] == 2
        assert result["accuracy"] == 0.7  # 7/(7+3)

    def test_fake_predictions_excluded(self, tmp_outcomes):
        preds = [
            _make_pred(market_id="0xfake_btc"),
            _make_pred(market_id="0xfake_eth"),
            _make_pred(market_id="556108"),
        ]
        _write_outcomes(tmp_outcomes, preds)
        result = check_readiness(tmp_outcomes)
        assert result["total_predictions"] == 3
        assert result["real_predictions"] == 1

    def test_horizon_distribution(self, tmp_outcomes):
        preds = [
            _make_pred(horizon="1h"),
            _make_pred(horizon="1h"),
            _make_pred(horizon="4h"),
            _make_pred(horizon="24h"),
        ]
        _write_outcomes(tmp_outcomes, preds)
        result = check_readiness(tmp_outcomes)
        assert result["horizon_distribution"] == {"1h": 2, "4h": 1, "24h": 1}

    def test_estimated_time_calculation(self, tmp_outcomes):
        preds = [_make_pred(hours_ago=i * 0.5) for i in range(20)]
        _write_outcomes(tmp_outcomes, preds)
        result = check_readiness(tmp_outcomes)
        assert result["estimated_hours_to_ready"] is not None
        assert result["estimated_hours_to_ready"] > 0

    def test_mixed_evaluated_and_pending(self, tmp_outcomes):
        preds = (
            [_make_pred(evaluated=True, outcome="CORRECT") for _ in range(30)] +
            [_make_pred(evaluated=False) for _ in range(20)]
        )
        _write_outcomes(tmp_outcomes, preds)
        result = check_readiness(tmp_outcomes)
        assert result["ready"] is False
        assert result["evaluated"] == 30
        assert result["pending"] == 20
        assert result["needed"] == 20


class TestFormatReport:

    def test_not_ready_report(self):
        result = {
            "ready": False, "total_predictions": 100, "real_predictions": 90,
            "evaluated": 10, "pending": 80, "correct": 6, "incorrect": 3,
            "neutral": 1, "accuracy": 0.667, "needed": 40,
            "estimated_hours_to_ready": 12.5,
            "horizon_distribution": {"24h": 90},
        }
        report = format_report(result)
        assert "NOT READY" in report
        assert "40 more" in report
        assert "66.7%" in report

    def test_ready_report(self):
        result = {
            "ready": True, "total_predictions": 200, "real_predictions": 180,
            "evaluated": 60, "pending": 120, "correct": 35, "incorrect": 20,
            "neutral": 5, "accuracy": 0.636, "needed": 0,
            "estimated_hours_to_ready": None,
            "horizon_distribution": {"4h": 100, "24h": 80},
        }
        report = format_report(result)
        assert "READY" in report
        assert "train_model" in report


class TestAvgHorizonHours:

    def test_empty_list(self):
        assert _avg_horizon_hours([]) == 4.0

    def test_mixed_horizons(self):
        preds = [
            {"time_horizon": "1h"},
            {"time_horizon": "24h"},
        ]
        assert _avg_horizon_hours(preds) == 12.5  # (1 + 24) / 2

    def test_all_same_horizon(self):
        preds = [{"time_horizon": "4h"}] * 5
        assert _avg_horizon_hours(preds) == 4.0
