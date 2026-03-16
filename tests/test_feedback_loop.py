#!/usr/bin/env python3
"""Tests for lab/feedback_loop.py — closed feedback loop."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from lab.feedback_loop import (
    compute_market_reports,
    compute_ev,
    run_feedback_cycle,
    MarketReport,
    EXCLUDE_ACCURACY_THRESHOLD,
    STAR_ACCURACY_THRESHOLD,
)


@pytest.fixture
def tmp_outcomes(tmp_path, monkeypatch):
    path = tmp_path / "outcomes.json"
    monkeypatch.setattr("lab.feedback_loop.OUTCOMES_FILE", path)
    return path


@pytest.fixture
def tmp_report(tmp_path, monkeypatch):
    path = tmp_path / ".feedback-report"
    monkeypatch.setattr("lab.feedback_loop.REPORT_FILE", path)
    return path


@pytest.fixture
def tmp_retrain(tmp_path, monkeypatch):
    path = tmp_path / ".retrain-trigger"
    monkeypatch.setattr("lab.feedback_loop.RETRAIN_TRIGGER", path)
    return path


def _make_predictions(market_id, correct, incorrect, neutral=0, days_ago=0):
    """Generate prediction records for testing."""
    base_ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    preds = []
    for i in range(correct):
        preds.append({
            "market_id": market_id,
            "hypothesis": "Bullish",
            "confidence": 0.8,
            "evaluated": True,
            "outcome": "CORRECT",
            "timestamp": (base_ts - timedelta(hours=i)).isoformat(),
            "evaluated_at": base_ts.isoformat(),
        })
    for i in range(incorrect):
        preds.append({
            "market_id": market_id,
            "hypothesis": "Bullish",
            "confidence": 0.7,
            "evaluated": True,
            "outcome": "INCORRECT",
            "timestamp": (base_ts - timedelta(hours=correct + i)).isoformat(),
            "evaluated_at": base_ts.isoformat(),
        })
    for i in range(neutral):
        preds.append({
            "market_id": market_id,
            "hypothesis": "Bullish",
            "confidence": 0.6,
            "evaluated": True,
            "outcome": "NEUTRAL",
            "timestamp": (base_ts - timedelta(hours=correct + incorrect + i)).isoformat(),
            "evaluated_at": base_ts.isoformat(),
        })
    return preds


class TestMarketReports:
    def test_empty_file(self, tmp_outcomes, tmp_report):
        reports = compute_market_reports()
        assert reports == []

    def test_single_market(self, tmp_outcomes, tmp_report):
        preds = _make_predictions("556108", correct=15, incorrect=5)
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        reports = compute_market_reports()
        assert len(reports) == 1
        assert reports[0].market_id == "556108"
        assert reports[0].accuracy == 0.75
        assert reports[0].correct == 15
        assert reports[0].incorrect == 5

    def test_excludes_low_accuracy(self, tmp_outcomes, tmp_report):
        preds = _make_predictions("bad_market", correct=5, incorrect=20)
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        reports = compute_market_reports()
        assert reports[0].recommendation == "exclude"

    def test_flags_star_performers(self, tmp_outcomes, tmp_report):
        preds = _make_predictions("star_market", correct=18, incorrect=2)
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        reports = compute_market_reports()
        assert reports[0].recommendation == "star"

    def test_ignores_fake_markets(self, tmp_outcomes, tmp_report):
        preds = _make_predictions("0xfake_btc", correct=10, incorrect=0)
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        reports = compute_market_reports()
        assert len(reports) == 0

    def test_multiple_markets_sorted(self, tmp_outcomes, tmp_report):
        preds = (
            _make_predictions("m1", correct=20, incorrect=5) +
            _make_predictions("m2", correct=5, incorrect=2)
        )
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        reports = compute_market_reports()
        assert len(reports) == 2
        assert reports[0].market_id == "m1"  # More data = first

    def test_old_data_excluded(self, tmp_outcomes, tmp_report):
        preds = _make_predictions("old_market", correct=20, incorrect=5, days_ago=30)
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        reports = compute_market_reports(window_days=14)
        assert len(reports) == 0


class TestEV:
    def test_ev_computation(self, tmp_outcomes, tmp_report):
        preds = _make_predictions("m1", correct=18, incorrect=2)
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        reports = compute_market_reports()
        reports = compute_ev(reports)
        assert reports[0].ev is not None
        assert reports[0].ev == pytest.approx(0.4, abs=0.01)  # 90% - 50%

    def test_ev_none_for_small_sample(self, tmp_outcomes, tmp_report):
        preds = _make_predictions("tiny", correct=3, incorrect=1)
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        reports = compute_market_reports()
        reports = compute_ev(reports)
        assert reports[0].ev is None


class TestFeedbackCycle:
    def test_full_cycle(self, tmp_outcomes, tmp_report, tmp_retrain):
        preds = (
            _make_predictions("good", correct=18, incorrect=2) +
            _make_predictions("bad", correct=3, incorrect=22)
        )
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        report = run_feedback_cycle()

        assert report.total_evaluated > 0
        assert len(report.markets) == 2
        assert tmp_report.exists()

        # Should recommend excluding the bad market
        exclude_recs = [r for r in report.recommendations if "EXCLUDE" in r]
        assert len(exclude_recs) == 1
        assert "bad" in exclude_recs[0]

        # Should flag the good market as star
        star_recs = [r for r in report.recommendations if "STAR" in r]
        assert len(star_recs) == 1

    def test_retrain_triggered_on_bad_accuracy(self, tmp_outcomes, tmp_report, tmp_retrain):
        preds = _make_predictions("terrible", correct=5, incorrect=30)
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        report = run_feedback_cycle()

        assert any("RETRAIN" in r for r in report.recommendations)
        assert tmp_retrain.exists()  # Trigger file written

    def test_no_retrain_on_good_accuracy(self, tmp_outcomes, tmp_report, tmp_retrain):
        preds = _make_predictions("great", correct=25, incorrect=5)
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        report = run_feedback_cycle()

        assert not any("RETRAIN" in r for r in report.recommendations)
        assert not tmp_retrain.exists()

    def test_writes_report_file(self, tmp_outcomes, tmp_report, tmp_retrain):
        preds = _make_predictions("m1", correct=10, incorrect=10)
        tmp_outcomes.write_text(json.dumps({"predictions": preds, "stats": {}}))
        run_feedback_cycle()

        assert tmp_report.exists()
        data = json.loads(tmp_report.read_text())
        assert "overall_accuracy" in data
        assert "markets" in data
        assert "recommendations" in data
