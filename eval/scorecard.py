"""eval/scorecard.py — PolySignal scorecard: skill against the market (KR-S1).

Reads a COPY of prediction_outcomes.json (optionally trading_log.json) and
prints a markdown scorecard for the windows all / 30d / 7d. Every number on
the page is computed here from the files; nothing is typed by hand.

    python3 eval/scorecard.py --outcomes COPY/prediction_outcomes.json \
        [--trades COPY/trading_log.json] [--now 2026-10-31T10:18:59Z]

Scored windows cut on evaluated_at, like lab/proper_scores.score. The headline
is ONE forecast per market (the earliest call, dedup=True): rows of the same
market are not independent, so the effective N is distinct markets. The 95%
interval on Brier skill is a bootstrap that resamples MARKETS (all of a
market's rows move together, model and market paired) with a fixed seed, so a
rerun on the same file prints the same page. "all" is the file's 5000-row
rotation window, not the lifetime counters, which carry no probabilities.
"""
import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lab.proper_scores import (brier, brier_skill, outcome, p_market,  # noqa: E402
                               p_yes, score, scored_records)

WINDOWS = (("all", None), ("30d", 30), ("7d", 7))
REPS, SEED = 2000, 20261031
GATE_WIN_RATE = 0.45  # lab/GOALS.md: live $1 trade gate (with real edge vs price)


def _market_ci(rs, pair, combine, reps=REPS, seed=SEED):
    """95% percentile interval of combine(sum a, sum b) over (a, b) = pair(row),
    resampling MARKETS with replacement (a market's rows move together)."""
    by = {}
    for r in rs:
        a, b = pair(r)
        g = by.setdefault(r.get("market_id"), [0.0, 0.0])
        g[0] += a
        g[1] += b
    groups = list(by.values())
    if len(groups) < 2:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        draw = rng.choices(groups, k=len(groups))
        v = combine(sum(g[0] for g in draw), sum(g[1] for g in draw))
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    return vals[round(0.025 * (len(vals) - 1))], vals[round(0.975 * (len(vals) - 1))]


def _squared_errors(r):
    y = outcome(r)
    return brier(p_yes(r), y), brier(p_market(r), y)


def edge_vs_price(r):
    """Result of buying the called side at the prediction-time price and holding
    to resolution, per $1 share, before fees and spread: y - p for Bullish,
    p - y for Bearish. With every call Bullish its mean is accuracy - mean price,
    the edge_vs_price_implied of eval/resolution_backtest.py."""
    d = outcome(r) - p_market(r)
    return d if r["hypothesis"] == "Bullish" else -d


def skill_ci(rs, reps=REPS, seed=SEED):
    """95% interval of Brier skill vs market, resampling markets."""
    return _market_ci(rs, _squared_errors, brier_skill, reps, seed)


def edge_ci(rs, reps=REPS, seed=SEED):
    """95% interval of the mean edge vs price, resampling markets."""
    return _market_ci(rs, lambda r: (edge_vs_price(r), 1.0), lambda a, n: a / n, reps, seed)


def vs_zero(ci):
    if ci is None:
        return "too few markets to tell"
    if ci[1] < 0:
        return "below zero"
    if ci[0] > 0:
        return "above zero"
    return "not distinguishable from zero"


def verdict(skill, ci):
    if skill is None:
        return "no data"
    if ci is None:
        return "too few markets to tell"
    if ci[1] < 0:
        return "worse than the market price"
    if ci[0] > 0:
        return "beats the market price"
    return "no detectable difference from the market price"


def _cut(now, days):
    return "" if days is None else (now - timedelta(days=days)).isoformat()


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def f4(x):
    return "–" if x is None else f"{x:.4f}"


def sk(x):
    return "–" if x is None else f"{x:+.4f}"


def pct(x):
    return "–" if x is None else f"{100 * x:.1f}%"


def ci_s(ci):
    return "–" if ci is None else f"[{ci[0]:+.3f}, {ci[1]:+.3f}]"


def pp(x):
    return "–" if x is None else f"{100 * x:+.1f} pp"


def ci_pp(ci):
    return "–" if ci is None else f"[{100 * ci[0]:+.1f}, {100 * ci[1]:+.1f}] pp"


def window(preds, days, now, dedup):
    rs = scored_records(preds, days=days, dedup=dedup, now=now)
    s = score(rs)  # rs is already windowed and deduped: the intervals score the same rows
    s["ci"] = skill_ci(rs)
    s["verdict"] = verdict(s["brier_skill_vs_market"], s["ci"])
    s["acc"] = _mean([(r["hypothesis"] == "Bullish") == bool(outcome(r)) for r in rs])
    s["edge"] = _mean([edge_vs_price(r) for r in rs])
    s["edge_ci"] = edge_ci(rs)
    s["yes_rate"] = _mean([outcome(r) for r in rs])
    s["mean_price"] = _mean([p_market(r) for r in rs])
    s["mean_p_yes"] = _mean([p_yes(r) for r in rs])
    s["no_price"] = sum(1 for r in rs if not r.get("price_at_prediction"))
    return s


def trades_window(trades, days, now):
    cut = _cut(now, days)
    ev = [t for t in trades if t.get("result") in ("win", "loss")
          and (t.get("timestamp") or "") >= cut]
    wins = sum(t["result"] == "win" for t in ev)
    return {"n": len(ev), "wins": wins, "win_rate": wins / len(ev) if ev else None,
            "pnl": sum(float(t.get("pnl") or 0) for t in ev),
            "markets": len({t.get("market_id") for t in ev}),
            "slippage": sorted({t.get("slippage_pp") for t in ev}, key=str)}


def render(outcomes_path, trades_path=None, now=None):
    now = now or datetime.now(timezone.utc)
    with open(outcomes_path, "rb") as fh:
        raw = fh.read()
    data = json.loads(raw)
    preds = data.get("predictions") or []
    one = {name: window(preds, days, now, True) for name, days in WINDOWS}
    rows = {name: window(preds, days, now, False) for name, days in WINDOWS}
    L = [f"# PolySignal scorecard — skill against the market, {now:%Y-%m-%d %H:%M}Z", ""]

    L += ["## Verdict", ""]
    beats = [w for w in one if one[w]["verdict"] == "beats the market price"]
    picks = [w for w in one if vs_zero(one[w]["edge_ci"]) == "above zero"]
    if beats or picks:
        L.append(f"**Edge detected** — Brier skill above zero in: {', '.join(beats) or 'none'}; "
                 f"edge vs price above zero in: {', '.join(picks) or 'none'}.")
    else:
        L.append("**No edge against the market.** In no window is the Brier skill vs the "
                 "market price, or the edge vs price, above zero with 95% confidence "
                 "(one forecast per market).")
    L.append("")
    for name, s in one.items():
        L.append(f"- {name}: {s['n_markets']} resolved markets. Brier skill "
                 f"{sk(s['brier_skill_vs_market'])} {ci_s(s['ci'])}, {s['verdict']}. "
                 f"Edge vs price {pp(s['edge'])} {ci_pp(s['edge_ci'])}, "
                 f"{vs_zero(s['edge_ci'])}.")
    scored_bull = {s["bullish_share"] for s in rows.values() if s["n"]}
    if scored_bull == {1.0}:
        L.append("- Every scored forecast is a Bullish call, so accuracy is the YES rate of "
                 "the markets picked, and the market price already predicts that rate.")
    L += ["", "Brier skill = 1 − Brier / market Brier: above 0 the model's probabilities beat "
          "quoting the market price, 0 ties, below 0 is worse. Edge vs price = the average "
          "result of buying the called side at the price of the first call and holding to "
          "resolution, per $1 share, before fees and spread. Both intervals resample markets.", ""]

    L += ["## Scores — one forecast per market (the earliest call)", "",
          "| window | resolved markets | accuracy | Brier | market Brier | Brier skill "
          "| 95% interval | log loss | market log loss | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in one.items():
        L.append(f"| {name} | {s['n_markets']} | {pct(s['acc'])} | {f4(s['brier'])} "
                 f"| {f4(s['market_brier'])} | {sk(s['brier_skill_vs_market'])} "
                 f"| {ci_s(s['ci'])} | {f4(s['log_loss'])} | {f4(s['market_log_loss'])} "
                 f"| {s['verdict']} |")

    L += ["", "## What the forecasts said — one per market", "",
          "| window | YES rate | mean entry price | mean model P(YES) "
          "| edge vs price | 95% interval | Bullish share (scored) |",
          "|---|---|---|---|---|---|---|"]
    for name, s in one.items():
        L.append(f"| {name} | {pct(s['yes_rate'])} | {f4(s['mean_price'])} "
                 f"| {f4(s['mean_p_yes'])} | {pp(s['edge'])} | {ci_pp(s['edge_ci'])} "
                 f"| {pct(s['bullish_share'])} |")

    L += ["", "## Contrast — every resolved row (repeat calls on one market counted again)", "",
          "| window | rows | markets | accuracy | Brier | market Brier | Brier skill "
          "| 95% interval (by market) | log loss | market log loss |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in rows.items():
        L.append(f"| {name} | {s['n']} | {s['n_markets']} | {pct(s['acc'])} "
                 f"| {f4(s['brier'])} | {f4(s['market_brier'])} "
                 f"| {sk(s['brier_skill_vs_market'])} | {ci_s(s['ci'])} "
                 f"| {f4(s['log_loss'])} | {f4(s['market_log_loss'])} |")

    L += ["", "## Bullish share of predictions made (every row in the file, by prediction time)", "",
          "| window | predictions | Bullish | Bullish share |", "|---|---|---|---|"]
    for name, days in WINDOWS:
        made = [r for r in preds if (r.get("timestamp") or "") >= _cut(now, days)]
        bull = sum(r.get("hypothesis") == "Bullish" for r in made)
        L.append(f"| {name} | {len(made)} | {bull} | {pct(bull / len(made) if made else None)} |")

    if trades_path:
        with open(trades_path, "rb") as fh:
            traw = fh.read()
        trades = json.loads(traw).get("trades") or []
        L += ["", "## Context — paper trades (scored on price drift, not on resolution)", "",
              "| window (by trade time) | evaluated trades | wins | win rate "
              f"| gap to the {pct(GATE_WIN_RATE)} bar | PnL (sum) | markets |",
              "|---|---|---|---|---|---|---|"]
        slips = set()
        for name, days in WINDOWS:
            t = trades_window(trades, days, now)
            slips.update(map(str, t["slippage"]))
            gap = None if t["win_rate"] is None else t["win_rate"] - GATE_WIN_RATE
            L.append(f"| {name} | {t['n']} | {t['wins']} | {pct(t['win_rate'])} "
                     f"| {'–' if gap is None else f'{100 * gap:+.1f} pp'} "
                     f"| {t['pnl']:+.2f} | {t['markets']} |")
        L += ["", f"A paper trade wins when its price move at least 4 h later, minus slippage "
              f"(values seen: {', '.join(sorted(slips))}), is at least zero "
              "(lab/polymarket_trader.py, evaluate_paper_trades). A flat market is a loss. "
              f"The {pct(GATE_WIN_RATE)} bar is the live $1 trade gate in lab/GOALS.md, which "
              "also requires real edge vs price. This page reads the gate; it does not touch it.",
              f"File: sha256 {hashlib.sha256(traw).hexdigest()[:16]}…, {len(trades)} trades."]

    res = [r for r in preds if r.get("resolved_outcome") in ("YES", "NO")]
    pend = [r for r in preds if not r.get("evaluated")]
    st = data.get("stats") or {}
    oldest_res = min((r.get("timestamp") or "" for r in res), default="")
    L += ["", "## Provenance and limits", "",
          f"- Source: {os.path.basename(outcomes_path)}, sha256 "
          f"{hashlib.sha256(raw).hexdigest()[:16]}…, {len(raw)} bytes, {len(preds)} rows; "
          f"reference time {now.isoformat()}.",
          "- Scored windows cut on evaluated_at, when the call was checked against its "
          "market's resolution, not on when the call was made.",
          f"- Rows: {len(res)} resolved YES/NO, "
          f"{sum(1 for r in preds if r.get('outcome') == 'AMBIGUOUS')} ambiguous (not scored), "
          f"{len(pend)} pending.",
          f"- Resolved rows were evaluated {min((r.get('evaluated_at') or '' for r in res), default='–')[:10]}"
          f" to {max((r.get('evaluated_at') or '' for r in res), default='–')[:10]} and predicted "
          f"{oldest_res[:10] or '–'} to "
          f"{max((r.get('timestamp') or '' for r in res), default='–')[:10]}. "
          "So \"all\" means this rotation window, not the system's lifetime.",
          f"- {sum(1 for r in pend if (r.get('timestamp') or '') < oldest_res)} pending rows "
          f"were predicted before the oldest resolved row. The 5000-row rotation keeps every "
          "pending row and drops evaluated rows from the front of the list "
          "(lab/outcome_tracker.py, OutcomeState.save), so long-dated calls can resolve and be "
          "dropped before this page sees them.",
          f"- Lifetime counters: {st.get('total_predictions')} predictions, "
          f"{st.get('total_evaluated')} evaluated, accuracy {st.get('accuracy')}. They carry no "
          "probabilities, so they cannot be Brier-scored.",
          f"- Scored rows with no usable market price (scored against 0.5): "
          f"{rows['all']['no_price']}.",
          f"- Interval: {REPS} bootstrap draws over markets, seed {SEED}, percentile 2.5–97.5.",
          f"- Generator: eval/scorecard.py on lab/proper_scores.py (log loss clip eps "
          f"{one['all']['eps']})."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--outcomes", required=True, help="a COPY of prediction_outcomes.json")
    ap.add_argument("--trades", help="a COPY of trading_log.json (optional)")
    ap.add_argument("--now", help="reference time, ISO 8601 (default: now, UTC)")
    a = ap.parse_args(argv)
    now = (datetime.fromisoformat(a.now.replace("Z", "+00:00")).astimezone(timezone.utc)
           if a.now else None)
    sys.stdout.write(render(a.outcomes, a.trades, now))


if __name__ == "__main__":
    main()
