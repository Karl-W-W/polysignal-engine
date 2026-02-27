"""
lab/masterloop_perception_patch.py
====================================
LAB EXPERIMENT — NOT promoted to /core or /workflows.

Objective:
  Drop-in replacement for the `perception_node` in workflows/masterloop.py.
  Uses proven bitcoin_signal.py logic instead of the generic observe_markets().

Promotion Criteria:
  [ ] Standalone test passes: python3 lab/masterloop_perception_patch.py
  [ ] output dict keys match LoopState["observations"] schema
  [ ] Human explicitly authorizes applying the diff to workflows/masterloop.py

Usage (standalone test):
  cd polysignal-engine/
  python3 lab/masterloop_perception_patch.py

Promotion path (AFTER authorization only):
  Replace `perception_node` in workflows/masterloop.py with the function below.
  Remove the `from core.perceive import observe_markets` import.
"""

import os
import sys
import json
from datetime import datetime, timezone

# ── Make lab imports resolvable when run from polysignal-engine/ ──────────────
_ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

from lab.experiments.bitcoin_signal import fetch_crypto_markets, detect_signals


# ── Observation schema expected by LoopState["observations"] ─────────────────
# (Matches what prediction_node reads downstream)
#
#   {
#       "market_id":     str   — Polymarket market ID
#       "title":         str   — human-readable market title
#       "price":         float — current YES price (0-1)
#       "volume":        float — USD volume
#       "change_24h":    float — delta vs last DB observation (labelled for compat)
#       "timestamp":     str   — ISO-8601 UTC
#       "source":        str   — always "polymarket"
#       "direction":     str   — "📈 Bullish" | "📉 Bearish" (signals only)
#       "url":           str   — trade URL
#   }


def _market_to_observation(m: dict) -> dict:
    """
    Convert a raw crypto market dict (from fetch_crypto_markets) into the
    normalized observation format that LoopState expects.
    """
    return {
        "market_id":  m["id"],
        "title":      f"{m['title']} — {m['outcome']}",
        "price":      m["price"],
        "volume":     m["volume"],
        "change_24h": 0.0,       # No prior data yet; will be non-zero on signals
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "source":     "polymarket",
        "direction":  "",
        "url":        m["url"],
    }


def _signal_to_observation(sig: dict) -> dict:
    """
    Convert a detected signal dict (from detect_signals) into the normalized
    observation format, with the real delta populated.
    """
    return {
        "market_id":  sig["market_id"],
        "title":      f"{sig['title']} — {sig['outcome']}",
        "price":      sig["current_price"],
        "volume":     sig["volume"],
        "change_24h": sig["delta"],   # Real measured move
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "source":     "polymarket",
        "direction":  sig["direction"],
        "url":        sig["url"],
    }


# ── Drop-in perception_node ───────────────────────────────────────────────────

def perception_node(state: dict) -> dict:
    """
    Replacement for the generic perception_node in workflows/masterloop.py.

    Instead of calling observe_markets() (which scans any top-10 market),
    this targets crypto/BTC markets specifically and uses the proven
    bitcoin_signal.py detection logic.

    Compatible with LoopState: reads/writes state["observations"] and
    state["errors"], updates state["stage_timings"]["perception"].
    """
    print("\n[PERCEPTION] Scanning crypto markets...")
    start = datetime.now(timezone.utc)

    try:
        # 1. Fetch live crypto markets from Polymarket Gamma API
        markets = fetch_crypto_markets()

        if not markets:
            print("  ⚠ No crypto markets returned from API")
            state["observations"] = []
            state["errors"].append("Perception: No markets returned")
        else:
            # 2. Detect signals (compares against DB, inserts new observations)
            signals = detect_signals(markets)

            if signals:
                # Signal run: emit only the markets that fired (rich data)
                state["observations"] = [_signal_to_observation(s) for s in signals]
                print(f"  🔔 {len(signals)} signal(s) detected:")
                for s in signals:
                    print(f"     {s['direction']}  {s['title'][:50]}  {s['delta']:+.3f}")
            else:
                # Quiet run: emit baseline observations (no delta yet)
                state["observations"] = [_market_to_observation(m) for m in markets]
                print(f"  ✓ {len(markets)} markets observed, 0 signals (quiet market)")

    except Exception as e:
        print(f"  ✗ Perception failed: {e}")
        state.setdefault("observations", [])
        state.setdefault("errors", []).append(f"Perception: {e}")

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    state.setdefault("stage_timings", {})["perception"] = elapsed
    print(f"  ⏱ {elapsed:.2f}s")
    return state


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("masterloop_perception_patch — Standalone Test")
    print("=" * 60)

    # Minimal mock state (mirrors LoopState initial dict in masterloop.py)
    mock_state = {
        "thread_id":             "patch_test_001",
        "cycle_number":          1,
        "started_at":            datetime.now(timezone.utc).isoformat(),
        "user_request":          "scan crypto markets",
        "observations":          [],
        "predictions":           [],
        "draft_action":          None,
        "draft_reasoning":       None,
        "audit_verdict":         None,
        "signature":             None,
        "human_approval_needed": False,
        "human_approved":        None,
        "execution_result":      None,
        "execution_status":      None,
        "errors":                [],
        "stage_timings":         {},
    }

    result_state = perception_node(mock_state)

    print(f"\n{'='*60}")
    print(f"RESULT: {len(result_state['observations'])} observation(s) in state")
    print(f"ERRORS: {result_state['errors']}")
    print(f"TIMING: {result_state['stage_timings']}")

    if result_state["observations"]:
        print("\nFirst observation (schema check):")
        print(json.dumps(result_state["observations"][0], indent=2))

        # Schema validation: assert required keys are present
        REQUIRED_KEYS = {"market_id", "title", "price", "volume",
                         "change_24h", "timestamp", "source"}
        obs = result_state["observations"][0]
        missing = REQUIRED_KEYS - obs.keys()
        if missing:
            print(f"\n❌ SCHEMA FAIL: missing keys: {missing}")
            sys.exit(1)
        else:
            print("\n✅ Schema OK — all required keys present")
            print("✅ Patch is ready for human diff review")
    else:
        print("\n⚠ No observations — check API connectivity or DB path")
