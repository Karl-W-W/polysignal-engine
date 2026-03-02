# time_horizon Dead Field Audit
**Author:** Loop | **Date:** 2026-03-02 | **Status:** Complete

## Current State

`time_horizon` appears in 3 locations:

| Location | Usage | Value |
|----------|-------|-------|
| `core/signal_model.py:78` | Field definition | `Literal["1h","4h","24h","7d"]`, default `"24h"` |
| `core/signal_model.py:101` | `to_telegram_message()` | Always displays, always `"24h"` |
| `core/predict.py:21` | `Prediction.time_horizon` | Hardcoded `"24h"` |

**No code ever sets `time_horizon` to anything other than the default.**

## Who Reads It?

1. **Telegram alerts** — `to_telegram_message()` renders `*Horizon:* 24h`. User sees "24h" every time. No information content.
2. **Nothing else.** Not used in risk checks, not used in masterloop routing, not in the DB schema.

## Why It Exists

The original design intent (from ARCHITECTURE.md) was to express how long a signal remains valid. A 1h signal on a fast-moving market vs a 7d signal on a slow resolution. Good idea in theory.

## Options

### Option A: Derive from volatility (recommended)
Compute `time_horizon` in `bitcoin_signal.py` based on observable data:
```python
def derive_time_horizon(volume_24h: float, abs_delta: float) -> str:
    """Higher volatility = shorter horizon."""
    if abs_delta > 0.10 or volume_24h > 5_000_000:
        return "1h"   # Fast-moving, signal may decay quickly
    elif abs_delta > 0.05 or volume_24h > 1_000_000:
        return "4h"
    elif abs_delta > 0.02:
        return "24h"
    else:
        return "7d"   # Slow market, signal has longer shelf life
```
- Wire into `detect_signals()` → Signal constructor
- Prediction could also set its own horizon independently
- Risk gate could use it: shorter horizon = tighter stops

**Effort:** ~30 lines across 2 files. 1 test file.

### Option B: Remove it
Strip `time_horizon` from Signal, Prediction, and Telegram message. Dead code is worse than no code.

**Effort:** ~10 deletions. But loses the design intent.

### Option C: Leave it (not recommended)
Keep displaying "24h" in every Telegram alert. Adds noise, zero signal. Actively misleading if someone assumes it's computed.

## Recommendation

**Option A.** The field was designed for a reason. The data to compute it (volume, price delta) already exists in `detect_signals()`. Wire it up, use it in risk gate for position holding period hints. Small effort, real information gain.

## Implementation Plan (if approved)

1. `lab/time_horizon.py` — `derive_time_horizon()` function + tests
2. Patch `bitcoin_signal.py` → `detect_signals()` to call it when constructing Signal
3. Patch `core/predict.py` → derive from observation data instead of hardcoded
4. Risk gate: log horizon but don't enforce yet (future: auto-close stale positions)

**Vault edits required:** `core/predict.py` (1 line), `core/signal_model.py` (0 — field already correct)
**Lab edits:** `lab/experiments/bitcoin_signal.py`, new `lab/time_horizon.py`
