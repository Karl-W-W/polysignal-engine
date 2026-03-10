#!/usr/bin/env python3
"""
lab/moltbook_scanner.py
========================
MoltBook Knowledge Scanner — extracts agent engineering intelligence from
the MoltBook social network.

Fetches posts from targeted submolts, sanitizes them through the existing
injection-detection pipeline, and saves structured knowledge to a local
JSON knowledge base.

Usage:
    from lab.moltbook_scanner import scan_feed, scan_submolts, MoltBookScanConfig

    config = MoltBookScanConfig.from_env()
    results = scan_submolts(config)

DGX deployment:
    Called from the scanner heartbeat or as a standalone cron job.
    Feeds into brain/memory.md for Loop's learning cycle.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Import the sanitizer — defense-in-depth for all inbound content
try:
    from lab.openclaw.moltbook_polysignal_skill.sanitize import (
        sanitize_post,
        InjectionDetectedError,
        log_dropped_post,
    )
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from lab.openclaw.moltbook_polysignal_skill.sanitize import (
        sanitize_post,
        InjectionDetectedError,
        log_dropped_post,
    )


# ============================================================================
# CONFIG
# ============================================================================

MOLTBOOK_API = "https://www.moltbook.com/api/v1"
KNOWLEDGE_BASE_DEFAULT = Path("/opt/loop/data/moltbook_knowledge.json")
SCAN_STATE_DEFAULT = Path("/opt/loop/data/moltbook_scan_state.json")

# Submolts to scan for intelligence (ordered by expected value)
TARGET_SUBMOLTS = [
    "agents",               # General agent engineering discussion
    "openclaw-explorers",   # OpenClaw tips, skill development
    "trading",              # Trading strategies and signals
    "crypto",               # Crypto market intelligence
    "agentfinance",         # Agent finance / DeFi
    "tooling",              # Developer tooling, frameworks
    "security",             # Security research, vuln disclosures
    "infrastructure",       # Infrastructure, deployment patterns
    "builds",               # Agent builds and showcases
    "signals",              # Our submolt — monitor competitors
]

# Keywords that indicate high-value posts (for relevance scoring)
HIGH_VALUE_KEYWORDS = [
    "polymarket", "prediction market", "signal detection", "xgboost",
    "langgraph", "langchain", "openclaw", "nvidia", "dgx", "ollama",
    "autonomous", "pipeline", "accuracy", "backtesting", "orderbook",
    "clob", "risk management", "feature engineering", "reinforcement",
    "fine-tuning", "rag", "agent loop", "self-improvement", "retrain",
    "sentiment", "alpha", "edge", "sharpe", "kelly criterion",
    "prompt injection", "security", "sandbox", "firejail",
]


@dataclass
class MoltBookScanConfig:
    """Scanner configuration."""
    jwt: str
    api_base: str = MOLTBOOK_API
    knowledge_base_path: Path = KNOWLEDGE_BASE_DEFAULT
    scan_state_path: Path = SCAN_STATE_DEFAULT
    target_submolts: list = field(default_factory=lambda: list(TARGET_SUBMOLTS))
    posts_per_submolt: int = 25
    request_delay: float = 1.5  # Seconds between API calls (respect rate limits)

    @classmethod
    def from_env(cls) -> "MoltBookScanConfig":
        jwt = os.getenv("MOLTBOOK_JWT", "")
        if not jwt:
            raise ValueError("MOLTBOOK_JWT not set — cannot scan")
        return cls(
            jwt=jwt,
            api_base=os.getenv("MOLTBOOK_API_BASE", MOLTBOOK_API),
        )


# ============================================================================
# SCAN STATE (track what we've already seen)
# ============================================================================

@dataclass
class ScanState:
    """Persistent state for deduplication across scans."""
    seen_post_ids: list = field(default_factory=list)
    last_scan_timestamp: str = ""
    total_scans: int = 0
    total_posts_scanned: int = 0
    total_posts_saved: int = 0
    total_posts_dropped: int = 0

    @classmethod
    def load(cls, path: Path) -> "ScanState":
        if path.exists():
            data = json.loads(path.read_text())
            return cls(
                seen_post_ids=data.get("seen_post_ids", []),
                last_scan_timestamp=data.get("last_scan_timestamp", ""),
                total_scans=data.get("total_scans", 0),
                total_posts_scanned=data.get("total_posts_scanned", 0),
                total_posts_saved=data.get("total_posts_saved", 0),
                total_posts_dropped=data.get("total_posts_dropped", 0),
            )
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "seen_post_ids": self.seen_post_ids[-5000:],  # Keep last 5000
            "last_scan_timestamp": self.last_scan_timestamp,
            "total_scans": self.total_scans,
            "total_posts_scanned": self.total_posts_scanned,
            "total_posts_saved": self.total_posts_saved,
            "total_posts_dropped": self.total_posts_dropped,
        }, indent=2))


# ============================================================================
# KNOWLEDGE BASE
# ============================================================================

@dataclass
class KnowledgeEntry:
    """A sanitized, scored knowledge entry from MoltBook."""
    post_id: str
    author_id: str
    submolt: str
    timestamp: str
    extracted_signal: str
    tags: list
    relevance_score: float
    scanned_at: str

    def to_dict(self) -> dict:
        return {
            "post_id": self.post_id,
            "author_id": self.author_id,
            "submolt": self.submolt,
            "timestamp": self.timestamp,
            "extracted_signal": self.extracted_signal,
            "tags": self.tags,
            "relevance_score": self.relevance_score,
            "scanned_at": self.scanned_at,
        }


def _compute_relevance(sanitized: dict, submolt: str) -> float:
    """Score how relevant a post is to our intelligence needs (0.0 - 1.0)."""
    text = sanitized.get("extracted_signal", "").lower()
    tags = [t.lower() for t in sanitized.get("tags", [])]
    combined = f"{text} {' '.join(tags)}"

    score = 0.0
    keyword_hits = sum(1 for kw in HIGH_VALUE_KEYWORDS if kw in combined)
    score += min(keyword_hits * 0.15, 0.6)

    # Bonus for high-priority submolts
    priority_submolts = {"agents", "trading", "security", "openclaw-explorers"}
    if submolt in priority_submolts:
        score += 0.15

    # Bonus for actionable content (contains numbers, percentages, code-like patterns)
    import re
    if re.search(r"\d+\.?\d*%", text):
        score += 0.1
    if re.search(r"pip install|import |def |class ", text):
        score += 0.1

    return min(round(score, 2), 1.0)


def load_knowledge_base(path: Path) -> list[dict]:
    """Load existing knowledge base."""
    if path.exists():
        return json.loads(path.read_text())
    return []


def save_knowledge_base(entries: list[dict], path: Path) -> None:
    """Save knowledge base, keeping most recent 10,000 entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sort by relevance (highest first), then by timestamp (newest first)
    entries.sort(key=lambda e: (-e.get("relevance_score", 0), e.get("timestamp", "")))
    path.write_text(json.dumps(entries[-10000:], indent=2))


# ============================================================================
# API FETCHER
# ============================================================================

def fetch_posts(
    submolt: str,
    config: MoltBookScanConfig,
    sort: str = "new",
    limit: int = 25,
) -> list[dict]:
    """Fetch posts from a submolt via MoltBook API."""
    try:
        resp = requests.get(
            f"{config.api_base}/posts",
            headers={"Authorization": f"Bearer {config.jwt}"},
            params={"submolt": submolt, "sort": sort, "limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("posts", data.get("data", [])) if isinstance(data, dict) else data
    except requests.RequestException as e:
        logger.warning("Failed to fetch %s: %s", submolt, e)
        return []


def fetch_feed(
    config: MoltBookScanConfig,
    feed_type: str = "popular",
    limit: int = 50,
) -> list[dict]:
    """Fetch from a global feed (popular, all, home)."""
    try:
        resp = requests.get(
            f"{config.api_base}/feed",
            headers={"Authorization": f"Bearer {config.jwt}"},
            params={"sort": "hot", "limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("posts", data.get("data", [])) if isinstance(data, dict) else data
    except requests.RequestException as e:
        logger.warning("Failed to fetch feed/%s: %s", feed_type, e)
        return []


def search_posts(
    query: str,
    config: MoltBookScanConfig,
    limit: int = 25,
) -> list[dict]:
    """Semantic search across MoltBook."""
    try:
        resp = requests.get(
            f"{config.api_base}/search/posts",
            headers={"Authorization": f"Bearer {config.jwt}"},
            params={"q": query, "limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("posts", data.get("data", [])) if isinstance(data, dict) else data
    except requests.RequestException as e:
        logger.warning("Search failed for '%s': %s", query, e)
        return []


# ============================================================================
# SCANNER PIPELINE
# ============================================================================

@dataclass
class ScanResult:
    """Result of a full scan run."""
    posts_fetched: int = 0
    posts_new: int = 0
    posts_saved: int = 0
    posts_dropped: int = 0
    high_relevance: list = field(default_factory=list)  # Top entries for summary
    errors: list = field(default_factory=list)


def scan_submolts(config: MoltBookScanConfig) -> ScanResult:
    """Scan all target submolts + popular feed, sanitize, score, save."""
    state = ScanState.load(config.scan_state_path)
    kb = load_knowledge_base(config.knowledge_base_path)
    existing_ids = {e["post_id"] for e in kb}
    result = ScanResult()

    all_posts = []

    # Fetch from each target submolt
    for submolt in config.target_submolts:
        posts = fetch_posts(submolt, config, limit=config.posts_per_submolt)
        for p in posts:
            p["_submolt"] = submolt
        all_posts.extend(posts)
        time.sleep(config.request_delay)

    # Also fetch popular feed for cross-pollination
    popular = fetch_feed(config, feed_type="popular", limit=50)
    for p in popular:
        p["_submolt"] = p.get("submolt", "popular")
    all_posts.extend(popular)

    result.posts_fetched = len(all_posts)

    # Process each post through sanitizer
    for raw_post in all_posts:
        post_id = str(raw_post.get("id", ""))
        if not post_id or post_id in existing_ids or post_id in state.seen_post_ids:
            continue  # Already processed

        result.posts_new += 1
        state.seen_post_ids.append(post_id)

        try:
            sanitized = sanitize_post(raw_post)
        except InjectionDetectedError as e:
            log_dropped_post(raw_post, e)
            result.posts_dropped += 1
            state.total_posts_dropped += 1
            continue
        except Exception as e:
            result.errors.append(f"Sanitize error on {post_id}: {e}")
            continue

        # Score relevance
        submolt = raw_post.get("_submolt", "unknown")
        relevance = _compute_relevance(sanitized, submolt)

        # Only save posts with minimum relevance (noise filter)
        if relevance < 0.1:
            continue

        entry = KnowledgeEntry(
            post_id=sanitized["post_id"],
            author_id=sanitized["author_id"],
            submolt=submolt,
            timestamp=sanitized["timestamp"],
            extracted_signal=sanitized["extracted_signal"],
            tags=sanitized["tags"],
            relevance_score=relevance,
            scanned_at=datetime.now(timezone.utc).isoformat(),
        )

        kb.append(entry.to_dict())
        existing_ids.add(post_id)
        result.posts_saved += 1
        state.total_posts_saved += 1

        if relevance >= 0.4:
            result.high_relevance.append(entry.to_dict())

    # Save state and knowledge base
    state.last_scan_timestamp = datetime.now(timezone.utc).isoformat()
    state.total_scans += 1
    state.total_posts_scanned += result.posts_fetched
    state.save(config.scan_state_path)
    save_knowledge_base(kb, config.knowledge_base_path)

    return result


def scan_topics(config: MoltBookScanConfig) -> ScanResult:
    """Targeted semantic search for high-value topics."""
    state = ScanState.load(config.scan_state_path)
    kb = load_knowledge_base(config.knowledge_base_path)
    existing_ids = {e["post_id"] for e in kb}
    result = ScanResult()

    queries = [
        "prediction market signal detection accuracy",
        "autonomous agent self-improvement loop",
        "XGBoost feature engineering trading",
        "OpenClaw skill development best practices",
        "polymarket CLOB orderbook analysis",
        "agent security prompt injection defense",
        "LangGraph pipeline optimization",
    ]

    for query in queries:
        posts = search_posts(query, config, limit=10)
        result.posts_fetched += len(posts)

        for raw_post in posts:
            post_id = str(raw_post.get("id", ""))
            if not post_id or post_id in existing_ids or post_id in state.seen_post_ids:
                continue

            result.posts_new += 1
            state.seen_post_ids.append(post_id)

            try:
                sanitized = sanitize_post(raw_post)
            except InjectionDetectedError as e:
                log_dropped_post(raw_post, e)
                result.posts_dropped += 1
                continue
            except Exception:
                continue

            submolt = raw_post.get("submolt", "search")
            relevance = _compute_relevance(sanitized, submolt)
            # Search results get a relevance bonus (the search itself is targeted)
            relevance = min(relevance + 0.2, 1.0)

            entry = KnowledgeEntry(
                post_id=sanitized["post_id"],
                author_id=sanitized["author_id"],
                submolt=submolt,
                timestamp=sanitized["timestamp"],
                extracted_signal=sanitized["extracted_signal"],
                tags=sanitized["tags"],
                relevance_score=relevance,
                scanned_at=datetime.now(timezone.utc).isoformat(),
            )

            kb.append(entry.to_dict())
            existing_ids.add(post_id)
            result.posts_saved += 1

            if relevance >= 0.4:
                result.high_relevance.append(entry.to_dict())

        time.sleep(config.request_delay)

    state.last_scan_timestamp = datetime.now(timezone.utc).isoformat()
    state.save(config.scan_state_path)
    save_knowledge_base(kb, config.knowledge_base_path)

    return result


def get_knowledge_summary(path: Path = KNOWLEDGE_BASE_DEFAULT, top_n: int = 10) -> str:
    """Return a brief summary of top knowledge entries for memory injection."""
    kb = load_knowledge_base(path)
    if not kb:
        return "No MoltBook knowledge collected yet."

    high = sorted(kb, key=lambda e: -e.get("relevance_score", 0))[:top_n]
    lines = [f"MoltBook Knowledge ({len(kb)} total entries, top {top_n}):"]
    for e in high:
        lines.append(
            f"  [{e.get('relevance_score', 0):.1f}] "
            f"[{e.get('submolt', '?')}] "
            f"{e.get('extracted_signal', '')[:120]}"
        )
    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    config = MoltBookScanConfig.from_env()

    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode in ("submolts", "all"):
        print("Scanning submolts...")
        r = scan_submolts(config)
        print(f"  Fetched: {r.posts_fetched}, New: {r.posts_new}, "
              f"Saved: {r.posts_saved}, Dropped: {r.posts_dropped}")
        if r.high_relevance:
            print(f"  High-relevance posts:")
            for e in r.high_relevance[:5]:
                print(f"    [{e['relevance_score']:.1f}] {e['extracted_signal'][:100]}")

    if mode in ("topics", "all"):
        print("\nRunning topic searches...")
        r = scan_topics(config)
        print(f"  Fetched: {r.posts_fetched}, New: {r.posts_new}, "
              f"Saved: {r.posts_saved}, Dropped: {r.posts_dropped}")
        if r.high_relevance:
            print(f"  High-relevance posts:")
            for e in r.high_relevance[:5]:
                print(f"    [{e['relevance_score']:.1f}] {e['extracted_signal'][:100]}")

    if mode == "summary":
        print(get_knowledge_summary(config.knowledge_base_path))
