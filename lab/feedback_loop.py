#!/usr/bin/env python3
"""
lab/feedback_loop.py
====================
Closed feedback loop — evaluates prediction accuracy and auto-adjusts the system.

Session 26: The missing piece that makes everything compound.
Without this, predictions happen → outcomes evaluate → nothing changes.

What it does:
1. Computes per-market accuracy over recent window
2. Auto-excludes markets with accuracy < 40% (20+ samples)
3. Flags star performers (accuracy > 70%)
4. Triggers XGBoost retrain when overall accuracy drops
5. Computes EV (expected value) per market for expansion decisions
6. Writes structured report for Loop and Claude Code

Usage:
    # Run daily via trigger file or cron
    python3 -m lab.feedback_loop

    # As module
    from lab.feedback_loop import run_feedback_cycle
    report = run_feedback_cycle()

Output: lab/.feedback-report (JSON)
Side effects: may write .retrain-trigger, update EXCLUDED_MARKETS suggestions
"""

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional


# ── Configuration ────────────────────────────────────────────────────────────
OUTCOMES_FILE = Path(os.getenv(
    "OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"
))
REPORT_FILE = Path(os.getenv(
    "FEEDBACK_REPORT_FILE",
    os.path.join(os.path.dirname(__file__), ".feedback-report")
))
RETRAIN_TRIGGER = Path(os.path.join(os.path.dirname(__file__), ".retrain-trigger"))

# Thresholds
EXCLUDE_ACCURACY_THRESHOLD = 0.40    # Auto-suggest exclusion below this
EXCLUDE_MIN_SAMPLES = 20             # Need this many evaluations to judge
STAR_ACCURACY_THRESHOLD = 0.70       # Flag as star performer above this
RETRAIN_TRIGGER_THRESHOLD = 0.50     # Trigger retrain if overall accuracy below this
RETRAIN_MIN_SAMPLES = 30             # Minimum evaluated before triggering retrain
EVAL_WINDOW_DAYS = 14                # Look at last N days of data
EV_MINIMUM = 0.10                    # Minimum EV (10%) to recommend trading


@dataclass
class MarketReport:
    """Accuracy + EV analysis for a single market."""
    market_id: str
    correct: int = 0
    incorrect: int = 0
    neutral: int = 0
    total_directional: int = 0
    accuracy: float = 0.0
    dominant_hypothesis: str = ""
    avg_confidence: float = 0.0
    last_prediction_age_hours: float = 0.0
    recommendation: str = ""  # "exclude", "star", "monitor", "expand"
    ev: Optional[float] = None


@dataclass
class FeedbackReport:
    """Full feedback cycle output."""
    timestamp: str
    eval_window_days: int
    total_predictions: int
    total_evaluated: int
    overall_accuracy: float
    markets: List[Dict]
    actions_taken: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


def compute_market_reports(window_days: int = EVAL_WINDOW_DAYS) -> List[MarketReport]:
    """Compute per-market accuracy over recent window."""
    if not OUTCOMES_FILE.exists():
        return []

    data = json.loads(OUTCOMES_FILE.read_text())
    preds = data.get("predictions", [])

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    now = datetime.now(timezone.utc)

    markets: Dict[str, MarketReport] = {}

    for p in preds:
        if not p.get("evaluated"):
            continue
        mid = p.get("market_id", "unknown")
        if "fake" in str(mid):
            continue

        # Filter by evaluation time
        eval_ts = _parse_ts(p.get("evaluated_at", p.get("timestamp", "")))
        if eval_ts < cutoff:
            continue

        if mid not in markets:
            markets[mid] = MarketReport(market_id=mid)

        report = markets[mid]
        outcome = p.get("outcome", "NEUTRAL")

        if outcome == "CORRECT":
            report.correct += 1
        elif outcome == "INCORRECT":
            report.incorrect += 1
        else:
            report.neutral += 1

        # Track hypothesis distribution
        hyp = p.get("hypothesis", "Unknown")
        if hyp != "Neutral":
            report.avg_confidence += p.get("confidence", 0.0)

        # Track recency
        pred_ts = _parse_ts(p.get("timestamp", ""))
        age_hours = (now - pred_ts).total_seconds() / 3600
        report.last_prediction_age_hours = min(
            report.last_prediction_age_hours or age_hours,
            age_hours,
        )

    # Finalize stats
    for report in markets.values():
        report.total_directional = report.correct + report.incorrect
        if report.total_directional > 0:
            report.accuracy = round(report.correct / report.total_directional, 3)
            report.avg_confidence = round(
                report.avg_confidence / report.total_directional, 3
            )

        # Classify
        if report.total_directional >= EXCLUDE_MIN_SAMPLES and report.accuracy < EXCLUDE_ACCURACY_THRESHOLD:
            report.recommendation = "exclude"
        elif report.total_directional >= EXCLUDE_MIN_SAMPLES and report.accuracy >= STAR_ACCURACY_THRESHOLD:
            report.recommendation = "star"
        elif report.total_directional < 10:
            report.recommendation = "insufficient_data"
        else:
            report.recommendation = "monitor"

    return sorted(markets.values(), key=lambda r: -r.total_directional)


def compute_ev(market_reports: List[MarketReport]) -> List[MarketReport]:
    """Add EV (expected value) to each market report.

    EV = (accuracy * win_payout) - ((1 - accuracy) * loss_amount)
    For binary prediction markets: win_payout ≈ (1 - price), loss = price.
    Simplified: EV = accuracy - price.
    """
    # Get current prices from scanner status or observations
    # For now, use base rate accuracy as EV proxy (accuracy - 0.5 break-even)
    for report in market_reports:
        if report.total_directional >= 10:
            # Simple EV: how much better than coin flip
            report.ev = round(report.accuracy - 0.5, 3)
        else:
            report.ev = None

    return market_reports


def run_feedback_cycle(window_days: int = EVAL_WINDOW_DAYS) -> FeedbackReport:
    """Run a complete feedback cycle.

    Returns:
        FeedbackReport with per-market analysis and action recommendations.
    """
    market_reports = compute_market_reports(window_days)
    market_reports = compute_ev(market_reports)

    # Overall stats
    total_correct = sum(r.correct for r in market_reports)
    total_incorrect = sum(r.incorrect for r in market_reports)
    total_directional = total_correct + total_incorrect
    overall_accuracy = round(total_correct / total_directional, 3) if total_directional > 0 else 0.0

    total_preds = sum(r.correct + r.incorrect + r.neutral for r in market_reports)

    actions_taken = []
    recommendations = []

    # Action: Suggest exclusions
    for r in market_reports:
        if r.recommendation == "exclude":
            recommendations.append(
                f"EXCLUDE {r.market_id}: {r.accuracy:.0%} accuracy ({r.correct}/{r.total_directional}) — below {EXCLUDE_ACCURACY_THRESHOLD:.0%}"
            )

    # Action: Flag stars
    for r in market_reports:
        if r.recommendation == "star":
            recommendations.append(
                f"STAR {r.market_id}: {r.accuracy:.0%} accuracy ({r.correct}/{r.total_directional}) — strong performer"
            )

    # Action: EV-positive markets
    for r in market_reports:
        if r.ev is not None and r.ev >= EV_MINIMUM:
            recommendations.append(
                f"HIGH-EV {r.market_id}: EV={r.ev:+.0%} — consider increasing position"
            )

    # Action: Trigger retrain if accuracy is bad
    if total_directional >= RETRAIN_MIN_SAMPLES and overall_accuracy < RETRAIN_TRIGGER_THRESHOLD:
        recommendations.append(
            f"RETRAIN: Overall accuracy {overall_accuracy:.0%} below {RETRAIN_TRIGGER_THRESHOLD:.0%} — retrain recommended"
        )
        # Auto-trigger retrain
        try:
            RETRAIN_TRIGGER.write_text(f"feedback_loop retrain trigger {datetime.now(timezone.utc).isoformat()}\n")
            actions_taken.append("Wrote .retrain-trigger")
        except Exception:
            pass

    # Build report
    report = FeedbackReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        eval_window_days=window_days,
        total_predictions=total_preds,
        total_evaluated=total_directional,
        overall_accuracy=overall_accuracy,
        markets=[asdict(r) for r in market_reports],
        actions_taken=actions_taken,
        recommendations=recommendations,
    )

    # Write report
    _write_report(report)

    return report


def _write_report(report: FeedbackReport):
    """Write feedback report to file."""
    try:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(REPORT_FILE, "w") as f:
            json.dump(asdict(report), f, indent=2)
    except Exception:
        pass


def _parse_ts(ts_str: str) -> datetime:
    """Parse ISO timestamp, returning epoch on failure."""
    if not ts_str:
        return datetime(2020, 1, 1, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return datetime(2020, 1, 1, tzinfo=timezone.utc)


# ── Standalone entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    report = run_feedback_cycle()

    print(f"Feedback Loop Report ({report.eval_window_days}-day window)")
    print("=" * 60)
    print(f"Evaluated: {report.total_evaluated} directional predictions")
    print(f"Overall accuracy: {report.overall_accuracy:.0%}")
    print()

    if report.markets:
        print("Per-Market Breakdown:")
        for m in report.markets:
            r = MarketReport(**m)
            flag = {"exclude": "🔴", "star": "⭐", "monitor": "📊", "insufficient_data": "⚪"}.get(
                r.recommendation, "❓"
            )
            ev_str = f"EV={r.ev:+.0%}" if r.ev is not None else "EV=?"
            print(f"  {flag} {r.market_id}: {r.accuracy:.0%} ({r.correct}/{r.total_directional}) {ev_str} [{r.recommendation}]")
        print()

    if report.recommendations:
        print("Recommendations:")
        for rec in report.recommendations:
            print(f"  → {rec}")
        print()

    if report.actions_taken:
        print("Actions Taken:")
        for action in report.actions_taken:
            print(f"  ✓ {action}")
    else:
        print("No actions taken.")
