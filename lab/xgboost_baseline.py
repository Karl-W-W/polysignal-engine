"""
lab/xgboost_baseline.py
========================
Phase 2 — XGBoost baseline model for prediction market direction.

Replaces rule-based predict_market_moves() with a trained ML model.
Consumes feature vectors from lab/feature_engineering.py.

Data Pipeline:
  feature_engineering.build_labeled_dataset()
    → X (27-dim float vectors), y (CORRECT/INCORRECT labels)
    → Train XGBoost classifier
    → Save model for inference in masterloop

Lab Promotion Protocol:
  1. Built in /lab ✅
  2. Tests in tests/test_xgboost_baseline.py
  3. Wire into masterloop prediction_node after human approval + accuracy > 55%

Dependencies: xgboost, scikit-learn (added to requirements.txt Session 13)
"""

import json
import os
import pickle
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import numpy as np

from lab.feature_engineering import (
    FeatureVector,
    build_labeled_dataset,
    extract_features,
    dataset_summary,
)

# ── Configuration ────────────────────────────────────────────────────────────
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/opt/loop/data/models"))
MODEL_PATH = MODEL_DIR / "xgboost_baseline.pkl"
METRICS_PATH = MODEL_DIR / "training_metrics.json"

# Minimum labeled samples before training is allowed
MIN_SAMPLES = 30

# Labels we train on (NEUTRAL is dropped — it means the market didn't move)
TRAINABLE_LABELS = {"CORRECT", "INCORRECT"}


# ── Data Types ───────────────────────────────────────────────────────────────

@dataclass
class TrainingResult:
    """Result of a training run."""
    model_path: str
    samples_total: int
    samples_train: int
    samples_test: int
    accuracy: float
    precision_correct: float
    recall_correct: float
    f1_correct: float
    cv_accuracy_mean: float
    cv_accuracy_std: float
    feature_importance: Dict[str, float]
    trained_at: str
    ready_for_production: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModelPrediction:
    """Single prediction from the trained model."""
    market_id: str
    hypothesis: str        # "Bullish" or "Bearish"
    confidence: float      # 0.0 to 1.0
    reasoning: str
    time_horizon: str = "4h"
    model_version: str = "xgboost_baseline_v1"

    def to_dict(self) -> dict:
        return asdict(self)


# ── Training ─────────────────────────────────────────────────────────────────

def prepare_training_data(
    dataset: List[FeatureVector],
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Convert labeled FeatureVectors into numpy arrays for training.

    Filters to CORRECT/INCORRECT only (drops NEUTRAL).
    Returns (X, y, feature_names) where y=1 for CORRECT, y=0 for INCORRECT.
    """
    filtered = [fv for fv in dataset if fv.label in TRAINABLE_LABELS]

    if not filtered:
        return np.array([]), np.array([]), []

    X = np.array([fv.feature_values() for fv in filtered], dtype=np.float32)
    y = np.array(
        [1 if fv.label == "CORRECT" else 0 for fv in filtered],
        dtype=np.int32,
    )
    feature_names = filtered[0].feature_names()

    return X, y, feature_names


def train_model(
    dataset: Optional[List[FeatureVector]] = None,
    db_path: Optional[str] = None,
    outcomes_path: Optional[Path] = None,
    save: bool = True,
) -> TrainingResult:
    """Train an XGBoost classifier on labeled prediction outcomes.

    Args:
        dataset: Pre-built labeled dataset (if None, builds from DB/outcomes)
        db_path: Override DB path for feature extraction
        outcomes_path: Override outcomes file path
        save: Whether to save model + metrics to disk

    Returns:
        TrainingResult with accuracy, feature importance, etc.

    Raises:
        ValueError: If insufficient training data (<MIN_SAMPLES)
    """
    # Lazy imports — keeps module importable without sklearn/xgboost installed
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import (
        accuracy_score,
        precision_recall_fscore_support,
        classification_report,
    )
    import xgboost as xgb

    # Build dataset if not provided
    if dataset is None:
        kwargs = {}
        if db_path:
            kwargs["db_path"] = db_path
        if outcomes_path:
            kwargs["outcomes_path"] = outcomes_path
        dataset = build_labeled_dataset(**kwargs)

    X, y, feature_names = prepare_training_data(dataset)

    if len(X) < MIN_SAMPLES:
        raise ValueError(
            f"Insufficient training data: {len(X)} samples "
            f"(need {MIN_SAMPLES}). Scanner needs more time to accumulate."
        )

    # Train/test split (stratified to preserve class balance)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # XGBoost with conservative hyperparameters for small datasets
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=3,           # Shallow trees to prevent overfitting
        learning_rate=0.1,
        min_child_weight=3,    # Conservative for small samples
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,         # L1 regularization
        reg_lambda=1.0,        # L2 regularization
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
    )

    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="binary", pos_label=1, zero_division=0.0
    )

    # Cross-validation (if enough data)
    n_folds = min(5, max(2, len(X) // 10))
    cv_scores = cross_val_score(model, X, y, cv=n_folds, scoring="accuracy")

    # Feature importance
    importance = dict(zip(feature_names, model.feature_importances_.tolist()))
    # Sort by importance descending
    importance = dict(
        sorted(importance.items(), key=lambda x: x[1], reverse=True)
    )

    # Save model and metrics
    model_path_str = str(MODEL_PATH)
    if save:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump({"model": model, "feature_names": feature_names}, f)
        model_path_str = str(MODEL_PATH)

    result = TrainingResult(
        model_path=model_path_str,
        samples_total=len(X),
        samples_train=len(X_train),
        samples_test=len(X_test),
        accuracy=round(accuracy, 4),
        precision_correct=round(float(precision), 4),
        recall_correct=round(float(recall), 4),
        f1_correct=round(float(f1), 4),
        cv_accuracy_mean=round(float(cv_scores.mean()), 4),
        cv_accuracy_std=round(float(cv_scores.std()), 4),
        feature_importance=importance,
        trained_at=datetime.now(timezone.utc).isoformat(),
        ready_for_production=accuracy > 0.55 and len(X) >= 50,
    )

    if save:
        with open(METRICS_PATH, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

    return result


# ── Inference ────────────────────────────────────────────────────────────────

def load_model(
    model_path: Path = MODEL_PATH,
) -> Tuple[object, List[str]]:
    """Load a trained model from disk.

    Returns:
        (model, feature_names) tuple

    Raises:
        FileNotFoundError: If model file doesn't exist
    """
    if not model_path.exists():
        raise FileNotFoundError(
            f"No trained model at {model_path}. Run train_model() first."
        )

    with open(model_path, "rb") as f:
        data = pickle.load(f)

    return data["model"], data["feature_names"]


def predict_single(
    market_id: str,
    hypothesis_direction: str = "Bullish",
    db_path: Optional[str] = None,
    model_path: Path = MODEL_PATH,
) -> ModelPrediction:
    """Predict whether a given hypothesis direction will be correct.

    This is the inference entry point for the masterloop.
    Given a market_id and a hypothesis direction (Bullish/Bearish),
    it returns the model's confidence that this prediction is CORRECT.

    Args:
        market_id: Polymarket market ID
        hypothesis_direction: "Bullish" or "Bearish" — the direction to evaluate
        db_path: Override DB path
        model_path: Path to trained model

    Returns:
        ModelPrediction with confidence and reasoning
    """
    model, feature_names = load_model(model_path)

    # Extract current features
    kwargs = {}
    if db_path:
        kwargs["db_path"] = db_path
    fv = extract_features(market_id, **kwargs)

    # Predict
    X = np.array([fv.feature_values()], dtype=np.float32)
    proba = model.predict_proba(X)[0]
    # proba[1] = probability of CORRECT, proba[0] = probability of INCORRECT
    confidence = float(proba[1])

    # Build reasoning from top features
    importances = dict(zip(feature_names, model.feature_importances_))
    top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:3]
    feature_context = ", ".join(
        f"{name}={getattr(fv, name, 0):.4f}" for name, _ in top_features
    )
    reasoning = (
        f"XGBoost v1: P(correct)={confidence:.2%} for {hypothesis_direction}. "
        f"Key features: {feature_context}"
    )

    return ModelPrediction(
        market_id=market_id,
        hypothesis=hypothesis_direction,
        confidence=round(confidence, 4),
        reasoning=reasoning,
    )


def predict_batch(
    observations: List[Dict],
    db_path: Optional[str] = None,
    model_path: Path = MODEL_PATH,
) -> List[ModelPrediction]:
    """Predict for a batch of observations (drop-in for predict_market_moves).

    For each observation, predicts both Bullish and Bearish directions,
    and returns the one with higher confidence.

    Args:
        observations: List of observation dicts from scanner
        db_path: Override DB path
        model_path: Path to trained model

    Returns:
        List of ModelPrediction objects
    """
    model, feature_names = load_model(model_path)
    predictions = []

    for obs in observations:
        market_id = obs.get("market_id")
        if not market_id:
            continue

        kwargs = {}
        if db_path:
            kwargs["db_path"] = db_path
        fv = extract_features(market_id, **kwargs)
        X = np.array([fv.feature_values()], dtype=np.float32)

        proba = model.predict_proba(X)[0]
        confidence_correct = float(proba[1])

        # The perceived direction from the scanner's signal
        perceived_delta = obs.get("change_since_last", 0.0) or obs.get("delta", 0.0)

        if perceived_delta > 0:
            hypothesis = "Bullish"
        elif perceived_delta < 0:
            hypothesis = "Bearish"
        else:
            # No directional signal — use model's view
            hypothesis = "Bullish" if confidence_correct > 0.5 else "Bearish"

        # Confidence: how likely this direction is correct
        confidence = confidence_correct if hypothesis == "Bullish" else (1 - confidence_correct)
        confidence = max(0.1, min(0.95, confidence))  # Clamp to [0.1, 0.95]

        importances = dict(zip(feature_names, model.feature_importances_))
        top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:3]
        feature_context = ", ".join(
            f"{name}={getattr(fv, name, 0):.4f}" for name, _ in top_features
        )

        predictions.append(ModelPrediction(
            market_id=market_id,
            hypothesis=hypothesis,
            confidence=round(confidence, 4),
            reasoning=f"XGBoost v1: {feature_context}",
            time_horizon=obs.get("time_horizon", "4h"),
        ))

    return predictions


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("PolySignal XGBoost Baseline — Phase 2 Training")
    print("=" * 60)

    # Check data readiness
    dataset = build_labeled_dataset()
    summary = dataset_summary(dataset)
    print(f"\nDataset: {summary['message']}")

    if summary.get("ready_for_training"):
        print("\nTraining XGBoost model...")
        try:
            result = train_model(dataset=dataset)
            print(f"\n  Accuracy:    {result.accuracy:.1%}")
            print(f"  Precision:   {result.precision_correct:.1%}")
            print(f"  Recall:      {result.recall_correct:.1%}")
            print(f"  F1:          {result.f1_correct:.1%}")
            print(f"  CV Accuracy: {result.cv_accuracy_mean:.1%} ± {result.cv_accuracy_std:.1%}")
            print(f"\n  Top features:")
            for name, imp in list(result.feature_importance.items())[:5]:
                print(f"    {name:30s} {imp:.4f}")
            print(f"\n  Model saved: {result.model_path}")
            print(f"  Production ready: {result.ready_for_production}")
        except ValueError as e:
            print(f"\n  ⚠ {e}")
    else:
        print(f"\n  Not enough data yet. {summary.get('message', '')}")
        print("  Scanner is accumulating — check back in 24-48h.")
