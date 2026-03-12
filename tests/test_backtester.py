"""Tests for lab/backtester.py — prediction market backtesting."""

import json
import pytest
from lab.backtester import (
    backtest,
    sweep_thresholds,
    kelly_criterion,
)


@pytest.fixture
def outcomes_file(tmp_path):
    """Create a test prediction outcomes file."""
    data = {
        "predictions": [
            # Clean market, correct bullish
            {"market_id": "556108", "hypothesis": "Bullish", "outcome": "CORRECT",
             "confidence": 0.85, "market_price": 0.60, "xgb_p_correct": 0.80,
             "timestamp": "2026-03-10T10:00:00Z"},
            # Clean market, correct bearish
            {"market_id": "556108", "hypothesis": "Bearish", "outcome": "CORRECT",
             "confidence": 0.80, "market_price": 0.40, "xgb_p_correct": 0.75,
             "timestamp": "2026-03-10T11:00:00Z"},
            # Clean market, incorrect bullish
            {"market_id": "999999", "hypothesis": "Bullish", "outcome": "INCORRECT",
             "confidence": 0.70, "market_price": 0.55, "xgb_p_correct": 0.60,
             "timestamp": "2026-03-10T12:00:00Z"},
            # Toxic market (should be excluded)
            {"market_id": "824952", "hypothesis": "Bullish", "outcome": "INCORRECT",
             "confidence": 0.90, "market_price": 0.70, "xgb_p_correct": 0.85,
             "timestamp": "2026-03-10T13:00:00Z"},
            # Neutral (should be excluded by default)
            {"market_id": "556108", "hypothesis": "Bullish", "outcome": "NEUTRAL",
             "confidence": 0.60, "market_price": 0.50,
             "timestamp": "2026-03-10T14:00:00Z"},
            # Another toxic market
            {"market_id": "556062", "hypothesis": "Bearish", "outcome": "INCORRECT",
             "confidence": 0.75, "market_price": 0.30, "xgb_p_correct": 0.70,
             "timestamp": "2026-03-10T15:00:00Z"},
            # No outcome yet (unevaluated)
            {"market_id": "556108", "hypothesis": "Bullish",
             "confidence": 0.85, "market_price": 0.65,
             "timestamp": "2026-03-10T16:00:00Z"},
            # Clean market, correct bearish, low confidence
            {"market_id": "1068702", "hypothesis": "Bearish", "outcome": "CORRECT",
             "confidence": 0.55, "market_price": 0.35, "xgb_p_correct": 0.45,
             "timestamp": "2026-03-10T17:00:00Z"},
        ],
        "stats": {"total": 8},
    }
    path = tmp_path / "test_outcomes.json"
    path.write_text(json.dumps(data))
    return str(path)


class TestBacktest:
    def test_excludes_toxic_markets(self, outcomes_file):
        r = backtest(outcomes_file)
        traded_markets = {t.market_id for t in r.trades}
        assert "824952" not in traded_markets
        assert "556062" not in traded_markets

    def test_excludes_neutral(self, outcomes_file):
        r = backtest(outcomes_file)
        outcomes = {t.outcome for t in r.trades}
        assert "NEUTRAL" not in outcomes

    def test_includes_neutral_when_disabled(self, outcomes_file):
        r_with = backtest(outcomes_file, exclude_neutral=False)
        r_without = backtest(outcomes_file, exclude_neutral=True)
        # With neutral included, we should have more evaluated but NEUTRAL
        # predictions don't have CORRECT/INCORRECT outcomes, so traded may
        # not increase. Verify the flag is respected by checking excluded count.
        assert r_with.excluded < r_without.excluded

    def test_correct_trade_count(self, outcomes_file):
        r = backtest(outcomes_file)
        # 3 clean evaluated (556108 correct, 556108 correct, 1541748 incorrect, 1068702 correct)
        # Excluding: 824952, 556062, NEUTRAL, unevaluated
        assert r.traded == 4

    def test_win_rate(self, outcomes_file):
        r = backtest(outcomes_file)
        # 3 correct out of 4 trades
        assert r.win_rate == 0.75

    def test_bullish_pnl(self, outcomes_file):
        r = backtest(outcomes_file)
        bullish_correct = [t for t in r.trades if t.direction == "Bullish" and t.outcome == "CORRECT"]
        assert len(bullish_correct) == 1
        # Bullish correct at 0.60: PnL = (1-0.60) = 0.40
        assert bullish_correct[0].pnl == pytest.approx(0.40, abs=0.01)

    def test_bearish_pnl(self, outcomes_file):
        r = backtest(outcomes_file)
        bearish_correct = [t for t in r.trades if t.direction == "Bearish" and t.outcome == "CORRECT"]
        assert len(bearish_correct) == 2
        # Bearish correct at 0.40: PnL = 0.40
        assert any(t.pnl == pytest.approx(0.40, abs=0.01) for t in bearish_correct)

    def test_incorrect_pnl_negative(self, outcomes_file):
        r = backtest(outcomes_file)
        incorrect = [t for t in r.trades if t.outcome == "INCORRECT"]
        assert all(t.pnl < 0 for t in incorrect)

    def test_confidence_filter(self, outcomes_file):
        r_low = backtest(outcomes_file, min_confidence=0.0)
        r_high = backtest(outcomes_file, min_confidence=0.80)
        assert r_high.traded < r_low.traded

    def test_xgb_filter(self, outcomes_file):
        r_no_gate = backtest(outcomes_file, min_xgb_score=0.0)
        r_gated = backtest(outcomes_file, min_xgb_score=0.70)
        assert r_gated.traded <= r_no_gate.traded

    def test_custom_exclude_markets(self, outcomes_file):
        r = backtest(outcomes_file, exclude_markets=set())
        traded_markets = {t.market_id for t in r.trades}
        assert "824952" in traded_markets

    def test_direction_split(self, outcomes_file):
        r = backtest(outcomes_file)
        assert "Bullish" in r.direction_split
        assert "Bearish" in r.direction_split

    def test_market_split(self, outcomes_file):
        r = backtest(outcomes_file)
        assert "556108" in r.market_split

    def test_summary_string(self, outcomes_file):
        r = backtest(outcomes_file)
        s = r.summary()
        assert "BACKTEST RESULTS" in s
        assert "Win rate" in s

    def test_sharpe_finite(self, outcomes_file):
        r = backtest(outcomes_file)
        assert r.sharpe != float("inf")
        assert r.sharpe != float("-inf")

    def test_max_drawdown_nonnegative(self, outcomes_file):
        r = backtest(outcomes_file)
        assert r.max_drawdown >= 0


class TestSweep:
    def test_returns_sorted_by_sharpe(self, outcomes_file):
        results = sweep_thresholds(
            outcomes_file,
            confidence_thresholds=[0.0, 0.5, 0.7],
            xgb_thresholds=[0.0, 0.5],
        )
        if len(results) >= 2:
            assert results[0]["sharpe"] >= results[1]["sharpe"]

    def test_filters_small_samples(self, outcomes_file):
        results = sweep_thresholds(
            outcomes_file,
            confidence_thresholds=[0.99],
            xgb_thresholds=[0.99],
        )
        # With very high thresholds, likely < 5 trades → filtered out
        for r in results:
            assert r["traded"] >= 5


class TestKelly:
    def test_positive_edge(self):
        k = kelly_criterion(win_rate=0.7, avg_win=0.5, avg_loss=0.3)
        assert k > 0
        assert k <= 0.25  # Capped at quarter-Kelly

    def test_no_edge(self):
        k = kelly_criterion(win_rate=0.5, avg_win=0.5, avg_loss=0.5)
        assert k == 0.0

    def test_negative_edge(self):
        k = kelly_criterion(win_rate=0.3, avg_win=0.5, avg_loss=0.5)
        assert k == 0.0

    def test_zero_loss(self):
        k = kelly_criterion(win_rate=0.7, avg_win=0.5, avg_loss=0.0)
        assert k == 0.0

    def test_capped_at_quarter(self):
        k = kelly_criterion(win_rate=0.95, avg_win=10.0, avg_loss=0.1)
        assert k == 0.25
