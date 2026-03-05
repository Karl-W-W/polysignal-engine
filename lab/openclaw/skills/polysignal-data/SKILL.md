---
name: polysignal-data
version: 1.0.0
description: Query PolySignal prediction and observation data
---

# PolySignal Data Query Skill

Query the production database and prediction outcomes without writing custom scripts.

## Database Locations
- **Observations DB**: `/mnt/polysignal/data/test.db` (SQLite, read-only)
- **Predictions JSON**: `/mnt/polysignal/data/prediction_outcomes.json` (read-only)

## Observation Queries

### Count total observations
```bash
sqlite3 /mnt/polysignal/data/test.db "SELECT COUNT(*) FROM observations;"
```

### Latest observations
```bash
sqlite3 /mnt/polysignal/data/test.db "SELECT market_id, title, price, timestamp FROM observations ORDER BY timestamp DESC LIMIT 10;"
```

### Observations per day
```bash
sqlite3 /mnt/polysignal/data/test.db "SELECT date(timestamp) as day, COUNT(*) as obs FROM observations GROUP BY day ORDER BY day DESC LIMIT 7;"
```

### Distinct markets being tracked
```bash
sqlite3 /mnt/polysignal/data/test.db "SELECT DISTINCT market_id, title FROM observations ORDER BY title;"
```

### Signal detection check (markets with direction)
```bash
sqlite3 /mnt/polysignal/data/test.db "SELECT market_id, direction, COUNT(*) as signals FROM observations WHERE direction != '' GROUP BY market_id, direction ORDER BY signals DESC;"
```

## Prediction Queries

### Full status report
```bash
/usr/local/bin/python3 -c "
import json
with open('/mnt/polysignal/data/prediction_outcomes.json') as f:
    d = json.load(f)
s = d['stats']
print(f'Total: {s[\"total_predictions\"]}, Evaluated: {s[\"total_evaluated\"]}')
print(f'Correct: {s[\"correct\"]}, Incorrect: {s[\"incorrect\"]}, Neutral: {s[\"neutral\"]}')
print(f'Accuracy: {s[\"accuracy\"]:.1%}')
pending = [p for p in d['predictions'] if not p['evaluated']]
real = [p for p in pending if not p['market_id'].startswith('0xfake')]
print(f'Pending evaluation: {len(real)} real, {len(pending)} total')
if real:
    oldest = min(p['timestamp'] for p in real)
    print(f'Oldest pending: {oldest}')
    horizons = {}
    for p in real:
        h = p.get('time_horizon', '4h')
        horizons[h] = horizons.get(h, 0) + 1
    print(f'By horizon: {horizons}')
"
```

### Check if XGBoost training is ready
```bash
/usr/local/bin/python3 -c "
import json
with open('/mnt/polysignal/data/prediction_outcomes.json') as f:
    d = json.load(f)
evaluated = [p for p in d['predictions'] if p['evaluated']]
print(f'Evaluated predictions: {len(evaluated)}')
print(f'Need 50+ for XGBoost training: {\"READY\" if len(evaluated) >= 50 else f\"NOT YET ({50 - len(evaluated)} more needed)\"}')
if evaluated:
    correct = sum(1 for p in evaluated if p['outcome'] == 'CORRECT')
    print(f'Current accuracy: {correct/len(evaluated):.1%}')
"
```

## Schema Reference
- **observations table**: market_id, title, price, volume, timestamp, direction, cycle_number, raw_data
- **prediction_outcomes.json**: dict with `predictions` list and `stats` summary
- Each prediction: market_id, hypothesis, confidence, price_at_prediction, timestamp, time_horizon, cycle_number, evaluated, outcome, actual_delta

## IMPORTANT: Task File Location
**`/mnt/polysignal/TASKS.md` is STALE** due to Docker inode caching on individual file bind mounts.
Read your tasks from: **`/mnt/polysignal/lab/LOOP_TASKS.md`** (syncs through directory mount).
