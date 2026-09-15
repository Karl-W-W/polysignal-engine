#!/usr/bin/env python3
"""
workflows/scanner.py
====================
Continuous market scanner — Phase 3 of the roadmap.

Runs run_cycle() every SCAN_INTERVAL_SECONDS (default: 300 = 5 minutes).
Between 07:00–01:00 CET (active trading hours), scans continuously.
Outside that window, sleeps until next active period.

Usage:
    # Run directly
    cd /opt/loop && .venv/bin/python3 -m workflows.scanner

    # Or via systemd (see polysignal-scanner.service)
    systemctl --user start polysignal-scanner

Environment:
    SCAN_INTERVAL_SECONDS: Scan frequency (default 300)
    SCAN_ACTIVE_START_HOUR: UTC hour to start scanning (default 6 = 07:00 CET)
    SCAN_ACTIVE_END_HOUR: UTC hour to stop scanning (default 0 = 01:00 CET)
    SCAN_SLEEP_BEAT_SECONDS: while sleeping outside active hours, rewrite the
        status file this often so its mtime stays a live heartbeat (default 1500
        = 25 min; the registry's cadence is 1800 s, stale at 2x)
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime, timezone, timedelta

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflows.masterloop import run_cycle
from core.otel import cycle_span, setup_tracing

# ── Configuration ────────────────────────────────────────────────────────────
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL_SECONDS", "300"))  # 5 minutes
ACTIVE_START_UTC = int(os.getenv("SCAN_ACTIVE_START_HOUR", "6"))  # 07:00 CET
ACTIVE_END_UTC = int(os.getenv("SCAN_ACTIVE_END_HOUR", "0"))     # 01:00 CET
# Sleeping heartbeat (2026-09-15): the status file was not rewritten while the
# scanner slept 00:28Z-06:00Z, so the heartbeat registry (cadence 1800 s) called
# a healthy, sleeping process stale every night at ~01:00Z. 25 min leaves margin.
SLEEP_BEAT_SECONDS = int(os.getenv("SCAN_SLEEP_BEAT_SECONDS", "1500"))

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCANNER] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("polysignal-scanner")

# ── Graceful shutdown ────────────────────────────────────────────────────────
_running = True

def _handle_signal(signum, frame):
    global _running
    log.info(f"Received signal {signum}, shutting down gracefully...")
    _running = False

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def is_active_hours() -> bool:
    """Check if current UTC hour is within active trading window."""
    hour = datetime.now(timezone.utc).hour
    if ACTIVE_START_UTC < ACTIVE_END_UTC:
        # Simple range: e.g., 6-23
        return ACTIVE_START_UTC <= hour < ACTIVE_END_UTC
    else:
        # Wraps midnight: e.g., 6-0 means 6,7,...,23
        return hour >= ACTIVE_START_UTC or hour < ACTIVE_END_UTC


def seconds_until_active() -> int:
    """Calculate seconds until the next active period starts."""
    now = datetime.now(timezone.utc)
    hour = now.hour

    if ACTIVE_START_UTC > hour:
        # Today, later
        target_hour = ACTIVE_START_UTC
    else:
        # Tomorrow
        target_hour = ACTIVE_START_UTC + 24

    hours_until = target_hour - hour
    seconds = hours_until * 3600 - now.minute * 60 - now.second
    return max(seconds, 60)  # At least 1 minute


SCANNER_STATUS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "lab", ".scanner-status.json"
)
EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "lab", ".events.jsonl"
)


def _write_scanner_status(cycle, n_obs, n_preds, n_errors, elapsed, result):
    """Write machine-readable status for Loop to check on heartbeat."""
    try:
        import json
        from lab.experiments.bitcoin_signal import detect_signals as _ds
        status = {
            "cycle": cycle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "observations": n_obs,
            "predictions": n_preds,
            "errors": n_errors,
            "elapsed_seconds": round(elapsed, 1),
            "gate_stats": result.get("stage_timings", {}).get("prediction", 0),
            "closest_signal": getattr(_ds, "closest_miss", None),
            "state": "active",
            "until": None,
        }
        with open(SCANNER_STATUS_PATH, "w") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        log.warning(f"Failed to write scanner status: {e}")


def _write_sleeping_status(until_iso: str) -> None:
    """Rewrite the status file while sleeping outside active hours.

    Keeps every field of the last cycle's status (readers use cycle,
    observations, predictions, errors, closest_signal) and adds
    state="sleeping", until=<iso of next active window>, with a fresh
    timestamp. The file's mtime is the heartbeat the registry watches;
    the timestamp is what lab/watchdog.py checks. Both now say "alive".
    """
    try:
        import json
        status = {}
        try:
            with open(SCANNER_STATUS_PATH) as f:
                status = json.load(f)
            if not isinstance(status, dict):
                status = {}
        except (OSError, ValueError):
            status = {}
        status.setdefault("cycle", 0)
        status.setdefault("observations", 0)
        status.setdefault("predictions", 0)
        status.setdefault("errors", 0)
        status["timestamp"] = datetime.now(timezone.utc).isoformat()
        status["state"] = "sleeping"
        status["until"] = until_iso
        with open(SCANNER_STATUS_PATH, "w") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        log.warning(f"Failed to write sleeping status: {e}")


def _sleep_until_active(wait: int, sleep_fn=time.sleep, beat_every=None,
                        clock=time.monotonic) -> int:
    """Sleep `wait` seconds in <=10 s chunks (so SIGTERM is honoured), writing
    the sleeping heartbeat immediately and then every `beat_every` seconds.
    `sleep_fn` and `clock` are injectable so tests run without waiting.
    Returns the number of heartbeats written."""
    beat_every = SLEEP_BEAT_SECONDS if beat_every is None else beat_every
    until_iso = (datetime.now(timezone.utc) + timedelta(seconds=wait)).isoformat()
    beats = 0
    _write_sleeping_status(until_iso)
    beats += 1
    start = clock()
    last_beat = start
    while _running:
        elapsed = clock() - start
        if elapsed >= wait:
            break
        sleep_fn(min(10, wait - elapsed))
        if clock() - last_beat >= beat_every:
            _write_sleeping_status(until_iso)
            beats += 1
            last_beat = clock()
    return beats


def _emit_event(event_type: str, data: dict = None):
    """Append an event to the event log for Loop to watch.

    Session 26: Event-driven presence — Loop checks this file instead of
    polling scanner status. Only emits on meaningful state changes.
    """
    try:
        import json
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(data or {}),
        }
        with open(EVENTS_PATH, "a") as f:
            f.write(json.dumps(event) + "\n")
        # Cap at 500 lines to prevent unbounded growth
        try:
            with open(EVENTS_PATH, "r") as f:
                lines = f.readlines()
            if len(lines) > 500:
                with open(EVENTS_PATH, "w") as f:
                    f.writelines(lines[-200:])
        except Exception:
            pass
    except Exception:
        pass


def run_scanner():
    """Main scanner loop."""
    cycle_count = 0

    if setup_tracing("polysignal-scanner"):
        log.info("OTel tracing active → %s",
                 os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:6006"))

    log.info("=" * 60)
    log.info("PolySignal Scanner starting")
    log.info(f"  Scan interval: {SCAN_INTERVAL}s ({SCAN_INTERVAL // 60}m)")
    log.info(f"  Active hours: {ACTIVE_START_UTC:02d}:00–{ACTIVE_END_UTC:02d}:00 UTC")
    log.info("=" * 60)

    while _running:
        if not is_active_hours():
            wait = seconds_until_active()
            log.info(f"Outside active hours. Sleeping {wait // 3600}h {(wait % 3600) // 60}m until {ACTIVE_START_UTC:02d}:00 UTC "
                     f"(heartbeat every {SLEEP_BEAT_SECONDS // 60}m)")
            # Sleep in chunks so we can respond to SIGTERM; keep the
            # status file's mtime fresh so the heartbeat means "alive".
            _sleep_until_active(wait)
            continue

        cycle_count += 1
        thread_id = f"scan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        log.info(f"--- Cycle {cycle_count} starting (thread: {thread_id}) ---")
        start = time.time()

        try:
            with cycle_span(
                "scanner.cycle", cycle=cycle_count, thread_id=thread_id
            ) as span:
                result = run_cycle(
                    user_request="Scan Polymarket for crypto signals",
                    thread_id=thread_id,
                    cycle_number=cycle_count,
                )

                elapsed = time.time() - start
                status = result.get("execution_status", "UNKNOWN")
                n_obs = len(result.get("observations", []))
                n_errors = len(result.get("errors", []))

                n_preds = len(result.get("predictions", []))
                if span is not None:
                    span.set_attribute("scanner.observations", n_obs)
                    span.set_attribute("scanner.predictions", n_preds)
                    span.set_attribute("scanner.errors", n_errors)
                    span.set_attribute("scanner.status", str(status))
            log.info(f"--- Cycle {cycle_count} complete: {status} "
                     f"({n_obs} observations, {n_preds} predictions, {n_errors} errors, {elapsed:.1f}s) ---")

            if n_errors > 0:
                for err in result["errors"]:
                    log.warning(f"  Error: {err}")

            # ── Write status file for Loop visibility (Session 19) ────────
            _write_scanner_status(cycle_count, n_obs, n_preds, n_errors, elapsed, result)

            # ── Emit events for meaningful state changes (Session 26) ────
            if n_preds > 0:
                _emit_event("prediction_made", {"cycle": cycle_count, "count": n_preds})
            if n_errors > 0:
                _emit_event("error_detected", {"cycle": cycle_count, "errors": result.get("errors", [])[:3]})

            # ── Watchdog checks (Session 26) — self-healing ──────────────
            # Runs every 12th cycle (~1 hour) to avoid overhead on every 5-min scan
            if cycle_count % 12 == 0:
                try:
                    from lab.watchdog import run_watchdog_checks
                    alerts = run_watchdog_checks()
                    if alerts:
                        for a in alerts:
                            log.warning(f"  🐕 [{a.severity}] {a.check}: {a.message}")
                except Exception as wd_err:
                    log.warning(f"  Watchdog failed: {wd_err}")

            # ── Whale tracker (Session 28) — insider/whale detection ──────
            # Runs every 12th cycle, offset by 9 to avoid collision with
            # staleness cooldown (cycle 6) and watchdog (cycle 12)
            if cycle_count % 12 == 9:
                try:
                    from lab.whale_tracker import scan_all as whale_scan
                    whale_signals = whale_scan()
                    if whale_signals:
                        high = [s for s in whale_signals if s.severity == "high"]
                        if high:
                            _emit_event("whale_detected", {
                                "cycle": cycle_count,
                                "count": len(whale_signals),
                                "high_severity": len(high),
                                "markets": [s.market_id for s in high[:5]],
                            })
                        log.info(f"  🐋 Whale scan: {len(whale_signals)} signals ({len(high)} high)")
                except Exception as wh_err:
                    log.warning(f"  Whale tracker failed: {wh_err}")

        except Exception as e:
            elapsed = time.time() - start
            log.error(f"--- Cycle {cycle_count} CRASHED after {elapsed:.1f}s: {e} ---")
            # Don't crash the scanner — log and continue
            import traceback
            log.error(traceback.format_exc())

        # Wait for next cycle
        log.info(f"Next scan in {SCAN_INTERVAL}s...")
        for _ in range(SCAN_INTERVAL // 5):
            if not _running:
                break
            time.sleep(5)

    log.info("Scanner stopped.")


if __name__ == "__main__":
    run_scanner()
