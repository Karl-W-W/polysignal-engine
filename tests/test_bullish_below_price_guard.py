"""Tests for the 2026-09-04 lever: no Bullish calls on markets priced < 0.50.

Guard lives in lab/base_rate_predictor.py predict(); counter is surfaced by
lab/truth_board.py. See lab/BACKTEST-2026-09-04-no-bullish-below-0.5.md.
"""
import json

import pytest

import lab.base_rate_predictor as brp
from lab.base_rate_predictor import BaseRatePredictor, MarketBias


def _bullish_bias(mid="m1"):
    return {mid: MarketBias(market_id=mid, up_count=80, down_count=20, total=100,
                            up_rate=0.8, dominant_direction="Bullish",
                            bias_strength=0.8, confident=True)}


def test_flag_defaults_on():
    assert brp.SUPPRESS_BULLISH_BELOW_PRICE is True
    assert brp.BULLISH_MIN_PRICE == 0.50


def test_bullish_below_threshold_is_suppressed(tmp_path):
    p = BaseRatePredictor(_bullish_bias())
    r = p.predict("m1", current_price=0.32)
    assert r.direction == "Neutral"
    assert r.confidence == 0.0
    assert "Bullish suppressed" in r.reasoning
    assert p.suppressed_bullish_below_price == 1
    # Persisted counter written for the truth board.
    data = json.loads(brp.SUPPRESSION_COUNTER_FILE.read_text())
    assert data["bullish_below_price"] == 1
    assert "updated_at" in data


def test_bullish_at_or_above_threshold_passes():
    p = BaseRatePredictor(_bullish_bias())
    assert p.predict("m1", current_price=0.50).direction == "Bullish"
    assert p.predict("m1", current_price=0.83).direction == "Bullish"
    assert p.suppressed_bullish_below_price == 0


def test_unknown_price_cannot_fire_guard():
    p = BaseRatePredictor(_bullish_bias())
    assert p.predict("m1").direction == "Bullish"


def test_price_captured_from_observations_via_from_all_sources(tmp_path):
    obs = [{"market_id": "m1", "current_price": 0.25}]
    # No outcomes file / db → only price-level source; m1 at 0.25 would be
    # Bearish under price-level, so inject the Bullish bias afterwards.
    p = BaseRatePredictor.from_all_sources(
        outcomes_path=tmp_path / "absent.json", db_path=str(tmp_path / "absent.db"),
        observations=obs)
    p.biases.update(_bullish_bias())
    assert p.prices["m1"] == 0.25
    assert p.predict("m1").direction == "Neutral"
    assert p.suppressed_bullish_below_price == 1


def test_flag_off_restores_old_behavior(monkeypatch):
    monkeypatch.setattr(brp, "SUPPRESS_BULLISH_BELOW_PRICE", False)
    p = BaseRatePredictor(_bullish_bias())
    assert p.predict("m1", current_price=0.2).direction == "Bullish"
    assert p.suppressed_bullish_below_price == 0


def test_threshold_override(monkeypatch):
    monkeypatch.setattr(brp, "BULLISH_MIN_PRICE", 0.70)
    p = BaseRatePredictor(_bullish_bias())
    assert p.predict("m1", current_price=0.65).direction == "Neutral"
    assert p.predict("m1", current_price=0.75).direction == "Bullish"


def test_counter_accumulates_across_instances():
    BaseRatePredictor(_bullish_bias()).predict("m1", current_price=0.1)
    BaseRatePredictor(_bullish_bias()).predict("m1", current_price=0.2)
    assert brp.read_suppression_counter()["bullish_below_price"] == 2


def test_read_counter_missing_file_is_empty(tmp_path):
    assert brp.read_suppression_counter(tmp_path / "nope.json") == {}


def test_truth_board_status_reports_counter(monkeypatch, tmp_path):
    from lab import truth_board
    monkeypatch.setenv("DB_PATH", str(tmp_path / "absent.db"))
    monkeypatch.setenv("OUTCOMES_FILE", str(tmp_path / "outcomes.json"))
    monkeypatch.setenv("TRUTH_BOARD_STATUS_FILE", str(tmp_path / "status.json"))
    monkeypatch.setenv("TRADING_LOG_FILE", str(tmp_path / "trading_log.json"))
    BaseRatePredictor(_bullish_bias()).predict("m1", current_price=0.3)
    status = truth_board.run_once()
    assert status["bullish_below_price_suppressed"] == 1
    assert json.loads((tmp_path / "status.json").read_text())["bullish_below_price_suppressed"] == 1


def test_backtest_replay_helpers():
    from lab import backtest_no_bullish_below as bt
    from datetime import datetime, timezone
    now = datetime(2026, 9, 4, 20, 30, tzinfo=timezone.utc)
    preds = [
        {"market_id": "a", "hypothesis": "Bullish", "price_at_prediction": 0.8,
         "outcome": "CORRECT", "timestamp": "2026-09-04T10:00:00+00:00"},
        {"market_id": "b", "hypothesis": "Bullish", "price_at_prediction": 0.2,
         "outcome": "INCORRECT", "timestamp": "2026-09-04T10:00:00+00:00"},
        {"market_id": "c", "hypothesis": "Bullish", "price_at_prediction": 0.3,
         "outcome": None, "timestamp": "2026-08-01T10:00:00+00:00"},  # pending, old
    ]
    trades = [
        {"market_id": "a", "side": "BUY", "price_at_entry": 0.8, "success": True,
         "pnl": 0.01, "timestamp": "2026-09-04T10:00:00+00:00"},
        {"market_id": "b", "side": "BUY", "price_at_entry": 0.2, "success": True,
         "pnl": -0.01, "timestamp": "2026-09-04T10:00:00+00:00"},
        {"market_id": "b", "side": "BUY", "price_at_entry": 0.2, "success": False,
         "pnl": None, "timestamp": "2026-09-04T10:00:00+00:00"},
    ]
    res = bt.run({"predictions": preds}, trades, 0.5, now)
    life = res["windows"]["lifetime"]
    assert life["A"]["pred"]["n"] == 2 and life["A"]["pred"]["accuracy"] == 0.5
    assert life["B"]["pred"]["n"] == 1 and life["B"]["pred"]["accuracy"] == 1.0
    assert life["dropped_predictions"] == 1  # pending record not counted
    assert life["A"]["trade"]["win_rate"] == 0.5 and life["B"]["trade"]["win_rate"] == 1.0
    assert life["dropped_trades"] == 1  # rejected trade not counted
    assert res["windows"]["7d"]["A"]["pred"]["n"] == 2
    md = bt.to_markdown(res, "o.json", "t.json")
    assert "| lifetime | B | 1 |" in md
