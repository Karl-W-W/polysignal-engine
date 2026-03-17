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
        biases = {
            "m1": MarketBias(
                market_id="m1", up_count=85, down_count=15,
                total=100, up_rate=0.85, dominant_direction="Bullish",
                bias_strength=0.85, confident=True
            )
        }
        predictor = BaseRatePredictor(biases)
        # Large negative delta SHOULD override (Session 27: threshold raised to 10pp)
        result = predictor.predict("m1", signal_delta=-0.12)
        assert result.direction == "Bearish"

    def test_summary_output(self):
        from lab.base_rate_predictor import BaseRatePredictor, MarketBias
        biases = {
            "m1": MarketBias("m1", 80, 20, 100, 0.8, "Bullish", 0.8, True)
        }
        predictor = BaseRatePredictor(biases)
        summary = predictor.summary()
        assert "m1" in summary
        assert "Bullish" in summary
