#!/usr/bin/env python3
"""
eval/migrate_outcomes_to_resolution.py
======================================
One-shot migration: clear the noise-labelled prediction outcomes so the S46
resolution-scoring evaluator can re-label them from scratch.

Why
---
S42-S45's lab/outcome_tracker.py:343-357 scored predictions against 4h/24h
price drift vs MIN_MOVE_THRESHOLD=0.0005 (sub-tick noise). At dd70650 the
DGX file had 692/774 records labelled by this broken instrument, producing
the 36% "accuracy" the brain entries call out as the broken-ruler-reading-
itself. S46 rebuilds the evaluator to score against Polymarket resolution
(YES/NO). The migration:

  - Backs up the current outcomes file to <path>.pre-s46-bak.
  - Clears `evaluated`, `outcome`, `price_at_evaluation`, `evaluated_at`,
    `actual_delta`, and the S46 fields (`resolution_status`,
    `resolved_outcome`, `outcome0_price_at_resolution`) on every record.
  - Zeros stats counters (correct, incorrect, neutral, total_evaluated,
    accuracy). Leaves `total_predictions` (a lifetime counter).
  - Wipes per_market (built from the noise labels).
  - Leaves the records themselves intact — first truth-board fire after
    deploy re-scores each one against gamma.

Run
---
    python3 -m eval.migrate_outcomes_to_resolution           # uses OUTCOMES_FILE env
    python3 -m eval.migrate_outcomes_to_resolution --dry-run # report, no write
    OUTCOMES_FILE=/tmp/x.json python3 -m eval.migrate_outcomes_to_resolution
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


DEFAULT_OUTCOMES_FILE = "/opt/loop/data/prediction_outcomes.json"

S46_LABEL_FIELDS = (
    "evaluated",
    "outcome",
    "price_at_evaluation",
    "evaluated_at",
    "actual_delta",
    "resolution_status",
    "resolved_outcome",
    "outcome0_price_at_resolution",
)


def migrate(state_path: Path, dry_run: bool = False) -> dict:
    """Clear labels + back up. Returns a report dict."""
    if not state_path.exists():
        return {
            "ok": False, "reason": "file not found", "path": str(state_path),
        }

    with open(state_path, "r") as f:
        data = json.load(f)

    preds = data.get("predictions", [])
    stats = data.get("stats", {})
    per_market = data.get("per_market", {})

    pre_evaluated = sum(1 for p in preds if p.get("evaluated"))
    pre_correct = stats.get("correct", 0)
    pre_incorrect = stats.get("incorrect", 0)
    pre_neutral = stats.get("neutral", 0)
    pre_total = pre_correct + pre_incorrect

    if dry_run:
        return {
            "ok": True, "dry_run": True, "path": str(state_path),
            "records_total": len(preds),
            "records_evaluated_pre": pre_evaluated,
            "stats_pre": {
                "correct": pre_correct, "incorrect": pre_incorrect,
                "neutral": pre_neutral, "directional_total": pre_total,
                "accuracy": round(pre_correct / pre_total, 3) if pre_total else None,
            },
            "per_market_entries_pre": len(per_market),
        }

    # Backup
    backup_path = state_path.with_suffix(state_path.suffix + ".pre-s46-bak")
    shutil.copy2(state_path, backup_path)

    # Wipe label fields
    for p in preds:
        for k in S46_LABEL_FIELDS:
            if k == "evaluated":
                p[k] = False
            else:
                if k in p:
                    p[k] = None

    # Zero stats counters (keep total_predictions — lifetime counter)
    stats["correct"] = 0
    stats["incorrect"] = 0
    stats["neutral"] = 0
    stats["total_evaluated"] = 0
    stats["accuracy"] = 0.0

    # Wipe per_market
    data["per_market"] = {}
    data["predictions"] = preds
    data["stats"] = stats

    # Atomic write
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, state_path)

    return {
        "ok": True, "dry_run": False, "path": str(state_path),
        "backup_path": str(backup_path),
        "records_total": len(preds),
        "records_evaluated_pre": pre_evaluated,
        "records_evaluated_post": 0,
        "stats_pre": {
            "correct": pre_correct, "incorrect": pre_incorrect,
            "neutral": pre_neutral, "directional_total": pre_total,
            "accuracy_pre": round(pre_correct / pre_total, 3) if pre_total else None,
        },
        "per_market_entries_pre": len(per_market),
        "per_market_entries_post": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without writing")
    parser.add_argument("--path",
                        default=os.getenv("OUTCOMES_FILE", DEFAULT_OUTCOMES_FILE),
                        help="Path to prediction_outcomes.json")
    args = parser.parse_args()

    report = migrate(Path(args.path), dry_run=args.dry_run)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
