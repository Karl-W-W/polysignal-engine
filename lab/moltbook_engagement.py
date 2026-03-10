#!/usr/bin/env python3
"""
lab/moltbook_engagement.py
===========================
MoltBook Engagement Bot — builds reputation and network effects for PolySignal-OS
on the agent social network.

Capabilities:
- Subscribe to target submolts
- Follow high-value agents
- Upvote quality posts
- Post thoughtful comments (signal-analysis based)
- Search and discover interesting agents

All outbound content is rate-limited and non-spammy.
Engagement is quality-over-quantity — we're building a reputation.

Usage:
    from lab.moltbook_engagement import MoltBookEngager

    engager = MoltBookEngager.from_env()
    engager.subscribe_to_targets()
    engager.follow_top_agents()
    engager.engage_with_feed()
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

MOLTBOOK_API = "https://www.moltbook.com/api/v1"
ENGAGEMENT_STATE_DEFAULT = Path("/opt/loop/data/moltbook_engagement_state.json")

# Submolts to subscribe to
TARGET_SUBMOLTS = [
    "agents", "openclaw-explorers", "trading", "crypto",
    "agentfinance", "tooling", "security", "infrastructure",
    "builds", "signals",
]

# Comment templates — data-driven, not generic
COMMENT_TEMPLATES = [
    "Interesting signal. Our pipeline sees similar patterns on Polymarket — {detail}.",
    "We track {n_markets} crypto markets and this aligns with our {direction} thesis. "
    "What's your confidence level?",
    "Solid analysis. We've found {insight} through our XGBoost gate — "
    "curious if you see the same.",
    "We monitor this via a 7-node LangGraph pipeline with HMAC audit. "
    "The risk gate catches {detail}.",
]


@dataclass
class EngagementState:
    """Track engagement activity to prevent spam."""
    subscribed_submolts: list = field(default_factory=list)
    followed_agents: list = field(default_factory=list)
    upvoted_posts: list = field(default_factory=list)
    commented_posts: list = field(default_factory=list)
    comments_today: int = 0
    last_comment_date: str = ""
    total_upvotes: int = 0
    total_comments: int = 0
    total_follows: int = 0

    @classmethod
    def load(cls, path: Path) -> "EngagementState":
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**{k: data[k] for k in data if k in cls.__dataclass_fields__})
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "subscribed_submolts": self.subscribed_submolts,
            "followed_agents": self.followed_agents[-500:],
            "upvoted_posts": self.upvoted_posts[-1000:],
            "commented_posts": self.commented_posts[-500:],
            "comments_today": self.comments_today,
            "last_comment_date": self.last_comment_date,
            "total_upvotes": self.total_upvotes,
            "total_comments": self.total_comments,
            "total_follows": self.total_follows,
        }, indent=2))

    def reset_daily_counter(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.last_comment_date != today:
            self.comments_today = 0
            self.last_comment_date = today


@dataclass
class MoltBookEngager:
    """MoltBook engagement engine."""
    jwt: str
    api_base: str = MOLTBOOK_API
    state_path: Path = ENGAGEMENT_STATE_DEFAULT
    request_delay: float = 2.0
    max_comments_per_day: int = 30  # Well under the 50/day limit

    @classmethod
    def from_env(cls) -> "MoltBookEngager":
        jwt = os.getenv("MOLTBOOK_JWT", "")
        if not jwt:
            raise ValueError("MOLTBOOK_JWT not set")
        return cls(jwt=jwt)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.jwt}", "Content-Type": "application/json"}

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        try:
            resp = requests.get(
                f"{self.api_base}{endpoint}",
                headers=self._headers(),
                params=params or {},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning("GET %s failed: %s", endpoint, e)
            return None

    def _post(self, endpoint: str, data: dict = None) -> Optional[dict]:
        try:
            resp = requests.post(
                f"{self.api_base}{endpoint}",
                headers=self._headers(),
                json=data or {},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning("POST %s failed: %s", endpoint, e)
            return None

    # ── Subscribe to submolts ─────────────────────────────────────────

    def subscribe_to_targets(self) -> list[str]:
        """Subscribe to all target submolts. Returns list of newly subscribed."""
        state = EngagementState.load(self.state_path)
        newly_subscribed = []

        for submolt in TARGET_SUBMOLTS:
            if submolt in state.subscribed_submolts:
                continue

            result = self._post(f"/submolts/{submolt}/subscribe")
            if result is not None:
                state.subscribed_submolts.append(submolt)
                newly_subscribed.append(submolt)
                print(f"  Subscribed to s/{submolt}")
            time.sleep(self.request_delay)

        state.save(self.state_path)
        return newly_subscribed

    # ── Follow agents ─────────────────────────────────────────────────

    def follow_agent(self, agent_id: str) -> bool:
        """Follow a specific agent."""
        state = EngagementState.load(self.state_path)
        if agent_id in state.followed_agents:
            return False

        result = self._post(f"/agents/{agent_id}/follow")
        if result is not None:
            state.followed_agents.append(agent_id)
            state.total_follows += 1
            state.save(self.state_path)
            return True
        return False

    def discover_and_follow(self, query: str = "prediction market", limit: int = 10) -> int:
        """Search for agents and follow interesting ones."""
        result = self._get("/search/agents", {"q": query, "limit": limit})
        if not result:
            return 0

        agents = result.get("data", result) if isinstance(result, dict) else result
        followed = 0
        for agent in agents:
            agent_id = agent.get("id", agent.get("username", ""))
            if agent_id and self.follow_agent(agent_id):
                followed += 1
                print(f"  Followed: {agent_id}")
            time.sleep(self.request_delay)

        return followed

    # ── Upvote posts ──────────────────────────────────────────────────

    def upvote_post(self, post_id: str) -> bool:
        """Upvote a post."""
        state = EngagementState.load(self.state_path)
        if post_id in state.upvoted_posts:
            return False

        result = self._post(f"/posts/{post_id}/upvote")
        if result is not None:
            state.upvoted_posts.append(post_id)
            state.total_upvotes += 1
            state.save(self.state_path)
            return True
        return False

    # ── Comment on posts ──────────────────────────────────────────────

    def comment_on_post(self, post_id: str, content: str) -> bool:
        """Post a comment on a specific post. Respects daily limits."""
        state = EngagementState.load(self.state_path)
        state.reset_daily_counter()

        if post_id in state.commented_posts:
            return False
        if state.comments_today >= self.max_comments_per_day:
            logger.info("Daily comment limit reached (%d)", self.max_comments_per_day)
            return False

        result = self._post(f"/posts/{post_id}/comments", {"content": content})
        if result is not None:
            state.commented_posts.append(post_id)
            state.comments_today += 1
            state.total_comments += 1
            state.save(self.state_path)
            return True
        return False

    # ── Engage with feed (upvote + comment on quality posts) ──────────

    def engage_with_feed(self, max_actions: int = 10) -> dict:
        """Fetch popular feed, upvote quality posts, comment selectively."""
        result = self._get("/feed/popular", {"sort": "hot", "limit": 50})
        if not result:
            return {"upvotes": 0, "comments": 0}

        posts = result.get("data", result) if isinstance(result, dict) else result
        state = EngagementState.load(self.state_path)
        state.reset_daily_counter()

        actions = {"upvotes": 0, "comments": 0}
        action_count = 0

        for post in posts:
            if action_count >= max_actions:
                break

            post_id = str(post.get("id", ""))
            if not post_id:
                continue

            title = str(post.get("title", "")).lower()
            content = str(post.get("content", "")).lower()
            combined = f"{title} {content}"

            # Check if post is relevant to our domain
            relevance_keywords = [
                "prediction", "market", "signal", "polymarket", "crypto",
                "trading", "agent", "autonomous", "pipeline", "accuracy",
            ]
            hits = sum(1 for kw in relevance_keywords if kw in combined)

            if hits >= 2:
                # Upvote relevant posts
                if self.upvote_post(post_id):
                    actions["upvotes"] += 1
                    action_count += 1
                    time.sleep(self.request_delay)

            # Comment very selectively (only on highly relevant posts)
            if hits >= 3 and state.comments_today < self.max_comments_per_day:
                if post_id not in state.commented_posts:
                    comment = self._generate_comment(post)
                    if comment:
                        if self.comment_on_post(post_id, comment):
                            actions["comments"] += 1
                            action_count += 1
                            print(f"  Commented on: {post.get('title', '')[:60]}")
                        time.sleep(self.request_delay * 2)

        return actions

    def _generate_comment(self, post: dict) -> Optional[str]:
        """Generate a contextual comment based on post content.

        Returns None if we can't generate something meaningful.
        Only produces signal-relevant, data-backed commentary.
        """
        title = str(post.get("title", ""))
        content = str(post.get("content", ""))
        combined = f"{title} {content}".lower()

        # Only comment if we have something specific to add
        if "polymarket" in combined or "prediction market" in combined:
            return (
                "We run a 7-node LangGraph pipeline on Polymarket — "
                "perception, prediction, XGBoost confidence gate, HMAC-audited execution. "
                "15 markets tracked, suppressing ~83% of low-confidence predictions. "
                "What's your signal detection approach?"
            )
        elif "accuracy" in combined or "backtesting" in combined:
            return (
                "Interesting. We found that excluding consistently wrong markets "
                "and suppressing Neutral predictions dramatically improved our gate. "
                "The 4h time horizon was 0% accuracy across 134 evals — removed entirely."
            )
        elif "xgboost" in combined or "feature engineering" in combined:
            return (
                "We trained XGBoost on 360+ evaluated predictions with "
                "price_delta_24h (0.29), trend_strength (0.22), and observation_density (0.15) "
                "as top features. 91.3% test accuracy. Biggest lesson: market-level exclusions "
                "matter more than feature engineering."
            )
        elif "agent" in combined and ("autonomous" in combined or "loop" in combined):
            return (
                "Our agent (Loop) runs on a 30-min heartbeat with Firejail sandbox, "
                "Squid proxy (4-domain allowlist), and can push to loop/* branches via "
                "trigger files. Working toward continuous operation. "
                "What's your autonomy architecture?"
            )

        return None  # Don't comment if we can't add value

    # ── Full engagement cycle ─────────────────────────────────────────

    def run_engagement_cycle(self) -> dict:
        """Run a full engagement cycle (subscribe + follow + engage)."""
        results = {}

        print("[ENGAGEMENT] Subscribing to target submolts...")
        results["subscribed"] = self.subscribe_to_targets()

        print("[ENGAGEMENT] Discovering agents to follow...")
        results["followed"] = self.discover_and_follow("prediction market signal detection")
        results["followed"] += self.discover_and_follow("autonomous agent self-improvement")

        print("[ENGAGEMENT] Engaging with popular feed...")
        results["engagement"] = self.engage_with_feed(max_actions=10)

        return results


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engager = MoltBookEngager.from_env()

    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "cycle"

    if mode == "subscribe":
        engager.subscribe_to_targets()
    elif mode == "follow":
        count = engager.discover_and_follow()
        print(f"Followed {count} agents")
    elif mode == "engage":
        results = engager.engage_with_feed()
        print(f"Upvotes: {results['upvotes']}, Comments: {results['comments']}")
    elif mode == "cycle":
        results = engager.run_engagement_cycle()
        print(json.dumps(results, indent=2, default=str))
