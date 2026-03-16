#!/usr/bin/env python3
"""
lab/watchdog.py
===============
Self-healing watchdog — detects pipeline failures and triggers remediation.

Session 26: Built because the base rate predictor shipped broken and produced
0 predictions for 2.5 days. Loop's heartbeat said "scanner OK" but never
checked if predictions were actually being produced.

Usage:
    # As a module (called from scanner or standalone)
    from lab.watchdog import run_watchdog_checks
    alerts = run_watchdog_checks()

    # Standalone
    python3 -m lab.watchdog

Wired into: scanner cycle (end of masterloop), or standalone cron.
Outputs: lab/.watchdog-alerts (JSON, Loop reads on heartbeat)
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional


# ── Configuration ────────────────────────────────────────────────────────────
OUTCOMES_FILE = Path(os.getenv(
    "OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"
))
SCANNER_STATUS_FILE = Path(os.getenv(
    "SCANNER_STATUS_FILE",
    os.path.join(os.path.dirname(__file__), ".scanner-status.json")
))
ALERTS_FILE = Path(os.getenv(
    "WATCHDOG_ALERTS_FILE",
    os.path.join(os.path.dirname(__file__), ".watchdog-alerts")
))
TRADING_LOG_FILE = Path(os.getenv(
    "TRADING_LOG_FILE",
    os.path.join(os.path.dirname(__file__), "trading_log.json")
))

# Thresholds
PREDICTION_DROUGHT_HOURS = 24      # Alert if 0 predictions recorded in this window
ACCURACY_ALERT_THRESHOLD = 0.40    # Alert if accuracy drops below this
ACCURACY_MIN_SAMPLES = 20          # Minimum evaluated predictions before alerting on accuracy
SCANNER_STALE_MINUTES = 15         # Alert if scanner status is older than this
MAX_CONSECUTIVE_ERRORS = 3         # Alert if scanner has this many consecutive errors


@dataclass
class WatchdogAlert:
    """A detected failure condition."""
    severity: str       # "critical", "warning", "info"
    check: str          # Name of the check that triggered
    message: str        # Human-readable description
    timestamp: str      # ISO 8601
    remediation: Optional[str] = None  # Suggested action or auto-triggered action


def check_prediction_drought(hours: int = PREDICTION_DROUGHT_HOURS) -> Optional[WatchdogAlert]:
    """Alert if no predictions have been recorded recently."""
    if not OUTCOMES_FILE.exists():
        return WatchdogAlert(
            severity="warning",
            check="prediction_drought",
            message="Outcomes file does not exist — no predictions ever recorded",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    try:
        data = json.loads(OUTCOMES_FILE.read_text())
        preds = data.get("predictions", [])
        if not preds:
            return WatchdogAlert(
                severity="critical",
                check="prediction_drought",
                message="No predictions in outcomes file at all",
                timestamp=datetime.now(timezone.utc).isoformat(),
                remediation="Check prediction_node in masterloop — base rate predictor may be failing",
            )

        # Find most recent prediction timestamp
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = [p for p in preds if not _is_fake(p) and _parse_ts(p.get("timestamp", "")) > cutoff]

        if len(recent) == 0:
            # Count how many hours since last real prediction
            real_preds = [p for p in preds if not _is_fake(p)]
            if real_preds:
                last_ts = max(_parse_ts(p.get("timestamp", "")) for p in real_preds)
                hours_ago = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
                msg = f"No predictions in {hours}h (last real prediction: {hours_ago:.0f}h ago)"
            else:
                msg = f"No real predictions ever recorded (all are test fixtures)"

            return WatchdogAlert(
                severity="critical",
                check="prediction_drought",
                message=msg,
                timestamp=datetime.now(timezone.utc).isoformat(),
                remediation="Investigate: gate too strict? markets too quiet? predictor failing?",
            )
    except Exception as e:
        return WatchdogAlert(
            severity="warning",
            check="prediction_drought",
            message=f"Failed to read outcomes file: {e}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    return None


def check_accuracy_regression() -> Optional[WatchdogAlert]:
    """Alert if recent prediction accuracy has dropped below threshold."""
    if not OUTCOMES_FILE.exists():
        return None

    try:
        data = json.loads(OUTCOMES_FILE.read_text())
        preds = data.get("predictions", [])

        # Only check recent evaluated predictions (last 7 days)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent_evaluated = [
            p for p in preds
            if p.get("evaluated") and not _is_fake(p)
            and _parse_ts(p.get("evaluated_at", p.get("timestamp", ""))) > cutoff
        ]

        if len(recent_evaluated) < ACCURACY_MIN_SAMPLES:
            return None  # Not enough data to judge

        correct = sum(1 for p in recent_evaluated if p.get("outcome") == "CORRECT")
        incorrect = sum(1 for p in recent_evaluated if p.get("outcome") == "INCORRECT")
        directional = correct + incorrect

        if directional == 0:
            return None

        accuracy = correct / directional
        if accuracy < ACCURACY_ALERT_THRESHOLD:
            return WatchdogAlert(
                severity="critical",
                check="accuracy_regression",
                message=f"Accuracy {accuracy:.0%} ({correct}/{directional}) below {ACCURACY_ALERT_THRESHOLD:.0%} threshold (7-day window)",
                timestamp=datetime.now(timezone.utc).isoformat(),
                remediation="Consider: retrain model, exclude failing markets, or review prediction logic",
            )
    except Exception:
        pass

    return None


def check_scanner_health() -> Optional[WatchdogAlert]:
    """Alert if scanner status is stale or shows errors."""
    if not SCANNER_STATUS_FILE.exists():
        return WatchdogAlert(
            severity="warning",
            check="scanner_health",
            message="Scanner status file missing — scanner may not be running",
            timestamp=datetime.now(timezone.utc).isoformat(),
            remediation="Check: systemctl --user status polysignal-scanner.service",
        )

    try:
        status = json.loads(SCANNER_STATUS_FILE.read_text())
        ts = _parse_ts(status.get("timestamp", ""))
        age_minutes = (datetime.now(timezone.utc) - ts).total_seconds() / 60

        if age_minutes > SCANNER_STALE_MINUTES:
            return WatchdogAlert(
                severity="critical",
                check="scanner_health",
                message=f"Scanner status is {age_minutes:.0f}m old (threshold: {SCANNER_STALE_MINUTES}m)",
                timestamp=datetime.now(timezone.utc).isoformat(),
                remediation="Scanner may have crashed — check journalctl or write .restart-scanner",
            )

        errors = status.get("errors", 0)
        if errors >= MAX_CONSECUTIVE_ERRORS:
            return WatchdogAlert(
                severity="warning",
                check="scanner_health",
                message=f"Scanner has {errors} errors in latest cycle",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
    except Exception as e:
        return WatchdogAlert(
            severity="warning",
            check="scanner_health",
            message=f"Failed to read scanner status: {e}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    return None


def check_paper_trade_quality() -> Optional[WatchdogAlert]:
    """Alert if all paper trades are on fake/test markets."""
    if not TRADING_LOG_FILE.exists():
        return None

    try:
        data = json.loads(TRADING_LOG_FILE.read_text())
        trades = data.get("trades", [])
        if not trades:
            return None

        # Check last 20 trades
        recent = trades[-20:]
        real_trades = [t for t in recent if not _is_fake_trade(t)]

        if len(recent) >= 10 and len(real_trades) == 0:
            return WatchdogAlert(
                severity="warning",
                check="paper_trade_quality",
                message=f"Last {len(recent)} paper trades are ALL on fake/test markets",
                timestamp=datetime.now(timezone.utc).isoformat(),
                remediation="Paper trades are coming from tests, not real scanner predictions",
            )
    except Exception:
        pass

    return None


def run_watchdog_checks() -> List[WatchdogAlert]:
    """Run all watchdog checks and return alerts."""
    alerts = []

    for check_fn in [
        check_prediction_drought,
        check_accuracy_regression,
        check_scanner_health,
        check_paper_trade_quality,
    ]:
        try:
            alert = check_fn()
            if alert:
                alerts.append(alert)
        except Exception as e:
            alerts.append(WatchdogAlert(
                severity="warning",
                check=check_fn.__name__,
                message=f"Check itself failed: {e}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

    # Write alerts to file for Loop visibility
    _write_alerts(alerts)

    return alerts


def _write_alerts(alerts: List[WatchdogAlert]):
    """Write alerts to file for Loop to read on heartbeat."""
    try:
        ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert_count": len(alerts),
            "alerts": [asdict(a) for a in alerts],
        }
        with open(ALERTS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _is_fake(pred: dict) -> bool:
    """Check if a prediction is from test fixtures."""
    mid = str(pred.get("market_id", ""))
    return "fake" in mid or mid.startswith("0xfake")


def _is_fake_trade(trade: dict) -> bool:
    """Check if a paper trade is on a fake/test market."""
    mid = str(trade.get("market_id", ""))
    title = str(trade.get("title", ""))
    return "fake" in mid or mid.startswith("0xfake") or title == "Unknown Market"


def _parse_ts(ts_str: str) -> datetime:
    """Parse an ISO timestamp string, returning epoch on failure."""
    if not ts_str:
        return datetime(2020, 1, 1, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return datetime(2020, 1, 1, tzinfo=timezone.utc)


# ── Standalone entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    alerts = run_watchdog_checks()
    if alerts:
        print(f"⚠ {len(alerts)} watchdog alert(s):")
        for a in alerts:
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(a.severity, "⚪")
            print(f"  {icon} [{a.check}] {a.message}")
            if a.remediation:
                print(f"     → {a.remediation}")
    else:
        print("✅ All watchdog checks passed")
