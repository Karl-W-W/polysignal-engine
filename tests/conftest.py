"""
Shared fixtures for PolySignal-OS test suite.
"""

import os
import sqlite3
import tempfile
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database with the PolySignal schema."""
    db_path = str(tmp_path / "test_polysignal.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
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
    c.execute("""
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT,
            type TEXT,
            value REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_hash TEXT UNIQUE,
            description TEXT,
            confidence REAL,
            occurrences INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def env_override(monkeypatch):
    """Helper to set env vars for testing without affecting the real env."""
    def _set(**kwargs):
        for k, v in kwargs.items():
            monkeypatch.setenv(k, v)
    return _set
