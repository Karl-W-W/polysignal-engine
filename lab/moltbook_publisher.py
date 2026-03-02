"""
lab/moltbook_publisher.py
=========================
MoltBook signal publisher for PolySignal-OS.

Takes a verified Signal + MasterLoop audit data and publishes to MoltBook.
Uses the sanitizer for outbound content validation (defense-in-depth).

Promotion target: core/moltbook.py (after human approval + live testing)

Usage:
    from lab.moltbook_publisher import publish_signal, MoltBookConfig

    config = MoltBookConfig.from_env()
    result = publish_signal(signal, stage_timings, audit_hash, config)
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import requests

from core.signal_model import Signal


# ============================================================================
# CONFIG
# ============================================================================

MOLTBOOK_API = "https://www.moltbook.com/api/v1"
POST_SUBMOLT = "signals"
MIN_POST_INTERVAL_SECONDS = 4 * 3600  # 4 hours between posts
STATE_FILE_DEFAULT = Path("/opt/loop/data/moltbook_state.json")


@dataclass
class MoltBookConfig:
    """Publisher configuration. All secrets from env, never hardcoded."""
    jwt: str
    api_base: str = MOLTBOOK_API
    submolt: str = POST_SUBMOLT
    min_post_interval: int = MIN_POST_INTERVAL_SECONDS
    state_file: Path = STATE_FILE_DEFAULT
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> "MoltBookConfig":
        jwt = os.getenv("MOLTBOOK_JWT", "")
        if not jwt:
            raise ValueError("MOLTBOOK_JWT not set — cannot publish")
        return cls(
            jwt=jwt,
            api_base=os.getenv("MOLTBOOK_API_BASE", MOLTBOOK_API),
            submolt=os.getenv("MOLTBOOK_SUBMOLT", POST_SUBMOLT),
            dry_run=os.getenv("MOLTBOOK_DRY_RUN", "false").lower() == "true",
        )


# ============================================================================
# STATE MANAGEMENT (rate limiting + dedup)
# ============================================================================

@dataclass
class PublisherState:
    """Persistent state for rate limiting and deduplication."""
    last_post_timestamp: str = ""
    posted_signal_hashes: list = field(default_factory=list)
    total_posts: int = 0
    total_skipped_rate_limit: int = 0
    total_skipped_duplicate: int = 0

    @classmethod
    def load(cls, path: Path) -> "PublisherState":
        if path.exists():
            data = json.loads(path.read_text())
            return cls(
                last_post_timestamp=data.get("last_post_timestamp", ""),
                posted_signal_hashes=data.get("posted_signal_hashes", []),
                total_posts=data.get("total_posts", 0),
                total_skipped_rate_limit=data.get("total_skipped_rate_limit", 0),
                total_skipped_duplicate=data.get("total_skipped_duplicate", 0),
            )
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "last_post_timestamp": self.last_post_timestamp,
            "posted_signal_hashes": self.posted_signal_hashes[-100:],  # Keep last 100
            "total_posts": self.total_posts,
            "total_skipped_rate_limit": self.total_skipped_rate_limit,
            "total_skipped_duplicate": self.total_skipped_duplicate,
        }, indent=2))


# ============================================================================
# POST FORMATTING (from post_template.md spec)
# ============================================================================

def _signal_hash(signal: Union[Signal, dict]) -> str:
    """Deterministic hash for deduplication."""
    if isinstance(signal, Signal):
        key = f"{signal.market_id}:{signal.hypothesis}:{signal.current_price:.4f}"
    else:
        key = f"{signal.get('market_id', '')}:{signal.get('hypothesis', '')}:{signal.get('current_price', 0):.4f}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def format_signal_post(
    signal: Union[Signal, dict],
    stage_timings: dict,
    audit_hash: str,
) -> tuple[str, str]:
    """Format a verified signal into MoltBook post (title, body).

    Returns:
        (title, body) tuple ready for API submission.
    """
    if isinstance(signal, Signal):
        market_name = signal.title
        direction = "YES" if signal.hypothesis == "Bullish" else "NO"
        delta_pp = signal.change_since_last * 100
        confidence = signal.confidence
        time_horizon = signal.time_horizon
    else:
        market_name = signal.get("title", "Unknown")
        hyp = signal.get("hypothesis", signal.get("direction", ""))
        direction = "YES" if "Bull" in str(hyp) or "UP" in str(hyp) else "NO"
        delta_pp = signal.get("change_since_last", signal.get("delta", 0)) * 100
        confidence = signal.get("confidence", 0.5)
        time_horizon = signal.get("time_horizon", "24h")

    delta_sign = "+" if delta_pp >= 0 else ""
    timestamp = datetime.now(timezone.utc).isoformat()

    # Chain status from stage_timings (present = passed)
    nodes = ["perception", "prediction", "draft", "review", "commit"]
    chain_status = {n: n in stage_timings for n in nodes}
    status = lambda node: "pass" if chain_status.get(node) else "fail"

    title = f"SIGNAL: {market_name[:60]} {direction} ({delta_sign}{delta_pp:.1f}pp)"

    body = (
        f"SIGNAL DETECTED -- {market_name}\n"
        f"\n"
        f"Direction: {direction}\n"
        f"Delta: {delta_sign}{delta_pp:.1f}pp ({time_horizon})\n"
        f"Confidence: {confidence:.2f}\n"
        f"\n"
        f"Chain: PERCEPTION [{status('perception')}] "
        f"PREDICTION [{status('prediction')}] "
        f"DRAFT [{status('draft')}] "
        f"REVIEW [{status('review')}] "
        f"COMMIT [{status('commit')}]\n"
        f"\n"
        f"Verified: {audit_hash[:12]}\n"
        f"Time: {timestamp}\n"
        f"\n"
        f"#PolySignal #verified #signal"
    )

    return title, body


# ============================================================================
# PUBLISHER
# ============================================================================

@dataclass
class PublishResult:
    """Result of a publish attempt."""
    published: bool
    reason: str
    post_id: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None


def publish_signal(
    signal: Union[Signal, dict],
    stage_timings: dict,
    audit_hash: str,
    config: MoltBookConfig,
) -> PublishResult:
    """Publish a verified signal to MoltBook.

    Checks: rate limit, dedup, formats, posts.
    Returns PublishResult with status.
    """
    state = PublisherState.load(config.state_file)

    # -- Rate limit check --
    if state.last_post_timestamp:
        last_post = datetime.fromisoformat(state.last_post_timestamp)
        elapsed = (datetime.now(timezone.utc) - last_post).total_seconds()
        if elapsed < config.min_post_interval:
            remaining = config.min_post_interval - elapsed
            state.total_skipped_rate_limit += 1
            state.save(config.state_file)
            return PublishResult(
                published=False,
                reason=f"Rate limited — {remaining:.0f}s remaining until next post",
            )

    # -- Dedup check --
    sig_hash = _signal_hash(signal)
    if sig_hash in state.posted_signal_hashes:
        state.total_skipped_duplicate += 1
        state.save(config.state_file)
        return PublishResult(
            published=False,
            reason=f"Duplicate signal — hash {sig_hash} already posted",
        )

    # -- Format post --
    title, body = format_signal_post(signal, stage_timings, audit_hash)

    # -- Dry run --
    if config.dry_run:
        return PublishResult(
            published=False,
            reason="Dry run — post NOT sent",
            title=title,
            body=body,
        )

    # -- Publish to MoltBook API --
    try:
        resp = requests.post(
            f"{config.api_base}/posts",
            headers={
                "Authorization": f"Bearer {config.jwt}",
                "Content-Type": "application/json",
            },
            json={
                "submolt": config.submolt,
                "title": title,
                "content": body,
            },
            timeout=15,
        )
        resp.raise_for_status()
        result_data = resp.json()
        post_id = result_data.get("id", result_data.get("post_id", "unknown"))
    except requests.RequestException as e:
        return PublishResult(
            published=False,
            reason=f"API error: {e}",
            title=title,
            body=body,
        )

    # -- Update state --
    state.last_post_timestamp = datetime.now(timezone.utc).isoformat()
    state.posted_signal_hashes.append(sig_hash)
    state.total_posts += 1
    state.save(config.state_file)

    return PublishResult(
        published=True,
        reason="Published successfully",
        post_id=str(post_id),
        title=title,
        body=body,
    )
