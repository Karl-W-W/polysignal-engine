#!/usr/bin/env python3
"""
lab/outcome_tracker.py
======================
Prediction outcome tracker — compares past predictions against actual price moves.

This module:
1. Stores predictions when they're made (record_prediction)
2. Checks whether past predictions were right (evaluate_outcomes)
3. Returns accuracy stats for the learning loop

The outcome data becomes labeled training data for Phase 2 (ML prediction).

Lab Promotion Protocol:
  1. Built in /lab
  2. Tests in tests/test_outcome_tracker.py
  3. Wire into masterloop after human approval
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# ── Configuration ────────────────────────────────────────────────────────────
OUTCOMES_FILE = Path(os.getenv(
    "OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"
))

# How long to wait before evaluating a prediction (must give market time to move)
EVAL_HORIZONS = {
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}
DEFAULT_HORIZON = "4h"

# Minimum price change to count as a directional move (avoid noise)
# Session 23: Lowered from 0.02 → 0.01 because 78% of outcomes were NEUTRAL
# at 2pp threshold, leaving only 51 training samples. At 1pp we get ~3x more
# labeled data without introducing pure noise (crypto markets regularly move 1pp).
MIN_MOVE_THRESHOLD = 0.01  # 1pp (was 2pp — too aggressive for quiet markets)


# ── Data Model ───────────────────────────────────────────────────────────────

@dataclass
class PredictionRecord:
    """A prediction snapshot for later evaluation."""
    market_id: str
    hypothesis: str          # "Bullish", "Bearish", "Neutral"
    confidence: float        # 0.0-1.0
    price_at_prediction: float
    timestamp: str           # ISO 8601 UTC
    time_horizon: str        # "1h", "4h", "24h", "7d"
    cycle_number: int = 0
    xgb_p_correct: Optional[float] = None  # XGBoost gate score (Session 19)
    evaluated: bool = False
    outcome: Optional[str] = None       # "CORRECT", "INCORRECT", "NEUTRAL"
    price_at_evaluation: Optional[float] = None
    evaluated_at: Optional[str] = None
    actual_delta: Optional[float] = None


# ── State Persistence ────────────────────────────────────────────────────────

class OutcomeState:
    """Persistent state: pending predictions + evaluated outcomes."""

    def __init__(self):
        self.predictions: List[Dict] = []
        self.stats = {
            "total_predictions": 0,
            "total_evaluated": 0,
            "correct": 0,
            "incorrect": 0,
            "neutral": 0,
            "accuracy": 0.0,
        }

    def save(self, path: Path = OUTCOMES_FILE):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "predictions": self.predictions[-500:],  # Cap at 500 records
            "stats": self.stats,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: Path = OUTCOMES_FILE) -> "OutcomeState":
        state = cls()
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                state.predictions = data.get("predictions", [])
                state.stats = data.get("stats", state.stats)
            except (json.JSONDecodeError, KeyError):
                pass
        return state


# ── Core Functions ───────────────────────────────────────────────────────────

def record_predictions(predictions: List[Dict], observations: List[Dict],
                       cycle_number: int = 0,
                       state_path: Path = OUTCOMES_FILE) -> int:
    """Record predictions from the current cycle for later evaluation.

    Args:
        predictions: List of prediction dicts from predict_market_moves()
        observations: List of observation dicts (to get current prices)
        cycle_number: Current MasterLoop cycle number
        state_path: Path to outcomes JSON file

    Returns:
        Number of predictions recorded.
    """
    state = OutcomeState.load(state_path)

    # Build price lookup from observations
    prices = {}
    for obs in observations:
        mid = obs.get("market_id")
        price = obs.get("current_price") or obs.get("price", 0.0)
        if mid and price:
            prices[mid] = price

    recorded = 0
    now = datetime.now(timezone.utc).isoformat()

    for pred in predictions:
        market_id = pred.get("market_id")
        hypothesis = pred.get("hypothesis", "Neutral")
        confidence = pred.get("confidence", 0.0)
        time_horizon = pred.get("time_horizon", DEFAULT_HORIZON)

        if not market_id or hypothesis == "Neutral":
            continue  # Don't track neutral predictions — no directional claim

        price = prices.get(market_id, 0.0)
        if price <= 0:
            continue

        record = asdict(PredictionRecord(
            market_id=market_id,
            hypothesis=hypothesis,
            confidence=confidence,
            price_at_prediction=price,
            timestamp=now,
            time_horizon=time_horizon,
            cycle_number=cycle_number,
            xgb_p_correct=pred.get("xgb_p_correct"),
        ))
        state.predictions.append(record)
        state.stats["total_predictions"] += 1
        recorded += 1

    state.save(state_path)
    return recorded


def evaluate_outcomes(current_observations: List[Dict],
                      state_path: Path = OUTCOMES_FILE) -> Dict:
    """Evaluate past predictions against current prices.

    Args:
        current_observations: Latest observation dicts with current prices
        state_path: Path to outcomes JSON file

    Returns:
        Dict with evaluation summary: {evaluated, correct, incorrect, neutral, accuracy}
    """
    state = OutcomeState.load(state_path)
    now = datetime.now(timezone.utc)

    # Build current price lookup
    current_prices = {}
    for obs in current_observations:
        mid = obs.get("market_id")
        price = obs.get("current_price") or obs.get("price", 0.0)
        if mid and price:
            current_prices[mid] = price

    evaluated_this_round = 0
    correct = 0
    incorrect = 0
    neutral = 0

    for pred in state.predictions:
        if pred.get("evaluated"):
            continue

        market_id = pred.get("market_id")
        if market_id not in current_prices:
            continue

        # Check if enough time has passed for this prediction's horizon
        pred_time = datetime.fromisoformat(pred["timestamp"])
        horizon_key = pred.get("time_horizon", DEFAULT_HORIZON)
        horizon_delta = EVAL_HORIZONS.get(horizon_key, EVAL_HORIZONS[DEFAULT_HORIZON])

        if now - pred_time < horizon_delta:
            continue  # Not yet time to evaluate

        # Evaluate
        price_then = pred["price_at_prediction"]
        price_now = current_prices[market_id]
        delta = price_now - price_then
        hypothesis = pred["hypothesis"]

        if abs(delta) < MIN_MOVE_THRESHOLD:
            outcome = "NEUTRAL"
            neutral += 1
        elif (hypothesis == "Bullish" and delta > 0) or \
             (hypothesis == "Bearish" and delta < 0):
            outcome = "CORRECT"
            correct += 1
        else:
            outcome = "INCORRECT"
            incorrect += 1

        pred["evaluated"] = True
        pred["outcome"] = outcome
        pred["price_at_evaluation"] = price_now
        pred["evaluated_at"] = now.isoformat()
        pred["actual_delta"] = round(delta, 4)
        evaluated_this_round += 1

    # Update stats
    state.stats["total_evaluated"] += evaluated_this_round
    state.stats["correct"] += correct
    state.stats["incorrect"] += incorrect
    state.stats["neutral"] += neutral

    directional = state.stats["correct"] + state.stats["incorrect"]
    if directional > 0:
        state.stats["accuracy"] = round(state.stats["correct"] / directional, 3)

    state.save(state_path)

    return {
        "evaluated": evaluated_this_round,
        "correct": correct,
        "incorrect": incorrect,
        "neutral": neutral,
        "accuracy": state.stats["accuracy"],
        "total_evaluated": state.stats["total_evaluated"],
        "total_predictions": state.stats["total_predictions"],
    }


def get_accuracy_summary(state_path: Path = OUTCOMES_FILE) -> str:
    """Return a one-line accuracy summary for memory/logging."""
    state = OutcomeState.load(state_path)
    s = state.stats
    if s["total_evaluated"] == 0:
        return "No predictions evaluated yet."
    return (
        f"Accuracy: {s['accuracy']:.0%} "
        f"({s['correct']}/{s['correct'] + s['incorrect']} directional, "
        f"{s['neutral']} neutral, "
        f"{s['total_predictions'] - s['total_evaluated']} pending)"
    )


def get_gated_accuracy(state_path: Path = OUTCOMES_FILE) -> Dict:
    """Return accuracy split by pre-gate vs post-gate (xgb_p_correct present).

    Post-gate predictions have xgb_p_correct field set (Session 15+).
    Pre-gate predictions lack this field (all predictions before gate was wired).
    """
    state = OutcomeState.load(state_path)

    pre_gate = {"correct": 0, "incorrect": 0, "neutral": 0, "total": 0}
    post_gate = {"correct": 0, "incorrect": 0, "neutral": 0, "total": 0}

    for pred in state.predictions:
        if not pred.get("evaluated"):
            continue

        bucket = post_gate if pred.get("xgb_p_correct") is not None else pre_gate
        outcome = pred.get("outcome", "NEUTRAL")
        bucket["total"] += 1
        if outcome == "CORRECT":
            bucket["correct"] += 1
        elif outcome == "INCORRECT":
            bucket["incorrect"] += 1
        else:
            bucket["neutral"] += 1

    for b in (pre_gate, post_gate):
        directional = b["correct"] + b["incorrect"]
        b["accuracy"] = round(b["correct"] / directional, 3) if directional > 0 else 0.0

    return {"pre_gate": pre_gate, "post_gate": post_gate}


def get_per_market_accuracy(state_path: Path = OUTCOMES_FILE) -> Dict:
    """Return accuracy breakdown per market_id.

    Enables identifying which markets are predictable vs unpredictable.
    Only includes evaluated predictions with directional outcomes.
    """
    state = OutcomeState.load(state_path)
    markets: Dict[str, Dict] = {}

    for pred in state.predictions:
        if not pred.get("evaluated"):
            continue
        mid = pred.get("market_id", "unknown")
        if mid not in markets:
            markets[mid] = {"correct": 0, "incorrect": 0, "neutral": 0, "total": 0}
        outcome = pred.get("outcome", "NEUTRAL")
        markets[mid]["total"] += 1
        if outcome == "CORRECT":
            markets[mid]["correct"] += 1
        elif outcome == "INCORRECT":
            markets[mid]["incorrect"] += 1
        else:
            markets[mid]["neutral"] += 1

    for m in markets.values():
        directional = m["correct"] + m["incorrect"]
        m["accuracy"] = round(m["correct"] / directional, 3) if directional > 0 else 0.0

    return markets
