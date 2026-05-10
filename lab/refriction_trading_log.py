#!/usr/bin/env python3
"""
lab/refriction_trading_log.py
=============================
One-shot backfill: re-evaluate every paper trade in lab/trading_log.json
under the new friction model (S42 Phase 5).

Pre-S42, evaluate_paper_trades computed pnl as (price_delta / entry_price) *
size with NO slippage and NO fees. That counted +0.0001 ticks as wins on
markets where Polymarket's typical spread is 0.5-2pp, and produced a
lifetime "83.7% win rate" that mechanically disagrees with the 36% directional
accuracy in prediction_outcomes.json.

This script:
- Snapshots: cp lab/trading_log.json lab/trading_log.json.pre-friction.bak
- Re-evaluates every successful trade with friction (default 0.5pp slippage,
  0pp fee — same defaults as the live evaluator).
- Writes the re-frictioned log atomically (S42 Phase 2 pattern).
- Prints old vs new W/L counts and lifetime win rate.

Idempotent: a second run produces the same number (deterministic given the
friction params).

Run-once. Does NOT push to git. Does NOT restart the scanner.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def _resolve_trading_log() -> Path:
    return Path(os.getenv(
        "TRADING_LOG_FILE",
        "/opt/loop/lab/trading_log.json",
    ))


def _resolve_friction() -> tuple[float, float]:
    try:
        slippage = float(os.getenv("FRICTION_SLIPPAGE_PP", "0.005"))
    except (ValueError, TypeError):
        slippage = 0.005
    try:
        fee = float(os.getenv("FRICTION_FEE_PP", "0.0"))
    except (ValueError, TypeError):
        fee = 0.0
    return slippage, fee


def main() -> int:
    path = _resolve_trading_log()
    if not path.exists():
        print(f"[refriction] {path} not found.")
        return 0

    backup = path.with_suffix(path.suffix + ".pre-friction.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"[refriction] backed up to {backup}")
    else:
        print(f"[refriction] backup already exists at {backup} — not overwriting")

    raw = json.loads(path.read_text())
    trades = raw.get("trades", [])

    slippage_pp, fee_pp = _resolve_friction()
    print(f"[refriction] applying slippage_pp={slippage_pp}, fee_pp={fee_pp}")

    old_wins = 0
    old_losses = 0
    new_wins = 0
    new_losses = 0
    re_evaluated = 0
    skipped = 0

    for trade in trades:
        if not trade.get("success"):
            continue
        # Only re-evaluate trades that were previously evaluated
        # (have a price_at_evaluation). Pending trades stay pending.
        eval_price = trade.get("price_at_evaluation")
        if eval_price is None:
            skipped += 1
            continue

        entry = trade.get("price_at_entry", 0.0)
        size = trade.get("size_usdc", 0.0)
        side = trade.get("side", "")
        if entry <= 0 or size <= 0 or side not in ("BUY", "SELL"):
            skipped += 1
            continue

        # Track the old result
        old_result = trade.get("result")
        if old_result == "win":
            old_wins += 1
        elif old_result == "loss":
            old_losses += 1

        # Recompute with friction
        price_delta = eval_price - entry
        if side == "BUY":
            effective_delta = price_delta - slippage_pp - fee_pp
        else:  # SELL
            effective_delta = -price_delta - slippage_pp - fee_pp
        pnl = (effective_delta / entry) * size
        new_result = "win" if pnl >= 0 else "loss"

        trade["pnl"] = round(pnl, 4)
        trade["result"] = new_result
        trade["slippage_pp"] = slippage_pp
        trade["fee_pp"] = fee_pp

        if new_result == "win":
            new_wins += 1
        else:
            new_losses += 1
        re_evaluated += 1

    raw["trades"] = trades
    # Atomic write (S42 Phase 2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(raw, indent=2))
    os.replace(tmp, path)

    old_total = old_wins + old_losses
    new_total = new_wins + new_losses
    old_wr = (100.0 * old_wins / old_total) if old_total else 0.0
    new_wr = (100.0 * new_wins / new_total) if new_total else 0.0

    print(f"[refriction] re-evaluated: {re_evaluated} trades (skipped {skipped})")
    print(f"[refriction] old: {old_wins}W / {old_losses}L  win rate {old_wr:.2f}%")
    print(f"[refriction] new: {new_wins}W / {new_losses}L  win rate {new_wr:.2f}%")
    print(f"[refriction] delta: {old_wr:.2f}% -> {new_wr:.2f}%  ({new_wr - old_wr:+.2f}pp)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
