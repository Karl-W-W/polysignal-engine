"""
Tests for lab/trade_proposal_bridge.py — Signal → TradeProposal bridge.
"""

import pytest
import uuid
from core.signal_model import Signal, SignalSource
from core.risk import TradeProposal, MAX_POSITION_USDC
from lab.trade_proposal_bridge import (
    TradeProposal_from_signal,
    from_observation_dict,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def bullish_signal():
    return Signal(
        market_id="0xabc",
        title="BTC above $100k",
        outcome="Yes",
        polymarket_url="https://polymarket.com/event/btc-100k",
        current_price=0.71,
        volume_24h=1_000_000,
        change_since_last=0.08,
        hypothesis="Bullish",
        confidence=0.85,
        source=SignalSource(method="momentum", raw_value=0.08, threshold=0.05),
        reasoning="Strong move up.",
    )


@pytest.fixture
def bearish_signal():
    return Signal(
        market_id="0xdef",
        title="ETH above $5k",
        outcome="No",
        polymarket_url="https://polymarket.com/event/eth-5k",
        current_price=0.35,
        volume_24h=500_000,
        hypothesis="Bearish",
        confidence=0.78,
        source=SignalSource(method="volume_spike", raw_value=2.5, threshold=2.0),
        reasoning="Volume dropping.",
    )


@pytest.fixture
def neutral_signal():
    return Signal(
        market_id="0xghi",
        title="Quiet market",
        outcome="Yes",
        polymarket_url="https://polymarket.com/event/quiet",
        current_price=0.50,
        volume_24h=100_000,
        hypothesis="Neutral",
        confidence=0.5,
        source=SignalSource(method="baseline", raw_value=0.01, threshold=0.05),
        reasoning="No signal.",
    )


@pytest.fixture
def bullish_observation():
    return {
        "market_id": "0xtest",
        "title": "BTC above $100k — Yes",
        "price": 0.71,
        "volume": 1_000_000,
        "change_24h": 0.05,
        "direction": "📈",
        "url": "https://polymarket.com/event/btc-100k",
        "source": "polymarket",
        "confidence": 0.82,
    }


# ============================================================================
# SIGNAL OBJECT TESTS
# ============================================================================

class TestFromSignalObject:
    def test_bullish_maps_to_buy(self, bullish_signal):
        tp = TradeProposal_from_signal(bullish_signal)
        assert tp is not None
        assert tp.side == "BUY"
        assert tp.outcome == "Yes"

    def test_bearish_maps_to_sell(self, bearish_signal):
        tp = TradeProposal_from_signal(bearish_signal)
        assert tp is not None
        assert tp.side == "SELL"
        assert tp.outcome == "No"

    def test_neutral_returns_none(self, neutral_signal):
        tp = TradeProposal_from_signal(neutral_signal)
        assert tp is None

    def test_fields_carried_through(self, bullish_signal):
        tp = TradeProposal_from_signal(bullish_signal)
        assert tp.market_id == "0xabc"
        assert tp.confidence == 0.85
        assert tp.current_price == 0.71
        assert tp.signal_id == bullish_signal.signal_id

    def test_default_size_is_5(self, bullish_signal):
        tp = TradeProposal_from_signal(bullish_signal)
        assert tp.proposed_size_usdc == 5.0

    def test_custom_size(self, bullish_signal):
        tp = TradeProposal_from_signal(bullish_signal, proposed_size_usdc=8.0)
        assert tp.proposed_size_usdc == 8.0

    def test_size_clamped_to_max(self, bullish_signal):
        tp = TradeProposal_from_signal(bullish_signal, proposed_size_usdc=100.0)
        assert tp.proposed_size_usdc == MAX_POSITION_USDC


# ============================================================================
# SIGNAL DICT TESTS
# ============================================================================

class TestFromSignalDict:
    def test_dict_from_to_dict(self, bullish_signal):
        sig_dict = bullish_signal.to_dict()
        tp = TradeProposal_from_signal(sig_dict)
        assert tp is not None
        assert tp.side == "BUY"
        assert tp.confidence == 0.85

    def test_dict_with_direction_fallback(self):
        """Neutral hypothesis but has direction emoji — should use direction."""
        hybrid = {
            "market_id": "0xhyb",
            "title": "Test",
            "current_price": 0.6,
            "direction": "📉",
            "confidence": 0.77,
            "hypothesis": "Neutral",
        }
        tp = TradeProposal_from_signal(hybrid)
        assert tp is not None
        assert tp.side == "SELL"

    def test_dict_neutral_no_direction_returns_none(self):
        d = {
            "market_id": "0x",
            "title": "Quiet",
            "current_price": 0.5,
            "hypothesis": "Neutral",
            "confidence": 0.5,
        }
        tp = TradeProposal_from_signal(d)
        assert tp is None


# ============================================================================
# OBSERVATION DICT TESTS
# ============================================================================

class TestFromObservationDict:
    def test_bullish_observation(self, bullish_observation):
        tp = from_observation_dict(bullish_observation)
        assert tp is not None
        assert tp.side == "BUY"
        assert tp.current_price == 0.71

    def test_bearish_observation(self):
        obs = {
            "market_id": "0x",
            "title": "Test",
            "price": 0.4,
            "direction": "📉",
        }
        tp = from_observation_dict(obs)
        assert tp is not None
        assert tp.side == "SELL"
        assert tp.outcome == "No"

    def test_empty_direction_returns_none(self):
        obs = {"market_id": "0x", "title": "T", "price": 0.5, "direction": ""}
        assert from_observation_dict(obs) is None

    def test_no_direction_key_returns_none(self):
        obs = {"market_id": "0x", "title": "T", "price": 0.5}
        assert from_observation_dict(obs) is None

    def test_size_clamped(self, bullish_observation):
        tp = from_observation_dict(bullish_observation, proposed_size_usdc=999.0)
        assert tp.proposed_size_usdc == MAX_POSITION_USDC
