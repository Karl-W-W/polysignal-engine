#!/usr/bin/env python3
"""
lab/recompute_outcomes_per_category.py
======================================
One-shot backfill: re-classify and (where applicable) re-evaluate every
prediction in data/prediction_outcomes.json under the new per-category
horizons (S42 Phase 6).

What it does:
- Snapshots: cp data/prediction_outcomes.json data/prediction_outcomes.json.pre-percat.bak
- For every prediction record:
    - If it lacks a `category` field, classify from `title` (or skip with default).
    - Re-derive `time_horizon` from category if absent.
- For every EVALUATED record, leave the existing CORRECT/INCORRECT/NEUTRAL
  in place (the evaluation already happened against an actual price; we don't
  re-fetch historical prices). Per-category accuracy can be reported from
  the existing outcome field, just bucketed by category.
- For UNEVALUATED records: the live evaluator (truth_board / masterloop) will
  pick up the new category-routed horizon on its next run.
- Reports per-category accuracy split for evaluated records.

Idempotent: a second run is a no-op for records that already have category.

Run-once. Does NOT push to git. Does NOT restart scanner.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

# Make lab.outcome_tracker importable when run from /opt/loop or repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lab.outcome_tracker import classify_category, horizon_for_category


def _resolve_outcomes_file() -> Path:
    return Path(os.getenv(
        "OUTCOMES_FILE",
        "/opt/loop/data/prediction_outcomes.json",
    ))


def main() -> int:
    path = _resolve_outcomes_file()
    if not path.exists():
        print(f"[recompute] {path} not found.")
        return 0

    backup = path.with_suffix(path.suffix + ".pre-percat.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"[recompute] backed up to {backup}")

    raw = json.loads(path.read_text())
    preds = raw.get("predictions", [])

    classified_now = 0
    horizon_changed = 0
    by_cat_eval = defaultdict(lambda: {"correct": 0, "incorrect": 0, "neutral": 0})

    for p in preds:
        existing_cat = p.get("category")
        if not existing_cat:
            cat = classify_category(p.get("title")) or "default"
            p["category"] = cat
            classified_now += 1
        else:
            cat = existing_cat

        # Backfill time_horizon from category for unevaluated records only.
        # Evaluated records keep their original horizon (the eval already happened).
        if not p.get("evaluated"):
            new_h = horizon_for_category(cat)
            if p.get("time_horizon") != new_h:
                p["time_horizon"] = new_h
                horizon_changed += 1

        # Bucket evaluated outcomes by category for the report
        if p.get("evaluated"):
            outcome = p.get("outcome")
            if outcome == "CORRECT":
                by_cat_eval[cat]["correct"] += 1
            elif outcome == "INCORRECT":
                by_cat_eval[cat]["incorrect"] += 1
            elif outcome == "NEUTRAL":
                by_cat_eval[cat]["neutral"] += 1

    raw["predictions"] = preds
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(raw, indent=2))
    os.replace(tmp, path)

    print(f"[recompute] classified {classified_now} records, "
          f"updated horizon on {horizon_changed} unevaluated records")
    print()
    print("Per-category accuracy (evaluated records):")
    print(f"  {'category':<10s} {'corr':>5s} {'incor':>5s} {'neut':>5s} "
          f"{'total':>6s} {'dir-acc':>8s}")
    for cat, d in sorted(by_cat_eval.items()):
        directional = d["correct"] + d["incorrect"]
        acc = (100.0 * d["correct"] / directional) if directional else 0.0
        total = directional + d["neutral"]
        print(f"  {cat:<10s} {d['correct']:>5d} {d['incorrect']:>5d} "
              f"{d['neutral']:>5d} {total:>6d} {acc:>7.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
