"""Tests for lab/direction_predictor.py — direction prediction prototype."""
import pytest
import numpy as np

pytest.importorskip("xgboost")
pytest.importorskip("sklearn")


class TestDirectionPredictor:
    def test_train_direction_model(self):
        from lab.direction_predictor import train_direction_model
        X = np.random.randn(50, 10)
        y = np.random.randint(0, 2, 50)
        model = train_direction_model(X, y, n_estimators=10, max_depth=2)
        assert hasattr(model, 'predict')
        preds = model.predict(X)
        assert len(preds) == 50

    def test_predict_proba_sums_to_one(self):
        from lab.direction_predictor import train_direction_model
        X = np.random.randn(50, 10)
        y = np.random.randint(0, 2, 50)
        model = train_direction_model(X, y, n_estimators=10)
        proba = model.predict_proba(X[:1])[0]
        assert abs(sum(proba) - 1.0) < 0.01

    def test_build_dataset_with_data(self):
        from lab.direction_predictor import build_direction_dataset
        from pathlib import Path
        import os
        outcomes_path = Path(os.getenv("OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"))
        db_path = os.getenv("DB_PATH", "/opt/loop/data/test.db")
        if not outcomes_path.exists() or not Path(db_path).exists():
            pytest.skip("Data files not available")
        X, y, features, meta = build_direction_dataset(outcomes_path, db_path)
        assert X.shape[0] == y.shape[0] > 0
        assert set(np.unique(y)).issubset({0, 1})
