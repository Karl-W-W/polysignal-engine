# MoltBook Publisher — DGX Verification Checklist
**Author:** Loop | **Date:** 2026-03-02

## Code Review: PASS

The publisher (lab/moltbook_publisher.py) is well-structured:
- Config: MoltBookConfig.from_env() reads MOLTBOOK_JWT, MOLTBOOK_API_BASE, MOLTBOOK_DRY_RUN
- Rate limiting: 4h minimum between posts
- Dedup: SHA-256 hash of market_id:hypothesis:price
- State persistence: JSON at /opt/loop/data/moltbook_state.json
- Dry run mode: MOLTBOOK_DRY_RUN=true formats but does not POST
- Graceful failure: API errors return PublishResult(published=False)

## Test Coverage: PASS (from code review)
tests/test_moltbook_publisher.py covers: formatting, state, hashing, dry run, rate limit, dedup, live mock, error handling.

## DGX Verification Commands (run on host)

### 1. Tests pass
    cd /opt/loop && python3 -m pytest tests/test_moltbook_publisher.py -v

### 2. Environment configured
    echo "MOLTBOOK_JWT set: $([ -n "$MOLTBOOK_JWT" ] && echo YES || echo NO)"

### 3. Network access
    curl -s -o /dev/null -w "%{http_code}" https://www.moltbook.com/api/v1/health

### 4. Dry run smoke test
    cd /opt/loop && MOLTBOOK_DRY_RUN=true MOLTBOOK_JWT=test python3 -c "
    from core.signal_model import Signal, SignalSource
    from lab.moltbook_publisher import publish_signal, MoltBookConfig
    config = MoltBookConfig.from_env()
    sig = Signal(market_id='0xtest', title='Verification', outcome='Yes',
        polymarket_url='https://polymarket.com/event/test',
        current_price=0.65, volume_24h=1000000, change_since_last=0.07,
        hypothesis='Bullish', confidence=0.82,
        source=SignalSource(method='test', raw_value=0.07, threshold=0.05),
        reasoning='Dry run.')
    r = publish_signal(sig, {'perception':1,'prediction':0.5,'draft':0.3,'review':0.2,'commit':0.1}, 'verify123', config)
    print(f'Published: {r.published}  Reason: {r.reason}')
    print(r.body)"

## INTEGRATION GAP FOUND

The publisher is built but never called. No code path from masterloop commit to publish_signal().

Proposed fix in workflows/masterloop.py commit_node, after SUCCESS:

    if state["execution_status"] == "SUCCESS":
        try:
            from lab.moltbook_publisher import publish_signal, MoltBookConfig
            config = MoltBookConfig.from_env()
            signal_obs = [o for o in state.get("observations", []) if o.get("direction")]
            if signal_obs:
                audit_hash = state.get("signature", "no_sig")[:24]
                result = publish_signal(signal_obs[0], state["stage_timings"], audit_hash, config)
                if result.published:
                    print(f"  Published to MoltBook: {result.post_id}")
        except Exception as e:
            print(f"  MoltBook publish failed (non-blocking): {e}")

This keeps it non-blocking -- MoltBook failure does not break the trade.
