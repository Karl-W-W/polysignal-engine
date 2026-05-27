"""
lab/_resolution_lookup.py
=========================
Polymarket resolution lookup for the live evaluator (Session 46).

Extracted from eval/resolution_backtest.py (S44) to make the gamma-API
resolution check importable from the live evaluator (lab.outcome_tracker)
and unit-testable by monkeypatching _http_get_json.

Public API:
    lookup_resolution(market_id) -> (status, info)
        status: "resolved_yes" | "resolved_no" | "unresolved"
              | "ambiguous"    | "not_found"
        info:   {"question", "slug", "closed", "outcome0_price_now",
                 "outcome_prices", "outcomes", "uma_status", "end_date"}

A market is considered:
- resolved_yes: closed AND outcome0 price >= 0.99 (the side the scanner tracks won)
- resolved_no:  closed AND outcome0 price <= 0.01 (the tracked side lost)
- ambiguous:    closed but outcome0 in (0.01, 0.99) — refund / void / multi-outcome
- unresolved:   not closed yet
- not_found:    market not returned by gamma
"""

import json
import time
import urllib.request
from typing import Optional


GAMMA = "https://gamma-api.polymarket.com"
HTTP_TRIES = 2
HTTP_TIMEOUT = 20
RESOLVED_YES_THRESHOLD = 0.99
RESOLVED_NO_THRESHOLD = 0.01


def _http_get_json(url: str) -> dict:
    """Two-attempt GET with linear backoff. Monkeypatched in tests."""
    last_err: Optional[str] = None
    for attempt in range(HTTP_TRIES):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "polysignal-evaluator/1.0"},
            )
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = repr(e)
            time.sleep(1.0 * (attempt + 1))
    return {"_error": last_err or "exhausted"}


def _as_list(v) -> list:
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


def _pick_market(data, mid: str) -> Optional[dict]:
    """Pick the matching market from a gamma response (list or single dict).
    Match on id first, then on clobTokenIds membership."""
    cands = data if isinstance(data, list) else (
        [data] if isinstance(data, dict) else []
    )
    for m in cands:
        if isinstance(m, dict) and str(m.get("id")) == str(mid):
            return m
    for m in cands:
        if isinstance(m, dict) and str(mid) in [
            str(t) for t in _as_list(m.get("clobTokenIds"))
        ]:
            return m
    return None


def lookup_resolution(market_id: str) -> tuple[str, dict]:
    """Look up a Polymarket market's resolution status.

    Tries three gamma URL shapes in order; first hit wins.
    """
    market = None
    for url in (
        f"{GAMMA}/markets?id={market_id}",
        f"{GAMMA}/markets?clob_token_ids={market_id}",
        f"{GAMMA}/markets/{market_id}",
    ):
        data = _http_get_json(url)
        if isinstance(data, dict) and data.get("_error"):
            continue
        market = _pick_market(data, market_id)
        if market:
            break

    if market is None:
        return ("not_found", {})

    outcomes = _as_list(market.get("outcomes"))
    prices = _as_list(market.get("outcomePrices"))
    closed = bool(market.get("closed"))
    p0: Optional[float] = None
    if prices:
        try:
            p0 = float(prices[0])
        except Exception:
            p0 = None

    info = {
        "question": market.get("question"),
        "slug": market.get("slug"),
        "closed": closed,
        "outcomes": outcomes,
        "outcome_prices": prices,
        "outcome0_price_now": p0,
        "uma_status": market.get("umaResolutionStatus"),
        "end_date": market.get("endDate"),
    }

    if closed and p0 is not None and p0 >= RESOLVED_YES_THRESHOLD:
        return ("resolved_yes", info)
    if closed and p0 is not None and p0 <= RESOLVED_NO_THRESHOLD:
        return ("resolved_no", info)
    if closed:
        return ("ambiguous", info)
    return ("unresolved", info)
