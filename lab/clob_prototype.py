#!/usr/bin/env python3
"""
lab/clob_prototype.py
======================
Market microstructure feature extraction for PolySignal-OS.

Fetches bid/ask/spread/volume/liquidity from gamma-api for our tracked markets.
These features populate the CLOB stubs in feature_engineering.py.

Discovery (Session 21): Our 15 markets are AMM-only — no CLOB orderbook.
But gamma-api exposes bid/ask/spread/volume/liquidity for ALL markets.
This gives us 5 new feature dimensions without needing CLOB orderbooks.

Usage:
    python3 lab/clob_prototype.py                    # Fetch all tracked markets
    python3 lab/clob_prototype.py --market 1373744   # Specific market
"""

import json
import os
import sqlite3
import sys
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

GAMMA_BASE = "https://gamma-api.polymarket.com"
USER_AGENT = "PolySignal/1.0"
DB_PATH = os.getenv("DB_PATH", "/mnt/polysignal/data/test.db")
CACHE_PATH = Path("/mnt/polysignal/data/clob_features_cache.json")
REQUEST_TIMEOUT = 15


@dataclass
class MarketFeatures:
    """Microstructure features from gamma-api."""
    market_id: str
    timestamp: str
    clob_spread: float          # best_ask - best_bid
    clob_bid_ask_ratio: float   # best_bid / best_ask (proxy for pressure)
    clob_depth_imbalance: float # (volume24hr - avg) / avg (activity signal)
    clob_mid_price: float       # (best_bid + best_ask) / 2
    clob_order_count_ratio: float  # liquidity / volume (market efficiency)
    # Raw data for analysis
    best_bid: float
    best_ask: float
    volume_24h: float
    volume_1wk: float
    liquidity: float
    last_trade_price: float


def _api_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    resp = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
    return json.loads(resp.read())


def get_tracked_market_ids() -> List[str]:
    """Get market IDs from our observations DB."""
    try:
        db = sqlite3.connect(DB_PATH)
        c = db.cursor()
        c.execute("SELECT DISTINCT market_id FROM observations")
        ids = [str(r[0]) for r in c.fetchall()]
        db.close()
        return ids
    except Exception:
        return []


def fetch_market_features(market_id: str) -> Optional[MarketFeatures]:
    """Fetch microstructure features for one market from gamma-api."""
    try:
        data = _api_get(f"{GAMMA_BASE}/markets/{market_id}")
    except Exception as e:
        print(f"  ⚠ {market_id}: {e}")
        return None

    best_bid = float(data.get("bestBid") or 0)
    best_ask = float(data.get("bestAsk") or 0)
    spread = best_ask - best_bid if best_bid and best_ask else 0.0
    mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.5
    
    vol_24h = float(data.get("volume24hr") or 0)
    vol_1wk = float(data.get("volume1wk") or 0)
    liquidity = float(data.get("liquidityNum") or 0)
    last_price = float(data.get("lastTradePrice") or 0)
    
    # Derived features matching feature_engineering.py stubs:
    # bid_ask_ratio: buying pressure proxy
    bid_ask_ratio = best_bid / best_ask if best_ask > 0 else 0.0
    
    # depth_imbalance: volume momentum (24h vs weekly average)
    avg_daily = vol_1wk / 7 if vol_1wk > 0 else vol_24h
    depth_imbalance = (vol_24h - avg_daily) / avg_daily if avg_daily > 0 else 0.0
    
    # order_count_ratio: market efficiency (liquidity per unit volume)
    order_count_ratio = liquidity / vol_24h if vol_24h > 0 else 0.0

    return MarketFeatures(
        market_id=market_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        clob_spread=round(spread, 6),
        clob_bid_ask_ratio=round(bid_ask_ratio, 4),
        clob_depth_imbalance=round(depth_imbalance, 4),
        clob_mid_price=round(mid, 6),
        clob_order_count_ratio=round(order_count_ratio, 4),
        best_bid=best_bid,
        best_ask=best_ask,
        volume_24h=round(vol_24h, 2),
        volume_1wk=round(vol_1wk, 2),
        liquidity=round(liquidity, 2),
        last_trade_price=last_price,
    )


def save_cache(features: List[MarketFeatures]):
    """Save features for feature_engineering.py consumption."""
    cache = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": {f.market_id: asdict(f) for f in features},
    }
    with open(CACHE_PATH, "w") as fp:
        json.dump(cache, fp, indent=2)


def load_cache() -> Dict[str, dict]:
    """Load cached features. Returns {market_id: feature_dict}."""
    if not CACHE_PATH.exists():
        return {}
    try:
        with open(CACHE_PATH) as fp:
            return json.load(fp).get("features", {})
    except Exception:
        return {}


def get_clob_features_for_market(market_id: str) -> Optional[dict]:
    """Integration point for feature_engineering.py.
    
    Usage in feature_engineering.py:
        from lab.clob_prototype import get_clob_features_for_market
        clob = get_clob_features_for_market(market_id)
        if clob:
            fv.clob_spread = clob['clob_spread']
            fv.clob_bid_ask_ratio = clob['clob_bid_ask_ratio']
            fv.clob_depth_imbalance = clob['clob_depth_imbalance']
            fv.clob_mid_price = clob['clob_mid_price']
            fv.clob_order_count_ratio = clob['clob_order_count_ratio']
    """
    return load_cache().get(str(market_id))


def fetch_all(target: str = None) -> List[MarketFeatures]:
    """Main pipeline: fetch features for all tracked markets."""
    print("=" * 65)
    print("MARKET MICROSTRUCTURE FEATURE EXTRACTION")
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 65)

    ids = [target] if target else get_tracked_market_ids()
    print(f"\nFetching {len(ids)} markets from gamma-api...")

    results = []
    for mid in ids:
        f = fetch_market_features(mid)
        if f:
            results.append(f)
            icon = "🟢" if f.clob_spread < 0.03 else "🟡" if f.clob_spread < 0.10 else "🔴"
            print(f"  {icon} {mid}: spread=${f.clob_spread:.3f} mid=${f.clob_mid_price:.3f} "
                  f"vol24h=${f.volume_24h:,.0f} liq=${f.liquidity:,.0f} "
                  f"imbalance={f.clob_depth_imbalance:+.2f}")

    if results:
        save_cache(results)
        print(f"\nCached {len(results)} feature sets → {CACHE_PATH}")

    # Summary
    print(f"\n{'=' * 65}")
    tight = [r for r in results if r.clob_spread < 0.03]
    active = [r for r in results if r.volume_24h > 1000]
    bullish = [r for r in results if r.clob_depth_imbalance > 0.5]
    bearish = [r for r in results if r.clob_depth_imbalance < -0.3]
    print(f"Tight spread (<$0.03): {len(tight)}")
    print(f"Active (vol24h > $1K): {len(active)}")
    print(f"Volume surge (imbalance > +0.5): {len(bullish)}")
    print(f"Volume drop (imbalance < -0.3): {len(bearish)}")
    if results:
        best = max(results, key=lambda r: r.volume_24h)
        print(f"Highest volume: {best.market_id} (${best.volume_24h:,.0f}/24h)")
    print(f"{'=' * 65}\n")

    return results


if __name__ == "__main__":
    target = None
    if "--market" in sys.argv:
        idx = sys.argv.index("--market")
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1]
    
    results = fetch_all(target)
    if results:
        print("Feature vectors for XGBoost:")
        for r in results:
            print(json.dumps({
                "market_id": r.market_id,
                "clob_spread": r.clob_spread,
                "clob_bid_ask_ratio": r.clob_bid_ask_ratio,
                "clob_depth_imbalance": r.clob_depth_imbalance,
                "clob_mid_price": r.clob_mid_price,
                "clob_order_count_ratio": r.clob_order_count_ratio,
            }))
