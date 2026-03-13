# Loop Heartbeat Protocol
# Every 30 minutes, OpenClaw triggers a heartbeat. This is your playbook.
# Updated: Session 25 (2026-03-13)
# Principle: "Don't ask permission to be helpful. Just build it." — Ronin, MoltBook

---

## COST DISCIPLINE (READ THIS FIRST)

Every heartbeat costs money. Opus 4.6 output tokens are $25/MTok. A single heartbeat
that generates 4k output tokens costs ~$0.10. Thinking tokens count as output.

**Rules:**
- If nothing changed since last heartbeat, say it in ONE LINE and stop
- Do NOT re-read NOW.md every heartbeat — only if you lost context
- Do NOT generate long analysis when a 2-line status update suffices
- Produce OUTPUT, not status reports. Ship code, make trades, engage on MoltBook.
- If your heartbeat would just be "Scanner OK, no signals" — skip the report

**Cost math:** 48 heartbeats/day x $0.10 = $4.80/day minimum. Make each one count.

---

## PHASE 0: ORIENT (30 seconds)

1. Check `lab/.scanner-status.json` — cycle count, errors, predictions
2. What time is it? → Determines which phase below
3. Only read `lab/NOW.md` if you don't remember your state

---

## DAYTIME HEARTBEAT (07:00–22:00 CET) — Monitor + Act

### Step 1: Quick Status (15 sec)
```bash
cat /mnt/polysignal/lab/.scanner-status.json
```
- If `errors > 0` → report on Telegram immediately
- If `predictions > 0` → check paper trading log
- If nothing changed → **stop here**, no report needed

### Step 2: Paper Trading + Accuracy (only if new data)
```bash
python3 -c "
import json
with open('/mnt/polysignal/lab/trading_log.json') as f:
    trades = json.load(f)
approved = [t for t in trades if t.get('risk_verdict') == 'APPROVED']
print(f'Paper trades: {len(approved)} approved / {len(trades)} total')
if approved: print(f'Latest: {approved[-1].get(\"market_id\",\"?\")} {approved[-1].get(\"side\",\"?\")} @ {approved[-1].get(\"confidence\",0):.0%}')
"
```
- Only report if there are NEW trades since last heartbeat

### Step 3: Do Something Productive (remaining time)
Instead of checking MoltBook notifications, PICK ONE:
- Write a MoltBook post with real data
- Comment on a trending post with our accuracy numbers
- Analyze a market's base rate and push to loop/*
- Trigger a retrain if we have enough data

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
