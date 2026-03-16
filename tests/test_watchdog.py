#!/usr/bin/env python3
"""Tests for lab/watchdog.py — self-healing watchdog."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from lab.watchdog import (
    check_prediction_drought,
    check_accuracy_regression,
    check_scanner_health,
    check_paper_trade_quality,
    run_watchdog_checks,
    PREDICTION_DROUGHT_HOURS,
    ACCURACY_ALERT_THRESHOLD,
    SCANNER_STALE_MINUTES,
)


@pytest.fixture
def tmp_outcomes(tmp_path, monkeypatch):
    """Create a temporary outcomes file."""
    path = tmp_path / "outcomes.json"
    monkeypatch.setattr("lab.watchdog.OUTCOMES_FILE", path)
    return path


@pytest.fixture
def tmp_scanner_status(tmp_path, monkeypatch):
    """Create a temporary scanner status file."""
    path = tmp_path / ".scanner-status.json"
    monkeypatch.setattr("lab.watchdog.SCANNER_STATUS_FILE", path)
    return path


@pytest.fixture
def tmp_alerts(tmp_path, monkeypatch):
    """Temporary alerts file."""
    path = tmp_path / ".watchdog-alerts"
    monkeypatch.setattr("lab.watchdog.ALERTS_FILE", path)
    return path


@pytest.fixture
def tmp_trading_log(tmp_path, monkeypatch):
    """Temporary trading log."""
    path = tmp_path / "trading_log.json"
    monkeypatch.setattr("lab.watchdog.TRADING_LOG_FILE", path)
    return path


class TestPredictionDrought:
    def test_alert_when_no_file(self, tmp_outcomes, tmp_alerts):
        alert = check_prediction_drought()
        assert alert is not None
        assert alert.severity == "warning"

    def test_alert_when_empty(self, tmp_outcomes, tmp_alerts):
        tmp_outcomes.write_text(json.dumps({"predictions": [], "stats": {}}))
        alert = check_prediction_drought()
        assert alert is not None
        assert alert.severity == "critical"

    def test_no_alert_when_recent_predictions(self, tmp_outcomes, tmp_alerts):
        now = datetime.now(timezone.utc).isoformat()
        tmp_outcomes.write_text(json.dumps({
            "predictions": [
                {"market_id": "556108", "timestamp": now, "evaluated": False}
            ],
            "stats": {},
        }))
        alert = check_prediction_drought()
        assert alert is None

    def test_alert_when_only_old_predictions(self, tmp_outcomes, tmp_alerts):
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        tmp_outcomes.write_text(json.dumps({
            "predictions": [
                {"market_id": "556108", "timestamp": old, "evaluated": True}
            ],
            "stats": {},
        }))
        alert = check_prediction_drought()
        assert alert is not None
        assert "48h ago" in alert.message or "No predictions" in alert.message

    def test_ignores_fake_predictions(self, tmp_outcomes, tmp_alerts):
        now = datetime.now(timezone.utc).isoformat()
        tmp_outcomes.write_text(json.dumps({
            "predictions": [
                {"market_id": "0xfake_btc", "timestamp": now, "evaluated": False}
            ],
            "stats": {},
        }))
        alert = check_prediction_drought()
        assert alert is not None  # Fake predictions don't count


class TestAccuracyRegression:
    def test_no_alert_insufficient_data(self, tmp_outcomes, tmp_alerts):
        now = datetime.now(timezone.utc).isoformat()
        tmp_outcomes.write_text(json.dumps({
            "predictions": [
                {"market_id": "m1", "evaluated": True, "outcome": "INCORRECT",
                 "evaluated_at": now, "timestamp": now}
            ] * 5,  # Only 5, below threshold of 20
            "stats": {},
        }))
        alert = check_accuracy_regression()
        assert alert is None

    def test_alert_when_accuracy_low(self, tmp_outcomes, tmp_alerts):
        now = datetime.now(timezone.utc).isoformat()
        preds = []
        for i in range(25):
            preds.append({
                "market_id": f"m{i}",
                "evaluated": True,
                "outcome": "INCORRECT" if i < 20 else "CORRECT",
                "evaluated_at": now,
                "timestamp": now,
            })
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        alert = check_accuracy_regression()
        assert alert is not None
        assert alert.severity == "critical"

    def test_no_alert_when_accuracy_good(self, tmp_outcomes, tmp_alerts):
        now = datetime.now(timezone.utc).isoformat()
        preds = []
        for i in range(25):
            preds.append({
                "market_id": f"m{i}",
                "evaluated": True,
                "outcome": "CORRECT" if i < 18 else "INCORRECT",
                "evaluated_at": now,
                "timestamp": now,
            })
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        alert = check_accuracy_regression()
        assert alert is None


class TestScannerHealth:
    def test_alert_when_no_status_file(self, tmp_scanner_status, tmp_alerts):
        alert = check_scanner_health()
        assert alert is not None
        assert "missing" in alert.message

    def test_alert_when_stale(self, tmp_scanner_status, tmp_alerts):
        old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        tmp_scanner_status.write_text(json.dumps({
            "cycle": 100, "timestamp": old, "errors": 0,
        }))
        alert = check_scanner_health()
        assert alert is not None
        assert alert.severity == "critical"

    def test_no_alert_when_fresh(self, tmp_scanner_status, tmp_alerts):
        now = datetime.now(timezone.utc).isoformat()
        tmp_scanner_status.write_text(json.dumps({
            "cycle": 100, "timestamp": now, "errors": 0,
        }))
        alert = check_scanner_health()
        assert alert is None


class TestPaperTradeQuality:
    def test_alert_when_all_fake(self, tmp_trading_log, tmp_alerts):
        trades = [
            {"market_id": "0xfake_btc", "title": "Unknown Market"}
            for _ in range(15)
        ]
        tmp_trading_log.write_text(json.dumps({"trades": trades}))
        alert = check_paper_trade_quality()
        assert alert is not None

    def test_no_alert_with_real_trades(self, tmp_trading_log, tmp_alerts):
        trades = [
            {"market_id": "556108", "title": "BTC 100k"}
            for _ in range(15)
        ]
        tmp_trading_log.write_text(json.dumps({"trades": trades}))
        alert = check_paper_trade_quality()
        assert alert is None


class TestRunWatchdog:
    def test_writes_alerts_file(self, tmp_outcomes, tmp_scanner_status,
                                 tmp_alerts, tmp_trading_log):
        alerts = run_watchdog_checks()
        assert isinstance(alerts, list)
        assert tmp_alerts.exists()
        data = json.loads(tmp_alerts.read_text())
        assert "alert_count" in data
