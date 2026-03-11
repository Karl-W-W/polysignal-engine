# Loop Heartbeat Protocol
# Every 30 minutes, OpenClaw triggers a heartbeat. This is your playbook.
# Updated: Session 23 (2026-03-11)
# Principle: "Don't ask permission to be helpful. Just build it." — Ronin, MoltBook

---

## PHASE 0: ORIENT (30 seconds)

1. Read `lab/NOW.md` — your operational state
2. Check `lab/.scanner-status.json` — cycle count, errors, predictions
3. What time is it? → Determines which phase below

---

## DAYTIME HEARTBEAT (07:00–22:00 CET) — Monitor + Engage

### Step 1: Scanner Health (30 sec)
```bash
cat /mnt/polysignal/lab/.scanner-status.json
```
- If `errors > 0` → report on Telegram immediately
- If `predictions > 0` → note the count, check outcomes below

### Step 2: New Predictions Check (1 min)
```python
# Check for new evaluated predictions since last heartbeat
python3 -c "
import json
with open('/mnt/polysignal/data/prediction_outcomes.json') as f:
    data = json.load(f)
stats = data.get('stats', {})
print(f'Evaluated: {stats.get(\"evaluated\",0)} | Correct: {stats.get(\"correct\",0)} | Incorrect: {stats.get(\"incorrect\",0)}')
"
```
- If new evaluations exist → calculate accuracy on clean markets
- If accuracy drops below 60% → flag on Telegram

### Step 3: MoltBook Quick Check (1 min)
- Check notifications: `GET /api/v1/notifications`
- If someone commented on our posts → read and consider replying
- If high-relevance notification → note in Telegram heartbeat

### Step 4: Report (30 sec)
Telegram format: `HEARTBEAT: cycle {N}, {pred} predictions, {acc}% accuracy, {notes}`

---

## NIGHT HEARTBEAT (22:00–07:00 CET) — Learn + Build

### Step 1: Scanner Health (same as daytime)

### Step 2: MoltBook Deep Scan (3 min)
```bash
export MOLTBOOK_JWT=<from env>
python3 /mnt/polysignal/lab/moltbook_scanner.py all
```
- Read new high-relevance posts (score >= 0.6)
- Extract actionable techniques
- Write discoveries to `lab/LEARNINGS_TO_TASKS.md`

### Step 3: Build Something (5 min)
Pick ONE small task and do it:
- Improve a test
- Write a utility function
- Analyze prediction data
- Experiment with a feature
- Write a ClawHub skill review

Save work to lab/, push via git skill if confident.

### Step 4: Prepare Morning Briefing (2 min)
At the 06:30 heartbeat, compile:
- Overnight scanner stats
- MoltBook discoveries
- Any code written
- Prediction accuracy update
- Today's recommended priority

Post to Telegram as the morning briefing.

---

## WEEKLY HEARTBEAT (Sunday 22:00 CET)

1. Run full backtest: `python3 /mnt/polysignal/lab/backtester.py /mnt/polysignal/data/prediction_outcomes.json`
2. Compare to previous week's numbers
3. Update MEMORY.md with distilled learnings
4. Prune old learnings that are no longer relevant
5. Post weekly performance update to MoltBook trading submolt

---

## RULES

- **Never skip scanner health check** — it's the pipeline heartbeat
- **Night builds must have tests** — push only if tests pass
- **Don't burn tokens on status quo** — if nothing changed, say so in 1 line
- **Write discoveries to LEARNINGS_TO_TASKS.md, not just memory** — make them actionable
- **Check NOW.md first, always** — context before action
