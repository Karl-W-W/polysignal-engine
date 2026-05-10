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


class TestCategoryRouting:
    """Phase 6, S42: per-category EVAL_HORIZONS. The 4h-on-everything default
    was scoring 6-month political markets against 4h noise (Orbán 13%/sample).
    Routing horizons by category fixes that."""

    def test_classify_category_crypto(self):
        from lab.outcome_tracker import classify_category
        assert classify_category("Will Bitcoin break $200k by Dec?") == "crypto"
        assert classify_category("ETH ETF approval 2026") == "crypto"

    def test_classify_category_sports(self):
        from lab.outcome_tracker import classify_category
        assert classify_category("Super Bowl 2027 winner") == "sports"
        assert classify_category("NBA Finals MVP") == "sports"

    def test_classify_category_politics(self):
        from lab.outcome_tracker import classify_category
        assert classify_category("Hungarian PM by 2027") == "politics"
        assert classify_category("Will Vance win 2028 presidential election?") == "politics"

    def test_classify_category_default(self):
        from lab.outcome_tracker import classify_category
        assert classify_category("Will Apple ship the rumored device?") == "default"
        assert classify_category("") == "default"
        assert classify_category(None) == "default"

    def test_horizon_for_category(self):
        from lab.outcome_tracker import horizon_for_category
        assert horizon_for_category("crypto") == "4h"
        assert horizon_for_category("sports") == "24h"
        assert horizon_for_category("politics") == "7d"
        assert horizon_for_category("default") == "4h"
        assert horizon_for_category("unknown_bucket") == "4h"
        assert horizon_for_category(None) == "4h"

    def test_record_predictions_writes_category_from_observation(
        self, sample_observations, state_file
    ):
        # Tag the observation with politics
        obs = [{**sample_observations[0], "category": "politics", "title": "X"}]
        preds = [{"market_id": "0xbtc", "hypothesis": "Bullish", "confidence": 0.7}]
        record_predictions(preds, obs, cycle_number=1, state_path=state_file)
        state = OutcomeState.load(state_file)
        # Find the BTC record (4h-default would also create dual-horizon, but
        # politics now → 7d → no dual-horizon copy since the dual-horizon
        # logic only fires for time_horizon == "4h").
        recs = [p for p in state.predictions if p["market_id"] == "0xbtc"]
        assert recs, "expected a recorded prediction"
        assert recs[0]["category"] == "politics"
        assert recs[0]["time_horizon"] == "7d"

    def test_evaluate_outcomes_uses_category_horizon(self, state_file):
        """A politics record 1 day old must NOT evaluate (7d horizon).
        A crypto record 5h old MUST evaluate (4h horizon)."""
        from lab.outcome_tracker import OutcomeState

        recent_politics = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        recent_crypto = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        state = OutcomeState()
        state.predictions = [
            {
                "market_id": "P_HU", "hypothesis": "Bullish", "confidence": 0.7,
                "price_at_prediction": 0.50, "timestamp": recent_politics,
                "time_horizon": "4h",  # legacy field kept for compatibility
                "category": "politics",
                "cycle_number": 0, "evaluated": False,
            },
            {
                "market_id": "C_BTC", "hypothesis": "Bullish", "confidence": 0.7,
                "price_at_prediction": 0.50, "timestamp": recent_crypto,
                "time_horizon": "4h",
                "category": "crypto",
                "cycle_number": 0, "evaluated": False,
            },
        ]
        state.stats["total_predictions"] = 2
        state.save(state_file)

        obs = [
            {"market_id": "P_HU", "current_price": 0.40},
            {"market_id": "C_BTC", "current_price": 0.55},
        ]
        result = evaluate_outcomes(obs, state_path=state_file)
        # Crypto evaluates at 5h > 4h horizon. Politics does NOT evaluate at
        # 1d < 7d horizon.
        assert result["evaluated"] == 1
        assert result["correct"] == 1


class TestAtomicWrites:
    """Phase 2 S42: OutcomeState.save uses tmp + os.replace, so a crash
    mid-write must leave the previous good file intact."""

    def test_crash_mid_write_preserves_original(self, state_file, monkeypatch):
        # Seed a known-good file
        state = OutcomeState()
        state.predictions = [{"market_id": "M1", "evaluated": False}]
        state.stats["total_predictions"] = 1
        state.save(state_file)
        original = state_file.read_text()

        # Now mutate state and save with json.dump raising mid-write
        state.predictions.append({"market_id": "M2", "evaluated": False})

        def boom(*a, **kw):
            raise RuntimeError("simulated crash mid-write")

        monkeypatch.setattr("lab.outcome_tracker.json.dump", boom)
        with pytest.raises(RuntimeError):
            state.save(state_file)

        # The original file must still be intact and parseable.
        assert state_file.read_text() == original
        loaded = OutcomeState.load(state_file)
        assert len(loaded.predictions) == 1


class TestPathResolutionAtCallTime:
    """Phase 1 S42: confirm OUTCOMES_FILE is resolved at call time, not at
    module import. Reproduces the test-isolation failure mode that allowed
    110 0xfake_btc rows to bleed into the prod outcomes file."""

    def test_setenv_after_import_redirects_writes(self, tmp_path, monkeypatch):
        """Set OUTCOMES_FILE *after* the module is already imported, then
        call record_predictions with no explicit state_path. The new path
        should be honored."""
        target = tmp_path / "post_import.json"
        monkeypatch.setenv("OUTCOMES_FILE", str(target))
        # No explicit state_path — the function must resolve the env var.
        preds = [{"market_id": "M1", "hypothesis": "Bullish",
                  "confidence": 0.7, "time_horizon": "4h"}]
        obs = [{"market_id": "M1", "current_price": 0.5}]
        record_predictions(preds, obs, cycle_number=1)
        assert target.exists()
        # The default prod path must NOT have been written by this call.

    def test_setenv_after_import_redirects_reads(self, tmp_path, monkeypatch):
        """Same shape, evaluate_outcomes side. Confirms the default-arg
        capture-at-definition bug is dead."""
        target = tmp_path / "post_import.json"
        ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        target.write_text(json.dumps({
            "predictions": [{
                "market_id": "M1", "hypothesis": "Bullish", "confidence": 0.7,
                "price_at_prediction": 0.5, "timestamp": ts,
                "time_horizon": "4h", "cycle_number": 0, "evaluated": False,
            }],
            "stats": {},
            "per_market": {},
        }))
        monkeypatch.setenv("OUTCOMES_FILE", str(target))
        result = evaluate_outcomes([{"market_id": "M1", "current_price": 0.55}])
        assert result["evaluated"] == 1


class TestEvaluateOutcomesPartialStats:
    """Regression: persisted stats dict missing the 'neutral' key must not
    KeyError out of evaluate_outcomes. This is the bug that froze the prod
    eval pipeline at 2026-05-05 06:22 UTC (Phase 0, S42)."""

    def test_load_merges_partial_stats_into_defaults(self, state_file):
        """OutcomeState.load with a 5-key stats dict (no 'neutral') should
        return a state whose stats dict has all 6 default keys."""
        ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        partial = {
            "predictions": [{
                "market_id": "0xbtc", "hypothesis": "Bullish", "confidence": 0.7,
                "price_at_prediction": 0.50, "timestamp": ts, "time_horizon": "4h",
                "cycle_number": 0, "evaluated": False,
            }],
            "stats": {
                "total_predictions": 1, "total_evaluated": 0,
                "correct": 0, "incorrect": 0, "accuracy": 0.0,
                # 'neutral' MISSING — mirrors the corrupted prod state
            },
            "per_market": {},
        }
        state_file.write_text(json.dumps(partial))
        state = OutcomeState.load(state_file)
        assert "neutral" in state.stats
        assert state.stats["neutral"] == 0
        # Other keys should retain their on-disk values
        assert state.stats["total_predictions"] == 1

    def test_evaluate_outcomes_does_not_raise_on_partial_stats(self, state_file):
        """The exact reproduction of the Phase 0 freeze: a partial stats dict
        on disk plus a pending prediction whose 4h horizon has elapsed.
        Pre-fix: KeyError('neutral'). Post-fix: clean evaluation."""
        ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        partial = {
            "predictions": [{
                "market_id": "0xbtc", "hypothesis": "Bullish", "confidence": 0.7,
                "price_at_prediction": 0.50, "timestamp": ts, "time_horizon": "4h",
                "cycle_number": 0, "evaluated": False,
            }],
            "stats": {
                "total_predictions": 1, "total_evaluated": 0,
                "correct": 0, "incorrect": 0, "accuracy": 0.0,
                # 'neutral' MISSING
            },
            "per_market": {},
        }
        state_file.write_text(json.dumps(partial))
        obs = [{"market_id": "0xbtc", "current_price": 0.55}]
        result = evaluate_outcomes(obs, state_path=state_file)
        assert result["evaluated"] == 1
        assert result["correct"] == 1


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
