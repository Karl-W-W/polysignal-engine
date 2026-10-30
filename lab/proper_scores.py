"""lab/proper_scores.py — Brier and log score beside accuracy (KR-S1, card 005).

Forecast: P(YES) = confidence for a Bullish call, 1 - confidence for Bearish
(confidence = the model's stated chance its call is right). Outcome: 1 iff the
market resolved YES. Only clean YES/NO resolutions are scored; AMBIGUOUS is out.
Brier = mean (p - y)^2, lower is better (0.25 = coin flip). Log loss = mean
-ln(p of what happened), lower is better (ln 2 = 0.693 = coin flip), with p
clipped to [EPS, 1 - EPS], EPS = 1e-4, so one miss costs at most ln(1e4) = 9.21.
`market_*` scores price_at_prediction as the forecast: the bar to beat.
"""
import math
from datetime import datetime, timedelta, timezone

EPS = 1e-4


def brier(p, y):
    return (p - y) ** 2


def log_loss(p, y, eps=EPS):
    p = min(max(p, eps), 1.0 - eps)
    return -math.log(p if y else 1.0 - p)


def p_yes(rec):
    c = float(rec.get("confidence") or 0.0)
    return c if rec.get("hypothesis") == "Bullish" else 1.0 - c


def score(records, days=None, dedup=False, now=None):
    """Score resolved records; `days` windows by evaluated_at; `dedup` keeps the
    earliest record per (market_id, hypothesis) like eval/resolution_backtest.py."""
    rs = [r for r in records if r.get("resolved_outcome") in ("YES", "NO")
          and r.get("hypothesis") in ("Bullish", "Bearish")]
    if days is not None:
        cut = ((now or datetime.now(timezone.utc)) - timedelta(days=days)).isoformat()
        rs = [r for r in rs if (r.get("evaluated_at") or "") >= cut]
    if dedup:
        first = {}
        for r in sorted(rs, key=lambda r: r.get("timestamp") or ""):
            first.setdefault((r["market_id"], r["hypothesis"]), r)
        rs = list(first.values())
    n = len(rs)
    if n == 0:
        return {"n": 0, "accuracy": None, "brier": None, "log_loss": None,
                "market_brier": None, "market_log_loss": None, "eps": EPS}
    ys = [1 if r["resolved_outcome"] == "YES" else 0 for r in rs]
    ps = [p_yes(r) for r in rs]
    ms = [float(r.get("price_at_prediction") or 0.5) for r in rs]
    hits = sum(1 for r, y in zip(rs, ys) if (r["hypothesis"] == "Bullish") == bool(y))
    return {"n": n, "accuracy": round(hits / n, 4),
            "brier": round(sum(map(brier, ps, ys)) / n, 4),
            "log_loss": round(sum(map(log_loss, ps, ys)) / n, 4),
            "market_brier": round(sum(map(brier, ms, ys)) / n, 4),
            "market_log_loss": round(sum(map(log_loss, ms, ys)) / n, 4), "eps": EPS}
