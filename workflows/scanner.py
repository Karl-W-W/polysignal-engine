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
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime, timezone

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflows.masterloop import run_cycle

# ── Configuration ────────────────────────────────────────────────────────────
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL_SECONDS", "300"))  # 5 minutes
ACTIVE_START_UTC = int(os.getenv("SCAN_ACTIVE_START_HOUR", "6"))  # 07:00 CET
ACTIVE_END_UTC = int(os.getenv("SCAN_ACTIVE_END_HOUR", "0"))     # 01:00 CET

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
        }
        with open(SCANNER_STATUS_PATH, "w") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        log.warning(f"Failed to write scanner status: {e}")


def run_scanner():
    """Main scanner loop."""
    cycle_count = 0

    log.info("=" * 60)
    log.info("PolySignal Scanner starting")
    log.info(f"  Scan interval: {SCAN_INTERVAL}s ({SCAN_INTERVAL // 60}m)")
    log.info(f"  Active hours: {ACTIVE_START_UTC:02d}:00–{ACTIVE_END_UTC:02d}:00 UTC")
    log.info("=" * 60)

    while _running:
        if not is_active_hours():
            wait = seconds_until_active()
            log.info(f"Outside active hours. Sleeping {wait // 3600}h {(wait % 3600) // 60}m until {ACTIVE_START_UTC:02d}:00 UTC")
            # Sleep in chunks so we can respond to SIGTERM
            for _ in range(wait // 10):
                if not _running:
                    break
                time.sleep(10)
            continue

        cycle_count += 1
        thread_id = f"scan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        log.info(f"--- Cycle {cycle_count} starting (thread: {thread_id}) ---")
        start = time.time()

        try:
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
            log.info(f"--- Cycle {cycle_count} complete: {status} "
                     f"({n_obs} observations, {n_preds} predictions, {n_errors} errors, {elapsed:.1f}s) ---")

            if n_errors > 0:
                for err in result["errors"]:
                    log.warning(f"  Error: {err}")

            # ── Write status file for Loop visibility (Session 19) ────────
            _write_scanner_status(cycle_count, n_obs, n_preds, n_errors, elapsed, result)

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
