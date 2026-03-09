#!/usr/bin/env python3
"""Live Polymarket data fetch — compares gamma-api events with local observations.

Usage: python3 lab/live_market_fetch.py
"""
import json
import sqlite3
import urllib.request
from datetime import datetime, timezone


def fetch_polymarket_events(tag="crypto", limit=20):
    """Fetch active events from gamma-api."""
    url = f"https://gamma-api.polymarket.com/events?tag={tag}&limit={limit}&active=true"
    req = urllib.request.Request(url, headers={"User-Agent": "PolySignal/1.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())


def get_local_markets(db_path="/mnt/polysignal/data/test.db"):
    """Get markets we're tracking locally."""
    db = sqlite3.connect(db_path)
    c = db.cursor()
    c.execute("""
        SELECT DISTINCT market_id,
               COUNT(*) as obs_count,
               MAX(timestamp) as latest
        FROM observations
        GROUP BY market_id
        ORDER BY obs_count DESC
    """)
    rows = c.fetchall()
    db.close()
    return {r[0]: {"obs_count": r[1], "latest": r[2]} for r in rows}


def main():
    print("=" * 70)
    print("POLYSIGNAL LIVE MARKET REPORT")
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    # Fetch live data
    events = fetch_polymarket_events()
    local = get_local_markets()

    print(f"\n📡 Live Polymarket crypto events: {len(events)}")
    print(f"📦 Local tracked markets: {len(local)}")

    # Show live events with prices
    print(f"\n{'Title':50} {'Markets':>7} {'Volume':>12}")
    print("-" * 70)
    for ev in events[:15]:
        title = ev.get("title", "?")[:49]
        n_markets = len(ev.get("markets", []))
        # Sum volume across markets
        total_vol = sum(
            float(m.get("volume", 0) or 0) for m in ev.get("markets", [])
        )
        vol_str = f"${total_vol:,.0f}" if total_vol else "N/A"
        print(f"{title:50} {n_markets:>7} {vol_str:>12}")

    # Cross-reference: which live markets are we tracking?
    print("\n" + "=" * 70)
    print("CROSS-REFERENCE: Live Markets vs Local Observations")
    print("=" * 70)

    live_market_ids = set()
    for ev in events:
        for m in ev.get("markets", []):
            cid = m.get("conditionId") or m.get("condition_id", "")
            if cid:
                live_market_ids.add(cid)

    tracked_and_live = live_market_ids & set(local.keys())
    tracked_not_live = set(local.keys()) - live_market_ids
    live_not_tracked = live_market_ids - set(local.keys())

    print(f"\n✅ Tracked & live:     {len(tracked_and_live)}")
    print(f"⚠️  Tracked, not live: {len(tracked_not_live)} (may have resolved)")
    print(f"🆕 Live, not tracked:  {len(live_not_tracked)} (potential new markets)")

    # Detail on tracked markets
    if local:
        print(f"\n{'Market ID':15} {'Obs':>6} {'Latest Observation':>25}")
        print("-" * 50)
        for mid, info in sorted(local.items(), key=lambda x: x[1]["obs_count"], reverse=True):
            status = "✅" if mid in live_market_ids else "⚠️"
            print(f"{status} {mid[:12]:12} {info['obs_count']:>6} {info['latest']:>25}")

    print("\n" + "=" * 70)
    print("END REPORT")


if __name__ == "__main__":
    main()
