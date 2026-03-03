#!/usr/bin/env python3
"""
lab/feature_engineering.py
==========================
Phase 2 ML Preparation — Feature Engineering Pipeline.

Transforms raw observations and prediction outcomes from the scanner
into structured feature vectors for ML model training.

Data Sources:
  - polysignal.db → observations table (1,293+ rows and growing)
  - prediction_outcomes.json → labeled predictions from outcome_tracker.py

Output:
  - Feature matrix (list of dicts or DataFrame-ready) with labels
  - Each row = one prediction with features computed from the observation window

Lab Promotion Protocol:
  1. Built in /lab ✅
  2. Tests in tests/test_feature_engineering.py
  3. Wire into masterloop after human approval + sufficient labeled data

Dependencies: stdlib only (no sklearn/pandas yet — keep sandbox-friendly)
"""

import json
import math
import os
import sqlite3
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ── Configuration ────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "/data/polysignal.db")
OUTCOMES_FILE = Path(os.getenv(
    "OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"
))


# ── Feature Schema ───────────────────────────────────────────────────────────

@dataclass
class FeatureVector:
    """One training sample: features extracted from market state at prediction time."""

    # Identity (not features — used for join/debug)
    market_id: str = ""
    timestamp: str = ""
    cycle_number: int = 0

    # Price features
    price: float = 0.0                    # Current implied probability (0-1)
    price_delta_1h: float = 0.0           # Price change over last hour
    price_delta_4h: float = 0.0           # Price change over last 4 hours
    price_delta_24h: float = 0.0          # Price change over last 24 hours
    price_volatility_1h: float = 0.0      # Std dev of price in last hour
    price_volatility_24h: float = 0.0     # Std dev of price in last 24 hours

    # Volume features
    volume_24h: float = 0.0               # Raw 24h volume
    volume_log: float = 0.0               # log(1 + volume) — normalised scale
    volume_delta_pct: float = 0.0         # % change in volume vs prior observation

    # Momentum features
    price_acceleration: float = 0.0       # delta_1h - delta_4h/4 (is momentum increasing?)
    trend_strength: float = 0.0           # |delta_24h| / volatility_24h (signal-to-noise)
    mean_reversion_score: float = 0.0     # distance from 24h mean / volatility

    # Market structure
    price_distance_from_50: float = 0.0   # |price - 0.5| — how resolved is the market?
    observation_count: int = 0            # How many observations we have for this market
    hours_since_first_obs: float = 0.0    # Market age in our DB
    observation_density: float = 0.0      # obs_count / hours — how frequently we're sampling

    # Signal features (from the scanner's detect_signals)
    signal_count_1h: int = 0              # Signals detected for this market in last hour
    signal_count_24h: int = 0             # Signals detected in last 24 hours
    max_signal_confidence: float = 0.0    # Highest confidence signal in window

    # Label (for supervised learning)
    label: Optional[str] = None           # "CORRECT", "INCORRECT", "NEUTRAL" or None
    actual_delta: Optional[float] = None  # Actual price move (for regression)

    def to_dict(self) -> dict:
        return asdict(self)

    def feature_names(self) -> List[str]:
        """Return only the numeric feature column names (exclude identity/label)."""
        exclude = {"market_id", "timestamp", "cycle_number", "label", "actual_delta"}
        return [k for k in asdict(self).keys() if k not in exclude]

    def feature_values(self) -> List[float]:
        """Return numeric feature values in consistent order."""
        d = self.to_dict()
        return [float(d[k]) if d[k] is not None else 0.0
                for k in self.feature_names()]


# ── Database Helpers ─────────────────────────────────────────────────────────

def _get_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_ts(ts_str: str) -> Optional[datetime]:
    """Parse various timestamp formats from the DB."""
    if not ts_str:
        return None
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%f+00:00",
        "%Y-%m-%dT%H:%M:%S+00:00",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]:
        try:
            dt = datetime.strptime(ts_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def get_market_history(market_id: str, db_path: str = DB_PATH,
                       hours_back: float = 48) -> List[Dict]:
    """Fetch observation history for a market, ordered by time."""
    conn = _get_db(db_path)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    rows = conn.execute(
        "SELECT * FROM observations WHERE market_id = ? AND timestamp > ? ORDER BY timestamp ASC",
        (market_id, cutoff)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_market_ids(db_path: str = DB_PATH) -> List[str]:
    """Get all unique market IDs in the DB."""
    conn = _get_db(db_path)
    rows = conn.execute("SELECT DISTINCT market_id FROM observations").fetchall()
    conn.close()
    return [r["market_id"] for r in rows]


def get_observation_stats(market_id: str, db_path: str = DB_PATH) -> Dict:
    """Quick stats: count, first/last timestamp for a market."""
    conn = _get_db(db_path)
    row = conn.execute(
        "SELECT COUNT(*) as cnt, MIN(timestamp) as first_ts, MAX(timestamp) as last_ts "
        "FROM observations WHERE market_id = ?",
        (market_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {"cnt": 0, "first_ts": None, "last_ts": None}


# ── Feature Extraction ───────────────────────────────────────────────────────

def _safe_std(values: List[float]) -> float:
    """Standard deviation with safety for empty/single-element lists."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _prices_in_window(history: List[Dict], ref_time: datetime,
                      hours: float) -> List[float]:
    """Extract prices from history within [ref_time - hours, ref_time]."""
    cutoff = ref_time - timedelta(hours=hours)
    prices = []
    for obs in history:
        ts = _parse_ts(obs.get("timestamp", ""))
        if ts and cutoff <= ts <= ref_time:
            p = obs.get("price", 0.0)
            if p and p > 0:
                prices.append(p)
    return prices


def _count_signals_in_window(history: List[Dict], ref_time: datetime,
                             hours: float) -> Tuple[int, float]:
    """Count observations with direction (signals) in time window. Returns (count, max_confidence)."""
    cutoff = ref_time - timedelta(hours=hours)
    count = 0
    max_conf = 0.0
    for obs in history:
        ts = _parse_ts(obs.get("timestamp", ""))
        if ts and cutoff <= ts <= ref_time:
            raw = obs.get("raw_data")
            if raw:
                try:
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    if data.get("direction") or data.get("hypothesis"):
                        count += 1
                        conf = float(data.get("confidence", 0.0))
                        max_conf = max(max_conf, conf)
                except (json.JSONDecodeError, TypeError):
                    pass
    return count, max_conf


def extract_features(market_id: str, ref_time: Optional[datetime] = None,
                     db_path: str = DB_PATH,
                     history: Optional[List[Dict]] = None) -> FeatureVector:
    """
    Extract a full feature vector for a market at a point in time.

    Args:
        market_id: Polymarket market ID
        ref_time: Point-in-time for feature extraction (default: now)
        db_path: Path to SQLite DB
        history: Pre-fetched history (avoids DB call if provided)

    Returns:
        FeatureVector with all computed features
    """
    if ref_time is None:
        ref_time = datetime.now(timezone.utc)

    if history is None:
        history = get_market_history(market_id, db_path, hours_back=48)

    if not history:
        return FeatureVector(market_id=market_id, timestamp=ref_time.isoformat())

    fv = FeatureVector(market_id=market_id, timestamp=ref_time.isoformat())

    # --- Price features ---
    prices_1h = _prices_in_window(history, ref_time, 1.0)
    prices_4h = _prices_in_window(history, ref_time, 4.0)
    prices_24h = _prices_in_window(history, ref_time, 24.0)

    # Current price = latest observation before ref_time
    latest_price = 0.0
    for obs in reversed(history):
        ts = _parse_ts(obs.get("timestamp", ""))
        if ts and ts <= ref_time:
            latest_price = obs.get("price", 0.0)
            break

    fv.price = latest_price

    if prices_1h and latest_price:
        fv.price_delta_1h = latest_price - prices_1h[0]
    if prices_4h and latest_price:
        fv.price_delta_4h = latest_price - prices_4h[0]
    if prices_24h and latest_price:
        fv.price_delta_24h = latest_price - prices_24h[0]

    fv.price_volatility_1h = _safe_std(prices_1h)
    fv.price_volatility_24h = _safe_std(prices_24h)

    # --- Volume features ---
    latest_volume = 0.0
    prev_volume = 0.0
    vol_seen = 0
    for obs in reversed(history):
        ts = _parse_ts(obs.get("timestamp", ""))
        if ts and ts <= ref_time:
            v = obs.get("volume", 0.0)
            if v and v > 0:
                if vol_seen == 0:
                    latest_volume = v
                elif vol_seen == 1:
                    prev_volume = v
                    break
                vol_seen += 1

    fv.volume_24h = latest_volume
    fv.volume_log = math.log1p(latest_volume)
    if prev_volume > 0:
        fv.volume_delta_pct = (latest_volume - prev_volume) / prev_volume

    # --- Momentum features ---
    avg_hourly_delta = fv.price_delta_4h / 4.0 if prices_4h else 0.0
    fv.price_acceleration = fv.price_delta_1h - avg_hourly_delta

    if fv.price_volatility_24h > 0:
        fv.trend_strength = abs(fv.price_delta_24h) / fv.price_volatility_24h
    else:
        fv.trend_strength = 0.0

    if prices_24h and fv.price_volatility_24h > 0:
        mean_24h = sum(prices_24h) / len(prices_24h)
        fv.mean_reversion_score = (latest_price - mean_24h) / fv.price_volatility_24h

    # --- Market structure ---
    fv.price_distance_from_50 = abs(latest_price - 0.5)

    stats = get_observation_stats(market_id, db_path)
    fv.observation_count = stats["cnt"]

    first_ts = _parse_ts(stats.get("first_ts", ""))
    if first_ts:
        fv.hours_since_first_obs = max(0.0,
            (ref_time - first_ts).total_seconds() / 3600.0)

    if fv.hours_since_first_obs > 0:
        fv.observation_density = fv.observation_count / fv.hours_since_first_obs

    # --- Signal features ---
    sig_1h, max_conf_1h = _count_signals_in_window(history, ref_time, 1.0)
    sig_24h, max_conf_24h = _count_signals_in_window(history, ref_time, 24.0)
    fv.signal_count_1h = sig_1h
    fv.signal_count_24h = sig_24h
    fv.max_signal_confidence = max(max_conf_1h, max_conf_24h)

    return fv


# ── Batch Feature Extraction ────────────────────────────────────────────────

def extract_all_features(db_path: str = DB_PATH) -> List[FeatureVector]:
    """Extract features for all markets at current time."""
    market_ids = get_all_market_ids(db_path)
    return [extract_features(mid, db_path=db_path) for mid in market_ids]


def build_labeled_dataset(db_path: str = DB_PATH,
                          outcomes_path: Path = OUTCOMES_FILE) -> List[FeatureVector]:
    """
    Build a labeled dataset by joining feature vectors with prediction outcomes.

    This is the key function for Phase 2: it produces the training data.
    Each row is a feature vector at the time a prediction was made,
    labeled with whether that prediction was CORRECT/INCORRECT.

    Returns:
        List of FeatureVectors with label and actual_delta populated
    """
    # Load outcomes
    if not outcomes_path.exists():
        return []

    with open(outcomes_path, "r") as f:
        data = json.load(f)

    predictions = data.get("predictions", [])
    evaluated = [p for p in predictions if p.get("evaluated")]

    if not evaluated:
        return []

    dataset = []
    # Cache histories to avoid repeated DB queries
    history_cache: Dict[str, List[Dict]] = {}

    for pred in evaluated:
        market_id = pred.get("market_id")
        if not market_id:
            continue

        # Parse prediction timestamp
        pred_time = _parse_ts(pred.get("timestamp", ""))
        if not pred_time:
            continue

        # Get or cache history
        if market_id not in history_cache:
            history_cache[market_id] = get_market_history(
                market_id, db_path, hours_back=72
            )

        # Extract features at the point-in-time of the prediction
        fv = extract_features(
            market_id,
            ref_time=pred_time,
            db_path=db_path,
            history=history_cache[market_id]
        )

        # Attach label
        fv.label = pred.get("outcome")  # CORRECT, INCORRECT, NEUTRAL
        fv.actual_delta = pred.get("actual_delta")
        fv.cycle_number = pred.get("cycle_number", 0)

        dataset.append(fv)

    return dataset


def dataset_summary(dataset: List[FeatureVector]) -> Dict:
    """Summary stats for a labeled dataset."""
    if not dataset:
        return {"total": 0, "labeled": 0, "message": "No data yet"}

    labels = [fv.label for fv in dataset if fv.label]
    label_counts = {}
    for l in labels:
        label_counts[l] = label_counts.get(l, 0) + 1

    unique_markets = len(set(fv.market_id for fv in dataset))
    deltas = [fv.actual_delta for fv in dataset if fv.actual_delta is not None]

    return {
        "total": len(dataset),
        "labeled": len(labels),
        "unlabeled": len(dataset) - len(labels),
        "label_distribution": label_counts,
        "unique_markets": unique_markets,
        "avg_actual_delta": sum(deltas) / len(deltas) if deltas else None,
        "feature_count": len(dataset[0].feature_names()) if dataset else 0,
        "ready_for_training": len(labels) >= 50,
        "message": (
            f"✅ {len(labels)} labeled samples across {unique_markets} markets. "
            f"{'Ready for Phase 2 training!' if len(labels) >= 50 else f'Need {50 - len(labels)} more labeled samples.'}"
        ),
    }


# ── Export for Training ──────────────────────────────────────────────────────

def export_csv(dataset: List[FeatureVector], output_path: str) -> int:
    """Export dataset to CSV for external ML tools (sklearn, etc.)."""
    if not dataset:
        return 0

    headers = dataset[0].feature_names() + ["label", "actual_delta"]

    with open(output_path, "w") as f:
        f.write(",".join(headers) + "\n")
        for fv in dataset:
            values = fv.feature_values()
            values.append(fv.label or "")
            values.append(str(fv.actual_delta) if fv.actual_delta is not None else "")
            f.write(",".join(str(v) for v in values) + "\n")

    return len(dataset)


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("PolySignal Feature Engineering — Phase 2 Data Pipeline")
    print("=" * 60)

    # Try labeled dataset first
    print(f"\nOutcomes file: {OUTCOMES_FILE}")
    print(f"Database: {DB_PATH}")

    dataset = build_labeled_dataset()
    summary = dataset_summary(dataset)
    print(f"\n📊 Dataset Summary:")
    for k, v in summary.items():
        print(f"   {k}: {v}")

    if dataset:
        # Show sample feature vector
        sample = dataset[0]
        print(f"\n📋 Sample Feature Vector ({sample.market_id[:20]}...):")
        for name, val in zip(sample.feature_names(), sample.feature_values()):
            print(f"   {name:30s} = {val:.6f}")
        print(f"   {'label':30s} = {sample.label}")
        print(f"   {'actual_delta':30s} = {sample.actual_delta}")

        # Export
        export_path = "/tmp/polysignal_features.csv"
        n = export_csv(dataset, export_path)
        print(f"\n💾 Exported {n} rows to {export_path}")
    else:
        # Fall back to current features (unlabeled)
        print("\nNo labeled data yet. Extracting current features...")
        features = extract_all_features()
        print(f"   Markets: {len(features)}")
        if features:
            sample = features[0]
            print(f"\n📋 Sample ({sample.market_id[:20]}...):")
            for name, val in zip(sample.feature_names(), sample.feature_values()):
                print(f"   {name:30s} = {val:.6f}")

    print("\n✅ Feature engineering pipeline ready.")
    print("   Waiting for outcome_tracker to accumulate 50+ labeled predictions.")
