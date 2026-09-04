#!/usr/bin/env python3
"""
lab/truth_board.py
==================
Standalone evaluation tick — extracts outcome resolution out of the masterloop
side-effect path so eval isolation no longer depends on perception_node
succeeding.

Intent (S42 Phase 7):
- Run on a systemd timer (Phase 8). Every 15 minutes, fetch the most recent
  observed price for every tracked market from data/test.db, then call the
  existing path-safe (Phase 1) evaluate_outcomes() and evaluate_paper_trades().
- Write a status file at lab/.truth-board-status.json so the watchdog
  (Phase 9) can detect stalls.

Why this exists:
The masterloop's perception_node embeds two eval calls inside a try/except
that prints to stdout and discards. When perception fails — empty observations,
gamma-api timeout, anything — eval silently dies with it. This module
decouples eval from perception, so a scanner crash or quiet-market window
no longer freezes Pillar 1.

This module does NOT yet replace the in-line eval in masterloop.py. Phase 11
removes that — only after truth_board has produced 48h of stable data
(per the spec).

Run-once via CLI: `python3 -m lab.truth_board`
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path when run as a module from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab.base_rate_predictor import read_suppression_counter  # noqa: E402
from lab.outcome_tracker import evaluate_outcomes, get_accuracy_summary  # noqa: E402
from lab.polymarket_trader import TradingLog  # noqa: E402


def _resolve_db_path() -> Path:
    return Path(os.getenv("DB_PATH", "/opt/loop/data/test.db"))


def _resolve_status_file() -> Path:
    return Path(os.getenv(
        "TRUTH_BOARD_STATUS_FILE",
        os.path.join(os.path.dirname(__file__), ".truth-board-status.json"),
    ))


def fetch_latest_observations(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Return the most recent observation per market_id as observation dicts.

    Used in place of state["observations"] from masterloop's perception_node.
    Reads from the same SQLite store the volatility gate already reads.
    """
    db_path = db_path or _resolve_db_path()
    if not db_path.exists():
        return []

    obs: List[Dict[str, Any]] = []
    try:
        # Read-only connection. WAL is enabled per S37 hardening.
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
        try:
            cur = conn.execute(
                """
                SELECT market_id, price, timestamp
                FROM observations o
                WHERE timestamp = (
                    SELECT MAX(timestamp) FROM observations
                    WHERE market_id = o.market_id
                )
                """
            )
            for row in cur.fetchall():
                mid, price, ts = row
                if mid is None or price is None:
                    continue
                obs.append({
                    "market_id": str(mid),
                    "current_price": float(price),
                    "price": float(price),
                    "timestamp": ts,
                    "source": "truth_board",
                })
        finally:
            conn.close()
    except Exception as e:
        # Surface as a status error rather than swallow.
        print(f"[truth_board] DB read failed: {e}", file=sys.stderr)
    return obs


def write_status(payload: Dict[str, Any], status_path: Optional[Path] = None) -> None:
    status_path = status_path or _resolve_status_file()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = status_path.with_suffix(status_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, status_path)


def run_once() -> Dict[str, Any]:
    """Single tick: fetch latest prices, evaluate outcomes + paper trades,
    write status file. Returns the status dict for caller introspection."""
    started = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    errors: List[str] = []
    eval_result: Dict[str, Any] = {}
    trade_eval: Dict[str, Any] = {}

    obs = fetch_latest_observations()
    if not obs:
        errors.append("no observations fetched from data/test.db")

    # Outcomes evaluation
    try:
        eval_result = evaluate_outcomes(obs)
    except Exception as e:
        errors.append(f"evaluate_outcomes: {e!r}")

    # Paper-trade evaluation (uses same current_prices map)
    try:
        current_prices = {o["market_id"]: o["current_price"] for o in obs}
        if current_prices:
            log = TradingLog()
            trade_eval = log.evaluate_paper_trades(current_prices)
    except Exception as e:
        errors.append(f"evaluate_paper_trades: {e!r}")

    elapsed_ms = int((time.time() - started) * 1000)
    status = {
        "timestamp": started_at,
        "elapsed_ms": elapsed_ms,
        "observations": len(obs),
        "evaluated_count": eval_result.get("evaluated", 0),
        "correct": eval_result.get("correct", 0),
        "incorrect": eval_result.get("incorrect", 0),
        "neutral": eval_result.get("neutral", 0),
        "accuracy_lifetime": eval_result.get("accuracy", 0.0),
        "trade_eval": trade_eval,
        # 2026-09-04 lever: cumulative Bullish calls swallowed by the
        # price<0.50 guard in lab/base_rate_predictor.py (0 if never fired).
        "bullish_below_price_suppressed": int(
            read_suppression_counter().get("bullish_below_price", 0) or 0
        ),
        "summary": get_accuracy_summary() if not errors else "",
        "errors": errors,
        "last_eval_age_minutes": 0,  # this run IS the last eval
    }
    write_status(status)
    return status


def main() -> int:
    status = run_once()
    err_str = ", ".join(status.get("errors", [])) or "none"
    print(
        f"[truth_board] obs={status['observations']} "
        f"evaluated={status['evaluated_count']} "
        f"correct={status['correct']} incorrect={status['incorrect']} "
        f"neutral={status['neutral']} "
        f"trade_eval={status['trade_eval']} "
        f"bullish_below_price_suppressed={status['bullish_below_price_suppressed']} "
        f"errors=[{err_str}] "
        f"elapsed={status['elapsed_ms']}ms"
    )
    return 0 if not status.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
