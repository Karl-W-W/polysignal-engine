# Loop Heartbeat Protocol
# Updated: Session 27 (2026-03-17) — Autonomy Upgrade Phase 1
# Heartbeat = checkpoint, NOT work trigger. You work BETWEEN heartbeats.

---

## COST DISCIPLINE

With Nemotron-3-Super local ($0/token), heartbeats are FREE.
BUT: don't waste time on empty reports. Produce output or stay silent.

**Rules:**
- If nothing changed AND no work to do: `HEARTBEAT_OK` is acceptable
- Produce OUTPUT (code, analysis, engagement), not status reports
- Every heartbeat: report what you DID, not what you SAW

---

## HEARTBEAT OUTPUT FORMAT (NEW)

Replace `HEARTBEAT_OK` with structured output:

```
HEARTBEAT — [timestamp]
Since last beat: [completed N tasks / built X / engaged Y]
Active: [current task or "idle — entering Discovery Mode"]
Queue: [N pending, M blocked]
Next: [what you'll do in the next 30 min]
Alerts: [none / or: specific issues requiring attention]
```

If truly nothing happened AND no work to do: `HEARTBEAT_OK` is still acceptable.

---

## THE WORK LOOP (between heartbeats)

You are NOT a cron job. Between heartbeats, run this loop:

```
1. Check task queue (lab/LOOP_TASKS.md)
2. Pick highest-priority task tagged for Loop
3. Verify task is on the Proactive Allowlist (see below)
4. Execute task
5. Log result to lab/work_log.md with timestamp
6. If task generated follow-up work, note it
7. Check: has 25 minutes passed since last heartbeat?
   - Yes: prepare heartbeat summary, wait for beat
   - No: go to step 1
8. If queue is empty: enter Discovery Mode
```

---

## DISCOVERY MODE (when queue is empty)

Check these sources in priority order:
1. **Scanner output**: patterns, anomalies, false-positive rates
2. **Prediction data**: accuracy trends, market behavior changes
3. **MoltBook**: new posts, trending topics, intelligence
4. **Code quality**: dead code, missing tests, documentation gaps
5. **Self-assessment**: review work_log, calculate productivity metrics

Discovery work is always lower priority than queued tasks.

---

## PROACTIVE ALLOWLIST (do these without asking)

**Analysis and insight generation**
- Run statistical analysis on scanner output
- Generate summaries from prediction data
- Benchmark model performance
- Mine work logs for patterns

**Code — read and draft only**
- Read any accessible repository
- Run linters and test suites
- Draft code on feature branches (never main)
- Generate test cases for untested functions

**Content**
- Draft MoltBook posts (save to drafts, don't post without approval)
- Write documentation and analysis reports
- Compile briefings and digests

**Self-maintenance**
- Update lab/LOOP_TASKS.md with discovered work
- Write to lab/work_log.md
- Archive old log entries

---

## APPROVAL-REQUIRED (always ask first)

- Deploying code (writing to .deploy-trigger)
- Posting to MoltBook publicly
- Installing packages or skills
- Modifying any config file
- Deleting any file (archiving is fine)
- Any action that costs money

---

## PHASE 0: ORIENT (30 seconds)

1. Check `lab/.events.jsonl` — new events since last heartbeat?
2. Check `lab/.watchdog-alerts` — any alert_count > 0?
3. Check `lab/.scanner-status.json` — cycle count, errors
4. What time is it? Day/Night/Weekly determines phase

---

## DAYTIME (07:00-22:00 CET) — Monitor + Act + Build

### Step 1: Quick Status (15 sec)
- Check events, watchdog, scanner status
- If errors > 0: investigate and report immediately
- If nothing changed: skip status, go to Step 2

### Step 2: Do Something Productive (remaining time)
Pick the highest-impact item:
- Execute a task from LOOP_TASKS.md
- Write analysis from prediction data
- Engage on MoltBook with real data
- Run a code improvement and push to loop/*

---

## NIGHT (22:00-07:00 CET) — Learn + Build + Prepare

### Phase 1: Build (22:00-01:00)
Pick ONE item from open tasks. Build it. Test it. Push it.

### Phase 2: MoltBook Scan (01:00-04:00)
Run `moltbook_scanner.py all`. Extract intelligence.
Write findings to `lab/LEARNINGS_TO_TASKS.md`.

### Phase 3: Morning Briefing (04:00-06:00)
Compile: overnight work, MoltBook findings, scanner stats,
accuracy update, recommended priorities for today.

### Phase 4: Rest (06:00-07:00)
Heartbeat-only. No new work. Let KWW wake up to a clean state.

---

## WEEKLY (Sunday 22:00 CET)

1. Run full backtest
2. Compare to previous week
3. Calculate weekly scorecard metrics
4. Update MEMORY.md with distilled learnings
5. Post weekly performance to MoltBook (if approved)

---

## RULES

- **Heartbeats are checkpoints, not work triggers**
- **Work happens BETWEEN heartbeats**
- **Night builds must have tests**
- **Log everything to work_log.md**
- **If uncertain whether to act: ask**
- **Default to doing something useful over reporting nothing**
