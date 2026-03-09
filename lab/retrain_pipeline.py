#!/usr/bin/env python3
"""
lab/retrain_pipeline.py
========================
Automatic XGBoost retrain pipeline — closes the intelligence feedback loop.

Usage:
    # Direct execution (host-side)
    cd /opt/loop && .venv/bin/python3 -m lab.retrain_pipeline

    # Via trigger file (Loop can request from sandbox)
    echo "retrain" > /opt/loop/lab/.retrain-trigger

    # The retrain handler (systemd path unit or cron) calls this script,
    # then restarts the scanner to load the new model.

Flow:
    1. Build labeled dataset from prediction_outcomes.json + observations DB
    2. Train new XGBoost model (same hyperparams as xgboost_baseline.py)
    3. Compare against current model
    4. If better: save as new model + restart scanner
    5. If worse: keep current model, log why
    6. Write report to lab/retrain_history.json
"""

import json
import os
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab.xgboost_baseline import (
    train_model,
    load_model,
    MODEL_PATH,
    METRICS_PATH,
    MODEL_DIR,
    TrainingResult,
)
from lab.feature_engineering import build_labeled_dataset, dataset_summary

# ── Configuration ────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "/opt/loop/data/test.db")
OUTCOMES_FILE = Path(os.getenv(
    "OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"
))
HISTORY_PATH = Path(os.path.dirname(os.path.abspath(__file__))) / "retrain_history.json"
BACKUP_DIR = MODEL_DIR / "backups"

# Minimum improvement to replace current model (avoid noise-driven swaps)
MIN_ACCURACY_IMPROVEMENT = 0.0  # Accept any model that meets the 55% threshold


def load_retrain_history() -> list:
    """Load retrain history from disk."""
    if HISTORY_PATH.exists():
        try:
            with open(HISTORY_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            pass
    return []


def save_retrain_history(history: list):
    """Save retrain history to disk."""
    # Keep last 50 entries
    with open(HISTORY_PATH, "w") as f:
        json.dump(history[-50:], f, indent=2)


def get_current_metrics() -> dict:
    """Load metrics from the currently deployed model."""
    if METRICS_PATH.exists():
        try:
            with open(METRICS_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def backup_current_model():
    """Backup the current model before replacing."""
    if MODEL_PATH.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"xgboost_baseline_{ts}.pkl"
        shutil.copy2(MODEL_PATH, backup)
        print(f"  Backed up current model to {backup}")
        # Keep only last 5 backups
        backups = sorted(BACKUP_DIR.glob("xgboost_baseline_*.pkl"))
        for old in backups[:-5]:
            old.unlink()


def retrain() -> dict:
    """Execute the full retrain pipeline.

    Returns:
        dict with retrain results: {action, reason, old_accuracy, new_accuracy, ...}
    """
    print("\n" + "=" * 60)
    print("XGBOOST RETRAIN PIPELINE")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # 1. Build labeled dataset
    print("\n[1/4] Building labeled dataset...")
    dataset = build_labeled_dataset(db_path=DB_PATH, outcomes_path=OUTCOMES_FILE)
    summary = dataset_summary(dataset)
    print(f"  Dataset: {summary.get('message', 'unknown')}")

    if not summary.get("ready_for_training"):
        reason = f"Not enough data: {summary.get('message', 'unknown')}"
        print(f"  ⚠ {reason}")
        return {"action": "SKIPPED", "reason": reason, "timestamp": datetime.now(timezone.utc).isoformat()}

    # 2. Load current model metrics for comparison
    print("\n[2/4] Loading current model metrics...")
    current = get_current_metrics()
    old_accuracy = current.get("accuracy", 0.0)
    old_cv = current.get("cv_accuracy_mean", 0.0)
    old_samples = current.get("samples_total", 0)
    print(f"  Current: accuracy={old_accuracy:.1%}, CV={old_cv:.1%}, samples={old_samples}")

    # 3. Train new model
    print("\n[3/4] Training new model...")
    try:
        new_result = train_model(
            dataset=dataset,
            db_path=DB_PATH,
            save=False,  # Don't save yet — compare first
        )
    except ValueError as e:
        reason = str(e)
        print(f"  ⚠ Training failed: {reason}")
        return {"action": "FAILED", "reason": reason, "timestamp": datetime.now(timezone.utc).isoformat()}

    print(f"  New:     accuracy={new_result.accuracy:.1%}, CV={new_result.cv_accuracy_mean:.1%}, samples={new_result.samples_total}")

    # 4. Compare and decide
    print("\n[4/4] Comparing models...")
    improvement = new_result.accuracy - old_accuracy
    cv_improvement = new_result.cv_accuracy_mean - old_cv
    more_data = new_result.samples_total > old_samples

    # Replace only if: production-ready AND (better accuracy OR more data with acceptable accuracy)
    acceptable_with_more_data = more_data and new_result.accuracy >= (old_accuracy - 0.05)
    should_replace = (
        new_result.ready_for_production
        and (improvement >= MIN_ACCURACY_IMPROVEMENT or acceptable_with_more_data)
    )

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "old_accuracy": old_accuracy,
        "old_cv": old_cv,
        "old_samples": old_samples,
        "new_accuracy": new_result.accuracy,
        "new_cv": new_result.cv_accuracy_mean,
        "new_samples": new_result.samples_total,
        "improvement": round(improvement, 4),
        "cv_improvement": round(cv_improvement, 4),
        "top_features": list(new_result.feature_importance.keys())[:5],
    }

    if should_replace:
        print(f"\n  ✅ NEW MODEL ACCEPTED")
        print(f"     Accuracy: {old_accuracy:.1%} → {new_result.accuracy:.1%} ({improvement:+.1%})")
        print(f"     CV:       {old_cv:.1%} → {new_result.cv_accuracy_mean:.1%} ({cv_improvement:+.1%})")
        print(f"     Samples:  {old_samples} → {new_result.samples_total}")

        # Backup current, save new
        backup_current_model()
        new_result_saved = train_model(dataset=dataset, db_path=DB_PATH, save=True)

        entry["action"] = "REPLACED"
        entry["reason"] = f"Improvement: {improvement:+.1%} accuracy, {cv_improvement:+.1%} CV, {new_result.samples_total} samples"
    else:
        reason = []
        if not new_result.ready_for_production:
            reason.append(f"Not production-ready (accuracy={new_result.accuracy:.1%}, need >55%)")
        if improvement < MIN_ACCURACY_IMPROVEMENT and not more_data:
            reason.append(f"No improvement ({improvement:+.1%})")
        reason_str = "; ".join(reason) or "Unknown"

        print(f"\n  ⊘ KEEPING CURRENT MODEL")
        print(f"     Reason: {reason_str}")

        entry["action"] = "KEPT_CURRENT"
        entry["reason"] = reason_str

    # Save history
    history = load_retrain_history()
    history.append(entry)
    save_retrain_history(history)

    print(f"\n{'=' * 60}")
    print(f"RETRAIN COMPLETE: {entry['action']}")
    print(f"{'=' * 60}\n")

    return entry


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = retrain()
    print(json.dumps(result, indent=2))
