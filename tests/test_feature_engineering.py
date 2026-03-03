#!/usr/bin/env python3
"""
tests/test_feature_engineering.py
=================================
Tests for lab/feature_engineering.py — Phase 2 feature pipeline.
"""

import json
import math
import os
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lab.feature_engineering import (
    FeatureVector,
    extract_features,
    build_labeled_dataset,
    dataset_summary,
    export_csv,
    get_market_history,
    get_all_market_ids,
    _safe_std,
    _prices_in_window,
    _parse_ts,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_db():
    """Create a temp SQLite DB with observations table and sample data."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT,
            title TEXT,
            price REAL,
            volume REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            raw_data TEXT
        )
    """)

    now = datetime.now(timezone.utc)
    market_id = "0xtest_btc_100k"

    # Insert observations over 24 hours (one per hour)
    for i in range(24):
        ts = (now - timedelta(hours=23 - i)).isoformat()
        price = 0.50 + (i * 0.01)  # steadily rising from 0.50 to 0.73
        volume = 100000 + (i * 5000)
        raw = json.dumps({
            "direction": "📈" if i > 20 else None,
            "hypothesis": "Bullish" if i > 20 else "Neutral",
            "confidence": 0.8 if i > 20 else 0.0,
        })
        conn.execute(
            "INSERT INTO observations (market_id, title, price, volume, timestamp, raw_data) VALUES (?, ?, ?, ?, ?, ?)",
            (market_id, "BTC > 100k", price, volume, ts, raw)
        )

    # Second market with fewer observations
    for i in range(5):
        ts = (now - timedelta(hours=4 - i)).isoformat()
        conn.execute(
            "INSERT INTO observations (market_id, title, price, volume, timestamp, raw_data) VALUES (?, ?, ?, ?, ?, ?)",
            ("0xtest_eth", "ETH > 5k", 0.30 - (i * 0.02), 50000, ts, "{}")
        )

    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


@pytest.fixture
def temp_outcomes(tmp_path):
    """Create a temp outcomes file with labeled predictions."""
    now = datetime.now(timezone.utc)
    outcomes = {
        "predictions": [
            {
                "market_id": "0xtest_btc_100k",
                "hypothesis": "Bullish",
                "confidence": 0.75,
                "price_at_prediction": 0.55,
                "timestamp": (now - timedelta(hours=20)).isoformat(),
                "time_horizon": "4h",
                "cycle_number": 5,
                "evaluated": True,
                "outcome": "CORRECT",
                "price_at_evaluation": 0.62,
                "evaluated_at": (now - timedelta(hours=16)).isoformat(),
                "actual_delta": 0.07,
            },
            {
                "market_id": "0xtest_btc_100k",
                "hypothesis": "Bullish",
                "confidence": 0.60,
                "price_at_prediction": 0.65,
                "timestamp": (now - timedelta(hours=10)).isoformat(),
                "time_horizon": "4h",
                "cycle_number": 12,
                "evaluated": True,
                "outcome": "INCORRECT",
                "price_at_evaluation": 0.63,
                "evaluated_at": (now - timedelta(hours=6)).isoformat(),
                "actual_delta": -0.02,
            },
            {
                "market_id": "0xtest_eth",
                "hypothesis": "Bearish",
                "confidence": 0.70,
                "price_at_prediction": 0.30,
                "timestamp": (now - timedelta(hours=3)).isoformat(),
                "time_horizon": "1h",
                "cycle_number": 20,
                "evaluated": False,  # Not yet evaluated
            },
        ],
        "stats": {
            "total_predictions": 3,
            "total_evaluated": 2,
            "correct": 1,
            "incorrect": 1,
            "neutral": 0,
            "accuracy": 0.5,
        }
    }
    path = tmp_path / "outcomes.json"
    path.write_text(json.dumps(outcomes))
    return path


# ── Unit Tests ───────────────────────────────────────────────────────────────

class TestHelpers:
    def test_safe_std_empty(self):
        assert _safe_std([]) == 0.0

    def test_safe_std_single(self):
        assert _safe_std([42.0]) == 0.0

    def test_safe_std_known(self):
        # std of [2, 4, 4, 4, 5, 5, 7, 9] = 2.0 (sample std)
        result = _safe_std([2, 4, 4, 4, 5, 5, 7, 9])
        assert abs(result - 2.138) < 0.01

    def test_parse_ts_iso(self):
        ts = _parse_ts("2026-03-03T12:00:00+00:00")
        assert ts is not None
        assert ts.hour == 12

    def test_parse_ts_none(self):
        assert _parse_ts("") is None
        assert _parse_ts(None) is None


class TestFeatureVector:
    def test_feature_names_excludes_identity(self):
        fv = FeatureVector()
        names = fv.feature_names()
        assert "market_id" not in names
        assert "timestamp" not in names
        assert "label" not in names
        assert "price" in names
        assert "volume_log" in names

    def test_feature_values_length(self):
        fv = FeatureVector()
        assert len(fv.feature_names()) == len(fv.feature_values())

    def test_to_dict_roundtrip(self):
        fv = FeatureVector(market_id="0x123", price=0.55, label="CORRECT")
        d = fv.to_dict()
        assert d["market_id"] == "0x123"
        assert d["price"] == 0.55
        assert d["label"] == "CORRECT"


class TestFeatureExtraction:
    def test_extract_basic(self, temp_db):
        fv = extract_features("0xtest_btc_100k", db_path=temp_db)
        assert fv.market_id == "0xtest_btc_100k"
        assert fv.price > 0
        assert fv.observation_count == 24
        assert fv.volume_24h > 0
        assert fv.volume_log > 0

    def test_price_deltas_positive_trend(self, temp_db):
        """Price is steadily rising, so deltas should be positive."""
        fv = extract_features("0xtest_btc_100k", db_path=temp_db)
        assert fv.price_delta_24h > 0  # Rising market
        assert fv.price_delta_4h > 0

    def test_volatility_nonzero(self, temp_db):
        fv = extract_features("0xtest_btc_100k", db_path=temp_db)
        assert fv.price_volatility_24h > 0  # Prices vary

    def test_momentum_features(self, temp_db):
        fv = extract_features("0xtest_btc_100k", db_path=temp_db)
        assert fv.trend_strength >= 0  # Should be positive for trending market

    def test_market_structure(self, temp_db):
        fv = extract_features("0xtest_btc_100k", db_path=temp_db)
        assert fv.observation_count == 24
        assert fv.hours_since_first_obs > 20
        assert fv.observation_density > 0

    def test_signal_detection(self, temp_db):
        """Last 3 observations have signals (hours 21, 22, 23)."""
        fv = extract_features("0xtest_btc_100k", db_path=temp_db)
        assert fv.signal_count_24h >= 3
        assert fv.max_signal_confidence >= 0.8

    def test_empty_market(self, temp_db):
        fv = extract_features("0xNONEXISTENT", db_path=temp_db)
        assert fv.price == 0.0
        assert fv.observation_count == 0

    def test_sparse_market(self, temp_db):
        fv = extract_features("0xtest_eth", db_path=temp_db)
        assert fv.observation_count == 5
        assert fv.price > 0

    def test_price_distance_from_50(self, temp_db):
        fv = extract_features("0xtest_btc_100k", db_path=temp_db)
        assert fv.price_distance_from_50 == abs(fv.price - 0.5)


class TestLabeledDataset:
    def test_build_labeled(self, temp_db, temp_outcomes):
        dataset = build_labeled_dataset(
            db_path=temp_db, outcomes_path=temp_outcomes
        )
        # Should get 2 labeled samples (the evaluated ones)
        assert len(dataset) == 2
        labels = [fv.label for fv in dataset]
        assert "CORRECT" in labels
        assert "INCORRECT" in labels

    def test_actual_delta_populated(self, temp_db, temp_outcomes):
        dataset = build_labeled_dataset(
            db_path=temp_db, outcomes_path=temp_outcomes
        )
        for fv in dataset:
            assert fv.actual_delta is not None

    def test_no_outcomes_file(self, temp_db, tmp_path):
        dataset = build_labeled_dataset(
            db_path=temp_db,
            outcomes_path=tmp_path / "nonexistent.json"
        )
        assert dataset == []


class TestDatasetSummary:
    def test_empty(self):
        s = dataset_summary([])
        assert s["total"] == 0

    def test_with_data(self, temp_db, temp_outcomes):
        dataset = build_labeled_dataset(
            db_path=temp_db, outcomes_path=temp_outcomes
        )
        s = dataset_summary(dataset)
        assert s["total"] == 2
        assert s["labeled"] == 2
        assert s["unique_markets"] >= 1
        assert s["feature_count"] > 10
        assert s["ready_for_training"] is False  # Need 50+

    def test_ready_threshold(self):
        """50+ labeled samples should flag as ready."""
        fvs = [FeatureVector(label="CORRECT") for _ in range(51)]
        s = dataset_summary(fvs)
        assert s["ready_for_training"] is True


class TestExport:
    def test_csv_export(self, temp_db, temp_outcomes, tmp_path):
        dataset = build_labeled_dataset(
            db_path=temp_db, outcomes_path=temp_outcomes
        )
        csv_path = str(tmp_path / "features.csv")
        n = export_csv(dataset, csv_path)
        assert n == 2

        with open(csv_path) as f:
            lines = f.readlines()
        assert len(lines) == 3  # header + 2 rows
        assert "price" in lines[0]
        assert "label" in lines[0]

    def test_csv_empty(self, tmp_path):
        csv_path = str(tmp_path / "empty.csv")
        n = export_csv([], csv_path)
        assert n == 0


class TestDatabaseHelpers:
    def test_get_all_market_ids(self, temp_db):
        ids = get_all_market_ids(temp_db)
        assert "0xtest_btc_100k" in ids
        assert "0xtest_eth" in ids

    def test_get_market_history(self, temp_db):
        history = get_market_history("0xtest_btc_100k", temp_db)
        assert len(history) == 24
