"""
tests/test_moltbook_publisher.py
================================
Tests for lab/moltbook_publisher.py — MoltBook signal publisher.

Written: Session 9 (2026-03-02) — Claude Code (architect).
"""

import json
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.signal_model import Signal, SignalSource
from lab.moltbook_publisher import (
    MoltBookConfig,
    PublisherState,
    format_signal_post,
    publish_signal,
    _signal_hash,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def config(tmp_path):
    """MoltBook config in dry-run mode with temp state file."""
    return MoltBookConfig(
        jwt="test_jwt_token_123",
        state_file=tmp_path / "moltbook_state.json",
        dry_run=True,
    )


@pytest.fixture
def live_config(tmp_path):
    """MoltBook config in live mode (for API mock tests)."""
    return MoltBookConfig(
        jwt="test_jwt_token_123",
        state_file=tmp_path / "moltbook_state.json",
        dry_run=False,
    )


@pytest.fixture
def sample_signal():
    """A typed Signal object for testing."""
    return Signal(
        market_id="0xtest_btc",
        title="Bitcoin above $120k by April 2026",
        outcome="Yes",
        polymarket_url="https://polymarket.com/event/btc-120k-april",
        current_price=0.65,
        volume_24h=2_500_000,
        change_since_last=0.07,
        hypothesis="Bullish",
        confidence=0.82,
        source=SignalSource(method="momentum", raw_value=0.07, threshold=0.05),
        reasoning="BTC moved +7pp against 5pp threshold.",
        time_horizon="4h",
    )


@pytest.fixture
def sample_stage_timings():
    return {
        "perception": 1.2,
        "prediction": 0.8,
        "draft": 0.5,
        "review": 0.3,
        "risk_gate": 0.1,
        "commit": 0.4,
    }


AUDIT_HASH = "abc123def456ghi789jkl012"


# ============================================================================
# FORMAT TESTS
# ============================================================================

class TestFormatSignalPost:
    def test_typed_signal_format(self, sample_signal, sample_stage_timings):
        title, body = format_signal_post(sample_signal, sample_stage_timings, AUDIT_HASH)

        assert "SIGNAL:" in title
        assert "Bitcoin above $120k" in title
        assert "YES" in title

        assert "SIGNAL DETECTED" in body
        assert "Direction: YES" in body
        assert "+7.0pp" in body
        assert "4h" in body
        assert "0.82" in body
        assert "abc123def456" in body
        assert "#PolySignal" in body

    def test_chain_status_reflects_timings(self, sample_signal, sample_stage_timings):
        _, body = format_signal_post(sample_signal, sample_stage_timings, AUDIT_HASH)

        assert "PERCEPTION [pass]" in body
        assert "PREDICTION [pass]" in body
        assert "DRAFT [pass]" in body
        assert "REVIEW [pass]" in body
        assert "COMMIT [pass]" in body

    def test_missing_node_shows_fail(self, sample_signal):
        partial_timings = {"perception": 1.0, "prediction": 0.5}
        _, body = format_signal_post(sample_signal, partial_timings, AUDIT_HASH)

        assert "PERCEPTION [pass]" in body
        assert "DRAFT [fail]" in body
        assert "COMMIT [fail]" in body

    def test_dict_signal_format(self, sample_stage_timings):
        sig_dict = {
            "market_id": "0xdict",
            "title": "ETH above $5k",
            "hypothesis": "Bearish",
            "current_price": 0.35,
            "delta": -0.06,
            "confidence": 0.78,
            "time_horizon": "1h",
        }
        title, body = format_signal_post(sig_dict, sample_stage_timings, AUDIT_HASH)

        assert "NO" in title
        assert "Direction: NO" in body
        assert "1h" in body

    def test_negative_delta(self, sample_stage_timings):
        sig = {
            "title": "Test",
            "hypothesis": "Bearish",
            "current_price": 0.4,
            "change_since_last": -0.08,
            "confidence": 0.75,
        }
        title, body = format_signal_post(sig, sample_stage_timings, AUDIT_HASH)
        assert "-8.0pp" in body


# ============================================================================
# STATE MANAGEMENT TESTS
# ============================================================================

class TestPublisherState:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "state.json"
        state = PublisherState(
            last_post_timestamp="2026-03-01T10:00:00+00:00",
            posted_signal_hashes=["abc123", "def456"],
            total_posts=5,
        )
        state.save(path)

        loaded = PublisherState.load(path)
        assert loaded.last_post_timestamp == "2026-03-01T10:00:00+00:00"
        assert loaded.posted_signal_hashes == ["abc123", "def456"]
        assert loaded.total_posts == 5

    def test_load_missing_file(self, tmp_path):
        state = PublisherState.load(tmp_path / "nonexistent.json")
        assert state.total_posts == 0
        assert state.posted_signal_hashes == []

    def test_hash_list_capped_at_100(self, tmp_path):
        path = tmp_path / "state.json"
        state = PublisherState(
            posted_signal_hashes=[f"hash_{i}" for i in range(150)],
        )
        state.save(path)
        loaded = PublisherState.load(path)
        assert len(loaded.posted_signal_hashes) == 100


# ============================================================================
# SIGNAL HASH TESTS
# ============================================================================

class TestSignalHash:
    def test_typed_signal_hashes(self, sample_signal):
        h = _signal_hash(sample_signal)
        assert len(h) == 16
        # Same signal = same hash
        assert _signal_hash(sample_signal) == h

    def test_dict_signal_hashes(self):
        d = {"market_id": "0x1", "hypothesis": "Bullish", "current_price": 0.65}
        h = _signal_hash(d)
        assert len(h) == 16

    def test_different_signals_different_hashes(self, sample_signal):
        other = Signal(
            market_id="0xother",
            title="Different",
            outcome="No",
            polymarket_url="https://polymarket.com/event/other",
            current_price=0.30,
            volume_24h=100_000,
            hypothesis="Bearish",
            confidence=0.60,
            source=SignalSource(method="test", raw_value=0.01, threshold=0.05),
            reasoning="Test.",
        )
        assert _signal_hash(sample_signal) != _signal_hash(other)


# ============================================================================
# PUBLISH FLOW TESTS
# ============================================================================

class TestPublishSignal:
    def test_dry_run_returns_formatted_post(self, sample_signal, sample_stage_timings, config):
        result = publish_signal(sample_signal, sample_stage_timings, AUDIT_HASH, config)

        assert not result.published
        assert "Dry run" in result.reason
        assert result.title is not None
        assert "SIGNAL:" in result.title
        assert result.body is not None
        assert "#PolySignal" in result.body

    def test_rate_limit_blocks_fast_posts(self, sample_signal, sample_stage_timings, config):
        # First post succeeds (dry run)
        r1 = publish_signal(sample_signal, sample_stage_timings, AUDIT_HASH, config)
        assert "Dry run" in r1.reason

        # Manually set last post time to now
        state = PublisherState.load(config.state_file)
        state.last_post_timestamp = datetime.now(timezone.utc).isoformat()
        state.save(config.state_file)

        # Second post should be rate limited
        other_signal = Signal(
            market_id="0xother",
            title="Other market",
            outcome="Yes",
            polymarket_url="https://polymarket.com/event/other",
            current_price=0.55,
            volume_24h=500_000,
            hypothesis="Bullish",
            confidence=0.80,
            source=SignalSource(method="test", raw_value=0.06, threshold=0.05),
            reasoning="Test.",
        )
        r2 = publish_signal(other_signal, sample_stage_timings, AUDIT_HASH, config)
        assert not r2.published
        assert "Rate limited" in r2.reason

    def test_duplicate_blocked(self, sample_signal, sample_stage_timings, config):
        # Manually add signal hash to state
        state = PublisherState()
        state.posted_signal_hashes.append(_signal_hash(sample_signal))
        state.save(config.state_file)

        result = publish_signal(sample_signal, sample_stage_timings, AUDIT_HASH, config)
        assert not result.published
        assert "Duplicate" in result.reason

    @patch("lab.moltbook_publisher.requests.post")
    def test_live_publish_success(self, mock_post, sample_signal, sample_stage_timings, live_config):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "post_12345"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = publish_signal(sample_signal, sample_stage_timings, AUDIT_HASH, live_config)

        assert result.published
        assert result.post_id == "post_12345"
        assert "Published successfully" in result.reason

        # Verify API was called correctly
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "Bearer test_jwt_token_123" in call_kwargs.kwargs["headers"]["Authorization"]
        assert call_kwargs.kwargs["json"]["submolt"] == "signals"

    @patch("lab.moltbook_publisher.requests.post")
    def test_live_publish_api_error(self, mock_post, sample_signal, sample_stage_timings, live_config):
        mock_post.side_effect = requests.RequestException("Connection refused")

        result = publish_signal(sample_signal, sample_stage_timings, AUDIT_HASH, live_config)

        assert not result.published
        assert "API error" in result.reason
        assert result.body is not None  # Body was formatted before failure

    @patch("lab.moltbook_publisher.requests.post")
    def test_state_updated_after_publish(self, mock_post, sample_signal, sample_stage_timings, live_config):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "post_999"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        publish_signal(sample_signal, sample_stage_timings, AUDIT_HASH, live_config)

        state = PublisherState.load(live_config.state_file)
        assert state.total_posts == 1
        assert len(state.posted_signal_hashes) == 1
        assert state.last_post_timestamp != ""
