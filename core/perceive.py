"""
core/perceive.py
================
VAULT FILE — do not modify without explicit human authorization.
ARCHITECTURE.md §5 — Vault Inventory.

Perception node: Fetch top Polymarket markets, compare with DB history,
emit Signal objects for significant price moves.
"""

import requests
import sqlite3
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("polybean-perception")

class Signal(BaseModel):
    market_id: str
    title: str
    price: float
    volume: float
    change_24h: float
    timestamp: str
    source: str = "polymarket"

DB_PATH = "/data/polysignal.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Observations table
    c.execute('''
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT,
            title TEXT,
            price REAL,
            volume REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            raw_data TEXT
        )
    ''')
    
    # Signals table (processed events)
    c.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT,
            type TEXT,
            value REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Patterns table (learned intelligence)
    c.execute('''
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_hash TEXT UNIQUE,
            description TEXT,
            confidence REAL,
            occurrences INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def fetch_top_markets(limit: int = 10) -> List[Dict]:
    """Fetch top markets by volume from Polymarket Gamma API."""
    url = "https://gamma-api.polymarket.com/events"
    params = {
        "limit": limit,
        "closed": "false"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        events = response.json()
        
        markets = []
        for event in events:
            # Flatten event structure to get main market
            if not event.get("markets"):
                continue
                
            # Usually the first market is the main binary outcome (Yes/No)
            # or we iterate all
            for m in event["markets"]:
                if m.get("closed"):
                    continue
                    
                # Gamma API often returns these fields as JSON strings
                try:
                    outcome_prices = json.loads(m.get("outcomePrices", "[\"0\", \"0\"]")) if isinstance(m.get("outcomePrices"), str) else m.get("outcomePrices", ["0", "0"])
                    price = float(outcome_prices[0])
                except (json.JSONDecodeError, ValueError, IndexError):
                    price = 0.0

                markets.append({
                    "id": m["id"],
                    "question": event.get("title"),
                    "outcome": m.get("question"), # "Yes", "No", "Trump", etc.
                    "price": price,
                    "volume": float(m.get("volume", 0)),
                    "raw": m
                })
        
        # Sort by volume again to be sure
        markets.sort(key=lambda x: x["volume"], reverse=True)
        return markets[:limit]
        
    except Exception as e:
        logger.error(f"Failed to fetch markets: {e}")
        return []

def observe_markets() -> List[Signal]:
    """
    Main perception loop.
    1. Fetch current state
    2. Compare with last DB state
    3. Record new observations
    4. Return significant signals
    """
    init_db()
    
    markets = fetch_top_markets(limit=20)
    signals = []
    
    conn = get_db_connection()
    c = conn.cursor()
    
    for m in markets:
        market_id = m["id"]
        current_price = m["price"]
        
        # Get last observation
        c.execute('''
            SELECT price, timestamp FROM observations 
            WHERE market_id = ? 
            ORDER BY timestamp DESC LIMIT 1
        ''', (market_id,))
        row = c.fetchone()
        
        # Store current observation
        c.execute('''
            INSERT INTO observations (market_id, title, price, volume, raw_data)
            VALUES (?, ?, ?, ?, ?)
        ''', (market_id, m["question"] + " - " + m["outcome"], current_price, m["volume"], json.dumps(m["raw"])))
        
        # Detect change
        if row:
            last_price = row["price"]
            last_time = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
            
            # Simple logic: >5% change since last check
            # (In reality we want time-weighted, but this is MVP)
            delta = current_price - last_price
            
            if abs(delta) > 0.05:
                sig = Signal(
                    market_id=market_id,
                    title=m["question"] + " (" + m["outcome"] + ")",
                    price=current_price,
                    volume=m["volume"],
                    change_24h=delta, # This is 'since last observation'
                    timestamp=datetime.now(timezone.utc).isoformat()
                )
                signals.append(sig)
                logger.info(f"SIGNAL DETECTED: {sig.title} moved {delta:.2f}")
    
    conn.commit()
    conn.close()
    
    return signals

if __name__ == "__main__":
    # Test run
    sigs = observe_markets()
    print(f"Observed {len(sigs)} signals")
    for s in sigs:
        print(s)
