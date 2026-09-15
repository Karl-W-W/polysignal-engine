"""The scanner keeps its heartbeat fresh while it sleeps outside active hours.

Finding 2026-09-10: lab/.scanner-status.json was not rewritten between the
last cycle (~00:28Z) and 06:00Z, so a heartbeat registry with an 1800 s
cadence called a healthy, sleeping scanner stale every night at ~01:00Z.
These tests inject the clock and the sleep, so nothing here waits.
"""
import json
import os
from datetime import datetime, timezone

import pytest

import workflows.scanner as sc


class FakeClock:
    """Monotonic clock advanced by the fake sleep."""
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        assert 0 < seconds <= 10, seconds   # chunks stay small for SIGTERM
        self.t += seconds


@pytest.fixture
def status_file(tmp_path, monkeypatch):
    path = tmp_path / ".scanner-status.json"
    monkeypatch.setattr(sc, "SCANNER_STATUS_PATH", str(path))
    monkeypatch.setattr(sc, "_running", True)
    return path


def _seed(path):
    path.write_text(json.dumps({
        "cycle": 44, "timestamp": "2026-09-15T00:23:00+00:00", "observations": 192,
        "predictions": 12, "errors": 1, "elapsed_seconds": 1620.4, "gate_stats": 0.2,
        "closest_signal": {"market": "x", "delta": 0.01},
    }))


def test_default_beat_is_under_the_registry_cadence():
    assert sc.SLEEP_BEAT_SECONDS <= 1800, "a 6 h cadence would hide a dead scanner by day"
    assert sc.SLEEP_BEAT_SECONDS == 1500


def test_sleeping_status_keeps_fields_and_adds_state(status_file):
    _seed(status_file)
    before = datetime.now(timezone.utc)
    sc._write_sleeping_status("2026-09-16T06:00:00+00:00")
    data = json.loads(status_file.read_text())
    # existing fields its readers use survive untouched
    assert data["cycle"] == 44 and data["observations"] == 192
    assert data["predictions"] == 12 and data["errors"] == 1
    assert data["closest_signal"] == {"market": "x", "delta": 0.01}
    # sleeping state beside them, with a fresh timestamp
    assert data["state"] == "sleeping"
    assert data["until"] == "2026-09-16T06:00:00+00:00"
    assert datetime.fromisoformat(data["timestamp"]) >= before.replace(microsecond=0)


def test_sleeping_status_without_prior_file_writes_minimal_shape(status_file):
    sc._write_sleeping_status("2026-09-16T06:00:00+00:00")
    data = json.loads(status_file.read_text())
    assert data["cycle"] == 0 and data["errors"] == 0
    assert data["state"] == "sleeping" and "timestamp" in data


def test_sleeping_status_survives_corrupt_file(status_file):
    status_file.write_text("{not json")
    sc._write_sleeping_status("2026-09-16T06:00:00+00:00")
    assert json.loads(status_file.read_text())["state"] == "sleeping"


def test_sleep_until_active_beats_at_least_every_30_min(status_file):
    """A 5 h 32 m sleep (the 00:28Z case) must rewrite the file every 25 min:
    one beat at once, then one every 1500 s -> 14 beats, none further apart
    than 1800 s (the registry's cadence), and the loop must spend the whole
    wait, not less."""
    _seed(status_file)
    clock = FakeClock()
    wait = 5 * 3600 + 32 * 60   # 19920 s
    beat_times = []
    real_write = sc._write_sleeping_status

    def spy(until_iso):
        beat_times.append(clock.t)
        real_write(until_iso)

    import unittest.mock as m
    with m.patch.object(sc, "_write_sleeping_status", spy):
        beats = sc._sleep_until_active(wait, sleep_fn=clock.sleep, clock=clock)
    assert beats == len(beat_times) == 1 + wait // 1500   # 14
    assert beat_times[0] == 0
    gaps = [b - a for a, b in zip(beat_times, beat_times[1:])]
    assert gaps and max(gaps) <= 1800
    assert clock.t >= wait                                  # slept the whole window
    data = json.loads(status_file.read_text())
    assert data["state"] == "sleeping" and data["cycle"] == 44
    assert datetime.fromisoformat(data["until"]) > datetime.now(timezone.utc)


def test_sleep_until_active_honours_custom_beat_and_short_wait(status_file):
    clock = FakeClock()
    beats = sc._sleep_until_active(60, sleep_fn=clock.sleep, beat_every=1500, clock=clock)
    assert beats == 1                      # immediate beat only
    assert clock.t == 60


def test_sleep_until_active_stops_on_shutdown_flag(status_file):
    clock = FakeClock()

    def sleep_then_sigterm(seconds):
        clock.sleep(seconds)
        if clock.t >= 30:
            sc._running = False            # what the SIGTERM handler does

    beats = sc._sleep_until_active(5 * 3600, sleep_fn=sleep_then_sigterm, clock=clock)
    assert beats == 1
    assert clock.t < 60                    # returned promptly, did not sleep 5 h
    sc._running = True


def test_active_status_marks_state_active(status_file):
    sc._write_scanner_status(cycle=45, n_obs=10, n_preds=2, n_errors=0, elapsed=3.2,
                             result={"stage_timings": {"prediction": 0.5}})
    data = json.loads(status_file.read_text())
    assert data["state"] == "active" and data["until"] is None and data["cycle"] == 45


def test_env_override_for_beat_seconds(monkeypatch):
    monkeypatch.setenv("SCAN_SLEEP_BEAT_SECONDS", "600")
    import importlib
    mod = importlib.reload(sc)
    try:
        assert mod.SLEEP_BEAT_SECONDS == 600
    finally:
        monkeypatch.delenv("SCAN_SLEEP_BEAT_SECONDS")
        importlib.reload(sc)
