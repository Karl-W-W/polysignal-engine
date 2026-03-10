#!/usr/bin/env python3
"""
tests/test_moltbook_engagement.py
==================================
Tests for lab/moltbook_engagement.py — MoltBook engagement bot.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lab.moltbook_engagement import (
    EngagementState,
    MoltBookEngager,
    TARGET_SUBMOLTS,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def engager(tmp_dir):
    return MoltBookEngager(
        jwt="test_jwt_123",
        state_path=tmp_dir / "engagement.json",
        request_delay=0,
    )


# ============================================================================
# ENGAGEMENT STATE
# ============================================================================

class TestEngagementState:
    def test_load_missing_file(self, tmp_dir):
        state = EngagementState.load(tmp_dir / "nonexistent.json")
        assert state.total_upvotes == 0
        assert state.subscribed_submolts == []

    def test_save_and_load(self, tmp_dir):
        path = tmp_dir / "state.json"
        state = EngagementState(
            subscribed_submolts=["agents", "trading"],
            total_upvotes=5,
            total_comments=2,
        )
        state.save(path)

        loaded = EngagementState.load(path)
        assert loaded.subscribed_submolts == ["agents", "trading"]
        assert loaded.total_upvotes == 5

    def test_daily_counter_reset(self):
        state = EngagementState(
            comments_today=10,
            last_comment_date="2025-01-01",
        )
        state.reset_daily_counter()
        assert state.comments_today == 0

    def test_daily_counter_no_reset_same_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state = EngagementState(
            comments_today=5,
            last_comment_date=today,
        )
        state.reset_daily_counter()
        assert state.comments_today == 5

    def test_caps_lists(self, tmp_dir):
        path = tmp_dir / "state.json"
        state = EngagementState(
            followed_agents=[f"a{i}" for i in range(600)],
            upvoted_posts=[f"p{i}" for i in range(1200)],
        )
        state.save(path)

        loaded = EngagementState.load(path)
        assert len(loaded.followed_agents) == 500
        assert len(loaded.upvoted_posts) == 1000


# ============================================================================
# SUBSCRIBE
# ============================================================================

class TestSubscribe:
    @patch.object(MoltBookEngager, "_post")
    def test_subscribe_to_targets(self, mock_post, engager):
        mock_post.return_value = {"success": True}

        result = engager.subscribe_to_targets()
        assert len(result) == len(TARGET_SUBMOLTS)
        assert mock_post.call_count == len(TARGET_SUBMOLTS)

    @patch.object(MoltBookEngager, "_post")
    def test_skip_already_subscribed(self, mock_post, engager):
        mock_post.return_value = {"success": True}

        # First subscription
        engager.subscribe_to_targets()
        # Second call — should skip all
        result2 = engager.subscribe_to_targets()
        assert len(result2) == 0


# ============================================================================
# FOLLOW
# ============================================================================

class TestFollow:
    @patch.object(MoltBookEngager, "_post")
    def test_follow_agent(self, mock_post, engager):
        mock_post.return_value = {"success": True}

        assert engager.follow_agent("agent_123") is True
        assert engager.follow_agent("agent_123") is False  # Already followed

    @patch.object(MoltBookEngager, "_get")
    @patch.object(MoltBookEngager, "_post")
    def test_discover_and_follow(self, mock_post, mock_get, engager):
        mock_get.return_value = {
            "data": [
                {"id": "agent_1", "username": "bot1"},
                {"id": "agent_2", "username": "bot2"},
            ]
        }
        mock_post.return_value = {"success": True}

        count = engager.discover_and_follow("prediction market", limit=5)
        assert count == 2


# ============================================================================
# UPVOTE
# ============================================================================

class TestUpvote:
    @patch.object(MoltBookEngager, "_post")
    def test_upvote_post(self, mock_post, engager):
        mock_post.return_value = {"success": True}

        assert engager.upvote_post("post_001") is True
        assert engager.upvote_post("post_001") is False  # Already upvoted


# ============================================================================
# COMMENT
# ============================================================================

class TestComment:
    @patch.object(MoltBookEngager, "_post")
    def test_comment_on_post(self, mock_post, engager):
        mock_post.return_value = {"success": True}

        assert engager.comment_on_post("post_001", "Great analysis!") is True
        assert engager.comment_on_post("post_001", "Duplicate!") is False

    @patch.object(MoltBookEngager, "_post")
    def test_daily_limit(self, mock_post, engager):
        mock_post.return_value = {"success": True}
        engager.max_comments_per_day = 2

        assert engager.comment_on_post("post_001", "Comment 1") is True
        assert engager.comment_on_post("post_002", "Comment 2") is True
        assert engager.comment_on_post("post_003", "Comment 3") is False  # Limit hit

    def test_generate_comment_polymarket(self, engager):
        post = {"title": "Polymarket prediction market analysis", "content": "Great signals"}
        comment = engager._generate_comment(post)
        assert comment is not None
        assert "LangGraph" in comment

    def test_generate_comment_irrelevant(self, engager):
        post = {"title": "Best recipes for pasta", "content": "Italian cooking tips"}
        comment = engager._generate_comment(post)
        assert comment is None


# ============================================================================
# ENGAGEMENT CYCLE
# ============================================================================

class TestEngagementCycle:
    @patch.object(MoltBookEngager, "engage_with_feed")
    @patch.object(MoltBookEngager, "discover_and_follow")
    @patch.object(MoltBookEngager, "subscribe_to_targets")
    def test_full_cycle(self, mock_sub, mock_follow, mock_engage, engager):
        mock_sub.return_value = ["agents", "trading"]
        mock_follow.return_value = 3
        mock_engage.return_value = {"upvotes": 5, "comments": 2}

        results = engager.run_engagement_cycle()
        assert "subscribed" in results
        assert "followed" in results
        assert "engagement" in results
