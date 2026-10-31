"""tests/test_proper_scores.py — Brier and log score beside accuracy (KR-S1)."""
import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from lab.outcome_tracker import get_proper_scores
from lab.proper_scores import EPS, brier, log_loss, p_yes, score

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def _rec(mid, hyp, conf, outcome, days_ago=1, price=None, ts="2026-10-01T00:00:00+00:00"):
    return {"market_id": mid, "hypothesis": hyp, "confidence": conf,
            "price_at_prediction": conf if price is None else price,
            "resolved_outcome": outcome, "timestamp": ts,
            "evaluated_at": (NOW - timedelta(days=days_ago)).isoformat()}


def test_brier_and_log_loss_basics():
    assert brier(0.5, 1) == 0.25 and brier(1.0, 1) == 0.0
    assert log_loss(0.5, 0) == pytest.approx(math.log(2))
    # clipping: a certain, wrong forecast costs ln(1/EPS), not infinity
    assert log_loss(1.0, 0) == pytest.approx(-math.log(EPS))
    assert log_loss(0.0, 0) == pytest.approx(-math.log(1 - EPS))


def test_bearish_maps_to_one_minus_confidence():
    assert p_yes({"hypothesis": "Bullish", "confidence": 0.8}) == 0.8
    assert p_yes({"hypothesis": "Bearish", "confidence": 0.8}) == pytest.approx(0.2)


def test_score_hand_computed():
    recs = [_rec("a", "Bullish", 0.8, "YES"), _rec("b", "Bullish", 0.8, "NO"),
            _rec("c", "Bearish", 0.6, "NO"),
            {**_rec("d", "Bullish", 0.9, None), "outcome": "AMBIGUOUS"}]
    s = score(recs)
    assert s["n"] == 3
    assert s["accuracy"] == pytest.approx(2 / 3, abs=1e-4)
    assert s["brier"] == pytest.approx((0.04 + 0.64 + 0.16) / 3, abs=1e-4)
    exp = -(math.log(0.8) + math.log(0.2) + math.log(0.6)) / 3
    assert s["log_loss"] == pytest.approx(exp, abs=1e-4)


def test_window_and_dedup():
    recs = [_rec("a", "Bullish", 0.7, "YES", days_ago=40),
            _rec("b", "Bullish", 0.7, "NO", days_ago=2, ts="2026-10-02T00:00:00+00:00"),
            _rec("b", "Bullish", 0.9, "NO", days_ago=2, ts="2026-10-03T00:00:00+00:00")]
    assert score(recs, days=30, now=NOW)["n"] == 2
    d = score(recs, dedup=True)
    assert d["n"] == 2 and d["brier"] == pytest.approx((0.09 + 0.49) / 2, abs=1e-4)
    assert score([])["brier"] is None


def test_get_proper_scores_reads_outcomes_file(tmp_path):
    f = tmp_path / "po.json"
    f.write_text(json.dumps({"predictions": [_rec("a", "Bullish", 0.75, "YES")],
                             "stats": {}, "per_market": {}}))
    s = get_proper_scores(str(f))
    assert s["n"] == 1 and s["brier"] == pytest.approx(0.0625)
    assert s["brier_skill_vs_market"] == 0.0  # confidence == price: a tie


# --- Brier skill vs market: 1 - brier / market_brier ------------------------

def test_brier_skill_beats_ties_and_loses_to_the_price():
    beat = [_rec("a", "Bullish", 0.9, "YES", price=0.6), _rec("b", "Bullish", 0.9, "YES", price=0.6)]
    assert score(beat)["brier_skill_vs_market"] == pytest.approx(1 - 0.02 / 0.32)  # 0.9375
    tie = [_rec("a", "Bullish", 0.7, "YES"), _rec("b", "Bullish", 0.7, "NO")]
    assert score(tie)["brier_skill_vs_market"] == 0.0
    lose = [_rec("a", "Bullish", 0.9, "NO", price=0.6)]
    assert score(lose)["brier_skill_vs_market"] == pytest.approx(1 - 0.81 / 0.36)  # -1.25
    # Bearish maps through 1 - confidence before scoring, like brier itself
    bear = [_rec("a", "Bearish", 0.9, "NO", price=0.4)]  # p_yes 0.1 vs market 0.4
    assert score(bear)["brier_skill_vs_market"] == pytest.approx(1 - 0.01 / 0.16)


def test_brier_skill_is_n_weighted_per_window_not_a_mean_of_ratios():
    recent = [_rec("a", "Bullish", 0.9, "YES", days_ago=2, price=0.6),
              _rec("b", "Bullish", 0.9, "YES", days_ago=2, price=0.6)]  # skill 0.9375
    old = [_rec("c", "Bullish", 0.9, "NO", days_ago=40, price=0.6)]      # skill -1.25
    assert score(recent + old, days=30, now=NOW)["brier_skill_vs_market"] == pytest.approx(0.9375)
    pooled = score(recent + old)["brier_skill_vs_market"]
    assert pooled == pytest.approx(1 - (0.02 + 0.81) / (0.32 + 0.36), abs=1e-4)  # -0.2206
    assert pooled != pytest.approx((0.9375 - 1.25) / 2, abs=1e-3)          # plain mean
    assert pooled != pytest.approx((2 * 0.9375 - 1.25) / 3, abs=1e-3)      # n-weighted mean of ratios


def test_brier_skill_uses_unrounded_sums():
    recs = [_rec("a", "Bullish", 0.83, "YES", price=0.77),
            _rec("b", "Bullish", 0.71, "NO", price=0.64),
            _rec("c", "Bullish", 0.66, "YES", price=0.58)]
    s = score(recs)
    assert (s["brier"], s["market_brier"]) == (0.2162, 0.213)
    assert s["brier_skill_vs_market"] == -0.0152  # exact sums; rounding first gives -0.0150


def test_brier_skill_undefined_when_market_made_no_error():
    # (a price of exactly 0.0 is read as missing -> 0.5, so the perfect market is 1.0 on YES)
    recs = [_rec("a", "Bullish", 0.8, "YES", price=1.0), _rec("b", "Bearish", 0.8, "YES", price=1.0)]
    s = score(recs)
    assert s["market_brier"] == 0.0 and s["brier_skill_vs_market"] is None
    assert score([])["brier_skill_vs_market"] is None


def test_distinct_markets_and_bullish_share():
    recs = [_rec("a", "Bullish", 0.7, "YES", ts="2026-10-01T00:00:00+00:00"),
            _rec("a", "Bullish", 0.8, "YES", ts="2026-10-02T00:00:00+00:00"),
            _rec("b", "Bearish", 0.6, "NO"),
            {**_rec("c", "Bullish", 0.9, None), "outcome": "AMBIGUOUS"}]
    s = score(recs)
    assert (s["n"], s["n_markets"], s["bullish_share"]) == (3, 2, pytest.approx(2 / 3, abs=1e-4))
    d = score(recs, dedup=True)
    assert (d["n"], d["n_markets"], d["bullish_share"]) == (2, 2, 0.5)
    assert score([])["n_markets"] == 0 and score([])["bullish_share"] is None
