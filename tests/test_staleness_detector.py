"""Tests for the staleness detector helper (workflows.masterloop._check_staleness).

S45 fix (2026-05-25): the staleness detector used to read predictions[-10:]
(position-based) and cold-start-blocked the scanner for ~10 min after every
universe change. The fix filters by `timestamp` instead. The first and last
tests in this file fail on the old position-based logic and pass on the
time-based one — the fix is verified, not asserted.
"""
from datetime import datetime, timezone, timedelta

from workflows.masterloop import _check_staleness


def _pred(mid, hyp, conf, ts):
    return {
        "market_id": mid,
        "hypothesis": hyp,
        "confidence": conf,
        "timestamp": ts.isoformat() if isinstance(ts, datetime) else ts,
    }


class TestStalenessTimeRecency:
    """The S45 fix: stale OLD records must not block a fresh universe."""

    def test_old_stale_records_do_not_block_fresh_universe(self):
        """Reproduces the S45 cold-start bug.

        Twelve identical predictions from 2 hours ago, then 1 fresh distinct
        candidate now. The old position-based detector took the last 10 of the
        12 stale records (all one signature), saw len(signatures) == 1, also
        saw current_sigs <= 2, and cooldown-skipped the cycle. The time-based
        detector filters the 2-hour-old records out of the window and
        silently allows.
        """
        now = datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc)
        old_ts = now - timedelta(hours=2)
        stored = [_pred("665374", "Bullish", 0.8, old_ts) for _ in range(12)]
        current = [_pred("999111", "Bullish", 0.7, now)]
        should_skip, _ = _check_staleness(stored, current, cycle_number=1, now=now)
        assert should_skip is False, (
            "S45 fix regression: stale records older than the lookback window "
            "must not block a fresh universe"
        )

    def test_recent_stuck_loop_is_still_caught(self):
        """The detector must still fire when the predictor IS stuck in a
        recent loop (6 identical predictions in the last 30 min, cooldown not
        expired, current batch also non-diverse)."""
        now = datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc)
        stored = [
            _pred("X", "Bullish", 0.8, now - timedelta(minutes=i + 1))
            for i in range(6)
        ]
        current = [_pred("X", "Bullish", 0.8, now)]
        should_skip, msg = _check_staleness(stored, current, cycle_number=1, now=now)
        assert should_skip is True
        assert "STALE" in msg
        assert "Skipping" in msg

    def test_cooldown_lets_recent_stuck_loop_through_periodically(self):
        """Even when stuck, the cooldown allows a probe every N cycles."""
        now = datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc)
        stored = [
            _pred("X", "Bullish", 0.8, now - timedelta(minutes=i + 1))
            for i in range(6)
        ]
        current = [_pred("X", "Bullish", 0.8, now)]
        # cycle 6 % 6 == 0 → cooldown expired
        should_skip, msg = _check_staleness(stored, current, cycle_number=6, now=now)
        assert should_skip is False
        assert "cooldown expired" in msg

    def test_diverse_current_batch_overrides_stale_history(self):
        """If history is monotonous but current batch is varied, allow
        through — unchanged from S25/S27 logic."""
        now = datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc)
        stored = [
            _pred("X", "Bullish", 0.8, now - timedelta(minutes=i + 1))
            for i in range(6)
        ]
        current = [
            _pred("A", "Bullish", 0.7, now),
            _pred("B", "Bullish", 0.7, now),
            _pred("C", "Bullish", 0.8, now),
        ]
        should_skip, msg = _check_staleness(stored, current, cycle_number=1, now=now)
        assert should_skip is False
        assert "current batch diverse" in msg

    def test_thin_recent_window_skipped_silently(self):
        """If fewer than STALE_MIN_RECENT predictions are in the window, the
        check does nothing — small or cold-start batches don't false-positive."""
        now = datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc)
        stored = [
            _pred("X", "Bullish", 0.8, now - timedelta(minutes=5)),
            _pred("X", "Bullish", 0.8, now - timedelta(minutes=4)),
        ]
        current = [_pred("X", "Bullish", 0.8, now)]
        should_skip, msg = _check_staleness(stored, current, cycle_number=1, now=now)
        assert should_skip is False
        assert msg == ""

    def test_history_diverse_silently_allows(self):
        """When the recent history has >2 unique signatures, the check returns
        silently — the predictor is not stuck."""
        now = datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc)
        stored = [
            _pred("A", "Bullish", 0.8, now - timedelta(minutes=1)),
            _pred("B", "Bullish", 0.7, now - timedelta(minutes=2)),
            _pred("C", "Bullish", 0.7, now - timedelta(minutes=3)),
            _pred("D", "Bullish", 0.8, now - timedelta(minutes=4)),
            _pred("E", "Bullish", 0.8, now - timedelta(minutes=5)),
        ]
        current = [_pred("F", "Bullish", 0.8, now)]
        should_skip, msg = _check_staleness(stored, current, cycle_number=1, now=now)
        assert should_skip is False
        assert msg == ""


class TestStalenessRegression:
    """Pin specifically that the S44 PSG/US-Iran scenario no longer blocks."""

    def test_s44_psg_us_iran_history_does_not_block_new_universe(self):
        """The exact scenario observed live 2026-05-25 cycle 2: the trailing
        10 records in prediction_outcomes.json were five (566136 PSG @ 0.8) +
        five (665374 US-Iran @ 0.8), all from 11 days ago. With the old
        detector, current cycle's 2 distinct fresh predictions got
        cooldown-skipped. The fix lets them through because the 11-day-old
        records are outside the time window."""
        now = datetime(2026, 5, 25, 15, 13, tzinfo=timezone.utc)
        ago = now - timedelta(days=11)
        stored = (
            [_pred("566136", "Bullish", 0.8, ago) for _ in range(5)]
            + [_pred("665374", "Bullish", 0.8, ago) for _ in range(5)]
        )
        # cycle 2, like the live observation
        current = [
            _pred("999111", "Bullish", 0.72, now),
            _pred("888222", "Neutral", 0.5, now),
        ]
        should_skip, _ = _check_staleness(stored, current, cycle_number=2, now=now)
        assert should_skip is False, (
            "S45 regression: 11-day-old PSG/US-Iran records must not block "
            "a fresh short-horizon universe in cycle 2"
        )
