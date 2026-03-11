"""
Tests for lab/polymarket_trader.py — Polymarket trading module.
All external API calls mocked. No real trades or keys.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

import core.risk as risk_module
from core.risk import (
    DailyPnLTracker,
    MAX_POSITION_USDC,
    MIN_CONFIDENCE,
)
from core.signal_model import Signal, SignalSource
from lab.polymarket_trader import (
    PolymarketTrader,
    TradeResult,
    TradingLog,
    ClobClientWrapper,
    _get_field,
)


# ============================================================================
# FIXTURES
# ============================================================================

class MockRiskTracker(DailyPnLTracker):
    """In-memory tracker for tests."""
    def __init__(self, total_trades=10, daily_loss=0.0):
        self._state = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "total_trades": total_trades,
            "daily_loss_usdc": daily_loss,
            "trades_today": 0,
            "trade_log": [],
        }
    def save(self):
        pass


@pytest.fixture
def tmp_log(tmp_path):
    return str(tmp_path / "test_trading_log.json")


@pytest.fixture
def tracker():
    return MockRiskTracker(total_trades=10)


@pytest.fixture
def trader(tmp_log, tracker):
    return PolymarketTrader(
        api_key="test-key-not-real",
        wallet_address="0xtest_not_real",
        log_path=tmp_log,
        risk_tracker=tracker,
    )


@pytest.fixture
def bullish_signal():
    return {
        "market_id": "0xabc123",
        "title": "BTC above $100k by Q1 2026",
        "outcome": "Yes",
        "hypothesis": "Bullish",
        "confidence": 0.85,
        "current_price": 0.71,
        "signal_id": "test-001",
    }


@pytest.fixture
def bearish_signal():
    return {
        "market_id": "0xdef456",
        "title": "ETH above $5k",
        "outcome": "No",
        "hypothesis": "Bearish",
        "confidence": 0.80,
        "current_price": 0.35,
        "signal_id": "test-002",
    }


@pytest.fixture
def neutral_signal():
    return {
        "market_id": "0xghi789",
        "title": "Quiet market",
        "outcome": "Yes",
        "hypothesis": "Neutral",
        "confidence": 0.50,
        "current_price": 0.50,
        "signal_id": "test-003",
    }


@pytest.fixture(autouse=True)
def reset_kill_switch():
    original = risk_module.TRADING_ENABLED
    yield
    risk_module.TRADING_ENABLED = original


# ============================================================================
# PAPER TRADE TESTS
# ============================================================================

class TestPaperTrade:
    def test_bullish_succeeds(self, trader, bullish_signal):
        risk_module.TRADING_ENABLED = True
        result = trader.paper_trade(bullish_signal)
        assert result.success is True
        assert result.mode == "paper"
        assert result.side == "BUY"
        assert result.outcome == "Yes"
        assert result.risk_verdict == "APPROVED"

    def test_bearish_succeeds(self, trader, bearish_signal):
        risk_module.TRADING_ENABLED = True
        result = trader.paper_trade(bearish_signal)
        assert result.success is True
        assert result.side == "SELL"

    def test_neutral_not_actionable(self, trader, neutral_signal):
        risk_module.TRADING_ENABLED = True
        result = trader.paper_trade(neutral_signal)
        assert result.success is False
        assert "not actionable" in (result.error or "").lower()

    def test_with_signal_object(self, trader):
        risk_module.TRADING_ENABLED = True
        sig = Signal(
            market_id="0xabc", title="BTC 100k", outcome="Yes",
            polymarket_url="https://polymarket.com/event/test",
            current_price=0.71, volume_24h=1_000_000,
            change_since_last=0.08, hypothesis="Bullish", confidence=0.85,
            source=SignalSource(method="momentum", raw_value=0.08, threshold=0.05),
            reasoning="Strong move.",
        )
        result = trader.paper_trade(sig)
        assert result.success is True

    def test_default_size(self, trader, bullish_signal):
        risk_module.TRADING_ENABLED = True
        result = trader.paper_trade(bullish_signal)
        assert result.size_usdc == 5.0

    def test_size_clamped_to_max(self, trader, bullish_signal):
        risk_module.TRADING_ENABLED = True
        result = trader.paper_trade(bullish_signal, proposed_size_usdc=50.0)
        assert result.size_usdc == MAX_POSITION_USDC


# ============================================================================
# P&L TRACKING
# ============================================================================

class TestPnL:
    def test_buy_profit(self, trader, bullish_signal):
        risk_module.TRADING_ENABLED = True
        result = trader.paper_trade(bullish_signal)
        pnl = trader.calculate_paper_pnl(result.trade_id, 0.85)
        assert pnl is not None
        assert pnl > 0

    def test_buy_loss(self, trader, bullish_signal):
        risk_module.TRADING_ENABLED = True
        result = trader.paper_trade(bullish_signal)
        pnl = trader.calculate_paper_pnl(result.trade_id, 0.50)
        assert pnl < 0

    def test_sell_profit(self, trader, bearish_signal):
        risk_module.TRADING_ENABLED = True
        result = trader.paper_trade(bearish_signal)
        pnl = trader.calculate_paper_pnl(result.trade_id, 0.20)
        assert pnl > 0

    def test_not_found(self, trader):
        assert trader.calculate_paper_pnl("nonexistent", 0.5) is None

    def test_persisted(self, trader, bullish_signal, tmp_log):
        risk_module.TRADING_ENABLED = True
        result = trader.paper_trade(bullish_signal)
        trader.calculate_paper_pnl(result.trade_id, 0.80)
        with open(tmp_log) as f:
            data = json.load(f)
        assert data["trades"][0]["pnl"] is not None

    def test_total(self, trader, bullish_signal, bearish_signal):
        risk_module.TRADING_ENABLED = True
        r1 = trader.paper_trade(bullish_signal)
        r2 = trader.paper_trade(bearish_signal)
        trader.calculate_paper_pnl(r1.trade_id, 0.80)
        trader.calculate_paper_pnl(r2.trade_id, 0.20)
        assert trader.log.total_pnl > 0


# ============================================================================
# RISK GATE INTEGRATION
# ============================================================================

class TestRiskGate:
    def test_kill_switch_blocks(self, trader, bullish_signal):
        risk_module.TRADING_ENABLED = False
        result = trader.paper_trade(bullish_signal)
        assert result.success is False
        assert "kill switch" in (result.risk_verdict or "").lower()

    def test_low_confidence_blocked(self, trader):
        risk_module.TRADING_ENABLED = True
        sig = {"market_id": "0x1", "title": "Low", "outcome": "Yes",
               "hypothesis": "Bullish", "confidence": 0.60, "current_price": 0.5}
        result = trader.paper_trade(sig)
        assert result.success is False

    def test_exact_threshold_passes(self, trader):
        risk_module.TRADING_ENABLED = True
        sig = {"market_id": "0x1", "title": "Exact", "outcome": "Yes",
               "hypothesis": "Bullish", "confidence": MIN_CONFIDENCE,
               "current_price": 0.5}
        result = trader.paper_trade(sig)
        assert result.success is True

    def test_daily_cap_blocks(self, tmp_log):
        risk_module.TRADING_ENABLED = True
        busted = MockRiskTracker(total_trades=10, daily_loss=55.0)
        trader = PolymarketTrader(
            api_key="test", wallet_address="0xtest",
            log_path=tmp_log, risk_tracker=busted,
        )
        sig = {"market_id": "0x1", "title": "Cap", "outcome": "Yes",
               "hypothesis": "Bullish", "confidence": 0.90, "current_price": 0.6}
        result = trader.paper_trade(sig)
        assert result.success is False


# ============================================================================
# TRADING_ENABLED FLAG
# ============================================================================

class TestTradingEnabled:
    def test_default_disabled(self, trader, monkeypatch):
        monkeypatch.delenv("TRADING_ENABLED", raising=False)
        assert trader.trading_enabled is False

    def test_enabled_true(self, trader, monkeypatch):
        monkeypatch.setenv("TRADING_ENABLED", "true")
        assert trader.trading_enabled is True

    def test_routes_to_paper_when_disabled(self, trader, bullish_signal, monkeypatch):
        monkeypatch.setenv("TRADING_ENABLED", "false")
        risk_module.TRADING_ENABLED = True
        result = trader.execute_trade(bullish_signal)
        assert result.mode == "paper"

    def test_live_when_enabled(self, tmp_log, tracker, bullish_signal, monkeypatch):
        monkeypatch.setenv("TRADING_ENABLED", "true")
        risk_module.TRADING_ENABLED = True
        mock_clob = MagicMock(spec=ClobClientWrapper)
        mock_clob.place_market_order.return_value = {"orderID": "mock-123"}
        trader = PolymarketTrader(
            api_key="test", wallet_address="0xtest",
            log_path=tmp_log, risk_tracker=tracker, clob_client=mock_clob,
        )
        result = trader.execute_trade(bullish_signal)
        assert result.mode == "live"
        assert result.success is True
        assert result.order_id == "mock-123"


# ============================================================================
# LIVE TRADE (MOCKED)
# ============================================================================

class TestLiveTrade:
    def test_clob_failure_handled(self, tmp_log, tracker, bullish_signal, monkeypatch):
        monkeypatch.setenv("TRADING_ENABLED", "true")
        risk_module.TRADING_ENABLED = True
        mock_clob = MagicMock(spec=ClobClientWrapper)
        mock_clob.place_market_order.side_effect = Exception("Connection refused")
        trader = PolymarketTrader(
            api_key="test", wallet_address="0xtest",
            log_path=tmp_log, risk_tracker=tracker, clob_client=mock_clob,
        )
        result = trader.execute_trade(bullish_signal)
        assert result.success is False
        assert "CLOB order failed" in result.error

    def test_risk_blocked_doesnt_touch_clob(self, tmp_log, tracker, monkeypatch):
        monkeypatch.setenv("TRADING_ENABLED", "true")
        risk_module.TRADING_ENABLED = True
        mock_clob = MagicMock(spec=ClobClientWrapper)
        trader = PolymarketTrader(
            api_key="test", wallet_address="0xtest",
            log_path=tmp_log, risk_tracker=tracker, clob_client=mock_clob,
        )
        sig = {"market_id": "0x1", "title": "Low", "outcome": "Yes",
               "hypothesis": "Bullish", "confidence": 0.50, "current_price": 0.5}
        result = trader.execute_trade(sig)
        assert result.success is False
        mock_clob.place_market_order.assert_not_called()


# ============================================================================
# TRADING LOG
# ============================================================================

class TestTradingLog:
    def test_record_and_persist(self, tmp_log):
        log = TradingLog(tmp_log)
        r = TradeResult(
            success=True, mode="paper", trade_id="t1",
            market_id="0x1", title="Test", side="BUY",
            outcome="Yes", size_usdc=5.0, price_at_entry=0.7,
            confidence=0.85, timestamp="2026-03-11T00:00:00+00:00",
            risk_verdict="APPROVED",
        )
        log.record(r)
        log2 = TradingLog(tmp_log)
        assert len(log2.trades) == 1

    def test_paper_live_separation(self, tmp_log):
        log = TradingLog(tmp_log)
        for mode in ["paper", "live", "paper"]:
            log.record(TradeResult(
                success=True, mode=mode, trade_id=f"t-{mode}",
                market_id="0x1", title="Test", side="BUY",
                outcome="Yes", size_usdc=5.0, price_at_entry=0.5,
                confidence=0.85, timestamp="2026-03-11T00:00:00+00:00",
                risk_verdict="APPROVED",
            ))
        assert len(log.paper_trades) == 2
        assert len(log.live_trades) == 1


# ============================================================================
# SUMMARY & HELPERS
# ============================================================================

class TestSummary:
    def test_structure(self, trader, bullish_signal):
        risk_module.TRADING_ENABLED = True
        trader.paper_trade(bullish_signal)
        s = trader.get_summary()
        assert "total_trades" in s
        assert "total_pnl" in s
        assert "trading_enabled" in s


class TestGetField:
    def test_dict(self):
        assert _get_field({"a": 1}, "a") == 1
        assert _get_field({"a": 1}, "b", "x") == "x"

    def test_signal_obj(self):
        sig = Signal(
            market_id="0x1", title="T", outcome="Yes",
            polymarket_url="https://polymarket.com/event/test",
            current_price=0.5, volume_24h=1000,
            source=SignalSource(method="test", raw_value=0.1),
            reasoning="test",
        )
        assert _get_field(sig, "market_id") == "0x1"


class TestInit:
    def test_from_env(self, tmp_log, monkeypatch):
        monkeypatch.setenv("POLYMARKET_BUILDER_API_KEY", "env-key")
        monkeypatch.setenv("POLYMARKET_ADDRESS", "0xenv")
        t = PolymarketTrader(log_path=tmp_log)
        assert t.api_key == "env-key"
        assert t.wallet_address == "0xenv"

    def test_constructor_overrides_env(self, tmp_log, monkeypatch):
        monkeypatch.setenv("POLYMARKET_BUILDER_API_KEY", "env-key")
        t = PolymarketTrader(api_key="explicit", log_path=tmp_log)
        assert t.api_key == "explicit"
