#!/usr/bin/env python3
"""
lab/backtester.py
==================
Prediction Market Backtester for PolySignal-OS.

Unlike traditional backtesting (continuous price, stop-loss, etc.),
prediction markets resolve to 0 or 1. This backtester handles:
- Binary outcomes (CORRECT/INCORRECT/NEUTRAL)
- XGBoost gate confidence filtering
- Per-market and per-direction analysis
- Kelly criterion position sizing
- Sweep over confidence thresholds

Usage:
    from lab.backtester import backtest, sweep_thresholds

    results = backtest("/opt/loop/data/prediction_outcomes.json")
    sweep = sweep_thresholds(results.predictions, thresholds=[0.5, 0.6, 0.7, 0.8])
"""

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ============================================================================
# CONFIG
# ============================================================================

OUTCOMES_DEFAULT = os.getenv(
    "OUTCOMES_PATH", "/opt/loop/data/prediction_outcomes.json"
)
# Markets known to be toxic (Session 23: Loop's per-market audit)
EXCLUDED_MARKETS = {"824952", "556062", "1373744", "965261", "1541748", "692258"}


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class BacktestTrade:
    """A single simulated trade from a historical prediction."""
    market_id: str
    direction: str              # Bullish or Bearish
    entry_price: float          # Market probability at prediction time
    outcome: str                # CORRECT or INCORRECT
    confidence: float           # Predictor confidence (0-1)
    xgb_p_correct: Optional[float]  # XGBoost gate score
    pnl: float                  # Profit/loss per $1 wagered
    timestamp: str


@dataclass
class BacktestResult:
    """Full backtest results."""
    total_predictions: int
    evaluated: int
    traded: int                 # Passed all filters
    excluded: int               # Filtered out
    win_rate: float
    total_pnl: float            # Per $1 wagered per trade
    avg_pnl: float
    sharpe: float
    max_drawdown: float
    best_trade: float
    worst_trade: float
    direction_split: Dict[str, Dict[str, Any]]
    market_split: Dict[str, Dict[str, Any]]
    predictions: List[Dict[str, Any]]  # Raw predictions for sweep
    trades: List[BacktestTrade]
    config: Dict[str, Any]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trades"] = [asdict(t) for t in self.trades]
        return d

    def summary(self) -> str:
        lines = [
            f"{'='*60}",
            f"BACKTEST RESULTS",
            f"{'='*60}",
            f"Predictions: {self.total_predictions} total, {self.evaluated} evaluated, {self.traded} traded",
            f"Win rate:    {self.win_rate:.1%}",
            f"Total P&L:   {self.total_pnl:+.4f} (per $1/trade)",
            f"Avg P&L:     {self.avg_pnl:+.4f}",
            f"Sharpe:      {self.sharpe:.2f}",
            f"Max DD:      {self.max_drawdown:.4f}",
            f"Best trade:  {self.best_trade:+.4f}",
            f"Worst trade: {self.worst_trade:+.4f}",
            "",
            "Direction breakdown:",
        ]
        for direction, stats in self.direction_split.items():
            lines.append(
                f"  {direction}: {stats['win_rate']:.0%} "
                f"({stats['wins']}W/{stats['losses']}L) "
                f"avg_pnl={stats['avg_pnl']:+.4f}"
            )
        lines.append("\nMarket breakdown:")
        for mid, stats in sorted(
            self.market_split.items(), key=lambda x: x[1]["win_rate"], reverse=True
        ):
            lines.append(
                f"  {mid}: {stats['win_rate']:.0%} "
                f"({stats['wins']}W/{stats['losses']}L) "
                f"avg_pnl={stats['avg_pnl']:+.4f}"
            )
        return "\n".join(lines)


# ============================================================================
# CORE BACKTEST
# ============================================================================

def backtest(
    outcomes_path: str = OUTCOMES_DEFAULT,
    min_confidence: float = 0.0,
    min_xgb_score: float = 0.0,
    exclude_markets: Optional[set] = None,
    exclude_neutral: bool = True,
    position_size_usd: float = 1.0,
) -> BacktestResult:
    """
    Backtest all historical predictions.

    Args:
        outcomes_path: Path to prediction_outcomes.json
        min_confidence: Minimum predictor confidence to trade
        min_xgb_score: Minimum XGBoost gate score to trade
        exclude_markets: Markets to exclude (defaults to EXCLUDED_MARKETS)
        exclude_neutral: Whether to skip NEUTRAL outcomes
        position_size_usd: Simulated position size per trade
    """
    if exclude_markets is None:
        exclude_markets = EXCLUDED_MARKETS

    with open(outcomes_path) as f:
        data = json.load(f)

    predictions = data.get("predictions", [])
    trades: List[BacktestTrade] = []
    excluded_count = 0

    for pred in predictions:
        outcome = pred.get("outcome")
        if not outcome:
            continue

        if exclude_neutral and outcome == "NEUTRAL":
            excluded_count += 1
            continue

        market_id = str(pred.get("market_id", ""))
        if market_id in exclude_markets:
            excluded_count += 1
            continue

        confidence = pred.get("confidence", 0)
        if confidence < min_confidence:
            excluded_count += 1
            continue

        xgb_score = pred.get("xgb_p_correct")
        if min_xgb_score > 0 and (xgb_score is None or xgb_score < min_xgb_score):
            excluded_count += 1
            continue

        direction = pred.get("hypothesis", pred.get("direction", ""))
        entry_price = pred.get("market_price", pred.get("current_price", 0.5))

        # Prediction market P&L:
        # Bullish (buy Yes): pay entry_price, receive 1 if correct, 0 if wrong
        # Bearish (buy No): pay (1-entry_price), receive 1 if correct, 0 if wrong
        if outcome == "CORRECT":
            if direction == "Bullish":
                pnl = (1.0 - entry_price) * position_size_usd
            else:  # Bearish
                pnl = entry_price * position_size_usd
        else:  # INCORRECT
            if direction == "Bullish":
                pnl = -entry_price * position_size_usd
            else:  # Bearish
                pnl = -(1.0 - entry_price) * position_size_usd

        trades.append(BacktestTrade(
            market_id=market_id,
            direction=direction,
            entry_price=entry_price,
            outcome=outcome,
            confidence=confidence,
            xgb_p_correct=xgb_score,
            pnl=round(pnl, 6),
            timestamp=pred.get("timestamp", ""),
        ))

    # Compute stats
    pnls = [t.pnl for t in trades]
    wins = sum(1 for t in trades if t.outcome == "CORRECT")
    losses = sum(1 for t in trades if t.outcome == "INCORRECT")
    total = wins + losses

    win_rate = wins / total if total > 0 else 0
    total_pnl = sum(pnls)
    avg_pnl = total_pnl / total if total > 0 else 0
    std_pnl = (sum((p - avg_pnl) ** 2 for p in pnls) / max(total - 1, 1)) ** 0.5
    sharpe = avg_pnl / std_pnl if std_pnl > 0 else 0

    # Max drawdown (cumulative)
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        cumulative += pnl
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

    # Direction split
    direction_split = {}
    for direction in ("Bullish", "Bearish"):
        dt = [t for t in trades if t.direction == direction]
        dw = sum(1 for t in dt if t.outcome == "CORRECT")
        dl = sum(1 for t in dt if t.outcome == "INCORRECT")
        dtot = dw + dl
        direction_split[direction] = {
            "wins": dw, "losses": dl, "total": dtot,
            "win_rate": dw / dtot if dtot > 0 else 0,
            "avg_pnl": sum(t.pnl for t in dt) / dtot if dtot > 0 else 0,
        }

    # Market split
    market_split = {}
    markets = set(t.market_id for t in trades)
    for mid in markets:
        mt = [t for t in trades if t.market_id == mid]
        mw = sum(1 for t in mt if t.outcome == "CORRECT")
        ml = sum(1 for t in mt if t.outcome == "INCORRECT")
        mtot = mw + ml
        market_split[mid] = {
            "wins": mw, "losses": ml, "total": mtot,
            "win_rate": mw / mtot if mtot > 0 else 0,
            "avg_pnl": sum(t.pnl for t in mt) / mtot if mtot > 0 else 0,
        }

    return BacktestResult(
        total_predictions=len(predictions),
        evaluated=sum(1 for p in predictions if p.get("outcome")),
        traded=total,
        excluded=excluded_count,
        win_rate=win_rate,
        total_pnl=round(total_pnl, 6),
        avg_pnl=round(avg_pnl, 6),
        sharpe=round(sharpe, 4),
        max_drawdown=round(max_dd, 6),
        best_trade=max(pnls) if pnls else 0,
        worst_trade=min(pnls) if pnls else 0,
        direction_split=direction_split,
        market_split=market_split,
        predictions=predictions,
        trades=trades,
        config={
            "min_confidence": min_confidence,
            "min_xgb_score": min_xgb_score,
            "exclude_markets": list(exclude_markets),
            "exclude_neutral": exclude_neutral,
            "position_size_usd": position_size_usd,
        },
    )


def sweep_thresholds(
    outcomes_path: str = OUTCOMES_DEFAULT,
    confidence_thresholds: Optional[List[float]] = None,
    xgb_thresholds: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """
    Sweep over confidence and XGBoost gate thresholds to find optimal.

    Returns list of results sorted by Sharpe ratio.
    """
    if confidence_thresholds is None:
        confidence_thresholds = [0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]
    if xgb_thresholds is None:
        xgb_thresholds = [0.0, 0.5, 0.6, 0.7, 0.8]

    results = []
    for conf in confidence_thresholds:
        for xgb in xgb_thresholds:
            r = backtest(
                outcomes_path=outcomes_path,
                min_confidence=conf,
                min_xgb_score=xgb,
            )
            if r.traded >= 5:  # Need minimum sample size
                results.append({
                    "min_confidence": conf,
                    "min_xgb_score": xgb,
                    "traded": r.traded,
                    "win_rate": r.win_rate,
                    "total_pnl": r.total_pnl,
                    "avg_pnl": r.avg_pnl,
                    "sharpe": r.sharpe,
                    "max_drawdown": r.max_drawdown,
                })

    return sorted(results, key=lambda x: x["sharpe"], reverse=True)


def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Kelly criterion for optimal position sizing.
    Returns fraction of bankroll to wager (0-1).
    """
    if avg_loss == 0 or win_rate <= 0:
        return 0.0
    b = avg_win / abs(avg_loss)  # odds ratio
    f = (b * win_rate - (1 - win_rate)) / b
    return max(0.0, min(f, 0.25))  # Cap at 25% of bankroll (quarter-Kelly)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else OUTCOMES_DEFAULT

    print("Running backtest on clean markets (excluding toxic 4)...")
    result = backtest(path)
    print(result.summary())

    print(f"\n{'='*60}")
    print("THRESHOLD SWEEP")
    print(f"{'='*60}")
    sweep = sweep_thresholds(path)
    print(f"{'Conf':>6} {'XGB':>6} {'Trades':>7} {'WinRate':>8} {'PnL':>8} {'Sharpe':>8}")
    for s in sweep[:10]:
        print(
            f"{s['min_confidence']:>6.2f} {s['min_xgb_score']:>6.2f} "
            f"{s['traded']:>7d} {s['win_rate']:>7.1%} "
            f"{s['total_pnl']:>+8.4f} {s['sharpe']:>8.4f}"
        )

    # Kelly criterion
    if result.traded > 0:
        wins = [t.pnl for t in result.trades if t.pnl > 0]
        losses = [t.pnl for t in result.trades if t.pnl < 0]
        if wins and losses:
            avg_win = sum(wins) / len(wins)
            avg_loss = sum(losses) / len(losses)
            kelly = kelly_criterion(result.win_rate, avg_win, avg_loss)
            print(f"\nKelly Criterion: {kelly:.1%} of bankroll per trade")
            print(f"  On $100 bankroll: ${kelly * 100:.2f} per trade")
