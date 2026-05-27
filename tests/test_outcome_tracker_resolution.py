"""
tests/test_outcome_tracker_resolution.py
========================================
Tests for the S46 resolution-based evaluator in lab/outcome_tracker.py.

The keystone test (TestKeystone) is designed to FAIL on dd70650 (the pre-S46
drift-based evaluator) and PASS on the s46-evaluator-resolution-scoring
branch. It demonstrates the change in scoring semantics, not just a new code
path: the same input record produces opposite outcomes under the two scorers.

Verification of "FAIL on drift, PASS on resolution":

    # On the branch (with the new evaluator):
    .venv/bin/python3 -m pytest tests/test_outcome_tracker_resolution.py -v
    # Expected: all green.

    # Then temporarily revert the evaluator and re-run JUST the keystone:
    git show dd70650:lab/outcome_tracker.py > /tmp/old.py
    cp /tmp/old.py lab/outcome_tracker.py   # also delete the import line
    .venv/bin/python3 -m pytest tests/test_outcome_tracker_resolution.py::TestKeystone -v
    # Expected: the keystone test FAILS with outcome="CORRECT".
    git checkout lab/outcome_tracker.py     # restore branch
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from lab.outcome_tracker import (
    OutcomeState,
    evaluate_outcomes,
    record_predictions,
)


def _make_pred(market_id, hypothesis, price, hours_ago=5, **extra):
    """Build a prediction record dict in the shape OutcomeState stores.

    Defaults to category="crypto" (4h horizon) so the pre-S46 drift
    evaluator's horizon-gate opens at hours_ago=5; this makes the
    drift-vs-resolution scoring divergence the binding behavior in
    TestKeystone, not the horizon gate.
    """
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    base = {
        "market_id": market_id,
        "hypothesis": hypothesis,
        "confidence": 0.85,
        "price_at_prediction": price,
        "timestamp": ts,
        "time_horizon": "4h",
        "cycle_number": 1,
        "xgb_p_correct": None,
        "evaluated": False,
        "outcome": None,
        "price_at_evaluation": None,
        "evaluated_at": None,
        "actual_delta": None,
        "category": "crypto",
    }
    base.update(extra)
    return base


def _seed_state(state_file, predictions):
    s = OutcomeState()
    s.predictions = predictions
    s.save(state_file)


def _load_first(state_file):
    return OutcomeState.load(state_file).predictions[0]


class TestKeystone:
    """The drift-vs-resolution keystone — FAILS on dd70650, PASSES on branch."""

    def test_bullish_on_resolved_no_market_marks_INCORRECT_not_CORRECT(
        self, monkeypatch, tmp_path
    ):
        """A Bullish call on a market that resolved NO.

        Pre-S46 (drift scoring): the live current price (0.41) is +0.01 above
        the entry price (0.40), exceeds MIN_MOVE_THRESHOLD=0.0005, and the
        bull bet wins on direction → outcome="CORRECT".  But this is wrong —
        the market actually resolved NO; the +0.01 drift was noise on the
        path to zero.

        Post-S46 (resolution scoring): the gamma resolution check sees
        closed=true, outcome0_price=0.0 → resolved_no → outcome="INCORRECT".

        Same input record. Opposite verdicts. The whole point.
        """
        state_file = tmp_path / "outcomes.json"
        _seed_state(state_file, [
            _make_pred("566188", "Bullish", price=0.40, hours_ago=5),
        ])

        def fake_lookup(market_id):
            assert market_id == "566188"
            return ("resolved_no", {
                "question": "Will Man City win the 2025-26 EPL?",
                "closed": True,
                "outcome0_price_now": 0.0,
                "outcomes": ["Yes", "No"],
                "outcome_prices": ["0.0", "1.0"],
            })

        monkeypatch.setattr(
            "lab.outcome_tracker.lookup_resolution",
            fake_lookup,
            raising=False,  # so this test is also IMPORTABLE on dd70650
        )

        # Current observation shows +0.01 drift — would mark CORRECT under
        # the old drift scorer; the new resolution scorer ignores this and
        # asks gamma instead.
        result = evaluate_outcomes(
            current_observations=[
                {"market_id": "566188", "current_price": 0.41, "title": "Man City"},
            ],
            state_path=state_file,
        )

        pred = _load_first(state_file)
        assert pred["evaluated"] is True, "Resolved market must be marked evaluated"
        assert pred["outcome"] == "INCORRECT", (
            f"Resolution scoring: Bullish on resolved-NO market must be INCORRECT. "
            f"Got outcome={pred['outcome']!r}. If this says 'CORRECT', "
            f"the drift-based scorer (MIN_MOVE_THRESHOLD=0.0005 vs +0.01 drift) "
            f"is still active and the S46 port has not been applied."
        )
        assert pred["resolved_outcome"] == "NO"
        assert pred["resolution_status"] == "resolved_no"
        assert result["correct"] == 0 and result["incorrect"] == 1


class TestResolutionScoringPaths:
    """Each resolution status maps to the right outcome."""

    def test_bullish_on_resolved_yes_marks_CORRECT(self, monkeypatch, tmp_path):
        state_file = tmp_path / "outcomes.json"
        _seed_state(state_file, [_make_pred("m1", "Bullish", 0.55)])
        monkeypatch.setattr(
            "lab.outcome_tracker.lookup_resolution",
            lambda mid: ("resolved_yes", {"outcome0_price_now": 1.0, "closed": True}),
            raising=False,
        )
        evaluate_outcomes([], state_path=state_file)
        pred = _load_first(state_file)
        assert pred["outcome"] == "CORRECT"
        assert pred["resolved_outcome"] == "YES"

    def test_bearish_on_resolved_no_marks_CORRECT(self, monkeypatch, tmp_path):
        state_file = tmp_path / "outcomes.json"
        _seed_state(state_file, [_make_pred("m1", "Bearish", 0.40)])
        monkeypatch.setattr(
            "lab.outcome_tracker.lookup_resolution",
            lambda mid: ("resolved_no", {"outcome0_price_now": 0.0, "closed": True}),
            raising=False,
        )
        evaluate_outcomes([], state_path=state_file)
        pred = _load_first(state_file)
        assert pred["outcome"] == "CORRECT"
        assert pred["resolved_outcome"] == "NO"

    def test_bearish_on_resolved_yes_marks_INCORRECT(self, monkeypatch, tmp_path):
        state_file = tmp_path / "outcomes.json"
        _seed_state(state_file, [_make_pred("m1", "Bearish", 0.60)])
        monkeypatch.setattr(
            "lab.outcome_tracker.lookup_resolution",
            lambda mid: ("resolved_yes", {"outcome0_price_now": 1.0, "closed": True}),
            raising=False,
        )
        evaluate_outcomes([], state_path=state_file)
        pred = _load_first(state_file)
        assert pred["outcome"] == "INCORRECT"

    def test_ambiguous_resolution_marks_AMBIGUOUS_not_correct(
        self, monkeypatch, tmp_path
    ):
        """Refund / void / multi-outcome markets must NOT count toward
        correct/incorrect — they have no directional ground truth."""
        state_file = tmp_path / "outcomes.json"
        _seed_state(state_file, [_make_pred("m1", "Bullish", 0.5)])
        monkeypatch.setattr(
            "lab.outcome_tracker.lookup_resolution",
            lambda mid: ("ambiguous", {"outcome0_price_now": 0.5, "closed": True}),
            raising=False,
        )
        result = evaluate_outcomes([], state_path=state_file)
        pred = _load_first(state_file)
        assert pred["outcome"] == "AMBIGUOUS"
        assert pred["resolved_outcome"] is None
        assert result["correct"] == 0 and result["incorrect"] == 0
        assert result["neutral"] == 1

    def test_unresolved_market_stays_pending(self, monkeypatch, tmp_path):
        """The pre-S46 evaluator would mark anything past the 4h horizon;
        S46 only commits when the market actually resolves."""
        state_file = tmp_path / "outcomes.json"
        _seed_state(state_file, [_make_pred("m1", "Bullish", 0.5, hours_ago=240)])
        monkeypatch.setattr(
            "lab.outcome_tracker.lookup_resolution",
            lambda mid: ("unresolved", {"closed": False, "outcome0_price_now": 0.5}),
            raising=False,
        )
        result = evaluate_outcomes([], state_path=state_file)
        pred = _load_first(state_file)
        assert pred["evaluated"] is False, (
            "Unresolved market must stay pending — no ground truth yet"
        )
        assert pred.get("outcome") is None
        assert result["correct"] == 0 and result["incorrect"] == 0

    def test_not_found_market_stays_pending(self, monkeypatch, tmp_path):
        state_file = tmp_path / "outcomes.json"
        _seed_state(state_file, [_make_pred("m1", "Bullish", 0.5)])
        monkeypatch.setattr(
            "lab.outcome_tracker.lookup_resolution",
            lambda mid: ("not_found", {}),
            raising=False,
        )
        evaluate_outcomes([], state_path=state_file)
        pred = _load_first(state_file)
        assert pred["evaluated"] is False


class TestS46Behaviors:
    """Behavior changes the S46 port introduces."""

    def test_horizon_no_longer_gates_resolved_market(self, monkeypatch, tmp_path):
        """Pre-S46 wouldn't evaluate a 4h prediction made 1 hour ago. S46
        evaluates as soon as the market resolves, regardless of horizon."""
        state_file = tmp_path / "outcomes.json"
        _seed_state(state_file, [_make_pred("m1", "Bullish", 0.5, hours_ago=1)])
        monkeypatch.setattr(
            "lab.outcome_tracker.lookup_resolution",
            lambda mid: ("resolved_yes", {"outcome0_price_now": 1.0, "closed": True}),
            raising=False,
        )
        evaluate_outcomes([], state_path=state_file)
        pred = _load_first(state_file)
        assert pred["evaluated"] is True, (
            "S46 must evaluate as soon as the market resolves, "
            "not wait for the (now-meaningless) 4h horizon"
        )
        assert pred["outcome"] == "CORRECT"

    def test_repeat_market_id_caches_one_gamma_lookup(self, monkeypatch, tmp_path):
        """Same market appearing on multiple unevaluated rows = one HTTP."""
        state_file = tmp_path / "outcomes.json"
        _seed_state(state_file, [
            _make_pred("m1", "Bullish", 0.5),
            _make_pred("m1", "Bullish", 0.5),
            _make_pred("m1", "Bullish", 0.5),
        ])
        calls = []

        def counting_lookup(mid):
            calls.append(mid)
            return ("resolved_yes", {"outcome0_price_now": 1.0, "closed": True})

        monkeypatch.setattr(
            "lab.outcome_tracker.lookup_resolution",
            counting_lookup,
            raising=False,
        )
        evaluate_outcomes([], state_path=state_file)
        assert len(calls) == 1, f"Expected 1 cached gamma lookup, got {len(calls)}"

    def test_fake_market_id_is_skipped_without_http(self, monkeypatch, tmp_path):
        """0xfake_btc and friends (test pollution per S42) must never hit gamma."""
        state_file = tmp_path / "outcomes.json"
        _seed_state(state_file, [_make_pred("0xfake_btc", "Bullish", 0.5)])
        called = []
        monkeypatch.setattr(
            "lab.outcome_tracker.lookup_resolution",
            lambda mid: (called.append(mid) or ("resolved_yes", {"outcome0_price_now": 1.0, "closed": True})),
            raising=False,
        )
        evaluate_outcomes([], state_path=state_file)
        assert called == [], f"Fake market id must be skipped, but lookup was called: {called}"
        pred = _load_first(state_file)
        assert pred["evaluated"] is False

    def test_record_predictions_does_not_write_dual_horizon_sibling(
        self, tmp_path
    ):
        """S39 dual-horizon (4h + 24h paired write) is dropped in S46."""
        state_file = tmp_path / "outcomes.json"
        preds = [{
            "market_id": "m1",
            "hypothesis": "Bullish",
            "confidence": 0.8,
            "time_horizon": "4h",
            "category": "crypto",
        }]
        obs = [{"market_id": "m1", "current_price": 0.5, "title": "x", "category": "crypto"}]
        n = record_predictions(preds, obs, cycle_number=1, state_path=state_file)
        assert n == 1
        loaded = OutcomeState.load(state_file)
        assert len(loaded.predictions) == 1, (
            f"S46 drops the dual-horizon sibling — expected 1 row per "
            f"prediction, got {len(loaded.predictions)}"
        )
        assert loaded.predictions[0]["time_horizon"] == "4h"
