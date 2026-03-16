#!/usr/bin/env python3
"""
lab/evolution_tracker.py
========================
Tracks whether code changes actually improve the system.

The REFLECT stage — the missing piece that turns a pipeline into a learning loop.

Every meaningful change records a hypothesis:
  "This change should improve X metric from Y to Z within N hours."

After the time window passes, the tracker measures the actual result and
writes a verdict: CONFIRMED, REFUTED, or INCONCLUSIVE.

This is how Loop (and Claude Code) learn which types of changes work and which
don't. Without this, we're coding blind — deploying changes and hoping.

Usage:
    # Record a hypothesis when making a change
    from lab.evolution_tracker import record_hypothesis
    record_hypothesis(
        change_id="session26-bearish-unban",
        description="Remove bearish ban for base rate predictor",
        metric="predictions_per_cycle",
        baseline=0,
        expected=1,
        window_hours=24,
    )

    # Later: evaluate all pending hypotheses
    from lab.evolution_tracker import evaluate_pending
    verdicts = evaluate_pending()

    # Review evolution history
    from lab.evolution_tracker import get_evolution_summary
    print(get_evolution_summary())

Output: lab/.evolution-log.jsonl (append-only)
"""

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Callable, Dict


# ── Configuration ────────────────────────────────────────────────────────────
EVOLUTION_LOG = Path(os.getenv(
    "EVOLUTION_LOG",
    os.path.join(os.path.dirname(__file__), ".evolution-log.jsonl")
))


@dataclass
class Hypothesis:
    """A recorded prediction about a code change's impact."""
    change_id: str              # Unique ID (e.g., "session26-bearish-unban")
    description: str            # What the change does
    metric: str                 # What we're measuring (e.g., "predictions_per_cycle")
    baseline: float             # Value before the change
    expected: float             # Expected value after the change
    window_hours: float         # How long to wait before measuring
    recorded_at: str = ""       # ISO 8601
    author: str = ""            # Who made the change ("claude_code", "loop", "human")
    status: str = "pending"     # "pending", "confirmed", "refuted", "inconclusive"
    actual: Optional[float] = None
    evaluated_at: Optional[str] = None
    verdict_reason: str = ""


# ── Metric Collectors ────────────────────────────────────────────────────────
# Each metric has a function that returns its current value.
# Add new metrics here as we track more things.

def _get_predictions_per_cycle() -> Optional[float]:
    """Average predictions per cycle from scanner status."""
    status_path = Path(os.path.dirname(__file__)) / ".scanner-status.json"
    if not status_path.exists():
        return None
    try:
        data = json.loads(status_path.read_text())
        return float(data.get("predictions", 0))
    except Exception:
        return None


def _get_overall_accuracy() -> Optional[float]:
    """Overall prediction accuracy from outcomes file."""
    outcomes_path = Path(os.getenv("OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"))
    if not outcomes_path.exists():
        return None
    try:
        data = json.loads(outcomes_path.read_text())
        stats = data.get("stats", {})
        return float(stats.get("accuracy", 0))
    except Exception:
        return None


def _get_recent_accuracy_7d() -> Optional[float]:
    """Accuracy over last 7 days only."""
    try:
        from lab.feedback_loop import compute_market_reports
        reports = compute_market_reports(window_days=7)
        total_correct = sum(r.correct for r in reports)
        total_incorrect = sum(r.incorrect for r in reports)
        total = total_correct + total_incorrect
        if total == 0:
            return None
        return round(total_correct / total, 3)
    except Exception:
        return None


def _get_watchdog_alert_count() -> Optional[float]:
    """Number of active watchdog alerts."""
    alerts_path = Path(os.path.dirname(__file__)) / ".watchdog-alerts"
    if not alerts_path.exists():
        return 0.0
    try:
        data = json.loads(alerts_path.read_text())
        return float(data.get("alert_count", 0))
    except Exception:
        return None


# Registry of metric collectors
METRIC_COLLECTORS: Dict[str, Callable[[], Optional[float]]] = {
    "predictions_per_cycle": _get_predictions_per_cycle,
    "overall_accuracy": _get_overall_accuracy,
    "recent_accuracy_7d": _get_recent_accuracy_7d,
    "watchdog_alerts": _get_watchdog_alert_count,
}


# ── Core Functions ───────────────────────────────────────────────────────────

def record_hypothesis(
    change_id: str,
    description: str,
    metric: str,
    baseline: float,
    expected: float,
    window_hours: float = 24,
    author: str = "unknown",
) -> Hypothesis:
    """Record a hypothesis about a code change.

    Args:
        change_id: Unique identifier for this change
        description: What the change does
        metric: Name of the metric to track (must be in METRIC_COLLECTORS)
        baseline: Current value of the metric
        expected: Expected value after the change
        window_hours: How many hours to wait before evaluating
        author: Who made the change

    Returns:
        The recorded Hypothesis
    """
    hyp = Hypothesis(
        change_id=change_id,
        description=description,
        metric=metric,
        baseline=baseline,
        expected=expected,
        window_hours=window_hours,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        author=author,
    )

    _append_log(hyp)
    return hyp


def evaluate_pending() -> List[Hypothesis]:
    """Evaluate all pending hypotheses whose windows have expired.

    Returns:
        List of hypotheses that were evaluated this round.
    """
    entries = _read_log()
    now = datetime.now(timezone.utc)
    evaluated = []

    for entry in entries:
        if entry.get("status") != "pending":
            continue

        recorded = _parse_ts(entry.get("recorded_at", ""))
        window = timedelta(hours=entry.get("window_hours", 24))

        if now - recorded < window:
            continue  # Not yet time to evaluate

        metric_name = entry.get("metric", "")
        collector = METRIC_COLLECTORS.get(metric_name)

        if not collector:
            entry["status"] = "inconclusive"
            entry["verdict_reason"] = f"Unknown metric: {metric_name}"
            entry["evaluated_at"] = now.isoformat()
            evaluated.append(Hypothesis(**{k: v for k, v in entry.items() if k in Hypothesis.__dataclass_fields__}))
            continue

        actual = collector()
        if actual is None:
            entry["status"] = "inconclusive"
            entry["verdict_reason"] = f"Could not measure {metric_name}"
            entry["evaluated_at"] = now.isoformat()
            evaluated.append(Hypothesis(**{k: v for k, v in entry.items() if k in Hypothesis.__dataclass_fields__}))
            continue

        entry["actual"] = actual
        entry["evaluated_at"] = now.isoformat()

        baseline = entry.get("baseline", 0)
        expected = entry.get("expected", 0)

        # Did it improve in the expected direction?
        expected_direction = 1 if expected > baseline else -1
        actual_direction = 1 if actual > baseline else (-1 if actual < baseline else 0)

        if expected_direction == actual_direction:
            # Moved in right direction — how close to target?
            if expected_direction > 0:
                achievement = (actual - baseline) / max(expected - baseline, 0.001)
            else:
                achievement = (baseline - actual) / max(baseline - expected, 0.001)

            if achievement >= 0.5:
                entry["status"] = "confirmed"
                entry["verdict_reason"] = f"Improved: {baseline} → {actual} (expected {expected})"
            else:
                entry["status"] = "inconclusive"
                entry["verdict_reason"] = f"Moved right direction but weak: {baseline} → {actual} (expected {expected})"
        elif actual_direction == 0:
            entry["status"] = "inconclusive"
            entry["verdict_reason"] = f"No change: {baseline} → {actual} (expected {expected})"
        else:
            entry["status"] = "refuted"
            entry["verdict_reason"] = f"Regressed: {baseline} → {actual} (expected {expected})"

        hyp = Hypothesis(**{k: v for k, v in entry.items() if k in Hypothesis.__dataclass_fields__})
        evaluated.append(hyp)

    # Rewrite log with updated entries
    if evaluated:
        _rewrite_log(entries)

    return evaluated


def get_evolution_summary() -> str:
    """Return a formatted summary of all evolution history."""
    entries = _read_log()
    if not entries:
        return "No evolution history recorded."

    confirmed = sum(1 for e in entries if e.get("status") == "confirmed")
    refuted = sum(1 for e in entries if e.get("status") == "refuted")
    inconclusive = sum(1 for e in entries if e.get("status") == "inconclusive")
    pending = sum(1 for e in entries if e.get("status") == "pending")

    lines = [
        f"Evolution Summary: {len(entries)} changes tracked",
        f"  Confirmed: {confirmed} | Refuted: {refuted} | Inconclusive: {inconclusive} | Pending: {pending}",
        "",
    ]

    for e in entries[-10:]:  # Last 10
        status_icon = {
            "confirmed": "✅", "refuted": "❌",
            "inconclusive": "❓", "pending": "⏳",
        }.get(e.get("status", ""), "?")
        lines.append(f"  {status_icon} {e.get('change_id', '?')}: {e.get('verdict_reason', e.get('description', ''))}")

    return "\n".join(lines)


# ── File I/O ─────────────────────────────────────────────────────────────────

def _append_log(hyp: Hypothesis):
    """Append a hypothesis to the evolution log."""
    EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EVOLUTION_LOG, "a") as f:
        f.write(json.dumps(asdict(hyp)) + "\n")


def _read_log() -> List[Dict]:
    """Read all entries from evolution log."""
    if not EVOLUTION_LOG.exists():
        return []
    entries = []
    for line in EVOLUTION_LOG.read_text().strip().split("\n"):
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _rewrite_log(entries: List[Dict]):
    """Rewrite the entire log (used after evaluation updates)."""
    EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EVOLUTION_LOG, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _parse_ts(ts_str: str) -> datetime:
    if not ts_str:
        return datetime(2020, 1, 1, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return datetime(2020, 1, 1, tzinfo=timezone.utc)


# ── Standalone ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "evaluate":
        verdicts = evaluate_pending()
        if verdicts:
            print(f"Evaluated {len(verdicts)} hypothesis(es):")
            for v in verdicts:
                print(f"  [{v.status}] {v.change_id}: {v.verdict_reason}")
        else:
            print("No pending hypotheses ready for evaluation.")
    else:
        print(get_evolution_summary())
