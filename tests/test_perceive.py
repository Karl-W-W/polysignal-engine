"""
Tests for core/perceive.py — Polymarket perception node.
"""

import sqlite3
import json
import pytest
from unittest.mock import patch, MagicMock
from core.perceive import Signal, fetch_top_markets, observe_markets, init_db


class TestSignalSchema:
    """Test the lightweight Signal model in perceive.py."""

    def test_valid_signal(self):
        sig = Signal(
            market_id="0x123",
            title="Test Market",
            price=0.65,
            volume=10000.0,
            change_24h=0.08,
            timestamp="2026-02-27T12:00:00Z",
        )
        assert sig.market_id == "0x123"
        assert sig.source == "polymarket"

    def test_default_source(self):
        sig = Signal(
            market_id="0x1",
            title="T",
            price=0.5,
            volume=0.0,
            change_24h=0.0,
            timestamp="now",
        )
        assert sig.source == "polymarket"


class TestInitDb:
    def test_creates_tables(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr("core.perceive.DB_PATH", db_path)
        init_db()

        conn = sqlite3.connect(db_path)
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        assert "observations" in tables
        assert "signals" in tables
        assert "patterns" in tables

    def test_idempotent(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr("core.perceive.DB_PATH", db_path)
        init_db()
        init_db()  # should not raise


class TestFetchTopMarkets:
    @patch("core.perceive.requests.get")
    def test_returns_markets_from_api(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "title": "Will BTC hit 100k?",
                    "markets": [
                        {
                            "id": "0xm1",
                            "question": "Yes",
                            "outcomePrices": '["0.72", "0.28"]',
                            "volume": "1500000",
                            "closed": False,
                        }
                    ],
                }
            ],
        )
        mock_get.return_value.raise_for_status = MagicMock()

        markets = fetch_top_markets(limit=5)
        assert len(markets) == 1
        assert markets[0]["id"] == "0xm1"
        assert markets[0]["price"] == 0.72

    @patch("core.perceive.requests.get")
    def test_handles_api_error(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        markets = fetch_top_markets()
        assert markets == []

    @patch("core.perceive.requests.get")
    def test_skips_closed_markets(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "title": "Closed Event",
                    "markets": [
                        {
                            "id": "0xclosed",
                            "question": "Yes",
                            "outcomePrices": '["0.99", "0.01"]',
                            "volume": "500",
                            "closed": True,
                        }
                    ],
                }
            ],
        )
        mock_get.return_value.raise_for_status = MagicMock()

        markets = fetch_top_markets()
        assert len(markets) == 0


class TestObserveMarkets:
    @patch("core.perceive.fetch_top_markets")
    def test_detects_price_move(self, mock_fetch, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr("core.perceive.DB_PATH", db_path)

        # Set up DB with a prior observation
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT,
                title TEXT,
                price REAL,
                volume REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                raw_data TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT, type TEXT, value REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_hash TEXT UNIQUE, description TEXT,
                confidence REAL, occurrences INTEGER DEFAULT 0
            )
        """)
        # Insert a prior observation at price 0.50
        conn.execute(
            "INSERT INTO observations (market_id, title, price, volume, raw_data) VALUES (?, ?, ?, ?, ?)",
            ("0xm1", "Test - Yes", 0.50, 1000, "{}"),
        )
        conn.commit()
        conn.close()

        # Mock fetcher returns market at 0.60 (+0.10 delta, > 0.05 threshold)
        mock_fetch.return_value = [
            {
                "id": "0xm1",
                "question": "Test",
                "outcome": "Yes",
                "price": 0.60,
                "volume": 2000.0,
                "raw": {},
            }
        ]

        signals = observe_markets()
        assert len(signals) == 1
        assert signals[0].market_id == "0xm1"
        assert abs(signals[0].change_24h - 0.10) < 0.001

    @patch("core.perceive.fetch_top_markets")
    def test_no_signal_for_small_move(self, mock_fetch, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr("core.perceive.DB_PATH", db_path)

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT, title TEXT, price REAL, volume REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, raw_data TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT, type TEXT, value REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_hash TEXT UNIQUE, description TEXT,
                confidence REAL, occurrences INTEGER DEFAULT 0
            )
        """)
        conn.execute(
            "INSERT INTO observations (market_id, title, price, volume, raw_data) VALUES (?, ?, ?, ?, ?)",
            ("0xm1", "Test - Yes", 0.50, 1000, "{}"),
        )
        conn.commit()
        conn.close()

        # Price moved only 0.02 (below 0.05 threshold)
        mock_fetch.return_value = [
            {
                "id": "0xm1",
                "question": "Test",
                "outcome": "Yes",
                "price": 0.52,
                "volume": 1100.0,
                "raw": {},
            }
        ]

        signals = observe_markets()
        assert len(signals) == 0
