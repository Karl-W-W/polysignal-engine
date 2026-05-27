"""
tests/test_migrate_outcomes.py
==============================
Tests for eval/migrate_outcomes_to_resolution.py — the one-shot S46
label-wipe migration.
"""

import json
from pathlib import Path

import pytest

from eval.migrate_outcomes_to_resolution import migrate, S46_LABEL_FIELDS


def _seed(path: Path):
    """Write a realistic outcomes file with mixed labelled / unlabelled records."""
    data = {
        "predictions": [
            {
                "market_id": "566188", "hypothesis": "Bullish",
                "confidence": 0.85, "price_at_prediction": 0.40,
                "timestamp": "2026-04-24T15:04:29Z", "time_horizon": "4h",
                "cycle_number": 1, "evaluated": True, "outcome": "CORRECT",
                "price_at_evaluation": 0.41, "evaluated_at": "2026-04-24T19:04Z",
                "actual_delta": 0.01,
            },
            {
                "market_id": "665374", "hypothesis": "Bullish",
                "confidence": 0.70, "price_at_prediction": 0.30,
                "timestamp": "2026-05-04T06:01Z", "time_horizon": "4h",
                "cycle_number": 2, "evaluated": True, "outcome": "INCORRECT",
                "price_at_evaluation": 0.27, "evaluated_at": "2026-05-04T10:01Z",
                "actual_delta": -0.03,
            },
            {
                "market_id": "999999", "hypothesis": "Bullish",
                "confidence": 0.60, "price_at_prediction": 0.55,
                "timestamp": "2026-05-26T18:00Z", "time_horizon": "4h",
                "cycle_number": 3, "evaluated": False, "outcome": None,
            },
        ],
        "stats": {
            "total_predictions": 3, "total_evaluated": 2,
            "correct": 1, "incorrect": 1, "neutral": 0,
            "accuracy": 0.5,
        },
        "per_market": {
            "566188": {"correct": 1, "incorrect": 0, "neutral": 0, "title": "Man City"},
            "665374": {"correct": 0, "incorrect": 1, "neutral": 0, "title": "Iran"},
        },
    }
    path.write_text(json.dumps(data, indent=2))


def test_migration_writes_backup(tmp_path):
    state_file = tmp_path / "outcomes.json"
    _seed(state_file)
    report = migrate(state_file, dry_run=False)
    backup = tmp_path / "outcomes.json.pre-s46-bak"
    assert backup.exists(), "pre-S46 backup must be written"
    assert report["backup_path"] == str(backup)
    # Backup must match the pre-migration content
    pre = json.loads(backup.read_text())
    assert pre["stats"]["accuracy"] == 0.5
    assert pre["predictions"][0]["outcome"] == "CORRECT"


def test_migration_preserves_record_count(tmp_path):
    state_file = tmp_path / "outcomes.json"
    _seed(state_file)
    migrate(state_file, dry_run=False)
    post = json.loads(state_file.read_text())
    assert len(post["predictions"]) == 3, "Records themselves must survive"


def test_migration_clears_all_label_fields(tmp_path):
    state_file = tmp_path / "outcomes.json"
    _seed(state_file)
    migrate(state_file, dry_run=False)
    post = json.loads(state_file.read_text())
    for p in post["predictions"]:
        assert p["evaluated"] is False
        for k in S46_LABEL_FIELDS:
            if k == "evaluated":
                continue
            assert p.get(k) is None, f"Field {k} should be cleared, got {p.get(k)!r}"


def test_migration_zeros_stats_counters(tmp_path):
    state_file = tmp_path / "outcomes.json"
    _seed(state_file)
    migrate(state_file, dry_run=False)
    post = json.loads(state_file.read_text())
    s = post["stats"]
    assert s["correct"] == 0
    assert s["incorrect"] == 0
    assert s["neutral"] == 0
    assert s["total_evaluated"] == 0
    assert s["accuracy"] == 0.0
    # total_predictions is a lifetime counter — preserve it
    assert s["total_predictions"] == 3


def test_migration_wipes_per_market(tmp_path):
    state_file = tmp_path / "outcomes.json"
    _seed(state_file)
    migrate(state_file, dry_run=False)
    post = json.loads(state_file.read_text())
    assert post["per_market"] == {}, "per_market built from noise must be cleared"


def test_dry_run_writes_nothing(tmp_path):
    state_file = tmp_path / "outcomes.json"
    _seed(state_file)
    original = state_file.read_text()
    report = migrate(state_file, dry_run=True)
    assert report["dry_run"] is True
    assert state_file.read_text() == original, "Dry-run must not write"
    assert not (tmp_path / "outcomes.json.pre-s46-bak").exists()
    # But the report must still summarize what would change
    assert report["records_evaluated_pre"] == 2
    assert report["stats_pre"]["accuracy"] == 0.5


def test_missing_file_returns_error_report(tmp_path):
    report = migrate(tmp_path / "does_not_exist.json", dry_run=False)
    assert report["ok"] is False
    assert "not found" in report["reason"]
