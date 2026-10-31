"""lab/proper_scores.py — Brier and log score beside accuracy (KR-S1, card 005).

Forecast: P(YES) = confidence for a Bullish call, 1 - confidence for Bearish
(confidence = the model's stated chance its call is right). Outcome: 1 iff the
market resolved YES. Only clean YES/NO resolutions are scored; AMBIGUOUS is out.
Brier = mean (p - y)^2, lower is better (0.25 = coin flip). Log loss = mean
-ln(p of what happened), lower is better (ln 2 = 0.693 = coin flip), with p
clipped to [EPS, 1 - EPS], EPS = 1e-4, so one miss costs at most ln(1e4) = 9.21.
`market_*` scores price_at_prediction as the forecast: the bar to beat.

Brier skill vs market = 1 - Brier / market Brier over the SAME scored records:
> 0 beats the price, 0 ties it, < 0 is worse than quoting the price. It is
computed from the window's summed squared errors, so it is n-weighted: two
windows pooled weigh by their n, never by the mean of their own ratios. It is
None when the market made no error at all (any skill is undefined there).
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


def p_market(rec):
    return float(rec.get("price_at_prediction") or 0.5)


def outcome(rec):
    return 1 if rec["resolved_outcome"] == "YES" else 0


def brier_skill(model_sse, market_sse):
    """1 - model/market from squared-error SUMS over the same records."""
    if market_sse <= 0:
        return None
    return round(1.0 - model_sse / market_sse, 4)


def scored_records(records, days=None, dedup=False, now=None):
    """The records `score` scores: resolved YES/NO directional calls; `days`
    windows by evaluated_at; `dedup` keeps the earliest record per
    (market_id, hypothesis) like eval/resolution_backtest.py."""
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
    return rs


def score(records, days=None, dedup=False, now=None):
    """Accuracy, Brier, log loss and Brier skill vs market over
    `scored_records(records, days, dedup, now)`."""
    rs = scored_records(records, days=days, dedup=dedup, now=now)
    n = len(rs)
    if n == 0:
        return {"n": 0, "n_markets": 0, "accuracy": None, "brier": None,
                "log_loss": None, "market_brier": None, "market_log_loss": None,
                "brier_skill_vs_market": None, "bullish_share": None, "eps": EPS}
    ys = [outcome(r) for r in rs]
    ps = [p_yes(r) for r in rs]
    ms = [p_market(r) for r in rs]
    hits = sum(1 for r, y in zip(rs, ys) if (r["hypothesis"] == "Bullish") == bool(y))
    sse, market_sse = sum(map(brier, ps, ys)), sum(map(brier, ms, ys))
    return {"n": n, "n_markets": len({r.get("market_id") for r in rs}),
            "accuracy": round(hits / n, 4),
            "brier": round(sse / n, 4),
            "log_loss": round(sum(map(log_loss, ps, ys)) / n, 4),
            "market_brier": round(market_sse / n, 4),
            "market_log_loss": round(sum(map(log_loss, ms, ys)) / n, 4),
            "brier_skill_vs_market": brier_skill(sse, market_sse),
            "bullish_share": round(sum(r["hypothesis"] == "Bullish" for r in rs) / n, 4),
            "eps": EPS}
