"""
Tests for core/signal_model.py — The canonical Signal schema.
"""

import pytest
from pydantic import ValidationError
from core.signal_model import Signal, SignalSource


class TestSignalSource:
    def test_valid_source(self):
        src = SignalSource(method="price_momentum", raw_value=0.08)
        assert src.method == "price_momentum"
        assert src.raw_value == 0.08
        assert src.baseline is None
        assert src.threshold is None

    def test_source_with_all_fields(self):
        src = SignalSource(
            method="volume_spike",
            raw_value=1500000.0,
            baseline=500000.0,
            threshold=1000000.0,
        )
        assert src.baseline == 500000.0
        assert src.threshold == 1000000.0

    def test_source_requires_method(self):
        with pytest.raises(ValidationError):
            SignalSource(raw_value=0.08)

    def test_source_requires_raw_value(self):
        with pytest.raises(ValidationError):
            SignalSource(method="test")


class TestSignal:
    @pytest.fixture
    def valid_signal_data(self):
        return dict(
            market_id="0xabc123",
            title="Will Bitcoin exceed $100k by end of Q1 2026?",
            outcome="Yes",
            polymarket_url="https://polymarket.com/event/btc-100k-q1-2026",
            current_price=0.71,
            volume_24h=1_250_000.0,
            source=SignalSource(method="price_momentum", raw_value=0.08),
            reasoning="Price moved +8pp against baseline.",
        )

    def test_valid_signal(self, valid_signal_data):
        sig = Signal(**valid_signal_data)
        assert sig.market_id == "0xabc123"
        assert sig.current_price == 0.71
        assert sig.hypothesis == "Neutral"  # default
        assert sig.confidence == 0.5  # default
        assert sig.time_horizon == "24h"  # default
        assert sig.signal_id  # auto-generated UUID

    def test_signal_id_is_unique(self, valid_signal_data):
        sig1 = Signal(**valid_signal_data)
        sig2 = Signal(**valid_signal_data)
        assert sig1.signal_id != sig2.signal_id

    def test_price_bounds(self, valid_signal_data):
        # Price must be between 0 and 1
        valid_signal_data["current_price"] = 1.5
        with pytest.raises(ValidationError):
            Signal(**valid_signal_data)

        valid_signal_data["current_price"] = -0.1
        with pytest.raises(ValidationError):
            Signal(**valid_signal_data)

    def test_confidence_bounds(self, valid_signal_data):
        valid_signal_data["confidence"] = 1.1
        with pytest.raises(ValidationError):
            Signal(**valid_signal_data)

        valid_signal_data["confidence"] = -0.1
        with pytest.raises(ValidationError):
            Signal(**valid_signal_data)

    def test_volume_non_negative(self, valid_signal_data):
        valid_signal_data["volume_24h"] = -100
        with pytest.raises(ValidationError):
            Signal(**valid_signal_data)

    def test_polymarket_url_validation(self, valid_signal_data):
        valid_signal_data["polymarket_url"] = "https://example.com/not-polymarket"
        with pytest.raises(ValidationError, match="polymarket.com"):
            Signal(**valid_signal_data)

    def test_hypothesis_literals(self, valid_signal_data):
        for h in ("Bullish", "Bearish", "Neutral"):
            valid_signal_data["hypothesis"] = h
            sig = Signal(**valid_signal_data)
            assert sig.hypothesis == h

        valid_signal_data["hypothesis"] = "InvalidValue"
        with pytest.raises(ValidationError):
            Signal(**valid_signal_data)

    def test_time_horizon_literals(self, valid_signal_data):
        for th in ("1h", "4h", "24h", "7d"):
            valid_signal_data["time_horizon"] = th
            sig = Signal(**valid_signal_data)
            assert sig.time_horizon == th

    def test_to_telegram_message(self, valid_signal_data):
        valid_signal_data["hypothesis"] = "Bullish"
        valid_signal_data["confidence"] = 0.82
        sig = Signal(**valid_signal_data)
        msg = sig.to_telegram_message()
        assert "SIGNAL DETECTED" in msg
        assert "Bitcoin" in msg
        assert "Bullish" in msg
        assert "82%" in msg

    def test_to_dict_roundtrip(self, valid_signal_data):
        sig = Signal(**valid_signal_data)
        d = sig.to_dict()
        assert isinstance(d, dict)
        assert d["market_id"] == "0xabc123"
        assert d["source"]["method"] == "price_momentum"
