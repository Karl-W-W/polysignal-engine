#!/usr/bin/env python3
"""
lab/cleanup_outcomes_pollution.py
=================================
One-shot cleanup: remove test-fixture pollution from data/prediction_outcomes.json.

Companion to lab/cleanup_trading_log.py from S41. The same import-time
OUTCOMES_FILE capture bug that bled 0xfake_* test rows into trading_log.json
also bled them into prediction_outcomes.json. Phase 1 of S42 closed the
mechanism; this cleans the data.

Behaviour:
- Loads /opt/loop/data/prediction_outcomes.json (or $OUTCOMES_FILE).
- Filters predictions where market_id starts with "0xfake_" or contains "fake".
- Recomputes stats (total_predictions, total_evaluated, correct, incorrect,
  neutral, accuracy) from the cleaned predictions list.
- Recomputes per_market with the polluted entries removed.
- Writes the cleaned file atomically (S42 Phase 2 pattern).
- Prints before/after counts and the new lifetime accuracy figure.

Idempotent: a second run with no remaining 0xfake_ rows is a no-op.

Run-once. Does NOT push to git. Does NOT restart the scanner.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def _is_fake(mid: str) -> bool:
    s = str(mid or "")
    return s.startswith("0xfake") or "fake" in s


def _resolve_outcomes_file() -> Path:
    return Path(os.getenv(
        "OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"
    ))


def _recompute_stats(preds: list[dict]) -> dict:
    total = len(preds)
    evaluated = [p for p in preds if p.get("evaluated")]
    correct = sum(1 for p in evaluated if p.get("outcome") == "CORRECT")
    incorrect = sum(1 for p in evaluated if p.get("outcome") == "INCORRECT")
    neutral = sum(1 for p in evaluated if p.get("outcome") == "NEUTRAL")
    directional = correct + incorrect
    accuracy = round(correct / directional, 4) if directional else 0.0
    return {
        "total_predictions": total,
        "total_evaluated": len(evaluated),
        "correct": correct,
        "incorrect": incorrect,
        "neutral": neutral,
        "accuracy": accuracy,
    }


def _recompute_per_market(preds: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for p in preds:
        if not p.get("evaluated"):
            continue
        mid = p.get("market_id")
        if mid is None or _is_fake(mid):
            continue
        bucket = out.setdefault(
            str(mid),
            {"correct": 0, "incorrect": 0, "neutral": 0, "title": p.get("title", "")},
        )
        outcome = p.get("outcome")
        if outcome == "CORRECT":
            bucket["correct"] += 1
        elif outcome == "INCORRECT":
            bucket["incorrect"] += 1
        else:
            bucket["neutral"] += 1
    return out


def main() -> int:
    path = _resolve_outcomes_file()
    if not path.exists():
        print(f"[cleanup] {path} not found — nothing to clean.")
        return 0

    raw = json.loads(path.read_text())
    preds_in = raw.get("predictions", [])
    real = [p for p in preds_in if not _is_fake(p.get("market_id", ""))]
    fakes_removed = len(preds_in) - len(real)

    if fakes_removed == 0:
        print(f"[cleanup] no 0xfake_ rows in {path} — already clean.")
        return 0

    new_stats = _recompute_stats(real)
    new_per_market = _recompute_per_market(real)
    cleaned = {
        "predictions": real,
        "stats": new_stats,
        "per_market": new_per_market,
    }

    # Atomic write (S42 Phase 2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cleaned, indent=2))
    os.replace(tmp, path)

    old_stats = raw.get("stats", {})
    print(f"[cleanup] file: {path}")
    print(f"[cleanup] removed {fakes_removed} 0xfake_ rows; kept {len(real)} real.")
    print(f"[cleanup] before stats: {old_stats}")
    print(f"[cleanup] after  stats: {new_stats}")
    old_acc = old_stats.get("accuracy", 0.0)
    new_acc = new_stats["accuracy"]
    print(f"[cleanup] lifetime directional accuracy: {old_acc:.4f} -> {new_acc:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
