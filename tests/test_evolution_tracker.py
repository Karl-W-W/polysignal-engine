#!/usr/bin/env python3
"""Tests for lab/evolution_tracker.py — evolution tracking (REFLECT stage)."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from lab.evolution_tracker import (
    record_hypothesis,
    evaluate_pending,
    get_evolution_summary,
    Hypothesis,
    METRIC_COLLECTORS,
)


@pytest.fixture
def tmp_log(tmp_path, monkeypatch):
    path = tmp_path / ".evolution-log.jsonl"
    monkeypatch.setattr("lab.evolution_tracker.EVOLUTION_LOG", path)
    return path


class TestRecordHypothesis:
    def test_creates_log_file(self, tmp_log):
        record_hypothesis(
            change_id="test-1",
            description="Test change",
            metric="predictions_per_cycle",
            baseline=0,
            expected=1,
            author="test",
        )
        assert tmp_log.exists()
        lines = tmp_log.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["change_id"] == "test-1"
        assert entry["status"] == "pending"

    def test_appends_multiple(self, tmp_log):
        record_hypothesis("a", "First", "m", 0, 1, author="test")
        record_hypothesis("b", "Second", "m", 0, 1, author="test")
        lines = tmp_log.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_records_timestamp(self, tmp_log):
        hyp = record_hypothesis("c", "Third", "m", 0, 1, author="test")
        assert hyp.recorded_at != ""


class TestEvaluatePending:
    def test_no_entries(self, tmp_log):
        verdicts = evaluate_pending()
        assert verdicts == []

    def test_skips_not_yet_due(self, tmp_log):
        record_hypothesis("future", "Not yet", "predictions_per_cycle", 0, 1,
                         window_hours=48, author="test")
        verdicts = evaluate_pending()
        assert len(verdicts) == 0

    def test_evaluates_due_hypothesis(self, tmp_log, monkeypatch):
        # Write a hypothesis that's already expired
        hyp = {
            "change_id": "old-change",
            "description": "Old change",
            "metric": "predictions_per_cycle",
            "baseline": 0.0,
            "expected": 5.0,
            "window_hours": 1,
            "recorded_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            "author": "test",
            "status": "pending",
            "actual": None,
            "evaluated_at": None,
            "verdict_reason": "",
        }
        tmp_log.write_text(json.dumps(hyp) + "\n")

        # Mock the metric collector to return a good value
        monkeypatch.setitem(METRIC_COLLECTORS, "predictions_per_cycle",
                           lambda: 3.0)

        verdicts = evaluate_pending()
        assert len(verdicts) == 1
        assert verdicts[0].status == "confirmed"
        assert verdicts[0].actual == 3.0

    def test_refutes_when_regressed(self, tmp_log, monkeypatch):
        hyp = {
            "change_id": "bad-change",
            "description": "Bad change",
            "metric": "overall_accuracy",
            "baseline": 0.7,
            "expected": 0.8,
            "window_hours": 1,
            "recorded_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            "author": "test",
            "status": "pending",
            "actual": None,
            "evaluated_at": None,
            "verdict_reason": "",
        }
        tmp_log.write_text(json.dumps(hyp) + "\n")

        # Accuracy dropped
        monkeypatch.setitem(METRIC_COLLECTORS, "overall_accuracy", lambda: 0.5)

        verdicts = evaluate_pending()
        assert len(verdicts) == 1
        assert verdicts[0].status == "refuted"

    def test_inconclusive_when_metric_unavailable(self, tmp_log, monkeypatch):
        hyp = {
            "change_id": "no-data",
            "description": "No data",
            "metric": "predictions_per_cycle",
            "baseline": 0.0,
            "expected": 5.0,
            "window_hours": 1,
            "recorded_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            "author": "test",
            "status": "pending",
            "actual": None,
            "evaluated_at": None,
            "verdict_reason": "",
        }
        tmp_log.write_text(json.dumps(hyp) + "\n")
        monkeypatch.setitem(METRIC_COLLECTORS, "predictions_per_cycle", lambda: None)

        verdicts = evaluate_pending()
        assert len(verdicts) == 1
        assert verdicts[0].status == "inconclusive"

    def test_skips_already_evaluated(self, tmp_log, monkeypatch):
        hyp = {
            "change_id": "done",
            "description": "Done",
            "metric": "m",
            "baseline": 0.0,
            "expected": 1.0,
            "window_hours": 1,
            "recorded_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            "author": "test",
            "status": "confirmed",
            "actual": 1.0,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "verdict_reason": "Already done",
        }
        tmp_log.write_text(json.dumps(hyp) + "\n")

        verdicts = evaluate_pending()
        assert len(verdicts) == 0


class TestSummary:
    def test_empty_summary(self, tmp_log):
        summary = get_evolution_summary()
        assert "No evolution history" in summary

    def test_summary_with_entries(self, tmp_log):
        record_hypothesis("a", "First", "m", 0, 1, author="test")
        record_hypothesis("b", "Second", "m", 0, 1, author="test")
        summary = get_evolution_summary()
        assert "2 changes tracked" in summary
        assert "Pending: 2" in summary
