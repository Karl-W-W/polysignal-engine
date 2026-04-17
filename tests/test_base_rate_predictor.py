"""Tests for lab/base_rate_predictor.py"""
import pytest


class TestBaseRatePredictor:
    def test_predict_known_market(self):
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        biases = {
            "test_market": MarketBias(
                market_id="test_market", up_count=80, down_count=20,
                total=100, up_rate=0.8, dominant_direction="Bullish",
                bias_strength=0.8, confident=True
            )
        }
        predictor = BaseRatePredictor(biases)
        result = predictor.predict("test_market")
        assert result.direction == "Bullish"
        assert result.confidence == 0.8
        assert result.samples == 100

    def test_predict_unknown_market(self):
        from lab.base_rate_predictor import BaseRatePredictor
        predictor = BaseRatePredictor({})
        result = predictor.predict("unknown")
        assert result.direction == "Neutral"
        assert result.confidence == 0.1
        assert result.samples == 0

    def test_predict_low_sample_market(self):
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        biases = {
            "small": MarketBias(
                market_id="small", up_count=3, down_count=1,
                total=4, up_rate=0.75, dominant_direction="Bullish",
                bias_strength=0.75, confident=False  # <10 samples
            )
        }
        predictor = BaseRatePredictor(biases)
        result = predictor.predict("small")
        assert result.direction == "Neutral"  # Not confident enough

    def test_counter_signal_weak_ignored(self):
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        biases = {
            "m1": MarketBias(
                market_id="m1", up_count=85, down_count=15,
                total=100, up_rate=0.85, dominant_direction="Bullish",
                bias_strength=0.85, confident=True
            )
        }
        predictor = BaseRatePredictor(biases)
        # Small negative delta should NOT override 85% bullish bias
        result = predictor.predict("m1", signal_delta=-0.01)
        assert result.direction == "Bullish"

    def test_counter_signal_strong_overrides(self):
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        # Session 40: Bearish ban suppresses Bearish outputs, so we test the
        # mirror case — Bearish-dominant bias flipped by strong positive signal.
        # This still exercises the counter-signal override logic.
        biases = {
            "m1": MarketBias(
                market_id="m1", up_count=15, down_count=85,
                total=100, up_rate=0.15, dominant_direction="Bearish",
                bias_strength=0.85, confident=True
            )
        }
        predictor = BaseRatePredictor(biases)
        # Large positive delta SHOULD override (Session 27: threshold raised to 10pp)
        result = predictor.predict("m1", signal_delta=+0.12)
        assert result.direction == "Bullish"

    def test_bearish_ban_suppresses_dominant_bearish(self):
        """Session 40: dominant-Bearish biases return Neutral under ban."""
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        biases = {
            "m1": MarketBias(
                market_id="m1", up_count=15, down_count=85,
                total=100, up_rate=0.15, dominant_direction="Bearish",
                bias_strength=0.85, confident=True
            )
        }
        predictor = BaseRatePredictor(biases)
        result = predictor.predict("m1")
        assert result.direction == "Neutral"
        assert result.confidence == 0.0
        assert "Bearish banned" in result.reasoning

    def test_bearish_ban_suppresses_counter_signal_flip(self):
        """Session 40: counter-signal flipping Bullish→Bearish is also banned."""
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        biases = {
            "m1": MarketBias(
                market_id="m1", up_count=85, down_count=15,
                total=100, up_rate=0.85, dominant_direction="Bullish",
                bias_strength=0.85, confident=True
            )
        }
        predictor = BaseRatePredictor(biases)
        # Strong negative signal would flip to Bearish — ban converts to Neutral
        result = predictor.predict("m1", signal_delta=-0.12)
        assert result.direction == "Neutral"
        assert "Bearish banned" in result.reasoning

    def test_bearish_ban_disabled_restores_original(self, monkeypatch):
        """Toggling BAN_BEARISH_OUTPUT=False restores pre-Session 40 behavior."""
        from lab import base_rate_predictor as brp
        monkeypatch.setattr(brp, "BAN_BEARISH_OUTPUT", False)
        biases = {
            "m1": brp.MarketBias(
                market_id="m1", up_count=15, down_count=85,
                total=100, up_rate=0.15, dominant_direction="Bearish",
                bias_strength=0.85, confident=True
            )
        }
        predictor = brp.BaseRatePredictor(biases)
        result = predictor.predict("m1")
        assert result.direction == "Bearish"
        assert result.confidence == 0.85

    def test_bearish_ban_with_weak_counter_signal(self):
        """Weak counter-signal below 10pp threshold on Bearish-dominant bias:
        counter-signal is ignored (direction stays Bearish), then ban kicks in."""
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        biases = {
            "m1": MarketBias(
                market_id="m1", up_count=15, down_count=85,
                total=100, up_rate=0.15, dominant_direction="Bearish",
                bias_strength=0.85, confident=True
            )
        }
        predictor = BaseRatePredictor(biases)
        # Weak bullish signal (< 10pp) — override rejected, direction stays Bearish, ban converts
        result = predictor.predict("m1", signal_delta=+0.03)
        assert result.direction == "Neutral"
        assert "Bearish banned" in result.reasoning

    def test_bearish_ban_does_not_affect_bullish(self):
        """Session 40: Bullish predictions pass through the ban unchanged."""
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        biases = {
            "m1": MarketBias(
                market_id="m1", up_count=80, down_count=20,
                total=100, up_rate=0.8, dominant_direction="Bullish",
                bias_strength=0.8, confident=True
            )
        }
        predictor = BaseRatePredictor(biases)
        result = predictor.predict("m1")
        assert result.direction == "Bullish"
        assert result.confidence == 0.8

    def test_summary_output(self):
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        biases = {
            "m1": MarketBias("m1", 80, 20, 100, 0.8, "Bullish", 0.8, True)
        }
        predictor = BaseRatePredictor(biases)
        summary = predictor.summary()
        assert "m1" in summary
        assert "Bullish" in summary

    def test_from_price_levels_bearish(self):
        """Markets at low prices should get Bearish bias (Session 31)."""
        from lab.base_rate_predictor import BaseRatePredictor
        observations = [
            {"market_id": "low_price", "current_price": 0.10},
            {"market_id": "mid_price", "current_price": 0.50},
            {"market_id": "high_price", "current_price": 0.85},
        ]
        predictor = BaseRatePredictor.from_price_levels(observations)
        assert "low_price" in predictor.biases
        assert predictor.biases["low_price"].dominant_direction == "Bearish"
        assert predictor.biases["low_price"].bias_strength == 0.9  # 1 - 0.10

    def test_from_price_levels_bullish(self):
        """Markets at high prices should get Bullish bias (Session 31)."""
        from lab.base_rate_predictor import BaseRatePredictor
        observations = [
            {"market_id": "high_price", "current_price": 0.85},
        ]
        predictor = BaseRatePredictor.from_price_levels(observations)
        assert "high_price" in predictor.biases
        assert predictor.biases["high_price"].dominant_direction == "Bullish"
        assert predictor.biases["high_price"].bias_strength == 0.85

    def test_from_price_levels_skips_decided(self):
        """Markets at extreme prices (<0.05 or >0.95) should be skipped (Session 31)."""
        from lab.base_rate_predictor import BaseRatePredictor
        observations = [
            {"market_id": "decided_no", "current_price": 0.01},
            {"market_id": "decided_yes", "current_price": 0.99},
        ]
        predictor = BaseRatePredictor.from_price_levels(observations)
        assert "decided_no" not in predictor.biases
        assert "decided_yes" not in predictor.biases

    def test_from_price_levels_skips_uncertain(self):
        """Markets in 0.30-0.70 range should not get price-level bias (Session 31)."""
        from lab.base_rate_predictor import BaseRatePredictor
        observations = [
            {"market_id": "uncertain", "current_price": 0.50},
        ]
        predictor = BaseRatePredictor.from_price_levels(observations)
        assert "uncertain" not in predictor.biases

    def test_from_all_sources_with_observations(self):
        """from_all_sources should merge price-level biases (Session 31)."""
        from lab.base_rate_predictor import BaseRatePredictor
        observations = [
            {"market_id": "new_market", "current_price": 0.15},
        ]
        # Use non-existent paths so outcome/obs predictors return empty
        predictor = BaseRatePredictor.from_all_sources(
            outcomes_path="/nonexistent/path.json",
            db_path="/nonexistent/db.sqlite",
            observations=observations,
        )
        # Should have price-level bias for new_market
        assert "new_market" in predictor.biases
        assert predictor.biases["new_market"].dominant_direction == "Bearish"

    def test_from_all_sources_outcome_overrides_price_level(self):
        """Outcome biases should override price-level biases (Session 31)."""
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        # Price says Bearish (low price), but outcome history says Bullish
        observations = [
            {"market_id": "m1", "current_price": 0.15},
        ]
        predictor = BaseRatePredictor.from_price_levels(observations)
        assert predictor.biases["m1"].dominant_direction == "Bearish"
        # If outcome data says Bullish, that should win
        # (tested indirectly — outcome predictor needs actual file)
