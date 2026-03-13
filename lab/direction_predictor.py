#!/usr/bin/env python3
"""
lab/direction_predictor.py
==========================
Direct XGBoost direction predictor — replaces toy momentum check.

Instead of: toy predictor → XGBoost gate (predict if correct)
This does:  features → XGBoost (predict direction directly)

Session 25 prototype. Results:
  - Time-series 5-fold CV: 73.1% ± 31.9%
  - Top features: clob_depth_imbalance (0.308), price_volatility_24h (0.243)
  - Baseline (always UP): 47.5%
  - Current production: 17.4%
  
WARNING: High variance in CV suggests overfitting risk. 179 samples is small.
Need leave-one-market-out validation before promoting.
"""

import json
import os
import numpy as np
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DB_PATH = os.getenv("DB_PATH", "/opt/loop/data/test.db")
OUTCOMES_FILE = Path(os.getenv("OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"))
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/opt/loop/data/models"))

# Features used for prediction (exclude identity/label columns)
EXCLUDE_COLS = {'market_id', 'timestamp', 'cycle_number'}


def build_direction_dataset(outcomes_path: Path = OUTCOMES_FILE,
                             db_path: str = DB_PATH) -> Tuple[np.ndarray, np.ndarray, List[str], List[Dict]]:
    """Build labeled dataset for direction prediction.
    
    Returns:
        X: feature matrix
        y: labels (1=price went up, 0=price went down)
        feature_names: column names
        metadata: list of dicts with market_id, timestamp, hypothesis
    """
    from lab.feature_engineering import extract_features

    outcomes = json.loads(outcomes_path.read_text())
    preds = outcomes['predictions']
    
    directional = [p for p in preds if p.get('evaluated')
                   and 'fake' not in str(p.get('market_id', ''))
                   and p.get('outcome') in ('CORRECT', 'INCORRECT')]

    dataset = []
    metadata = []
    for p in directional:
        try:
            ref_time = datetime.fromisoformat(p['timestamp'])
            fv = extract_features(p['market_id'], ref_time=ref_time, db_path=db_path)
            row = asdict(fv)
            hyp = p.get('hypothesis', 'Unknown')
            
            # Derive actual direction from hypothesis + correctness
            if hyp == 'Bullish':
                price_went_up = 1 if p['outcome'] == 'CORRECT' else 0
            else:
                price_went_up = 0 if p['outcome'] == 'CORRECT' else 1
            
            row['_label'] = price_went_up
            dataset.append(row)
            metadata.append({
                'market_id': p['market_id'],
                'timestamp': p['timestamp'],
                'hypothesis': hyp,
                'original_outcome': p['outcome'],
            })
        except Exception:
            continue

    if not dataset:
        raise ValueError("No samples could be extracted")

    feature_names = [k for k in dataset[0].keys() 
                     if k not in EXCLUDE_COLS and k != '_label'
                     and isinstance(dataset[0][k], (int, float))]

    X = np.array([[row[f] for f in feature_names] for row in dataset])
    y = np.array([row['_label'] for row in dataset])

    return X, y, feature_names, metadata


def train_direction_model(X: np.ndarray, y: np.ndarray,
                          n_estimators: int = 100, max_depth: int = 3):
    """Train XGBoost direction predictor."""
    import xgboost as xgb
    
    model = xgb.XGBClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_child_weight=2,
        random_state=42,
        eval_metric='logloss',
    )
    model.fit(X, y)
    return model


def predict_direction(model, feature_names: List[str], market_id: str,
                      db_path: str = DB_PATH) -> Dict:
    """Predict whether a market's price will go up in next 24h.
    
    Returns:
        {direction: 'Bullish'/'Bearish', confidence: float, features_used: list}
    """
    from lab.feature_engineering import extract_features
    
    fv = extract_features(market_id, db_path=db_path)
    row = asdict(fv)
    X = np.array([[row[f] for f in feature_names]])
    
    proba = model.predict_proba(X)[0]
    p_up = float(proba[1])
    
    return {
        'direction': 'Bullish' if p_up > 0.5 else 'Bearish',
        'confidence': round(max(p_up, 1 - p_up), 3),
        'p_up': round(p_up, 3),
        'market_id': market_id,
    }


if __name__ == "__main__":
    print("Building direction dataset...")
    X, y, features, meta = build_direction_dataset()
    print(f"Dataset: {X.shape[0]} samples, {X.shape[1]} features")
    print(f"Label balance: UP={sum(y)}, DOWN={len(y)-sum(y)}")
    
    from sklearn.model_selection import TimeSeriesSplit, cross_val_score
    import xgboost as xgb
    
    model = xgb.XGBClassifier(n_estimators=100, max_depth=3, min_child_weight=2,
                               random_state=42, eval_metric='logloss')
    
    tscv = TimeSeriesSplit(n_splits=5)
    scores = cross_val_score(model, X, y, cv=tscv, scoring='accuracy')
    print(f"Time-series 5-fold CV: {scores.mean():.1%} ± {scores.std():.1%}")
    print(f"Per-fold: {[f'{s:.1%}' for s in scores]}")
    
    # Feature importance
    model.fit(X, y)
    importances = sorted(zip(features, model.feature_importances_), key=lambda x: -x[1])
    print("\nTop features:")
    for feat, imp in importances[:5]:
        print(f"  {feat}: {imp:.3f}")
