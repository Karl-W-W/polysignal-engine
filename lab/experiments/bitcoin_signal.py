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
from datetime import datetime, timezone, timedelta
from lab.time_horizon import derive_time_horizon

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH           = os.getenv("DB_PATH", "/data/polysignal.db")
SIGNAL_THRESHOLD  = float(os.getenv("SIGNAL_THRESHOLD", "0.05"))   # 5pp
SEARCH_KEYWORDS   = ["bitcoin", "btc", "crypto", "ethereum", "eth"]
# Session 28: Minimum liquidity for market inclusion (USD).
# Markets below this are too thin to trade or generate reliable signals.
MIN_LIQUIDITY     = float(os.getenv("MIN_LIQUIDITY", "50000"))  # $50K
# Session 28: Scan ALL markets (not just crypto) when enabled.
SCAN_ALL_MARKETS  = os.getenv("SCAN_ALL_MARKETS", "false").lower() in ("true", "1", "yes")

# Session 44 (2026-05-21): only consider markets that RESOLVE within this many
# days. The resolution backtest found all 4 historical predictions were on
# multi-month markets — unscoreable until mid-2026. A short-horizon universe
# lets a statistically evaluable track record accrue in weeks. `endDate` is the
# gamma resolution-deadline field.
MAX_DAYS_TO_RESOLUTION = float(os.getenv("MAX_DAYS_TO_RESOLUTION", "7"))
# Session 44: also require a MINIMUM remaining horizon — exclude markets that
# have already resolved (past endDate) or resolve too soon to forecast
# meaningfully. Default 0.25 days (6h).
MIN_DAYS_TO_RESOLUTION = float(os.getenv("MIN_DAYS_TO_RESOLUTION", "0.25"))

# Markets excluded from signal detection (still recorded for observation data).
# Session 16: 824952 "MicroStrategy sells any Bitcoin" — 32% accuracy, 33W/70L
# Session 23: Loop's per-market audit found 3 more toxic markets:
#   556062: 0% accuracy (0W/4L), 1373744: 17% (1W/5L), 965261: 0% (0W/5L)
# Session 24: Antigravity audit found 2 more toxic markets:
#   1541748: 36% accuracy (7C/12I), 692258: 0% accuracy (0C/5I)
# Without these 6: post-exclusion accuracy jumps to ~88% (bullish-only).
# Session 38: 559653 "AOC 2028 Dem Primary" — 41.7% accuracy (45W/63L), toxic.
EXCLUDED_MARKETS  = set(
    m.strip() for m in os.getenv("EXCLUDED_MARKETS", "824952,556062,1373744,965261,1541748,692258,559653").split(",") if m.strip()
)
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID")


# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    if not os.path.exists(DB_PATH):
        # Local testing fallback
        fallback = os.path.join(os.path.dirname(__file__), "../../data/test.db")
        conn = sqlite3.connect(fallback, timeout=30)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
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

def _days_to_resolution(market: dict):
    """Days until a gamma market resolves, read from its `endDate` field.
    Returns None if endDate is missing or unparseable. Session 44."""
    ed = market.get("endDate") or market.get("endDateIso")
    if not ed:
        return None
    try:
        dt = datetime.fromisoformat(str(ed).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - datetime.now(timezone.utc)).total_seconds() / 86400.0


def _within_horizon(market: dict) -> bool:
    """True iff the market resolves within [MIN_DAYS_TO_RESOLUTION,
    MAX_DAYS_TO_RESOLUTION] days. Markets with no parseable endDate, an
    already-past endDate, or too little remaining life are excluded. Session 44."""
    dtr = _days_to_resolution(market)
    return dtr is not None and MIN_DAYS_TO_RESOLUTION <= dtr <= MAX_DAYS_TO_RESOLUTION


def quote_fields(m: dict) -> dict:
    """Rung 1 (2026-09-05, lab/AUTONOMY.md): keep the order-book quote that
    gamma-api already returns on every market object, so a fill price, spread
    and fee can be logged with each prediction / paper trade. Without these
    the friction-adjusted win rate is not computable from the stores.
    Missing or zero quotes are recorded as None, never invented."""
    def _f(key):
        try:
            v = m.get(key)
            v = float(v) if v is not None and v != "" else None
        except (TypeError, ValueError):
            return None
        return v if v is not None and v > 0 else None
    bid, ask = _f("bestBid"), _f("bestAsk")
    spread = _f("spread")
    if spread is None and bid is not None and ask is not None and ask >= bid:
        spread = round(ask - bid, 6)
    return {
        "best_bid": bid,
        "best_ask": ask,
        "spread": spread,
        "last_trade_price": _f("lastTradePrice"),
        "quote_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def fetch_crypto_markets(limit: int = 50) -> list:
    """Fetch Polymarket markets. Crypto-only by default, ALL liquid markets when SCAN_ALL_MARKETS=true."""
    if SCAN_ALL_MARKETS:
        return fetch_all_liquid_markets()
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
                "id":      str(m.get("conditionId") or m["id"]),
                "title":   event.get("title", "Unknown"),
                "outcome": m.get("question", "Yes"),
                "price":   price,
                "volume":  float(m.get("volume", 0)),
                "url":     f"https://polymarket.com/event/{slug}",
                **quote_fields(m),
            })

    crypto_markets.sort(key=lambda x: x["volume"], reverse=True)
    print(f"Found {len(crypto_markets)} crypto markets on Polymarket")
    return crypto_markets


def fetch_all_liquid_markets(max_markets: int = 300) -> list:
    """Session 28: Fetch Polymarket markets above MIN_LIQUIDITY, sorted by volume.

    Session 44 (2026-05-21): restricted to markets that RESOLVE within
    MAX_DAYS_TO_RESOLUTION days, using gamma's end_date_min/end_date_max window,
    so a statistically evaluable track record can accrue in weeks rather than by
    mid-2026 (resolution backtest finding). Pagination fixed: gamma caps a page
    at 100 items, so the offset steps by 100 — the old limit=500 / break-on-<500
    only ever read the first page (~100 markets).
    """
    now = datetime.now(timezone.utc)
    end_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_max = (now + timedelta(days=MAX_DAYS_TO_RESOLUTION)).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_markets = []
    # Paginate the /markets endpoint (gamma caps a page at 100 items).
    for offset in range(0, 3000, 100):
        try:
            resp = requests.get(
                "https://gamma-api.polymarket.com/markets",
                params={
                    "closed": "false", "limit": 100, "offset": offset,
                    "end_date_min": end_min, "end_date_max": end_max,
                },
                headers={"User-Agent": "PolySignal/1.0"},
                timeout=15,
            )
            resp.raise_for_status()
            batch = resp.json()
        except Exception as e:
            print(f"  ⚠ API page {offset}: {e}")
            break

        if not batch:
            break

        for m in batch:
            liquidity = float(m.get("liquidity", 0) or 0)
            if liquidity < MIN_LIQUIDITY:
                continue
            # Session 44: the server-side date window can be loose at the edges
            # — re-check the resolution horizon client-side from endDate.
            if not _within_horizon(m):
                continue
            try:
                op = m.get("outcomePrices", '["0","0"]')
                prices = json.loads(op) if isinstance(op, str) else op
                price = float(prices[0])
            except Exception:
                price = 0.0

            slug = m.get("slug") or m.get("conditionId", "")
            event_slug = m.get("eventSlug") or slug
            all_markets.append({
                "id":        str(m.get("id", m.get("conditionId", ""))),
                "title":     m.get("question", "Unknown"),
                "outcome":   m.get("groupItemTitle") or "Yes",
                "price":     price,
                "volume":    float(m.get("volume", 0) or 0),
                "liquidity": liquidity,
                "end_date":  m.get("endDate"),
                "url":       f"https://polymarket.com/event/{event_slug}",
                **quote_fields(m),
            })

        if len(batch) < 100:
            break

    all_markets.sort(key=lambda x: x["volume"], reverse=True)
    # Cap to avoid overwhelming the scanner
    if len(all_markets) > max_markets:
        all_markets = all_markets[:max_markets]
    print(f"Found {len(all_markets)} short-horizon liquid markets on Polymarket "
          f"(min ${MIN_LIQUIDITY:,.0f} liquidity, resolve <={MAX_DAYS_TO_RESOLUTION:.0f}d)")
    return all_markets


# ── Signal Detection ──────────────────────────────────────────────────────────

def detect_signals(markets: list) -> list:
    """Compare current prices with DB history using rolling time windows.

    Instead of comparing only to the previous scan (5min ago, usually 0 delta),
    checks 1h and 4h windows to catch meaningful price moves in prediction markets.
    """
    conn = get_db()
    init_db(conn)
    c = conn.cursor()

    signals = []
    # Track closest-to-threshold market for status visibility (Session 20)
    _closest_delta = 0.0
    _closest_market = None

    # Rolling windows: (label, min_age_seconds, max_age_seconds)
    # We look for the closest observation within each window.
    # Session 15: Removed 4h window — 0% accuracy (0W/17L across 134 evals).
    # Prediction markets move too slowly for 4h windows to be useful.
    WINDOWS = [
        ("15m", 600,   1800),   # 10–30min ago (catches fast intra-hour moves)
        ("1h",  3600,  7200),   # 1–2h ago
    ]

    for m in markets:
        market_id     = m["id"]
        current_price = m["price"]

        # Record current observation first
        c.execute(
            "INSERT INTO observations (market_id, title, price, volume, raw_data) VALUES (?, ?, ?, ?, ?)",
            (market_id, f"{m['title']} — {m['outcome']}", current_price, m["volume"], json.dumps(m))
        )

        # Skip excluded markets (observation already recorded above for data collection)
        if market_id in EXCLUDED_MARKETS:
            continue

        # Find the best (largest absolute) delta across all time windows
        best_delta     = 0.0
        best_ref_price = None
        best_ref_ts    = None
        best_window    = None

        for window_name, min_sec, max_sec in WINDOWS:
            row = c.execute(
                """SELECT price, timestamp FROM observations
                   WHERE market_id = ?
                     AND timestamp < datetime('now', ?)
                     AND timestamp > datetime('now', ?)
                   ORDER BY timestamp DESC LIMIT 1""",
                (market_id, f"-{min_sec} seconds", f"-{max_sec} seconds")
            ).fetchone()

            if row:
                ref_price = row["price"]
                delta = current_price - ref_price
                if abs(delta) > abs(best_delta):
                    best_delta     = delta
                    best_ref_price = ref_price
                    best_ref_ts    = row["timestamp"]
                    best_window    = window_name

        # Track closest-to-threshold for status visibility
        if abs(best_delta) > abs(_closest_delta) and abs(best_delta) < SIGNAL_THRESHOLD:
            _closest_delta = best_delta
            _closest_market = market_id

        if abs(best_delta) >= SIGNAL_THRESHOLD and best_ref_price is not None:
            direction = "📈 Bullish" if best_delta > 0 else "📉 Bearish"
            time_horizon = derive_time_horizon(
                volume_24h=m["volume"],
                abs_price_delta=abs(best_delta),
                num_recent_signals=len(signals),
            )
            signals.append({
                "market_id":     market_id,
                "title":         m["title"],
                "outcome":       m["outcome"],
                "current_price": current_price,
                "last_price":    best_ref_price,
                "delta":         best_delta,
                "volume":        m["volume"],
                "url":           m["url"],
                "direction":     direction,
                "last_seen":     best_ref_ts,
                "time_horizon":  time_horizon,
                "window":        best_window,
                # Rung 1: carry the quote through to the observation.
                "best_bid":        m.get("best_bid"),
                "best_ask":        m.get("best_ask"),
                "spread":          m.get("spread"),
                "last_trade_price": m.get("last_trade_price"),
                "quote_timestamp": m.get("quote_timestamp"),
            })
            print(f"  🔔 SIGNAL: {m['title'][:50]} {best_delta:+.3f} ({best_window}) [{time_horizon}]")

    conn.commit()
    conn.close()

    # Store closest-miss for scanner status visibility
    detect_signals.closest_miss = {
        "market_id": _closest_market,
        "delta": round(_closest_delta, 4),
        "threshold": SIGNAL_THRESHOLD,
    } if _closest_market else None

    return signals

# Initialize attribute
detect_signals.closest_miss = None


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
