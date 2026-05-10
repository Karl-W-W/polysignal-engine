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
def _resolve_outcomes_file() -> Path:
    """Resolve the outcomes-file path at call time, not import time.

    Phase 1, S42: previously the module-level constant
        OUTCOMES_FILE = Path(os.getenv("OUTCOMES_FILE", default))
    was captured at import, so any test that did monkeypatch.setenv after
    import had no effect — function defaults were already locked. That bug
    let test fixtures bleed 110 0xfake_btc rows into the prod outcomes
    file. Same pattern as the S41 fix on lab.polymarket_trader._DEFAULT_LOG_PATH.
    """
    return Path(os.getenv(
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

# Phase 6, S42 (S41 P1): per-category evaluation horizons. The 4h horizon
# default was producing 13% accuracy on 6-month political markets that crash
# 0.295 -> 0.035 on noise — the eval was scoring against short-horizon noise,
# not resolution. Routing by category gives each market type a horizon that
# matches the timescale on which the prediction is meaningful.
EVAL_HORIZONS_BY_CATEGORY = {
    "crypto": "4h",
    "sports": "24h",
    "politics": "7d",
    "default": "4h",
}

# Lightweight title-based classifier — no external API call. Used by
# observation factories (workflows.masterloop._signal_to_observation /
# _market_to_observation) and as a fallback when a prediction record lacks
# an explicit category.
_CATEGORY_KEYWORDS = {
    "crypto": (
        "btc", "bitcoin", "eth", "ethereum", "sol ", "solana", "doge", "ada ",
        "cardano", "xrp", "ripple", "crypto", "blockchain", "stablecoin",
    ),
    "sports": (
        "nfl", "nba", "mlb", "nhl", "epl", "uefa", "fifa",
        "super bowl", "world cup", "world series", "playoff", "champions",
        "champion", "championship", "olympics", "ufc", "boxing", "tennis",
        "soccer", "football", "basketball", "baseball", "hockey", "fight",
        "match", " vs ",
    ),
    "politics": (
        "election", "president", "senate", "senator", "house", "congress",
        "prime minister", " pm ", "vote", "ballot", "governor", "mayor",
        "democrat", "republican", "trump", "biden", "harris", "vance",
        "putin", "zelensky", "orban", "magyar", "primary", "midterm",
        "parliament", "minister", "secretary",
    ),
}


def classify_category(title: Optional[str]) -> str:
    """Best-effort category from market title. Returns one of:
    'crypto', 'sports', 'politics', or 'default'. Not perfect — the cost
    of a misclassified market is only that it gets the wrong eval horizon
    (4h default rather than 7d for politics). Phase 6, S42.
    """
    if not title:
        return "default"
    t = title.lower()
    for cat, kws in _CATEGORY_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return cat
    return "default"


def horizon_for_category(category: Optional[str]) -> str:
    """Resolve a horizon string ('4h' / '24h' / '7d') from a category."""
    cat = (category or "default").lower()
    return EVAL_HORIZONS_BY_CATEGORY.get(cat, EVAL_HORIZONS_BY_CATEGORY["default"])

# Minimum price change to count as a directional move (avoid noise)
# Session 23: Lowered from 0.02 → 0.01 (78% NEUTRAL at 2pp, only 51 samples)
# Session 37: Lowered from 0.01 → 0.003 because time_horizon was changed from
# 24h to 4h. At 4h, max observed delta was 0.0095 — zero predictions ever crossed
# 1pp. At 0.3pp (0.003), mid-range markets yield ~35 directional evals per batch.
MIN_MOVE_THRESHOLD = 0.0005  # 0.05pp (Session 39: was 0.3pp. Data shows accuracy 59.3%→60.5% AND 9x more samples. Matches Polymarket tick size floor.)


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
    # Phase 6, S42: per-category eval horizons. "category" is the bucket
    # (crypto/sports/politics/default); time_horizon is then resolved from it.
    # Older records lack this field — eval falls back to time_horizon.
    category: Optional[str] = None


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
        # Per-market accuracy tracking (persists across 500-record cap)
        self.per_market: Dict[str, Dict] = {}  # {market_id: {correct, incorrect, neutral, title}}

    def save(self, path: Optional[Path] = None):
        path = path or _resolve_outcomes_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Protect unevaluated predictions from rotation — they need time
        # to reach their evaluation horizon (4h/24h). Drop evaluated first
        # since their stats are preserved in per_market and stats dicts.
        MAX_RECORDS = 5000
        if len(self.predictions) > MAX_RECORDS:
            unevaluated = [p for p in self.predictions if not p.get("evaluated")]
            evaluated = [p for p in self.predictions if p.get("evaluated")]
            keep_evaluated = max(0, MAX_RECORDS - len(unevaluated))
            self.predictions = evaluated[-keep_evaluated:] + unevaluated
            # Hard cap: if unevaluated alone exceed limit, keep newest
            if len(self.predictions) > MAX_RECORDS:
                self.predictions = self.predictions[-MAX_RECORDS:]
        data = {
            "predictions": self.predictions,
            "stats": self.stats,
            "per_market": self.per_market,
        }
        # Atomic write: tmp file + os.replace. Prevents half-written JSON if
        # the process dies mid-write, and prevents readers from seeing a
        # partial file when truth_board (Phase 7) writes concurrently with
        # the masterloop (Phase 2, S42).
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "OutcomeState":
        path = path or _resolve_outcomes_file()
        state = cls()
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                state.predictions = data.get("predictions", [])
                # Merge into defaults so partial on-disk stats (e.g. a 5-key
                # dict missing "neutral") don't replace the full default schema
                # and KeyError later in evaluate_outcomes. Phase 0, S42.
                state.stats = {**state.stats, **data.get("stats", {})}
                state.per_market = data.get("per_market", {})
            except (json.JSONDecodeError, KeyError):
                pass
        return state


# ── Core Functions ───────────────────────────────────────────────────────────

def record_predictions(predictions: List[Dict], observations: List[Dict],
                       cycle_number: int = 0,
                       state_path: Optional[Path] = None) -> int:
    """Record predictions from the current cycle for later evaluation.

    Args:
        predictions: List of prediction dicts from predict_market_moves()
        observations: List of observation dicts (to get current prices)
        cycle_number: Current MasterLoop cycle number
        state_path: Path to outcomes JSON file

    Returns:
        Number of predictions recorded.
    """
    state_path = state_path or _resolve_outcomes_file()
    state = OutcomeState.load(state_path)

    # Build price + category lookup from observations.
    # Phase 6, S42: observations carry "category" set by perception; if absent
    # we classify from title here so old observation factories still work.
    prices: Dict[str, float] = {}
    categories: Dict[str, str] = {}
    for obs in observations:
        mid = obs.get("market_id")
        price = obs.get("current_price") or obs.get("price", 0.0)
        if mid and price:
            prices[mid] = price
            cat = obs.get("category") or classify_category(obs.get("title"))
            categories[mid] = cat

    recorded = 0
    now = datetime.now(timezone.utc).isoformat()

    for pred in predictions:
        market_id = pred.get("market_id")
        hypothesis = pred.get("hypothesis", "Neutral")
        confidence = pred.get("confidence", 0.0)
        # Phase 6, S42: explicit category on the prediction wins; else use
        # the observation lookup; else classify from title; else "default".
        category = (
            pred.get("category")
            or categories.get(market_id)
            or classify_category(pred.get("title"))
            or "default"
        )
        # Time horizon: explicit on the prediction wins; else routed by category.
        time_horizon = pred.get("time_horizon") or horizon_for_category(category)

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
            category=category,
        ))
        state.predictions.append(record)
        state.stats["total_predictions"] += 1
        recorded += 1

        # Session 39: Dual-horizon — also record a 24h evaluation for every
        # 4h prediction so we can compare which horizon produces better accuracy.
        if time_horizon == "4h":
            record_24h = dict(record)
            record_24h["time_horizon"] = "24h"
            state.predictions.append(record_24h)
            state.stats["total_predictions"] += 1

    state.save(state_path)
    return recorded


def evaluate_outcomes(current_observations: List[Dict],
                      state_path: Optional[Path] = None) -> Dict:
    """Evaluate past predictions against current prices.

    Args:
        current_observations: Latest observation dicts with current prices
        state_path: Path to outcomes JSON file

    Returns:
        Dict with evaluation summary: {evaluated, correct, incorrect, neutral, accuracy}
    """
    state_path = state_path or _resolve_outcomes_file()
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

        # Check if enough time has passed for this prediction's horizon.
        # Phase 6, S42: if the record has a category, route through it.
        # Otherwise fall back to the explicit time_horizon (legacy records).
        pred_time = datetime.fromisoformat(pred["timestamp"])
        category = pred.get("category")
        if category:
            horizon_key = horizon_for_category(category)
        else:
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

        # Track per-market accuracy (persists across 500-record cap)
        if market_id not in state.per_market:
            state.per_market[market_id] = {
                "correct": 0, "incorrect": 0, "neutral": 0,
                "title": pred.get("title", ""),
            }
        pm = state.per_market[market_id]
        if outcome == "CORRECT":
            pm["correct"] += 1
        elif outcome == "INCORRECT":
            pm["incorrect"] += 1
        else:
            pm["neutral"] += 1

    # Update stats
    state.stats["total_evaluated"] += evaluated_this_round
    state.stats["correct"] += correct
    state.stats["incorrect"] += incorrect
    # Defensive: belt-and-suspenders against partial stats dicts that survive
    # the load-merge above (Phase 0, S42).
    state.stats["neutral"] = state.stats.get("neutral", 0) + neutral

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


def get_accuracy_summary(state_path: Optional[Path] = None) -> str:
    """Return a one-line accuracy summary for memory/logging."""
    state_path = state_path or _resolve_outcomes_file()
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


def get_gated_accuracy(state_path: Optional[Path] = None) -> Dict:
    """Return accuracy split by pre-gate vs post-gate (xgb_p_correct present).

    Post-gate predictions have xgb_p_correct field set (Session 15+).
    Pre-gate predictions lack this field (all predictions before gate was wired).
    """
    state_path = state_path or _resolve_outcomes_file()
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


def get_per_market_accuracy(state_path: Optional[Path] = None) -> Dict:
    """Return accuracy breakdown per market_id.

    Uses persistent per_market stats that survive the 500-record cap.
    Falls back to scanning active predictions if per_market is empty.
    """
    state_path = state_path or _resolve_outcomes_file()
    state = OutcomeState.load(state_path)

    # Prefer persistent per_market stats (survives 500-record cap)
    if state.per_market:
        markets = {}
        for mid, pm in state.per_market.items():
            m = dict(pm)
            m["total"] = m["correct"] + m["incorrect"] + m["neutral"]
            directional = m["correct"] + m["incorrect"]
            m["accuracy"] = round(m["correct"] / directional, 3) if directional > 0 else 0.0
            markets[mid] = m
        return markets

    # Fallback: scan active predictions (only covers last 500)
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


def get_accuracy_by_horizon(state_path: Optional[Path] = None) -> Dict:
    """Return accuracy split by time horizon (4h vs 24h).

    Session 39: Dual-horizon evaluation — compare which horizon
    produces better accuracy so we can optimize over the next week.
    """
    state_path = state_path or _resolve_outcomes_file()
    state = OutcomeState.load(state_path)

    horizons: Dict[str, Dict] = {}
    for pred in state.predictions:
        if not pred.get("evaluated"):
            continue
        h = pred.get("time_horizon", DEFAULT_HORIZON)
        if h not in horizons:
            horizons[h] = {"correct": 0, "incorrect": 0, "neutral": 0, "total": 0}
        outcome = pred.get("outcome", "NEUTRAL")
        horizons[h]["total"] += 1
        if outcome == "CORRECT":
            horizons[h]["correct"] += 1
        elif outcome == "INCORRECT":
            horizons[h]["incorrect"] += 1
        else:
            horizons[h]["neutral"] += 1

    for h in horizons.values():
        directional = h["correct"] + h["incorrect"]
        h["accuracy"] = round(h["correct"] / directional, 3) if directional > 0 else 0.0

    return horizons
