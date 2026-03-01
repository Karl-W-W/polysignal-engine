"""
Tests for lab/polymarket/risk.py — Risk management gate.
"""

import pytest
from datetime import datetime, timezone
from core.risk import (
    TradeProposal,
    RiskVerdict,
    DailyPnLTracker,
    check_risk,
    MAX_POSITION_USDC,
    MIN_CONFIDENCE,
    DAILY_LOSS_CAP_USDC,
    HUMAN_APPROVAL_FIRST_N,
)
import core.risk as risk_module


class MockTracker(DailyPnLTracker):
    """In-memory tracker for tests (no disk I/O)."""

    def __init__(self):
        self._state = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "total_trades": 0,
            "daily_loss_usdc": 0.0,
            "trades_today": 0,
            "trade_log": [],
        }

    def save(self):
        pass


@pytest.fixture
def tracker():
    return MockTracker()


@pytest.fixture
def good_trade():
    return TradeProposal(
        market_id="0xtest1",
        title="Bitcoin above $70k by March 2026",
        outcome="Yes",
        side="BUY",
        confidence=0.82,
        proposed_size_usdc=8.0,
        current_price=0.71,
        signal_id="test-signal-001",
    )


@pytest.fixture(autouse=True)
def reset_kill_switch():
    """Ensure kill switch is reset after each test."""
    original = risk_module.TRADING_ENABLED
    yield
    risk_module.TRADING_ENABLED = original


class TestKillSwitch:
    def test_kill_switch_blocks_all_trades(self, good_trade, tracker):
        risk_module.TRADING_ENABLED = False
        v = check_risk(good_trade, tracker)
        assert not v.approved
        assert "kill switch" in v.rejection_reason.lower()

    def test_kill_switch_off_allows_trades(self, good_trade, tracker):
        risk_module.TRADING_ENABLED = True
        v = check_risk(good_trade, tracker)
        assert v.approved


class TestConfidenceThreshold:
    def test_low_confidence_rejected(self, tracker):
        risk_module.TRADING_ENABLED = True
        trade = TradeProposal(
            market_id="0x2",
            title="Test",
            outcome="Yes",
            side="BUY",
            confidence=0.60,
            proposed_size_usdc=5.0,
            current_price=0.45,
            signal_id="s2",
        )
        v = check_risk(trade, tracker)
        assert not v.approved
        assert "confidence" in v.rejection_reason.lower()

    def test_exact_threshold_passes(self, tracker):
        risk_module.TRADING_ENABLED = True
        trade = TradeProposal(
            market_id="0x3",
            title="Test",
            outcome="Yes",
            side="BUY",
            confidence=MIN_CONFIDENCE,
            proposed_size_usdc=5.0,
            current_price=0.5,
            signal_id="s3",
        )
        v = check_risk(trade, tracker)
        assert v.approved


class TestPositionSizeCap:
    def test_oversized_trade_clamped(self, tracker):
        risk_module.TRADING_ENABLED = True
        trade = TradeProposal(
            market_id="0x4",
            title="Test",
            outcome="Yes",
            side="BUY",
            confidence=0.90,
            proposed_size_usdc=50.0,
            current_price=0.55,
            signal_id="s4",
        )
        v = check_risk(trade, tracker)
        assert v.approved
        assert v.approved_size_usdc == MAX_POSITION_USDC

    def test_normal_size_unclamped(self, good_trade, tracker):
        risk_module.TRADING_ENABLED = True
        v = check_risk(good_trade, tracker)
        assert v.approved_size_usdc == good_trade.proposed_size_usdc


class TestDailyLossCap:
    def test_daily_cap_blocks_trades(self, good_trade, tracker):
        risk_module.TRADING_ENABLED = True
        tracker.record_loss(DAILY_LOSS_CAP_USDC + 1)
        v = check_risk(good_trade, tracker)
        assert not v.approved
        assert "daily loss cap" in v.rejection_reason.lower()


class TestHumanApprovalGate:
    def test_first_trades_require_approval(self, good_trade, tracker):
        risk_module.TRADING_ENABLED = True
        tracker._state["total_trades"] = 0
        v = check_risk(good_trade, tracker)
        assert v.requires_human_approval

    def test_after_n_trades_no_approval_needed(self, good_trade, tracker):
        risk_module.TRADING_ENABLED = True
        tracker._state["total_trades"] = HUMAN_APPROVAL_FIRST_N
        v = check_risk(good_trade, tracker)
        assert not v.requires_human_approval


class TestTradeRecording:
    def test_record_increments_counts(self, good_trade, tracker):
        tracker.record_trade(good_trade, 8.0)
        assert tracker.total_trades == 1
        assert tracker.trades_today == 1
        assert len(tracker._state["trade_log"]) == 1


class TestTelegramFormatting:
    def test_verdict_message_contains_market(self, good_trade, tracker):
        risk_module.TRADING_ENABLED = True
        v = check_risk(good_trade, tracker)
        msg = v.to_telegram_message()
        assert good_trade.title in msg
        assert "APPROVED" in msg


# ============================================================================
# EDGE CASE TESTS (Loop's autonomous contribution — Session 7)
# ============================================================================


class TestExactPositionSizeBoundary:
    """Edge case: proposed_size == MAX_POSITION_USDC exactly ($10.00)."""

    def test_exact_max_approved_unclamped(self, tracker):
        risk_module.TRADING_ENABLED = True
        trade = TradeProposal(
            market_id="0xedge1", title="Edge", outcome="Yes", side="BUY",
            confidence=0.85, proposed_size_usdc=10.0, current_price=0.6,
            signal_id="edge-1",
        )
        v = check_risk(trade, tracker)
        assert v.approved
        assert v.approved_size_usdc == 10.0
        assert not any("clamped" in c for c in v.checks_passed)

    def test_one_cent_over_is_clamped(self, tracker):
        risk_module.TRADING_ENABLED = True
        trade = TradeProposal(
            market_id="0xedge1b", title="Edge", outcome="Yes", side="BUY",
            confidence=0.85, proposed_size_usdc=10.01, current_price=0.6,
            signal_id="edge-1b",
        )
        v = check_risk(trade, tracker)
        assert v.approved
        assert v.approved_size_usdc == MAX_POSITION_USDC


class TestExactConfidenceBoundary:
    """Edge case: confidence == MIN_CONFIDENCE exactly (0.75)."""

    def test_exact_threshold_approved(self, tracker):
        risk_module.TRADING_ENABLED = True
        trade = TradeProposal(
            market_id="0xedge2", title="Edge", outcome="Yes", side="BUY",
            confidence=0.75, proposed_size_usdc=5.0, current_price=0.5,
            signal_id="edge-2",
        )
        v = check_risk(trade, tracker)
        assert v.approved

    def test_one_tick_below_rejected(self, tracker):
        risk_module.TRADING_ENABLED = True
        trade = TradeProposal(
            market_id="0xedge2b", title="Edge", outcome="Yes", side="BUY",
            confidence=0.7499999, proposed_size_usdc=5.0, current_price=0.5,
            signal_id="edge-2b",
        )
        v = check_risk(trade, tracker)
        assert not v.approved
        assert "confidence" in v.rejection_reason.lower()


class TestDailyLossCapBoundary:
    """Edge case: daily loss at $49.99, new $1.01 trade."""

    def test_just_under_cap_approved(self, tracker):
        risk_module.TRADING_ENABLED = True
        tracker._state["daily_loss_usdc"] = 49.99
        trade = TradeProposal(
            market_id="0xedge3", title="Edge", outcome="Yes", side="BUY",
            confidence=0.85, proposed_size_usdc=1.01, current_price=0.6,
            signal_id="edge-3",
        )
        v = check_risk(trade, tracker)
        assert v.approved
        assert v.approved_size_usdc == 1.01

    def test_exact_cap_blocked(self, tracker):
        risk_module.TRADING_ENABLED = True
        tracker._state["daily_loss_usdc"] = 50.0
        trade = TradeProposal(
            market_id="0xedge3b", title="Edge", outcome="Yes", side="BUY",
            confidence=0.85, proposed_size_usdc=1.0, current_price=0.6,
            signal_id="edge-3b",
        )
        v = check_risk(trade, tracker)
        assert not v.approved

    def test_loss_crossing_cap_blocks_next(self, tracker):
        risk_module.TRADING_ENABLED = True
        tracker._state["daily_loss_usdc"] = 49.99
        trade = TradeProposal(
            market_id="0xedge3c", title="Edge", outcome="Yes", side="BUY",
            confidence=0.85, proposed_size_usdc=1.01, current_price=0.6,
            signal_id="edge-3c",
        )
        v = check_risk(trade, tracker)
        assert v.approved
        tracker.record_loss(1.01)
        assert tracker.is_daily_cap_hit()
        v2 = check_risk(trade, tracker)
        assert not v2.approved

