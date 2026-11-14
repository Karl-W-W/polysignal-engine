"""tests/test_scorecard.py — eval/scorecard.py: skill against the market (KR-S1)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from eval.scorecard import (edge_ci, edge_vs_price, main, render, skill_ci, verdict,
                            vs_zero)

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def _rec(mid, conf, outcome, price, days_ago=2, ts="2026-10-01T00:00:00+00:00", hyp="Bullish"):
    return {"market_id": mid, "hypothesis": hyp, "confidence": conf, "price_at_prediction": price,
            "resolved_outcome": outcome, "outcome": None if outcome is None else "X",
            "evaluated": outcome is not None, "timestamp": ts,
            "evaluated_at": (NOW - timedelta(days=days_ago)).isoformat()}


def _file(tmp_path):
    preds = [_rec("a", 0.8, "YES", 0.7), _rec("b", 0.8, "NO", 0.7),
             _rec("c", 0.6, "YES", 0.6, days_ago=20),
             _rec("a", 0.9, "YES", 0.75, ts="2026-10-02T00:00:00+00:00"),  # repeat call on a
             {**_rec("d", 0.7, None, 0.7), "evaluated_at": None}]          # pending
    f = tmp_path / "prediction_outcomes.json"
    f.write_text(json.dumps({"predictions": preds, "per_market": {},
                             "stats": {"total_predictions": 9, "total_evaluated": 8,
                                       "accuracy": 0.5}}))
    return f


def test_edge_vs_price_is_the_hold_to_resolution_result_of_the_called_side():
    assert edge_vs_price(_rec("a", 0.8, "YES", 0.7)) == pytest.approx(0.3)
    assert edge_vs_price(_rec("a", 0.8, "NO", 0.7)) == pytest.approx(-0.7)
    # Bearish buys NO at 1 - price: pays 1 on NO
    assert edge_vs_price(_rec("a", 0.8, "NO", 0.7, hyp="Bearish")) == pytest.approx(0.7)
    assert edge_vs_price(_rec("a", 0.8, "YES", 0.7, hyp="Bearish")) == pytest.approx(-0.3)


def test_intervals_resample_markets_and_are_deterministic():
    tie = [_rec("a", 0.7, "YES", 0.7), _rec("b", 0.6, "NO", 0.6), _rec("c", 0.8, "YES", 0.8)]
    assert skill_ci(tie) == (0.0, 0.0)  # model == market on every market: skill is 0 in every draw
    assert skill_ci(tie[:1]) is None and edge_ci(tie[:1]) is None  # one market: no interval
    mixed = tie + [_rec("d", 0.9, "NO", 0.6), _rec("e", 0.9, "YES", 0.6)]
    lo, hi = skill_ci(mixed)
    assert lo <= hi and skill_ci(mixed) == skill_ci(mixed)
    lo, hi = edge_ci(mixed)
    assert lo <= (0.3 + -0.6 + 0.2 - 0.6 + 0.4) / 5 <= hi


def test_verdict_words():
    assert verdict(None, None) == "no data"
    assert verdict(-0.1, None) == "too few markets to tell"
    assert verdict(-0.1, (-0.2, -0.01)) == "worse than the market price"
    assert verdict(0.1, (0.01, 0.2)) == "beats the market price"
    assert verdict(-0.1, (-0.2, 0.1)) == "no detectable difference from the market price"
    assert vs_zero((-0.1, 0.1)) == "not distinguishable from zero"
    assert vs_zero((0.01, 0.1)) == "above zero" and vs_zero((-0.2, -0.1)) == "below zero"


def test_render_scores_one_forecast_per_market(tmp_path):
    page = render(str(_file(tmp_path)), now=NOW)
    # dedup: a (first call), b, c. Model SE .04+.64+.16 vs market .09+.49+.16
    assert "| all | 3 | 66.7% | 0.2800 | 0.2467 | -0.1351 |" in page
    assert "| 7d | 2 | 50.0% |" in page            # c resolved 20 days ago
    assert "| all | 4 | 3 | 75.0% |" in page        # every row: the repeat call counts again
    assert "| all | 5 | 5 | 100.0% |" in page       # predictions made, pending included
    assert "Every scored forecast is a Bullish call" in page
    assert "4 resolved YES/NO, 0 ambiguous (not scored), 1 pending." in page
    assert page == render(str(_file(tmp_path)), now=NOW)  # same file, same page


def test_render_paper_trades_context_and_cli(tmp_path, capsys):
    t = tmp_path / "trading_log.json"
    t.write_text(json.dumps({"trades": [
        {"market_id": "a", "result": "win", "pnl": 0.01, "slippage_pp": 0.005,
         "timestamp": "2026-10-29T00:00:00+00:00"},
        {"market_id": "b", "result": "loss", "pnl": -0.03, "slippage_pp": 0.005,
         "timestamp": "2026-10-29T00:00:00+00:00"},
        {"market_id": "c", "result": None, "timestamp": "2026-10-29T00:00:00+00:00"}]}))
    main(["--outcomes", str(_file(tmp_path)), "--trades", str(t), "--now", "2026-10-30T00:00:00Z"])
    page = capsys.readouterr().out
    assert "| all | 2 | 1 | 50.0% | +5.0 pp | -0.02 | 2 |" in page
    assert "reference time 2026-10-30T00:00:00+00:00" in page
