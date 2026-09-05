"""Rung 1 (lab/AUTONOMY.md, 2026-09-05): the scanner logs fill price, size,
side, fee and spread with every prediction and paper trade, so the
friction-adjusted win rate is computable from prediction_outcomes.json.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from lab.experiments.bitcoin_signal import quote_fields
from lab.outcome_tracker import (
    OutcomeState, PredictionRecord, apply_friction_pnl, build_fill_fields,
    evaluate_outcomes, get_friction_win_rate, record_predictions,
)
from lab.polymarket_trader import PolymarketTrader, TradeResult, TradingLog
from workflows.masterloop import _attach_quotes, _market_to_observation, _signal_to_observation


# ── fetcher ────────────────────────────────────────────────────────────────

def test_quote_fields_from_gamma_market():
    q = quote_fields({"bestBid": "0.79", "bestAsk": "0.81", "spread": "0.02", "lastTradePrice": 0.8})
    assert q["best_bid"] == 0.79 and q["best_ask"] == 0.81
    assert q["spread"] == 0.02 and q["last_trade_price"] == 0.8
    assert q["quote_timestamp"]


def test_quote_fields_missing_or_zero_are_none_and_spread_derived():
    q = quote_fields({"bestBid": 0, "bestAsk": "", "lastTradePrice": None})
    assert q == {**q, "best_bid": None, "best_ask": None, "spread": None, "last_trade_price": None}
    q = quote_fields({"bestBid": 0.4, "bestAsk": 0.45})
    assert q["spread"] == pytest.approx(0.05)


# ── masterloop passthrough ────────────────────────────────────────────────

def test_observation_builders_carry_quote():
    m = {"id": "1", "title": "T", "outcome": "Yes", "price": 0.8, "volume": 1.0, "url": "u",
         "best_bid": 0.79, "best_ask": 0.81, "spread": 0.02, "last_trade_price": 0.8,
         "quote_timestamp": "ts"}
    o = _market_to_observation(m)
    assert (o["best_bid"], o["best_ask"], o["spread"], o["quote_timestamp"]) == (0.79, 0.81, 0.02, "ts")
    sig = {"market_id": "1", "title": "T", "outcome": "Yes", "current_price": 0.8, "volume": 1.0,
           "delta": 0.01, "direction": "📈", "url": "u", "best_bid": 0.79, "best_ask": 0.81,
           "spread": 0.02}
    o2 = _signal_to_observation(sig)
    assert o2["best_ask"] == 0.81 and o2["last_trade_price"] is None


def test_attach_quotes_fills_predictions_without_overwriting():
    obs = [{"market_id": "1", "current_price": 0.8, "best_bid": 0.79, "best_ask": 0.81, "spread": 0.02}]
    preds = [{"market_id": "1", "hypothesis": "Bullish"},
             {"market_id": "1", "hypothesis": "Bullish", "best_ask": 0.9},
             {"market_id": "x", "hypothesis": "Bullish"}]
    assert _attach_quotes(preds, obs) == 2
    assert preds[0]["best_ask"] == 0.81 and preds[0]["current_price"] == 0.8
    assert preds[1]["best_ask"] == 0.9 and preds[1]["best_bid"] == 0.79
    assert "best_ask" not in preds[2]


# ── outcome tracker fill fields ───────────────────────────────────────────

def test_build_fill_fields_bullish_buys_at_ask(monkeypatch):
    monkeypatch.setenv("FRICTION_FEE_PP", "0.01")
    monkeypatch.setenv("MAX_POSITION_USDC", "3")
    f = build_fill_fields("Bullish", {"best_bid": 0.79, "best_ask": 0.81}, 0.80)
    assert f["side"] == "BUY" and f["outcome_token"] == "Yes"
    assert f["fill_price"] == 0.81 and f["fill_source"] == "best_ask"
    assert f["spread"] == pytest.approx(0.02) and f["mid_price"] == pytest.approx(0.80)
    assert f["fee_pp"] == 0.01 and f["size_usdc"] == 3.0


def test_build_fill_fields_bearish_buys_no_at_one_minus_bid():
    f = build_fill_fields("Bearish", {"best_bid": 0.30, "best_ask": 0.34}, 0.32)
    assert f["side"] == "SELL" and f["outcome_token"] == "No"
    assert f["fill_price"] == pytest.approx(0.70) and f["fill_source"] == "one_minus_best_bid"


def test_build_fill_fields_no_book_falls_back_and_is_labelled():
    f = build_fill_fields("Bullish", {}, 0.62)
    assert f["fill_price"] == 0.62 and f["fill_source"] == "mid_no_book"
    assert f["best_bid"] is None and f["spread"] is None and f["mid_price"] == 0.62


def test_record_predictions_persists_fill_fields(tmp_path):
    state_file = tmp_path / "o.json"
    obs = [{"market_id": "m1", "current_price": 0.80, "title": "T",
            "best_bid": 0.79, "best_ask": 0.81, "spread": 0.02, "quote_timestamp": "q"}]
    preds = [{"market_id": "m1", "hypothesis": "Bullish", "confidence": 0.8}]
    assert record_predictions(preds, obs, state_path=state_file) == 1
    rec = json.loads(state_file.read_text())["predictions"][0]
    for k in ("side", "outcome_token", "fill_price", "fill_source", "best_bid", "best_ask",
              "spread", "mid_price", "fee_pp", "size_usdc", "quote_timestamp"):
        assert k in rec, k
    assert rec["fill_price"] == 0.81 and rec["side"] == "BUY" and rec["quote_timestamp"] == "q"


def test_record_predictions_prefers_quote_on_prediction(tmp_path):
    state_file = tmp_path / "o.json"
    obs = [{"market_id": "m1", "current_price": 0.80, "best_ask": 0.81}]
    preds = [{"market_id": "m1", "hypothesis": "Bullish", "confidence": 0.8, "best_ask": 0.83, "best_bid": 0.8}]
    record_predictions(preds, obs, state_path=state_file)
    rec = json.loads(state_file.read_text())["predictions"][0]
    assert rec["fill_price"] == 0.83


def test_pre_rung_record_still_loads_and_defaults_none():
    r = PredictionRecord(market_id="m", hypothesis="Bullish", confidence=0.8,
                         price_at_prediction=0.8, timestamp="t", time_horizon="4h")
    assert r.fill_price is None and r.side is None


# ── friction pnl at resolution ────────────────────────────────────────────

def test_apply_friction_pnl_win_and_loss(monkeypatch):
    monkeypatch.delenv("FRICTION_FEE_PP", raising=False)
    p = {"fill_price": 0.80, "outcome_token": "Yes", "fee_pp": 0.0, "size_usdc": 2.0}
    apply_friction_pnl(p, "YES")
    assert p["friction_result"] == "win"
    assert p["friction_pnl_per_usd"] == pytest.approx(0.25)   # (1-0.8)/0.8
    assert p["friction_pnl_usd"] == pytest.approx(0.5)
    p = {"fill_price": 0.80, "outcome_token": "Yes", "fee_pp": 0.01, "size_usdc": 2.0}
    apply_friction_pnl(p, "NO")
    assert p["friction_result"] == "loss"
    assert p["friction_pnl_per_usd"] == pytest.approx(-0.81 / 0.8)


def test_apply_friction_pnl_no_token_and_missing_fill():
    p = {"fill_price": 0.70, "outcome_token": "No", "fee_pp": 0.0, "size_usdc": 1.0}
    apply_friction_pnl(p, "NO")
    assert p["friction_result"] == "win"
    p = {"outcome_token": "Yes"}
    apply_friction_pnl(p, "YES")
    assert p["friction_result"] is None and "friction_pnl_per_usd" not in p
    p = {"fill_price": 0.5, "outcome_token": "Yes"}
    apply_friction_pnl(p, None)
    assert p["friction_result"] is None


def test_evaluate_outcomes_writes_friction_fields(tmp_path, monkeypatch):
    state_file = tmp_path / "o.json"
    monkeypatch.setenv("OUTCOMES_FILE", str(state_file))
    obs = [{"market_id": "m1", "current_price": 0.80, "best_bid": 0.79, "best_ask": 0.81}]
    record_predictions([{"market_id": "m1", "hypothesis": "Bullish", "confidence": 0.8}], obs,
                       state_path=state_file)
    monkeypatch.setattr("lab.outcome_tracker.lookup_resolution",
                        lambda mid: ("resolved_yes", {"outcome0_price_now": 1.0, "closed": True}))
    res = evaluate_outcomes([{"market_id": "m1", "current_price": 1.0}], state_path=state_file)
    assert res["correct"] == 1
    rec = json.loads(state_file.read_text())["predictions"][0]
    assert rec["friction_result"] == "win"
    assert rec["friction_pnl_per_usd"] == pytest.approx((1 - 0.81) / 0.81)


def _scored(mid, ts, result, per_usd, fill=0.8, spread=0.02):
    return {"market_id": mid, "hypothesis": "Bullish", "confidence": 0.8, "price_at_prediction": fill,
            "timestamp": ts, "time_horizon": "4h", "evaluated": True, "outcome": "CORRECT" if result == "win" else "INCORRECT",
            "fill_price": fill, "spread": spread, "friction_result": result, "friction_pnl_per_usd": per_usd}


def test_get_friction_win_rate_windows(tmp_path):
    now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    iso = lambda d: (now - timedelta(days=d)).isoformat()
    st = OutcomeState()
    st.predictions = [
        _scored("a", iso(1), "win", 0.25),
        _scored("b", iso(10), "loss", -1.0),
        _scored("a", iso(40), "win", 0.25),
        # pre-rung evaluated record: counted as unscorable, never as a win
        {"market_id": "c", "timestamp": iso(2), "evaluated": True, "outcome": "CORRECT"},
    ]
    path = tmp_path / "o.json"; st.save(path)
    r = get_friction_win_rate(path, now=now)
    assert r["lifetime"]["evaluated"] == 3 and r["lifetime"]["wins"] == 2
    assert r["lifetime"]["win_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert r["lifetime"]["unique_markets"] == 2 and r["lifetime"]["mean_spread"] == 0.02
    assert r["30d"]["evaluated"] == 2 and r["30d"]["edge_per_usd"] == pytest.approx(-0.375)
    assert r["7d"]["evaluated"] == 1 and r["7d"]["win_rate"] == 1.0
    assert r["without_fill"] == 1


def test_get_friction_win_rate_empty(tmp_path):
    r = get_friction_win_rate(tmp_path / "absent.json")
    assert r["lifetime"]["evaluated"] == 0 and r["lifetime"]["win_rate"] is None


# ── trading log ───────────────────────────────────────────────────────────

def test_trade_result_has_quote_fields_default_none():
    r = TradeResult(success=True, mode="paper", trade_id="t", market_id="m", title="T", side="BUY",
                    outcome="Yes", size_usdc=1.0, price_at_entry=0.8, confidence=0.8,
                    timestamp="ts", risk_verdict="APPROVED")
    d = r.to_dict()
    assert d["fill_price"] is None and "spread" in d and "quote_timestamp" in d


def test_paper_trade_logs_fill_from_signal(tmp_path):
    trader = PolymarketTrader(api_key="test", wallet_address="0xtest", log_path=str(tmp_path / "tl.json"))
    sig = {"market_id": "m1", "title": "T", "outcome": "Yes", "hypothesis": "Bullish",
           "confidence": 0.85, "current_price": 0.80, "best_bid": 0.79, "best_ask": 0.81,
           "spread": 0.02, "quote_timestamp": "q"}
    r = trader.paper_trade(sig, proposed_size_usdc=1.0)
    assert r.success, r.error
    assert r.fill_price == 0.81 and r.fill_source == "best_ask" and r.spread == 0.02
    assert r.best_bid == 0.79 and r.quote_timestamp == "q" and r.fee_pp == 0.0
    saved = json.loads((tmp_path / "tl.json").read_text())["trades"][0]
    assert saved["fill_price"] == 0.81 and saved["side"] == "BUY" and saved["size_usdc"] == 1.0


def test_paper_trade_without_book_logs_none_fill(tmp_path):
    trader = PolymarketTrader(api_key="test", wallet_address="0xtest", log_path=str(tmp_path / "tl.json"))
    sig = {"market_id": "m1", "title": "T", "outcome": "Yes", "hypothesis": "Bullish",
           "confidence": 0.85, "current_price": 0.80}
    r = trader.paper_trade(sig, proposed_size_usdc=1.0)
    assert r.success and r.fill_price is None and r.fill_source is None


def test_evaluate_paper_trades_uses_fill_price(tmp_path):
    log = TradingLog(str(tmp_path / "tl.json"))
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    base = {"success": True, "mode": "paper", "market_id": "m1", "side": "BUY", "size_usdc": 1.0,
            "timestamp": old, "pnl": None}
    log._trades = [dict(base, trade_id="a", price_at_entry=0.80, fill_price=0.81),
                   dict(base, trade_id="b", price_at_entry=0.80, fill_price=None)]
    res = log.evaluate_paper_trades({"m1": 0.812}, min_age_hours=4.0)
    assert res["evaluated"] == 2
    by = {t["trade_id"]: t for t in log._trades}
    assert by["a"]["result"] == "loss"   # 0.812 - 0.81 - 0.005 < 0
    assert by["b"]["result"] == "win"    # 0.812 - 0.80 - 0.005 > 0


# ── truth board ───────────────────────────────────────────────────────────

def test_truth_board_status_has_friction_resolution(monkeypatch, tmp_path):
    from lab import truth_board
    monkeypatch.setenv("DB_PATH", str(tmp_path / "absent.db"))
    monkeypatch.setenv("OUTCOMES_FILE", str(tmp_path / "o.json"))
    monkeypatch.setenv("TRUTH_BOARD_STATUS_FILE", str(tmp_path / "status.json"))
    monkeypatch.setenv("TRADING_LOG_FILE", str(tmp_path / "tl.json"))
    status = truth_board.run_once()
    fr = status["friction_resolution"]
    assert set(fr) == {"lifetime", "30d", "7d", "without_fill"}
    assert fr["7d"]["evaluated"] == 0
