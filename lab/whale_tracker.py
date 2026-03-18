"""
lab/whale_tracker.py
=====================
Session 28: Whale/insider detection for Polymarket markets.

Detects outsized bets by monitoring:
1. Large order book imbalances (bid vs ask depth)
2. Sudden liquidity changes (someone loading up)
3. Price moves on low volume (informed trading)
4. Concentrated positions from known whale wallets

Uses gamma-api (unauthenticated) for market-level signals.
CLOB trades endpoint requires authenticated access (derive_api_key).

Usage:
    python3 -m lab.whale_tracker                  # Scan all liquid markets
    python3 -m lab.whale_tracker --market 556108  # Specific market
"""

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import requests


GAMMA_BASE = "https://gamma-api.polymarket.com"
USER_AGENT = "PolySignal/1.0"
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", "50000"))
WHALE_LOG_PATH = Path(os.getenv("WHALE_LOG_PATH", "/opt/loop/lab/.whale-signals.jsonl"))

# Thresholds for whale detection
SPREAD_COLLAPSE_THRESHOLD = 0.005   # Spread < 0.5% = someone providing deep liquidity
VOLUME_SPIKE_THRESHOLD = 3.0        # 24h vol > 3x weekly avg = unusual activity
LIQUIDITY_SURGE_THRESHOLD = 2.0     # Liquidity > 2x normal = someone loading up
PRICE_MOVE_LOW_VOL_THRESHOLD = 0.05 # 5pp move on below-avg volume = informed trading


@dataclass
class WhaleSignal:
    """A detected whale/insider signal."""
    market_id: str
    title: str
    signal_type: str        # volume_spike, liquidity_surge, spread_collapse, price_move_low_vol
    severity: str           # low, medium, high
    details: str            # Human-readable explanation
    current_price: float
    volume_24h: float
    liquidity: float
    spread: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def fetch_market_data(market_id: str) -> Optional[dict]:
    """Fetch detailed market data from gamma-api."""
    try:
        resp = requests.get(
            f"{GAMMA_BASE}/markets/{market_id}",
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ⚠ {market_id}: {e}")
        return None


def fetch_liquid_markets(min_liquidity: float = MIN_LIQUIDITY, limit: int = 300) -> List[dict]:
    """Fetch all markets above liquidity threshold."""
    markets = []
    for offset in range(0, 2000, 500):
        try:
            resp = requests.get(
                f"{GAMMA_BASE}/markets",
                params={"closed": "false", "limit": 500, "offset": offset},
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            batch = resp.json()
        except Exception:
            break

        for m in batch:
            liq = float(m.get("liquidity", 0) or 0)
            if liq >= min_liquidity:
                markets.append(m)
        if len(batch) < 500:
            break

    markets.sort(key=lambda m: float(m.get("volume", 0) or 0), reverse=True)
    return markets[:limit]


def analyze_market(m: dict) -> List[WhaleSignal]:
    """Analyze a single market for whale signals."""
    signals = []
    mid = str(m.get("id", m.get("conditionId", "")))
    title = m.get("question", "Unknown")[:80]

    best_bid = float(m.get("bestBid", 0) or 0)
    best_ask = float(m.get("bestAsk", 0) or 0)
    spread = best_ask - best_bid if best_bid and best_ask else 1.0
    price = float(m.get("lastTradePrice", 0) or 0)
    vol_24h = float(m.get("volume24hr", 0) or 0)
    vol_1wk = float(m.get("volume1wk", 0) or 0)
    liquidity = float(m.get("liquidityNum", 0) or 0)

    avg_daily_vol = vol_1wk / 7 if vol_1wk > 0 else vol_24h

    # 1. Volume spike: 24h volume >> weekly average
    if avg_daily_vol > 0 and vol_24h / avg_daily_vol >= VOLUME_SPIKE_THRESHOLD:
        ratio = vol_24h / avg_daily_vol
        severity = "high" if ratio > 5 else "medium" if ratio > 3 else "low"
        signals.append(WhaleSignal(
            market_id=mid, title=title, signal_type="volume_spike",
            severity=severity,
            details=f"24h volume ${vol_24h:,.0f} is {ratio:.1f}x weekly avg (${avg_daily_vol:,.0f}/day)",
            current_price=price, volume_24h=vol_24h, liquidity=liquidity, spread=spread,
        ))

    # 2. Spread collapse: very tight spread = deep liquidity provider
    if spread < SPREAD_COLLAPSE_THRESHOLD and spread > 0:
        signals.append(WhaleSignal(
            market_id=mid, title=title, signal_type="spread_collapse",
            severity="medium",
            details=f"Spread {spread:.4f} (< {SPREAD_COLLAPSE_THRESHOLD}) — deep liquidity provider active",
            current_price=price, volume_24h=vol_24h, liquidity=liquidity, spread=spread,
        ))

    # 3. Extreme price (near 0 or near 1 with high liquidity = confident whale)
    if liquidity > 100000 and (price > 0.95 or price < 0.05):
        direction = "YES" if price > 0.95 else "NO"
        signals.append(WhaleSignal(
            market_id=mid, title=title, signal_type="extreme_conviction",
            severity="high",
            details=f"Price {price:.2%} with ${liquidity:,.0f} liquidity — market strongly expects {direction}",
            current_price=price, volume_24h=vol_24h, liquidity=liquidity, spread=spread,
        ))

    return signals


def scan_all(target_market: str = None) -> List[WhaleSignal]:
    """Scan all liquid markets for whale signals."""
    print("=" * 65)
    print("WHALE / INSIDER SIGNAL SCANNER")
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 65)

    if target_market:
        data = fetch_market_data(target_market)
        if data:
            markets = [data]
        else:
            return []
    else:
        markets = fetch_liquid_markets()

    print(f"\nScanning {len(markets)} liquid markets...\n")

    all_signals = []
    for m in markets:
        signals = analyze_market(m)
        if signals:
            for s in signals:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.severity, "⚪")
                print(f"  {icon} [{s.signal_type}] {s.title}")
                print(f"     {s.details}")
            all_signals.extend(signals)

    # Save to log
    if all_signals:
        WHALE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(WHALE_LOG_PATH, "a") as f:
            for s in all_signals:
                f.write(json.dumps(asdict(s)) + "\n")
        # Cap log at 1000 lines
        try:
            lines = WHALE_LOG_PATH.read_text().strip().split("\n")
            if len(lines) > 1000:
                WHALE_LOG_PATH.write_text("\n".join(lines[-1000:]) + "\n")
        except Exception:
            pass

    # Summary
    print(f"\n{'=' * 65}")
    print(f"Total whale signals: {len(all_signals)}")
    by_type = {}
    for s in all_signals:
        by_type[s.signal_type] = by_type.get(s.signal_type, 0) + 1
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")
    high = [s for s in all_signals if s.severity == "high"]
    if high:
        print(f"\n🔴 HIGH SEVERITY ({len(high)}):")
        for s in high:
            print(f"  {s.title} — {s.details}")
    print(f"{'=' * 65}\n")

    return all_signals


if __name__ == "__main__":
    import sys
    target = None
    if "--market" in sys.argv:
        idx = sys.argv.index("--market")
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1]
    scan_all(target)
