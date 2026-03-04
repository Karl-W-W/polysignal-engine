#!/usr/bin/env python3
"""
lab/data_readiness.py
=====================
Phase 2 data monitor — reports when enough labeled predictions exist to train XGBoost.

Reads prediction_outcomes.json and reports:
- Total/evaluated/pending predictions
- Accuracy breakdown
- Estimated time to 50 labeled samples
- Ready/not-ready verdict

Usage:
    python3 -m lab.data_readiness
    python3 lab/data_readiness.py
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict

OUTCOMES_FILE = Path(os.getenv(
    "OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"
))

MIN_LABELED = 50  # Minimum evaluated predictions to start XGBoost training


def check_readiness(state_path: Path = OUTCOMES_FILE) -> Dict:
    """Check if we have enough labeled data for XGBoost training.

    Returns:
        Dict with stats and ready: bool (True when >= MIN_LABELED evaluated).
    """
    if not state_path.exists():
        return {
            "ready": False,
            "total_predictions": 0,
            "real_predictions": 0,
            "evaluated": 0,
            "pending": 0,
            "correct": 0,
            "incorrect": 0,
            "neutral": 0,
            "accuracy": 0.0,
            "needed": MIN_LABELED,
            "estimated_hours_to_ready": None,
            "horizon_distribution": {},
            "error": "No predictions file found",
        }

    with open(state_path) as f:
        data = json.load(f)

    predictions = data.get("predictions", [])
    stats = data.get("stats", {})

    real = [p for p in predictions if not p.get("market_id", "").startswith("0xfake")]
    evaluated = [p for p in real if p.get("evaluated")]
    pending = [p for p in real if not p.get("evaluated")]

    correct = sum(1 for p in evaluated if p.get("outcome") == "CORRECT")
    incorrect = sum(1 for p in evaluated if p.get("outcome") == "INCORRECT")
    neutral = sum(1 for p in evaluated if p.get("outcome") == "NEUTRAL")
    directional = correct + incorrect
    accuracy = correct / directional if directional > 0 else 0.0

    # Horizon distribution
    horizons = {}
    for p in real:
        h = p.get("time_horizon", "4h")
        horizons[h] = horizons.get(h, 0) + 1

    # Estimate time to MIN_LABELED evaluated
    estimated_hours = None
    if len(evaluated) < MIN_LABELED and len(real) > 0:
        # Calculate accumulation rate from timestamps
        timestamps = sorted(
            datetime.fromisoformat(p["timestamp"])
            for p in real if p.get("timestamp")
        )
        if len(timestamps) >= 2:
            span = (timestamps[-1] - timestamps[0]).total_seconds() / 3600
            if span > 0:
                rate_per_hour = len(real) / span
                still_needed = MIN_LABELED - len(evaluated)
                # Predictions need their horizon to elapse before evaluation
                avg_horizon_hours = _avg_horizon_hours(pending)
                estimated_hours = round(still_needed / max(rate_per_hour, 0.1) + avg_horizon_hours, 1)

    return {
        "ready": len(evaluated) >= MIN_LABELED,
        "total_predictions": len(predictions),
        "real_predictions": len(real),
        "evaluated": len(evaluated),
        "pending": len(pending),
        "correct": correct,
        "incorrect": incorrect,
        "neutral": neutral,
        "accuracy": round(accuracy, 3),
        "needed": max(0, MIN_LABELED - len(evaluated)),
        "estimated_hours_to_ready": estimated_hours,
        "horizon_distribution": horizons,
    }


def _avg_horizon_hours(predictions: list) -> float:
    """Average time horizon in hours for pending predictions."""
    horizon_map = {"1h": 1, "4h": 4, "24h": 24, "7d": 168}
    if not predictions:
        return 4.0
    total = sum(horizon_map.get(p.get("time_horizon", "4h"), 4) for p in predictions)
    return total / len(predictions)


def format_report(result: Dict) -> str:
    """Format check_readiness() output as a human-readable report."""
    lines = []
    lines.append("=" * 50)
    lines.append("  PolySignal-OS — Data Readiness Report")
    lines.append("=" * 50)

    status = "READY" if result["ready"] else "NOT READY"
    lines.append(f"\n  Status: {status}")
    lines.append(f"  Total predictions: {result['total_predictions']} "
                 f"({result['real_predictions']} real)")
    lines.append(f"  Evaluated: {result['evaluated']}")
    lines.append(f"  Pending: {result['pending']}")

    if result["evaluated"] > 0:
        lines.append(f"\n  Accuracy: {result['accuracy']:.1%}")
        lines.append(f"    Correct: {result['correct']}")
        lines.append(f"    Incorrect: {result['incorrect']}")
        lines.append(f"    Neutral: {result['neutral']}")

    if result.get("horizon_distribution"):
        lines.append(f"\n  Horizons: {result['horizon_distribution']}")

    if not result["ready"]:
        lines.append(f"\n  Need {result['needed']} more evaluated predictions")
        if result.get("estimated_hours_to_ready"):
            lines.append(f"  Estimated time: ~{result['estimated_hours_to_ready']}h")

    if result["ready"]:
        lines.append("\n  >>> Run: from lab.xgboost_baseline import train_model")
        lines.append("  >>> train_model()")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    result = check_readiness()
    print(format_report(result))
