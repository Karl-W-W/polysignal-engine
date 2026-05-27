"""
Tests for lab/truth_board.py — Phase 7, S42.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta

import pytest

from lab import truth_board
from lab.outcome_tracker import OutcomeState


@pytest.fixture
def stub_db(tmp_path, monkeypatch):
    """Build a tiny SQLite db with an observations table that mirrors prod
    schema (market_id, price, timestamp), seed the latest row per market."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE observations (market_id TEXT, price REAL, timestamp TEXT)"
    )
    now = datetime.now(timezone.utc)
    rows = [
        ("M_BTC", 0.55, now.isoformat()),
        ("M_BTC", 0.50, (now - timedelta(hours=6)).isoformat()),  # older row
        ("M_HU", 0.40, now.isoformat()),
    ]
    conn.executemany(
        "INSERT INTO observations VALUES (?, ?, ?)", rows
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(db_path))
    return db_path


@pytest.fixture
def stub_outcomes(tmp_path, monkeypatch):
    """Seed an outcomes file with a pending crypto prediction whose 4h
    horizon has elapsed."""
    outcomes_path = tmp_path / "outcomes.json"
    ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    payload = {
        "predictions": [{
            "market_id": "M_BTC", "hypothesis": "Bullish", "confidence": 0.7,
            "price_at_prediction": 0.50, "timestamp": ts,
            "time_horizon": "4h", "category": "crypto",
            "cycle_number": 0, "evaluated": False,
        }],
        "stats": {
            "total_predictions": 1, "total_evaluated": 0,
            "correct": 0, "incorrect": 0, "neutral": 0, "accuracy": 0.0,
        },
        "per_market": {},
    }
    outcomes_path.write_text(json.dumps(payload))
    monkeypatch.setenv("OUTCOMES_FILE", str(outcomes_path))
    return outcomes_path


@pytest.fixture
def stub_status(tmp_path, monkeypatch):
    p = tmp_path / ".truth-board-status.json"
    monkeypatch.setenv("TRUTH_BOARD_STATUS_FILE", str(p))
    return p


@pytest.fixture
def stub_trading_log(tmp_path, monkeypatch):
    p = tmp_path / "trading_log.json"
    p.write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_trades": 0, "trades": [],
    }))
    # polymarket_trader._DEFAULT_LOG_PATH is import-time-captured; tests that
    # rely on TradingLog default path are out of scope here. We construct
    # TradingLog with explicit paths in this test, so this fixture just
    # exists to keep the layout clean.
    return p


def test_fetch_latest_observations_returns_one_row_per_market(stub_db):
    obs = truth_board.fetch_latest_observations()
    by_id = {o["market_id"]: o for o in obs}
    assert "M_BTC" in by_id
    assert "M_HU" in by_id
    # The latest BTC row (price 0.55) wins, not the 6h-old 0.50 row.
    assert by_id["M_BTC"]["current_price"] == 0.55


def test_fetch_latest_observations_empty_when_db_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "absent.db"))
    obs = truth_board.fetch_latest_observations()
    assert obs == []


def test_run_once_evaluates_and_writes_status(
    stub_db, stub_outcomes, stub_status, monkeypatch, tmp_path
):
    """End-to-end: truth_board reads observations from db, evaluates a
    pending prediction, writes lab/.truth-board-status.json."""
    # Point TradingLog at a tmp dir to avoid touching prod paths if defaults leak.
    monkeypatch.setenv("TRADING_LOG_FILE", str(tmp_path / "trading_log.json"))
    # S46: evaluate_outcomes now scores against Polymarket resolution. Mock
    # the gamma lookup so M_BTC (Bullish) resolves YES — the same CORRECT
    # outcome this test asserted before, just sourced from resolution
    # instead of 4h price drift.
    monkeypatch.setattr(
        "lab.outcome_tracker.lookup_resolution",
        lambda mid: ("resolved_yes", {"outcome0_price_now": 1.0, "closed": True}),
    )

    status = truth_board.run_once()

    # Outcome eval should have advanced
    assert status["observations"] >= 1
    assert status["evaluated_count"] == 1
    assert status["correct"] == 1
    assert status["incorrect"] == 0
    assert status["errors"] == []
    # And the status file should exist with the same payload
    assert stub_status.exists()
    persisted = json.loads(stub_status.read_text())
    assert persisted["evaluated_count"] == 1


def test_run_once_no_observations_records_error(
    tmp_path, monkeypatch, stub_outcomes, stub_status
):
    """If db is empty, status file records a clear error (visible failure)
    rather than silently passing."""
    empty_db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(empty_db))
    conn.execute("CREATE TABLE observations (market_id TEXT, price REAL, timestamp TEXT)")
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(empty_db))

    status = truth_board.run_once()
    assert any("no observations" in e for e in status["errors"])
