"""
lab/experiments/bitcoin_signal.py
====================================
LAB EXPERIMENT — NOT promoted to /core.

Objective: Detect ONE real Polymarket signal for Bitcoin/BTC markets
and format it for a Telegram alert.

Success Criteria:
  - Queries Polymarket Gamma API for Bitcoin-related markets
  - Compares current price with last DB observation
  - Detects moves > THRESHOLD (5pp default)
  - Prints a formatted Telegram-ready alert message
  - Runs standalone: python3 lab/experiments/bitcoin_signal.py

Promotion Criteria (to be integrated into masterloop):
  [ ] Detects at least one REAL signal on a second run (>5 min apart)
  [ ] Karl receives Telegram alert manually triggered from this script
  [ ] Human approves integration into workflows/masterloop.py
"""

import requests
import sqlite3
import json
import os
from datetime import datetime
from lab.time_horizon import derive_time_horizon

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH           = os.getenv("DB_PATH", "/data/polysignal.db")
SIGNAL_THRESHOLD  = float(os.getenv("SIGNAL_THRESHOLD", "0.05"))   # 5pp
SEARCH_KEYWORDS   = ["bitcoin", "btc", "crypto", "ethereum", "eth"]
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID")


# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    if not os.path.exists(DB_PATH):
        # Local testing fallback
        fallback = os.path.join(os.path.dirname(__file__), "../../data/test.db")
        conn = sqlite3.connect(fallback)
    else:
        conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS observations (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT,
            title     TEXT,
            price     REAL,
            volume    REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            raw_data  TEXT
        )
    ''')
    conn.commit()


# ── Polymarket Fetch ──────────────────────────────────────────────────────────

def fetch_crypto_markets(limit: int = 50) -> list:
    """Fetch Polymarket events and filter for crypto/Bitcoin markets."""
    try:
        resp = requests.get(
            "https://gamma-api.polymarket.com/events",
            params={"limit": limit, "closed": "false"},
            timeout=10
        )
        resp.raise_for_status()
        events = resp.json()
    except Exception as e:
        print(f"❌ API error: {e}")
        return []

    crypto_markets = []
    for event in events:
        title = (event.get("title") or "").lower()
        slug  = (event.get("slug") or event.get("id", ""))

        # Only keep crypto-related events
        if not any(kw in title for kw in SEARCH_KEYWORDS):
            continue

        for m in event.get("markets", []):
            if m.get("closed"):
                continue
            try:
                op = m.get("outcomePrices", '["0","0"]')
                prices = json.loads(op) if isinstance(op, str) else op
                price = float(prices[0])
            except Exception:
                price = 0.0

            crypto_markets.append({
                "id":      m["id"],
                "title":   event.get("title", "Unknown"),
                "outcome": m.get("question", "Yes"),
                "price":   price,
                "volume":  float(m.get("volume", 0)),
                "url":     f"https://polymarket.com/event/{slug}",
            })

    crypto_markets.sort(key=lambda x: x["volume"], reverse=True)
    print(f"Found {len(crypto_markets)} crypto markets on Polymarket")
    return crypto_markets


# ── Signal Detection ──────────────────────────────────────────────────────────

def detect_signals(markets: list) -> list:
    """Compare current prices with DB history. Return signals > THRESHOLD."""
    conn = get_db()
    init_db(conn)
    c = conn.cursor()

    signals = []

    for m in markets:
        market_id     = m["id"]
        current_price = m["price"]

        # Read PREVIOUS observation BEFORE inserting current one (fixes off-by-one)
        row = c.execute(
            "SELECT price, timestamp FROM observations WHERE market_id = ? ORDER BY timestamp DESC LIMIT 1",
            (market_id,)
        ).fetchone()

        # NOW record current observation
        c.execute(
            "INSERT INTO observations (market_id, title, price, volume, raw_data) VALUES (?, ?, ?, ?, ?)",
            (market_id, f"{m['title']} — {m['outcome']}", current_price, m["volume"], json.dumps(m))
        )

        if row:
            last_price = row["price"]
            last_ts    = row["timestamp"]
            delta      = current_price - last_price

            if abs(delta) >= SIGNAL_THRESHOLD:
                direction = "📈 Bullish" if delta > 0 else "📉 Bearish"
                time_horizon = derive_time_horizon(
                    volume_24h=m["volume"],
                    abs_price_delta=abs(delta),
                    num_recent_signals=len(signals),
                )
                signals.append({
                    "market_id":     market_id,
                    "title":         m["title"],
                    "outcome":       m["outcome"],
                    "current_price": current_price,
                    "last_price":    last_price,
                    "delta":         delta,
                    "volume":        m["volume"],
                    "url":           m["url"],
                    "direction":     direction,
                    "last_seen":     last_ts,
                    "time_horizon":  time_horizon,
                })
                print(f"  🔔 SIGNAL: {m['title'][:50]} {delta:+.3f} [{time_horizon}]")

    conn.commit()
    conn.close()

    return signals


# ── Telegram Alert ────────────────────────────────────────────────────────────

def format_alert(signal: dict) -> str:
    """Format ONE signal into a Telegram message."""
    return (
        f"{signal['direction']} *SIGNAL DETECTED*\n\n"
        f"*Market:* {signal['title']}\n"
        f"*Outcome:* {signal['outcome']}\n"
        f"*Price:* {signal['current_price']:.2%} → was {signal['last_price']:.2%}\n"
        f"*Move:* {signal['delta']:+.2%}\n"
        f"*Volume:* ${signal['volume']:,.0f}\n\n"
        f"*Trade:* {signal['url']}"
    )


def send_telegram(message: str):
    """Send a message to Karl via Telegram. Requires TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — printing alert instead:")
        print(message)
        return

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
        if resp.status_code == 200:
            print("✅ Telegram alert sent")
        else:
            print(f"❌ Telegram error: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram send failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("="*60)
    print("Bitcoin Signal Detector — Lab Experiment")
    print("="*60)
    print(f"DB: {DB_PATH}")
    print(f"Threshold: >{SIGNAL_THRESHOLD:.0%} price move")
    print()

    markets = fetch_crypto_markets()
    if not markets:
        print("No crypto markets found. Check Polymarket API.")
        exit(1)

    print(f"\nScanning {len(markets)} markets for signals...")
    signals = detect_signals(markets)

    print(f"\n{'='*60}")
    if not signals:
        print("No signals (0 markets moved enough since last scan).")
        print("Run again in 5+ minutes to compare against this baseline.")
    else:
        print(f"🔔 {len(signals)} signal(s) detected!")
        for s in signals:
            msg = format_alert(s)
            print("\n--- TELEGRAM ALERT ---")
            print(msg)
            print("--- END ALERT ---")
            send_telegram(msg)

    print(f"\nDone. Next run will compare against today's baseline.")
