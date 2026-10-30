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
