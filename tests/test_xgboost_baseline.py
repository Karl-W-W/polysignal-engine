#!/usr/bin/env python3
"""
tests/test_xgboost_baseline.py
===============================
Tests for lab/xgboost_baseline.py — Phase 2 XGBoost training pipeline.
"""

import json
import os
import pickle
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lab.feature_engineering import FeatureVector
from lab.xgboost_baseline import (
    prepare_training_data,
    train_model,
    load_model,
    predict_single,
    predict_batch,
    TrainingResult,
    ModelPrediction,
    MIN_SAMPLES,
    TRAINABLE_LABELS,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_feature_vector(label: str, actual_delta: float = 0.05,
                         price: float = 0.55, market_id: str = "0xtest") -> FeatureVector:
    """Create a FeatureVector with realistic values for testing."""
    return FeatureVector(
        market_id=market_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        price=price,
        price_delta_1h=actual_delta * 0.3,
        price_delta_4h=actual_delta * 0.7,
        price_delta_24h=actual_delta,
        price_volatility_1h=abs(actual_delta) * 0.5,
        price_volatility_24h=abs(actual_delta) * 1.2,
        volume_24h=100000 + np.random.randint(0, 50000),
        volume_log=11.5 + np.random.random(),
        volume_delta_pct=np.random.uniform(-0.1, 0.1),
        price_acceleration=actual_delta * 0.1,
        trend_strength=abs(actual_delta) / max(abs(actual_delta) * 1.2, 0.001),
        mean_reversion_score=np.random.uniform(-1, 1),
        price_distance_from_50=abs(price - 0.5),
        observation_count=np.random.randint(10, 200),
        hours_since_first_obs=np.random.uniform(24, 168),
        observation_density=np.random.uniform(1, 10),
        signal_count_1h=np.random.randint(0, 3),
        signal_count_24h=np.random.randint(0, 10),
        max_signal_confidence=np.random.uniform(0.5, 0.9),
        label=label,
        actual_delta=actual_delta,
    )


@pytest.fixture
def labeled_dataset():
    """Create a labeled dataset with enough samples for training."""
    np.random.seed(42)
    dataset = []
    # Generate CORRECT samples (positive delta, bullish features)
    for _ in range(25):
        delta = np.random.uniform(0.03, 0.15)
        dataset.append(_make_feature_vector("CORRECT", delta, price=0.5 + delta))
    # Generate INCORRECT samples (negative outcomes)
    for _ in range(25):
        delta = np.random.uniform(-0.15, -0.03)
        dataset.append(_make_feature_vector("INCORRECT", delta, price=0.5 + delta))
    return dataset


@pytest.fixture
def small_dataset():
    """Dataset too small for training."""
    return [
        _make_feature_vector("CORRECT", 0.05),
        _make_feature_vector("INCORRECT", -0.03),
    ]


@pytest.fixture
def mixed_dataset():
    """Dataset with NEUTRAL labels (should be filtered out)."""
    np.random.seed(42)
    dataset = []
    for _ in range(20):
        dataset.append(_make_feature_vector("CORRECT", np.random.uniform(0.03, 0.1)))
    for _ in range(20):
        dataset.append(_make_feature_vector("INCORRECT", np.random.uniform(-0.1, -0.03)))
    for _ in range(10):
        dataset.append(_make_feature_vector("NEUTRAL", 0.001))
    return dataset


@pytest.fixture
def temp_model_dir(tmp_path):
    """Temporary directory for model storage."""
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    return model_dir


@pytest.fixture
def temp_db():
    """Create a temp SQLite DB with observations for inference testing."""
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
    for i in range(24):
        ts = (now - timedelta(hours=23 - i)).isoformat()
        price = 0.50 + (i * 0.01)
        conn.execute(
            "INSERT INTO observations (market_id, title, price, volume, timestamp, raw_data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("0xtest_market", "Test BTC", price, 100000, ts, "{}")
        )
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


# ── prepare_training_data ────────────────────────────────────────────────────

class TestPrepareTrainingData:
    def test_basic_conversion(self, labeled_dataset):
        X, y, names = prepare_training_data(labeled_dataset)
        assert X.shape == (50, len(names))
        assert y.shape == (50,)
        assert set(y.tolist()) == {0, 1}

    def test_filters_neutral(self, mixed_dataset):
        X, y, names = prepare_training_data(mixed_dataset)
        # 20 CORRECT + 20 INCORRECT = 40 (10 NEUTRAL dropped)
        assert X.shape[0] == 40

    def test_empty_dataset(self):
        X, y, names = prepare_training_data([])
        assert len(X) == 0
        assert len(y) == 0

    def test_label_encoding(self, labeled_dataset):
        X, y, names = prepare_training_data(labeled_dataset)
        # First 25 are CORRECT=1, last 25 are INCORRECT=0
        assert y[:25].sum() == 25
        assert y[25:].sum() == 0

    def test_feature_count_matches(self, labeled_dataset):
        X, y, names = prepare_training_data(labeled_dataset)
        fv = labeled_dataset[0]
        assert len(names) == len(fv.feature_names())
        assert X.shape[1] == len(fv.feature_names())

    def test_dtype_float32(self, labeled_dataset):
        X, y, names = prepare_training_data(labeled_dataset)
        assert X.dtype == np.float32
        assert y.dtype == np.int32


# ── train_model ──────────────────────────────────────────────────────────────

class TestTrainModel:
    def test_trains_successfully(self, labeled_dataset, temp_model_dir):
        with patch("lab.xgboost_baseline.MODEL_DIR", temp_model_dir), \
             patch("lab.xgboost_baseline.MODEL_PATH", temp_model_dir / "model.pkl"), \
             patch("lab.xgboost_baseline.METRICS_PATH", temp_model_dir / "metrics.json"):
            result = train_model(dataset=labeled_dataset)

        assert isinstance(result, TrainingResult)
        assert result.samples_total == 50
        assert 0.0 <= result.accuracy <= 1.0
        assert 0.0 <= result.precision_correct <= 1.0
        assert 0.0 <= result.recall_correct <= 1.0
        assert result.feature_importance  # Non-empty

    def test_saves_model_file(self, labeled_dataset, temp_model_dir):
        model_path = temp_model_dir / "model.pkl"
        metrics_path = temp_model_dir / "metrics.json"

        with patch("lab.xgboost_baseline.MODEL_DIR", temp_model_dir), \
             patch("lab.xgboost_baseline.MODEL_PATH", model_path), \
             patch("lab.xgboost_baseline.METRICS_PATH", metrics_path):
            train_model(dataset=labeled_dataset)

        assert model_path.exists()
        assert metrics_path.exists()

        # Verify model is loadable
        with open(model_path, "rb") as f:
            data = pickle.load(f)
        assert "model" in data
        assert "feature_names" in data

    def test_saves_metrics_json(self, labeled_dataset, temp_model_dir):
        metrics_path = temp_model_dir / "metrics.json"

        with patch("lab.xgboost_baseline.MODEL_DIR", temp_model_dir), \
             patch("lab.xgboost_baseline.MODEL_PATH", temp_model_dir / "model.pkl"), \
             patch("lab.xgboost_baseline.METRICS_PATH", metrics_path):
            train_model(dataset=labeled_dataset)

        with open(metrics_path) as f:
            metrics = json.load(f)
        assert "accuracy" in metrics
        assert "cv_accuracy_mean" in metrics
        assert "trained_at" in metrics

    def test_rejects_small_dataset(self, small_dataset):
        with pytest.raises(ValueError, match="Insufficient training data"):
            train_model(dataset=small_dataset, save=False)

    def test_no_save_mode(self, labeled_dataset, temp_model_dir):
        model_path = temp_model_dir / "model.pkl"
        with patch("lab.xgboost_baseline.MODEL_PATH", model_path):
            result = train_model(dataset=labeled_dataset, save=False)
        assert not model_path.exists()
        assert isinstance(result, TrainingResult)

    def test_feature_importance_sorted(self, labeled_dataset):
        result = train_model(dataset=labeled_dataset, save=False)
        importances = list(result.feature_importance.values())
        # Should be sorted descending
        assert importances == sorted(importances, reverse=True)

    def test_cross_validation_runs(self, labeled_dataset):
        result = train_model(dataset=labeled_dataset, save=False)
        assert result.cv_accuracy_mean > 0
        assert result.cv_accuracy_std >= 0

    def test_production_readiness_flag(self, labeled_dataset):
        result = train_model(dataset=labeled_dataset, save=False)
        # With only 50 samples and synthetic data, may or may not be ready
        # but the flag logic should work
        if result.accuracy > 0.55 and result.samples_total >= 50:
            assert result.ready_for_production is True
        else:
            assert result.ready_for_production is False


# ── load_model ───────────────────────────────────────────────────────────────

class TestLoadModel:
    def test_load_saved_model(self, labeled_dataset, temp_model_dir):
        model_path = temp_model_dir / "model.pkl"

        with patch("lab.xgboost_baseline.MODEL_DIR", temp_model_dir), \
             patch("lab.xgboost_baseline.MODEL_PATH", model_path), \
             patch("lab.xgboost_baseline.METRICS_PATH", temp_model_dir / "metrics.json"):
            train_model(dataset=labeled_dataset)

        model, feature_names = load_model(model_path)
        assert model is not None
        assert len(feature_names) > 0

    def test_missing_model_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No trained model"):
            load_model(tmp_path / "nonexistent.pkl")


# ── predict_single ───────────────────────────────────────────────────────────

class TestPredictSingle:
    def test_prediction_output(self, labeled_dataset, temp_model_dir, temp_db):
        model_path = temp_model_dir / "model.pkl"

        with patch("lab.xgboost_baseline.MODEL_DIR", temp_model_dir), \
             patch("lab.xgboost_baseline.MODEL_PATH", model_path), \
             patch("lab.xgboost_baseline.METRICS_PATH", temp_model_dir / "metrics.json"):
            train_model(dataset=labeled_dataset)

        pred = predict_single(
            "0xtest_market",
            hypothesis_direction="Bullish",
            db_path=temp_db,
            model_path=model_path,
        )
        assert isinstance(pred, ModelPrediction)
        assert pred.market_id == "0xtest_market"
        assert pred.hypothesis == "Bullish"
        assert 0.0 <= pred.confidence <= 1.0
        assert "XGBoost v1" in pred.reasoning

    def test_bearish_prediction(self, labeled_dataset, temp_model_dir, temp_db):
        model_path = temp_model_dir / "model.pkl"

        with patch("lab.xgboost_baseline.MODEL_DIR", temp_model_dir), \
             patch("lab.xgboost_baseline.MODEL_PATH", model_path), \
             patch("lab.xgboost_baseline.METRICS_PATH", temp_model_dir / "metrics.json"):
            train_model(dataset=labeled_dataset)

        pred = predict_single(
            "0xtest_market",
            hypothesis_direction="Bearish",
            db_path=temp_db,
            model_path=model_path,
        )
        assert pred.hypothesis == "Bearish"


# ── predict_batch ────────────────────────────────────────────────────────────

class TestPredictBatch:
    def test_batch_predictions(self, labeled_dataset, temp_model_dir, temp_db):
        model_path = temp_model_dir / "model.pkl"

        with patch("lab.xgboost_baseline.MODEL_DIR", temp_model_dir), \
             patch("lab.xgboost_baseline.MODEL_PATH", model_path), \
             patch("lab.xgboost_baseline.METRICS_PATH", temp_model_dir / "metrics.json"):
            train_model(dataset=labeled_dataset)

        observations = [
            {"market_id": "0xtest_market", "title": "Test", "delta": 0.05},
            {"market_id": "0xtest_market", "title": "Test2", "delta": -0.03},
        ]
        preds = predict_batch(observations, db_path=temp_db, model_path=model_path)
        assert len(preds) == 2
        assert preds[0].hypothesis == "Bullish"   # positive delta
        assert preds[1].hypothesis == "Bearish"    # negative delta

    def test_batch_skips_missing_market_id(self, labeled_dataset, temp_model_dir, temp_db):
        model_path = temp_model_dir / "model.pkl"

        with patch("lab.xgboost_baseline.MODEL_DIR", temp_model_dir), \
             patch("lab.xgboost_baseline.MODEL_PATH", model_path), \
             patch("lab.xgboost_baseline.METRICS_PATH", temp_model_dir / "metrics.json"):
            train_model(dataset=labeled_dataset)

        observations = [
            {"title": "No market_id"},
            {"market_id": "0xtest_market", "title": "Has ID", "delta": 0.01},
        ]
        preds = predict_batch(observations, db_path=temp_db, model_path=model_path)
        assert len(preds) == 1

    def test_batch_confidence_clamped(self, labeled_dataset, temp_model_dir, temp_db):
        model_path = temp_model_dir / "model.pkl"

        with patch("lab.xgboost_baseline.MODEL_DIR", temp_model_dir), \
             patch("lab.xgboost_baseline.MODEL_PATH", model_path), \
             patch("lab.xgboost_baseline.METRICS_PATH", temp_model_dir / "metrics.json"):
            train_model(dataset=labeled_dataset)

        observations = [{"market_id": "0xtest_market", "delta": 0.0}]
        preds = predict_batch(observations, db_path=temp_db, model_path=model_path)
        assert 0.1 <= preds[0].confidence <= 0.95

    def test_batch_empty_observations(self, labeled_dataset, temp_model_dir, temp_db):
        model_path = temp_model_dir / "model.pkl"

        with patch("lab.xgboost_baseline.MODEL_DIR", temp_model_dir), \
             patch("lab.xgboost_baseline.MODEL_PATH", model_path), \
             patch("lab.xgboost_baseline.METRICS_PATH", temp_model_dir / "metrics.json"):
            train_model(dataset=labeled_dataset)

        preds = predict_batch([], db_path=temp_db, model_path=model_path)
        assert preds == []


# ── Data Types ───────────────────────────────────────────────────────────────

class TestDataTypes:
    def test_training_result_to_dict(self):
        result = TrainingResult(
            model_path="/tmp/model.pkl",
            samples_total=100,
            samples_train=80,
            samples_test=20,
            accuracy=0.75,
            precision_correct=0.80,
            recall_correct=0.70,
            f1_correct=0.75,
            cv_accuracy_mean=0.73,
            cv_accuracy_std=0.05,
            feature_importance={"price": 0.3, "volume_log": 0.2},
            trained_at="2026-03-04T00:00:00+00:00",
            ready_for_production=True,
        )
        d = result.to_dict()
        assert d["accuracy"] == 0.75
        assert d["ready_for_production"] is True

    def test_model_prediction_to_dict(self):
        pred = ModelPrediction(
            market_id="0x123",
            hypothesis="Bullish",
            confidence=0.85,
            reasoning="XGBoost v1: strong signal",
        )
        d = pred.to_dict()
        assert d["market_id"] == "0x123"
        assert d["model_version"] == "xgboost_baseline_v1"
