#!/usr/bin/env python3
"""
eval/resolution_backtest.py
===========================
Standalone, READ-ONLY backtest. Scores PolySignal's prediction history against
ACTUAL Polymarket market resolution (YES / NO) — not the 4h/24h price-drift
evaluator that produced the invalid 0.31 lifetime accuracy.

Context
-------
lab/.truth-board-status.json reports accuracy_lifetime = 0.31. That number is
produced by lab/outcome_tracker.py:343-357, which scores price drift over a
4h/24h window against MIN_MOVE_THRESHOLD = 0.0005 (line 115). 82% of all 598
verdicts rest on sub-0.5pp moves — i.e. tick noise. This script discards that
method and asks the only question that matters while trading is OFF:

    When the model made a directional call on a market, did that market
    actually resolve in the predicted direction?

Scoring rule
------------
A "Bullish" call = the market's tracked (index-0) price will rise = a bet that
the market resolves YES. A "Bearish" call = a bet it resolves NO. Therefore:

    Bullish  CORRECT  iff  market resolved YES
    Bearish  CORRECT  iff  market resolved NO

Only markets that have ACTUALLY resolved are scored. Unresolved markets are
counted and reported separately, never folded into the accuracy.

Dedup
-----
The history records the same standing call every 5-min cycle and doubles it
across 4h/24h horizons (outcome_tracker.py:282-286) — e.g. market 665374
appears 67x. A market resolves once; a directional call on it is right or
wrong once. Records are collapsed to ONE verdict per (market_id, hypothesis).

Safety
------
Read-only: opens prediction_outcomes.json in 'r'; issues only HTTP GETs to
gamma-api.polymarket.com. Additive: writes ONLY eval/resolution_results.json.
Imports nothing from the live pipeline; modifies no live code, data or service.

Run:  python3 eval/resolution_backtest.py
"""
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

OUTCOMES_FILE = os.getenv("OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json")
RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "resolution_results.json")
GAMMA = "https://gamma-api.polymarket.com"
Z95 = 1.959963985
HTTP_TRIES = 2
HTTP_TIMEOUT = 20
REQUEST_PAUSE_S = 0.35
UNDERPOWERED_N = 30  # below this many resolved markets, treat result as indicative only


def wilson_ci(k, n, z=Z95):
    """95% Wilson score interval — valid for small n and p near 0/1."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def http_get_json(url):
    last = None
    for attempt in range(HTTP_TRIES):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "polysignal-resolution-backtest/1.0"})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # URLError / HTTPError / timeout / JSON
            last = repr(e)
            time.sleep(1.0 * (attempt + 1))
    return {"_error": last or "exhausted"}


def as_list(v):
    """gamma returns outcomes / outcomePrices / clobTokenIds as JSON strings."""
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def pick_market(data, mid):
    cands = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
    for m in cands:
        if isinstance(m, dict) and str(m.get("id")) == str(mid):
            return m
    for m in cands:
        if isinstance(m, dict) and str(mid) in [str(t) for t in as_list(m.get("clobTokenIds"))]:
            return m
    return None


def fetch_resolution(mid):
    """Return (status, info). status in:
    resolved_yes | resolved_no | unresolved | ambiguous | not_found.
    'yes' = outcome index 0 (the side the scanner prices) won."""
    market = None
    for url in (f"{GAMMA}/markets?id={mid}",
                f"{GAMMA}/markets?clob_token_ids={mid}",
                f"{GAMMA}/markets/{mid}"):
        data = http_get_json(url)
        if isinstance(data, dict) and data.get("_error"):
            continue
        market = pick_market(data, mid)
        if market:
            break
    if market is None:
        return ("not_found", {})

    outcomes = as_list(market.get("outcomes"))
    prices = as_list(market.get("outcomePrices"))
    closed = bool(market.get("closed"))
    p0 = None
    if prices:
        try:
            p0 = float(prices[0])
        except Exception:
            p0 = None
    info = {
        "question": market.get("question"),
        "slug": market.get("slug"),
        "closed": closed,
        "uma_status": market.get("umaResolutionStatus"),
        "outcomes": outcomes,
        "outcome_prices": prices,
        "outcome0_price_now": p0,
        "end_date": market.get("endDate"),
    }
    if closed and p0 is not None and p0 >= 0.99:
        return ("resolved_yes", info)
    if closed and p0 is not None and p0 <= 0.01:
        return ("resolved_no", info)
    if closed:
        return ("ambiguous", info)  # closed but not a clean 1/0 (void / refund / multi)
    return ("unresolved", info)


def main():
    if not os.path.exists(OUTCOMES_FILE):
        print(f"FATAL: outcomes file not found: {OUTCOMES_FILE}", file=sys.stderr)
        return 2
    with open(OUTCOMES_FILE, "r") as f:
        doc = json.load(f)
    records = doc.get("predictions", [])
    print(f"loaded {len(records)} raw records from {OUTCOMES_FILE}")

    # ── Step 1: dedup to one verdict per (market_id, hypothesis) ──────────
    units = {}
    skipped = 0
    for r in records:
        mid = str(r.get("market_id") or "").strip()
        hyp = r.get("hypothesis")
        if not mid or mid.lower() == "none" or "fake" in mid.lower():
            skipped += 1
            continue
        if hyp not in ("Bullish", "Bearish"):
            skipped += 1
            continue
        ts = r.get("timestamp") or ""
        key = (mid, hyp)
        u = units.get(key)
        if u is None:
            units[key] = {
                "market_id": mid, "hypothesis": hyp, "raw_count": 1,
                "first_ts": ts, "last_ts": ts,
                "entry_price": r.get("price_at_prediction"),
            }
        else:
            u["raw_count"] += 1
            if ts and ts < u["first_ts"]:
                u["first_ts"] = ts
                u["entry_price"] = r.get("price_at_prediction")
            if ts and ts > u["last_ts"]:
                u["last_ts"] = ts
    units = list(units.values())
    dedup_factor = round(len(records) / len(units), 1) if units else None
    print(f"deduped: {len(records)} records -> {len(units)} unique "
          f"(market_id, hypothesis) verdicts  (x{dedup_factor}; {skipped} skipped)")

    # ── Step 2 & 3: resolution lookup + score ────────────────────────────
    for i, u in enumerate(units, 1):
        try:
            status, info = fetch_resolution(u["market_id"])
        except Exception as e:
            status, info = ("not_found", {"error": repr(e)})
        u["resolution_status"] = status
        u["market_question"] = info.get("question")
        u["outcomes"] = info.get("outcomes")
        u["outcome0_price_now"] = info.get("outcome0_price_now")
        u["uma_status"] = info.get("uma_status")
        if status in ("resolved_yes", "resolved_no"):
            yes = (status == "resolved_yes")
            u["resolved"] = True
            u["resolved_outcome"] = "YES" if yes else "NO"
            u["scored_correct"] = bool(yes if u["hypothesis"] == "Bullish" else not yes)
        else:
            u["resolved"] = False
            u["resolved_outcome"] = None
            u["scored_correct"] = None
        tag = ""
        if u["resolved"]:
            tag = f"  -> {u['resolved_outcome']}  ({'CORRECT' if u['scored_correct'] else 'INCORRECT'})"
        print(f"  [{i}/{len(units)}] {u['market_id']:>11}  {u['hypothesis']:<7}"
              f"  raw x{u['raw_count']:<4} {status}{tag}")
        time.sleep(REQUEST_PAUSE_S)

    # ── Step 4: accuracy over resolved markets ONLY ──────────────────────
    resolved = [u for u in units if u["resolved"]]
    R = len(resolved)
    k = sum(1 for u in resolved if u["scored_correct"])
    acc, lo, hi = wilson_ci(k, R)
    yes_n = sum(1 for u in resolved if u["resolved_outcome"] == "YES")
    no_n = R - yes_n
    entries = [u["entry_price"] for u in resolved if isinstance(u["entry_price"], (int, float))]
    avg_entry = (sum(entries) / len(entries)) if entries else None

    status_counts = {}
    for u in units:
        status_counts[u["resolution_status"]] = status_counts.get(u["resolution_status"], 0) + 1

    # contrast: what the un-deduped (raw-weighted) counting would report
    raw_total = sum(u["raw_count"] for u in resolved)
    raw_correct = sum(u["raw_count"] for u in resolved if u["scored_correct"])
    raw_weighted_acc = (raw_correct / raw_total) if raw_total else None

    # ── Verdict ──────────────────────────────────────────────────────────
    underpowered = R < UNDERPOWERED_N
    if R == 0:
        edge = None
        verdict = ("NO DATA: zero predicted markets have resolved — the model "
                   "has no evaluable track record. Edge cannot be assessed.")
    else:
        beats_coin = lo > 0.50
        worse_than_coin = hi < 0.50
        beats_price = (avg_entry is not None) and (lo > avg_entry)
        if beats_coin and beats_price:
            edge = True
            verdict = ("EDGE DEMONSTRATED: 95% CI lower bound exceeds both 0.50 "
                       "and the price-implied base rate.")
        elif worse_than_coin:
            edge = False
            verdict = ("ANTI-EDGE: 95% CI lies entirely below 0.50 — the calls "
                       "resolve against the model.")
        else:
            edge = False
            verdict = ("NO EDGE: 95% CI spans 0.50 / the price-implied base rate "
                       "— indistinguishable from chance.")
        if underpowered:
            verdict = f"UNDERPOWERED (N={R} < {UNDERPOWERED_N}) — {verdict}"

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "directional call scored vs actual Polymarket resolution (YES/NO)",
        "scoring_rule": "Bullish CORRECT iff resolved YES; Bearish CORRECT iff resolved NO",
        "source_file": OUTCOMES_FILE,
        "resolution_source": GAMMA,
        "raw_records": len(records),
        "unique_verdicts": len(units),
        "dedup_factor": dedup_factor,
        "resolution_status_counts": status_counts,
        "resolved": {
            "n": R,
            "correct": k,
            "incorrect": R - k,
            "accuracy": round(acc, 4) if R else None,
            "ci95_wilson": [round(lo, 4), round(hi, 4)] if R else None,
            "resolved_yes": yes_n,
            "resolved_no": no_n,
            "yes_resolution_rate": round(yes_n / R, 4) if R else None,
            "avg_entry_price": round(avg_entry, 4) if avg_entry is not None else None,
            "edge_vs_coinflip": round(acc - 0.50, 4) if R else None,
            "edge_vs_price_implied": (round(acc - avg_entry, 4)
                                      if (R and avg_entry is not None) else None),
        },
        "unresolved_n": len(units) - R,
        "contrast_raw_weighted_accuracy": (round(raw_weighted_acc, 4)
                                           if raw_weighted_acc is not None else None),
        "underpowered": underpowered,
        "edge": edge,
        "verdict": verdict,
        "markets": sorted(units, key=lambda u: (not u["resolved"], u["market_id"])),
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)

    # ── Console summary ──────────────────────────────────────────────────
    print("\n" + "=" * 66)
    print("RESOLUTION BACKTEST — RESULT")
    print("=" * 66)
    print(f"raw records ............ {len(records)}")
    print(f"unique verdicts ........ {len(units)}   (dedup x{dedup_factor})")
    print(f"resolution status ...... {status_counts}")
    print(f"RESOLVED  (scored) ..... {R}")
    print(f"UNRESOLVED (excluded) .. {len(units) - R}")
    if R:
        print(f"correct ................ {k} / {R}")
        print(f"REAL ACCURACY .......... {acc * 100:.1f}%   "
              f"95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%]")
        print(f"resolved YES / NO ...... {yes_n} / {no_n}")
        if avg_entry is not None:
            print(f"avg entry price ........ {avg_entry:.3f}  (price-implied base rate)")
            print(f"edge vs price-implied .. {(acc - avg_entry) * 100:+.1f} pp")
        print(f"edge vs coin flip ...... {(acc - 0.5) * 100:+.1f} pp")
        if raw_weighted_acc is not None:
            print(f"(contrast) raw-weighted  {raw_weighted_acc * 100:.1f}%  "
                  f"— what un-deduped counting would report")
    print(f"\nVERDICT: {verdict}")
    if resolved:
        print("\nresolved markets (scored):")
        print(f"  {'market_id':>11}  {'hyp':<7} {'entry':>6}  {'resolved':>8}  result")
        for u in sorted(resolved, key=lambda x: x["market_id"]):
            ep = u["entry_price"]
            eps = f"{ep:.3f}" if isinstance(ep, (int, float)) else "  ?  "
            print(f"  {u['market_id']:>11}  {u['hypothesis']:<7} {eps:>6}  "
                  f"{u['resolved_outcome']:>8}  "
                  f"{'CORRECT' if u['scored_correct'] else 'INCORRECT'}")
    print(f"\nwritten: {RESULTS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
