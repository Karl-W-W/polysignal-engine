#!/usr/bin/env python3
"""
lab/backtest_no_bullish_below.py
================================
Replay the resolved predictions in prediction_outcomes.json and the evaluated
paper trades in trading_log.json with and without the 2026-09-04 lever
("no Bullish calls on markets priced below BULLISH_MIN_PRICE").

Arm A (baseline): every resolved directional prediction / evaluated trade.
Arm B (lever):    drop Bullish predictions with price_at_prediction < threshold
                  and BUY trades with price_at_entry < threshold.

Metrics per window (lifetime / 30d / 7d, by record timestamp):
  directional accuracy   correct / (correct + incorrect), resolution-scored
  edge vs price          accuracy - mean(price_at_prediction)  (Bullish-only
                         calls: the price IS the market's forecast)
  friction win rate      pnl >= 0 after the 0.5pp slippage already baked into
                         the log by TradingLog.evaluate_paper_trades
  unique markets         distinct market_id in the arm/window

Read-only over copies of the stores. Usage:
  python3 -m lab.backtest_no_bullish_below --outcomes X.json --trades Y.json \
      [--threshold 0.5] [--now ISO] [--markdown out.md]
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

WINDOWS = (("lifetime", None), ("30d", 30), ("7d", 7))


def _ts(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _in_window(rec: dict, now: datetime, days: Optional[int]) -> bool:
    return days is None or _ts(rec["timestamp"]) >= now - timedelta(days=days)


def prediction_metrics(preds: List[dict]) -> Dict[str, Optional[float]]:
    rows = [p for p in preds if p.get("outcome") in ("CORRECT", "INCORRECT")]
    n = len(rows)
    if n == 0:
        return {"n": 0, "correct": 0, "incorrect": 0, "accuracy": None,
                "mean_price": None, "edge": None, "unique_markets": 0}
    correct = sum(p["outcome"] == "CORRECT" for p in rows)
    mean_price = statistics.mean(float(p["price_at_prediction"]) for p in rows)
    acc = correct / n
    return {"n": n, "correct": correct, "incorrect": n - correct, "accuracy": acc,
            "mean_price": mean_price, "edge": acc - mean_price,
            "unique_markets": len({p["market_id"] for p in rows})}


def trade_metrics(trades: List[dict]) -> Dict[str, Optional[float]]:
    rows = [t for t in trades if t.get("success") and t.get("pnl") is not None]
    n = len(rows)
    if n == 0:
        return {"n": 0, "wins": 0, "win_rate": None, "pnl": 0.0, "unique_markets": 0}
    wins = sum(float(t["pnl"]) >= 0 for t in rows)
    return {"n": n, "wins": wins, "win_rate": wins / n,
            "pnl": sum(float(t["pnl"]) for t in rows),
            "unique_markets": len({t["market_id"] for t in rows})}


def lever_keeps_prediction(p: dict, threshold: float) -> bool:
    price = p.get("price_at_prediction")
    return not (p.get("hypothesis") == "Bullish" and price is not None and float(price) < threshold)


def lever_keeps_trade(t: dict, threshold: float) -> bool:
    price = t.get("price_at_entry")
    return not (t.get("side") == "BUY" and price is not None and float(price) < threshold)


def run(outcomes: dict, trades: List[dict], threshold: float, now: datetime) -> Dict:
    preds = outcomes.get("predictions", [])
    out: Dict[str, Dict] = {"threshold": threshold, "now": now.isoformat(),
                            "stats_lifetime_counters": outcomes.get("stats", {}),
                            "windows": {}}
    for name, days in WINDOWS:
        pw = [p for p in preds if _in_window(p, now, days)]
        tw = [t for t in trades if _in_window(t, now, days)]
        pb = [p for p in pw if lever_keeps_prediction(p, threshold)]
        tb = [t for t in tw if lever_keeps_trade(t, threshold)]
        out["windows"][name] = {
            "A": {"pred": prediction_metrics(pw), "trade": trade_metrics(tw)},
            "B": {"pred": prediction_metrics(pb), "trade": trade_metrics(tb)},
            # Dropped = resolved directional predictions / evaluated trades the
            # lever removes (pending and rejected records are not counted).
            "dropped_predictions": prediction_metrics(pw)["n"] - prediction_metrics(pb)["n"],
            "dropped_trades": trade_metrics(tw)["n"] - trade_metrics(tb)["n"],
        }
    return out


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _pp(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f} pp"


def to_markdown(res: Dict, outcomes_src: str, trades_src: str) -> str:
    th = res["threshold"]
    lines = [
        f"# Backtest — no Bullish calls below {th:.2f} (2026-09-04 lever)",
        "",
        f"Replay of the live stores, read-only. Arm A = baseline, Arm B = lever "
        f"(drop Bullish predictions with price_at_prediction < {th:.2f}; drop BUY paper "
        f"trades with price_at_entry < {th:.2f}). Windows by record timestamp relative to "
        f"`{res['now']}`.",
        "",
        f"- Predictions: `{outcomes_src}` (`predictions` list; resolution-scored outcomes)",
        f"- Paper trades: `{trades_src}` (pnl already net of 0.5 pp slippage)",
        f"- Lifetime counters in the store (not replayable per record): "
        f"`{json.dumps(res['stats_lifetime_counters'])}`",
        "",
        "## Directional accuracy and edge vs price",
        "",
        "| Window | Arm | Directional N | Correct | Accuracy | Mean price | Edge vs price | Unique markets | Dropped |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, w in res["windows"].items():
        for arm in ("A", "B"):
            m = w[arm]["pred"]
            dropped = "—" if arm == "A" else str(w["dropped_predictions"])
            lines.append(
                f"| {name} | {arm} | {m['n']} | {m['correct']} | {_pct(m['accuracy'])} | "
                f"{_pct(m['mean_price'])} | {_pp(m['edge'])} | {m['unique_markets']} | {dropped} |")
    lines += [
        "",
        "## Friction-adjusted paper win rate (where computable)",
        "",
        "| Window | Arm | Evaluated trades | Wins | Win rate | PnL ($1 stakes) | Unique markets | Dropped |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, w in res["windows"].items():
        for arm in ("A", "B"):
            m = w[arm]["trade"]
            dropped = "—" if arm == "A" else str(w["dropped_trades"])
            lines.append(
                f"| {name} | {arm} | {m['n']} | {m['wins']} | {_pct(m['win_rate'])} | "
                f"{m['pnl']:+.2f} | {m['unique_markets']} | {dropped} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcomes", required=True)
    ap.add_argument("--trades", required=True)
    ap.add_argument("--threshold", type=float, default=0.50)
    ap.add_argument("--now", default=None, help="ISO timestamp for window cut (default: now UTC)")
    ap.add_argument("--markdown", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    now = _ts(a.now) if a.now else datetime.now(timezone.utc)
    outcomes = json.load(open(a.outcomes))
    tl = json.load(open(a.trades))
    trades = tl.get("trades", tl) if isinstance(tl, dict) else tl
    res = run(outcomes, trades, a.threshold, now)
    md = to_markdown(res, a.outcomes, a.trades)
    if a.markdown:
        open(a.markdown, "w").write(md)
    if a.json:
        json.dump(res, open(a.json, "w"), indent=2)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
