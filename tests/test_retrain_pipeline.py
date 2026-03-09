"""
tests/test_retrain_pipeline.py
===============================
Tests for lab/retrain_pipeline.py — XGBoost retrain pipeline.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from lab.retrain_pipeline import (
    retrain,
    load_retrain_history,
    save_retrain_history,
    get_current_metrics,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def history_file(tmp_path):
    return tmp_path / "retrain_history.json"


@pytest.fixture
def metrics_file(tmp_path):
    return tmp_path / "training_metrics.json"


# ============================================================================
# HISTORY PERSISTENCE
# ============================================================================

class TestRetrainHistory:
    def test_empty_history(self, tmp_path):
        with patch("lab.retrain_pipeline.HISTORY_PATH", tmp_path / "nonexistent.json"):
            h = load_retrain_history()
            assert h == []

    def test_save_and_load(self, history_file):
        entries = [{"action": "REPLACED", "accuracy": 0.92}]
        with patch("lab.retrain_pipeline.HISTORY_PATH", history_file):
            save_retrain_history(entries)
            loaded = load_retrain_history()
            assert len(loaded) == 1
            assert loaded[0]["action"] == "REPLACED"

    def test_caps_at_50(self, history_file):
        entries = [{"i": i} for i in range(100)]
        with patch("lab.retrain_pipeline.HISTORY_PATH", history_file):
            save_retrain_history(entries)
            loaded = load_retrain_history()
            assert len(loaded) == 50


# ============================================================================
# RETRAIN PIPELINE
# ============================================================================

class TestRetrain:
    def test_skips_when_insufficient_data(self):
        """Retrain should skip if build_labeled_dataset returns too few samples."""
        with (
            patch("lab.retrain_pipeline.build_labeled_dataset", return_value=[]),
            patch("lab.retrain_pipeline.dataset_summary", return_value={
                "total": 0, "labeled": 0, "message": "No data yet",
                "ready_for_training": False,
            }),
            patch("lab.retrain_pipeline.save_retrain_history"),
        ):
            result = retrain()
            assert result["action"] == "SKIPPED"

    def test_replaces_when_better(self, tmp_path):
        """Retrain should replace model when new one is better."""
        from lab.xgboost_baseline import TrainingResult

        mock_dataset = [MagicMock() for _ in range(50)]
        mock_summary = {
            "total": 50, "labeled": 50, "ready_for_training": True,
            "message": "50 samples",
        }

        new_result = TrainingResult(
            model_path=str(tmp_path / "model.pkl"),
            samples_total=200,
            samples_train=160,
            samples_test=40,
            accuracy=0.85,
            precision_correct=0.83,
            recall_correct=0.87,
            f1_correct=0.85,
            cv_accuracy_mean=0.82,
            cv_accuracy_std=0.05,
            feature_importance={"price_delta_24h": 0.3},
            trained_at=datetime.now(timezone.utc).isoformat(),
            ready_for_production=True,
        )

        old_metrics = {
            "accuracy": 0.75,
            "cv_accuracy_mean": 0.72,
            "samples_total": 100,
        }

        with (
            patch("lab.retrain_pipeline.build_labeled_dataset", return_value=mock_dataset),
            patch("lab.retrain_pipeline.dataset_summary", return_value=mock_summary),
            patch("lab.retrain_pipeline.get_current_metrics", return_value=old_metrics),
            patch("lab.retrain_pipeline.train_model", return_value=new_result),
            patch("lab.retrain_pipeline.backup_current_model"),
            patch("lab.retrain_pipeline.save_retrain_history"),
            patch("lab.retrain_pipeline.HISTORY_PATH", tmp_path / "history.json"),
        ):
            result = retrain()
            assert result["action"] == "REPLACED"
            assert result["new_accuracy"] == 0.85

    def test_keeps_current_when_not_production_ready(self, tmp_path):
        """Retrain should keep current model when new one doesn't meet threshold."""
        from lab.xgboost_baseline import TrainingResult

        mock_dataset = [MagicMock() for _ in range(50)]
        mock_summary = {
            "total": 50, "labeled": 50, "ready_for_training": True,
            "message": "50 samples",
        }

        new_result = TrainingResult(
            model_path=str(tmp_path / "model.pkl"),
            samples_total=50,
            samples_train=40,
            samples_test=10,
            accuracy=0.50,  # Below 55% threshold
            precision_correct=0.50,
            recall_correct=0.50,
            f1_correct=0.50,
            cv_accuracy_mean=0.48,
            cv_accuracy_std=0.10,
            feature_importance={"price_delta_24h": 0.3},
            trained_at=datetime.now(timezone.utc).isoformat(),
            ready_for_production=False,
        )

        old_metrics = {
            "accuracy": 0.91,
            "cv_accuracy_mean": 0.85,
            "samples_total": 112,
        }

        with (
            patch("lab.retrain_pipeline.build_labeled_dataset", return_value=mock_dataset),
            patch("lab.retrain_pipeline.dataset_summary", return_value=mock_summary),
            patch("lab.retrain_pipeline.get_current_metrics", return_value=old_metrics),
            patch("lab.retrain_pipeline.train_model", return_value=new_result),
            patch("lab.retrain_pipeline.save_retrain_history"),
            patch("lab.retrain_pipeline.HISTORY_PATH", tmp_path / "history.json"),
        ):
            result = retrain()
            assert result["action"] == "KEPT_CURRENT"
